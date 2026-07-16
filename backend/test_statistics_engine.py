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
    assert "cultura" in _cv_label(5.0).lower()
    assert "\u00d3timo" not in _cv_label(5.0)


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


def test_comparacao_de_medias_preserva_analysis_type():
    """Pedir Tukey num DBC nao pode virar uma regressao."""
    res = _dbc(DBC_EXEMPLO, comparison_test="tukey")
    assert res["meta"]["analysis_type"] == "single"
    assert len(res["anova"]["table"]) > 0, "quadro de ANOVA veio vazio"
    assert res["means"]["comparison"] is not None, "Tukey nao foi calculado"


def test_bug_2_regressao_sem_numeric_factor_column_nao_roda():
    """[FIX P0-6] Sem numeric_factor_column, a regressao nao pode inventar um eixo
    a partir do ROTULO do tratamento (T1->1, T2->2...). T1..T4 nao sao doses.
    Reproduz o payload vazado do post-teste em producao: analysis_type="regression"
    sem numeric_factor_column, sobre tratamentos categoricos."""
    res = _dbc(DBC_EXEMPLO, analysis_type="regression", numeric_factor_column=None)
    assert res["regression"] is None, "Regressao nao deveria rodar sem coluna numerica declarada"


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


# =========================================================================
# Auditoria de 15/07/2026: Dunnett exato, Scott-Knott, alpha_mode, regressao
# por parcimonia.
# =========================================================================


def test_dunnett_exato_menos_conservador_que_bonferroni_antigo():
    """[AUDITORIA P0-01] A versao anterior usava t + Bonferroni (conservador demais). O
    Dunnett exato (distribuicao t multivariada) deve ter diferenca critica MENOR — mais
    poder — para o mesmo dataset e alfa. Valor antigo documentado nesta auditoria: 10.768442."""
    res = _dbc(DBC_EXEMPLO, comparison_test="dunnett", control_group="T1")
    comp = res["means"]["comparison"]
    assert comp["test"] == "DUNNETT"
    crit_diffs = [c["critical_diff"] for c in comp["comparisons"]]
    assert all(c < 10.768442 for c in crit_diffs), "Dunnett exato deveria ser menos conservador que o Bonferroni antigo"
    assert all(c["p_value"] is not None for c in comp["comparisons"]), "Dunnett exato deve expor p-valor ajustado"


def test_dunnett_e_reproduzivel_entre_chamadas():
    """A integracao numerica da t multivariada usa Monte Carlo quase-aleatorio; sem uma
    semente fixa, duas chamadas identicas poderiam devolver p-valores levemente diferentes
    — inaceitavel para uma ferramenta que preve ser usada como laudo."""
    res1 = _dbc(DBC_EXEMPLO, comparison_test="dunnett", control_group="T1")
    res2 = _dbc(DBC_EXEMPLO, comparison_test="dunnett", control_group="T1")
    p1 = [c["p_value"] for c in res1["means"]["comparison"]["comparisons"]]
    p2 = [c["p_value"] for c in res2["means"]["comparison"]["comparisons"]]
    assert p1 == p2


def test_dunnett_sem_testemunha_informada_avisa_no_texto():
    """[AUDITORIA] Sem control_group, o app nao pode fingir que sabe qual e' a testemunha.
    A nota precisa alertar explicitamente que a escolha foi automatica."""
    res = _dbc(DBC_EXEMPLO, comparison_test="dunnett")
    nota = res["means"]["comparison"]["note"]
    assert "não informada" in nota or "nao informada" in nota.lower()


def test_dunnett_nao_usa_letras_compactas():
    """[AUDITORIA P1-02] Dunnett so testa tratamento vs. testemunha, nunca tratamento vs.
    tratamento. Um compact letter display (CLD) sugeriria relacoes nunca testadas (ex.: dois
    tratamentos com letras diferentes por acaso de ordenacao). A coluna 'Grupo' agora usa
    marcadores nao-transitivos: 'testemunha' para o controle, 'sig'/'ns' para os demais."""
    res = _dbc(DBC_EXEMPLO, comparison_test="dunnett", control_group="T1")
    comp = res["means"]["comparison"]
    assert comp["control"] == "T1"
    assert comp["letters"]["T1"] == "testemunha"
    for t in ("T2", "T3", "T4"):
        assert comp["letters"][t] in {"sig", "ns"}


