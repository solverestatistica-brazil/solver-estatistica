"""Exportadores de resultados do Solver em PDF, Excel, PNG e PDF vetorial."""

from __future__ import annotations

import base64
import io
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from statistics_engine import analyze

import os
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Tipografia: replica a identidade do site (Exo 2 nos titulos, Open Sans no corpo).
# Sem acesso a rede neste ambiente de build para baixar as fontes exatas do Google
# Fonts, entao embutimos Lato (familia humanista, metricamente proxima de Open Sans)
# direto no repo em backend/fonts/. Se as fontes originais (Exo2-*.ttf/OpenSans-*.ttf)
# ficarem disponiveis depois, basta trocar os arquivos em backend/fonts/ - o resto do
# codigo referencia apenas os nomes logicos FONT_* abaixo.
_FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
try:
    pdfmetrics.registerFont(TTFont("Lato", os.path.join(_FONTS_DIR, "Lato-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("Lato-Bold", os.path.join(_FONTS_DIR, "Lato-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("Lato-Black", os.path.join(_FONTS_DIR, "Lato-Black.ttf")))
    pdfmetrics.registerFont(TTFont("Lato-Semibold", os.path.join(_FONTS_DIR, "Lato-Semibold.ttf")))
    pdfmetrics.registerFontFamily("Lato", normal="Lato", bold="Lato-Bold", italic="Lato", boldItalic="Lato-Bold")
    FONT_BODY = "Lato"
    FONT_BODY_BOLD = "Lato-Bold"
    FONT_HEADING = "Lato-Bold"
    FONT_HEADING_BLACK = "Lato-Black"
    FONT_SEMIBOLD = "Lato-Semibold"
except Exception:
    FONT_BODY = "Helvetica"
    FONT_BODY_BOLD = "Helvetica-Bold"
    FONT_HEADING = "Helvetica-Bold"
    FONT_HEADING_BLACK = "Helvetica-Bold"
    FONT_SEMIBOLD = "Helvetica-Bold"

# Paleta identica a assets/css/styles.css (identidade visual Solver, v3 harmonizada).
BRAND_DARK = colors.HexColor("#061210")
BRAND_DEEP = colors.HexColor("#194B41")
BRAND = colors.HexColor("#339D89")
BRAND_BRIGHT = colors.HexColor("#88D8C9")
TEXT_L1 = colors.HexColor("#16423A")
TEXT_L2 = colors.HexColor("#339D89")
SURFACE_LINE = colors.HexColor("#E7ECE9")
SURFACE_SUBTLE = colors.HexColor("#F4F7F5")
SUCCESS = colors.HexColor("#459586")
SUCCESS_TINT = colors.HexColor("#E0ECEA")
WARNING = colors.HexColor("#C6892E")
WARNING_TINT = colors.HexColor("#F2E7D2")
NEUTRAL = colors.HexColor("#94A3B8")
NEUTRAL_TINT = colors.HexColor("#EEF2F0")
ACCENT = colors.HexColor("#D16D2E")
ACCENT_TINT = colors.HexColor("#F1E2D4")
MUTED_ON_DARK = colors.HexColor("#5C8079")

# Layout: relatorio em A4 retrato (formato padrao de laudo tecnico impresso).
PAGE_SIZE = A4
PAGE_W, PAGE_H = PAGE_SIZE
MARGIN = 1.3 * cm
CONTENT_W = PAGE_W - 2 * MARGIN
CARD_W = 5.85 * cm
CARD_GAP_W = 0.4 * cm

# Hex simples (sem objeto Color) para marcacao inline em Paragraph (<font color="...">).
BRAND_HEX = "#339D89"
BRAND_DEEP_HEX = "#194B41"

HEX = {
    "brand_deep": "194B41",
    "brand": "339D89",
    "surface_line": "E7ECE9",
    "surface_subtle": "F4F7F5",
    "success": "459586",
    "success_tint": "E0ECEA",
    "warning": "C6892E",
    "warning_tint": "F2E7D2",
    "neutral": "94A3B8",
    "neutral_tint": "EEF2F0",
    "text_l1": "16423A",
    "text_l2": "339D89",
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
        decimals = 2 if abs(value) >= 1000 else 4
        return f"{value:.{decimals}f}".replace(".", ",")
    return str(value)

def _fmt_pct(value: Any) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}%".replace(".", ",")

def _draw_logo_mark(
    canvas_obj,
    x: float,
    y: float,
    size: float,
    mark_color=BRAND,
    trend_color=BRAND_BRIGHT,
    line_scale: float = 1.6,
) -> None:
    """Desenha apenas o icone do logo (moldura + linha de tendencia com seta na ponta),
    replicando o SVG do site. Parametrizado em x/y/size para ser reutilizado tanto no
    cabecalho pequeno de cada pagina quanto em tamanho grande na capa."""
    view = 40.0
    scale = size / view

    def _sp(px: float, py: float) -> Tuple[float, float]:
        return x + px * scale, y + size - py * scale

    canvas_obj.setStrokeColor(mark_color)
    canvas_obj.setLineWidth(line_scale * scale)
    canvas_obj.roundRect(x, y, size, size, 10 * scale, fill=0, stroke=1)

    canvas_obj.setStrokeColor(trend_color)
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

def _draw_header_footer(canvas_obj, doc) -> None:
    """Desenha a faixa de marca no topo e o rodape em toda pagina de conteudo do PDF
    (nao roda na capa, que tem seu proprio desenho de pagina inteira)."""
    canvas_obj.saveState()
    width, height = PAGE_SIZE

    canvas_obj.setFillColor(BRAND_DARK)
    band_clip = canvas_obj.beginPath()
    band_clip.rect(0, height - 2.2 * cm, width, 2.2 * cm)
    canvas_obj.clipPath(band_clip, stroke=0, fill=0)
    canvas_obj.linearGradient(
        0, height - 2.2 * cm, width, height,
        [BRAND_DARK, BRAND_DEEP],
        [0, 1],
    )

    logo_x, logo_y = 1.3 * cm, height - 1.75 * cm
    logo_size = 1.05 * cm
    _draw_logo_mark(canvas_obj, logo_x, logo_y, logo_size)

    canvas_obj.setFillColor(colors.white)
    canvas_obj.setFont(FONT_HEADING, 15)
    canvas_obj.drawString(logo_x + 1.35 * cm, height - 1.2 * cm, "SOLVER")
    canvas_obj.setFont(FONT_BODY, 6.8)
    canvas_obj.setFillColor(BRAND_BRIGHT)
    canvas_obj.drawString(logo_x + 1.35 * cm, height - 1.62 * cm, "INTELLIGENCE FOR FIELD TRIALS")

    canvas_obj.setFont(FONT_HEADING, 12.5)
    canvas_obj.setFillColor(colors.white)
    canvas_obj.drawRightString(width - 1.3 * cm, height - 1.2 * cm, "Relatório estatístico")
    canvas_obj.setFont(FONT_BODY, 7.5)
    canvas_obj.setFillColor(BRAND_BRIGHT)
    canvas_obj.drawRightString(
        width - 1.3 * cm,
        height - 1.62 * cm,
        datetime.now().strftime("Gerado em %d/%m/%Y às %H:%M"),
    )

    canvas_obj.setStrokeColor(SURFACE_LINE)
    canvas_obj.setLineWidth(0.6)
    canvas_obj.line(1.3 * cm, 1.15 * cm, width - 1.3 * cm, 1.15 * cm)
    canvas_obj.setFont(FONT_BODY, 7.5)
    canvas_obj.setFillColor(TEXT_L2)
    canvas_obj.drawString(
        1.3 * cm,
        0.75 * cm,
        "Solver Estatística Experimental · resultados de MVP devem ser validados antes de uso como laudo técnico oficial.",
    )
    canvas_obj.setFillColor(TEXT_L2)
    canvas_obj.drawRightString(width - 1.3 * cm, 0.75 * cm, f"Página {doc.page - 1}")
    canvas_obj.restoreState()

def _draw_cover_page(canvas_obj, doc) -> None:
    """Capa do relatorio: fundo cheio na cor de marca, logo grande, titulo em
    destaque e uma faixa com os 3 indicadores-chave (eco dos cards do dashboard)."""
    canvas_obj.saveState()
    width, height = PAGE_SIZE
    meta = getattr(doc, "_solver_meta", {}) or {}

    cover_clip = canvas_obj.beginPath()
    cover_clip.rect(0, 0, width, height)
    canvas_obj.clipPath(cover_clip, stroke=0, fill=0)
    canvas_obj.linearGradient(
        0, height, 0, 0,
        [colors.HexColor("#0F332B"), BRAND_DARK],
        [0, 1],
    )

    canvas_obj.setStrokeColor(BRAND_DEEP)
    canvas_obj.setLineWidth(1.1)
    canvas_obj.circle(width / 2, height - 10.6 * cm, 7.4 * cm, fill=0, stroke=1)

    logo_size = 2.55 * cm
    logo_x = width / 2 - logo_size / 2
    logo_y = height - 9.35 * cm
    _draw_logo_mark(canvas_obj, logo_x, logo_y, logo_size, line_scale=1.5)

    canvas_obj.setFillColor(colors.white)
    canvas_obj.setFont(FONT_HEADING_BLACK, 22)
    canvas_obj.drawCentredString(width / 2, height - 10.85 * cm, "SOLVER")
    canvas_obj.setFont(FONT_BODY, 9.5)
    canvas_obj.setFillColor(BRAND_BRIGHT)
    canvas_obj.drawCentredString(width / 2, height - 11.45 * cm, "I N T E L L I G E N C E   F O R   F I E L D   T R I A L S")

    canvas_obj.setFillColor(colors.white)
    canvas_obj.setFont(FONT_HEADING_BLACK, 30)
    canvas_obj.drawCentredString(width / 2, height - 15.6 * cm, "Relatório Estatístico")

    canvas_obj.setStrokeColor(BRAND)
    canvas_obj.setLineWidth(2.2)
    canvas_obj.line(width / 2 - 2.2 * cm, height - 16.35 * cm, width / 2 + 2.2 * cm, height - 16.35 * cm)

    design_label = DESIGN_LABELS.get(meta.get("design"), meta.get("design") or "—")
    type_label = TYPE_LABELS.get(meta.get("analysis_type"), meta.get("analysis_type") or "—")
    if meta.get("analysis_type") in (None, "single"):
        subtitle = design_label
    else:
        subtitle = f"{design_label} · {type_label.capitalize()}"
    canvas_obj.setFont(FONT_SEMIBOLD, 13.5)
    canvas_obj.setFillColor(BRAND_BRIGHT)
    canvas_obj.drawCentredString(width / 2, height - 17.35 * cm, subtitle)

    stats = getattr(doc, "_solver_cover_stats", []) or []
    if stats:
        strip_y = height - 21.7 * cm
        strip_w = width - 2 * 2.4 * cm
        n = len(stats)
        col_w = strip_w / n
        canvas_obj.setStrokeColor(BRAND_DEEP)
        canvas_obj.setLineWidth(0.8)
        canvas_obj.roundRect(2.4 * cm, strip_y, strip_w, 2.55 * cm, 9, fill=0, stroke=1)
        for i, (label, value) in enumerate(stats):
            cx = 2.4 * cm + col_w * i + col_w / 2
            if i > 0:
                canvas_obj.setStrokeColor(BRAND_DEEP)
                canvas_obj.setLineWidth(0.6)
                canvas_obj.line(2.4 * cm + col_w * i, strip_y + 0.35 * cm, 2.4 * cm + col_w * i, strip_y + 2.2 * cm)
            canvas_obj.setFont(FONT_HEADING_BLACK, 15.5)
            canvas_obj.setFillColor(colors.white)
            canvas_obj.drawCentredString(cx, strip_y + 1.5 * cm, value)
            canvas_obj.setFont(FONT_HEADING, 7.3)
            canvas_obj.setFillColor(BRAND_BRIGHT)
            canvas_obj.drawCentredString(cx, strip_y + 0.75 * cm, label.upper())

    canvas_obj.setStrokeColor(BRAND_DEEP)
    canvas_obj.setLineWidth(0.6)
    canvas_obj.line(2.4 * cm, 2.35 * cm, width - 2.4 * cm, 2.35 * cm)
    canvas_obj.setFont(FONT_BODY, 8.5)
    canvas_obj.setFillColor(BRAND_BRIGHT)
    canvas_obj.drawCentredString(width / 2, 1.85 * cm, "Documento gerado automaticamente pela plataforma Solver Estatística Experimental")
    canvas_obj.setFont(FONT_BODY, 7.5)
    canvas_obj.setFillColor(MUTED_ON_DARK)
    canvas_obj.drawCentredString(width / 2, 1.4 * cm, datetime.now().strftime("Gerado em %d/%m/%Y às %H:%M"))
    canvas_obj.restoreState()

def _kpi_card(label: str, value: str, sub: str) -> Table:
    label_style = ParagraphStyle("KpiLabel", fontName=FONT_HEADING, fontSize=7.5, textColor=TEXT_L2, leading=9)
    value_style = ParagraphStyle("KpiValue", fontName=FONT_HEADING_BLACK, fontSize=18, textColor=TEXT_L1, leading=21, spaceBefore=3)
    sub_style = ParagraphStyle("KpiSub", fontName=FONT_HEADING, fontSize=8, textColor=SUCCESS, spaceBefore=2)
    card = Table(
        [[Paragraph(label.upper(), label_style)], [Paragraph(value, value_style)], [Paragraph(sub, sub_style)]],
        colWidths=[CARD_W],
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

    card_w = CARD_W
    gap_w = CARD_GAP_W
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

def _styled_table(rows: List[List[Any]], sig_col: Optional[int] = None, col0_width: Optional[float] = None) -> Table:
    """Tabela no estilo do dashboard: sem grade vertical, so linhas horizontais
    finas + zebra, moldura externa arredondada - evita a cara de planilha crua.

    col0_width: quando informado, fixa a largura da 1a coluna (FV/Tratamento/Nivel)
    e envolve seu conteudo em Paragraph, para que nomes longos quebrem linha em vez
    de forcar a tabela a ficar mais larga que o frame (relevante no A4 retrato, onde
    a largura util e bem menor do que era na paisagem)."""
    n_rows = len(rows)
    col_widths = None
    if col0_width is not None and rows:
        n_cols = len(rows[0])
        other_w = (CONTENT_W - col0_width) / max(n_cols - 1, 1)
        col_widths = [col0_width] + [other_w] * (n_cols - 1)
        col0_style = ParagraphStyle("TableCol0", fontName=FONT_HEADING, fontSize=8.5, textColor=TEXT_L1, leading=10.5)
        rows = [rows[0]] + [
            [Paragraph(str(row[0]), col0_style)] + list(row[1:])
            for row in rows[1:]
        ]
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    table.hAlign = "LEFT"
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_DEEP),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), FONT_HEADING),
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
        ("ALIGN", (1, 1), (-1, -1), "LEFT"),
        ("FONTNAME", (0, 1), (0, -1), FONT_HEADING),
        ("TEXTCOLOR", (0, 1), (-1, -1), TEXT_L1),
    ]
    if sig_col is not None:
        for row_idx in range(1, n_rows):
            bg, fg = _sig_colors(rows[row_idx][sig_col])
            if bg is None:
                continue
            style.append(("BACKGROUND", (sig_col, row_idx), (sig_col, row_idx), bg))
            style.append(("TEXTCOLOR", (sig_col, row_idx), (sig_col, row_idx), fg))
            style.append(("FONTNAME", (sig_col, row_idx), (sig_col, row_idx), FONT_HEADING))
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

