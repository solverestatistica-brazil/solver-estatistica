"""Exportadores Solver — PDF (estilo dashboard escuro), Excel e gráficos.

v2: PDF em fundo preto (#0A0A0A) com verde emerald (#22C55E) como cor de
marca, no mesmo idioma visual do site (bento cards, tipografia limpa).
Excel mantém cabeçalho escuro + corpo claro para facilitar impressão.
"""

from __future__ import annotations

import io
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

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
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

from statistics_engine import analyze
from provenance import build_provenance

# ============================================================================
# Paleta v2 — idêntica ao site (dark / emerald)
# ============================================================================
CANVAS = colors.HexColor("#0A0A0A")           # fundo da página
CANVAS_ELEVATED = colors.HexColor("#121212")   # fundo dos cards
CANVAS_ELEVATED_2 = colors.HexColor("#171717")  # cabeçalho de tabela
BORDER = colors.HexColor("#262626")            # borda dos cards / linhas
BORDER_BRAND = colors.HexColor("#166534")      # borda destacada verde

TEXT_D1 = colors.HexColor("#F5F5F5")           # texto principal
TEXT_D2 = colors.HexColor("#A3A3A3")           # texto secundário
TEXT_D3 = colors.HexColor("#666666")           # texto terciário

BRAND = colors.HexColor("#22C55E")             # verde primário
BRAND_HI = colors.HexColor("#4ADE80")          # verde highlight
BRAND_DEEP = colors.HexColor("#166534")        # verde escuro
BRAND_DIM = colors.HexColor("#0E2818")         # verde muito escuro (fundo de badge)

SUCCESS = BRAND
SUCCESS_DIM = colors.HexColor("#0E2818")
WARNING = colors.HexColor("#F5A85B")
WARNING_DIM = colors.HexColor("#2A1B0A")
ERROR = colors.HexColor("#EF4444")
ERROR_DIM = colors.HexColor("#2A0F0F")
NEUTRAL = colors.HexColor("#737373")
NEUTRAL_DIM = colors.HexColor("#1F1F1F")

