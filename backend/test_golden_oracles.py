"""Oráculos numéricos independentes para os delineamentos e pós-testes.

Os valores esperados são obtidos por fórmulas fechadas ou por distribuições do
SciPy/ajuste do NumPy, sem reutilizar as rotinas internas do Solver.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats
from scipy.stats import studentized_range

from statistics_engine import analyze


ROOT = Path(__file__).resolve().parents[1]
TOL = 2e-6


def _close(actual, expected, tolerance=TOL):
    assert actual == pytest.approx(expected, rel=tolerance, abs=tolerance)


def _source(result, label):
    return next(row for row in result["anova"]["table"] if row["source"] == label)


def _payload(design, analysis_type, data, **extra):
    payload = {
        "design": design, "analysis_type": analysis_type,
        "response_column": "valor", "treatment_column": "tratamento",
        "block_column": "bloco", "row_column": "linha", "column_column": "coluna",
        "factor_columns": [], "comparison_test": "tukey", "goal": "max",
        "alpha": 0.05, "alpha_mode": "fixed", "data": data,
    }
    payload.update(extra)
    return payload


def test_golden_dic_e_dbc_por_formulas_fechadas():
    dic_df = pd.read_csv(ROOT / "examples" / "dic_exemplo.csv")
    dic = analyze(_payload("DIC", "single", dic_df.to_dict("records")))
    grand = dic_df.valor.mean()
    groups = dic_df.groupby("tratamento").valor
    ss_t = sum(len(group) * (group.mean() - grand) ** 2 for _, group in groups)
    ss_e = sum(((group - group.mean()) ** 2).sum() for _, group in groups)
    f_t = (ss_t / (dic_df.tratamento.nunique() - 1)) / (
        ss_e / (len(dic_df) - dic_df.tratamento.nunique())
    )
    _close(_source(dic, "Tratamentos")["sum_sq"], ss_t)
    _close(_source(dic, "Resíduo")["sum_sq"], ss_e)
    _close(_source(dic, "Tratamentos")["f_calc"], f_t)

    dbc_df = pd.read_csv(ROOT / "examples" / "dbc_exemplo.csv")
    dbc = analyze(_payload("DBC", "single", dbc_df.to_dict("records")))
    b, t = dbc_df.bloco.nunique(), dbc_df.tratamento.nunique()
    grand = dbc_df.valor.mean()
    total = ((dbc_df.valor - grand) ** 2).sum()
    ss_t = b * ((dbc_df.groupby("tratamento").valor.mean() - grand) ** 2).sum()
    ss_b = t * ((dbc_df.groupby("bloco").valor.mean() - grand) ** 2).sum()
    ss_e = total - ss_t - ss_b
    f_t = (ss_t / (t - 1)) / (ss_e / ((t - 1) * (b - 1)))
    _close(_source(dbc, "Tratamentos")["sum_sq"], ss_t)
    _close(_source(dbc, "Blocos")["sum_sq"], ss_b)
    _close(_source(dbc, "Resíduo")["sum_sq"], ss_e)
    _close(_source(dbc, "Tratamentos")["f_calc"], f_t)


def test_golden_dql_quatro_por_quatro():
    noise = np.array([
        [0.20, -0.35, 0.10, 0.05], [-0.10, 0.30, -0.25, 0.05],
        [0.15, -0.05, 0.20, -0.30], [-0.25, 0.10, -0.05, 0.20],
    ])
    treatment_effect = [0, 3, 6, 9]
    row_effect = [-1.5, -0.5, 0.5, 1.5]
    column_effect = [-0.6, 0.4, -0.2, 0.4]
    rows = []
    for i in range(4):
        for j in range(4):
            k = (i + j) % 4
            rows.append({
                "linha": f"L{i + 1}", "coluna": f"C{j + 1}", "tratamento": f"T{k + 1}",
                "valor": 50 + treatment_effect[k] + row_effect[i] + column_effect[j] + noise[i, j],
            })
    df = pd.DataFrame(rows)
    result = analyze(_payload("DQL", "single", rows))
    t = df.tratamento.nunique()
    grand = df.valor.mean()
    total = ((df.valor - grand) ** 2).sum()
    expected = {
        "Linhas": t * ((df.groupby("linha").valor.mean() - grand) ** 2).sum(),
        "Colunas": t * ((df.groupby("coluna").valor.mean() - grand) ** 2).sum(),
        "Tratamentos": t * ((df.groupby("tratamento").valor.mean() - grand) ** 2).sum(),
    }
    expected["Resíduo"] = total - sum(expected.values())
    for label, value in expected.items():
        _close(_source(result, label)["sum_sq"], value)
    f_t = (expected["Tratamentos"] / (t - 1)) / (expected["Resíduo"] / ((t - 1) * (t - 2)))
    _close(_source(result, "Tratamentos")["f_calc"], f_t)


def test_golden_fatorial_balanceado():
    rows = []
    for a in ("A1", "A2"):
        for b in ("B1", "B2", "B3"):
            for rep, epsilon in enumerate((-0.45, -0.1, 0.2, 0.35), 1):
                ai = 0 if a == "A1" else 4
                bi = {"B1": 0, "B2": 2, "B3": 5}[b]
                interaction = 0 if a == "A1" else {"B1": 0, "B2": 1.5, "B3": -1}[b]
                rows.append({
                    "A": a, "B": b, "tratamento": f"{a}-{b}",
                    "valor": 20 + ai + bi + interaction + epsilon + 0.07 * rep,
                })
    df = pd.DataFrame(rows)
    result = analyze(_payload("DIC", "factorial", rows, factor_columns=["A", "B"]))
    a, b, r = df.A.nunique(), df.B.nunique(), 4
    grand = df.valor.mean()
    am, bm = df.groupby("A").valor.mean(), df.groupby("B").valor.mean()
    cm = df.groupby(["A", "B"]).valor.mean()
    ss_a = b * r * ((am - grand) ** 2).sum()
    ss_b = a * r * ((bm - grand) ** 2).sum()
    ss_ab = r * sum(
        (cm.loc[i, j] - am.loc[i] - bm.loc[j] + grand) ** 2
        for i in am.index for j in bm.index
    )
    ss_e = sum(((group.valor - group.valor.mean()) ** 2).sum() for _, group in df.groupby(["A", "B"]))
    for label, expected in (("A", ss_a), ("B", ss_b), ("A × B", ss_ab), ("Resíduo", ss_e)):
        _close(_source(result, label)["sum_sq"], expected)


def test_golden_parcelas_subdivididas_com_dois_residuos():
    whole = {
        ("K1", "A1"): -0.4, ("K1", "A2"): 0.6, ("K2", "A1"): 0.5, ("K2", "A2"): -0.3,
        ("K3", "A1"): -0.1, ("K3", "A2"): 0.2, ("K4", "A1"): 0.2, ("K4", "A2"): -0.5,
    }
    errors = [-.25, .15, .10, .20, -.30, .10, -.10, .05, .05, .30, -.15, -.15,
              .15, -.05, -.10, -.20, .25, -.05, .05, -.20, .15, -.15, .10, .05]
    rows, q = [], 0
    for k, block in enumerate(("K1", "K2", "K3", "K4")):
        for a in ("A1", "A2"):
            for b in ("B1", "B2", "B3"):
                ai = 0 if a == "A1" else 4
                bi = {"B1": 0, "B2": 2, "B3": 5}[b]
                interaction = 0 if a == "A1" else {"B1": 0, "B2": 1, "B3": -1.5}[b]
                rows.append({"bloco": block, "A": a, "B": b, "tratamento": f"{a}-{b}",
                             "valor": 30 + .8 * k + ai + bi + interaction + whole[block, a] + errors[q]})
                q += 1
    df = pd.DataFrame(rows)
    result = analyze(_payload("DBC", "split_plot", rows, factor_columns=["A", "B"]))
    nblk, na, nb = 4, 2, 3
    grand = df.valor.mean()
    block_mean, a_mean = df.groupby("bloco").valor.mean(), df.groupby("A").valor.mean()
    b_mean = df.groupby("B").valor.mean()
    ba_mean, ab_mean = df.groupby(["bloco", "A"]).valor.mean(), df.groupby(["A", "B"]).valor.mean()
    total = ((df.valor - grand) ** 2).sum()
    ss_blk = na * nb * ((block_mean - grand) ** 2).sum()
    ss_a = nblk * nb * ((a_mean - grand) ** 2).sum()
    ss_ea = nb * sum((ba_mean.loc[k, i] - block_mean.loc[k] - a_mean.loc[i] + grand) ** 2
                     for k in block_mean.index for i in a_mean.index)
    ss_b = nblk * na * ((b_mean - grand) ** 2).sum()
    ss_ab = nblk * sum((ab_mean.loc[i, j] - a_mean.loc[i] - b_mean.loc[j] + grand) ** 2
                       for i in a_mean.index for j in b_mean.index)
    ss_eb = total - ss_blk - ss_a - ss_ea - ss_b - ss_ab
    expected = {
        "Blocos": ss_blk, "Parcela (A)": ss_a, "Erro (a) — Bloco × Parcela": ss_ea,
        "Subparcela (B)": ss_b, "A × B": ss_ab, "Erro (b) — Resíduo": ss_eb,
    }
    for label, value in expected.items():
        _close(_source(result, label)["sum_sq"], value, 1e-7)
    _close(_source(result, "Parcela (A)")["f_calc"], (ss_a / 1) / (ss_ea / 3), 1e-7)
    _close(_source(result, "Subparcela (B)")["f_calc"], (ss_b / 2) / (ss_eb / 12), 1e-7)


def test_golden_regressao_contra_numpy():
    df = pd.read_csv(ROOT / "examples" / "regressao_doses.csv")
    result = analyze(_payload(
        "DIC", "regression", df.to_dict("records"), numeric_factor_column="dose",
    ))
    selected = result["regression"]["selected_model"]
    degree = result["regression"]["selected_degree"]
    coefficients = np.polyfit(df.dose, df.valor, degree)[::-1]
    predicted = sum(coefficients[i] * df.dose.to_numpy() ** i for i in range(len(coefficients)))
    expected_r2 = 1 - np.sum((df.valor - predicted) ** 2) / np.sum((df.valor - df.valor.mean()) ** 2)
    assert np.asarray(selected["coefficients"]) == pytest.approx(coefficients, rel=TOL, abs=TOL)
    _close(selected["r2"], expected_r2)


@pytest.mark.parametrize("test_name", ["tukey", "duncan", "snk", "scheffe"])
def test_golden_diferenca_critica_dos_pos_testes(test_name):
    df = pd.read_csv(ROOT / "examples" / "dic_exemplo.csv")
    result = analyze(_payload(
        "DIC", "single", df.to_dict("records"), comparison_test=test_name,
    ))
    comparison = result["means"]["comparison"]
    row = comparison["comparisons"][0]
    means = {str(item["treatment"]): item for item in result["means"]["treatment_means"]}
    g1, g2 = row["group_a"], row["group_b"]
    n1, n2, k = means[g1]["n"], means[g2]["n"], len(means)
    mse, df_error, alpha = result["anova"]["mse"], result["anova"]["df_error"], comparison["alpha"]
    if test_name == "scheffe":
        expected = math.sqrt((k - 1) * stats.f.ppf(1 - alpha, k - 1, df_error) * mse * (1 / n1 + 1 / n2))
    else:
        ordered = sorted(means, key=lambda group: means[group]["mean"], reverse=True)
        p_range = abs(ordered.index(g2) - ordered.index(g1)) + 1
        if test_name == "snk":
            qcrit = studentized_range.ppf(1 - alpha, p_range, df_error)
        elif test_name == "duncan":
            alpha_range = 1 - (1 - alpha) ** (p_range - 1)
            qcrit = studentized_range.ppf(1 - alpha_range, p_range, df_error)
        else:
            qcrit = studentized_range.ppf(1 - alpha, k, df_error)
        expected = qcrit * math.sqrt(mse / 2 * (1 / n1 + 1 / n2))
    _close(row["critical_diff"], expected)
