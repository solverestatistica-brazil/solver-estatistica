"""Exportadores de resultados do Solver em PDF, Excel, PNG e PDF vetorial."""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Dict, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle

from statistics_engine import analyze

# Paleta identica a assets/css/styles.css (identidade visual Solver).
BRAND_DARK = colors.HexColor("#081C13")
BRAND_DEEP = colors.HexColor("#24492E")
BRAND = colors.HexColor("#3E7E54")
BRAND_BRIGHT = colors.HexColor("#8FC378")
TEXT_L1 = colors.HexColor("#14211A")
TEXT_L2 = colors.HexColor("#5C6D64")
SURFACE_LINE = colors.HexColor("#E7ECE9")
SURFACE_SUBTLE = colors.HexColor("#F4F7F5")
SUCCESS = colors.HexColor("#4C8E50")
SUCCESS_TINT = colors.HexColor("#E3ECE0")
WARNING = colors.HexColor("#B8863C")
WARNING_TINT = colors.HexColor("#F2E7D2")
NEUTRAL = colors.HexColor("#94A3B8")
NEUTRAL_TINT = colors.HexColor("#EEF2F0")

HEX = {
    "brand_deep": "24492E",
    "brand": "3E7E54",
    "surface_line": "E7ECE9",
    "surface_subtle": "F4F7F5",
    "success": "4C8E50",
    "success_tint": "E3ECE0",
    "warning": "B8863C",
    "warning_tint": "F2E7D2",
    "neutral": "94A3B8",
    "neutral_tint": "EEF2F0",
    "text_l1": "14211A",
    "text_l2": "5C6D64",
}


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}".replace(".", ",")
    return str(value)


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}%".replace(".", ",")


def _draw_header_footer(canvas_obj, doc) -> None:
    """Desenha a faixa de marca no topo e o rodape em toda pagina do PDF."""
    canvas_obj.saveState()
    width, height = landscape(A4)

    # Faixa de topo com a marca Solver.
    canvas_obj.setFillColor(BRAND_DARK)
    canvas_obj.rect(0, height - 2.2 * cm, width, 2.2 * cm, fill=1, stroke=0)

    logo_x, logo_y = 1.3 * cm, height - 1.75 * cm
    canvas_obj.setStrokeColor(BRAND)
    canvas_obj.setLineWidth(1.3)
    canvas_obj.roundRect(logo_x, logo_y, 1.05 * cm, 1.05 * cm, 4, fill=0, stroke=1)
    canvas_obj.setStrokeColor(BRAND_BRIGHT)
    canvas_obj.setLineWidth(1.6)
    canvas_obj.setLineCap(1)
    canvas_obj.setLineJoin(1)
    path = canvas_obj.beginPath()
    path.moveTo(logo_x + 0.2 * cm, logo_y + 0.32 * cm)
    path.lineTo(logo_x + 0.42 * cm, logo_y + 0.62 * cm)
    path.lineTo(logo_x + 0.58 * cm, logo_y + 0.46 * cm)
    path.lineTo(logo_x + 0.85 * cm, logo_y + 0.78 * cm)
    canvas_obj.drawPath(path, stroke=1, fill=0)

    canvas_obj.setFillColor(colors.white)
    canvas_obj.setFont("Helvetica-Bold", 15)
    canvas_obj.drawString(logo_x + 1.35 * cm, height - 1.2 * cm, "SOLVER")
    canvas_obj.setFont("Helvetica", 6.8)
    canvas_obj.setFillColor(BRAND_BRIGHT)
    canvas_obj.drawString(logo_x + 1.35 * cm, height - 1.62 * cm, "INTELLIGENCE FOR FIELD TRIALS")

    canvas_obj.setFont("Helvetica-Bold", 12.5)
    canvas_obj.setFillColor(colors.white)
    canvas_obj.drawRightString(width - 1.3 * cm, height - 1.2 * cm, "Relatório estatístico")
    canvas_obj.setFont("Helvetica", 7.5)
    canvas_obj.setFillColor(BRAND_BRIGHT)
    canvas_obj.drawRightString(
        width - 1.3 * cm,
        height - 1.62 * cm,
        datetime.now().strftime("Gerado em %d/%m/%Y às %H:%M"),
    )

    # Rodape.
    canvas_obj.setStrokeColor(SURFACE_LINE)
    canvas_obj.setLineWidth(0.6)
    canvas_obj.line(1.3 * cm, 1.15 * cm, width - 1.3 * cm, 1.15 * cm)
    canvas_obj.setFont("Helvetica", 7.5)
    canvas_obj.setFillColor(TEXT_L2)
    canvas_obj.drawString(
        1.3 * cm,
        0.75 * cm,
        "Solver Estatística Experimental · resultados de MVP devem ser validados antes de uso como laudo técnico oficial.",
    )
    canvas_obj.setFillColor(TEXT_L2)
    canvas_obj.drawRightString(width - 1.3 * cm, 0.75 * cm, f"Página {doc.page}")
    canvas_obj.restoreState()