# Excel — cabeçalho escuro, corpo claro para impressão.
HEX = {
    "brand_deep": "166534",
    "brand": "22C55E",
    "canvas": "0A0A0A",
    "surface": "FFFFFF",
    "surface_line": "E5E7EB",
    "surface_subtle": "F4F6F5",
    "success": "16A34A",
    "success_tint": "DCFCE7",
    "warning": "D97706",
    "warning_tint": "FEF3C7",
    "neutral": "737373",
    "neutral_tint": "F5F5F5",
    "text_l1": "0F1F14",
    "text_l2": "525252",
    "white": "FFFFFF",
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
    """Desenha fundo preto + faixa de marca no topo + rodapé em toda página."""
    canvas_obj.saveState()
    width, height = landscape(A4)

    # ---------- fundo preto full-bleed ----------
    canvas_obj.setFillColor(CANVAS)
    canvas_obj.rect(0, 0, width, height, fill=1, stroke=0)

    # ---------- header ----------
    header_h = 2.4 * cm
    canvas_obj.setFillColor(CANVAS_ELEVATED)
    canvas_obj.rect(0, height - header_h, width, header_h, fill=1, stroke=0)

    # linha inferior sutil no header
    canvas_obj.setStrokeColor(BORDER)
    canvas_obj.setLineWidth(0.5)
    canvas_obj.line(0, height - header_h, width, height - header_h)

    # logo — mesma geometria do site
    logo_x, logo_y = 1.3 * cm, height - 1.85 * cm
    logo_size = 1.1 * cm
    view = 40.0
    scale = logo_size / view

    def _sp(x: float, y: float) -> Tuple[float, float]:
        return logo_x + x * scale, logo_y + logo_size - y * scale

    # moldura do logo
    canvas_obj.setStrokeColor(BRAND)
    canvas_obj.setLineWidth(1.6 * scale)
    canvas_obj.setFillColor(CANVAS)
    canvas_obj.roundRect(logo_x, logo_y, logo_size, logo_size, 10 * scale, fill=1, stroke=1)

    # trend line + seta
    canvas_obj.setStrokeColor(BRAND_HI)
    canvas_obj.setLineWidth(2.4 * scale)
    canvas_obj.setLineCap(1)
    canvas_obj.setLineJoin(1)

    trend = canvas_obj.beginPath()
    for i, (px, py) in enumerate([(10, 25), (16, 18), (20, 21), (28, 12)]):
        cx, cy = _sp(px, py)
        (trend.moveTo if i == 0 else trend.lineTo)(cx, cy)
    canvas_obj.drawPath(trend, stroke=1, fill=0)

    arrow = canvas_obj.beginPath()
    for i, (px, py) in enumerate([(23, 12), (28, 12), (28, 17)]):
        cx, cy = _sp(px, py)
        (arrow.moveTo if i == 0 else arrow.lineTo)(cx, cy)
    canvas_obj.drawPath(arrow, stroke=1, fill=0)

    # wordmark
    canvas_obj.setFillColor(TEXT_D1)
    canvas_obj.setFont("Helvetica-Bold", 15)
    canvas_obj.drawString(logo_x + 1.4 * cm, height - 1.25 * cm, "SOLVER")
    canvas_obj.setFont("Helvetica", 6.8)
    canvas_obj.setFillColor(TEXT_D3)
    canvas_obj.drawString(logo_x + 1.4 * cm, height - 1.62 * cm, "INTELLIGENCE FOR FIELD TRIALS")

    # título direito
    canvas_obj.setFont("Helvetica-Bold", 12.5)
    canvas_obj.setFillColor(TEXT_D1)
    canvas_obj.drawRightString(width - 1.3 * cm, height - 1.25 * cm, "Relatório estatístico")
    canvas_obj.setFont("Helvetica", 7.5)
    canvas_obj.setFillColor(BRAND)
    canvas_obj.drawRightString(
        width - 1.3 * cm,
        height - 1.62 * cm,
        datetime.now().strftime("Gerado em %d/%m/%Y às %H:%M"),
    )

    # ---------- footer ----------
    canvas_obj.setStrokeColor(BORDER)
    canvas_obj.setLineWidth(0.5)
    canvas_obj.line(1.3 * cm, 1.15 * cm, width - 1.3 * cm, 1.15 * cm)
    canvas_obj.setFont("Helvetica", 7.5)
    canvas_obj.setFillColor(TEXT_D3)
    canvas_obj.drawString(
        1.3 * cm,
        0.75 * cm,
        f"Solver {getattr(doc, 'engine_version', '—')} · commit {getattr(doc, 'commit_short', '—')} · revisão técnica obrigatória.",
    )
    canvas_obj.drawRightString(width - 1.3 * cm, 0.75 * cm, f"Página {doc.page}")
    canvas_obj.restoreState()


def _kpi_card(label: str, value: str, sub: str) -> Table:
    """Card de KPI escuro no estilo do dashboard bento."""
    label_style = ParagraphStyle(
        "KpiLabel", fontName="Helvetica-Bold", fontSize=7.5,
        textColor=TEXT_D3, leading=9,
    )
    value_style = ParagraphStyle(
        "KpiValue", fontName="Helvetica-Bold", fontSize=22,
        textColor=TEXT_D1, leading=24, spaceBefore=6,
    )
    sub_style = ParagraphStyle(
        "KpiSub", fontName="Helvetica-Bold", fontSize=8,
        textColor=BRAND, spaceBefore=3,
    )
    card = Table(
        [[Paragraph(label.upper(), label_style)],
         [Paragraph(value, value_style)],
         [Paragraph(sub, sub_style)]],
        colWidths=[8.7 * cm],
    )
    card.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, BORDER),
        ("ROUNDEDCORNERS", [10, 10, 10, 10]),
        ("BACKGROUND", (0, 0), (-1, -1), CANVAS_ELEVATED),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 16),
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
    """Fundo + cor do texto para o badge de significância."""
    if value == "1%":
        return SUCCESS_DIM, BRAND
    if value == "5%":
        return WARNING_DIM, WARNING
    if value in (None, "—", "-", "ns"):
        return NEUTRAL_DIM, NEUTRAL
    return None, None


