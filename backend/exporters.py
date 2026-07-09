"""Exportadores de resultados do Solver em PDF, Excel, PNG e PDF vetorial."""

from __future__ import annotations

import base64
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
from reportlab.platypus import BaseDocTemplate, Frame, Image, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle

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

DESIGN_LABELS = {
    "DIC": "Inteiramente Casualizado (DIC)",
    "DBC": "Blocos Casualizados (DBC)",
    "DQL": "Quadrado Latino (DQL)",
}
TYPE_LABELS = {
    "single": "fator único",
    "factorial": "fatorial",
    "split_plot": "parcelas subdivididas",
    "regression": "regressão direta",
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

    canvas_obj.setFillColor(BRAND_DARK)
    canvas_obj.rect(0, height - 2.2 * cm, width, 2.2 * cm, fill=1, stroke=0)

    # Replica exatamente o SVG do site (viewBox 0-40, rect rx=10, polyline de
    # tendencia + polyline em L formando a seta na ponta) em vez de um rabisco
    # a mao livre sem seta - o usuario notou que o logo do PDF ficava diferente
    # e mais feio que o do site.
    logo_x, logo_y = 1.3 * cm, height - 1.75 * cm
    logo_size = 1.05 * cm
    view = 40.0
    scale = logo_size / view

    def _sp(x: float, y: float) -> Tuple[float, float]:
        return logo_x + x * scale, logo_y + logo_size - y * scale

    canvas_obj.setStrokeColor(BRAND)
    canvas_obj.setLineWidth(1.6 * scale)
    canvas_obj.roundRect(logo_x, logo_y, logo_size, logo_size, 10 * scale, fill=0, stroke=1)

    canvas_obj.setStrokeColor(BRAND_BRIGHT)
    canvas_obj.setLineWidth(2.2 * scale)
    canvas_obj.setLineCap(1)
    canvas_obj.setLineJoin(1)

    trend = canvas_obj.beginPath()
    trend_points = [(10, 25), (16, 18), (20, 21), (28, 12)]
    tx0, ty0 = _sp(*trend_points[0])
    trend.moveTo(tx0, ty0)
    for px, py in trend_points[1:]:
        cx, cy = _sp(px, py)
        trend.lineTo(cx, cy)
    canvas_obj.drawPath(trend, stroke=1, fill=0)

    arrowhead = canvas_obj.beginPath()
    arrow_points = [(23, 12), (28, 12), (28, 17)]
    ax0, ay0 = _sp(*arrow_points[0])
    arrowhead.moveTo(ax0, ay0)
    for px, py in arrow_points[1:]:
        cx, cy = _sp(px, py)
        arrowhead.lineTo(cx, cy)
    canvas_obj.drawPath(arrowhead, stroke=1, fill=0)

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


def _kpi_card(label: str, value: str, sub: str) -> Table:
    label_style = ParagraphStyle("KpiLabel", fontName="Helvetica-Bold", fontSize=7.5, textColor=TEXT_L2, leading=9)
    value_style = ParagraphStyle("KpiValue", fontName="Helvetica-Bold", fontSize=18, textColor=TEXT_L1, leading=21, spaceBefore=3)
    sub_style = ParagraphStyle("KpiSub", fontName="Helvetica-Bold", fontSize=8, textColor=SUCCESS, spaceBefore=2)
    card = Table(
        [[Paragraph(label.upper(), label_style)], [Paragraph(value, value_style)], [Paragraph(sub, sub_style)]],
        colWidths=[8.7 * cm],
    )
    card.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, SURFACE_LINE),
        ("ROUNDEDCORNERS", [8, 8, 8, 8]),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 11),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
        ("LEFTPADDING", (0, 0), (-1, -1), 13),
        ("RIGHTPADDING", (0, 0), (-1, -1), 13),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return card


