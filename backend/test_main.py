"""
Testes da API FastAPI (main.py) — Solver Estatistica.

Como rodar (dentro de backend/):
    pip install -r requirements-dev.txt
    pytest -v test_main.py
"""

from __future__ import annotations

import io
import json

from fastapi.testclient import TestClient
from openpyxl import Workbook

import main
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
    assert res.json()["status"] == "ok"
    assert res.json()["version"] == "0.2.0"


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


def test_analyze_upload_aceita_xlsx():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["bloco", "tratamento", "valor"])
    for line in CSV_BR.decode("utf-8-sig").splitlines()[1:]:
        bloco, tratamento, valor = line.split(";")
        sheet.append([bloco, tratamento, float(valor.replace(",", "."))])
    stream = io.BytesIO()
    workbook.save(stream)
    stream.seek(0)

    files = {
        "file": (
            "dados.xlsx", stream,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    res = client.post("/api/analyze-upload", data={"config": CONFIG}, files=files)
    assert res.status_code == 200
    assert res.json()["meta"]["n_rows"] == 16


def test_analyze_upload_rejeita_extensao_nao_suportada():
    files = {"file": ("dados.xls", io.BytesIO(b"nao e uma planilha"), "application/vnd.ms-excel")}
    res = client.post("/api/analyze-upload", data={"config": CONFIG}, files=files)
    assert res.status_code == 422
    assert "XLSX" in res.json()["detail"]


def test_analyze_upload_rejeita_arquivo_acima_do_limite(monkeypatch):
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 32)
    files = {"file": ("dados.csv", io.BytesIO(CSV_BR), "text/csv")}
    res = client.post("/api/analyze-upload", data={"config": CONFIG}, files=files)
    assert res.status_code == 413


def test_api_adota_alfa_automatico_como_convencao_pedagogica():
    payload = json.loads(CONFIG)
    payload["data"] = [
        {"bloco": f"B{b}", "tratamento": t, "valor": v}
        for b, values in enumerate(((10, 15), (11, 16), (9, 14)), start=1)
        for t, v in zip(("T1", "T2"), values)
    ]
    res = client.post("/api/analyze", json=payload)
    assert res.status_code == 200
    assert res.json()["meta"]["alpha_mode"] == "auto"
    assert res.json()["meta"]["alpha"] == 0.05


def test_api_rejeita_alfa_fora_do_intervalo_aberto_unitario():
    payload = json.loads(CONFIG)
    payload["alpha"] = 1
    payload["data"] = [
        {"bloco": "B1", "tratamento": "T1", "valor": 10},
        {"bloco": "B1", "tratamento": "T2", "valor": 12},
    ]
    res = client.post("/api/analyze", json=payload)
    assert res.status_code == 422
    assert "alpha" in res.text

def test_rate_limit_retorna_429(monkeypatch):
    main._request_times.clear()
    monkeypatch.setattr(main, "RATE_LIMIT_PER_MINUTE", 1)
    first = client.post("/api/analyze", json={"data": []})
    second = client.post("/api/analyze", json={"data": []})
    assert first.status_code == 422
    assert second.status_code == 429
    main._request_times.clear()


def test_rate_limit_ignora_x_forwarded_for_sem_proxy_confiavel(monkeypatch):
    main._request_times.clear()
    monkeypatch.setattr(main, "RATE_LIMIT_PER_MINUTE", 1)
    monkeypatch.setattr(main, "TRUST_PROXY_HEADERS", False)
    first = client.post("/api/analyze", json={"data": []}, headers={"X-Forwarded-For": "198.51.100.10"})
    second = client.post("/api/analyze", json={"data": []}, headers={"X-Forwarded-For": "198.51.100.20"})
    assert first.status_code == 422
    assert second.status_code == 429
    main._request_times.clear()


def test_rate_limit_usa_x_forwarded_for_com_proxy_confiavel(monkeypatch):
    main._request_times.clear()
    monkeypatch.setattr(main, "RATE_LIMIT_PER_MINUTE", 1)
    monkeypatch.setattr(main, "TRUST_PROXY_HEADERS", True)
    first = client.post("/api/analyze", json={"data": []}, headers={"X-Forwarded-For": "198.51.100.10"})
    second = client.post("/api/analyze", json={"data": []}, headers={"X-Forwarded-For": "198.51.100.20"})
    assert first.status_code == 422
    assert second.status_code == 422
    main._request_times.clear()
