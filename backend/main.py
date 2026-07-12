"""API FastAPI do Solver Estatística."""

from __future__ import annotations

import io
import json
import os
import re
from typing import Any, Dict, Optional

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from exporters import build_excel, build_pdf, build_regression_plot
from statistics_engine import analyze


class AnalyzePayload(BaseModel):
    design: str = Field("DIC", description="DIC, DBC ou DQL")
    analysis_type: str = Field("single", description="single, factorial, split_plot ou regression")
    response_column: str = "valor"
    treatment_column: str = "tratamento"
    block_column: Optional[str] = "bloco"
    row_column: Optional[str] = "linha"
    column_column: Optional[str] = "coluna"
    factor_columns: list[str] = Field(default_factory=list)
    numeric_factor_column: Optional[str] = None
    dose_column: Optional[str] = None
    comparison_test: str = "tukey"
    control_group: Optional[str] = None
    regression_degree: Optional[int] = None
    goal: str = "max"
    alpha: float = Field(
        0.05,
        description=(
            "Não é mais usado para o pós-teste de comparação de médias: o nível de "
            "significância (1% ou 5%) agora é herdado automaticamente do teste F de cada "
            "fonte de variação (tratamento, fator ou interação). Campo mantido só por "
            "compatibilidade de API."
        ),
    )
    data: list[dict[str, Any]]


app = FastAPI(
    title="Solver Estatística API",
    version="0.1.0",
    description="Backend para ANOVA, comparação de médias, regressão e exportações do Solver.",
)

origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> Dict[str, str]:
    return {"service": "Solver Estatística API", "status": "online"}


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze")
def analyze_endpoint(payload: AnalyzePayload) -> Dict[str, Any]:
    try:
        return analyze(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro interno na análise: {exc}") from exc


@app.post("/api/analyze-upload")
async def analyze_upload(config: str = Form(...), file: UploadFile = File(...)) -> Dict[str, Any]:
    """Recebe CSV (separado por ;) e um JSON de configuração para análise."""
    try:
        payload = json.loads(config)
        df = await _read_uploaded_table(file)
        payload["data"] = df.to_dict(orient="records")
        return analyze(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao processar arquivo: {exc}") from exc


@app.post("/api/export/pdf")
def export_pdf(payload: AnalyzePayload) -> Response:
    try:
        content = build_pdf(payload.model_dump())
        return Response(
            content,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=solver-relatorio.pdf"},
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/export/excel")
def export_excel(payload: AnalyzePayload) -> Response:
    try:
        content = build_excel(payload.model_dump())
        return Response(
            content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=solver-resultados.xlsx"},
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/export/regression-plot")
def export_regression_plot(payload: AnalyzePayload, fmt: str = "png") -> Response:
    try:
        fmt = fmt.lower()
        if fmt not in {"png", "pdf"}:
            raise ValueError("Formato inválido. Use png ou pdf.")
        content = build_regression_plot(payload.model_dump(), fmt=fmt)
        media = "image/png" if fmt == "png" else "application/pdf"
        filename = f"solver-regressao.{fmt}"
        return Response(content, media_type=media, headers={"Content-Disposition": f"attachment; filename={filename}"})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


_BR_NUMBER_RE = re.compile(r"^-?\d{1,3}(\.\d{3})*,\d+$|^-?\d+,\d+$|^-?\d+$")


def _looks_brazilian_numeric(series: pd.Series) -> bool:
    """Detecta coluna com decimal ',' (padrão brasileiro), ex.: '12,5' ou '1.234,56'."""
    values = series.dropna().astype(str).str.strip()
    if values.empty:
        return False
    has_comma = values.str.contains(",", regex=False)
    if not has_comma.any():
        return False
    return bool(values.apply(lambda v: bool(_BR_NUMBER_RE.match(v))).all())


def _normalize_brazilian_decimals(df: pd.DataFrame) -> pd.DataFrame:
    """Converte colunas de texto com decimal ',' para float, sem mexer em colunas de
    rótulo (tratamento, bloco etc.). Corrige o 422 relatado quando o CSV vem no padrão
    brasileiro (separador ';' e decimal ',') e a coluna de resposta chega como texto."""
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == object and _looks_brazilian_numeric(df[col]):
            df[col] = (
                df[col]
                .astype(str)
                .str.strip()
                .str.replace(".", "", regex=False)
                .str.replace(",", ".", regex=False)
                .astype(float)
            )
    return df


async def _read_uploaded_table(file: UploadFile) -> pd.DataFrame:
    """Lê o arquivo enviado pelo usuário. Entrada padronizada: somente CSV separado por
    ponto e vírgula (;), o padrão do Excel em português (BR), onde a vírgula já é o
    separador decimal. A versão anterior tentava adivinhar o separador (sep=None) e ainda
    aceitava XLS/XLSX; isso deixava a causa de um erro de formatação difícil de identificar."""
    raw = await file.read()
    name = (file.filename or "").lower()
    if not name.endswith(".csv"):
        raise ValueError(
            "Formato não suportado. Envie um arquivo CSV separado por ponto e vírgula (;)."
        )
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "Não foi possível ler a codificação do arquivo. Salve o CSV como UTF-8 e tente novamente."
        ) from exc
    try:
        df = pd.read_csv(io.StringIO(text), sep=";")
    except Exception as exc:
        raise ValueError(
            "Não foi possível ler o CSV. Confirme que as colunas estão separadas por ponto e vírgula (;)."
        ) from exc
    if df.shape[1] < 2:
        raise ValueError(
            "O arquivo parece ter uma única coluna. Confirme que o separador usado é ponto e vírgula (;), não vírgula."
        )
    df.columns = [str(c).strip() for c in df.columns]
    return _normalize_brazilian_decimals(df)
