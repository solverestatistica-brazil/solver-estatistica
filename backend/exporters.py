"""Exportadores de resultados do Solver em PDF, Excel, PNG e PDF vetorial."""

from __future__ import annotations

import base64
import io
from typing import Any, Dict, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from statistics_engine import analyze


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def build_pdf(payload: Dict[str, Any]) -> bytes:
    """Gera relatório técnico em PDF a partir do payload de análise."""
    result = analyze(payload)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=1.3 * cm,
        leftMargin=1.3 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
        title="Relatório Solver Estatística",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("SolverTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=18, textColor=colors.HexColor("#24492E"))
    h2 = ParagraphStyle("SolverH2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12, textColor=colors.HexColor("#3E7E54"))
    body = ParagraphStyle("SolverBody", parent=styles["BodyText"], fontSize=9, leading=12)

    story: List[Any] = []
    story.append(Paragraph("SOLVER · Relatório estatístico", title))
    story.append(Paragraph(f"Delineamento: {result['meta']['design']} · Tipo: {result['meta']['analysis_type']} · Linhas: {result['meta']['n_rows']}", body))
    story.append(Spacer(1, 0.25 * cm))

    story.append(Paragraph("Resumo executivo", h2))
    for msg in result.get("recommendations", []):
        story.append(Paragraph("• " + msg, body))
    story.append(Spacer(1, 0.25 * cm))

    anova_rows = [["FV", "GL", "SQ", "QM", "F calc", "F 5%", "F 1%", "p", "Sig"]]
    for r in result.get("anova", {}).get("table", []):
        anova_rows.append([
            r.get("source"), _fmt(r.get("df")), _fmt(r.get("sum_sq")), _fmt(r.get("mean_sq")),
            _fmt(r.get("f_calc")), _fmt(r.get("f_5")), _fmt(r.get("f_1")), _fmt(r.get("p_value")), r.get("significance"),
        ])
    story.append(Paragraph("Quadro de ANOVA", h2))
    story.append(_styled_table(anova_rows))
    story.append(Spacer(1, 0.25 * cm))

    means_rows = [["Tratamento", "Média", "n", "DP", "Grupo"]]
    for r in result.get("means", {}).get("treatment_means", []):
        means_rows.append([r.get("treatment"), _fmt(r.get("mean")), _fmt(r.get("n")), _fmt(r.get("sd")), r.get("group", "")])
    if len(means_rows) > 1:
        story.append(Paragraph("Médias por tratamento", h2))
        story.append(_styled_table(means_rows))
        story.append(Spacer(1, 0.25 * cm))

    reg = result.get("regression")
    if reg:
        selected = reg.get("selected_model", {})
        story.append(Paragraph("Regressão", h2))
        story.append(Paragraph(f"{selected.get('equation')} · R² ajustado: {_fmt(selected.get('adj_r2'))}", body))

    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("Observação: resultados de MVP devem ser validados antes de uso como laudo técnico oficial.", body))
    doc.build(story)
    return buffer.getvalue()


def _styled_table(rows: List[List[Any]]) -> Table:
    table = Table(rows, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#24492E")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D7DEDA")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#F6F9F6"), colors.white]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def build_excel(payload: Dict[str, Any]) -> bytes:
    """Gera planilha Excel com abas de ANOVA, médias e recomendações."""
    result = analyze(payload)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(result.get("anova", {}).get("table", [])).to_excel(writer, index=False, sheet_name="ANOVA")
        pd.DataFrame(result.get("means", {}).get("treatment_means", [])).to_excel(writer, index=False, sheet_name="Medias")
        pd.DataFrame({"recomendacao": result.get("recommendations", [])}).to_excel(writer, index=False, sheet_name="Resumo")
        if result.get("regression"):
            pd.DataFrame(result["regression"].get("models", [])).drop(columns=["coefficients"], errors="ignore").to_excel(writer, index=False, sheet_name="Regressao")
    return buffer.getvalue()


def build_regression_plot(payload: Dict[str, Any], fmt: str = "png") -> bytes:
    """Exporta gráfico de regressão em PNG ou PDF vetorial."""
    result = analyze(payload)
    reg = result.get("regression")
    if not reg:
        raise ValueError("Não há regressão disponível para exportar.")
    points = pd.DataFrame(reg["points"])
    curve = pd.DataFrame(reg["fitted_curve"])
    selected = reg["selected_model"]
    fig, ax = plt.subplots(figsize=(9, 5.2), dpi=200)
    ax.scatter(points["x"], points["y"], label="Observado")
    ax.plot(curve["x"], curve["y"], label=f"Grau {reg['selected_degree']} · R²aj {selected['adj_r2']:.3f}")
    opt = selected.get("optimum") or {}
    if opt.get("x") is not None:
        ax.axvline(opt["x"], linestyle="--", linewidth=1)
        ax.scatter([opt["x"]], [opt["y"]], marker="o", s=55, label="Ótimo")
    ax.set_xlabel(reg.get("x_label", "x"))
    ax.set_ylabel(reg.get("y_label", "Resposta"))
    ax.set_title("Regressão Solver")
    ax.grid(True, alpha=0.25)
    ax.legend()
    output = io.BytesIO()
    fig.tight_layout()
    fig.savefig(output, format=fmt)
    plt.close(fig)
    return output.getvalue()
