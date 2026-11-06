"""
Formal newsletter PDF for government officials and donors.

Layout (multi-page if needed):
  - Masthead (full-width navy bar, programme bulletin title, period)
  - Introductory rule + issue line
  - Executive Summary section (from Groq)
  - Programme Highlights (bullet list from Groq)
  - Data Highlights (coloured stat boxes)
  - Narrative section (from Groq)
  - KPI data table
  - Forward Look section (from Groq)
  - Footer (CIPRB | UNFPA | AI disclaimer)
"""
from __future__ import annotations

import io
from datetime import date as _date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether,
)
from reportlab.platypus.flowables import Flowable

# ── Brand palette ──────────────────────────────────────────────────────────────
NAVY       = colors.HexColor('#003F72')
BLUE       = colors.HexColor('#0093D0')
LIGHT_BLUE = colors.HexColor('#DDF0FA')
DARK       = colors.HexColor('#172B4D')
GREY       = colors.HexColor('#6B778C')
LIGHT_GREY = colors.HexColor('#F4F5F7')
MID_GREY   = colors.HexColor('#DFE1E6')
GREEN      = colors.HexColor('#00875A')
AMBER      = colors.HexColor('#FF8B00')
WHITE      = colors.white
# ──────────────────────────────────────────────────────────────────────────────

W, H    = A4
MARGIN  = 1.8 * cm


# ── Custom flowable: coloured stat box ───────────────────────────────────────
class StatBox(Flowable):
    """A single coloured KPI stat box for the data highlights row."""

    def __init__(self, value, label, color=BLUE, width=3.5*cm, height=2.2*cm):
        super().__init__()
        self.value  = str(value)
        self.label  = label
        self.color  = color
        self._w     = width
        self._h     = height

    def wrap(self, *_):
        return self._w, self._h

    def draw(self):
        c = self.canv
        # Background
        c.setFillColor(self.color)
        c.roundRect(0, 0, self._w, self._h, 6, fill=1, stroke=0)
        # Value
        c.setFillColor(WHITE)
        c.setFont('Helvetica-Bold', 22)
        c.drawCentredString(self._w / 2, self._h / 2 + 4, self.value)
        # Label
        c.setFont('Helvetica', 7)
        c.drawCentredString(self._w / 2, 8, self.label)