def test_scott_knott_agrupa_sem_sobreposicao_de_letras():
    """Scott-Knott nunca da mais de uma letra por tratamento (ao contrario do CLD de Tukey),
    porque particiona em grupos disjuntos."""
    res = _dbc(DBC_EXEMPLO, comparison_test="scott_knott")
    comp = res["means"]["comparison"]
    assert comp["test"] == "SCOTT_KNOTT"
    for letters in comp["letters"].values():
        assert len(letters) == 1, f"Scott-Knott nao deveria atribuir mais de uma letra: {letters!r}"
    # T3 tem media bem destacada dos demais (72.8 vs ~58-60) -> deve ficar isolado no grupo 'a'
    assert comp["letters"]["T3"] == "a"
    assert len({comp["letters"][t] for t in ("T1", "T2", "T4")}) == 1


def test_scott_knott_formula_canonica_caso_da_auditoria():
    """[AUDITORIA P0-01, 15/07/2026 pos-commit 0df4f3d] A formula anterior usava B0 (SQ so do
    melhor split) tambem no denominador de sigma0^2, e qui-quadrado com df=k em vez de
    k/(pi-2). No caso reproduzivel da auditoria (T1=0,8510003; T2=1,9416329; T3=5,6462449;
    MSE=0,4982669; 16 GL; r=4), isso fazia o Solver devolver {T1,T2},{T3} em vez do resultado
    canonico {T1},{T2},{T3} (conferido contra a formula do artigo original, Scott & Knott
    1974). Este e' O TESTE MAIS IMPORTANTE do Scott-Knott: garante que a formula usa a
    dispersao TOTAL das medias do subconjunto (nao so do melhor split) no denominador."""
    from statistics_engine import _scott_knott_groups
    means = {"T1": 0.8510003, "T2": 1.9416329, "T3": 5.6462449}
    ns = {"T1": 4, "T2": 4, "T3": 4}
    groups = _scott_knott_groups(["T1", "T2", "T3"], means, ns, mse=0.4982669, df_error=16, alpha=0.05)
    assert groups == [["T1"], ["T2"], ["T3"]], (
        f"esperado 3 grupos singleton (formula canonica), obtido: {groups}"
    )


def test_alpha_mode_fixed_ignora_significancia_do_f():
    """[AUDITORIA P0-02] Com alpha_mode='fixed', o pos-teste deve usar o alfa informado
    (nao o bucket 1%/5% do teste F), mesmo quando o F for significativo a 1%."""
    res_default = _dbc(DBC_EXEMPLO, comparison_test="tukey")
    assert res_default["means"]["comparison"]["alpha"] == 0.01

    res_auto = _dbc(DBC_EXEMPLO, comparison_test="tukey", alpha_mode="auto")
    assert res_auto["means"]["comparison"]["alpha"] == 0.01  # F significativo a 1% -> auto usa 1%

    res_fixed = _dbc(DBC_EXEMPLO, comparison_test="tukey", alpha_mode="fixed", alpha=0.05)
    assert res_fixed["means"]["comparison"]["alpha"] == 0.05


def test_factorial_aceita_tipos_i_ii_iii_de_soma_de_quadrados():
    base = {
        "design": "DBC", "analysis_type": "factorial", "goal": "max",
        "response_column": "Valor", "treatment_column": "A", "block_column": "Bloco",
        "factor_columns": ["A", "B"], "data": FACTORIAL,
    }
    for ss_type in (1, 2, 3):
        result = analyze({**base, "sum_squares_type": ss_type})
        assert result["anova"]["sum_squares_type"] == ss_type
        assert result["meta"]["sum_squares_type"] == ss_type
        assert any(row["source"] == "A" for row in result["anova"]["table"])
        assert any(row["source"] == "A × B" for row in result["anova"]["table"])


