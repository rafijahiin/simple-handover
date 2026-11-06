"""
Editorial A4 one-pager / infographic — matches the One-Pager Brief and
Programme Infographic previews.

Layout (top → bottom):
  - Navy → blue header band with coral radial accent
    · "SPONDON IDMS · ONE-PAGER"   "NO. 12"
    · Italic serif "{Period}."     "CIPRB · UNFPA BANGLADESH"
  - Headline number (huge italic) + context + 12-month sparkline
  - 4-up split: PHD · BONDHU · WORKERS · PENDING
  - Top districts leaderboard with bars (replaces the old map)
  - BY CATEGORY breakdown with thin bars and percent
  - Editorial pull-quote between top/bottom rules
  - Light footer: "GENERATED … · M&E TEAM · SIGNED OFF" + Bangla date
"""
from __future__ import annotations

import io
from datetime import date as _date

from reportlab.lib.colors import HexColor, white, Color
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as _canvas

# ── Editorial palette ─────────────────────────────────────────────────────────
NAVY       = HexColor('#002A3D')
UNFPA      = HexColor('#00658C')
UNFPA_BRT  = HexColor('#0091C7')
PAPER      = HexColor('#F7F4EE')
PAPER_2    = HexColor('#EFEBE3')
SURFACE_2  = HexColor('#FAF8F4')
SURFACE_3  = HexColor('#F2EEE7')
INK        = HexColor('#14202B')
INK_2      = HexColor('#2E3D4E')
INK_3      = HexColor('#4C5A6D')
MUTED      = HexColor('#6E7B8E')
MUTED_2    = HexColor('#97A1B0')
HAIR       = HexColor('#E2DED5')
CORAL      = HexColor('#F26A4F')
AMBER      = HexColor('#E9970A')
EMERALD    = HexColor('#1F9A6D')
VIOLET     = HexColor('#8B5CF6')

W, H = A4   # 595.27 × 841.89 pt


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fill(c, color: Color):
    c.setFillColor(color)


def _rect(c, x, y, w, h, color: Color):
    _fill(c, color)
    c.rect(x, y, w, h, fill=1, stroke=0)


def _circle(c, cx, cy, r, color: Color):
    _fill(c, color)
    c.circle(cx, cy, r, fill=1, stroke=0)


def _text(c, x, y, text, *, font='Helvetica', size=10, color=INK):
    c.setFillColor(color)
    c.setFont(font, size)
    c.drawString(x, y, text)


def _text_right(c, x_right, y, text, *, font='Helvetica', size=10, color=INK):
    c.setFillColor(color)
    c.setFont(font, size)
    c.drawRightString(x_right, y, text)


def _text_center(c, cx, y, text, *, font='Helvetica', size=10, color=INK):
    c.setFillColor(color)
    c.setFont(font, size)
    c.drawCentredString(cx, y, text)


def _hairline(c, x1, y, x2, color=HAIR, width=0.5):
    c.setStrokeColor(color)
    c.setLineWidth(width)
    c.line(x1, y, x2, y)


def _kicker(c, x, y, text, *, dot_color=UNFPA, size=8):
    """Mono kicker with leading dot."""
    _circle(c, x + 3, y + size * 0.35, 2, dot_color)
    _text(c, x + 10, y, text, font='Helvetica', size=size, color=MUTED)


def _draw_header_band(c, period_label: str, edition_no: int = 1):
    """Dark navy → unfpa gradient band with coral radial accent."""
    band_h = 130
    band_bottom = H - band_h

    # Background — layered rects to simulate gradient
    _rect(c, 0, band_bottom, W, band_h, UNFPA)
    # Darker overlay top → bottom (5 bands fading from NAVY to UNFPA)
    bands = 6
    for i in range(bands):
        ratio = (bands - i) / bands  # 1.0 at top to ~0 at bottom
        col = Color(
            NAVY.red   * ratio + UNFPA.red   * (1 - ratio),
            NAVY.green * ratio + UNFPA.green * (1 - ratio),
            NAVY.blue  * ratio + UNFPA.blue  * (1 - ratio),
        )
        y = band_bottom + (band_h / bands) * i
        _rect(c, 0, y, W, band_h / bands + 1, col)

    # Coral radial accent (top right) — emulate with several blurred circles
    cx, cy = W - 30, H - 30
    for r, alpha in [(70, 0.55), (50, 0.45), (32, 0.45)]:
        _circle(c, cx, cy, r, Color(CORAL.red, CORAL.green, CORAL.blue, alpha))

    # Top row labels
    _text(c, 32, H - 28,
          'SPONDON IDMS · ONE-PAGER',
          font='Helvetica-Bold', size=8,
          color=Color(1, 1, 1, 0.65))
    _text_right(c, W - 32, H - 28,
                f'NO. {edition_no:02d}',
                font='Helvetica-Bold', size=8,
                color=Color(1, 1, 1, 0.55))

    # Big italic serif title
    _text(c, 32, H - 75,
          f'{period_label}.',
          font='Times-Italic', size=38,
          color=white)
    _text(c, 32, H - 100,
          'CIPRB · UNFPA BANGLADESH',
          font='Helvetica-Bold', size=9,
          color=Color(1, 1, 1, 0.75))


