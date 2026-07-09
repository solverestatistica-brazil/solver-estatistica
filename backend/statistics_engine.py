"""
Motor estatístico do Solver.

Objetivo do MVP:
- Receber dados em formato tabular.
- Validar o delineamento escolhido.
- Ajustar ANOVA para DIC, DBC, DQL, fatorial e parcelas subdivididas.
- Gerar comparação de médias e regressão linear/quadrática/cúbica.

Observação técnica:
Este código foi estruturado para facilitar auditoria e evolução. Em produção,
valide as rotinas estatísticas com um profissional responsável antes de usar
os resultados como laudo oficial.
"""

from __future__ import annotations

import base64
import io
import math
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats
from scipy.stats import studentized_range
from statsmodels.stats.anova import anova_lm


ALLOWED_DESIGNS = {"DIC", "DBC", "DQL"}
ALLOWED_ANALYSIS_TYPES = {"single", "factorial", "split_plot", "regression"}
ALLOWED_TESTS = {"tukey", "duncan", "dunnett", "snk", "scheffe"}


def _q(column: str) -> str:
    """Escapa nomes de colunas para fórmulas patsy/statsmodels."""
    return f'Q("{column}")'


def _c(column: str) -> str:
    """Transforma uma coluna em fator categórico para a fórmula."""
    return f'C({_q(column)})'


def _clean_value(value: Any) -> Any:
    """Converte NaN/inf para None para permitir serialização JSON."""
    if isinstance(value, (np.floating, float)):
        if math.isnan(float(value)) or math.isinf(float(value)):
            return None
        return round(float(value), 6)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, dict):
        return {k: _clean_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean_value(v) for v in value]
    return value