def _styled_table(
    rows: List[List[Any]], sig_col: Optional[int] = None, col_widths: Optional[List[float]] = None,
    right_align_from: Optional[int] = 1, row_padding: float = 8,
) -> Table:
    """Tabela escura no estilo do dashboard: header verde-escuro, zebra sutil,
    moldura arredondada."""
    table = Table(rows, repeatRows=1, colWidths=col_widths)
    n_rows = len(rows)
    style = [
        # header
        ("BACKGROUND", (0, 0), (-1, 0), CANVAS_ELEVATED_2),
        ("TEXTCOLOR", (0, 0), (-1, 0), TEXT_D2),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        # corpo
        ("TEXTCOLOR", (0, 1), (-1, -1), TEXT_D1),
        ("BACKGROUND", (0, 1), (-1, -1), CANVAS_ELEVATED),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [CANVAS_ELEVATED, colors.HexColor("#0F0F0F")]),
        # linhas separadoras
        ("LINEBELOW", (0, 0), (-1, n_rows - 2), 0.5, BORDER),
        ("LINEBELOW", (0, 0), (-1, 0), 1.4, BRAND),
        ("BOX", (0, 0), (-1, -1), 0.8, BORDER),
        ("ROUNDEDCORNERS", [8, 8, 8, 8]),
        # alinhamento e padding
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), row_padding),
        ("BOTTOMPADDING", (0, 0), (-1, -1), row_padding),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
    ]
    if right_align_from is not None:
        style.append(("ALIGN", (right_align_from, 1), (-1, -1), "RIGHT"))
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


def _anova_caption() -> str:
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
    # [FIX auditoria P1-04] Dunnett so compara cada tratamento contra a testemunha — nunca
    # tratamento contra tratamento. A legenda de "mesma letra" e' invalida aqui (sugeriria
    # relacoes nunca testadas) e a coluna Grupo nem usa mais letras para este teste.
    if test_name == "DUNNETT":
        control = comparison.get("control") or "—"
        legenda = (
            f"Coluna <b>Grupo</b>: 'testemunha' identifica o controle ({control}); 'sig' indica "
            f"diferença estatisticamente significativa contra a testemunha pelo teste de "
            f"<b>Dunnett</b> exato, ao nível de {alpha_pct}; 'ns' indica ausência de diferença "
            f"significativa. O Dunnett <b>não</b> compara tratamentos entre si, apenas cada um "
            f"contra a testemunha."
        )
        note = comparison.get("note") or ""
        if "não informada" in note or "nao informada" in note.lower():
            legenda += f" <b>Atenção:</b> {note}"
        return legenda
    return (
        f"Tratamentos seguidos pela mesma letra na coluna <b>Grupo</b> não diferem estatisticamente "
        f"entre si pelo teste de <b>{test_name.title()}</b>, ao nível de {alpha_pct} de significância."
    )


