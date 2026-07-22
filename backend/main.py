"""API FastAPI do Solver Estatística."""

from __future__ import annotations

import io
import json
import logging
import os
import re
import threading
import time
import uuid
from collections import defaultdict, deque
from typing import Any, Dict, Optional

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from exporters import build_excel, build_means_plot, build_pdf, build_regression_plot
from provenance import ENGINE_VERSION
from statistics_engine import analyze


logger = logging.getLogger("solver.api")
MAX_REQUEST_BYTES = int(os.getenv("MAX_REQUEST_BYTES", str(5 * 1024 * 1024)))
MAX_UPLOAD_BYTES = MAX_REQUEST_BYTES
MAX_DATA_ROWS = int(os.getenv("MAX_DATA_ROWS", "10000"))
MAX_CONCURRENT_ANALYSES = int(os.getenv("MAX_CONCURRENT_ANALYSES", "2"))
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
# Em producao, habilite apenas quando o proxy reverso substituir X-Forwarded-For
# pelo IP real do cliente. Sem essa garantia, o cabecalho e forjavel e permitiria
# contornar o limite de requisicoes.
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "false").lower() in {"1", "true", "yes"}
_analysis_semaphore = threading.BoundedSemaphore(MAX_CONCURRENT_ANALYSES)
_request_times: Dict[str, deque[float]] = defaultdict(deque)


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
    sum_squares_type: int = Field(2, ge=1, le=3)
    goal: str = "max"
    author_name: Optional[str] = Field(default=None, max_length=80, description="Nome exibido na capa do laudo em PDF. Vazio = laudo sem nome pessoal.")
    alpha_mode: str = Field(
        "auto",
        description=(
            "'auto' (padrão): o alfa do pós-teste é herdado do nível de significância do "
            "próprio teste F (1% ou 5%) para cada fonte de variação — convenção de Pimentel "
            "Gomes. 'fixed': usa o valor de 'alpha' abaixo em toda a análise, independente do "
            "resultado do teste F."
        ),
    )
    alpha: float = Field(
        0.05,
        gt=0,
        lt=1,
        description="Usado apenas quando alpha_mode='fixed'. Ignorado quando alpha_mode='auto'.",
    )
    data: list[dict[str, Any]] = Field(min_length=2, max_length=MAX_DATA_ROWS)


app = FastAPI(
    title="Solver Estatística API",
    version=ENGINE_VERSION,
    description="Backend para ANOVA, comparação de médias, regressão e exportações do Solver.",
)