def _num(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def _source_label(index_name: str, payload: Dict[str, Any]) -> str:
    mapping = {
        f'C({_q(payload.get("treatment_column", "tratamento"))})': "Tratamentos",
        f'C({_q(payload.get("block_column", "bloco"))})': "Blocos",
        f'C({_q(payload.get("row_column", "linha"))})': "Linhas",
        f'C({_q(payload.get("column_column", "coluna"))})': "Colunas",
        "Residual": "Resíduo",
    }
    for factor in payload.get("factor_columns", []) or []:
        mapping[f'C({_q(factor)})'] = factor
    if index_name in mapping:
        return mapping[index_name]
    label = index_name
    label = label.replace("C(Q(\"", "").replace("\"))", "")
    label = label.replace(":", " × ")
    return label


def _significance(p_value: Optional[float]) -> str:
    if p_value is None:
        return "—"
    if p_value <= 0.01:
        return "1%"
    if p_value <= 0.05:
        return "5%"
    return "ns"


def _cv_label(cv: Optional[float]) -> str:
    if cv is None:
        return "Indisponível"
    if cv <= 10:
        return "Ótimo"
    if cv <= 20:
        return "Bom"
    if cv <= 30:
        return "Moderado"
    return "Alto — revisar variabilidade"


def _parse_numeric_from_text(series: pd.Series) -> pd.Series:
    """Extrai primeiro número de textos como 'Dose 120 kg/ha'."""
    def parse_one(v: Any) -> Optional[float]:
        if pd.isna(v):
            return None
        if isinstance(v, (int, float, np.number)):
            return float(v)
        text = str(v).replace(",", ".")
        match = re.search(r"[-+]?\d*\.?\d+", text)
        return float(match.group(0)) if match else None

    return series.apply(parse_one)


@dataclass
class AnalysisContext:
    df: pd.DataFrame
    payload: Dict[str, Any]
    response: str
    treatment: str
    design: str
    analysis_type: str
    goal: str


def _prepare_context(payload: Dict[str, Any]) -> AnalysisContext:
    data = payload.get("data") or []
    if not data:
        raise ValueError("Nenhuma linha de dados foi enviada.")

    df = pd.DataFrame(data)
    df.columns = [str(c).strip() for c in df.columns]

    response = payload.get("response_column") or "valor"
    treatment = payload.get("treatment_column") or "tratamento"
    design = (payload.get("design") or "DIC").upper()
    analysis_type = payload.get("analysis_type") or "single"
    goal = payload.get("goal") or "max"

    if design not in ALLOWED_DESIGNS:
        raise ValueError(f"Delineamento inválido: {design}. Use DIC, DBC ou DQL.")
    if analysis_type not in ALLOWED_ANALYSIS_TYPES:
        raise ValueError(f"Tipo de análise inválido: {analysis_type}.")
    if goal not in {"max", "min"}:
        raise ValueError("Objetivo inválido. Use 'max' para maior resposta ou 'min' para menor resposta.")

    required = [response]
    if analysis_type != "regression":
        required.append(treatment)
    if design == "DBC":
        required.append(payload.get("block_column") or "bloco")
    if design == "DQL":
        required.extend([payload.get("row_column") or "linha", payload.get("column_column") or "coluna"])
    if analysis_type in {"factorial", "split_plot"}:
        required.extend(payload.get("factor_columns") or [])

    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError("Colunas ausentes na base: " + ", ".join(missing))

    df[response] = pd.to_numeric(df[response], errors="coerce")
    if df[response].isna().any():
        bad = int(df[response].isna().sum())
        raise ValueError(f"A coluna de resposta '{response}' contém {bad} valor(es) vazio(s) ou não numérico(s).")

    df = df.dropna(subset=[response]).copy()

    if analysis_type != "regression" and df[treatment].nunique() < 2:
        raise ValueError("A análise precisa de pelo menos 2 tratamentos.")

    if analysis_type != "regression":
        _validate_design(df, payload, design, treatment)
    return AnalysisContext(df=df, payload=payload, response=response, treatment=treatment, design=design, analysis_type=analysis_type, goal=goal)


def _validate_design(df: pd.DataFrame, payload: Dict[str, Any], design: str, treatment: str) -> None:
    """Valida regras mínimas de cada delineamento experimental."""
    if design == "DIC":
        reps = df.groupby(treatment).size()
        if reps.min() < 1:
            raise ValueError("No DIC, cada tratamento deve ter ao menos uma observação.")

    if design == "DBC":
        block = payload.get("block_column") or "bloco"
        if df[block].nunique() < 2:
            raise ValueError("No DBC, informe pelo menos 2 blocos.")
        counts = df.groupby([block, treatment]).size()
        if counts.max() > 1:
            raise ValueError("No DBC, foi encontrada mais de uma observação para o mesmo tratamento dentro do mesmo bloco. Revise repetições ou agregue os dados.")
        expected = df[block].nunique() * df[treatment].nunique()
        if len(counts) < expected:
            raise ValueError("No DBC, faltam combinações entre blocos e tratamentos.")

    if design == "DQL":
        row = payload.get("row_column") or "linha"
        col = payload.get("column_column") or "coluna"
        n_t = df[treatment].nunique()
        n_r = df[row].nunique()
        n_c = df[col].nunique()
        if not (n_t == n_r == n_c):
            raise ValueError("No DQL, o número de tratamentos, linhas e colunas deve ser igual.")
        if len(df) != n_t * n_t:
            raise ValueError("No DQL, o total de observações deve ser t², onde t é o número de tratamentos.")
        if not (df.groupby(row).size() == n_t).all() or not (df.groupby(col).size() == n_t).all():
            raise ValueError("No DQL, cada linha e cada coluna deve conter t observações.")
        if not (df.groupby(treatment).size() == n_t).all():
            raise ValueError("No DQL, cada tratamento deve aparecer exatamente t vezes.")


def _formula_for(ctx: AnalysisContext) -> Tuple[str, List[str]]:
    p = ctx.payload
    response = ctx.response
    treatment = ctx.treatment
    terms: List[str] = []
    notes: List[str] = []

    if ctx.analysis_type == "regression":
        return "", notes

    if ctx.design == "DBC":
        terms.append(_c(p.get("block_column") or "bloco"))
    elif ctx.design == "DQL":
        terms.extend([_c(p.get("row_column") or "linha"), _c(p.get("column_column") or "coluna")])

    if ctx.analysis_type == "factorial":
        factors = p.get("factor_columns") or []
        if len(factors) < 2:
            raise ValueError("Para análise fatorial, informe pelo menos dois fatores.")
        terms.append(" * ".join(_c(f) for f in factors[:3]))
    elif ctx.analysis_type == "split_plot":
        factors = p.get("factor_columns") or []
        if len(factors) < 2:
            raise ValueError("Para parcelas subdivididas, informe fator de parcela e fator de subparcela.")
        if ctx.design != "DBC":
            notes.append("Parcelas subdivididas normalmente exigem blocos. O modelo foi ajustado com os fatores informados, mas recomenda-se revisar a estrutura experimental.")
        main, sub = factors[0], factors[1]
        terms.append(f"{_c(main)} * {_c(sub)}")
        notes.append("MVP: parcelas subdivididas foram ajustadas por OLS com bloco e interação dos fatores. Para laudo final, revisar estratos de erro do experimento.")
    else:
        terms.append(_c(treatment))

    formula = f"{_q(response)} ~ " + " + ".join(terms)
    return formula, notes


def _anova(ctx: AnalysisContext) -> Dict[str, Any]:
    formula, notes = _formula_for(ctx)
    if not formula:
        return {"table": [], "cv": None, "cv_label": "Indisponível", "model_notes": notes}

    model = smf.ols(formula, data=ctx.df).fit()
    table = anova_lm(model, typ=2)
    df_resid = float(model.df_resid)
    mse = float(model.mse_resid) if model.df_resid > 0 else None
    mean_response = float(ctx.df[ctx.response].mean())
    cv = (math.sqrt(mse) / mean_response * 100) if mse is not None and mean_response != 0 else None

    rows: List[Dict[str, Any]] = []
    for idx, row in table.iterrows():
        dfv = _num(row.get("df"))
        sum_sq = _num(row.get("sum_sq"))
        mean_sq = (sum_sq / dfv) if sum_sq is not None and dfv not in (None, 0) else None
        f_value = _num(row.get("F"))
        p_value = _num(row.get("PR(>F)"))
        f5 = stats.f.ppf(0.95, dfv, df_resid) if idx != "Residual" and dfv and df_resid > 0 else None
        f1 = stats.f.ppf(0.99, dfv, df_resid) if idx != "Residual" and dfv and df_resid > 0 else None
        rows.append({
            "source": _source_label(str(idx), ctx.payload),
            "raw_source": str(idx),
            "df": dfv,
            "sum_sq": sum_sq,
            "mean_sq": mean_sq,
            "f_calc": f_value,
            "f_5": f5,
            "f_1": f1,
            "p_value": p_value,
            "significance": _significance(p_value),
        })

    total_ss = float(((ctx.df[ctx.response] - ctx.df[ctx.response].mean()) ** 2).sum())
    rows.append({
        "source": "Total",
        "raw_source": "Total",
        "df": int(len(ctx.df) - 1),
        "sum_sq": total_ss,
        "mean_sq": None,
        "f_calc": None,
        "f_5": None,
        "f_1": None,
        "p_value": None,
        "significance": "—",
    })

    return {
        "formula": formula,
        "table": rows,
        "mse": mse,
        "df_error": df_resid,
        "cv": cv,
        "cv_label": _cv_label(cv),
        "model_notes": notes,
    }


def _means(ctx: AnalysisContext, anova: Dict[str, Any]) -> Dict[str, Any]:
    if ctx.analysis_type == "regression":
        return {"treatment_means": [], "best": None, "comparison": None}

    grouped = ctx.df.groupby(ctx.treatment)[ctx.response]
    table = grouped.agg(["mean", "count", "std"]).reset_index().rename(columns={ctx.treatment: "treatment", "count": "n", "std": "sd"})
    table["sd"] = table["sd"].fillna(0)
    table = table.sort_values("mean", ascending=(ctx.goal == "min"))

    mean_min = float(table["mean"].min())
    mean_max = float(table["mean"].max())
    span = mean_max - mean_min
    if span > 0:
        if ctx.goal == "min":
            table["rank_pct"] = table["mean"].apply(lambda v: round((mean_max - float(v)) / span * 100, 1))
        else:
            table["rank_pct"] = table["mean"].apply(lambda v: round((float(v) - mean_min) / span * 100, 1))
    else:
        table["rank_pct"] = 100.0

    best_row = table.iloc[0].to_dict() if len(table) else None
    comparison = _comparison_tests(table, anova, ctx)
    if comparison and comparison.get("letters"):
        letters = comparison["letters"]
        table["group"] = table["treatment"].astype(str).map(letters).fillna("")
    else:
        table["group"] = ""

    return {
        "treatment_means": table.to_dict(orient="records"),
        "best": best_row,
        "comparison": comparison,
    }


def _resolve_alpha(ctx: AnalysisContext, anova: Dict[str, Any]) -> float:
    """Alinha o alfa da comparacao de medias ao nivel de significancia do
    teste F da fonte comparada (ctx.treatment). Nunca comparar medias a 5%
    quando o teste F so foi significativo a 1%, ou vice-versa: o pos-teste
    tem que herdar a mesma probabilidade que a ANOVA usou para aquela fonte."""
    raw_key = f'C({_q(ctx.treatment)})'
    for row in anova.get("table", []):
        if row.get("raw_source") == raw_key:
            if row.get("significance") == "1%":
                return 0.01
            return 0.05
    return 0.05


def _comparison_tests(table: pd.DataFrame, anova: Dict[str, Any], ctx: AnalysisContext) -> Optional[Dict[str, Any]]:
    mse = anova.get("mse")
    df_error = anova.get("df_error")
    if mse is None or not df_error or df_error <= 0 or table["treatment"].nunique() < 2:
        return None

    test_name = (ctx.payload.get("comparison_test") or "tukey").lower()
    if test_name not in ALLOWED_TESTS:
        test_name = "tukey"
    alpha = _resolve_alpha(ctx, anova)

    means = {str(r["treatment"]): float(r["mean"]) for _, r in table.iterrows()}
    ns = {str(r["treatment"]): int(r["n"]) for _, r in table.iterrows()}
    order = [str(v) for v in table["treatment"].tolist()]
    groups = list(means.keys())
    k = len(groups)
    comparisons: List[Dict[str, Any]] = []
    nonsig_pairs: set[Tuple[str, str]] = set()

    def add_result(g1: str, g2: str, diff: float, crit: float, p_value: Optional[float] = None) -> None:
        significant = abs(diff) > crit
        if not significant:
            nonsig_pairs.add(tuple(sorted((g1, g2))))
        comparisons.append({
            "group_a": g1,
            "group_b": g2,
            "diff": diff,
            "critical_diff": crit,
            "p_value": p_value,
            "significant": bool(significant),
        })

    if test_name == "dunnett":
        control = ctx.payload.get("control_group") or order[-1]
        if str(control) not in means:
            control = order[-1]
        m = max(k - 1, 1)
        tcrit = stats.t.ppf(1 - alpha / (2 * m), df_error)
        for g in groups:
            if g == str(control):
                continue
            se = math.sqrt(mse * (1 / ns[g] + 1 / ns[str(control)]))
            diff = means[g] - means[str(control)]
            add_result(g, str(control), diff, tcrit * se, None)
        method_note = "Dunnett no MVP usa aproximação t com correção de Bonferroni contra o controle informado."
    else:
        sorted_by_mean = sorted(groups, key=lambda g: means[g], reverse=True)
        for i, g1 in enumerate(sorted_by_mean):
            for j, g2 in enumerate(sorted_by_mean[i + 1 :], start=i + 1):
                diff = means[g1] - means[g2]
                se_tukey = math.sqrt(mse / 2 * (1 / ns[g1] + 1 / ns[g2]))
                if test_name == "scheffe":
                    fcrit = stats.f.ppf(1 - alpha, k - 1, df_error)
                    crit = math.sqrt((k - 1) * fcrit * mse * (1 / ns[g1] + 1 / ns[g2]))
                    p_value = None
                else:
                    range_size = abs(j - i) + 1
                    if test_name == "snk":
                        qcrit = studentized_range.ppf(1 - alpha, range_size, df_error)
                    elif test_name == "duncan":
                        alpha_r = 1 - (1 - alpha) ** (range_size - 1)
                        qcrit = studentized_range.ppf(1 - alpha_r, range_size, df_error)
                    else:  # Tukey-Kramer
                        qcrit = studentized_range.ppf(1 - alpha, k, df_error)
                    crit = qcrit * se_tukey
                    q_stat = abs(diff) / se_tukey if se_tukey else np.nan
                    p_value = float(studentized_range.sf(q_stat, k, df_error)) if not np.isnan(q_stat) else None
                add_result(g1, g2, diff, crit, p_value)
        method_note = _comparison_note(test_name)

    letters = _assign_letters(order, nonsig_pairs)
    return {
        "test": test_name.upper(),
        "alpha": alpha,
        "letters": letters,
        "comparisons": comparisons,
        "note": method_note,
    }


def _comparison_note(test_name: str) -> str:
    notes = {
        "tukey": "Tukey-Kramer para tamanhos de amostra iguais ou desiguais.",
        "duncan": "Duncan implementado por amplitude studentizada com nível por amplitude; validar antes de laudo oficial.",
        "snk": "SNK implementado por amplitude studentizada por distância entre médias ordenadas; validar antes de laudo oficial.",
        "scheffe": "Scheffé aplicado com F crítico e erro médio residual da ANOVA.",
    }
    return notes.get(test_name, "Teste de comparação de médias calculado.")


def _assign_letters(order: List[str], nonsig_pairs: set[Tuple[str, str]]) -> Dict[str, str]:
    """Gera letras compactas simples para médias. Valores sem diferença compartilham letras."""
    if not order:
        return {}
    letters = {g: "" for g in order}
    letter_groups: List[List[str]] = []

    for g in order:
        placed = False
        for idx, members in enumerate(letter_groups):
            if all(tuple(sorted((g, h))) in nonsig_pairs for h in members):
                members.append(g)
                letters[g] += chr(ord("a") + idx)
                placed = True
        if not placed:
            letter_groups.append([g])
            letters[g] += chr(ord("a") + len(letter_groups) - 1)
    return letters


def _regression(ctx: AnalysisContext) -> Optional[Dict[str, Any]]:
    p = ctx.payload
    response = ctx.response
    numeric_col = p.get("numeric_factor_column") or p.get("dose_column")
    df = ctx.df.copy()

    if numeric_col and numeric_col in df.columns:
        x = pd.to_numeric(df[numeric_col], errors="coerce")
        x_label = numeric_col
    elif ctx.treatment in df.columns:
        x = _parse_numeric_from_text(df[ctx.treatment])
        x_label = ctx.treatment
    else:
        return None

    reg_df = pd.DataFrame({"x": x, "y": df[response]}).dropna()
    if reg_df["x"].nunique() < 2:
        return None

    means_df = (
        reg_df.groupby("x")["y"]
        .agg(["mean", "count", "std"])
        .reset_index()
        .rename(columns={"mean": "y", "count": "n", "std": "sd"})
        .sort_values("x")
    )
    means_df["sd"] = means_df["sd"].fillna(0)

    requested_degree = p.get("regression_degree")
    requested_degree = int(requested_degree) if requested_degree else None
    max_degree = min(3, int(reg_df["x"].nunique()) - 1)
    models: List[Dict[str, Any]] = []

    for degree in range(1, max_degree + 1):
        fit = _fit_poly(reg_df["x"].to_numpy(dtype=float), reg_df["y"].to_numpy(dtype=float), degree, ctx.goal)
        fit["degree"] = degree
        models.append(fit)

    if not models:
        return None

    best = sorted(models, key=lambda m: (m.get("adj_r2") if m.get("adj_r2") is not None else -999), reverse=True)[0]
    selected = next((m for m in models if m["degree"] == requested_degree), best) if requested_degree else best
    recommendation = "Modelo escolhido pelo maior R² ajustado."
    if requested_degree and selected["degree"] != best["degree"]:
        recommendation = f"O grau solicitado ({requested_degree}) não foi o melhor pelo R² ajustado. Sugestão automática: grau {best['degree']}."
        selected = best

    x_grid = np.linspace(reg_df["x"].min(), reg_df["x"].max(), 120)
    y_grid = _predict_poly(selected["coefficients"], x_grid)
    plot_png = _regression_plot_base64(means_df, x_grid, y_grid, selected)

    return {
        "x_label": x_label,
        "y_label": response,
        "models": models,
        "recommended_degree": best["degree"],
        "selected_degree": selected["degree"],
        "recommendation": recommendation,
        "selected_model": selected,
        "points": means_df.to_dict(orient="records"),
        "fitted_curve": [{"x": float(a), "y": float(b)} for a, b in zip(x_grid, y_grid)],
        "plot_png_base64": plot_png,
    }


def _fit_poly(x: np.ndarray, y: np.ndarray, degree: int, goal: str) -> Dict[str, Any]:
    X = np.column_stack([x ** i for i in range(1, degree + 1)])
    X = sm.add_constant(X)
    model = sm.OLS(y, X).fit()
    coeffs = model.params.tolist()  # intercepto, x, x², x³...
    equation = _equation_text(coeffs)
    optimum = _poly_optimum(coeffs, float(np.min(x)), float(np.max(x)), goal)
    return {
        "r2": float(model.rsquared),
        "adj_r2": float(model.rsquared_adj),
        "aic": float(model.aic),
        "bic": float(model.bic),
        "p_model": float(model.f_pvalue) if model.f_pvalue is not None and not np.isnan(model.f_pvalue) else None,
        "coefficients": [float(v) for v in coeffs],
        "equation": equation,
        "optimum": optimum,
    }


def _predict_poly(coefficients: Iterable[float], x: np.ndarray) -> np.ndarray:
    coeffs = list(coefficients)
    y = np.full_like(x, coeffs[0], dtype=float)
    for power, coef in enumerate(coeffs[1:], start=1):
        y += coef * (x ** power)
    return y


def _equation_text(coeffs: List[float]) -> str:
    parts = [f"{coeffs[0]:.4f}"]
    for power, coef in enumerate(coeffs[1:], start=1):
        sign = "+" if coef >= 0 else "-"
        var = "x" if power == 1 else f"x^{power}"
        parts.append(f" {sign} {abs(coef):.4f}{var}")
    return "ŷ = " + "".join(parts)


def _poly_optimum(coeffs: List[float], x_min: float, x_max: float, goal: str) -> Dict[str, Any]:
    candidates = [x_min, x_max]
    if len(coeffs) == 3:  # quadrático
        b = coeffs[1]
        c = coeffs[2]
        if c != 0:
            vertex = -b / (2 * c)
            if x_min <= vertex <= x_max:
                candidates.append(vertex)
    elif len(coeffs) == 4:  # cúbico: derivada b + 2cx + 3dx²
        b, c, d = coeffs[1], coeffs[2], coeffs[3]
        roots = np.roots([3 * d, 2 * c, b]) if d != 0 else []
        for root in roots:
            if np.isreal(root):
                r = float(np.real(root))
                if x_min <= r <= x_max:
                    candidates.append(r)

    values = [(float(x), float(_predict_poly(coeffs, np.array([x]))[0])) for x in candidates]
    chosen = max(values, key=lambda t: t[1]) if goal == "max" else min(values, key=lambda t: t[1])
    return {"x": chosen[0], "y": chosen[1], "goal": goal}


def _regression_plot_base64(means_df: pd.DataFrame, x_grid: np.ndarray, y_grid: np.ndarray, model: Dict[str, Any]) -> str:
    fig, ax = plt.subplots(figsize=(9, 5.2), dpi=160)
    ax.errorbar(
        means_df["x"], means_df["y"], yerr=means_df["sd"],
        fmt="o", color="#24492E", ecolor="#3E7E54", elinewidth=1.4,
        capsize=4, markersize=7, label="Observado (média por dose)",
    )
    ax.plot(x_grid, y_grid, color="#5FAF77", linewidth=2.2, label=f"Grau {model['degree']} · R²aj {model['adj_r2']:.3f}")
    optimum = model.get("optimum") or {}
    if optimum.get("x") is not None:
        ax.axvline(optimum["x"], linestyle="--", linewidth=1, color="#8a6d2f")
        ax.scatter([optimum["x"]], [optimum["y"]], marker="D", s=60, color="#c99a2e", zorder=5, label="Dose ótima")
    ax.set_xlabel("Dose / fator numérico")
    ax.set_ylabel("Resposta")
    ax.set_title("Regressão ajustada")
    ax.grid(True, alpha=0.25)
    ax.legend()
    buffer = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buffer, format="png")
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def analyze(payload: Dict[str, Any]) -> Dict[str, Any]:
    ctx = _prepare_context(payload)
    anova = _anova(ctx)
    means = _means(ctx, anova)
    regression = _regression(ctx) if ctx.analysis_type == "regression" else None
    recommendations = _recommendations(ctx, anova, means, regression)

    result = {
        "meta": {
            "design": ctx.design,
            "analysis_type": ctx.analysis_type,
            "n_rows": int(len(ctx.df)),
            "response_column": ctx.response,
            "treatment_column": ctx.treatment,
            "goal": ctx.goal,
        },
        "anova": anova,
        "means": means,
        "regression": regression,
        "recommendations": recommendations,
    }
    return _clean_value(result)


