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

import assumptions
import transformations

ALLOWED_DESIGNS = {"DIC", "DBC", "DQL"}
ALLOWED_ANALYSIS_TYPES = {"single", "factorial", "split_plot", "regression"}
ALLOWED_TESTS = {"tukey", "duncan", "dunnett", "snk", "scheffe", "scott_knott"}

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
    # [FIX 3.2-sp] Guarda contra residuo singular no split-plot.
    _sp_total_var_ = float(ctx.df[ctx.response].var(ddof=0)) or 1.0
    _sp_singular_ = (ms_errB is not None and ms_errB < 1e-10 * _sp_total_var_) or (ms_errA is not None and ms_errA < 1e-10 * _sp_total_var_)
    if _sp_singular_:
        notes.append(
            "Split-plot: erro (a) e/ou erro (b) sao praticamente nulos (MSE ~ 0). "
            "F e p sao numericamente instaveis; refaca com dados de campo reais "
            "que tenham variabilidade dentro de cada bloco x tratamento."
        )

    def f_test(row: Dict[str, Any], err_ms: Optional[float], err_df: Optional[float]):
        # [FIX P0-3] Se o erro (a) ou (b) e singular, F e p sao ruido de ponto flutuante
        # (divisao por MSE~0 gera valores astronomicos tipo F=2e27, p=0.0, publicados
        # como se fossem resultado real). A versao anterior calculava e publicava esses
        # valores mesmo assim, so anexando uma nota que o frontend ignorava.
        if _sp_singular_:
            return None, None, None, None
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
    cv = None if _sp_singular_ else ((math.sqrt(ms_errB) / abs(mean_response) * 100) if ms_errB is not None and mean_response != 0 else None)

    return {
        "formula": formula,
        "table": rows,
        "mse": ms_errB,
        "df_error": resid_r.get("df"),
        "error_a": {"mse": ms_errA, "df": errA_r.get("df")},
        "residual_is_singular": _sp_singular_,   # o frontend precisa dessa flag
        "cv": cv,
        "cv_label": _cv_label(cv),
        "model_notes": notes,
        "residuals": model.resid.to_numpy(float).tolist(),
    }


def _anova(ctx: AnalysisContext) -> Dict[str, Any]:
    if ctx.analysis_type == "split_plot":
        return _anova_split_plot(ctx)
    formula, notes = _formula_for(ctx)
    if not formula:
        return {"table": [], "cv": None, "cv_label": "Indisponível", "residual_is_singular": False, "model_notes": notes}

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
        "residuals": model.resid.to_numpy(float).tolist(),
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

def _alpha_for_row(payload: Dict[str, Any], row: Optional[Dict[str, Any]]) -> float:
    """Alfa do pós-teste. Dois modos, escolhidos pelo usuário via payload['alpha_mode']:

    - 'auto' (padrão): deriva o alfa diretamente da significância (1% ou 5%) da fonte de
      variação no teste F — convenção clássica de Pimentel Gomes (Tukey a 1% quando o F foi
      significativo a 1%, a 5% quando significativo a 5%).
    - 'fixed': usa o alfa informado a priori em payload['alpha'], igual em toda a análise,
      independente do p-valor observado no teste F.
    """
    if str(payload.get("alpha_mode") or "auto").lower() == "fixed":
        try:
            alpha = float(payload.get("alpha", 0.05))
        except (TypeError, ValueError):
            alpha = 0.05
        return alpha if 0 < alpha < 1 else 0.05
    sig = (row or {}).get("significance")
    if sig == "1%":
        return 0.01
    return 0.05