_default_origins = (
    "https://www.solver-estatistica.com.br,"
    "https://solver-estatistica.com.br,"
    "https://solverestatistica-brazil.github.io"
)
origins = [o.strip() for o in os.getenv("CORS_ORIGINS", _default_origins).split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def production_guards(request: Request, call_next):
    """Rejeita payloads declaradamente grandes e adiciona cabeçalhos defensivos."""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_REQUEST_BYTES:
                return Response("Requisição muito grande.", status_code=413)
        except ValueError:
            return Response("Content-Length inválido.", status_code=400)
    if request.url.path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH"}:
        forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        client = (
            forwarded
            if TRUST_PROXY_HEADERS and forwarded
            else (request.client.host if request.client else "unknown")
        )
        now = time.monotonic()
        bucket = _request_times[client]
        while bucket and now - bucket[0] >= 60:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT_PER_MINUTE:
            return JSONResponse(
                status_code=429,
                content={"detail": "Limite de requisições excedido. Aguarde um minuto e tente novamente."},
                headers={"Retry-After": "60", "X-Request-ID": request_id},
            )
        bucket.append(now)
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    logger.info(
        "request_id=%s method=%s path=%s status=%s duration_ms=%s",
        request_id, request.method, request.url.path, response.status_code, elapsed_ms,
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["X-Request-ID"] = request_id
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def _acquire_analysis_slot() -> None:
    if not _analysis_semaphore.acquire(blocking=False):
        raise HTTPException(
            status_code=503,
            detail="O serviço está processando outras análises. Tente novamente em instantes.",
            headers={"Retry-After": "5"},
        )


def _internal_error(context: str) -> HTTPException:
    error_id = uuid.uuid4().hex[:12]
    logger.exception("Falha interna em %s [id=%s]", context, error_id)
    return HTTPException(
        status_code=500,
        detail=f"Erro interno inesperado. Informe o código {error_id} ao suporte.",
    )


@app.get("/")
def root() -> Dict[str, str]:
    return {"service": "Solver Estatística API", "status": "online", "version": ENGINE_VERSION}


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "version": ENGINE_VERSION}


@app.post("/api/analyze")
def analyze_endpoint(payload: AnalyzePayload) -> Dict[str, Any]:
    _acquire_analysis_slot()
    try:
        return analyze(payload.model_dump())
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise _internal_error("analyze") from exc
    finally:
        _analysis_semaphore.release()


@app.post("/api/analyze-upload")
async def analyze_upload(config: str = Form(...), file: UploadFile = File(...)) -> Dict[str, Any]:
    """Recebe CSV (separado por ;) e um JSON de configuração para análise."""
    try:
        try:
            payload = json.loads(config)
        except json.JSONDecodeError as exc:
            raise ValueError("Configuração inválida: não foi possível ler os parâmetros da análise.") from exc
        df = await _read_uploaded_table(file)
        payload["data"] = df.to_dict(orient="records")
        # analyze() e' CPU-bound (pandas/statsmodels/scipy) e sincrono; chama-lo direto
        # dentro deste endpoint async bloquearia o event loop (e todos os outros usuarios
        # conectados ao mesmo worker) durante o calculo. run_in_threadpool despacha para
        # uma thread separada, mantendo o event loop livre.
        if len(payload.get("data") or []) > MAX_DATA_ROWS:
            raise ValueError(f"O limite é de {MAX_DATA_ROWS} linhas por análise.")
        _acquire_analysis_slot()
        try:
            return await run_in_threadpool(analyze, payload)
        finally:
            _analysis_semaphore.release()
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise _internal_error("analyze-upload") from exc


@app.post("/api/export/pdf")
def export_pdf(payload: AnalyzePayload) -> Response:
    _acquire_analysis_slot()
    try:
        content = build_pdf(payload.model_dump())
        return Response(
            content,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=solver-relatorio.pdf"},
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise _internal_error("export-pdf") from exc
    finally:
        _analysis_semaphore.release()


@app.post("/api/export/excel")
def export_excel(payload: AnalyzePayload) -> Response:
    _acquire_analysis_slot()
    try:
        content = build_excel(payload.model_dump())
        return Response(
            content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=solver-resultados.xlsx"},
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise _internal_error("export-excel") from exc
    finally:
        _analysis_semaphore.release()


@app.post("/api/export/regression-plot")
def export_regression_plot(payload: AnalyzePayload, fmt: str = "png") -> Response:
    _acquire_analysis_slot()
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
    except Exception as exc:
        raise _internal_error("export-regression-plot") from exc
    finally:
        _analysis_semaphore.release()


@app.post("/api/export/means-plot")
def export_means_plot(payload: AnalyzePayload, fmt: str = "png") -> Response:
    _acquire_analysis_slot()
    try:
        fmt = fmt.lower()
        if fmt not in {"png", "pdf"}:
            raise ValueError("Formato inválido. Use png ou pdf.")
        content = build_means_plot(payload.model_dump(), fmt=fmt)
        media = "image/png" if fmt == "png" else "application/pdf"
        filename = f"solver-medias.{fmt}"
        return Response(content, media_type=media, headers={"Content-Disposition": f"attachment; filename={filename}"})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise _internal_error("export-means-plot") from exc
    finally:
        _analysis_semaphore.release()


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
    """Lê CSV UTF-8 separado por ';' ou XLSX, aplicando limite de tamanho."""
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        limit_mb = MAX_UPLOAD_BYTES / (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"Arquivo maior que o limite de {limit_mb:g} MB.")
    name = (file.filename or "").lower()
    if not name.endswith((".csv", ".xlsx")):
        raise ValueError(
            "Formato não suportado. Envie CSV UTF-8 separado por ponto e vírgula (;) ou XLSX."
        )
    if name.endswith(".xlsx"):
        try:
            df = pd.read_excel(io.BytesIO(raw), engine="openpyxl")
        except Exception as exc:
            raise ValueError("Não foi possível ler o XLSX. Verifique se o arquivo não está corrompido.") from exc
    else:
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
