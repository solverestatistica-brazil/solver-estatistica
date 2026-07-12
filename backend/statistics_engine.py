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
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
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
    # [FIX 3.4] CV abaixo de 0,5 % é sinal de dados agregados/sinteticos,
    # nao de precisao excelente. Distinguimos essa faixa antes de rotular como "Otimo".
    if cv is None:
        return "Indisponível"
    if cv < 0.5:
        return "Muito baixo — verifique variabilidade"
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



def _coerce_categorical(df: pd.DataFrame, columns: Iterable[str]) -> None:
    """[FIX 3.1] Forca colunas categoricas a str.

    Elimina o KeyError '90' em fatorial/split-plot com fator numerico.
    O numeric_factor_column continua sendo lido via pd.to_numeric na regressao.
    """
    for col in columns:
        if col and col in df.columns:
            df[col] = df[col].astype(str)


def _dedupe_keep_order(values: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    output: List[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output

def _has_blank(series: pd.Series) -> bool:
    return series.isna().any() or series.astype(str).str.strip().eq("").any()

def _factor_key(column: str) -> str:
    return f'C({_q(column)})'

def _anova_source(anova: Dict[str, Any], raw_source: str) -> Optional[Dict[str, Any]]:
    for row in anova.get("table", []) or []:
        if row.get("raw_source") == raw_source:
            return row
    return None

def _is_significant_source(anova: Dict[str, Any], raw_source: str) -> bool:
    row = _anova_source(anova, raw_source)
    return bool(row and row.get("significance") in {"1%", "5%"})

def _validate_complete_grid(df: pd.DataFrame, keys: List[str], expected: int, label: str) -> None:
    counts = df.groupby(keys, dropna=False).size()
    if not counts.empty and counts.max() > 1:
        raise ValueError(f"{label}: foi encontrada mais de uma observação para a mesma combinação ({' × '.join(keys)}).")
    if len(counts) < expected:
        raise ValueError(f"{label}: faltam combinações obrigatórias em {' × '.join(keys)}.")
    if not (counts == 1).all():
        raise ValueError(f"{label}: cada combinação em {' × '.join(keys)} deve aparecer exatamente uma vez.")

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

    response = str(payload.get("response_column") or "valor").strip()
    treatment = str(payload.get("treatment_column") or "tratamento").strip()
    design = (payload.get("design") or "DIC").upper()
    analysis_type = payload.get("analysis_type") or "single"
    goal = payload.get("goal") or "max"
    payload["response_column"] = response
    payload["treatment_column"] = treatment

    if design not in ALLOWED_DESIGNS:
        raise ValueError(f"Delineamento inválido: {design}. Use DIC, DBC ou DQL.")
    if analysis_type not in ALLOWED_ANALYSIS_TYPES:
        raise ValueError(f"Tipo de análise inválido: {analysis_type}.")
    if goal not in {"max", "min"}:
        raise ValueError("Objetivo inválido. Use 'max' para maior resposta ou 'min' para menor resposta.")

    factor_columns = _dedupe_keep_order([str(c).strip() for c in (payload.get("factor_columns") or []) if str(c).strip()])
    payload["factor_columns"] = factor_columns

    required = [response]
    if analysis_type in {"factorial", "split_plot"} and treatment not in df.columns and factor_columns:
        if all(f in df.columns for f in factor_columns):
            df[treatment] = df[factor_columns].astype(str).agg(" x ".join, axis=1)
    if analysis_type != "regression":
        required.append(treatment)
    if design == "DBC":
        required.append(payload.get("block_column") or "bloco")
    if design == "DQL":
        required.extend([payload.get("row_column") or "linha", payload.get("column_column") or "coluna"])
    if analysis_type in {"factorial", "split_plot"}:
        required.extend(factor_columns)
    numeric_col = str(payload.get("numeric_factor_column") or payload.get("dose_column") or "").strip() or None
    if analysis_type == "regression" and numeric_col:
        required.append(numeric_col)

    required = _dedupe_keep_order([str(c).strip() for c in required if str(c).strip()])
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError("Colunas ausentes na base: " + ", ".join(missing))

    df[response] = pd.to_numeric(df[response], errors="coerce")
    if df[response].isna().any():
        bad = int(df[response].isna().sum())
        raise ValueError(f"A coluna de resposta '{response}' contém {bad} valor(es) vazio(s) ou não numérico(s).")

    categorical_required = [c for c in required if c != response and c != numeric_col]
    for column in categorical_required:
        if _has_blank(df[column]):
            raise ValueError(f"A coluna '{column}' contém valor(es) vazio(s).")
        df[column] = df[column].astype(str).str.strip()

    df = df.dropna(subset=[response]).copy()

    # [FIX 3.1] coerce_categorical: garante que colunas usadas como fator
    # categorico (treatment/block/row/column/factor_columns) sejam string,
    # eliminando a incompatibilidade int/str que causava KeyError '90'.
    _cat_cols = set()
    if analysis_type != "regression":
        _cat_cols.add(treatment)
    if design == "DBC":
        _cat_cols.add(payload.get("block_column") or "bloco")
    if design == "DQL":
        _cat_cols.add(payload.get("row_column") or "linha")
        _cat_cols.add(payload.get("column_column") or "coluna")
    if analysis_type in {"factorial", "split_plot"}:
        for _f in (payload.get("factor_columns") or []):
            _cat_cols.add(_f)
    _coerce_categorical(df, [c for c in _cat_cols if c])

    if analysis_type == "regression":
        _validate_regression_input(df, payload, response, treatment)
    else:
        if df[treatment].nunique() < 2:
            raise ValueError("A análise precisa de pelo menos 2 tratamentos.")
        _validate_design(df, payload, design, treatment)
    return AnalysisContext(df=df, payload=payload, response=response, treatment=treatment, design=design, analysis_type=analysis_type, goal=goal)

def _validate_regression_input(df: pd.DataFrame, payload: Dict[str, Any], response: str, treatment: str) -> None:
    numeric_col = str(payload.get("numeric_factor_column") or payload.get("dose_column") or "").strip() or None
    if numeric_col:
        if numeric_col not in df.columns:
            raise ValueError(f"Coluna numérica/dose ausente na base: {numeric_col}")
        x = pd.to_numeric(df[numeric_col], errors="coerce")
        bad = int(x.isna().sum())
        if bad:
            raise ValueError(f"A coluna numérica '{numeric_col}' contém {bad} valor(es) vazio(s) ou não numérico(s).")
    elif treatment in df.columns:
        x = _parse_numeric_from_text(df[treatment])
        bad = int(x.isna().sum())
        if bad:
            raise ValueError("Para regressão, informe uma coluna de dose numérica ou use tratamentos com valores numéricos reconhecíveis.")
    else:
        raise ValueError("Para regressão, informe a coluna de dose/fator numérico.")

    n_levels = int(pd.Series(x).nunique())
    if n_levels < 3:
        raise ValueError("A regressão precisa de pelo menos 3 doses ou níveis numéricos distintos, para manter 1 grau de liberdade residual e evitar curvas superajustadas (ajuste perfeito).")

    requested_degree = payload.get("regression_degree")
    if requested_degree:
        requested_degree = int(requested_degree)
        if requested_degree not in {1, 2, 3}:
            raise ValueError("O grau de regressão deve ser 1, 2 ou 3.")
        if n_levels < requested_degree + 2:
            raise ValueError(f"Regressão de grau {requested_degree} exige pelo menos {requested_degree + 2} níveis numéricos distintos, para manter 1 grau de liberdade residual e evitar curvas superajustadas.")

def _validate_design(df: pd.DataFrame, payload: Dict[str, Any], design: str, treatment: str) -> None:
    """Valida regras críticas de cada delineamento experimental."""
    analysis_type = payload.get("analysis_type") or "single"

    if design == "DIC":
        reps = df.groupby(treatment, dropna=False).size()
        if reps.min() < 1:
            raise ValueError("No DIC, cada tratamento deve ter ao menos uma observação.")
        n_treat = df[treatment].nunique()
        if len(df) <= n_treat:
            raise ValueError(
                "No DIC, é preciso haver ao menos uma repetição a mais do que o número de "
                "tratamentos, para que sobrem graus de liberdade para estimar o erro (resíduo)."
            )

    if design == "DBC" and analysis_type not in ("factorial", "split_plot"):
        block = payload.get("block_column") or "bloco"
        if df[block].nunique() < 2:
            raise ValueError("No DBC, informe pelo menos 2 blocos.")
        expected = int(df[block].nunique() * df[treatment].nunique())
        _validate_complete_grid(df, [block, treatment], expected, "No DBC")

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
        _validate_complete_grid(df, [row, col], int(n_t * n_t), "No DQL")
        _validate_complete_grid(df, [row, treatment], int(n_r * n_t), "No DQL")
        _validate_complete_grid(df, [col, treatment], int(n_c * n_t), "No DQL")

    if analysis_type in {"factorial", "split_plot"}:
        factors = payload.get("factor_columns") or []
        if len(factors) < 2:
            raise ValueError("Para análise fatorial ou parcelas subdivididas, informe pelo menos dois fatores.")
        for factor in factors:
            if df[factor].nunique() < 2:
                raise ValueError(f"O fator '{factor}' precisa ter pelo menos 2 níveis.")
        expected_combinations = 1
        for factor in factors:
            expected_combinations *= int(df[factor].nunique())
        combo_counts = df.groupby(factors, dropna=False).size()
        if len(combo_counts) < expected_combinations:
            raise ValueError("Faltam combinações entre os níveis dos fatores informados.")
        if design == "DBC":
            block = payload.get("block_column") or "bloco"
            expected = int(df[block].nunique() * expected_combinations)
            _validate_complete_grid(df, [block] + factors, expected, "Na estrutura fatorial em DBC")
        elif analysis_type == "split_plot":
            raise ValueError("Parcelas subdivididas exigem delineamento base DBC neste MVP para validar blocos, parcelas e subparcelas.")

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

def _find_interaction_row(index: Any, key_a: str, key_b: str) -> Optional[str]:
    """Localiza o termo de interação em um índice de resultado do anova_lm, independente da
    ordem em que o patsy tenha nomeado o termo (key_a:key_b ou key_b:key_a)."""
    for candidate in (f"{key_a}:{key_b}", f"{key_b}:{key_a}"):
        if candidate in index:
            return candidate
    return None


def _anova_split_plot(ctx: AnalysisContext) -> Dict[str, Any]:
    """ANOVA de parcelas subdivididas com dois estratos de erro (Gomez & Gomez / Steel &
    Torrie). O fator de parcela (whole-plot) precisa ser testado contra o Erro (a) = Bloco ×
    Parcela; o fator de subparcela e a interação Parcela × Subparcela são testados contra o
    Erro (b) = resíduo. A versão anterior ajustava um único modelo OLS e usava o mesmo
    resíduo fino para testar todas as fontes, inflando artificialmente o F do fator de
    parcela (ex.: F=39,60 relatado pela auditoria contra o F=8,13 correto)."""
    p = ctx.payload
    response = ctx.response
    block = p.get("block_column") or "bloco"
    factors = p.get("factor_columns") or []
    if len(factors) < 2:
        raise ValueError("Para parcelas subdivididas, informe fator de parcela e fator de subparcela.")
    main, sub = factors[0], factors[1]

    notes = [
        f"Parcelas subdivididas: o fator de parcela ({main}) é testado contra o Erro (a) "
        f"(interação Bloco × Parcela); o fator de subparcela ({sub}) e a interação "
        f"{main} × {sub} são testados contra o Erro (b) (resíduo)."
    ]

    block_key = _c(block)
    main_key = _c(main)
    sub_key = _c(sub)
    formula = f"{_q(response)} ~ {block_key} * {main_key} + {sub_key} + {main_key}:{sub_key}"
    model = smf.ols(formula, data=ctx.df).fit()
    table = anova_lm(model, typ=2)

    errA_key = _find_interaction_row(table.index, block_key, main_key)
    ab_key = _find_interaction_row(table.index, main_key, sub_key)
    resid_key = "Residual"

    def get_row(key: Optional[str]) -> Optional[Dict[str, Any]]:
        if key is None or key not in table.index:
            return None
        r = table.loc[key]
        return {"df": _num(r.get("df")), "sum_sq": _num(r.get("sum_sq"))}

    block_r = get_row(block_key)
    main_r = get_row(main_key)
    errA_r = get_row(errA_key)
    sub_r = get_row(sub_key)
    ab_r = get_row(ab_key)
    resid_r = get_row(resid_key)

    if not (main_r and errA_r and sub_r and ab_r and resid_r):
        raise ValueError(
            "Não foi possível montar a ANOVA de parcelas subdivididas com os dados informados. "
            "Verifique se o delineamento está balanceado (mesmo número de blocos, parcelas e "
            "subparcelas em todas as combinações)."
        )

    def mean_sq(row: Optional[Dict[str, Any]]) -> Optional[float]:
        if not row or not row.get("df"):
            return None
        return row["sum_sq"] / row["df"]

    ms_errA = mean_sq(errA_r)
    ms_errB = mean_sq(resid_r)

    def f_test(row: Dict[str, Any], err_ms: Optional[float], err_df: Optional[float]):
        ms = mean_sq(row)
        if ms is None or err_ms in (None, 0) or not err_df or err_df <= 0 or not row.get("df"):
            return None, None, None, None
        f_calc = ms / err_ms
        f5 = stats.f.ppf(0.95, row["df"], err_df)
        f1 = stats.f.ppf(0.99, row["df"], err_df)
        p_value = float(stats.f.sf(f_calc, row["df"], err_df))
        return f_calc, f5, f1, p_value

    def build_row(source: str, raw_source: str, row: Dict[str, Any], err_ms, err_df) -> Dict[str, Any]:
        f_calc, f5, f1, p_value = f_test(row, err_ms, err_df)
        return {
            "source": source,
            "raw_source": raw_source,
            "df": row.get("df"),
            "sum_sq": row.get("sum_sq"),
            "mean_sq": mean_sq(row),
            "f_calc": f_calc,
            "f_5": f5,
            "f_1": f1,
            "p_value": p_value,
            "significance": _significance(p_value),
        }

    rows: List[Dict[str, Any]] = []
    if block_r:
        rows.append(build_row("Blocos", block_key, block_r, ms_errA, errA_r.get("df")))
    rows.append(build_row(f"Parcela ({main})", main_key, main_r, ms_errA, errA_r.get("df")))
    rows.append({
        "source": "Erro (a) — Bloco × Parcela", "raw_source": errA_key, "df": errA_r.get("df"),
        "sum_sq": errA_r.get("sum_sq"), "mean_sq": ms_errA, "f_calc": None, "f_5": None,
        "f_1": None, "p_value": None, "significance": "—",
    })
    rows.append(build_row(f"Subparcela ({sub})", sub_key, sub_r, ms_errB, resid_r.get("df")))
    rows.append(build_row(f"{main} × {sub}", ab_key, ab_r, ms_errB, resid_r.get("df")))
    rows.append({
        "source": "Erro (b) — Resíduo", "raw_source": resid_key, "df": resid_r.get("df"),
        "sum_sq": resid_r.get("sum_sq"), "mean_sq": ms_errB, "f_calc": None, "f_5": None,
        "f_1": None, "p_value": None, "significance": "—",
    })

    total_ss = float(((ctx.df[response] - ctx.df[response].mean()) ** 2).sum())
    rows.append({
        "source": "Total", "raw_source": "Total", "df": int(len(ctx.df) - 1), "sum_sq": total_ss,
        "mean_sq": None, "f_calc": None, "f_5": None, "f_1": None, "p_value": None, "significance": "—",
    })

    mean_response = float(ctx.df[response].mean())
    cv = (math.sqrt(ms_errB) / abs(mean_response) * 100) if ms_errB is not None and mean_response != 0 else None

    return {
        "formula": formula,
        "table": rows,
        "mse": ms_errB,
        "df_error": resid_r.get("df"),
        "error_a": {"mse": ms_errA, "df": errA_r.get("df")},
        "cv": cv,
        "cv_label": _cv_label(cv),
        "model_notes": notes,
    }


def _anova(ctx: AnalysisContext) -> Dict[str, Any]:
    if ctx.analysis_type == "split_plot":
        return _anova_split_plot(ctx)
    formula, notes = _formula_for(ctx)
    if not formula:
        return {"table": [], "cv": None, "cv_label": "Indisponível", "model_notes": notes}

    model = smf.ols(formula, data=ctx.df).fit()
    table = anova_lm(model, typ=2)
    df_resid = float(model.df_resid)
    mse = float(model.mse_resid) if model.df_resid > 0 else None

    # [FIX 3.2] Guarda contra residuo numericamente nulo. Quando MSE eh
    # ordens de magnitude menor que a variancia total, F/p sao ruido de
    # ponto flutuante e nao devem ser publicados como resultado estatistico.
    _total_var_ = float(ctx.df[ctx.response].var(ddof=0)) or 1.0
    _residual_is_singular_ = mse is not None and mse < 1e-10 * _total_var_
    if _residual_is_singular_:
        notes.append(
            "Resíduo praticamente nulo (MSE ≈ 0). Os valores de F e p são "
            "numericamente instáveis — provavelmente os dados são aditivos "
            "entre blocos e tratamentos, sem variabilidade dentro de célula. "
            "Refaça com dados reais de campo."
        )
    mean_response = float(ctx.df[ctx.response].mean())
    cv = None if _residual_is_singular_ else ((math.sqrt(mse) / abs(mean_response) * 100) if mse is not None and mean_response != 0 else None)

    rows: List[Dict[str, Any]] = []
    for idx, row in table.iterrows():
        dfv = _num(row.get("df"))
        sum_sq = _num(row.get("sum_sq"))
        mean_sq = (sum_sq / dfv) if sum_sq is not None and dfv not in (None, 0) else None
        f_value = _num(row.get("F"))
        p_value = _num(row.get("PR(>F)"))
        # [FIX 3.2] Se o residuo eh singular, F/p das fontes reais sao ruido.
        if _residual_is_singular_ and str(idx) != "Residual":
            f_value = None
            p_value = None
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
        "residual_is_singular": _residual_is_singular_,
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

def _alpha_for_row(row: Optional[Dict[str, Any]]) -> float:
    """Deriva o alfa do pós-teste diretamente da significância (1% ou 5%) da fonte de
    variação no teste F, em vez de usar um valor fixo enviado pelo front-end."""
    sig = (row or {}).get("significance")
    if sig == "1%":
        return 0.01
    return 0.05

def _comparison_tests(table: pd.DataFrame, anova: Dict[str, Any], ctx: AnalysisContext) -> Optional[Dict[str, Any]]:
    mse = anova.get("mse")
    df_error = anova.get("df_error")
    if mse is None or not df_error or df_error <= 0 or table["treatment"].nunique() < 2:
        return None

    source_key = _factor_key(ctx.treatment)
    if not _is_significant_source(anova, source_key):
        return None

    test_name = (ctx.payload.get("comparison_test") or "tukey").lower()
    if test_name not in ALLOWED_TESTS:
        test_name = "tukey"
    alpha = _alpha_for_row(_anova_source(anova, source_key))

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
                    else: # Tukey-Kramer
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
    """Gera letras compactas (CLD) via enumeração de cliques maximais (Bron-Kerbosch).
    A versão anterior era gulosa/sequencial e falha no caso clássico de não transitividade
    (A≈B, B≈C, A≠C): B precisa herdar as duas letras ('a' de {A,B} e 'b' de {B,C}), mas o
    algoritmo guloso só comparava cada novo tratamento contra grupos já fechados e nunca
    reabria um novo grupo {B,C} porque B já tinha sido "colocado" no primeiro grupo."""
    if not order:
        return {}
    if len(order) == 1:
        return {order[0]: "a"}

    def non_significant(a: str, b: str) -> bool:
        return tuple(sorted((a, b))) in nonsig_pairs

    graph: Dict[str, set] = {g: {h for h in order if h != g and non_significant(g, h)} for g in order}

    cliques: List[set] = []

    def bron_kerbosch(r: set, p: set, x: set) -> None:
        if not p and not x:
            if r:
                cliques.append(set(r))
            return
        for v in list(p):
            bron_kerbosch(r | {v}, p & graph[v], x & graph[v])
            p = p - {v}
            x = x | {v}

    bron_kerbosch(set(), set(order), set())

    covered: set = set()
    for c in cliques:
        covered |= c
    for g in order:
        if g not in covered:
            cliques.append({g})

    cliques = [c for i, c in enumerate(cliques) if not any(c < other for j, other in enumerate(cliques) if i != j)]

    position = {g: i for i, g in enumerate(order)}
    cliques.sort(key=lambda c: min(position[g] for g in c))

    letters: Dict[str, str] = {g: "" for g in order}
    for idx, clique in enumerate(cliques):
        letter = chr(ord("a") + idx)
        for g in clique:
            letters[g] += letter
    return letters

def _regression(ctx: AnalysisContext) -> Optional[Dict[str, Any]]:
    p = ctx.payload
    response = ctx.response
    numeric_col = str(p.get("numeric_factor_column") or p.get("dose_column") or "").strip() or None
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
    if reg_df["x"].nunique() < 3:
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
    # Mantem ao menos 1 grau de liberdade residual (nunique >= degree + 2):
    # sem isso o ajuste fica perfeito/superajustado e a curva oscila de forma
    # instavel fora dos pontos observados ("curva infinita").
    max_degree = min(3, int(reg_df["x"].nunique()) - 2)
    if max_degree < 1:
        return None
    models: List[Dict[str, Any]] = []

    for degree in range(1, max_degree + 1):
        fit = _fit_poly(reg_df["x"].to_numpy(dtype=float), reg_df["y"].to_numpy(dtype=float), degree, ctx.goal)
        fit["degree"] = degree
        models.append(fit)

    if not models:
        return None

    best = sorted(models, key=lambda m: (m.get("adj_r2") if m.get("adj_r2") is not None else -999), reverse=True)[0]
    selected = next((m for m in models if m["degree"] == requested_degree), best) if requested_degree else best
    if requested_degree and selected["degree"] != best["degree"]:
        # Antes o backend substituía silenciosamente o grau pedido pelo usuário pelo de
        # maior R² ajustado (selected = best), mesmo a mensagem soando como um aviso
        # opcional. Agora o grau escolhido pelo usuário é sempre respeitado; a mensagem
        # apenas sinaliza que outro grau teve R² ajustado maior.
        recommendation = (
            f"Você escolheu o grau {requested_degree} (R² ajustado {selected['adj_r2']:.3f}). "
            f"O grau {best['degree']} teve R² ajustado maior ({best['adj_r2']:.3f}), "
            f"mas o grau solicitado foi mantido."
        )
    else:
        recommendation = "Modelo escolhido pelo maior R² ajustado."

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
    # Centraliza x (x - media) antes de ajustar: evita mal-condicionamento
    # numerico do polinomio em escala bruta (ex.: 120**3 = 1.728.000), que
    # gera curvas instaveis/"infinitas" mesmo com graus de liberdade validos.
    # Os coeficientes sao convertidos de volta para a escala original de x
    # no final, entao equation/optimum/fitted_curve continuam em x bruto.
    x_mean = float(np.mean(x))
    u = x - x_mean
    X = np.column_stack([u ** i for i in range(1, degree + 1)])
    X = sm.add_constant(X)
    model = sm.OLS(y, X).fit()
    centered_coeffs = model.params.tolist()  # intercepto, u, u², u³... (u = x - x_mean)
    p_u = np.poly1d(list(reversed(centered_coeffs)))
    p_x = p_u(np.poly1d([1, -x_mean]))
    raw_coeffs = list(reversed(np.atleast_1d(p_x.coefficients).tolist()))
    while len(raw_coeffs) < len(centered_coeffs):
        raw_coeffs.append(0.0)
    coeffs = raw_coeffs # intercepto, x, x², x³...
    equation = _equation_text(coeffs)
    optimum = _poly_optimum(coeffs, float(np.min(x)), float(np.max(x)), goal)
    return {
        "r2": float(model.rsquared),
        "adj_r2": float(model.rsquared_adj),
        "aic": float(model.aic),
        "bic": float(model.bic),
        "p_model": float(model.f_pvalue) if model.f_pvalue is not None and not np.isnan(model.f_pvalue) else None,
        "p_top_term": (float(model.pvalues[-1]) if len(list(model.pvalues)) > 0 and not (math.isnan(float(model.pvalues[-1])) or math.isinf(float(model.pvalues[-1]))) else None),  # [FIX 3.3]
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
    if len(coeffs) == 3: # quadrático
        b = coeffs[1]
        c = coeffs[2]
        if c != 0:
            vertex = -b / (2 * c)
            if x_min <= vertex <= x_max:
                candidates.append(vertex)
    elif len(coeffs) == 4: # cúbico: derivada b + 2cx + 3dx²
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

def _pairwise_letters(
    levels: List[str], means: Dict[str, float], ns: Dict[str, int],
    mse: float, df_error: float, alpha: float, test_name: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Rotina compartilhada de comparação de médias duas a duas (Tukey-Kramer, Duncan, SNK ou
    Scheffé), reaproveitada tanto para médias marginais de fator quanto para efeitos simples
    dentro do desdobramento de interação."""
    k = len(levels)
    comparisons: List[Dict[str, Any]] = []
    nonsig_pairs: set = set()
    sorted_by_mean = sorted(levels, key=lambda g: means[g], reverse=True)
    for i, g1 in enumerate(sorted_by_mean):
        for j, g2 in enumerate(sorted_by_mean[i + 1:], start=i + 1):
            diff = means[g1] - means[g2]
            se = math.sqrt(mse / 2 * (1 / ns[g1] + 1 / ns[g2])) if ns[g1] and ns[g2] else None
            if se is None:
                continue
            if test_name == "scheffe":
                fcrit = stats.f.ppf(1 - alpha, k - 1, df_error)
                crit = math.sqrt((k - 1) * fcrit * mse * (1 / ns[g1] + 1 / ns[g2]))
            else:
                range_size = abs(j - i) + 1
                if test_name == "snk":
                    qcrit = studentized_range.ppf(1 - alpha, range_size, df_error)
                elif test_name == "duncan":
                    alpha_r = 1 - (1 - alpha) ** (range_size - 1)
                    qcrit = studentized_range.ppf(1 - alpha_r, range_size, df_error)
                else:
                    qcrit = studentized_range.ppf(1 - alpha, k, df_error)
                crit = qcrit * se
            significant = abs(diff) > crit
            if not significant:
                nonsig_pairs.add(tuple(sorted((g1, g2))))
            comparisons.append({
                "group_a": g1, "group_b": g2, "diff": diff,
                "critical_diff": crit, "significant": bool(significant),
            })
    letters = _assign_letters(levels, nonsig_pairs)
    return comparisons, letters


def _factor_comparisons(ctx: AnalysisContext, anova: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Para fatorial/parcelas subdivididas: compara as médias marginais de cada fator quando
    seu efeito principal é significativo na ANOVA. No split-plot, o fator de parcela usa o
    Erro (a); o fator de subparcela usa o Erro (b). Ausente na versão anterior, que só
    comparava os níveis de 'treatment_column' (a combinação completa), sem decompor por fator."""
    if ctx.analysis_type not in {"factorial", "split_plot"}:
        return []
    factors = ctx.payload.get("factor_columns") or []
    if len(factors) < 2:
        return []
    error_a = anova.get("error_a") or {}
    test_name = (ctx.payload.get("comparison_test") or "tukey").lower()
    if test_name not in ALLOWED_TESTS:
        test_name = "tukey"
    results: List[Dict[str, Any]] = []
    for i, factor in enumerate(factors[:2]):
        raw_key = _c(factor)
        if not _is_significant_source(anova, raw_key):
            continue
        alpha = _alpha_for_row(_anova_source(anova, raw_key))
        if ctx.analysis_type == "split_plot" and i == 0 and error_a.get("mse") is not None:
            use_mse, use_df = error_a["mse"], error_a["df"]
        else:
            use_mse, use_df = anova.get("mse"), anova.get("df_error")
        if use_mse is None or not use_df or use_df <= 0:
            continue

        grouped = ctx.df.groupby(factor)[ctx.response]
        table = grouped.agg(["mean", "count"]).reset_index().rename(columns={factor: "treatment", "count": "n"})
        table = table.sort_values("mean", ascending=(ctx.goal == "min"))
        if table["treatment"].nunique() < 2:
            continue

        means = {str(r["treatment"]): float(r["mean"]) for _, r in table.iterrows()}
        ns = {str(r["treatment"]): int(r["n"]) for _, r in table.iterrows()}
        levels = [str(v) for v in table["treatment"].tolist()]
        comparisons, letters = _pairwise_letters(levels, means, ns, use_mse, use_df, alpha, test_name)
        table["group"] = table["treatment"].astype(str).map(letters).fillna("")

        results.append({
            "factor": factor,
            "test": test_name.upper(),
            "alpha": alpha,
            "error_used": "a" if (ctx.analysis_type == "split_plot" and i == 0) else "b",
            "levels": table.to_dict(orient="records"),
            "comparisons": comparisons,
        })
    return results


def _interaction_breakdown(ctx: AnalysisContext, anova: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Desdobramento da interação: quando Parcela × Subparcela (ou Fator A × Fator B) é
    significativa, compara os níveis do segundo fator dentro de cada nível do primeiro
    (efeitos simples), sempre usando o Erro (b)/resíduo. Recurso ausente na versão anterior."""
    if ctx.analysis_type not in {"factorial", "split_plot"}:
        return []
    factors = ctx.payload.get("factor_columns") or []
    if len(factors) < 2:
        return []
    main, sub = factors[0], factors[1]
    inter_key = f"{_c(main)}:{_c(sub)}"
    if not _is_significant_source(anova, inter_key):
        return []

    mse = anova.get("mse")
    df_error = anova.get("df_error")
    if mse is None or not df_error or df_error <= 0:
        return []

    test_name = (ctx.payload.get("comparison_test") or "tukey").lower()
    if test_name not in ALLOWED_TESTS:
        test_name = "tukey"
    alpha = _alpha_for_row(_anova_source(anova, inter_key))

    blocks: List[Dict[str, Any]] = []
    for level_main, sub_df in ctx.df.groupby(main):
        grouped = sub_df.groupby(sub)[ctx.response]
        table = grouped.agg(["mean", "count"]).reset_index().rename(columns={sub: "treatment", "count": "n"})
        table = table.sort_values("mean", ascending=(ctx.goal == "min"))
        means = {str(r["treatment"]): float(r["mean"]) for _, r in table.iterrows()}
        ns = {str(r["treatment"]): int(r["n"]) for _, r in table.iterrows()}
        levels = [str(v) for v in table["treatment"].tolist()]
        if len(levels) < 2:
            table["group"] = "a" if levels else ""
        else:
            comparisons, letters = _pairwise_letters(levels, means, ns, mse, df_error, alpha, test_name)
            table["group"] = table["treatment"].astype(str).map(letters).fillna("")
        blocks.append({
            "level": str(level_main),
            "factor": main,
            "sub_factor": sub,
            "test": test_name.upper(),
            "alpha": alpha,
            "levels": table.to_dict(orient="records"),
        })
    return blocks


def analyze(payload: Dict[str, Any]) -> Dict[str, Any]:
    ctx = _prepare_context(payload)
    anova = _anova(ctx)
    means = _means(ctx, anova)
    regression = _regression(ctx) if ctx.analysis_type in {"regression", "single", "factorial"} else None
    factor_comparisons = _factor_comparisons(ctx, anova)
    interaction_breakdown = _interaction_breakdown(ctx, anova)
    recommendations = _recommendations(ctx, anova, means, regression)
    if interaction_breakdown:
        factors = ctx.payload.get("factor_columns") or []
        if len(factors) >= 2:
            recommendations.append(
                f"A interação {factors[0]} × {factors[1]} foi significativa: interprete os "
                f"efeitos simples (desdobramento da interação) em vez das médias marginais "
                f"isoladas de cada fator."
            )

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
        "factor_comparisons": factor_comparisons,
        "interaction_breakdown": interaction_breakdown,
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
    elif ctx.analysis_type == "regression":
        messages.append("Regressão não foi calculada: são necessários ao menos 3 níveis numéricos distintos do fator, com 1 grau de liberdade residual, para evitar curvas superajustadas.")

    return [m for m in messages if m]