def _kpi_cards(result: Dict[str, Any]) -> Table:
    cv = result.get("anova", {}).get("cv")
    cv_label = result.get("anova", {}).get("cv_label", "Indisponível")
    n_rows = result.get("meta", {}).get("n_rows")
    best = (result.get("means") or {}).get("best")
    best_label = best.get("treatment") if best else "—"
    best_mean = f"Média {_fmt(best.get('mean'))}" if best else "—"

    label_style = ParagraphStyle("KpiLabel", fontName="Helvetica-Bold", fontSize=7.5, textColor=TEXT_L2, leading=9)
    value_style = ParagraphStyle("KpiValue", fontName="Helvetica-Bold", fontSize=18, textColor=TEXT_L1, leading=21, spaceBefore=3)
    sub_style = ParagraphStyle("KpiSub", fontName="Helvetica-Bold", fontSize=8, textColor=SUCCESS, spaceBefore=2)

    def cell(label: str, value: str, sub: str) -> List[Any]:
        return [
            Paragraph(label.upper(), label_style),
            Paragraph(value, value_style),
            Paragraph(sub, sub_style),
        ]

    data = [[
        cell("CV experimental", _fmt_pct(cv) if cv is not None else "—", cv_label),
        "",
        cell("Linhas analisadas", str(n_rows if n_rows is not None else "—"), "Observações"),
        "",
        cell("Melhor tratamento", str(best_label), best_mean),
    ]]
    card_w = 8.7 * cm
    gap_w = 0.5 * cm
    table = Table(data, colWidths=[card_w, gap_w, card_w, gap_w, card_w])
    table.setStyle(TableStyle([
        ("BOX", (0, 0), (0, 0), 0.8, SURFACE_LINE),
        ("BOX", (2, 0), (2, 0), 0.8, SURFACE_LINE),
        ("BOX", (4, 0), (4, 0), 0.8, SURFACE_LINE),
        ("BACKGROUND", (0, 0), (0, 0), colors.white),
        ("BACKGROUND", (2, 0), (2, 0), colors.white),
        ("BACKGROUND", (4, 0), (4, 0), colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 11),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
        ("LEFTPADDING", (0, 0), (0, 0), 13),
        ("LEFTPADDING", (2, 0), (2, 0), 13),
        ("LEFTPADDING", (4, 0), (4, 0), 13),
        ("RIGHTPADDING", (0, 0), (-1, -1), 13),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def _sig_colors(value: Optional[str]):
    if value == "1%":
        return SUCCESS_TINT, SUCCESS
    if value == "5%":
        return WARNING_TINT, WARNING
    if value in (None, "—", "-", "ns"):
        return NEUTRAL_TINT, NEUTRAL
    return None, None


def _styled_table(rows: List[List[Any]], sig_col: Optional[int] = None) -> Table:
    table = Table(rows, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_DEEP),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, SURFACE_LINE),
        ("LINEBELOW", (0, 0), (-1, 0), 1.4, BRAND),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [SURFACE_SUBTLE, colors.white]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 1), (0, -1), TEXT_L1),
    ]
    if sig_col is not None:
        for row_idx in range(1, len(rows)):
            bg, fg = _sig_colors(rows[row_idx][sig_col])
            if bg is None:
                continue
            style.append(("BACKGROUND", (sig_col, row_idx), (sig_col, row_idx), bg))
            style.append(("TEXTCOLOR", (sig_col, row_idx), (sig_col, row_idx), fg))
            style.append(("FONTNAME", (sig_col, row_idx), (sig_col, row_idx), "Helvetica-Bold"))
            style.append(("ALIGN", (sig_col, row_idx), (sig_col, row_idx), "CENTER"))
    table.setStyle(TableStyle(style))
    return table


