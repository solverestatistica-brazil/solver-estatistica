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

import csv
import random
from pathlib import Path

import pytest

from statistics_engine import _cv_label, analyze

EXAMPLE_CSV_PATH = Path(__file__).resolve().parents[1] / "examples" / "dbc_exemplo.csv"


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


# Dataset perfeitamente aditivo (T2 = T1+3,2, T3 = T1+8,6, T4 = T1+6,5 em TODOS os
# blocos) — o mesmo caso que gerava SQ residuo = 0 / F indefinido em producao.
DBC_ADITIVO = [
    {"bloco": "B1", "tratamento": "T1", "valor": 58.2},
    {"bloco": "B1", "tratamento": "T2", "valor": 61.4},
    {"bloco": "B1", "tratamento": "T3", "valor": 66.8},
    {"bloco": "B1", "tratamento": "T4", "valor": 64.7},
    {"bloco": "B2", "tratamento": "T1", "valor": 57.6},
    {"bloco": "B2", "tratamento": "T2", "valor": 60.8},
    {"bloco": "B2", "tratamento": "T3", "valor": 66.2},
    {"bloco": "B2", "tratamento": "T4", "valor": 64.1},
    {"bloco": "B3", "tratamento": "T1", "valor": 58.6},
    {"bloco": "B3", "tratamento": "T2", "valor": 61.8},
    {"bloco": "B3", "tratamento": "T3", "valor": 67.2},
    {"bloco": "B3", "tratamento": "T4", "valor": 65.1},
    {"bloco": "B4", "tratamento": "T1", "valor": 59.1},
    {"bloco": "B4", "tratamento": "T2", "valor": 62.3},
    {"bloco": "B4", "tratamento": "T3", "valor": 67.7},
    {"bloco": "B4", "tratamento": "T4", "valor": 65.6},
]

# Dataset realista (produtividade de cultivares de soja, sc/ha) que substitui o exemplo
# oficial do produto — o exemplo anterior era o proprio DBC_ADITIVO acima.
DBC_EXEMPLO = [
    {"bloco": "B1", "tratamento": "T1", "valor": 52.4},
    {"bloco": "B1", "tratamento": "T2", "valor": 54.6},
    {"bloco": "B1", "tratamento": "T3", "valor": 60.9},
    {"bloco": "B1", "tratamento": "T4", "valor": 58.0},
    {"bloco": "B2", "tratamento": "T1", "valor": 56.6},
    {"bloco": "B2", "tratamento": "T2", "valor": 57.3},
    {"bloco": "B2", "tratamento": "T3", "valor": 72.0},
    {"bloco": "B2", "tratamento": "T4", "valor": 54.5},
    {"bloco": "B3", "tratamento": "T1", "valor": 59.6},
    {"bloco": "B3", "tratamento": "T2", "valor": 59.0},
    {"bloco": "B3", "tratamento": "T3", "valor": 80.9},
    {"bloco": "B3", "tratamento": "T4", "valor": 59.7},
    {"bloco": "B4", "tratamento": "T1", "valor": 61.6},
    {"bloco": "B4", "tratamento": "T2", "valor": 59.6},
    {"bloco": "B4", "tratamento": "T3", "valor": 77.5},
    {"bloco": "B4", "tratamento": "T4", "valor": 67.6},
]


def _dbc(data, **extra):
    payload = {
        "design": "DBC", "analysis_type": "single", "goal": "max",
        "response_column": "valor", "treatment_column": "tratamento",
        "block_column": "bloco", "data": data,
    }
    payload.update(extra)
    return analyze(payload)


def _row(res, source):
    return next(r for r in res["anova"]["table"] if r["source"] == source)


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


def test_integracao_pressupostos_exposto_no_analyze():
    """assumptions.py deve estar plugado em analyze(): toda análise DBC/single com
    resíduos disponíveis precisa devolver a chave 'pressupostos' com um veredito."""
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
    assert result["anova"]["residuals"] is not None
    pressupostos = result["pressupostos"]
    assert pressupostos is not None
    assert pressupostos["veredito"] in {"ok", "atencao", "violado", "indeterminado"}
    assert set(pressupostos["testes"]) >= {"normalidade", "homocedasticidade", "independencia", "outliers", "aditividade"}
    # Dataset é perfeitamente aditivo por construção -> aditividade cai em ATENCAO,
    # não gera sugestão de transformação (só VIOLADO dispara transformacao_sugerida).
    assert "transformacao_sugerida" in result


def test_integracao_transformacao_sugerida_quando_pressuposto_violado():
    """Quando homocedasticidade/normalidade são violadas, transformations.py deve ser
    acionado a partir de statistics_engine e devolver um método aplicado com sucesso."""
    random.seed(1)
    means_sds = {"A": (10, 0.2), "B": (10, 15), "C": (10, 0.3)}
    data = []
    for t, (m, sd) in means_sds.items():
        for b in range(1, 9):
            data.append({"Trat": t, "Bloco": b, "Valor": round(max(0.01, random.gauss(m, sd)), 3)})

    result = analyze({
        "design": "DBC",
        "analysis_type": "single",
        "response_column": "Valor",
        "treatment_column": "Trat",
        "block_column": "Bloco",
        "comparison_test": "tukey",
        "goal": "max",
        "alpha": 0.05,
        "data": data,
    })
    assert result["pressupostos"]["veredito"] == "violado"
    transformacao = result["transformacao_sugerida"]
    assert transformacao is not None
    assert transformacao["metodo"] in {"log_x1", "raiz_x05", "arcsin_percentual", "box_cox"}
    assert transformacao["aplicado"] is True
    assert "normalidade_apos" in transformacao and "homocedasticidade_apos" in transformacao


