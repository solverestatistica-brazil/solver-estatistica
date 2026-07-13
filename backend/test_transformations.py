"""
Testes do modulo transformations.py — Solver Estatistica.

Como rodar (dentro de backend/):
    pip install pytest
    pytest -v test_transformations.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import transformations as tr


def test_log_x1_valores_validos():
    out = tr.log_x1(np.array([0.0, 1.0, np.e - 1]))
    assert out[0] == pytest.approx(0.0)
    assert out[1] == pytest.approx(np.log(2))
    assert out[2] == pytest.approx(1.0)


def test_log_x1_rejeita_menor_que_menos_um():
    with pytest.raises(ValueError):
        tr.log_x1(np.array([-2.0, 1.0]))


def test_raiz_x05_valores_validos():
    out = tr.raiz_x05(np.array([0.0, 3.5]))
    assert out[0] == pytest.approx(np.sqrt(0.5))
    assert out[1] == pytest.approx(2.0)


def test_raiz_x05_rejeita_menor_que_menos_meio():
    with pytest.raises(ValueError):
        tr.raiz_x05(np.array([-1.0]))


def test_arcsin_percentual_valores_validos():
    out = tr.arcsin_raiz_percentual(np.array([0.0, 100.0]))
    assert out[0] == pytest.approx(0.0)
    assert out[1] == pytest.approx(np.pi / 2)


def test_arcsin_percentual_rejeita_fora_de_0_100():
    with pytest.raises(ValueError):
        tr.arcsin_raiz_percentual(np.array([-1.0, 50.0]))
    with pytest.raises(ValueError):
        tr.arcsin_raiz_percentual(np.array([50.0, 101.0]))


def test_box_cox_desloca_series_com_zero_ou_negativo():
    transformado, lam = tr.box_cox(np.array([-1.0, 0.0, 1.0, 2.0, 3.0]))
    assert len(transformado) == 5
    assert np.all(np.isfinite(transformado))
    assert isinstance(lam, float)


def test_aplicar_adiciona_coluna_sem_alterar_original():
    df = pd.DataFrame({"Valor": [1.0, 2.0, 3.0], "Trat": ["A", "B", "C"]})
    out = tr.aplicar(df, "Valor", tr.LOG_X1)
    assert "Valor_transformado" in out.columns
    assert "Valor_transformado" not in df.columns
    assert list(out["Valor"]) == [1.0, 2.0, 3.0]


def test_aplicar_metodo_desconhecido_leva_erro():
    df = pd.DataFrame({"Valor": [1.0, 2.0]})
    with pytest.raises(ValueError):
        tr.aplicar(df, "Valor", "metodo_inexistente")


def test_sugerir_metodo_nenhuma_violacao_retorna_none():
    testes = {
        "normalidade": {"status": "ok"},
        "homocedasticidade": {"status": "ok"},
    }
    assert tr.sugerir_metodo(testes) is None


def test_sugerir_metodo_normalidade_e_variancia_violadas_sugere_box_cox():
    testes = {
        "normalidade": {"status": "violado"},
        "homocedasticidade": {"status": "violado"},
    }
    assert tr.sugerir_metodo(testes) == tr.BOX_COX


def test_sugerir_metodo_so_normalidade_sugere_log():
    testes = {
        "normalidade": {"status": "violado"},
        "homocedasticidade": {"status": "ok"},
    }
    assert tr.sugerir_metodo(testes) == tr.LOG_X1


def test_sugerir_metodo_so_variancia_usa_natureza_do_dado():
    testes = {"normalidade": {"status": "ok"}, "homocedasticidade": {"status": "violado"}}
    # Percentuais reais (razao x/n * 100) raramente caem em numero inteiro -> sinal usado
    # para distingui-los de contagens, que sao inteiras por natureza.
    percentuais = pd.Series([16.67, 58.33, 91.67])
    contagens = pd.Series([1.0, 4.0, 12.0, 30.0])
    continuos = pd.Series([120.5, 340.2, 980.7])
    assert tr.sugerir_metodo(testes, percentuais) == tr.ARCSIN_PCT
    assert tr.sugerir_metodo(testes, contagens) == tr.RAIZ_X05
    assert tr.sugerir_metodo(testes, continuos) == tr.LOG_X1