def _draw_headline_number(c, total: int, mom_pct: float, sparkline_data: list[int],
                          period_label: str, y_top: float) -> float:
    """Huge italic number on left, context + sparkline on right. Returns y_bottom."""
    box_h = 130
    y_bottom = y_top - box_h

    # Big italic number
    _text(c, 36, y_top - 100,
          str(total), font='Times-Italic', size=120, color=UNFPA)

    # Right side: kicker + italic context + sparkline
    rx = 200
    _text(c, rx, y_top - 22,
          f'FIELD SUBMISSIONS · {period_label.upper()}',
          font='Helvetica-Bold', size=8, color=MUTED)

    sign = '+' if mom_pct >= 0 else ''
    _text(c, rx, y_top - 45,
          f'{sign}{mom_pct:.1f}% on the previous period.',
          font='Times-Italic', size=14, color=INK_2)

    # Sparkline
    _hairline(c, rx, y_top - 75, W - 36, HAIR, 0.5)
    _text(c, rx, y_top - 90, '12-MONTH TRAJECTORY',
          font='Helvetica-Bold', size=7, color=MUTED)

    spark_x = rx
    spark_y = y_top - 125
    spark_w = W - 36 - rx
    spark_h = 20
    if sparkline_data:
        n = len(sparkline_data)
        mx = max(sparkline_data) or 1
        c.setStrokeColor(UNFPA)
        c.setLineWidth(1.4)
        path = c.beginPath()
        for i, v in enumerate(sparkline_data):
            x = spark_x + (spark_w * i / max(1, n - 1))
            y = spark_y + (v / mx) * spark_h
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        c.drawPath(path, stroke=1, fill=0)

    return y_bottom


def _draw_4up(c, kpis: list[tuple], y_top: float) -> float:
    """4-up grid: (number, label, sub, color). Returns y_bottom."""
    box_h = 78
    gap = 0.5
    col_w = (W - 72 - 3 * gap) / 4
    y_bottom = y_top - box_h

    # Outer border
    c.setStrokeColor(HAIR)
    c.setLineWidth(0.5)
    c.rect(36, y_bottom, W - 72, box_h, fill=0, stroke=1)

    for i, (n, lab, sub, color) in enumerate(kpis):
        x = 36 + i * (col_w + gap)
        # Vertical separators
        if i > 0:
            _hairline(c, x - gap / 2, y_bottom, x - gap / 2, HAIR, 0.5)
            c.line(x - gap / 2, y_bottom, x - gap / 2, y_top)
        # Number
        _text(c, x + 12, y_top - 32,
              str(n), font='Times-Italic', size=26, color=color)
        # Label (uppercase mono)
        _text(c, x + 12, y_top - 50,
              lab, font='Helvetica-Bold', size=7, color=MUTED)
        # Sub
        _text(c, x + 12, y_top - 65,
              sub, font='Helvetica', size=8, color=INK_3)

    return y_bottom


def _draw_districts(c, districts: list[tuple], x: float, y_top: float,
                     width: float, height: float):
    """Top districts leaderboard with bars."""
    # Container
    _rect(c, x, y_top - height, width, height, SURFACE_2)
    c.setStrokeColor(HAIR)
    c.rect(x, y_top - height, width, height, fill=0, stroke=1)

    # Header
    _kicker(c, x + 8, y_top - 16, 'TOP DISTRICTS', dot_color=UNFPA, size=7)

    if not districts:
        return

    max_v = max(d[1] for d in districts) or 1
    row_h = (height - 28) / max(1, len(districts))
    inner_x = x + 12
    inner_w = width - 24

    for i, (name, v) in enumerate(districts[:6]):
        rank_y = y_top - 32 - i * row_h
        pct = v / max_v
        # Rank + name
        _text(c, inner_x, rank_y, f'{i+1:02d}',
              font='Helvetica-Bold', size=7, color=MUTED)
        _text(c, inner_x + 16, rank_y, name,
              font='Helvetica-Bold', size=9, color=INK)
        # Value
        _text_right(c, x + width - 12, rank_y, str(v),
                    font='Times-Italic', size=13, color=UNFPA)
        # Bar
        bar_y = rank_y - 6
        bar_h = 2
        _rect(c, inner_x, bar_y, inner_w, bar_h, SURFACE_3)
        if pct > 0:
            _rect(c, inner_x, bar_y, inner_w * pct, bar_h, UNFPA_BRT)