def test_residuo_singular_nunca_diz_nao_significativo():
    """O TESTE MAIS IMPORTANTE DO REPOSITORIO.

    Com residuo nulo o F e indefinido, nao baixo. Dizer 'nao significativo' aqui
    e afirmar ausencia de efeito sem nenhuma base. Este era o estado de producao
    em 13/07/2026.
    """
    res = _dbc(DBC_ADITIVO)
    txt = " ".join(res["recommendations"]).lower()
    assert "indetermin" in txt, "precisa dizer INDETERMINADO"
    assert "nenhuma fonte de variação foi significativa" not in txt, (
        "REGRESSAO: o app voltou a afirmar ausencia de efeito para um F indefinido"
    )


def test_dbc_categorico_nao_gera_regressao_de_dose():
    """T1..T4 sao rotulos, nao doses. 'Ponto otimo em x=3,44' e sem sentido."""
    res = _dbc(DBC_EXEMPLO)
    txt = " ".join(res["recommendations"]).lower()
    assert "ponto ótimo" not in txt and "ponto otimo" not in txt, (
        "regressao de dose oferecida sobre fator categorico"
    )
    assert res.get("regression") in (None, {}, []), (
        "regressao nao deveria existir sem fator numerico"
    )


def test_split_plot_residuo_singular_neutraliza_f_e_expoe_flag():
    """[FIX P0-3] SPLIT_PLOT e aditivo por construcao (Erro(a) e Erro(b) ~ 0). Antes
    do fix, o codigo calculava F como divisao por MSE~0 e publicava valores
    astronomicos (ex.: F=2.14e27, p=0.0) como resultado real, e a chave
    'residual_is_singular' nem existia no retorno. Agora tem que se comportar como
    o caminho 'single': flag True e F/p neutralizados (None) nas fontes reais."""
    result = analyze({
        "design": "DBC", "analysis_type": "split_plot", "response_column": "Valor",
        "treatment_column": "A", "block_column": "Bloco", "factor_columns": ["A", "B"],
        "numeric_factor_column": "A", "comparison_test": "tukey", "goal": "max", "alpha": 0.05,
        "data": SPLIT_PLOT,
    })
    anova = result["anova"]
    assert anova.get("residual_is_singular") is True
    for row in anova["table"]:
        src = str(row.get("source") or "")
        if src not in ("Erro (a) — Bloco × Parcela", "Erro (b) — Resíduo", "Total"):
            assert row.get("f_calc") is None, f"F nao foi neutralizado em {src}"
            assert row.get("p_value") is None, f"p nao foi neutralizado em {src}"


def test_exemplo_csv_oficial_reproduz_a_tabela_de_aceite():
    """[FIX P0-4] examples/dbc_exemplo.csv e o dataset que 'Carregar exemplo' usa no
    site. Precisa ser o dataset real (cultivares de soja, sc/ha) e reproduzir a
    tabela de aceite documentada -- nao pode mais ser o dataset aditivo que zerava
    o residuo (F indefinido) para todo visitante novo."""
    with EXAMPLE_CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    data = [{"bloco": r["bloco"], "tratamento": r["tratamento"], "valor": float(r["valor"])} for r in rows]
    res = _dbc(data)
    trat = _row(res, "Tratamentos")
    assert not res["anova"]["residual_is_singular"]
    assert trat["f_calc"] == pytest.approx(14.412, rel=1e-3)
    assert trat["significance"] == "1%"
    assert res["anova"]["cv"] == pytest.approx(6.21, abs=0.05)


def test_exemplo_oficial_demonstra_o_produto_funcionando():
    res = _dbc(DBC_EXEMPLO)
    trat = _row(res, "Tratamentos")
    assert trat["f_calc"] == pytest.approx(14.412, rel=1e-3)
    assert trat["significance"] == "1%"
    assert res["anova"]["cv"] == pytest.approx(6.21, abs=0.05)
    assert not res["anova"]["residual_is_singular"]


def test_exemplo_oficial_libera_pos_teste():
    """Se o pos-teste nao abre, o exemplo nao demonstra nada."""
    res = _dbc(DBC_EXEMPLO, comparison_test="tukey")
    assert res["means"]["comparison"] is not None, "Tukey deveria estar liberado"


def test_valores_criticos_de_f_nao_estao_invertidos():
    """F(3,9): 3,8625 a 5% e 6,9919 a 1%. O 1% e SEMPRE maior que o 5%."""
    trat = _row(_dbc(DBC_EXEMPLO), "Tratamentos")
    assert trat["f_5"] == pytest.approx(3.8625, abs=1e-3)
    assert trat["f_1"] == pytest.approx(6.9919, abs=1e-3)
    assert trat["f_1"] > trat["f_5"]


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