def _styles():
    base = getSampleStyleSheet()

    heading1 = ParagraphStyle(
        'NL_H1',
        parent=base['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        textColor=NAVY,
        spaceBefore=12,
        spaceAfter=4,
    )
    heading2 = ParagraphStyle(
        'NL_H2',
        parent=base['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        textColor=BLUE,
        spaceBefore=10,
        spaceAfter=2,
        borderPad=2,
    )
    body = ParagraphStyle(
        'NL_Body',
        parent=base['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=14,
        textColor=DARK,
        spaceAfter=6,
    )
    bullet = ParagraphStyle(
        'NL_Bullet',
        parent=body,
        leftIndent=16,
        firstLineIndent=-10,
        spaceAfter=4,
    )
    caption = ParagraphStyle(
        'NL_Caption',
        parent=base['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        textColor=GREY,
        spaceAfter=4,
    )
    return {'h1': heading1, 'h2': heading2, 'body': body, 'bullet': bullet, 'caption': caption}


def _parse_newsletter_sections(text: str) -> dict[str, str]:
    """
    Parse the structured Groq newsletter output into sections.
    Expected headings: EXECUTIVE SUMMARY, PROGRAMME HIGHLIGHTS, NARRATIVE, FORWARD LOOK
    """
    known = ['EXECUTIVE SUMMARY', 'PROGRAMME HIGHLIGHTS', 'NARRATIVE', 'FORWARD LOOK']
    sections: dict[str, str] = {}
    current_key = '_intro'
    current_lines: list[str] = []

    for line in text.splitlines():
        stripped = line.strip().upper()
        matched = next((k for k in known if stripped == k), None)
        if matched:
            sections[current_key] = '\n'.join(current_lines).strip()
            current_key = matched
            current_lines = []
        else:
            current_lines.append(line)
    sections[current_key] = '\n'.join(current_lines).strip()

    # Fallback: if no sections parsed, put everything under NARRATIVE
    if all(sections.get(k, '') == '' for k in known):
        sections['NARRATIVE'] = text.strip()

    return sections


def _masthead_onFirstPage(canvas, doc):
    """Draw the masthead on the first page using canvas (called via pageTemplate)."""
    canvas.saveState()
    # Navy masthead bar
    bar_h = 72
    canvas.setFillColor(NAVY)
    canvas.rect(0, H - bar_h, W, bar_h, fill=1, stroke=0)

    # Programme bulletin title
    canvas.setFillColor(WHITE)
    canvas.setFont('Helvetica-Bold', 22)
    canvas.drawString(MARGIN, H - 36, 'PROGRAMME BULLETIN')

    # Right side: org + period (passed via doc._header_info)
    info = getattr(doc, '_header_info', {})
    canvas.setFont('Helvetica', 9)
    canvas.setFillColor(colors.HexColor('#9BB5D0'))
    canvas.drawRightString(W - MARGIN, H - 30, info.get('period_label', ''))
    canvas.drawRightString(W - MARGIN, H - 44, info.get('organisation', ''))

    # Blue subtitle band
    canvas.setFillColor(BLUE)
    canvas.rect(0, H - bar_h - 20, W, 20, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont('Helvetica-Bold', 9)
    canvas.drawString(MARGIN, H - bar_h - 14, 'SIMPLE · CIPRB / UNFPA Bangladesh Reproductive & Child Health Programme')

    # Footer
    info = getattr(doc, '_header_info', {})
    _draw_footer(canvas, narrative_source=info.get('narrative_source', 'template'))
    canvas.restoreState()


def _subsequent_pages(canvas, doc):
    canvas.saveState()
    # Narrow header strip
    canvas.setFillColor(NAVY)
    canvas.rect(0, H - 28, W, 28, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont('Helvetica-Bold', 8)
    canvas.drawString(MARGIN, H - 18, 'SIMPLE · Programme Bulletin')
    info = getattr(doc, '_header_info', {})
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(colors.HexColor('#9BB5D0'))
    canvas.drawRightString(W - MARGIN, H - 18, info.get('period_label', ''))
    _draw_footer(canvas, narrative_source=info.get('narrative_source', 'template'))
    canvas.restoreState()


_PROVENANCE_FOOTER_TEXT = {
    'ai':                    'AI-assisted (figures validated before render)',
    'ai_validation_failed':  'Template content — AI output failed figure validation',
    'ai_api_error':          'Template content — AI service unavailable',
    'ai_disabled':           'Template content — AI disabled by operator',
    'insufficient_data':     'Template content — insufficient data for AI narrative',
    'hand_written_demo':     'Demo content — illustrative only, not from live submissions',
    'template':              'Template content',
}


def _draw_footer(canvas, narrative_source: str = 'template'):
    today = _date.today()
    canvas.setFillColor(DARK)
    canvas.rect(0, 0, W, 36, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont('Helvetica-Bold', 7.5)
    canvas.drawString(MARGIN, 22, 'CIPRB — Centre for Injury Prevention and Research, Bangladesh')
    canvas.setFont('Helvetica', 7.5)
    canvas.drawString(MARGIN, 10, 'In partnership with UNFPA Bangladesh  |  ciprb-simple.org')
    canvas.setFont('Helvetica', 7)
    canvas.setFillColor(colors.HexColor('#9BB5D0'))
    canvas.drawRightString(W - MARGIN, 22, f"Generated: {today.day} {today.strftime('%b %Y')}")
    canvas.drawRightString(
        W - MARGIN, 10,
        _PROVENANCE_FOOTER_TEXT.get(narrative_source, _PROVENANCE_FOOTER_TEXT['template']),
    )


def build_newsletter(
    data: dict | None = None,
    narrative: str = '',
    title: str = '',
    sections: list[dict] | None = None,
    narrative_source: str = 'template',
) -> bytes:
    """
    Build the formal newsletter PDF.

    Args:
        data:      Dict from collect_programme_data() — used for stat boxes and table.
        narrative: Raw Groq newsletter narrative (structured with headings).
        title:     Report title (used if data is None — legacy call).
        sections:  Legacy list of {'heading', 'body'} dicts (kept for backward compat).

    Returns:
        PDF bytes.
    """
    # ── Backward compat: if called the old way ───────────────────────────────
    if data is None:
        data = {}
    if sections and not narrative:
        narrative = '\n\n'.join(
            f"{s.get('heading', '')}\n{s.get('body', '')}" for s in sections
        )

    period_label  = data.get('period_label', title or 'Programme Report')
    organisation  = data.get('organisation', 'All Partners')
    total         = data.get('total_submissions', 0)
    counts        = data.get('counts', {})

    parsed = _parse_newsletter_sections(narrative) if narrative else {}
    S      = _styles()

    buf = io.BytesIO()

    # ── Doc setup: first page has large masthead, subsequent pages have narrow one ──
    first_frame = Frame(
        MARGIN, 1.2*cm,
        W - 2*MARGIN, H - 72 - 20 - 1.2*cm - 0.5*cm,
        id='first',
    )
    other_frame = Frame(
        MARGIN, 1.2*cm,
        W - 2*MARGIN, H - 28 - 1.2*cm - 0.5*cm,
        id='other',
    )

    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=72 + 20 + 0.5*cm, bottomMargin=1.2*cm,
    )
    doc._header_info = {
        'period_label': period_label,
        'organisation': organisation,
        'narrative_source': narrative_source,
    }

    first_template = PageTemplate(
        id='First', frames=[first_frame], onPage=_masthead_onFirstPage,
    )
    other_template = PageTemplate(
        id='Later', frames=[other_frame], onPage=_subsequent_pages,
    )
    doc.addPageTemplates([first_template, other_template])

    # ── Story ────────────────────────────────────────────────────────────────
    story = []

    # Issue line
    story.append(Paragraph(f'<b>{organisation}</b> · {period_label}', S['caption']))
    story.append(HRFlowable(width='100%', thickness=2, color=BLUE, spaceAfter=8))

    # ── Executive Summary ────────────────────────────────────────────────────
    exec_text = parsed.get('EXECUTIVE SUMMARY', '')
    if exec_text:
        story.append(KeepTogether([
            Paragraph('Executive Summary', S['h1']),
            HRFlowable(width='100%', thickness=1, color=LIGHT_BLUE, spaceAfter=6),
            Paragraph(exec_text.replace('\n', ' '), S['body']),
        ]))

    # ── Data Highlights (stat boxes) ─────────────────────────────────────────
    kpi_items = [
        (total,                         'Total Activities',    BLUE),
        (counts.get('clinic_visits', 0),'Clinic Visits',       colors.HexColor('#00875A')),
        (counts.get('outreach_sessions',0), 'Outreach Sessions', colors.HexColor('#FF8B00')),
        (counts.get('gbv_cases', 0),    'GBV Cases Reported',  colors.HexColor('#DE350B')),
    ]
    boxes = [StatBox(v, label, color=c) for v, label, c in kpi_items]
    row_data = []
    for i, box in enumerate(boxes):
        row_data.append(box)
        if i < len(boxes) - 1:
            row_data.append(Spacer(0.25*cm, 1))

    stat_table = Table(
        [row_data],
        colWidths=[3.5*cm, 0.25*cm] * (len(boxes) - 1) + [3.5*cm],
    )
    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph('Data Highlights', S['h1']))
    story.append(HRFlowable(width='100%', thickness=1, color=LIGHT_BLUE, spaceAfter=6))
    story.append(stat_table)
    story.append(Spacer(1, 0.5*cm))

    # ── Programme Highlights (bullets) ───────────────────────────────────────
    highlights_text = parsed.get('PROGRAMME HIGHLIGHTS', '')
    if highlights_text:
        story.append(Paragraph('Programme Highlights', S['h1']))
        story.append(HRFlowable(width='100%', thickness=1, color=LIGHT_BLUE, spaceAfter=6))
        for line in highlights_text.splitlines():
            line = line.strip().lstrip('•-*· ')
            if line:
                story.append(Paragraph(f'• &nbsp; {line}', S['bullet']))
        story.append(Spacer(1, 0.3*cm))

    # ── Narrative ────────────────────────────────────────────────────────────
    narrative_text = parsed.get('NARRATIVE', '')
    if narrative_text:
        story.append(Paragraph('Programme Narrative', S['h1']))
        story.append(HRFlowable(width='100%', thickness=1, color=LIGHT_BLUE, spaceAfter=6))
        for para in narrative_text.split('\n\n'):
            para = para.strip()
            if para:
                story.append(Paragraph(para, S['body']))

    # ── KPI Summary Table ────────────────────────────────────────────────────
    table_rows = [
        ('Activity Type', 'Count'),
        ('Clinic Visits', counts.get('clinic_visits', 0)),
        ('HIV/STI Tests', counts.get('hiv_sti_tests', 0)),
        ('Outreach Sessions', counts.get('outreach_sessions', 0)),
        ('Group Education Sessions', counts.get('group_education', 0)),
        ('Individual Counselling', counts.get('individual_counselling', 0)),
        ('HTC Counselling', counts.get('htc_counselling', 0)),
        ('GBV Cases Reported', counts.get('gbv_cases', 0)),
        ('Referrals Made', counts.get('referrals', 0)),
        ('Antenatal Cards', counts.get('antenatal_cards', 0)),
        ('MH Screenings', counts.get('mh_screenings', 0)),
        ('Training Events', counts.get('training_events', 0)),
        ('Mobile Health Camps', counts.get('mobile_camps', 0)),
        ('Coord. Meetings', counts.get('coord_meetings', 0)),
        ('Hygiene Kits Distributed', counts.get('hygiene_kits', 0)),
        ('ADR Records', counts.get('adr_records', 0)),
        ('Autoclave Logs', counts.get('autoclave_logs', 0)),
    ]

    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph('Activity Summary', S['h1']))
    story.append(HRFlowable(width='100%', thickness=1, color=LIGHT_BLUE, spaceAfter=6))

    tbl = Table(table_rows, colWidths=[12*cm, 3*cm])
    tbl.setStyle(TableStyle([
        # Header row
        ('BACKGROUND',   (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR',    (0, 0), (-1, 0), WHITE),
        ('FONTNAME',     (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',     (0, 0), (-1, 0), 9),
        # Body rows
        ('FONTNAME',     (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE',     (0, 1), (-1, -1), 8.5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, colors.HexColor('#F0F8FF')]),
        ('TEXTCOLOR',    (0, 1), (-1, -1), DARK),
        ('ALIGN',        (1, 0), (1, -1), 'CENTER'),
        # Grid
        ('GRID',         (0, 0), (-1, -1), 0.4, MID_GREY),
        ('TOPPADDING',   (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 5),
        ('LEFTPADDING',  (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(tbl)

    # ── Forward Look ─────────────────────────────────────────────────────────
    forward_text = parsed.get('FORWARD LOOK', '')
    if forward_text:
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph('Forward Look', S['h1']))
        story.append(HRFlowable(width='100%', thickness=1, color=LIGHT_BLUE, spaceAfter=6))
        for para in forward_text.split('\n\n'):
            para = para.strip()
            if para:
                story.append(Paragraph(para, S['body']))

    # ── Closing note ─────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.8*cm))
    story.append(HRFlowable(width='100%', thickness=1, color=MID_GREY))
    story.append(Spacer(1, 0.2*cm))
    closing_note = {
        'ai':                    'Narrative was AI-generated and reviewed by programme staff. All figures cited were validated against source data before distribution.',
        'ai_validation_failed':  'Narrative is template-based for this period because the AI-generated text could not be validated against source data.',
        'ai_api_error':          'Narrative is template-based for this period because the AI service was unavailable at generation time.',
        'ai_disabled':           'Narrative is template-based for this period; AI-assisted generation was disabled.',
        'insufficient_data':     'Narrative is template-based because activity volume for this period was below the threshold for AI summary generation.',
        'hand_written_demo':     'This is a demo bulletin using static evaluation data. It does not reflect live programme submissions.',
        'template':              'Narrative is template-based for this period.',
    }.get(narrative_source, 'Narrative is template-based for this period.')
    story.append(Paragraph(
        f'<i>This bulletin was generated by the Spondon Integrated Data Management System. '
        f'{closing_note} '
        f'For queries, contact CIPRB RCH Department.</i>',
        S['caption'],
    ))

    doc.build(story)
    return buf.getvalue()
