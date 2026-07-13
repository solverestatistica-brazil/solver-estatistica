"""
Transformacoes de dados para estabilizar variancia e aproximar normalidade — Solver
Estatistica.

Companion do assumptions.py: quando verificar_pressupostos() aponta um pressuposto
violado, este modulo aplica de fato a transformacao sugerida (nao so descreve em texto),
para que o pesquisador veja o diagnostico antes/depois na mesma tela.

Transformacoes disponiveis:
  log_x1                  -> log(x + 1), dados de crescimento/producao
  raiz_x05                -> sqrt(x + 0,5), contagens (insetos, plantas, vagens)
  arcsin_raiz_percentual  -> arcsen(sqrt(x/100)), porcentagens (germinacao, severidade)
  box_cox                 -> Box-Cox com lambda estimado dos proprios dados

Nota de projeto: sugerir_metodo() traduz o diagnostico de verificar_pressupostos()
(assumptions.py) numa chave executavel, com a MESMA logica descrita em
assumptions._sugerir_transformacao — a diferenca e que ali o resultado e um paragrafo
para o usuario ler, aqui e uma chave que o statistics_engine pode aplicar direto.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

LOG_X1 = "log_x1"
RAIZ_X05 = "raiz_x05"
ARCSIN_PCT = "arcsin_percentual"
BOX_COX = "box_cox"

DESCRICOES: Dict[str, str] = {
    LOG_X1: "log(x + 1) — indicada para dados de crescimento/producao com variancia crescente.",
    RAIZ_X05: "raiz(x + 0,5) — indicada para contagens (insetos, plantas, vagens por parcela).",
    ARCSIN_PCT: "arcsen(raiz(x/100)) — indicada para porcentagens (germinacao, severidade, controle).",
    BOX_COX: (
        "Box-Cox com lambda estimado dos dados — indicada quando normalidade e "
        "homocedasticidade estao violadas simultaneamente."
    ),
}


def log_x1(x: np.ndarray) -> np.ndarray:
    """log(x + 1). Exige x >= -1 (aceita zero)."""
    arr = np.asarray(x, dtype=float)
    if np.any(arr < -1):
        raise ValueError("log(x+1) exige valores >= -1; ha valor(es) negativo(s) demais na serie.")
    return np.log1p(arr)


def raiz_x05(x: np.ndarray) -> np.ndarray:
    """sqrt(x + 0,5). Exige x >= -0,5."""
    arr = np.asarray(x, dtype=float)
    if np.any(arr < -0.5):
        raise ValueError("raiz(x+0,5) exige valores >= -0,5; ha valor(es) negativo(s) demais na serie.")
    return np.sqrt(arr + 0.5)


def arcsin_raiz_percentual(x: np.ndarray) -> np.ndarray:
    """arcsen(sqrt(x/100)), em radianos. Exige 0 <= x <= 100 (porcentagem)."""
    arr = np.asarray(x, dtype=float)
    if np.any((arr < 0) | (arr > 100)):
        raise ValueError(
            "arcsen(raiz(x/100)) exige valores entre 0 e 100 (porcentagem); a serie tem "
            "valor(es) fora desse intervalo."
        )
    return np.arcsin(np.sqrt(arr / 100.0))


def box_cox(x: np.ndarray) -> Tuple[np.ndarray, float]:
    """Box-Cox com lambda estimado por maxima verossimilhanca.

    Exige x > 0. Series com zero ou negativos sao deslocadas automaticamente (constante
    minima para tornar o menor valor positivo) antes de estimar lambda.
    """
    arr = np.asarray(x, dtype=float)
    if np.any(arr <= 0):
        arr = arr + (abs(float(arr.min())) + 1.0)
    transformado, lam = stats.boxcox(arr)
    return transformado, float(lam)


METODOS = {
    LOG_X1: log_x1,
    RAIZ_X05: raiz_x05,
    ARCSIN_PCT: arcsin_raiz_percentual,
}


def aplicar(df: pd.DataFrame, resposta: str, metodo: str) -> pd.DataFrame:
    """Devolve uma COPIA de df com a coluna '{resposta}_transformado' adicionada.

    Nao modifica df original nem substitui a coluna de resposta original.
    """
    valores = pd.to_numeric(df[resposta], errors="coerce").to_numpy(float)
    out = df.copy()
    if metodo == BOX_COX:
        transformado, _lam = box_cox(valores)
    elif metodo in METODOS:
        transformado = METODOS[metodo](valores)
    else:
        raise ValueError(f"Metodo de transformacao desconhecido: {metodo!r}.")
    out[f"{resposta}_transformado"] = transformado
    return out


def sugerir_metodo(testes: Dict[str, Any], serie_resposta: Optional[pd.Series] = None) -> Optional[str]:
    """Traduz o diagnostico de verificar_pressupostos() (assumptions.py) num metodo
    executavel. Mesma logica de assumptions._sugerir_transformacao, com uma decisao a
    mais: quando so a variancia esta violada, a natureza do dado (serie_resposta) escolhe
    entre percentual, contagem ou crescimento — texto livre nao precisa decidir isso,
    mas uma chave executavel precisa.
    """
    norm_ruim = testes.get("normalidade", {}).get("status") == "violado"
    var_ruim = testes.get("homocedasticidade", {}).get("status") == "violado"
    adit_ruim = testes.get("aditividade", {}).get("status") == "violado"

    if not (norm_ruim or var_ruim or adit_ruim):
        return None
    if var_ruim and norm_ruim:
        return BOX_COX
    if var_ruim:
        return _sugerir_por_natureza(serie_resposta)
    # norm_ruim isolado ou adit_ruim isolado: log(x+1) e a recomendacao textual em
    # ambos os casos de assumptions._sugerir_transformacao.
    return LOG_X1


def _sugerir_por_natureza(serie: Optional[pd.Series]) -> str:
    """Contagem e percentual sao ambiguos quando ambos caem em 0-100 (ex.: 12 insetos vs.
    12% de severidade) — nao ha como distinguir com certeza so pelo valor numerico. O sinal
    mais forte disponivel e a presenca de casas decimais: um percentual calculado como
    razao (x/n)*100 raramente cai num numero inteiro; uma contagem e inteira por natureza.
    """
    if serie is None:
        return LOG_X1
    vals = pd.to_numeric(serie, errors="coerce").dropna()
    if vals.empty:
        return LOG_X1
    dentro_de_100 = bool(vals.min() >= 0 and vals.max() <= 100)
    tem_decimais = not np.allclose(vals, np.round(vals))
    if dentro_de_100 and tem_decimais:
        return ARCSIN_PCT
    if (vals >= 0).all() and not tem_decimais:
        return RAIZ_X05
    if dentro_de_100:
        return ARCSIN_PCT
    return LOG_X1