def build_pdf(payload: Dict[str, Any]) -> bytes:
    """Gera relatorio tecnico em PDF, com identidade visual Solver, a partir do payload de analise."""
    result = analyze(payload)
    buffer = io.BytesIO()
    page_size = landscape(A4)
    doc = BaseDocTemplate(
        buffer,
        pagesize=page_size,
        leftMargin=1.3 * cm,
        rightMargin=1.3 * cm,
        topMargin=2.6 * cm,
        bottomMargin=1.55 * cm,
        title="Relatório Solver Estatística",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="solver-frame")
    doc.addPageTemplates([PageTemplate(id="solver", frames=[frame], onPage=_draw_header_footer)])

    styles = getSampleStyleSheet()
    meta_style = ParagraphStyle("SolverMeta", parent=styles["BodyText"], fontSize=9.5, textColor=TEXT_L2, spaceAfter=4)
    h2 = ParagraphStyle("SolverH2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12.5, textColor=BRAND_DEEP, spaceBefore=4, spaceAfter=7)
    body = ParagraphStyle("SolverBody", parent=styles["BodyText"], fontSize=9.5, leading=14, textColor=TEXT_L1)
    bullet = ParagraphStyle("SolverBullet", parent=body, leftIndent=10, spaceAfter=2)

    meta = result.get("meta", {})
    story: List[Any] = [
        Paragraph(
            f"Delineamento <b>{meta.get('design')}</b> · Tipo <b>{meta.get('analysis_type')}</b> · "
            f"{meta.get('n_rows')} linhas analisadas",
            meta_style,
        ),
        Spacer(1, 0.3 * cm),
        _kpi_cards(result),
        Spacer(1, 0.45 * cm),
        Paragraph("Resumo executivo", h2),
    ]
    for msg in result.get("recommendations", []):
        story.append(Paragraph("• " + msg, bullet))
    story.append(Spacer(1, 0.3 * cm))

    anova_rows = [["FV", "GL", "SQ", "QM", "F calc", "F 5%", "F 1%", "p", "Sig"]]
    for r in result.get("anova", {}).get("table", []):
        anova_rows.append([
            r.get("source"), _fmt(r.get("df")), _fmt(r.get("sum_sq")), _fmt(r.get("mean_sq")),
            _fmt(r.get("f_calc")), _fmt(r.get("f_5")), _fmt(r.get("f_1")), _fmt(r.get("p_value")), r.get("significance"),
        ])
    story.append(KeepTogether([
        Paragraph("Quadro de ANOVA · Teste F", h2),
        _styled_table(anova_rows, sig_col=8),
    ]))
    story.append(Spacer(1, 0.3 * cm))

    means_rows = [["Tratamento", "Média", "n", "DP", "Grupo"]]
    for r in result.get("means", {}).get("treatment_means", []):
        means_rows.append([r.get("treatment"), _fmt(r.get("mean")), _fmt(r.get("n")), _fmt(r.get("sd")), r.get("group", "")])
    if len(means_rows) > 1:
        story.append(KeepTogether([
            Paragraph("Médias por tratamento", h2),
            _styled_table(means_rows),
        ]))
        story.append(Spacer(1, 0.3 * cm))

    reg = result.get("regression")
    if reg:
        selected = reg.get("selected_model", {})
        story.append(KeepTogether([
            Paragraph("Regressão", h2),
            Paragraph(
                f"{selected.get('equation')} &nbsp;·&nbsp; R² ajustado: <b>{_fmt(selected.get('adj_r2'))}</b>",
                body,
            ),
        ]))

    doc.build(story)
    return buffer.getvalue()


def _style_excel_sheet(worksheet, n_cols: int) -> None:
    """Aplica cabecalho com a cor da marca, zebra e largura automatica as planilhas exportadas."""
    header_fill = PatternFill(start_color=HEX["brand_deep"], end_color=HEX["brand_deep"], fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=10)
    body_font = Font(color=HEX["text_l1"], size=10)
    zebra_fill = PatternFill(start_color=HEX["surface_subtle"], end_color=HEX["surface_subtle"], fill_type="solid")
    thin = Side(style="thin", color=HEX["surface_line"])
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for col in range(1, n_cols + 1):
        cell = worksheet.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="left", vertical="center")
        cell.border = border

    for row in range(2, worksheet.max_row + 1):
        for col in range(1, n_cols + 1):
            cell = worksheet.cell(row=row, column=col)
            cell.font = body_font
            cell.border = border
            if row % 2 == 0:
                cell.fill = zebra_fill

    for col in range(1, n_cols + 1):
        letter = get_column_letter(col)
        max_len = max((len(str(worksheet.cell(row=r, column=col).value or "")) for r in range(1, worksheet.max_row + 1)), default=10)
        worksheet.column_dimensions[letter].width = min(max(max_len + 4, 12), 40)

    worksheet.freeze_panes = "A2"
    worksheet.row_dimensions[1].height = 20


