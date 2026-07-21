from __future__ import annotations

import io

import pytest
from openpyxl import load_workbook
from pypdf import PdfReader

from exporters import build_excel, build_pdf
from test_statistics_engine import DBC_EXEMPLO


PAYLOAD = {
    "design": "DBC", "analysis_type": "single", "goal": "max",
    "response_column": "valor", "treatment_column": "tratamento",
    "block_column": "bloco", "comparison_test": "tukey",
    "alpha": 0.05, "alpha_mode": "fixed", "data": DBC_EXEMPLO,
}


def test_pdf_contem_resultados_e_proveniencia():
    pdf = build_pdf(PAYLOAD)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 10_000
    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) >= 2, "o relatório deve ter capa e ao menos uma página de resultados"
    first_page = reader.pages[0]
    width = float(first_page.mediabox.width)
    height = float(first_page.mediabox.height)
    assert height > width
    assert width == pytest.approx(595.28, abs=1.0)
    assert height == pytest.approx(841.89, abs=1.0)

    cover_text = first_page.extract_text() or ""
    assert "RELATÓRIO ESTATÍSTICO" in cover_text
    assert "Relatório gerado pelo Solver Estatística" in cover_text
    assert "Fernando Paes Lorena" not in cover_text
    assert "Página" not in cover_text

    body_text = "\n".join(page.extract_text() or "" for page in reader.pages[1:])
    assert "Página 1" in body_text
    assert "Gerado em Brasília" in body_text
    assert "BRT" in body_text
    assert "Gerado em UTC" not in body_text
    assert reader.metadata.title == "Relatório Solver Estatística"
    text = cover_text + "\n" + body_text
    for expected in (
        "ANOVA", "Comparações detalhadas", "Pressupostos", "Configuração e rastreabilidade",
            "SHA-256 dos dados", "Soma de quadrados",
    ):
        assert expected.upper() in text.upper()


def test_pdf_usa_nome_do_autor_informado():
    payload = {**PAYLOAD, "author_name": "Maria Souza"}
    pdf = build_pdf(payload)
    reader = PdfReader(io.BytesIO(pdf))
    cover_text = reader.pages[0].extract_text() or ""
    assert "Maria Souza" in cover_text
    assert reader.metadata.author == "Maria Souza"
    assert "Relatório gerado pelo Solver Estatística" not in cover_text


def test_pdf_sem_nome_nao_vaza_nome_pessoal_padrao():
    pdf = build_pdf(PAYLOAD)
    reader = PdfReader(io.BytesIO(pdf))
    cover_text = reader.pages[0].extract_text() or ""
    assert "Fernando Paes Lorena" not in cover_text
    assert reader.metadata.author == "Relatório gerado pelo Solver Estatística"


def test_excel_contem_planilhas_tecnicas_e_dados_de_entrada():
    excel = build_excel(PAYLOAD)
    workbook = load_workbook(io.BytesIO(excel), data_only=False)
    expected = {
        "Resumo", "Metadados", "Configuracao", "Dados_Entrada", "ANOVA", "Medias",
        "Comparacoes", "Pressupostos", "Pressupostos_Detalhes", "Transformacao", "Regressao",
    }
    assert expected.issubset(workbook.sheetnames)
    assert workbook.active.title == "Resumo"
    assert workbook["Dados_Entrada"].max_row == len(DBC_EXEMPLO) + 1
    metadata = {
        workbook["Metadados"].cell(row=row, column=1).value:
        workbook["Metadados"].cell(row=row, column=2).value
        for row in range(2, workbook["Metadados"].max_row + 1)
    }
    assert len(metadata["SHA-256 dos dados"]) == 64
    assert metadata["Versão do motor"]
    assert "Gerado em Brasília" in metadata
    assert "BRT" in metadata["Gerado em Brasília"]
    assert "Gerado em UTC" not in metadata
    assert workbook["ANOVA"].auto_filter.ref
    assert workbook["Resumo"].sheet_view.showGridLines is False
