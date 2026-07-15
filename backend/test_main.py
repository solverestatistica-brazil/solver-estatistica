"""
Testes da API FastAPI (main.py) — Solver Estatistica.

Como rodar (dentro de backend/, com httpx instalado):
    pip install pytest httpx
    pytest -v test_main.py
"""

from __future__ import annotations

import io
import json

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

CSV_BR = (
    "bloco;tratamento;valor\n"
    "B1;T1;52,4\nB1;T2;54,6\nB1;T3;60,9\nB1;T4;58,0\n"
    "B2;T1;56,6\nB2;T2;57,3\nB2;T3;72,0\nB2;T4;54,5\n"
    "B3;T1;59,6\nB3;T2;59,0\nB3;T3;80,9\nB3;T4;59,7\n"
    "B4;T1;61,6\nB4;T2;59,6\nB4;T3;77,5\nB4;T4;67,6\n"
).encode("utf-8-sig")

CONFIG = json.dumps({
    "design": "DBC", "analysis_type": "single", "response_column": "valor",
    "treatment_column": "tratamento", "block_column": "bloco", "data": [],
})


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_analyze_upload_ainda_funciona_apos_run_in_threadpool():
    """[AUDITORIA P1-03] analyze_upload despacha analyze() via run_in_threadpool para nao
    bloquear o event loop. Este teste garante que a mudanca nao quebrou o fluxo normal."""
    files = {"file": ("dados.csv", io.BytesIO(CSV_BR), "text/csv")}
    res = client.post("/api/analyze-upload", data={"config": CONFIG}, files=files)
    assert res.status_code == 200
    body = res.json()
    assert body["meta"]["n_rows"] == 16
    assert body["anova"]["cv"] is not None


def test_analyze_upload_rejeita_coluna_ausente_com_422_nao_500():
    csv_errado = "blco;tratamento;valor\nB1;T1;52,4\nB1;T2;54,6\n".encode("utf-8-sig")
    files = {"file": ("dados.csv", io.BytesIO(csv_errado), "text/csv")}
    res = client.post("/api/analyze-upload", data={"config": CONFIG}, files=files)
    assert res.status_code == 422