def _kpi_cards(result: Dict[str, Any]) -> Table:
    cv = result.get("anova", {}).get("cv")
    cv_label = result.get("anova", {}).get("cv_label", "Indisponível")
    n_rows = result.get("meta", {}).get("n_rows")
    best = (result.get("means") or {}).get("best")
    best_label = best.get("treatment") if best else "—"
    best_mean = f"Média {_fmt(best.get('mean'))}" if best else "—"

    card1 = _kpi_card("CV experimental", _fmt_pct(cv) if cv is not None else "—", cv_label)
    card2 = _kpi_card("Linhas analisadas", str(n_rows if n_rows is not None else "—"), "Observações")
    card3 = _kpi_card("Melhor tratamento", str(best_label), best_mean)

    card_w = 8.7 * cm
    gap_w = 0.5 * cm
    layout = Table([[card1, "", card2, "", card3]], colWidths=[card_w, gap_w, card_w, gap_w, card_w])
    layout.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return layout


def _sig_colors(value: Optional[str]):
    if value == "1%":
        return SUCCESS_TINT, SUCCESS
    if value == "5%":
        return WARNING_TINT, WARNING
    if value in (None, "—", "-", "ns"):
        return NEUTRAL_TINT, NEUTRAL
    return None, None


def _styled_table(rows: List[List[Any]], sig_col: Optional[int] = None) -> Table:
    """Tabela no estilo do dashboard: sem grade vertical, so linhas horizontais
    finas + zebra, moldura externa arredondada - evita a cara de planilha crua."""
    table = Table(rows, repeatRows=1)
    n_rows = len(rows)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_DEEP),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [SURFACE_SUBTLE, colors.white]),
        ("LINEBELOW", (0, 0), (-1, n_rows - 2), 0.5, SURFACE_LINE),
        ("LINEBELOW", (0, 0), (-1, 0), 1.6, BRAND),
        ("BOX", (0, 0), (-1, -1), 0.8, SURFACE_LINE),
        ("ROUNDEDCORNERS", [8, 8, 8, 8]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 1), (0, -1), TEXT_L1),
    ]
    if sig_col is not None:
        for row_idx in range(1, n_rows):
            bg, fg = _sig_colors(rows[row_idx][sig_col])
            if bg is None:
                continue
            style.append(("BACKGROUND", (sig_col, row_idx), (sig_col, row_idx), bg))
            style.append(("TEXTCOLOR", (sig_col, row_idx), (sig_col, row_idx), fg))
            style.append(("FONTNAME", (sig_col, row_idx), (sig_col, row_idx), "Helvetica-Bold"))
            style.append(("ALIGN", (sig_col, row_idx), (sig_col, row_idx), "CENTER"))
    table.setStyle(TableStyle(style))
    return table


def _intro_text(result: Dict[str, Any]) -> str:
    meta = result.get("meta", {})
    design = meta.get("design")
    analysis_type = meta.get("analysis_type")
    design_label = DESIGN_LABELS.get(design, design or "—")
    type_label = TYPE_LABELS.get(analysis_type, analysis_type or "—")

    if analysis_type == "regression":
        return (
            f"Este relatório apresenta o ajuste de regressão sobre um fator numérico contínuo "
            f"(dose ou concentração), a partir de {meta.get('n_rows')} observações. O objetivo é "
            f"estimar a curva de resposta e o ponto ótimo, e não comparar médias de tratamentos."
        )
    return (
        f"Este relatório apresenta os resultados da análise estatística de um experimento em "
        f"delineamento {design_label}, com estrutura de {type_label}, totalizando {meta.get('n_rows')} "
        f"observações. A análise de variância (ANOVA) avalia, pelo teste F, se há diferença "
        f"estatisticamente significativa entre as fontes de variação testadas, aos níveis de "
        f"5% e 1% de probabilidade."
    )


def _anova_caption(result: Dict[str, Any]) -> str:
    return (
        "Fontes de variação marcadas como <b>1%</b> ou <b>5%</b> apresentam efeito estatisticamente "
        "significativo sobre a variável resposta nesses níveis de probabilidade; <b>ns</b> "
        "(não significativo) indica que não houve evidência estatística de efeito."
    )