def _dunnett_exact(
    diffs: List[float], ns: List[int], n_control: int, mse: float, df_error: float, alpha: float,
) -> Tuple[List[float], List[float]]:
    """Dunnett exato via distribuicao t multivariada (Dunnett, 1955), em vez da aproximacao
    conservadora t + Bonferroni. Ao contrario de scipy.stats.dunnett (que so aceita amostras
    brutas de um delineamento inteiramente casualizado), esta versao usa o MSE e os GL da
    propria ANOVA — respeitando blocos, quadrado latino ou fatorial — igual ao Tukey/Duncan/
    SNK/Scheffe deste modulo.

    Formula da correlacao entre duas comparacoes i, j contra o mesmo controle (Dunnett 1955):
        rho_ij = (1/n0) / sqrt((1/ni + 1/n0) * (1/nj + 1/n0))
    Com n0 = repeticoes do controle. Para grupos balanceados (ni=nj=n0), rho=0,5.

    Validado numericamente contra scipy.stats.dunnett (que implementa o mesmo teste para o
    caso balanceado/desbalanceado de via unica): valor critico e p-valores concordam com
    diferenca tipicamente na ordem de 1e-4 a 3e-4 — o piso de precisao da integracao Monte
    Carlo quase-aleatoria da propria scipy (nao cai abaixo disso mesmo aumentando `maxpts`;
    testado ate 1e6 pontos). Essa ordem de grandeza nao muda decisao de significancia em
    nenhum alfa usual (1%/5%), mas o valor absoluto do p nao deve ser citado com mais de 3
    casas decimais.
    """
    m = len(diffs)
    if m == 0:
        return [], []
    se_list = [math.sqrt(mse * (1 / ns[i] + 1 / n_control)) for i in range(m)]
    t_stats = [diffs[i] / se_list[i] if se_list[i] else 0.0 for i in range(m)]

    if m == 1:
        # Um unico contraste: nao ha multiplicidade a corrigir, t de Student comum.
        crit_t = float(stats.t.ppf(1 - alpha / 2, df_error))
        p_value = float(2 * stats.t.sf(abs(t_stats[0]), df_error))
        return [crit_t * se_list[0]], [p_value]

    corr = np.empty((m, m))
    for i in range(m):
        for j in range(m):
            if i == j:
                corr[i, j] = 1.0
            else:
                corr[i, j] = (1.0 / n_control) / math.sqrt(
                    (1.0 / ns[i] + 1.0 / n_control) * (1.0 / ns[j] + 1.0 / n_control)
                )
    # random_state fixo: os resultados devem ser reproduziveis entre duas chamadas com os
    # mesmos dados (a integracao numerica da t multivariada usa Monte Carlo quase-aleatorio).
    mvt = stats.multivariate_t(loc=np.zeros(m), shape=corr, df=df_error, allow_singular=True, seed=42)

    def prob_all_within(c: float) -> float:
        return float(mvt.cdf(np.full(m, c), lower_limit=np.full(m, -c)))

    lo, hi = 0.0, 12.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if prob_all_within(mid) < 1 - alpha:
            lo = mid
        else:
            hi = mid
    c_star = (lo + hi) / 2

    crit_diffs = [c_star * se for se in se_list]
    p_values = [float(max(0.0, min(1.0, 1 - prob_all_within(abs(t))))) for t in t_stats]
    return crit_diffs, p_values


