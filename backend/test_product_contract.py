"""Contratos entre o produto publicado, os exemplos e o motor estatístico."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from statistics_engine import analyze


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_JSON = ROOT / "frontend" / "assets" / "data" / "dbc_exemplo.json"
EXAMPLE_CSV = ROOT / "examples" / "dbc_exemplo.csv"
APP_JS = ROOT / "frontend" / "assets" / "js" / "app.js"


def _official_rows():
    return json.loads(EXAMPLE_JSON.read_text(encoding="utf-8"))


def test_frontend_carrega_a_fonte_oficial_sem_dataset_hardcoded():
    source = APP_JS.read_text(encoding="utf-8")
    assert "assets/data/dbc_exemplo.json" in source
    assert "valor: 58.2" not in source


def test_csv_para_download_permanece_igual_ao_exemplo_do_produto():
    with EXAMPLE_CSV.open(encoding="utf-8-sig", newline="") as handle:
        csv_rows = [
            {"bloco": row["bloco"], "tratamento": row["tratamento"], "valor": float(row["valor"])}
            for row in csv.DictReader(handle)
        ]
    assert csv_rows == _official_rows()


def test_exemplo_real_do_frontend_reproduz_resultado_de_aceite():
    result = analyze({
        "design": "DBC", "analysis_type": "single", "goal": "max",
        "response_column": "valor", "treatment_column": "tratamento",
        "block_column": "bloco", "comparison_test": "tukey",
        "data": _official_rows(),
    })
    treatment = next(row for row in result["anova"]["table"] if row["source"] == "Tratamentos")
    assert treatment["f_calc"] == pytest.approx(14.412, rel=1e-3)
    assert treatment["significance"] == "1%"
    assert result["anova"]["cv"] == pytest.approx(6.21, abs=0.05)
    assert result["means"]["comparison"] is not None
