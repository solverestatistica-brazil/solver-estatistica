"""
Testes de regressao para o statistics_engine do Solver.

Objetivo: garantir que os bugs corrigidos em 12/07/2026 nao voltem.

Bugs cobertos:
  [FIX 3.1] KeyError '90' em factorial/split_plot com fator numerico
  [FIX 3.2] Guarda contra residuo singular (MSE ~ 0)
  [FIX 3.3] p_top_term exposto para selecao parcimoniosa da regressao
  [FIX 3.4] CV muito baixo nao deve ser rotulado como "Otimo"

Como rodar (dentro de backend/):
    pip install pytest
    pytest -v test_statistics_engine.py
"""

from __future__ import annotations

import random

import pytest

from statistics_engine import _cv_label, analyze


# =========================================================================
# Datasets embutidos (mesmos CSVs que dispararam os bugs em producao).
# =========================================================================

DBC_SINGLE = [
    {"Tratamento": 0, "Bloco": 1, "Valor": 16.1},
    {"Tratamento": 0, "Bloco": 2, "Valor": 16.3},
    {"Tratamento": 0, "Bloco": 3, "Valor": 16.5},
    {"Tratamento": 30, "Bloco": 1, "Valor": 18.5},
    {"Tratamento": 30, "Bloco": 2, "Valor": 18.7},
    {"Tratamento": 30, "Bloco": 3, "Valor": 18.9},
    {"Tratamento": 60, "Bloco": 1, "Valor": 21.1},
    {"Tratamento": 60, "Bloco": 2, "Valor": 21.3},
    {"Tratamento": 60, "Bloco": 3, "Valor": 21.5},
    {"Tratamento": 90, "Bloco": 1, "Valor": 22.5},
    {"Tratamento": 90, "Bloco": 2, "Valor": 22.7},
    {"Tratamento": 90, "Bloco": 3, "Valor": 22.9},
    {"Tratamento": 120, "Bloco": 1, "Valor": 20.8},
    {"Tratamento": 120, "Bloco": 2, "Valor": 21.0},
    {"Tratamento": 120, "Bloco": 3, "Valor": 21.2},
]


def _make_two_factor(level_label: str):
    rows = []
    for dose in (0, 30, 60, 90, 120):
        for lvl_num in (1, 2):
            for bloco in (1, 2, 3):
                base = {0: 16.0, 30: 18.5, 60: 21.2, 90: 22.6, 120: 20.9}[dose]
                bump = 0.1 * bloco + (0.3 if lvl_num == 2 else 0.0)
                rows.append({
                    "A": dose,
                    "B": f"{level_label}_{lvl_num}",
                    "Bloco": bloco,
                    "Valor": round(base + bump, 2),
                })
    return rows


FACTORIAL = _make_two_factor("Cultivar")
SPLIT_PLOT = _make_two_factor("Manejo")


# =========================================================================
# Testes
# =========================================================================


def test_bug_3_1_factorial_com_fator_numerico_nao_quebra():
    """[FIX 3.1] Antes: HTTP 500 KeyError '90' quando o fator eh numerico
    e numeric_factor_column esta setado. Agora: roda sem excecao."""
    result = analyze({
        "design": "DBC",
        "analysis_type": "factorial",
        "response_column": "Valor",
        "treatment_column": "A",
        "block_column": "Bloco",
        "factor_columns": ["A", "B"],
        "numeric_factor_column": "A",
        "comparison_test": "tukey",
        "goal": "max",
        "alpha": 0.05,
        "data": FACTORIAL,
    })
    assert result["meta"]["analysis_type"] == "factorial"
    assert len(result["anova"]["table"]) > 0


def test_bug_3_1_split_plot_com_fator_numerico_nao_quebra():
    """[FIX 3.1] Mesma protecao para parcelas subdivididas."""
    result = analyze({
        "design": "DBC",
        "analysis_type": "split_plot",
        "response_column": "Valor",
        "treatment_column": "A",
        "block_column": "Bloco",
        "factor_columns": ["A", "B"],
        "numeric_factor_column": "A",
        "comparison_test": "tukey",
        "goal": "max",
        "alpha": 0.05,
        "data": SPLIT_PLOT,
    })
    assert result["meta"]["analysis_type"] == "split_plot"
    assert len(result["anova"]["table"]) > 0


def test_bug_3_2_residuo_singular_dispara_flag_e_neutraliza_F():
    """[FIX 3.2] Com dados perfeitamente aditivos, o backend deve marcar
    residual_is_singular, zerar CV e neutralizar F/p das fontes reais."""
    result = analyze({
        "design": "DBC",
        "analysis_type": "single",
        "response_column": "Valor",
        "treatment_column": "Tratamento",
        "block_column": "Bloco",
        "numeric_factor_column": "Tratamento",
        "comparison_test": "tukey",
        "goal": "max",
        "alpha": 0.05,
        "data": DBC_SINGLE,
    })
    anova = result["anova"]
    assert anova.get("residual_is_singular") is True
    assert anova.get("cv") is None
    for row in anova["table"]:
        src = str(row.get("source") or "")
        if src not in ("Residuo", "Res\u00edduo", "Total"):
            assert row.get("f_calc") is None, f"F nao foi neutralizado em {src}"


def test_bug_3_4_cv_muito_baixo_nao_e_otimo():
    """[FIX 3.4] CV < 0.5%% deve ser rotulado como 'muito baixo', nao 'Otimo'."""
    assert _cv_label(0.0) != "\u00d3timo"
    assert _cv_label(0.1) != "\u00d3timo"
    assert "Muito baixo" in _cv_label(0.3)
    assert _cv_label(5.0) == "\u00d3timo"


def test_bug_3_3_regressao_expoe_p_top_term():
    """[FIX 3.3] _fit_poly deve incluir p_top_term em cada modelo, permitindo
    selecao parcimoniosa do grau na camada de apresentacao."""
    result = analyze({
        "design": "DIC",
        "analysis_type": "regression",
        "response_column": "Valor",
        "numeric_factor_column": "Tratamento",
        "goal": "max",
        "alpha": 0.05,
        "data": DBC_SINGLE,
    })
    reg = result["regression"]
    assert reg is not None
    for model in reg["models"]:
        # p_top_term pode ser None em degenerados, mas o campo tem que existir
        assert "p_top_term" in model, f"p_top_term ausente no grau {model['degree']}"


def test_smoke_dbc_com_dados_realistas():
    """Sanidade: DBC com CV realista (5-15%%) roda e devolve estatistica valida."""
    random.seed(42)
    data = []
    means = {0: 16.3, 30: 18.7, 60: 21.3, 90: 22.7, 120: 21.0}
    for t, m in means.items():
        for b in (1, 2, 3, 4):
            data.append({"Tratamento": t, "Bloco": b, "Valor": round(m + random.gauss(0, 0.9), 2)})
    result = analyze({
        "design": "DBC",
        "analysis_type": "single",
        "response_column": "Valor",
        "treatment_column": "Tratamento",
        "block_column": "Bloco",
        "numeric_factor_column": "Tratamento",
        "comparison_test": "tukey",
        "goal": "max",
        "alpha": 0.05,
        "data": data,
    })
    assert result["anova"]["cv"] is not None
    assert 0.5 < result["anova"]["cv"] < 30
    assert result["anova"].get("residual_is_singular") is not True
    assert str(result["means"]["best"]["treatment"]) in ("60", "90")