def build_pdf(payload: Dict[str, Any]) -> bytes:
    """Gera relatório técnico em PDF no estilo dashboard escuro."""
    result = analyze(payload)
    provenance = result.get("provenance") or build_provenance(payload)
    buffer = io.BytesIO()
    page_size = landscape(A4)
    doc = BaseDocTemplate(
        buffer,
        pagesize=page_size,
        leftMargin=1.3 * cm,
        rightMargin=1.3 * cm,
        topMargin=2.75 * cm,
        bottomMargin=1.55 * cm,
        title="Relatório Solver Estatística",
    )
    doc.engine_version = provenance.get("engine_version", "—")
    doc.commit_short = str(provenance.get("git_commit", "—"))[:12]
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="solver-frame")
    doc.addPageTemplates([PageTemplate(id="solver", frames=[frame], onPage=_draw_header_footer)])

    styles = getSampleStyleSheet()
    meta_style = ParagraphStyle(
        "SolverMeta", parent=styles["BodyText"],
        fontName="Helvetica", fontSize=9.5, textColor=TEXT_D2, spaceAfter=4,
    )
    h2 = ParagraphStyle(
        "SolverH2", parent=styles["Heading2"],
        fontName="Helvetica-Bold", fontSize=13, textColor=TEXT_D1,
        spaceBefore=6, spaceAfter=9, keepWithNext=1,
    )
    body = ParagraphStyle(
        "SolverBody", parent=styles["BodyText"],
        fontName="Helvetica", fontSize=9.5, leading=14.5, textColor=TEXT_D1,
    )
    body_dim = ParagraphStyle(
        "SolverBodyDim", parent=body, textColor=TEXT_D2,
    )
    bullet = ParagraphStyle(
        "SolverBullet", parent=body, leftIndent=10, spaceAfter=3, textColor=TEXT_D2,
    )
    caption = ParagraphStyle(
        "SolverCaption", parent=body_dim,
        fontSize=8.5, leading=12.5, spaceBefore=8,
    )
    tag = ParagraphStyle(
        "SolverTag", parent=body, fontName="Helvetica-Bold",
        fontSize=8.5, textColor=BRAND, leading=11, spaceBefore=0, spaceAfter=6,
    )

    meta = result.get("meta", {})
    story: List[Any] = [
        Paragraph(
            f"DELINEAMENTO {meta.get('design')} · TIPO {meta.get('analysis_type')} · "
            f"{meta.get('n_rows')} LINHAS",
            tag,
        ),
        Paragraph(_intro_text(result), body),
        Paragraph(
            f"Alfa: <b>{_fmt(meta.get('alpha'))}</b> ({escape(str(meta.get('alpha_mode', 'auto')))}) · "
            f"Soma de quadrados: <b>tipo {_fmt(meta.get('sum_squares_type'))}</b> · "
            f"Motor: <b>{escape(str(provenance.get('engine_version', '—')))}</b> · "
            f"Commit: <b>{escape(str(provenance.get('git_commit', '—'))[:12])}</b>",
            meta_style,
        ),
        Spacer(1, 0.35 * cm),
        _kpi_cards(result),
        Spacer(1, 0.5 * cm),
        Paragraph("Resumo executivo", h2),
    ]
    for msg in result.get("recommendations", []):
        story.append(Paragraph("• " + msg, bullet))
    story.append(Spacer(1, 0.35 * cm))

    anova_rows = [["FV", "GL", "SQ", "QM", "F calc", "F 5%", "F 1%", "p", "Sig"]]
    for r in result.get("anova", {}).get("table", []):
        anova_rows.append([
            r.get("source"), _fmt(r.get("df")), _fmt(r.get("sum_sq")), _fmt(r.get("mean_sq")),
            _fmt(r.get("f_calc")), _fmt(r.get("f_5")), _fmt(r.get("f_1")), _fmt(r.get("p_value")),
            r.get("significance"),
        ])
    story.append(KeepTogether([
        Paragraph("Quadro de ANOVA · Teste F", h2),
        _styled_table(anova_rows, sig_col=8),
        Paragraph(_anova_caption(), caption),
    ]))
    story.append(Spacer(1, 0.4 * cm))

    means_rows = [["Tratamento", "Média", "n", "DP", "Grupo"]]
    for r in result.get("means", {}).get("treatment_means", []):
        means_rows.append([
            r.get("treatment"), _fmt(r.get("mean")), _fmt(r.get("n")),
            _fmt(r.get("sd")), r.get("group", ""),
        ])
    if len(means_rows) > 1:
        means_block = [Paragraph("Médias por tratamento", h2), _styled_table(means_rows)]
        m_caption = _means_caption(result)
        if m_caption:
            means_block.append(Paragraph(m_caption, caption))
        story.append(KeepTogether(means_block))
        story.append(Spacer(1, 0.35 * cm))

    comparison = (result.get("means") or {}).get("comparison") or {}
    comparison_rows = comparison.get("comparisons") or []
    if comparison_rows:
        detail_rows: List[List[Any]] = [["Grupo A", "Grupo B", "Diferença", "Dif. crítica", "p ajustado", "Decisão"]]
        for row in comparison_rows:
            detail_rows.append([
                row.get("group_a"), row.get("group_b"), _fmt(row.get("diff")),
                _fmt(row.get("critical_diff")), _fmt(row.get("p_value")),
                "significativo" if row.get("significant") else "não significativo",
            ])
        story.append(KeepTogether([
            Paragraph("Comparações detalhadas", h2),
            _styled_table(detail_rows),
        ]))
        story.append(Spacer(1, 0.35 * cm))

    factor_comparisons = result.get("factor_comparisons") or []
    if factor_comparisons:
        story.append(Paragraph("Comparações por fator", h2))
        for item in factor_comparisons:
            story.append(Paragraph(
                f"<b>{escape(str(item.get('factor', '—')))}</b> · {escape(str(item.get('test', '—')))} · "
                f"alfa {_fmt(item.get('alpha'))} · erro {escape(str(item.get('error_used', '—')))}",
                caption,
            ))
            rows = [["Nível", "Média", "n", "Grupo"]]
            for level in item.get("levels") or []:
                rows.append([level.get("treatment"), _fmt(level.get("mean")), _fmt(level.get("n")), level.get("group")])
            story.append(_styled_table(rows))
            story.append(Spacer(1, 0.25 * cm))

    breakdown = result.get("interaction_breakdown") or []
    if breakdown:
        story.append(Paragraph("Desdobramento da interação", h2))
        for item in breakdown:
            story.append(Paragraph(
                f"<b>{escape(str(item.get('factor', '—')))} = {escape(str(item.get('level', '—')))}</b> · "
                f"níveis de {escape(str(item.get('sub_factor', '—')))} · {escape(str(item.get('test', '—')))}",
                caption,
            ))
            rows = [["Nível", "Média", "n", "Grupo"]]
            for level in item.get("levels") or []:
                rows.append([level.get("treatment"), _fmt(level.get("mean")), _fmt(level.get("n")), level.get("group")])
            story.append(_styled_table(rows))
            story.append(Spacer(1, 0.25 * cm))

    pressupostos = result.get("pressupostos") or {}
    tests = pressupostos.get("testes") or {}
    if tests:
        story.append(Paragraph("Pressupostos da ANOVA", h2))
        story.append(Paragraph(
            f"Veredito: <b>{escape(str(pressupostos.get('veredito', '—')).upper())}</b> · "
            f"{escape(str(pressupostos.get('resumo', '')))}",
            body,
        ))
        assumption_rows: List[List[Any]] = [["Pressuposto", "Teste", "Status", "Estatística", "p", "Interpretação"]]
        for key, item in tests.items():
            assumption_rows.append([
                Paragraph(escape(str(key)), caption),
                Paragraph(escape(str(item.get("teste", ""))), caption),
                Paragraph(escape(str(item.get("status", ""))), caption),
                _fmt(item.get("statistic")),
                _fmt(item.get("p_value")), Paragraph(escape(str(item.get("mensagem", ""))), caption),
            ])
        story.append(_styled_table(
            assumption_rows,
            col_widths=[4.0 * cm, 4.8 * cm, 2.4 * cm, 2.4 * cm, 1.7 * cm, 11.4 * cm],
        ))
        transform = result.get("transformacao_sugerida")
        if transform:
            story.append(Paragraph(
                f"Transformação sugerida: <b>{escape(str(transform.get('metodo', '—')))}</b> · "
                f"{escape(str(transform.get('descricao', '')))} {escape(str(transform.get('mensagem', '')))}",
                caption,
            ))
        story.append(Spacer(1, 0.35 * cm))

    reg = result.get("regression")
    if reg:
        selected = reg.get("selected_model", {})
        opt = selected.get("optimum") or {}
        reg_text = (
            f"{escape(str(selected.get('equation', '')))} &nbsp;·&nbsp; "
            f"R² ajustado: <b>{_fmt(selected.get('adj_r2'))}</b> &nbsp;·&nbsp; "
            f"AIC: <b>{_fmt(selected.get('aic'))}</b> &nbsp;·&nbsp; "
            f"BIC: <b>{_fmt(selected.get('bic'))}</b> &nbsp;·&nbsp; "
            f"p do termo superior: <b>{_fmt(selected.get('p_top_term'))}</b>"
        )
        if opt.get("x") is not None:
            reg_text += (
                f" &nbsp;·&nbsp; Ponto ótimo estimado: "
                f"<b>x = {_fmt(opt.get('x'))}</b>, y = {_fmt(opt.get('y'))}"
            )
        story.append(KeepTogether([
            Paragraph("Regressão", h2),
            Paragraph(reg_text, body),
        ]))
        lack = selected.get("lack_of_fit") or {}
        story.append(Paragraph(
            (
                f"Falta de ajuste: F={_fmt(lack.get('f_value'))}, p={_fmt(lack.get('p_value'))}. "
                f"{escape(str(lack.get('note', '')))}"
            ),
            caption,
        ))

    config = provenance.get("config") or {}
    trace_rows: List[List[Any]] = [["Campo", "Valor"]]
    trace_rows.extend([
        ["Versão do motor", provenance.get("engine_version")],
        ["Commit", provenance.get("git_commit")],
        ["Gerado em UTC", provenance.get("generated_at_utc")],
        ["SHA-256 dos dados", provenance.get("data_sha256")],
        ["SHA-256 da configuração", provenance.get("config_sha256")],
    ])
    for key, value in sorted(config.items()):
        trace_rows.append([key, Paragraph(escape(json.dumps(value, ensure_ascii=False, default=str)), caption)])
    story.extend([
        Spacer(1, 0.35 * cm),
        Paragraph("Configuração e rastreabilidade", h2),
        _styled_table(
            trace_rows,
            col_widths=[6.2 * cm, 20.5 * cm],
            right_align_from=None,
            row_padding=5,
        ),
    ])

    doc.build(story)
    return buffer.getvalue()