def _scott_knott_groups(
    names: List[str], means: Dict[str, float], ns: Dict[str, int], mse: float, df_error: float, alpha: float,
) -> List[List[str]]:
    """Agrupamento de Scott & Knott (1974, Biometrics 30:507-512) por particao recursiva de
    verossimilhanca — grupos sem sobreposicao de letras (ao contrario de Tukey/Duncan/SNK).

    [FIX auditoria 15/07/2026 pos-commit 0df4f3d] A versao anterior usava B0 (a SQ apenas do
    melhor split em 2 grupos) tambem no denominador de sigma0^2, e usava k graus de liberdade
    no qui-quadrado de referencia. Ambos divergem da formula canonica do artigo original:

        sigma0^2 = [T0 + v*s^2] / (k+v)              -- T0 = SQ TOTAL entre as k medias do
                                                          subconjunto (nao so do melhor split)
        lambda   = [pi / (2*(pi-2))] * B0 / sigma0^2  -- B0 = SQ do melhor split contiguo
        graus de liberdade do qui-quadrado de referencia: k / (pi-2)

    Com k=2 (unico split possivel), T0 == B0 sempre, entao so o df do qui-quadrado (k vs.
    k/(pi-2)) already muda a decisao — foi exatamente esse o caso reproduzido pela auditoria
    (T1=0.8510003, T2=1.9416329, T3=5.6462449, MSE=0.4982669, v=16, r=4): a formula antiga
    nao separava {T1,T2}; a formula correta separa, reproduzindo {T1},{T2},{T3}. Confirmado
    numericamente contra esse caso e recalibrado por simulacao (Tipo I entre 4,5% e 6,0% sob
    H0 com k=2..10, alvo nominal 5%; sem R disponivel neste ambiente para conferencia direta
    do pacote ScottKnott).

    Generalizacao para repeticoes desbalanceadas: substitui somas simples por somas ponderadas
    por n_i (reduz a formula acima quando todos os n_i sao iguais).
    """
    def recurse(subset: List[str]) -> List[List[str]]:
        k = len(subset)
        if k <= 1:
            return [subset]
        ordered = sorted(subset, key=lambda g: means[g])
        y = np.array([means[g] for g in ordered], dtype=float)
        n = np.array([ns[g] for g in ordered], dtype=float)
        N = float(n.sum())
        y_total = float((n * y).sum())
        best_B, best_i = -1.0, None
        for i in range(1, k):
            n1 = float(n[:i].sum())
            n2 = N - n1
            y1 = float((n[:i] * y[:i]).sum())
            y2 = y_total - y1
            b = (y1 ** 2) / n1 + (y2 ** 2) / n2 - (y_total ** 2) / N
            if b > best_B:
                best_B, best_i = b, i
        t0 = float((n * y ** 2).sum() - (y_total ** 2) / N)  # SQ total entre as k medias
        sigma0 = (df_error * mse + t0) / (df_error + k)
        if sigma0 <= 0 or best_i is None:
            return [ordered]
        lam = (math.pi / (2 * (math.pi - 2))) * best_B / sigma0
        crit = float(stats.chi2.ppf(1 - alpha, k / (math.pi - 2)))
        if lam <= crit:
            return [ordered]
        return recurse(ordered[:best_i]) + recurse(ordered[best_i:])

    return recurse(names)


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
    alpha = _alpha_for_row(ctx.payload, _anova_source(anova, source_key))

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

    sk_letters: Optional[Dict[str, str]] = None
    control_result: Optional[str] = None
    if test_name == "scott_knott":
        sk_groups = _scott_knott_groups(order, means, ns, mse, df_error, alpha)
        # _scott_knott_groups ordena internamente por media ascendente (independente do
        # goal); reordena os grupos aqui pela posicao em 'order' (que ja e' melhor->pior
        # conforme goal), para que a letra 'a' va sempre para o grupo com o tratamento
        # de melhor média — igual à convenção usada por _assign_letters no Tukey/Duncan/SNK.
        position = {g: i for i, g in enumerate(order)}
        sk_groups.sort(key=lambda grp: min(position[g] for g in grp))
        sk_letters = {}
        for idx, group in enumerate(sk_groups):
            letter = chr(ord("a") + idx)
            for g in group:
                sk_letters[g] = letter
        for i, g1 in enumerate(order):
            for g2 in order[i + 1:]:
                same_group = sk_letters[g1] == sk_letters[g2]
                comparisons.append({
                    "group_a": g1, "group_b": g2, "diff": means[g1] - means[g2],
                    "critical_diff": None, "p_value": None, "significant": not same_group,
                })
        method_note = (
            "Scott-Knott (1974): particiona os tratamentos em grupos sem sobreposição de "
            "letras, por partição recursiva de máxima verossimilhança — ao contrário de "
            "Tukey/Duncan/SNK/Scheffé, cada tratamento pertence a exatamente um grupo."
        )
    elif test_name == "dunnett":
        control_informado = ctx.payload.get("control_group")
        control = control_informado or order[-1]
        if str(control) not in means:
            control = order[-1]
        control = str(control)
        others = [g for g in groups if g != control]
        diffs = [means[g] - means[control] for g in others]
        ns_others = [ns[g] for g in others]
        crit_diffs, p_values = _dunnett_exact(diffs, ns_others, ns[control], mse, df_error, alpha)
        for g, diff, crit, p_value in zip(others, diffs, crit_diffs, p_values):
            add_result(g, control, diff, crit, p_value)
        # [FIX auditoria P1-02] Dunnett so testa cada tratamento contra a testemunha — nunca
        # tratamento contra tratamento. Um compact letter display (CLD) sugeriria relacoes
        # nunca testadas (ex.: dois tratamentos com letras diferentes por acaso de ordenacao,
        # quando na verdade nunca foram comparados entre si). Por isso o Dunnett nao usa
        # letras: 'testemunha' marca o controle, 'sig'/'ns' indica so a relacao com ela.
        sk_letters = {control: "testemunha"}
        for g, comp_row in zip(others, comparisons):
            sk_letters[g] = "sig" if comp_row["significant"] else "ns"
        control_result = control
        if control_informado and str(control_informado) in means:
            method_note = (
                f"Dunnett exato (distribuição t multivariada, Dunnett 1955) contra a testemunha "
                f"informada '{control}'."
            )
        else:
            method_note = (
                f"Testemunha não informada — o sistema usou '{control}' (extremo da ordenação por "
                f"média) como controle. Para um resultado correto, informe explicitamente qual "
                f"tratamento é a testemunha real do experimento. Teste: Dunnett exato (distribuição "
                f"t multivariada, Dunnett 1955)."
            )
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

    letters = sk_letters if sk_letters is not None else _assign_letters(order, nonsig_pairs)
    return {
        "test": test_name.upper(),
        "alpha": alpha,
        "letters": letters,
        "comparisons": comparisons,
        "control": control_result,
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
    else:
        # [FIX P0-6] A regressao so faz sentido com um eixo quantitativo DECLARADO
        # via numeric_factor_column. O fallback anterior extraia numero do ROTULO
        # do tratamento (T1->1, T2->2...) sempre que analysis_type=="regression",
        # mesmo sem nenhuma coluna de dose informada. Isso permitia que um payload
        # com analysis_type incorreto (ex.: vazado de um post-teste na tela de
        # comparacao de medias) publicasse uma "dose otima" para tratamentos
        # categoricos (T1..T4) que nao sao doses. Sem numeric_factor_column
        # valido, a regressao nao roda.
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

    # [P1-04] Selecao automatica por parcimonia: entre os modelos cujo termo de MAIOR grau e'
    # estatisticamente significativo (p_top_term <= 0,05), escolhe o de maior grau — convencao
    # classica de Pimentel Gomes/Banzatto & Kronka para regressao polinomial (testar do grau
    # mais alto para o mais baixo e ficar com o primeiro cujo termo extra se justifique). So o
    # R² ajustado (maior R² sempre vence, mesmo com termo de grau alto nao-significativo) e'
    # insuficiente como criterio unico: pode empurrar para um polinomio superajustado.
    significant_models = [m for m in models if m.get("p_top_term") is not None and m["p_top_term"] <= 0.05]
    parsimonious = max(significant_models, key=lambda m: m["degree"]) if significant_models else min(models, key=lambda m: m["degree"])

    if requested_degree:
        selected = next((m for m in models if m["degree"] == requested_degree), best)
    else:
        selected = parsimonious

    if requested_degree and selected["degree"] != best["degree"]:
        # O grau escolhido pelo usuário é sempre respeitado; a mensagem apenas sinaliza que
        # outro grau teve R² ajustado maior.
        recommendation = (
            f"Você escolheu o grau {requested_degree} (R² ajustado {selected['adj_r2']:.3f}). "
            f"O grau {best['degree']} teve R² ajustado maior ({best['adj_r2']:.3f}), "
            f"mas o grau solicitado foi mantido."
        )
    elif not requested_degree and parsimonious["degree"] != best["degree"]:
        recommendation = (
            f"Grau {parsimonious['degree']} escolhido por parcimônia: é o maior grau cujo "
            f"termo de mais alta ordem é significativo (p={parsimonious.get('p_top_term'):.4f}). "
            f"O grau {best['degree']} teve R² ajustado maior ({best['adj_r2']:.3f} vs. "
            f"{parsimonious['adj_r2']:.3f}), mas seu termo de maior grau não é significativo — "
            f"sinal de superajuste (overfitting), não de um modelo biologicamente melhor."
        )
    else:
        recommendation = "Modelo escolhido pelo maior grau com termo de maior ordem significativo (parcimônia), que também teve o maior R² ajustado."

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
    # [FIX P0-9] Grafico embutido no PDF no tema escuro do site (fundo #0d1e15,
    # texto claro, verde vivo) em vez do fundo branco original.
    fig, ax = plt.subplots(figsize=(9, 5.2), dpi=160)
    fig.patch.set_facecolor("#0d1e15")
    ax.set_facecolor("#0d1e15")
    ax.errorbar(
        means_df["x"], means_df["y"], yerr=means_df["sd"],
        fmt="o", color="#8FC378", ecolor="#3E7E54", elinewidth=1.4,
        capsize=4, markersize=7, label="Observado (média por dose)",
        markeredgecolor="#F6F9F6", markeredgewidth=0.6,
    )
    ax.plot(x_grid, y_grid, color="#8FC378", linewidth=2.2, label=f"Grau {model['degree']} · R²aj {model['adj_r2']:.3f}")
    optimum = model.get("optimum") or {}
    if optimum.get("x") is not None:
        ax.axvline(optimum["x"], linestyle="--", linewidth=1, color="#D4B14A")
        ax.scatter([optimum["x"]], [optimum["y"]], marker="D", s=60, color="#D4B14A", zorder=5, label="Dose ótima")
    ax.set_xlabel("Dose / fator numérico", color="#a8b8ac", fontsize=10)
    ax.set_ylabel("Resposta", color="#a8b8ac", fontsize=10)
    ax.set_title("Regressão ajustada", color="#F6F9F6", fontsize=13, fontweight="bold")
    ax.tick_params(colors="#a8b8ac")
    for spine in ax.spines.values():
        spine.set_color("#8FC37833")
    ax.grid(True, color="#8FC378", alpha=0.15)
    ax.legend(facecolor="#122820", edgecolor="#8FC37855", labelcolor="#F6F9F6")
    buffer = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buffer, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

def _pairwise_letters(
    levels: List[str], means: Dict[str, float], ns: Dict[str, int],
    mse: float, df_error: float, alpha: float, test_name: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Rotina compartilhada de comparação de médias duas a duas (Tukey-Kramer, Duncan, SNK,
    Scheffé ou Scott-Knott), reaproveitada tanto para médias marginais de fator quanto para
    efeitos simples dentro do desdobramento de interação."""
    k = len(levels)
    comparisons: List[Dict[str, Any]] = []
    nonsig_pairs: set = set()

    if test_name == "scott_knott":
        sk_groups = _scott_knott_groups(levels, means, ns, mse, df_error, alpha)
        position = {g: i for i, g in enumerate(levels)}
        sk_groups.sort(key=lambda grp: min(position[g] for g in grp))
        letters_sk: Dict[str, str] = {}
        for idx, group in enumerate(sk_groups):
            letter = chr(ord("a") + idx)
            for g in group:
                letters_sk[g] = letter
        for i, g1 in enumerate(levels):
            for g2 in levels[i + 1:]:
                same_group = letters_sk[g1] == letters_sk[g2]
                comparisons.append({
                    "group_a": g1, "group_b": g2, "diff": means[g1] - means[g2],
                    "critical_diff": None, "significant": not same_group,
                })
        return comparisons, letters_sk

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
        alpha = _alpha_for_row(ctx.payload, _anova_source(anova, raw_key))
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
    alpha = _alpha_for_row(ctx.payload, _anova_source(anova, inter_key))

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


def _pressupostos_e_transformacao(ctx: AnalysisContext, anova: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Roda assumptions.verificar_pressupostos() sobre os resíduos do modelo já ajustado
    em _anova()/_anova_split_plot() e, se algum pressuposto estiver violado, aplica a
    transformação sugerida (transformations.py) e reajusta o mesmo modelo com a coluna
    transformada — só para mostrar se ela de fato resolveu a violação, sem propagar a
    transformação para médias, comparações ou regressão (isso fica a critério do
    pesquisador, que decide se refaz a análise inteira com os dados transformados)."""
    residuos = anova.get("residuals")
    formula = anova.get("formula")
    if residuos is None or not formula:
        return None, None

    bloco = ctx.payload.get("block_column") if ctx.design == "DBC" else None
    if bloco and bloco not in ctx.df.columns:
        bloco = None

    pressupostos = assumptions.verificar_pressupostos(
        ctx.df,
        np.array(residuos, dtype=float),
        ctx.response,
        ctx.treatment,
        bloco=bloco,
        alpha=float(ctx.payload.get("alpha") or 0.05),
    )

    if pressupostos["veredito"] != assumptions.VIOLADO:
        return pressupostos, None

    metodo = transformations.sugerir_metodo(pressupostos["testes"], ctx.df[ctx.response])
    if metodo is None:
        return pressupostos, None

    try:
        df_transformado = transformations.aplicar(ctx.df, ctx.response, metodo)
        coluna_t = f"{ctx.response}_transformado"
        formula_t = formula.replace(_q(ctx.response), _q(coluna_t), 1)
        modelo_t = smf.ols(formula_t, data=df_transformado).fit()
        residuos_t = modelo_t.resid.to_numpy(float)
        normalidade_t = assumptions.normalidade(residuos_t)
        homoced_t = assumptions.homocedasticidade(df_transformado, coluna_t, ctx.treatment)
        melhorou = normalidade_t["status"] != assumptions.VIOLADO and homoced_t["status"] != assumptions.VIOLADO
        transformacao = {
            "metodo": metodo,
            "descricao": transformations.DESCRICOES.get(metodo, ""),
            "aplicado": True,
            "normalidade_apos": normalidade_t,
            "homocedasticidade_apos": homoced_t,
            "melhorou": melhorou,
            "mensagem": (
                "A transformação resolveu as violações de normalidade e homocedasticidade "
                "detectadas nos resíduos originais."
                if melhorou else
                "A transformação não foi suficiente para resolver todas as violações; "
                "considere um teste não-paramétrico (Kruskal-Wallis) como alternativa."
            ),
        }
    except Exception as exc:
        transformacao = {
            "metodo": metodo,
            "descricao": transformations.DESCRICOES.get(metodo, ""),
            "aplicado": False,
            "mensagem": f"Não foi possível aplicar ou reajustar o modelo com a transformação sugerida: {exc}",
        }

    return pressupostos, transformacao


def analyze(payload: Dict[str, Any]) -> Dict[str, Any]:
    ctx = _prepare_context(payload)
    anova = _anova(ctx)
    means = _means(ctx, anova)
    regression = _regression(ctx) if ctx.analysis_type in {"regression", "single", "factorial"} else None
    factor_comparisons = _factor_comparisons(ctx, anova)
    interaction_breakdown = _interaction_breakdown(ctx, anova)
    recommendations = _recommendations(ctx, anova, means, regression)
    pressupostos, transformacao_sugerida = _pressupostos_e_transformacao(ctx, anova)
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
        "pressupostos": pressupostos,
        "transformacao_sugerida": transformacao_sugerida,
    }
    return _clean_value(result)

def _recommendations(ctx: AnalysisContext, anova: Dict[str, Any], means: Dict[str, Any], regression: Optional[Dict[str, Any]]) -> List[str]:
    messages: List[str] = []
    cv = anova.get("cv")
    if cv is not None:
        messages.append(f"CV experimental: {cv:.2f}% ({_cv_label(cv)}).")

    anova_table = anova.get("table", [])
    significant_sources = [r for r in anova_table if r.get("significance") in {"1%", "5%"}]

    # [FIX P0] Residuo singular NAO e "nao significativo". O F e INDEFINIDO
    # (divisao por zero), nao baixo. Confundir os dois faz o app afirmar ausencia
    # de efeito onde ha separacao perfeita entre tratamentos — o erro mais grave
    # possivel num app de estatistica.
    # Este ramo TEM que vir antes de qualquer leitura de significancia.
    if anova.get("residual_is_singular"):
        messages.append(
            "RESULTADO INDETERMINADO — nao 'nao significativo'. O quadrado medio do "
            "residuo e praticamente zero, entao o teste F (QM_tratamento / QM_residuo) "
            "e uma divisao por zero e nao existe. Isso NAO significa ausencia de efeito: "
            "significa que os dados nao tem variabilidade dentro das celulas do "
            "experimento (dados perfeitamente aditivos, sinteticos, arredondados ou "
            "duplicados). Nenhuma conclusao estatistica pode ser tirada destes dados. "
            "Verifique a coleta e refaca com dados reais de campo."
        )
    elif anova_table:
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