def _draw_categories(c, cats: list[tuple], x: float, y_top: float,
                     width: float, height: float):
    """BY CATEGORY breakdown with name, count, percent, bar."""
    _kicker(c, x, y_top, 'BY CATEGORY', dot_color=CORAL, size=7)

    total = max(1, sum(v for _, v, _, _ in cats))
    row_h = (height - 16) / max(1, len(cats))
    bar_max_w = width - 70  # leave room for value on the right

    for i, (lab, val, color, sub) in enumerate(cats):
        row_y = y_top - 18 - i * row_h
        pct = (val / total) * 100
        _text(c, x, row_y, lab,
              font='Helvetica-Bold', size=10, color=INK)
        _text(c, x, row_y - 11, sub,
              font='Helvetica', size=7, color=MUTED)
        # Value + pct
        _text_right(c, x + width, row_y, str(val),
                    font='Times-Italic', size=15, color=color)
        _text_right(c, x + width, row_y - 11, f'{pct:.0f}%',
                    font='Helvetica-Bold', size=7, color=MUTED)
        # Bar
        bar_y = row_y - 22
        bar_h = 3
        _rect(c, x, bar_y, bar_max_w, bar_h, SURFACE_3)
        if pct > 0:
            _rect(c, x, bar_y, bar_max_w * (pct / 100), bar_h, color)


def _draw_editorial_quote(c, quote: str, y_top: float) -> float:
    """Pull quote between top/bottom rules."""
    box_h = 56
    y_bottom = y_top - box_h
    # Top + bottom hairlines (heavier — black)
    c.setStrokeColor(INK)
    c.setLineWidth(0.6)
    c.line(36, y_top, W - 36, y_top)
    c.line(36, y_bottom, W - 36, y_bottom)
    # Quote text (italic serif, with simple wrap)
    c.setFillColor(INK)
    c.setFont('Times-Italic', 13)
    # Manual wrap
    max_w = W - 72
    words = quote.split()
    line = ''
    lines = []
    for w in words:
        test = (line + ' ' + w).strip()
        if c.stringWidth(test, 'Times-Italic', 13) > max_w:
            lines.append(line)
            line = w
        else:
            line = test
    if line:
        lines.append(line)
    ty = y_top - 18
    for ln in lines[:2]:
        c.drawString(36, ty, ln)
        ty -= 18
    return y_bottom


def _draw_footer(c, period_label: str, narrative_source: str = 'template'):
    """Light footer band — provenance text reflects how the narrative was produced."""
    foot_h = 40
    _rect(c, 0, 0, W, foot_h, SURFACE_2)
    _hairline(c, 0, foot_h, W, HAIR, 0.5)

    today = _date.today()
    _text(c, 36, 22,
          f'GENERATED {today.day:02d} {today.strftime("%b %Y").upper()} · M&E TEAM',
          font='Helvetica-Bold', size=7, color=MUTED)
    _text(c, 36, 10,
          _footer_provenance_text(narrative_source).upper(),
          font='Helvetica', size=6.5, color=MUTED_2)
    _text_right(c, W - 36, 22,
                period_label,
                font='Helvetica', size=9, color=INK_2)
    _text_right(c, W - 36, 10,
                'SPONDON · v2.4',
                font='Helvetica-Bold', size=7, color=MUTED_2)


# ─── Public API ──────────────────────────────────────────────────────────────

def _footer_provenance_text(narrative_source: str) -> str:
    """Honest footer text that reflects how the narrative was actually produced."""
    return {
        'ai':                    'AI-assisted (figures validated)',
        'ai_validation_failed':  'Template content (AI output failed validation)',
        'ai_api_error':          'Template content (AI service unavailable)',
        'ai_disabled':           'Template content (AI disabled by operator)',
        'insufficient_data':     'Template content (insufficient data for narrative)',
        'hand_written_demo':     'Demo content — illustrative only',
    }.get(narrative_source, 'Template content')