# ============================================================================
# EXCEL — mantém cabeçalho escuro + corpo claro (impressão amigável)
# ============================================================================
def _style_excel_sheet(worksheet, n_cols: int) -> None:
    header_fill = PatternFill(start_color=HEX["brand_deep"], end_color=HEX["brand_deep"], fill_type="solid")
    header_font = Font(color=HEX["white"], bold=True, size=10, name="Calibri")
    body_font = Font(color=HEX["text_l1"], size=10, name="Calibri")
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
            cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
            if isinstance(cell.value, float):
                cell.number_format = "0.0000"
            elif isinstance(cell.value, int):
                cell.number_format = "0"
            if row % 2 == 0:
                cell.fill = zebra_fill

    for col in range(1, n_cols + 1):
        letter = get_column_letter(col)
        max_len = max(
            (len(str(worksheet.cell(row=r, column=col).value or "")) for r in range(1, worksheet.max_row + 1)),
            default=10,
        )
        worksheet.column_dimensions[letter].width = min(max(max_len + 4, 12), 60)

    worksheet.freeze_panes = "A2"
    worksheet.row_dimensions[1].height = 22
    worksheet.sheet_view.showGridLines = False
    if worksheet.max_row > 1 and n_cols > 0:
        worksheet.auto_filter.ref = f"A1:{get_column_letter(n_cols)}{worksheet.max_row}"

    headers = {str(worksheet.cell(1, col).value): col for col in range(1, n_cols + 1)}
    for header in ("significance", "significant", "status"):
        col = headers.get(header)
        if not col:
            continue
        for row in range(2, worksheet.max_row + 1):
            cell = worksheet.cell(row, col)
            value = str(cell.value or "").lower()
            if value in {"1%", "5%", "true", "violado", "atenção", "atencao"}:
                cell.fill = PatternFill(start_color=HEX["warning_tint"], end_color=HEX["warning_tint"], fill_type="solid")
                cell.font = Font(color=HEX["warning"], bold=True, size=10, name="Calibri")
            elif value in {"false", "ok", "ns"}:
                cell.fill = PatternFill(start_color=HEX["success_tint"], end_color=HEX["success_tint"], fill_type="solid")
                cell.font = Font(color=HEX["success"], bold=True, size=10, name="Calibri")


