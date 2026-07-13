def f():
    if True:
        return 1
    return 0
"""
Validacao de pressupostos da ANOVA — Solver Estatistica.

A ANOVA so e valida se seus pressupostos forem atendidos. Rodar o teste F sem
verifica-los e o que separa uma calculadora de uma ferramenta cientifica: qualquer
banca de TCC, revisor de periodico ou pesquisador de P&D vai perguntar por isso.

Pressupostos verificados:
  1. Normalidade dos residuos      -> Shapiro-Wilk (n < 50) / D'Agostino-Pearson
  2. Homocedasticidade (variancias) -> Levene (mediana = Brown-Forsythe) + Bartlett
  3. Aditividade bloco x tratamento -> Teste de Tukey de nao-aditividade (1 GL)
  4. Independencia dos residuos     -> Durbin-Watson
  5. Outliers                        -> residuos studentizados

Nota de projeto: NENHUMA funcao aqui levanta excecao por pressuposto violado. O papel
deste modulo e INFORMAR, nao bloquear. Quem decide se prossegue e o pesquisador — mas
ele decide sabendo.

Regra herdada do incidente de 13/07/2026: um estado indeterminado NUNCA pode ser
apresentado como um resultado. Quando um teste nao pode ser computado (residuo nulo,
n insuficiente, variancia zero), devolvemos status="indeterminado" — jamais um veredito.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats

# Abaixo deste limite (relativo a variancia total), tratamos o residuo como nulo.
# Mesmo criterio ja usado em statistics_engine._anova (FIX 3.2). Manter em sincronia.
_SINGULAR_TOL = 1e-10

# Abaixo deste numero de repeticoes por tratamento, o teste de Levene nao tem poder
# suficiente para que um resultado nao-significativo signifique alguma coisa.
# Medido por simulacao: com n=5 e razao de variancias de 15x, a taxa de deteccao e 4,1%
# — abaixo do proprio alpha. Ver docstring de homocedasticidade().
_N_MIN_PODER = 6

OK = "ok"
VIOLADO = "violado"
ATENCAO = "atencao"
INDETERMINADO = "indeterminado"


def _round(v: Optional[float], nd: int = 4) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, nd)


def _indeterminado(nome: str, motivo: str) -> Dict[str, Any]:
    return {
        "teste": nome,
        "status": INDETERMINADO,
        "statistic": None,
        "p_value": None,
        "mensagem": motivo,
    }


# --------------------------------------------------------------------------- 1. NORMALIDADE

def normalidade(residuos: np.ndarray, alpha: float = 0.05) -> Dict[str, Any]:
    """Shapiro-Wilk para n < 50; D'Agostino-Pearson acima disso.

    H0: os residuos seguem distribuicao normal.
    p > alpha  -> nao rejeitamos H0 -> pressuposto ATENDIDO.
    """
    r = np.asarray(residuos, dtype=float)
    r = r[np.isfinite(r)]
    n = len(r)

    if n < 3:
        return _indeterminado(
            "Shapiro-Wilk",
            "Sao necessarias ao menos 3 observacoes para testar normalidade.",
        )

    # Residuo constante (tipicamente zero): variancia nula. Nao ha distribuicao a testar.
    if np.allclose(r, r[0]):
        return _indeterminado(
            "Shapiro-Wilk",
            "Todos os residuos sao identicos (variancia nula). Nao ha distribuicao a "
            "testar — verifique se os dados sao reais.",
        )

    if n < 50:
        nome = "Shapiro-Wilk"
        stat, p = stats.shapiro(r)
    else:
        nome = "D'Agostino-Pearson"
        stat, p = stats.normaltest(r)

    atende = p > alpha
    return {
        "teste": nome,
        "status": OK if atende else VIOLADO,
        "statistic": _round(stat),
        "p_value": _round(p, 6),
        "n": int(n),
        "mensagem": (
            f"Residuos compativeis com a normalidade (p = {p:.4f} > {alpha}). "
            "Pressuposto atendido."
            if atende else
            f"Residuos nao seguem distribuicao normal (p = {p:.4f} <= {alpha}). "
            "Considere uma transformacao dos dados ou um teste nao-parametrico."
        ),
    }


# ---------------------------------------------------------------- 2. HOMOCEDASTICIDADE

def homocedasticidade(
    df: pd.DataFrame, resposta: str, tratamento: str, alpha: float = 0.05
) -> Dict[str, Any]:
    """Levene com centro na MEDIANA (= Brown-Forsythe) como teste principal.

    Bartlett vai junto so como referencia: ele e muito sensivel a nao-normalidade e
    nao deve ser o criterio de decisao. Reportar os dois e deixar claro qual manda.

    H0: as variancias dos tratamentos sao iguais.

    ------------------------------------------------------------------------------
    ATENCAO — PODER DO TESTE (o guard mais importante desta funcao)
    ------------------------------------------------------------------------------
    O Levene tem poder MUITO baixo com poucas repeticoes. Medido por simulacao
    (1000 corridas, 4 tratamentos, dados binomiais de germinacao):

        repeticoes | razao de variancias | taxa de deteccao
             5     |        15x          |       4,1%   <-- abaixo do proprio alpha!
             5     |        24x          |       8,7%
             8     |        20x          |      60,7%
             8     |        38x          |      82,0%

    Com 5 repeticoes — tamanho tipico de um ensaio de germinacao — uma heterocedasticidade
    REAL e SEVERA (15x) passa despercebida em 96% dos casos.

    Portanto: um p > alpha aqui NAO prova homogeneidade. Prova apenas que o teste nao
    conseguiu ver nada — o que, com n pequeno, era o desfecho mais provavel de qualquer
    forma. Chamar isso de "pressuposto atendido" e apresentar ausencia de evidencia como
    evidencia de ausencia. E o mesmo erro do bug de 13/07/2026, so que com semaforo verde.

    Por isso, com n < 6 por grupo, o status maximo e ATENCAO — nunca OK.
    """
    grupos: List[np.ndarray] = []
    for _, g in df.groupby(tratamento, dropna=False):
        vals = pd.to_numeric(g[resposta], errors="coerce").dropna().to_numpy(float)
        if len(vals) >= 2:
            grupos.append(vals)

    if len(grupos) < 2:
        return _indeterminado(
            "Levene (Brown-Forsythe)",
            "Sao necessarios ao menos 2 tratamentos com 2+ repeticoes cada.",
        )

    # Se todo grupo tem variancia zero, nao ha o que comparar.
    if all(np.allclose(g, g[0]) for g in grupos):
        return _indeterminado(
            "Levene (Brown-Forsythe)",
            "Todos os tratamentos tem variancia zero. Sem variabilidade dentro dos "
            "grupos, a homogeneidade de variancias nao e testavel.",
        )

    stat_l, p_l = stats.levene(*grupos, center="median")

    bartlett: Dict[str, Any] = {"statistic": None, "p_value": None}
    try:
        stat_b, p_b = stats.bartlett(*grupos)
        bartlett = {"statistic": _round(stat_b), "p_value": _round(p_b, 6)}
    except Exception:
        pass

    # Razao entre a maior e a menor variancia: evidencia DESCRITIVA, independente do
    # teste. Quando o teste nao tem poder, e nisto que o usuario deve olhar.
    variancias = [float(np.var(g, ddof=1)) for g in grupos]
    v_min = min(v for v in variancias if v > 0) if any(v > 0 for v in variancias) else 0.0
    razao = (max(variancias) / v_min) if v_min > 0 else None

    n_min = min(len(g) for g in grupos)
    baixo_poder = n_min < _N_MIN_PODER

    rejeita = p_l <= alpha

    if rejeita:
        status = VIOLADO
        msg = (
            f"Variancias heterogeneas entre os tratamentos (p = {p_l:.4f} <= {alpha}). "
            "O teste F fica menos confiavel. Considere transformar os dados."
        )
    elif baixo_poder:
        # NAO dizemos "atendido". O teste simplesmente nao teve poder para ver.
        status = ATENCAO
        msg = (
            f"Heterogeneidade nao detectada (p = {p_l:.4f}), MAS o teste tem baixo poder "
            f"com apenas {n_min} repeticoes por tratamento. Isso NAO prova homogeneidade: "
            f"com {n_min} repeticoes, o Levene deixa passar despercebida uma diferenca de "
            "15x entre variancias em ~96% dos casos. "
            + (f"A razao observada entre a maior e a menor variancia e {razao:.1f}x. "
               if razao is not None else "")
            + "Olhe a natureza do dado: porcentagens e contagens sao heterocedasticas por "
              "construcao, mesmo quando o teste nao acusa."
        )
    else:
        status = OK
        msg = (
            f"Variancias homogeneas entre os tratamentos (p = {p_l:.4f} > {alpha}), com "
            f"{n_min} repeticoes por tratamento — poder adequado. Pressuposto atendido."
        )

    return {
        "teste": "Levene (centro = mediana / Brown-Forsythe)",
        "status": status,
        "statistic": _round(stat_l),
        "p_value": _round(p_l, 6),
        "bartlett": bartlett,
        "k_grupos": len(grupos),
        "n_min": int(n_min),
        "baixo_poder": bool(baixo_poder),
        "razao_variancias": _round(razao, 1),
        "mensagem": msg,
        "nota": (
            "O criterio de decisao e o Levene com centro na mediana (Brown-Forsythe), "
            "robusto a desvios de normalidade. O Bartlett e reportado apenas como "
            "referencia — ele e muito sensivel a nao-normalidade e tende a rejeitar H0 "
            "em excesso."
        ),
    }


# ------------------------------------------------------------------- 3. ADITIVIDADE

def aditividade_tukey(
    df: pd.DataFrame, resposta: str, tratamento: str, bloco: str, alpha: float = 0.05
) -> Dict[str, Any]:
    """Teste de Tukey de nao-aditividade (1 grau de liberdade).

    ESTE E O TESTE MAIS IMPORTANTE DESTE MODULO.

    O modelo do DBC assume que os efeitos de bloco e tratamento sao ADITIVOS:
        y_ij = mu + tau_i + beta_j + e_ij
    Se houver interacao bloco x tratamento, esse termo vai inteiro para o residuo e
    infla o erro experimental — ou, no extremo oposto, uma aditividade PERFEITA zera
    o residuo e torna o teste F indefinido.

    Foi exatamente esse extremo que quebrou o exemplo oficial do produto: os dados
    eram perfeitamente aditivos, o residuo virou zero, o F virou divisao por zero e o
    app afirmou "nao significativo". Este teste pega esse caso automaticamente.

    Procedimento (Tukey, 1949):
      1. Ajusta o modelo aditivo e obtem os residuos e_ij
      2. Constroi z_ij = alpha_i * beta_j  (efeitos estimados de tratamento e bloco)
      3. SQ_naoaditividade = (sum e_ij * z_ij)^2 / (sum alpha_i^2 * sum beta_j^2)
      4. F = QM_naoaditividade / QM_residuo_restante,  com 1 e (gl_res - 1) GL

    H0: os efeitos sao aditivos.
    p > alpha -> aditividade nao rejeitada -> pressuposto ATENDIDO.
    """
    d = df[[resposta, tratamento, bloco]].copy()
    d[resposta] = pd.to_numeric(d[resposta], errors="coerce")
    d = d.dropna()

    t = d[tratamento].nunique()
    b = d[bloco].nunique()

    if t < 2 or b < 2:
        return _indeterminado(
            "Tukey de nao-aditividade",
            "Sao necessarios ao menos 2 tratamentos e 2 blocos.",
        )
    if len(d) != t * b:
        return _indeterminado(
            "Tukey de nao-aditividade",
            "O teste exige o delineamento completo e balanceado "
            "(exatamente uma observacao por combinacao bloco x tratamento).",
        )

    gl_res = (t - 1) * (b - 1)
    if gl_res < 2:
        return _indeterminado(
            "Tukey de nao-aditividade",
            "Graus de liberdade do residuo insuficientes (e preciso gl_res >= 2). "
            "Aumente o numero de blocos ou tratamentos.",
        )

    tab = d.pivot_table(index=bloco, columns=tratamento, values=resposta, aggfunc="mean")
    Y = tab.to_numpy(float)
    if np.isnan(Y).any():
        return _indeterminado(
            "Tukey de nao-aditividade",
            "Ha combinacoes bloco x tratamento sem observacao.",
        )

    mu = Y.mean()
    media_bloco = Y.mean(axis=1)          # por linha  (bloco)
    media_trat = Y.mean(axis=0)           # por coluna (tratamento)
    beta = media_bloco - mu               # efeito de bloco
    tau = media_trat - mu                 # efeito de tratamento

    # Residuos do modelo aditivo
    E = Y - media_bloco[:, None] - media_trat[None, :] + mu
    sq_res = float((E ** 2).sum())

    denom = float((beta ** 2).sum() * (tau ** 2).sum())
    if denom <= 0:
        return _indeterminado(
            "Tukey de nao-aditividade",
            "Efeitos de bloco ou de tratamento sao todos nulos. Nao ha nao-aditividade "
            "a testar.",
        )

    num = float((E * np.outer(beta, tau)).sum()) ** 2
    sq_na = num / denom
    sq_restante = sq_res - sq_na
    gl_restante = gl_res - 1

    var_total = float(np.var(Y))
    # Residuo do modelo aditivo praticamente nulo -> dados perfeitamente aditivos.
    # Este e o caso do exemplo quebrado. Nao e "aditividade confirmada": e um sinal
    # de alerta de que os dados nao sao reais.
    if var_total > 0 and sq_res < _SINGULAR_TOL * var_total * Y.size:
        return {
            "teste": "Tukey de nao-aditividade",
            "status": ATENCAO,
            "statistic": None,
            "p_value": None,
            "sq_nao_aditividade": _round(sq_na),
            "sq_residuo": _round(sq_res),
            "mensagem": (
                "ADITIVIDADE PERFEITA — sinal de alerta, nao de qualidade. O residuo do "
                "modelo aditivo e praticamente zero: cada tratamento difere dos demais "
                "por uma constante exata em TODOS os blocos. Dados reais de campo nunca "
                "se comportam assim. Isso torna o teste F indefinido (divisao por zero). "
                "Verifique se os dados nao sao sinteticos, arredondados ou duplicados."
            ),
        }

    if sq_restante <= 0 or gl_restante < 1:
        return _indeterminado(
            "Tukey de nao-aditividade",
            "Nao restaram graus de liberdade ou soma de quadrados para o residuo apos "
            "extrair o termo de nao-aditividade.",
        )

    qm_na = sq_na / 1.0
    qm_restante = sq_restante / gl_restante
    f_calc = qm_na / qm_restante
    p = float(stats.f.sf(f_calc, 1, gl_restante))

    atende = p > alpha
    return {
        "teste": "Tukey de nao-aditividade",
        "status": OK if atende else VIOLADO,
        "statistic": _round(f_calc),
        "p_value": _round(p, 6),
        "gl": [1, int(gl_restante)],
        "sq_nao_aditividade": _round(sq_na),
        "sq_residuo": _round(sq_res),
        "mensagem": (
            f"Efeitos de bloco e tratamento sao aditivos (p = {p:.4f} > {alpha}). "
            "O modelo do DBC e adequado."
            if atende else
            f"Ha interacao significativa entre bloco e tratamento (p = {p:.4f} <= {alpha}). "
            "O modelo aditivo do DBC nao descreve bem estes dados: o efeito do tratamento "
            "muda conforme o bloco. Considere uma transformacao dos dados ou reveja se o "
            "delineamento em blocos e apropriado."
        ),
    }


# ----------------------------------------------------------------- 4. INDEPENDENCIA

def independencia(residuos: np.ndarray, ordem_valida: bool = False) -> Dict[str, Any]:
    """Durbin-Watson — SO e valido se os residuos estiverem numa ordem com significado.

    ARMADILHA QUE ESTE GUARD EVITA:
    O Durbin-Watson mede correlacao entre residuos CONSECUTIVOS. Ele pressupoe que a
    sequencia significa alguma coisa — ordem de coleta, posicao no croqui, tempo. Numa
    tabela de DBC, a ordem das linhas e arbitraria (so o resultado de como o pivot ficou).
    Rodar DW sobre ela mede a autocorrelacao de uma sequencia que nao existe no mundo real.

    Isso gera FALSO ALARME: no teste do novo dataset de exemplo — dados limpos, todos os
    demais pressupostos atendidos — o DW deu 2,708 e acusou "autocorrelacao negativa".
    Ruido puro, apresentado como diagnostico.

    Essa e a MESMA classe de erro do bug de 13/07/2026: transformar um numero sem
    significado em um veredito. Entao aplicamos a mesma regra: sem ordem real, o teste
    e INDETERMINADO — nunca "ok" e nunca "violado".

    Para habilitar: o usuario precisa informar a ordem de coleta ou a posicao no croqui
    (passe ordem_valida=True depois de ordenar os residuos por essa coluna).
    """
    r = np.asarray(residuos, dtype=float)
    r = r[np.isfinite(r)]

    if not ordem_valida:
        return {
            "teste": "Durbin-Watson",
            "status": INDETERMINADO,
            "statistic": None,
            "p_value": None,
            "mensagem": (
                "Nao testado. O Durbin-Watson exige que os residuos estejam na ordem real "
                "de coleta ou na posicao do croqui de campo — a ordem das linhas da planilha "
                "e arbitraria e testa-la produziria um resultado sem significado. Informe uma "
                "coluna de ordem/posicao para habilitar este diagnostico."
            ),
        }

    if len(r) < 3:
        return _indeterminado("Durbin-Watson", "Sao necessarias ao menos 3 observacoes.")

    denom = float((r ** 2).sum())
    if denom <= 0:
        return _indeterminado(
            "Durbin-Watson",
            "Residuos todos nulos. Nao ha autocorrelacao a medir.",
        )

    dw = float((np.diff(r) ** 2).sum() / denom)

    if 1.5 <= dw <= 2.5:
        status, msg = OK, (
            f"Durbin-Watson = {dw:.3f} (faixa aceitavel: 1,5 a 2,5). Sem indicio de "
            "autocorrelacao entre os residuos."
        )
    elif dw < 1.5:
        status, msg = ATENCAO, (
            f"Durbin-Watson = {dw:.3f} (< 1,5): indicio de autocorrelacao POSITIVA. "
            "Em ensaios de campo isso costuma indicar gradiente espacial (fertilidade, "
            "umidade, declive) que os blocos nao capturaram. Revise o croqui e a "
            "casualizacao."
        )
    else:
        status, msg = ATENCAO, (
            f"Durbin-Watson = {dw:.3f} (> 2,5): indicio de autocorrelacao NEGATIVA "
            "entre parcelas vizinhas (efeito de bordadura / competicao entre parcelas)."
        )

    return {
        "teste": "Durbin-Watson",
        "status": status,
        "statistic": _round(dw, 3),
        "p_value": None,
        "mensagem": msg,
    }


# --------------------------------------------------------------------- 5. OUTLIERS

def outliers(df: pd.DataFrame, residuos: np.ndarray, limite: float = 3.5) -> Dict[str, Any]:
    """Z-score MODIFICADO (Iglewicz-Hoaglin, 1993), baseado na mediana e na MAD.

    POR QUE NAO USAR O Z PADRONIZADO (r / desvio-padrao):
    O desvio-padrao e calculado a partir dos proprios residuos — incluindo o outlier.
    Um valor grosseiro INFLA a regua usada para detecta-lo. Isso se chama mascaramento,
    e em amostras pequenas ele e fatal, porque |z| tem um teto matematico:

        |z|_max = (n - 1) / sqrt(n)

        n =  8  ->  |z|_max = 2,47   <- com limiar 3,0 e IMPOSSIVEL detectar qualquer outlier
        n = 16  ->  |z|_max = 3,75
        n = 30  ->  |z|_max = 5,29

    Ou seja: num ensaio de 4 tratamentos x 2 blocos, o teste do z padronizado com
    limiar 3,0 NUNCA dispara — nem para um erro de digitacao de uma ordem de grandeza.
    Verificado: um 655 digitado no lugar de 65,5 passava batido (z = 2,90).

    A mediana e a MAD sao estimadores robustos: nao sao arrastados pelo outlier, entao
    a regua continua valida. Limiar 3,5 conforme Iglewicz & Hoaglin.
    """
    r = np.asarray(residuos, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 3:
        return _indeterminado(
            "Z-score modificado (MAD)",
            "Sao necessarias ao menos 3 observacoes.",
        )

    mediana = float(np.median(r))
    mad = float(np.median(np.abs(r - mediana)))

    if mad <= 0:
        # MAD zero: mais da metade dos residuos e identica. Cai no estimador classico,
        # mas avisa que a deteccao esta enfraquecida.
        sd = float(np.std(r, ddof=1))
        if sd <= 0:
            return _indeterminado(
                "Z-score modificado (MAD)",
                "Residuos sem dispersao alguma. Nao ha outliers a detectar — "
                "verifique se os dados sao reais.",
            )
        z = (r - mediana) / sd
        metodo = "z padronizado (fallback: MAD = 0)"
        lim = 3.0
    else:
        # 0.6745 = quantil 0.75 da normal padrao; torna a MAD comparavel a um desvio-padrao.
        z = 0.6745 * (r - mediana) / mad
        metodo = "z modificado (mediana / MAD)"
        lim = limite

    idx = np.where(np.abs(z) > lim)[0]
    achados = [
        {"linha": int(i) + 1, "z_modificado": _round(float(z[i]), 2)}
        for i in idx
    ]

    return {
        "teste": "Z-score modificado (MAD)",
        "status": OK if not achados else ATENCAO,
        "statistic": _round(float(np.max(np.abs(z))), 2),
        "p_value": None,
        "metodo": metodo,
        "limiar": lim,
        "outliers": achados,
        "mensagem": (
            f"Nenhum outlier detectado (maior |z| modificado = {np.max(np.abs(z)):.2f}, "
            f"limiar {lim:g})."
            if not achados else
            f"{len(achados)} observacao(oes) suspeita(s) — linha(s) "
            f"{', '.join(str(a['linha']) for a in achados)}. "
            "NAO remova automaticamente: verifique primeiro se houve erro de anotacao, "
            "medicao ou digitacao. Um outlier legitimo e informacao, nao sujeira."
        ),
    }


# ------------------------------------------------------------------------ ORQUESTRADOR

def verificar_pressupostos(
    df: pd.DataFrame,
    residuos: np.ndarray,
    resposta: str,
    tratamento: str,
    bloco: Optional[str] = None,
    alpha: float = 0.05,
    ordem_valida: bool = False,
) -> Dict[str, Any]:
    """Roda a bateria completa e devolve um veredito consolidado.

    `bloco` so e usado no teste de aditividade (aplicavel a DBC). Passe None em DIC.
    `ordem_valida` so deve ser True se os residuos estiverem ordenados por uma coluna
    de ordem de coleta ou posicao no croqui — caso contrario o Durbin-Watson mede ruido.
    """
    testes: Dict[str, Any] = {
        "normalidade": normalidade(residuos, alpha),
        "homocedasticidade": homocedasticidade(df, resposta, tratamento, alpha),
        "independencia": independencia(residuos, ordem_valida=ordem_valida),
        "outliers": outliers(df, residuos),
    }
    if bloco and bloco in df.columns:
        testes["aditividade"] = aditividade_tukey(df, resposta, tratamento, bloco, alpha)

    violados = [k for k, v in testes.items() if v["status"] == VIOLADO]
    atencao = [k for k, v in testes.items() if v["status"] == ATENCAO]
    indef = [k for k, v in testes.items() if v["status"] == INDETERMINADO]

    if violados:
        veredito = VIOLADO
        resumo = (
            f"{len(violados)} pressuposto(s) violado(s): {', '.join(violados)}. "
            "Os resultados da ANOVA devem ser interpretados com cautela — considere "
            "transformar os dados antes de concluir."
        )
    elif atencao:
        veredito = ATENCAO
        resumo = f"Pontos de atencao em: {', '.join(atencao)}. Revise antes de publicar."
    elif indef and len(indef) == len(testes):
        veredito = INDETERMINADO
        resumo = (
            "Nenhum pressuposto pode ser testado com estes dados. Isso costuma indicar "
            "ausencia de variabilidade — verifique se os dados sao reais."
        )
    else:
        veredito = OK
        resumo = "Todos os pressupostos testaveis foram atendidos. A ANOVA e valida."

    return {
        "veredito": veredito,
        "resumo": resumo,
        "alpha": alpha,
        "testes": testes,
        "sugestao_transformacao": _sugerir_transformacao(testes),
    }


def _sugerir_transformacao(testes: Dict[str, Any]) -> Optional[str]:
    """Recomenda uma transformacao com base em QUAL pressuposto quebrou."""
    norm_ruim = testes.get("normalidade", {}).get("status") == VIOLADO
    var_ruim = testes.get("homocedasticidade", {}).get("status") == VIOLADO
    adit_ruim = testes.get("aditividade", {}).get("status") == VIOLADO

    if not (norm_ruim or var_ruim or adit_ruim):
        return None
    if var_ruim and norm_ruim:
        return (
            "Normalidade e homocedasticidade violadas. A transformacao Box-Cox (com lambda "
            "estimado dos proprios dados) e a escolha mais geral: ela busca simultaneamente "
            "estabilizar a variancia e aproximar a normalidade."
        )
    if var_ruim:
        return (
            "Variancia heterogenea. Se a variancia cresce com a media: log(x+1) para dados "
            "de crescimento/producao, raiz(x+0,5) para contagens (numero de insetos, plantas, "
            "vagens), arcsen(raiz(x/100)) para porcentagens (germinacao, severidade, controle)."
        )
    if norm_ruim:
        return (
            "Residuos nao-normais com variancia homogenea. Com delineamento balanceado, a "
            "ANOVA e razoavelmente robusta a esse desvio. Ainda assim, considere log(x+1) "
            "ou um teste nao-parametrico (Kruskal-Wallis) para confirmar as conclusoes."
        )
    return (
        "Interacao bloco x tratamento detectada. Uma transformacao logaritmica frequentemente "
        "restaura a aditividade quando os efeitos sao multiplicativos em vez de aditivos."
    )