def build_excel(payload: Dict[str, Any]) -> bytes:
    """Gera planilha Excel com abas de ANOVA, medias e recomendacoes, com a identidade visual Solver."""
    result = analyze(payload)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        anova_df = pd.DataFrame(result.get("anova", {}).get("table", []))
        anova_df.to_excel(writer, index=False, sheet_name="ANOVA")
        _style_excel_sheet(writer.sheets["ANOVA"], len(anova_df.columns) if not anova_df.empty else 1)

        means_df = pd.DataFrame(result.get("means", {}).get("treatment_means", []))
        means_df.to_excel(writer, index=False, sheet_name="Medias")
        _style_excel_sheet(writer.sheets["Medias"], len(means_df.columns) if not means_df.empty else 1)

        resumo_df = pd.DataFrame({"recomendacao": result.get("recommendations", [])})
        resumo_df.to_excel(writer, index=False, sheet_name="Resumo")
        _style_excel_sheet(writer.sheets["Resumo"], 1)

        if result.get("regression"):
            reg_df = pd.DataFrame(result["regression"].get("models", [])).drop(columns=["coefficients"], errors="ignore")
            reg_df.to_excel(writer, index=False, sheet_name="Regressao")
            _style_excel_sheet(writer.sheets["Regressao"], len(reg_df.columns) if not reg_df.empty else 1)
    return buffer.getvalue()


def build_regression_plot(payload: Dict[str, Any], fmt: str = "png") -> bytes:
    """Exporta grafico de regressao em PNG ou PDF vetorial."""
    result = analyze(payload)
    reg = result.get("regression")
    if not reg:
        raise ValueError("Não há regressão disponível para exportar.")
    points = pd.DataFrame(reg["points"])
    curve = pd.DataFrame(reg["fitted_curve"])
    selected = reg["selected_model"]
    fig, ax = plt.subplots(figsize=(9, 5.2), dpi=200)
    ax.scatter(points["x"], points["y"], label="Observado", color="#3E7E54")
    ax.plot(curve["x"], curve["y"], label=f"Grau {reg['selected_degree']} · R²aj {selected['adj_r2']:.3f}", color="#24492E")
    opt = selected.get("optimum") or {}
    if opt.get("x") is not None:
        ax.axvline(opt["x"], linestyle="--", linewidth=1, color="#C2703D")
        ax.scatter([opt["x"]], [opt["y"]], marker="o", s=55, label="Ótimo", color="#C2703D")
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