def build_excel(payload: Dict[str, Any]) -> bytes:
    result = analyze(payload)
    provenance = result.get("provenance") or build_provenance(payload)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        def write_df(name: str, frame: pd.DataFrame) -> None:
            if frame.empty and len(frame.columns) == 0:
                frame = pd.DataFrame({"informacao": []})
            frame.to_excel(writer, index=False, sheet_name=name)
            _style_excel_sheet(writer.sheets[name], max(1, len(frame.columns)))

        write_df("Resumo", pd.DataFrame({"recomendacao": result.get("recommendations", [])}))

        metadata_rows = [
            {"campo": "Versão do motor", "valor": provenance.get("engine_version")},
            {"campo": "Commit", "valor": provenance.get("git_commit")},
            {"campo": "Gerado em UTC", "valor": provenance.get("generated_at_utc")},
            {"campo": "SHA-256 dos dados", "valor": provenance.get("data_sha256")},
            {"campo": "SHA-256 da configuração", "valor": provenance.get("config_sha256")},
        ]
        for key, value in sorted((result.get("meta") or {}).items()):
            metadata_rows.append({"campo": key, "valor": value})
        write_df("Metadados", pd.DataFrame(metadata_rows))

        config_rows = [
            {"campo": key, "valor": json.dumps(value, ensure_ascii=False, default=str)}
            for key, value in sorted((provenance.get("config") or {}).items())
        ]
        write_df("Configuracao", pd.DataFrame(config_rows, columns=["campo", "valor"]))
        write_df("Dados_Entrada", pd.DataFrame(payload.get("data") or []))
        write_df("ANOVA", pd.DataFrame(result.get("anova", {}).get("table", [])))
        write_df("Medias", pd.DataFrame(result.get("means", {}).get("treatment_means", [])))

        comparison = (result.get("means") or {}).get("comparison") or {}
        comparison_rows = []
        for row in comparison.get("comparisons") or []:
            comparison_rows.append({
                "test": comparison.get("test"), "alpha": comparison.get("alpha"),
                "control": comparison.get("control"), **row,
            })
        write_df("Comparacoes", pd.DataFrame(comparison_rows, columns=[
            "test", "alpha", "control", "group_a", "group_b", "diff",
            "critical_diff", "p_value", "significant",
        ]))

        factor_rows = []
        for item in result.get("factor_comparisons") or []:
            for level in item.get("levels") or []:
                factor_rows.append({
                    "factor": item.get("factor"), "test": item.get("test"),
                    "alpha": item.get("alpha"), "error_used": item.get("error_used"), **level,
                })
        write_df("Fatores", pd.DataFrame(factor_rows, columns=[
            "factor", "test", "alpha", "error_used", "treatment", "mean", "n", "group",
        ]))

        interaction_rows = []
        for item in result.get("interaction_breakdown") or []:
            for level in item.get("levels") or []:
                interaction_rows.append({
                    "factor": item.get("factor"), "fixed_level": item.get("level"),
                    "sub_factor": item.get("sub_factor"), "test": item.get("test"),
                    "alpha": item.get("alpha"), **level,
                })
        write_df("Interacao", pd.DataFrame(interaction_rows, columns=[
            "factor", "fixed_level", "sub_factor", "test", "alpha", "treatment", "mean", "n", "group",
        ]))

        assumption_rows = []
        assumption_detail_rows = []
        pressupostos = result.get("pressupostos") or {}
        core_assumption_fields = {"teste", "status", "statistic", "p_value", "n", "mensagem"}
        for key, item in (pressupostos.get("testes") or {}).items():
            assumption_rows.append({
                "pressuposto": key,
                **{field: item.get(field) for field in core_assumption_fields},
            })
            for field, value in item.items():
                if field in core_assumption_fields:
                    continue
                assumption_detail_rows.append({
                    "pressuposto": key,
                    "campo": field,
                    "valor": json.dumps(value, ensure_ascii=False, default=str)
                    if isinstance(value, (dict, list, tuple)) else value,
                })
        write_df("Pressupostos", pd.DataFrame(assumption_rows, columns=[
            "pressuposto", "teste", "status", "statistic", "p_value", "n", "mensagem",
        ]))
        write_df("Pressupostos_Detalhes", pd.DataFrame(assumption_detail_rows, columns=[
            "pressuposto", "campo", "valor",
        ]))

        transform = result.get("transformacao_sugerida")
        write_df("Transformacao", pd.DataFrame([transform] if transform else [], columns=[
            "metodo", "descricao", "aplicado", "mensagem",
        ]))

        regression = result.get("regression") or {}
        regression_rows = []
        for model in regression.get("models") or []:
            lack = model.get("lack_of_fit") or {}
            regression_rows.append({
                "selected": model.get("degree") == regression.get("selected_degree"),
                "degree": model.get("degree"), "equation": model.get("equation"),
                "r2": model.get("r2"), "adj_r2": model.get("adj_r2"),
                "aic": model.get("aic"), "bic": model.get("bic"),
                "p_model": model.get("p_model"), "p_top_term": model.get("p_top_term"),
                "coefficients": json.dumps(model.get("coefficients"), ensure_ascii=False),
                "optimum_x": (model.get("optimum") or {}).get("x"),
                "optimum_y": (model.get("optimum") or {}).get("y"),
                "lack_of_fit_f": lack.get("f_value"), "lack_of_fit_p": lack.get("p_value"),
                "lack_of_fit_significant": lack.get("significant"), "lack_of_fit_note": lack.get("note"),
            })
        write_df("Regressao", pd.DataFrame(regression_rows))

        writer.book.active = 0
    return buffer.getvalue()