def _fmt_p(value: Any) -> str:
    if value is None:
        return "—"
    if value < 0.0001:
        return "p &lt; 0,0001"
    return f"p = {_fmt(value)}"

def _accent_heading(text: str) -> str:
    """Prefixa titulos de secao com um marcador colorido (acabamento do site)."""
    return f'<font color="{BRAND_HEX}">▪</font>&nbsp;&nbsp;{text}'

def _anova_narrative(result: Dict[str, Any]) -> Optional[str]:
    """Paragrafo cientifico que interpreta o teste F para as fontes de variacao reais do experimento."""
    anova = result.get("anova", {})
    table = anova.get("table", []) or []
    cv = anova.get("cv")
    cv_label = (anova.get("cv_label") or "").strip()
    named_rows = [r for r in table if r.get("source") not in (None, "Total", "Resíduo", "Residual")]
    sig_rows = [r for r in named_rows if r.get("significance") in ("1%", "5%")]
    ns_rows = [r for r in named_rows if r.get("significance") == "ns"]
    if not table:
        return None

    parts: List[str] = []
    if sig_rows:
        ranked = sorted(sig_rows, key=lambda r: r.get("f_calc") if r.get("f_calc") is not None else -1, reverse=True)
        lead = ranked[0]
        clauses = [f"{r['source']} (F = {_fmt(r.get('f_calc'))}; {_fmt_p(r.get('p_value'))})" for r in sig_rows]
        levels = sorted({r["significance"] for r in sig_rows})
        if len(sig_rows) > 1:
            others = [c for r, c in zip(sig_rows, clauses) if r is not lead]
            parts.append(
                f"O teste F aponta <b>{lead['source']}</b> como a fonte de variação de maior efeito relativo "
                f"(F = {_fmt(lead.get('f_calc'))}), acompanhada de efeito também significativo de " +
                " e ".join(others) +
                f" sobre a variável resposta, a {' e '.join(levels)} de probabilidade."
            )
        else:
            parts.append(
                "O teste F indica efeito estatisticamente significativo de " + clauses[0] +
                f" sobre a variável resposta, a {' e '.join(levels)} de probabilidade."
            )
    else:
        parts.append(
            "O teste F não indicou efeito estatisticamente significativo para nenhuma fonte de variação testada, "
            "a 5% de probabilidade — as diferenças observadas entre os grupos podem ser atribuídas ao acaso amostral."
        )
    if ns_rows:
        names = ", ".join(r["source"] for r in ns_rows)
        parts.append(f"Não houve evidência estatística de efeito para {names} (ns) nesse mesmo nível de exigência.")
    if cv is not None:
        qualifier = {
            "ótimo": "reforça a confiabilidade das conclusões e sugere boa condução experimental",
            "bom": "indica boa precisão experimental, compatível com ensaios de campo bem conduzidos",
            "moderado": "sugere precisão experimental moderada — interprete as diferenças com alguma cautela",
        }.get(cv_label.lower(), "deve ser considerado ao interpretar as diferenças observadas")
        parts.append(f"O coeficiente de variação experimental (CV = {_fmt_pct(cv)}, {cv_label.lower()}) {qualifier}.")
    return " ".join(parts)