def build_infographic(data: dict, narrative: str = '', narrative_source: str = 'template') -> bytes:
    """
    Build an editorial A4 one-pager / infographic PDF matching the preview.

    Args:
        data:             Output of collect_programme_data() — see one_pager spec.
        narrative:        AI narrative (parsed; first paragraph used as quote).
        narrative_source: Provenance flag — controls the footer text.
    """
    buf = io.BytesIO()
    c = _canvas.Canvas(buf, pagesize=A4)
    c.setTitle('Spondon · One-Pager Brief')

    # Background paper
    _rect(c, 0, 0, W, H, white)

    counts = data.get('counts', {})
    total = data.get('total_submissions', 0)
    period_label = data.get('period_label', 'This period')

    # ─── HEADER BAND ──────────────────────────────────────────────────────────
    _draw_header_band(c, period_label.split(' ')[0] if period_label else 'Period',
                      edition_no=12)

    # ─── HEADLINE NUMBER ──────────────────────────────────────────────────────
    headline_top = H - 145
    sparkline = data.get('monthly_trend') or []
    mom = data.get('mom_pct', 0)
    next_y = _draw_headline_number(c, total, mom, sparkline, period_label, headline_top)

    # ─── 4-UP KPI GRID ────────────────────────────────────────────────────────
    phd_total = (counts.get('clinic_visits', 0) + counts.get('antenatal_cards', 0)
                 + counts.get('mh_screenings', 0))
    bondhu_total = (counts.get('outreach_sessions', 0) + counts.get('individual_counselling', 0)
                    + counts.get('hygiene_kits', 0))
    workers = data.get('active_workers', 0)
    pending = data.get('pending', 0)

    kpis = [
        (phd_total,    'PHD',     'clinical, ANC, MH',   UNFPA),
        (bondhu_total, 'BONDHU',  'outreach, counsel.',  VIOLET),
        (workers,      'WORKERS', 'active in field',     EMERALD),
        (pending,      'PENDING', 'review queue',        CORAL),
    ]
    next_y = _draw_4up(c, kpis, next_y - 16)

    # ─── DISTRICTS + CATEGORIES (2-col) ───────────────────────────────────────
    section_top = next_y - 24
    section_h = 175
    col_gap = 16
    left_w = (W - 72 - col_gap) * 0.52
    right_w = (W - 72 - col_gap) - left_w

    districts = data.get('top_districts') or []
    _draw_districts(c, districts, 36, section_top, left_w, section_h)

    clinical = (counts.get('clinic_visits', 0) + counts.get('hiv_sti_tests', 0)
                + counts.get('antenatal_cards', 0) + counts.get('htc_counselling', 0)
                + counts.get('mh_screenings', 0))
    community = (counts.get('outreach_sessions', 0) + counts.get('individual_counselling', 0)
                 + counts.get('group_education', 0) + counts.get('referrals', 0)
                 + counts.get('hygiene_kits', 0) + counts.get('gbv_cases', 0))
    operations = (counts.get('training_events', 0) + counts.get('coord_meetings', 0)
                  + counts.get('mobile_camps', 0))
    cats = [
        ('Clinical',   clinical,   UNFPA_BRT, 'Clinic visits, ANC, HIV testing'),
        ('Community',  community,  CORAL,     'Outreach, education, counselling'),
        ('Operations', operations, AMBER,     'Training, mobile camps, coord.'),
    ]
    _draw_categories(c, cats, 36 + left_w + col_gap, section_top, right_w, section_h)

    # ─── EDITORIAL QUOTE ──────────────────────────────────────────────────────
    quote_top = section_top - section_h - 20
    quote = ''
    if narrative:
        # First non-empty line that isn't a heading
        for line in narrative.splitlines():
            line = line.strip()
            if line and not line.isupper() and len(line) > 30:
                quote = f'"{line}"'
                break
    if not quote:
        org = data.get('organisation', 'All Partners')
        quote = (f'"This period\'s field submissions for {org} are summarised above, '
                 'drawn live from approved programme data."')
    _draw_editorial_quote(c, quote, quote_top)

    # ─── FOOTER ───────────────────────────────────────────────────────────────
    _draw_footer(c, period_label, narrative_source=narrative_source)

    c.showPage()
    c.save()
    return buf.getvalue()