# ============================================================================
# GRÁFICOS — matplotlib com tema escuro (idêntico ao site)
# ============================================================================
def _apply_dark_theme(ax) -> None:
    ax.set_facecolor("#0A0A0A")
    ax.figure.patch.set_facecolor("#0A0A0A")
    for spine in ax.spines.values():
        spine.set_color("#262626")
    ax.tick_params(colors="#A3A3A3", which="both")
    ax.xaxis.label.set_color("#A3A3A3")
    ax.yaxis.label.set_color("#A3A3A3")
    ax.title.set_color("#F5F5F5")
    ax.grid(True, color="#1F1F1F", alpha=1.0, linewidth=0.6)


def build_regression_plot(payload: Dict[str, Any], fmt: str = "png") -> bytes:
    """Exporta gráfico de regressão em PNG ou PDF vetorial no tema escuro."""
    result = analyze(payload)
    reg = result.get("regression")
    if not reg:
        raise ValueError("Não há regressão disponível para exportar.")
    points = pd.DataFrame(reg["points"])
    curve = pd.DataFrame(reg["fitted_curve"])
    selected = reg["selected_model"]

    fig, ax = plt.subplots(figsize=(9, 5.2), dpi=200)
    _apply_dark_theme(ax)

    ax.scatter(points["x"], points["y"], label="Observado", color="#22C55E", edgecolor="#0A0A0A", s=55, zorder=3)
    ax.plot(
        curve["x"], curve["y"],
        label=f"Grau {reg['selected_degree']} · R²aj {selected['adj_r2']:.3f}",
        color="#4ADE80", linewidth=2.4, zorder=2,
    )
    ax.fill_between(curve["x"], curve["y"], curve["y"].min(), color="#22C55E", alpha=0.08, zorder=1)

    opt = selected.get("optimum") or {}
    if opt.get("x") is not None:
        ax.axvline(opt["x"], linestyle="--", linewidth=1.1, color="#F5A85B", alpha=0.7)
        ax.scatter([opt["x"]], [opt["y"]], marker="o", s=90, label="Ótimo",
                   color="#F5A85B", edgecolor="#0A0A0A", linewidth=2, zorder=4)

    ax.set_xlabel(reg.get("x_label", "x"))
    ax.set_ylabel(reg.get("y_label", "Resposta"))
    ax.set_title("Regressão Solver", pad=14, fontweight="bold")
    leg = ax.legend(facecolor="#121212", edgecolor="#262626", labelcolor="#F5F5F5", framealpha=1.0)
    for text in leg.get_texts():
        text.set_color("#F5F5F5")

    output = io.BytesIO()
    fig.tight_layout()
    fig.savefig(output, format=fmt, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    return output.getvalue()