def _means_narrative(result: Dict[str, Any]) -> Optional[str]:
    """Paragrafo que contextualiza o melhor e o pior tratamento com base na comparacao de medias real."""
    means = result.get("means", {}) or {}
    rows = means.get("treatment_means", []) or []
    comparison = means.get("comparison")
    if len(rows) < 2 or not comparison:
        return None
    best, worst = rows[0], rows[-1]
    test_name = str(comparison.get("test", "Tukey")).title()
    n_groups = len({r.get("group") for r in rows if r.get("group")})
    group_txt = (
        f" Ao todo, os {len(rows)} tratamentos avaliados se distribuíram em {n_groups} grupo(s) estatisticamente "
        f"distinto(s) pelo teste de {test_name}."
        if n_groups else ""
    )
    same_group = best.get("group") and best.get("group") == worst.get("group")
    if same_group:
        return (
            f"O tratamento <b>{best['treatment']}</b> apresentou a maior média ({_fmt(best.get('mean'))}), mas não "
            f"difere estatisticamente de <b>{worst['treatment']}</b> ({_fmt(worst.get('mean'))}) pelo teste de "
            f"{test_name}, ambos no grupo '{best.get('group')}' — ou seja, nenhum tratamento se destacou isoladamente "
            f"como superior aos demais.{group_txt}"
        )
    diff = None
    pct_txt = ""
    try:
        diff = float(best.get("mean")) - float(worst.get("mean"))
        if worst.get("mean"):
            pct = diff / float(worst["mean"]) * 100
            pct_txt = f" (+{pct:.1f}%)".replace(".", ",")
    except Exception:
        diff = None
    diff_txt = f", uma diferença de {_fmt(diff)} unidades{pct_txt} em relação ao tratamento de menor média" if diff is not None else ""
    return (
        f"O tratamento <b>{best['treatment']}</b> apresentou a maior média ({_fmt(best.get('mean'))}, grupo "
        f"'{best.get('group','')}'), estatisticamente superior a <b>{worst['treatment']}</b> "
        f"({_fmt(worst.get('mean'))}, grupo '{worst.get('group','')}') pelo teste de {test_name}{diff_txt}.{group_txt}"
    )