def _means_caption(result: Dict[str, Any]) -> Optional[str]:
    comparison = (result.get("means") or {}).get("comparison")
    if not comparison:
        return None
    test_name = comparison.get("test", "TUKEY")
    alpha = comparison.get("alpha", 0.05)
    alpha_pct = f"{alpha * 100:.0f}%".replace(".", ",")
    return (
        f"Tratamentos seguidos pela mesma letra na coluna <b>Grupo</b> não diferem estatisticamente "
        f"entre si pelo teste de <b>{test_name.title()}</b>, ao nível de {alpha_pct} de significância."
    )


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
    body = ParagraphStyle("SolverBody", parent=styles["BodyText"], fontSize=9.5, leading=14.5, textColor=TEXT_L1)
    bullet = ParagraphStyle("SolverBullet", parent=body, leftIndent=10, spaceAfter=2)
    caption = ParagraphStyle("SolverCaption", parent=body, fontSize=8.5, textColor=TEXT_L2, leading=12.5, spaceBefore=6)

    meta = result.get("meta", {})
    story: List[Any] = [
        Paragraph(
            f"Delineamento <b>{meta.get('design')}</b> · Tipo <b>{meta.get('analysis_type')}</b> · "
            f"{meta.get('n_rows')} linhas analisadas",
            meta_style,
        ),
        Paragraph(_intro_text(result), body),
        Spacer(1, 0.3 * cm),
        _kpi_cards(result),
        Spacer(1, 0.45 * cm),
        Paragraph("Resumo executivo", h2),
    ]
    for msg in result.get("recommendations", []):
        story.append(Paragraph("• " + msg, bullet))
    for note in result.get("anova", {}).get("model_notes", []) or []:
        story.append(Paragraph("• Nota técnica: " + note, bullet))
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
        Paragraph(_anova_caption(result), caption),
    ]))
    story.append(Spacer(1, 0.35 * cm))

    means_rows = [["Tratamento", "Média", "n", "DP", "Grupo"]]
    for r in result.get("means", {}).get("treatment_means", []):
        means_rows.append([r.get("treatment"), _fmt(r.get("mean")), _fmt(r.get("n")), _fmt(r.get("sd")), r.get("group", "")])
    if len(means_rows) > 1:
        means_block = [Paragraph("Médias por tratamento", h2), _styled_table(means_rows)]
        means_caption = _means_caption(result)
        if means_caption:
            means_block.append(Paragraph(means_caption, caption))
        story.append(KeepTogether(means_block))
        story.append(Spacer(1, 0.3 * cm))

    comparison = result.get("means", {}).get("comparison")
    if comparison and comparison.get("comparisons"):
        comp_rows = [["Grupo A", "Grupo B", "Diferença", "Dif. crítica", "p", "Significativo"]]
        for c in comparison["comparisons"]:
            comp_rows.append([
                c.get("group_a"), c.get("group_b"), _fmt(c.get("diff")), _fmt(c.get("critical_diff")),
                _fmt(c.get("p_value")), "Sim" if c.get("significant") else "Não",
            ])
        comparison_block = [
            Paragraph(f"Teste de comparação de médias · {comparison.get('test')} (α = {comparison.get('alpha')})", h2),
            _styled_table(comp_rows),
        ]
        if comparison.get("note"):
            comparison_block.append(Paragraph(comparison.get("note"), caption))
        story.append(KeepTogether(comparison_block))
        story.append(Spacer(1, 0.3 * cm))

    reg = result.get("regression")
    if reg:
        selected = reg.get("selected_model", {})
        opt = selected.get("optimum") or {}
        reg_text = f"{selected.get('equation')} &nbsp;·&nbsp; R² ajustado: <b>{_fmt(selected.get('adj_r2'))}</b>"
        if opt.get("x") is not None:
            reg_text += f" &nbsp;·&nbsp; Ponto ótimo estimado: <b>x = {_fmt(opt.get('x'))}</b>, y = {_fmt(opt.get('y'))}"
        reg_flowables = [
            Paragraph("Regressão", h2),
            Paragraph(reg_text, body),
        ]
        plot_b64 = reg.get("plot_png_base64")
        if plot_b64:
            img_buffer = io.BytesIO(base64.b64decode(plot_b64))
            reg_flowables.append(Spacer(1, 0.25 * cm))
            reg_flowables.append(Image(img_buffer, width=14 * cm, height=8.1 * cm))
        story.append(KeepTogether(reg_flowables))

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

        comparison = result.get("means", {}).get("comparison") or {}
        if comparison.get("comparisons"):
            comp_df = pd.DataFrame(comparison.get("comparisons", []))
            comp_df.to_excel(writer, index=False, sheet_name="Comparacoes")
            _style_excel_sheet(writer.sheets["Comparacoes"], len(comp_df.columns) if not comp_df.empty else 1)

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