def test_tipo_de_soma_de_quadrados_invalido_e_rejeitado():
    with pytest.raises(ValueError, match="soma de quadrados"):
        analyze({
            "design": "DBC", "analysis_type": "factorial",
            "response_column": "Valor", "block_column": "Bloco",
            "factor_columns": ["A", "B"], "sum_squares_type": 4,
            "data": FACTORIAL,
        })


def test_regressao_replicada_expoe_teste_formal_de_falta_de_ajuste():
    result = analyze({
        "design": "DIC", "analysis_type": "regression", "goal": "max",
        "response_column": "Valor", "numeric_factor_column": "Tratamento",
        "alpha": 0.05, "data": DBC_SINGLE,
    })
    for model in result["regression"]["models"]:
        lack = model["lack_of_fit"]
        assert lack["available"] is True
        assert lack["df_pure_error"] > 0
        assert lack["df_lack_of_fit"] >= 0
        assert "significant" in lack


def test_falta_de_ajuste_respeita_alfa_definido_a_priori():
    import numpy as np
    from statistics_engine import _lack_of_fit_test

    x = np.array([0, 0, 1, 1, 2, 2, 3, 3], dtype=float)
    y = np.array([0.0, 0.2, 1.0, 1.2, 4.0, 4.2, 9.0, 9.2], dtype=float)
    coefficients = np.polyfit(x, y, 1)
    residual_ss = float(np.sum((y - np.polyval(coefficients, x)) ** 2))
    probe = _lack_of_fit_test(x, y, 1, residual_ss, alpha=0.05)
    assert probe["available"] is True
    p_value = probe["p_value"]
    strict = _lack_of_fit_test(x, y, 1, residual_ss, alpha=p_value / 2)
    permissive = _lack_of_fit_test(x, y, 1, residual_ss, alpha=min(0.99, p_value * 2))
    assert strict["significant"] is False
    assert permissive["significant"] is True


def test_scott_knott_rejeita_repeticoes_desbalanceadas():
    unbalanced = [
        {"tratamento": treatment, "valor": value}
        for treatment, values in {
            "T1": [10.0, 10.5, 11.0, 10.7],
            "T2": [14.0, 14.5, 15.0, 14.7],
            "T3": [18.0, 18.5, 19.0],
        }.items()
        for value in values
    ]
    with pytest.raises(ValueError, match="balanceado"):
        analyze({
            "design": "DIC", "analysis_type": "single", "goal": "max",
            "response_column": "valor", "treatment_column": "tratamento",
            "comparison_test": "scott_knott", "data": unbalanced,
        })


def test_resultado_inclui_proveniencia_reprodutivel():
    result = _dbc(DBC_EXEMPLO, comparison_test="tukey")
    provenance = result["provenance"]
    assert provenance["engine_version"]
    assert provenance["git_commit"]
    assert len(provenance["data_sha256"]) == 64
    assert len(provenance["config_sha256"]) == 64


def test_regressao_prefere_parcimonia_a_r2_ajustado_cego():
    """[AUDITORIA P1-04] Quando o grau com maior R² ajustado tem termo de maior ordem
    NAO significativo, a selecao automatica deve preferir o grau mais simples (parcimonia),
    nao o maior R² ajustado isolado."""
    random.seed(1)
    data = []
    for dose in (0, 50, 100, 150, 200):
        for _ in range(4):
            data.append({"dose": dose, "valor": round(40 + 0.15 * dose + random.gauss(0, 1.5), 3)})
    res = analyze({
        "design": "DIC", "analysis_type": "regression", "goal": "max",
        "response_column": "valor", "numeric_factor_column": "dose", "data": data,
    })
    reg = res["regression"]
    grau2 = next(m for m in reg["models"] if m["degree"] == 2)
    assert grau2["p_top_term"] > 0.05, "premissa do teste: o termo quadratico nao deveria ser significativo"
    assert reg["recommended_degree"] == 2, "premissa do teste: R2 ajustado bruto favoreceria o grau 2"
    assert reg["selected_degree"] == 1, "selecao automatica deveria preferir o grau parcimonioso (1), nao o maior R2 ajustado"