def _regression_narrative(result: Dict[str, Any]) -> Optional[str]:
    """Paragrafo que interpreta o modelo de regressao selecionado e o ponto otimo estimado."""
    reg = result.get("regression")
    if not reg:
        return None
    selected = reg.get("selected_model", {}) or {}
    opt = selected.get("optimum") or {}
    r2 = selected.get("adj_r2")
    x_label = reg.get("x_label") or "x"
    y_label = reg.get("y_label") or "resposta"
    parts = [
        f"O modelo de regressão de grau {reg.get('selected_degree')} apresentou o melhor ajuste entre os "
        f"candidatos avaliados (R² ajustado = {_fmt(r2)}), descrevendo a relação entre {x_label} e {y_label}."
    ]
    if opt.get("x") is not None:
        goal_word = "máxima" if opt.get("goal") == "max" else "mínima"
        parts.append(
            f" A resposta {goal_word} estimada pelo modelo ocorre em {x_label} = {_fmt(opt.get('x'))}, com valor "
            f"previsto de {_fmt(opt.get('y'))} para {y_label}."
        )
        points = reg.get("points") or []
        xs = [p.get("x") for p in points if p.get("x") is not None]
        if xs:
            try:
                x_min, x_max = min(xs), max(xs)
                opt_x = float(opt.get("x"))
                if opt_x <= x_min or opt_x >= x_max:
                    trend = "subindo" if goal_word == "máxima" else "descendo"
                    parts.append(
                        f" Esse ponto ótimo está no limite da faixa efetivamente testada ({_fmt(x_min)} a "
                        f"{_fmt(x_max)}) — recomenda-se avaliar níveis adicionais além desse limite para confirmar "
                        f"se a resposta continua {trend} fora do intervalo avaliado."
                    )
                else:
                    parts.append(
                        f" Como esse ponto está dentro da faixa efetivamente testada ({_fmt(x_min)} a {_fmt(x_max)}), "
                        f"a estimativa tem boa confiabilidade prática, sem necessidade de extrapolação."
                    )
            except (TypeError, ValueError):
                pass
    return "".join(parts)

