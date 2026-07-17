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


def test_dql_accepts_title_case_headers_and_resposta_alias():
    treatments = [
        ["RA", "RB", "RC", "RD", "RE"],
        ["RB", "RC", "RD", "RE", "RA"],
        ["RC", "RD", "RE", "RA", "RB"],
        ["RD", "RE", "RA", "RB", "RC"],
        ["RE", "RA", "RB", "RC", "RD"],
    ]
    data = [
        {"Linha": row + 1, "Coluna": column + 1, "Tratamento": treatments[row][column],
         "Resposta": 20 + row * 2 + column + ((row * column) % 3)}
        for row in range(5) for column in range(5)
    ]
    result = analyze({
        "design": "DQL", "analysis_type": "single",
        "response_column": "valor", "treatment_column": "tratamento",
        "row_column": "linha", "column_column": "coluna", "data": data,
    })
    assert result["meta"]["n_rows"] == 25
    assert result["meta"]["response_column"] == "Resposta"


def test_factorial_accepts_a_b_headers_with_default_factor_names():
    data = [
        {"A": dose, "B": cultivar, "Bloco": block, "Valor": 15 + dose * 2 + cultivar_index + block / 10}
        for dose in (0, 1)
        for cultivar_index, cultivar in enumerate(("Cultivar_1", "Cultivar_2"), start=1)
        for block in (1, 2, 3)
    ]
    result = analyze({
        "design": "DBC", "analysis_type": "factorial",
        "response_column": "valor", "treatment_column": "tratamento", "block_column": "bloco",
        "factor_columns": ["fator_a", "fator_b"], "data": data,
    })
    assert result["meta"]["n_rows"] == 12
    assert result["meta"]["response_column"] == "Valor"


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


def test_dql_accepts_title_case_headers_and_resposta_alias():
    treatments = [
        ["RA", "RB", "RC", "RD", "RE"],
        ["RB", "RC", "RD", "RE", "RA"],
        ["RC", "RD", "RE", "RA", "RB"],
        ["RD", "RE", "RA", "RB", "RC"],
        ["RE", "RA", "RB", "RC", "RD"],
    ]
    data = [
        {"Linha": row + 1, "Coluna": column + 1, "Tratamento": treatments[row][column],
         "Resposta": 20 + row * 2 + column + ((row * column) % 3)}
        for row in range(5) for column in range(5)
    ]
    result = analyze({
        "design": "DQL", "analysis_type": "single",
        "response_column": "valor", "treatment_column": "tratamento",
        "row_column": "linha", "column_column": "coluna", "data": data,
    })
    assert result["meta"]["n_rows"] == 25
    assert result["meta"]["response_column"] == "Resposta"


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
