"""
Shared visual tokens + tiny HTML helpers for the report family.

One brand, four faces: the document (editorial A4), the poster (1080x1350
bilingual), the deck (native pptx) and the web report (scrolling, EN/BN)
share these colours and type choices but nothing else — the point of the
2026-08 redesign was that the four pieces stop being one template.
"""
from __future__ import annotations

ORANGE = '#E8562B'
ORANGE_DEEP = '#B23A15'
INK = '#1A242C'
MUTED = '#5C6C78'
FAINT = '#8A97A0'
PAPER = '#FFFFFF'
SOFT = '#F6F4F1'
LINE = '#E3E0DA'
GREEN = '#2E7D54'
AMBER = '#C77F1F'
RED = '#B6392F'

FONT_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Atkinson+Hyperlegible:wght@400;700&'
    'family=Noto+Sans+Bengali:wght@400;600;700&display=swap" rel="stylesheet">'
)
EN_FONT = "'Atkinson Hyperlegible', 'Segoe UI', sans-serif"
BN_FONT = "'Noto Sans Bengali', 'Nirmala UI', 'Atkinson Hyperlegible', sans-serif"


def fmt(n) -> str:
    try:
        return f'{int(n):,}'
    except (TypeError, ValueError):
        return str(n)


def pct_colour(p) -> str:
    if p is None:
        return FAINT
    return GREEN if p >= 75 else AMBER if p >= 40 else RED


def esc(s) -> str:
    return (str(s or '').replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


def bar_rows(rows, accent=ORANGE, label_key='en', max_width=100) -> str:
    """<div> bar list for a block's rows — value-scaled, zero-safe."""
    if not rows:
        return ''
    top = max((r['value'] for r in rows), default=0) or 1
    out = []
    for r in rows:
        w = round(r['value'] / top * max_width, 1)
        out.append(
            f'<div class="br"><span class="brl">{esc(r[label_key])}</span>'
            f'<span class="brt"><i style="width:{w}%;background:{accent}"></i></span>'
            f'<span class="brv">{fmt(r["value"])}</span></div>')
    return ''.join(out)


def spark_path(trend, w=200, h=44, pad=3) -> str:
    """SVG polyline points for a 12-month trend."""
    if not trend or max(trend) == 0:
        return ''
    top = max(trend)
    n = len(trend)
    pts = []
    for i, v in enumerate(trend):
        x = pad + i * (w - 2 * pad) / max(n - 1, 1)
        y = h - pad - (v / top) * (h - 2 * pad)
        pts.append(f'{x:.1f},{y:.1f}')
    return ' '.join(pts)