def _executive_summary_box(messages: List[str], width: float) -> Table:
    """Caixa destacada (callout) para o resumo executivo, com barra de acento a esquerda,
    no lugar de uma lista solta de marcadores - visual mais premium/relatorio de verdade."""
    head_style = ParagraphStyle("ExecHead", fontName=FONT_HEADING, fontSize=12, textColor=BRAND_DEEP, spaceAfter=9)
    item_style = ParagraphStyle("ExecItem", fontName=FONT_BODY, fontSize=9.5, leading=14, textColor=TEXT_L1, spaceAfter=3)
    content: List[Any] = [Paragraph(_accent_heading("Resumo executivo"), head_style)]
    for msg in messages:
        content.append(Paragraph("•&nbsp;&nbsp;" + msg, item_style))
    inner = Table([[c] for c in content], colWidths=[width - 0.9 * cm])
    inner.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (0, 0), 9),
    ]))
    bar = Table([[""]], colWidths=[0.14 * cm], rowHeights=[inner.wrap(width - 0.9 * cm, 1000)[1]])
    bar.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BRAND)]))
    outer = Table([[bar, inner]], colWidths=[0.14 * cm, width - 0.14 * cm])
    outer.setStyle(TableStyle([
        ("BACKGROUND", (1, 0), (1, -1), SUCCESS_TINT),
        ("LEFTPADDING", (1, 0), (1, -1), 16),
        ("RIGHTPADDING", (1, 0), (1, -1), 16),
        ("TOPPADDING", (1, 0), (1, -1), 14),
        ("BOTTOMPADDING", (1, 0), (1, -1), 14),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, -1), 0),
        ("TOPPADDING", (0, 0), (0, -1), 0),
        ("BOTTOMPADDING", (0, 0), (0, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return outer

def build_pdf(payload: Dict[str, Any]) -> bytes:
    """Gera relatorio tecnico em PDF, com identidade visual Solver, a partir do payload de analise."""
    result = analyze(payload)
    buffer = io.BytesIO()
    doc = BaseDocTemplate(
        buffer,
        pagesize=PAGE_SIZE,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=2.6 * cm,
        bottomMargin=1.55 * cm,
        title="Relatório Solver Estatística",
    )
    content_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="solver-frame")
    cover_frame = Frame(MARGIN, MARGIN, doc.width, PAGE_H - 2 * MARGIN, id="solver-cover-frame")
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[cover_frame], onPage=_draw_cover_page),
        PageTemplate(id="solver", frames=[content_frame], onPage=_draw_header_footer),
    ])

    meta_for_cover = result.get("meta", {})
    cv_for_cover = result.get("anova", {}).get("cv")
    best_for_cover = (result.get("means") or {}).get("best")
    doc._solver_meta = meta_for_cover
    doc._solver_cover_stats = [
        ("Observações", str(meta_for_cover.get("n_rows", "—"))),
        ("CV experimental", _fmt_pct(cv_for_cover) if cv_for_cover is not None else "—"),
        ("Melhor tratamento", str(best_for_cover.get("treatment")) if best_for_cover else "—"),
    ]

    styles = getSampleStyleSheet()
    meta_style = ParagraphStyle("SolverMeta", parent=styles["BodyText"], fontName=FONT_BODY, fontSize=9.5, textColor=TEXT_L2, spaceAfter=4)
    h2 = ParagraphStyle("SolverH2", parent=styles["Heading2"], fontName=FONT_HEADING, fontSize=12.5, textColor=BRAND_DEEP, spaceBefore=4, spaceAfter=7)
    body = ParagraphStyle("SolverBody", parent=styles["BodyText"], fontName=FONT_BODY, fontSize=9.5, leading=14.5, textColor=TEXT_L1)
    bullet = ParagraphStyle("SolverBullet", parent=body, leftIndent=10, spaceAfter=2)
    caption = ParagraphStyle("SolverCaption", parent=body, fontSize=8.5, textColor=TEXT_L2, leading=12.5, spaceBefore=6)

    meta = result.get("meta", {})
    story: List[Any] = [
        NextPageTemplate("solver"),
        Spacer(1, 1),
        PageBreak(),
        Paragraph(
            f"Delineamento <b>{meta.get('design')}</b> · Tipo <b>{meta.get('analysis_type')}</b> · "
            f"{meta.get('n_rows')} linhas analisadas",
            meta_style,
        ),
        Paragraph(_intro_text(result), body),
        Spacer(1, 0.3 * cm),
        _kpi_cards(result),
        Spacer(1, 0.4 * cm),
    ]
    exec_messages = list(result.get("recommendations", []))
    for note in result.get("anova", {}).get("model_notes", []) or []:
        exec_messages.append("Nota técnica: " + note)
    if exec_messages:
        story.append(_executive_summary_box(exec_messages, doc.width))
    story.append(Spacer(1, 0.4 * cm))

    anova_rows = [["FV", "GL", "SQ", "QM", "F calc", "F 5%", "F 1%", "p", "Sig"]]
    for r in result.get("anova", {}).get("table", []):
        anova_rows.append([
            r.get("source"), _fmt(r.get("df")), _fmt(r.get("sum_sq")), _fmt(r.get("mean_sq")),
            _fmt(r.get("f_calc")), _fmt(r.get("f_5")), _fmt(r.get("f_1")), _fmt(r.get("p_value")), r.get("significance"),
        ])
    if len(anova_rows) > 1:
        anova_block: List[Any] = [
            Paragraph(_accent_heading("Quadro de ANOVA · Teste F"), h2),
            _styled_table(anova_rows, sig_col=8, col0_width=4.6 * cm),
        ]
        anova_narrative = _anova_narrative(result)
        if anova_narrative:
            anova_block.append(Spacer(1, 0.14 * cm))
            anova_block.append(Paragraph(anova_narrative, body))
        anova_block.append(Paragraph(_anova_caption(result), caption))
        story.append(CondPageBreak(3.2 * cm))
        story.append(KeepTogether(anova_block))
        story.append(Spacer(1, 0.35 * cm))

    means_rows = [["Tratamento", "Média", "n", "DP", "Grupo"]]
    for r in result.get("means", {}).get("treatment_means", []):
        means_rows.append([r.get("treatment"), _fmt(r.get("mean")), _fmt(r.get("n")), _fmt(r.get("sd")), r.get("group", "")])
    if len(means_rows) > 1:
        means_block: List[Any] = [
            Paragraph(_accent_heading("Médias por tratamento"), h2),
            _styled_table(means_rows),
        ]
        means_narrative = _means_narrative(result)
        if means_narrative:
            means_block.append(Spacer(1, 0.14 * cm))
            means_block.append(Paragraph(means_narrative, body))
        means_caption = _means_caption(result)
        if means_caption:
            means_block.append(Paragraph(means_caption, caption))
        story.append(CondPageBreak(3.2 * cm))
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
        comp_block: List[Any] = [
            Paragraph(_accent_heading(f"Teste de comparação de médias · {comparison.get('test')} (α = {comparison.get('alpha')})"), h2),
            _styled_table(comp_rows),
        ]
        if comparison.get("note"):
            comp_block.append(Paragraph(comparison.get("note"), caption))
        story.append(CondPageBreak(3.2 * cm))
        story.append(KeepTogether(comp_block))
        story.append(Spacer(1, 0.3 * cm))

    for fc in result.get("factor_comparisons", []) or []:
        fc_rows = [["Nível", "Média", "n", "Grupo"]]
        for lv in fc.get("levels", []):
            fc_rows.append([lv.get("treatment"), _fmt(lv.get("mean")), _fmt(lv.get("n")), lv.get("group", "")])
        if len(fc_rows) <= 1:
            continue
        error_label = "Erro (a)" if fc.get("error_used") == "a" else "Erro (b)"
        story.append(CondPageBreak(3.2 * cm))
        story.append(Paragraph(_accent_heading(f"Médias marginais · fator {fc.get('factor')} ({fc.get('test')}, {error_label})"), h2))
        story.append(_styled_table(fc_rows))
        alpha_pct = f"{fc.get('alpha', 0.05) * 100:.0f}%".replace(".", ",")
        story.append(Paragraph(
            f"Médias do fator <b>{fc.get('factor')}</b> seguidas pela mesma letra não diferem "
            f"estatisticamente entre si (α = {alpha_pct}).", caption,
        ))
        story.append(Spacer(1, 0.3 * cm))

    interaction_blocks = result.get("interaction_breakdown", []) or []
    if interaction_blocks:
        story.append(CondPageBreak(3.2 * cm))
        first_block = interaction_blocks[0]
        story.append(Paragraph(_accent_heading(
            f"Desdobramento da interação · {first_block.get('factor')} × {first_block.get('sub_factor')}"), h2,
        ))
        story.append(Paragraph(
            "Interação significativa: cada nível do fator de parcela é analisado separadamente, "
            "comparando os níveis do outro fator dentro dele (efeitos simples).", caption,
        ))
        for block in interaction_blocks:
            ib_rows = [["Nível", "Média", "n", "Grupo"]]
            for lv in block.get("levels", []):
                ib_rows.append([lv.get("treatment"), _fmt(lv.get("mean")), _fmt(lv.get("n")), lv.get("group", "")])
            if len(ib_rows) <= 1:
                continue
            story.append(Spacer(1, 0.15 * cm))
            story.append(Paragraph(f"{block.get('factor')} = {block.get('level')}", body))
            story.append(_styled_table(ib_rows))
        story.append(Spacer(1, 0.3 * cm))

    reg = result.get("regression")
    if reg:
        selected = reg.get("selected_model", {})
        opt = selected.get("optimum") or {}
        reg_text = f"{selected.get('equation')} &nbsp;·&nbsp; R² ajustado: <b>{_fmt(selected.get('adj_r2'))}</b>"
        if opt.get("x") is not None:
            reg_text += f" &nbsp;·&nbsp; Ponto ótimo estimado: <b>x = {_fmt(opt.get('x'))}</b>, y = {_fmt(opt.get('y'))}"
        story.append(CondPageBreak(3.2 * cm))
        story.append(Paragraph(_accent_heading("Regressão"), h2))
        story.append(Paragraph(reg_text, body))
        reg_narrative = _regression_narrative(result)
        if reg_narrative:
            story.append(Spacer(1, 0.12 * cm))
            story.append(Paragraph(reg_narrative, body))
        plot_b64 = reg.get("plot_png_base64")
        if plot_b64:
            img_buffer = io.BytesIO(base64.b64decode(plot_b64))
            story.append(Spacer(1, 0.25 * cm))
            story.append(Image(img_buffer, width=17.5 * cm, height=10.13 * cm))

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

        factor_rows = []
        for fc in result.get("factor_comparisons", []) or []:
            for lv in fc.get("levels", []):
                factor_rows.append({
                    "fator": fc.get("factor"), "nivel": lv.get("treatment"),
                    "media": lv.get("mean"), "n": lv.get("n"), "grupo": lv.get("group", ""),
                    "teste": fc.get("test"), "alpha": fc.get("alpha"),
                })
        if factor_rows:
            factor_df = pd.DataFrame(factor_rows)
            factor_df.to_excel(writer, index=False, sheet_name="Fatores")
            _style_excel_sheet(writer.sheets["Fatores"], len(factor_df.columns))

        interaction_rows = []
        for block in result.get("interaction_breakdown", []) or []:
            for lv in block.get("levels", []):
                interaction_rows.append({
                    "fator_parcela": block.get("factor"), "nivel_parcela": block.get("level"),
                    "fator_subparcela": block.get("sub_factor"), "nivel_subparcela": lv.get("treatment"),
                    "media": lv.get("mean"), "n": lv.get("n"), "grupo": lv.get("group", ""),
                })
        if interaction_rows:
            interaction_df = pd.DataFrame(interaction_rows)
            interaction_df.to_excel(writer, index=False, sheet_name="Interacao")
            _style_excel_sheet(writer.sheets["Interacao"], len(interaction_df.columns))

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
    ax.scatter(points["x"], points["y"], label="Observado", color="#339D89")
    ax.plot(curve["x"], curve["y"], label=f"Grau {reg['selected_degree']} · R²aj {selected['adj_r2']:.3f}", color="#194B41")
    opt = selected.get("optimum") or {}
    if opt.get("x") is not None:
        ax.axvline(opt["x"], linestyle="--", linewidth=1, color="#D16D2E")
        ax.scatter([opt["x"]], [opt["y"]], marker="o", s=55, label="Ótimo", color="#D16D2E")
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
