"""API FastAPI do Solver Estatística."""

from __future__ import annotations

import io
import json
import os
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
    alpha: float = 0.05
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
    """Recebe CSV/XLSX e um JSON de configuração para análise."""
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


async def _read_uploaded_table(file: UploadFile) -> pd.DataFrame:
    raw = await file.read()
    name = (file.filename or "").lower()
    if name.endswith(".csv"):
        try:
            return pd.read_csv(io.BytesIO(raw), sep=None, engine="python")
        except Exception:
            return pd.read_csv(io.BytesIO(raw), sep=";")
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(raw))
    raise ValueError("Formato não suportado. Envie CSV, XLS ou XLSX.")
