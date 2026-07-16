from __future__ import annotations

import io

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
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    for expected in (
        "ANOVA", "Comparações detalhadas", "Pressupostos", "Configuração e rastreabilidade",
            "SHA-256 dos dados", "Soma de quadrados",
    ):
        assert expected in text


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
    assert workbook["ANOVA"].auto_filter.ref
    assert workbook["Resumo"].sheet_view.showGridLines is False