def _recommendations(ctx: AnalysisContext, anova: Dict[str, Any], means: Dict[str, Any], regression: Optional[Dict[str, Any]]) -> List[str]:
    messages: List[str] = []
    cv = anova.get("cv")
    if cv is not None:
        messages.append(f"CV experimental: {cv:.2f}% ({_cv_label(cv)}).")

    anova_table = anova.get("table", [])
    significant_sources = [r for r in anova_table if r.get("significance") in {"1%", "5%"}]
    if anova_table:
        if significant_sources:
            for row in significant_sources:
                if row.get("source") != "Total":
                    messages.append(f"{row['source']} significativo a {row['significance']}; priorize interpretação dessa fonte de variação.")
        else:
            messages.append("Nenhuma fonte de variação foi significativa a 5%; revise objetivo, variabilidade e poder experimental antes de concluir ausência de efeito.")

    best = means.get("best") if means else None
    if best:
        direction = "maior" if ctx.goal == "max" else "menor"
        messages.append(f"Tratamento com {direction} média: {best['treatment']} ({float(best['mean']):.3f}).")

    if regression:
        selected = regression.get("selected_model") or {}
        opt = selected.get("optimum") or {}
        if opt.get("x") is not None:
            messages.append(f"Regressão sugerida: grau {regression['selected_degree']} com R² ajustado {selected.get('adj_r2'):.3f}; ponto ótimo estimado em x={opt['x']:.3f}.")
        messages.append(regression.get("recommendation", ""))

    return [m for m in messages if m]
