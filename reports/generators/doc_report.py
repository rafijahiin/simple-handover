"""
The monthly report DOCUMENT — an editorial A4 PDF, not a dashboard screenshot.

Three pages, each earning its place:
  1  cover: brand, month, the hero figure, a contents strip and the lead of
     the narrative — the old cover was half empty;
  2  the month in numbers: KPI tiles, then each content block as a labelled
     table with in-row bars;
  3  geography, the indicator table (target / achieved / %) and the full
     narrative, with an explicit data-sources note.

English throughout (Rafi, 2026-08-08). Rendered by Chromium print via
html_render.html_to_pdf.
"""
from __future__ import annotations

from .brand import (BN_FONT, EN_FONT, FAINT, FONT_LINK, GREEN, INK, LINE,
                    MUTED, ORANGE, ORANGE_DEEP, PAPER, SOFT, esc, fmt,
                    pct_colour, spark_path)

_CSS = f"""
* {{ margin:0; padding:0; box-sizing:border-box; }}
@page {{ size: A4; margin: 0; }}
body {{ font-family:{EN_FONT}; color:{INK}; background:{PAPER};
        -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
.page {{ width:210mm; height:296mm; padding:16mm 17mm; position:relative;
         page-break-after:always; overflow:hidden; }}
.page:last-child {{ page-break-after:auto; }}
.brand {{ display:flex; align-items:center; gap:7px; }}
.brand b {{ font-size:14px; letter-spacing:3px; }}
.dot {{ width:9px; height:9px; border-radius:50%; background:{ORANGE}; }}
.tag {{ font-size:8.5px; letter-spacing:2.6px; color:{FAINT}; }}
.rule {{ height:2.5px; background:{ORANGE}; margin:9mm 0 0; width:34mm; }}
h1 {{ font-size:40px; line-height:1.05; margin-top:4mm; }}
.bnm {{ font-family:{BN_FONT}; color:{MUTED}; font-size:13px; margin-top:2mm; }}
.scope {{ font-size:12.5px; color:{MUTED}; margin-top:1.5mm; }}
.heroNum {{ font-size:64px; font-weight:700; color:{ORANGE}; letter-spacing:-1px; }}
.heroLbl {{ font-size:13px; color:{INK}; max-width:70mm; line-height:1.35; }}
.heroNote {{ font-size:10.5px; color:{MUTED}; margin-top:1.2mm; }}
.lead {{ border-left:3px solid {ORANGE}; padding:3mm 0 3mm 5mm; margin-top:8mm;
         font-size:11.5px; line-height:1.6; color:{INK}; font-style:italic; }}
.toc {{ margin-top:8mm; border-top:1px solid {LINE}; }}
.toc div {{ display:flex; justify-content:space-between; padding:3mm 0;
            border-bottom:1px solid {LINE}; font-size:11px; }}
.toc span:last-child {{ color:{FAINT}; }}
.cover-kpis {{ display:flex; gap:4mm; margin-top:8mm; }}
.ck {{ flex:1; background:{SOFT}; border-radius:3mm; padding:4mm; }}
.ck b {{ font-size:20px; display:block; }}
.ck span {{ font-size:9px; color:{MUTED}; }}
h2 {{ font-size:20px; margin:0 0 1mm; }}
.sub {{ font-size:10px; letter-spacing:2.2px; color:{ORANGE_DEEP};
        text-transform:uppercase; margin-bottom:2mm; }}
.kgrid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:4mm; margin-top:5mm; }}
.kt {{ border:1px solid {LINE}; border-radius:3mm; padding:4mm 4.5mm; }}
.kt b {{ font-size:24px; display:block; letter-spacing:-0.5px; }}
.kt span {{ font-size:9.5px; color:{MUTED}; }}
.blk {{ margin-top:7mm; }}
.blk h3 {{ font-size:13px; margin-bottom:2.5mm; }}
.br {{ display:flex; align-items:center; gap:3mm; padding:1.7mm 0;
       border-bottom:1px solid {LINE}; }}
.brl {{ width:52mm; font-size:10.5px; }}
.brt {{ flex:1; height:3.2mm; background:{SOFT}; border-radius:2mm; overflow:hidden; }}
.brt i {{ display:block; height:100%; border-radius:2mm; }}
.brv {{ width:16mm; text-align:right; font-size:11px; font-weight:700; }}
table {{ width:100%; border-collapse:collapse; margin-top:3mm; }}
th {{ font-size:8.5px; letter-spacing:1.6px; color:{FAINT}; text-transform:uppercase;
      text-align:left; padding:2mm 2mm; border-bottom:1.5px solid {INK}; }}
td {{ font-size:10.5px; padding:2.4mm 2mm; border-bottom:1px solid {LINE};
      vertical-align:middle; }}
td.num, th.num {{ text-align:right; }}
.pill {{ display:inline-block; min-width:12mm; text-align:center; padding:0.8mm 2mm;
         border-radius:3mm; color:#fff; font-size:9.5px; font-weight:700; }}
.foot {{ position:absolute; left:17mm; right:17mm; bottom:9mm; display:flex;
         justify-content:space-between; font-size:8.5px; color:{FAINT};
         border-top:1px solid {LINE}; padding-top:2.5mm; }}
.nar p {{ font-size:10.8px; line-height:1.65; margin-bottom:3mm; }}
.ai {{ display:inline-block; background:{SOFT}; border-radius:2mm; padding:1mm 2.5mm;
       font-size:8.5px; color:{MUTED}; }}
.spark {{ margin-top:6mm; }}
"""


def _cover(c, ai_summary):
    hero = c['hero']
    toc = [('The month in numbers', '2')]
    toc += [('Programme detail', '2')] if c['blocks'] else []
    toc += [('Geography & indicators', '3'), ('Narrative & sources', '3')]
    toc_html = ''.join(f'<div><span>{esc(a)}</span><span>{b}</span></div>' for a, b in toc)
    kpis = ''.join(
        f'<div class="ck"><b>{fmt(k["value"])}</b><span>{esc(k["en"])}</span></div>'
        for k in c['kpis'][:3])
    lead = (f'<div class="lead">{esc(ai_summary)}</div>' if ai_summary else '')
    spark = ''
    pts = spark_path(c['trend'], w=340, h=52)
    if pts:
        spark = (f'<svg class="spark" width="340" height="52">'
                 f'<polyline points="{pts}" fill="none" stroke="{ORANGE}" '
                 f'stroke-width="2.5" stroke-linejoin="round"/></svg>'
                 f'<div style="font-size:8.5px;color:{FAINT}">12-month trend of '
                 f'approved records</div>')
    return f"""
<div class="page">
  <div style="display:flex;justify-content:space-between;align-items:flex-start">
    <div class="brand"><span class="dot"></span><b>SIMPLE</b></div>
    <div class="tag">MONTHLY PROGRAMME REPORT</div>
  </div>
  <div class="rule"></div>
  <h1>{esc(c['period_label'])}</h1>
  <div class="scope">{esc(c['org_label'])} &nbsp;·&nbsp; Reproductive &amp; Child Health</div>
  <div style="display:flex;align-items:flex-end;gap:8mm;margin-top:11mm">
    <div class="heroNum">{fmt(hero['value'])}</div>
    <div style="padding-bottom:4mm">
      <div class="heroLbl">{esc(hero['en'])}</div>
      <div class="heroNote">{esc(hero['note'])}</div>
    </div>
  </div>
  {lead}
  <div class="cover-kpis">{kpis}</div>
  <div class="toc">{toc_html}</div>
  {spark}
  <div class="foot"><span>SIMPLE — Integrated Digital M&amp;E System · CIPRB / UNFPA Bangladesh</span><span>Page 1</span></div>
</div>"""


def _numbers_page(c):
    kpis = ''.join(
        f'<div class="kt"><b>{fmt(k["value"])}</b><span>{esc(k["en"])}</span></div>'
        for k in c['kpis'])
    blocks = []
    from .brand import bar_rows
    for b in c['blocks']:
        blocks.append(f'<div class="blk"><h3>{esc(b["en"])}</h3>'
                      f'{bar_rows(b["rows"])}</div>')
    partners = ''
    if c.get('partners'):
        rows = []
        for p in c['partners']:
            d = p['data']
            rows.append(
                f'<div class="blk"><h3>{esc(d["org_label"])}</h3>'
                f'<div style="display:flex;gap:4mm">' + ''.join(
                    f'<div class="kt" style="flex:1"><b>{fmt(k["value"])}</b>'
                    f'<span>{esc(k["en"])}</span></div>' for k in d['kpis'][:3])
                + '</div></div>')
        partners = ''.join(rows)
    mom = ''
    if c.get('mom_pct') is not None:
        up = c['mom_pct'] >= 0
        mom = (f'<span class="ai" style="color:{GREEN if up else ORANGE_DEEP}">'
               f'{"▲" if up else "▼"} {abs(c["mom_pct"])}% vs previous month</span>')
    return f"""
<div class="page">
  <div class="sub">The month in numbers</div>
  <h2>{esc(c['org_label'])} — {esc(c['period_label'])} {mom}</h2>
  <div class="kgrid">{kpis}</div>
  {''.join(blocks)}{partners}
  <div class="foot"><span>Figures are approved submissions only, as shown on the live dashboard</span><span>Page 2</span></div>
</div>"""


def _detail_page(c, paras, meta_line):
    geo = ''
    if c['geo']['rows']:
        from .brand import bar_rows
        rows = [{'en': n, 'value': v} for n, v in c['geo']['rows']]
        cov = (f'<div style="font-size:9.5px;color:{MUTED};margin-top:2mm">'
               f'{esc(c["geo"]["coverage"])}</div>' if c['geo']['coverage'] else '')
        geo = (f'<div class="blk"><div class="sub">Where</div>'
               f'<h2 style="font-size:15px">{esc(c["geo"]["en"])}</h2>'
               f'{bar_rows(rows)}{cov}</div>')
    ind = ''
    if c['indicators']:
        trs = []
        for r in c['indicators']:
            pc = pct_colour(r['pct'])
            pill = (f'<span class="pill" style="background:{pc}">{r["pct"]:.0f}%</span>'
                    if r['pct'] is not None else
                    f'<span style="color:{FAINT};font-size:9.5px">no target</span>')
            tgt = fmt(r['target']) if r['target'] is not None else '—'
            trs.append(f'<tr><td style="width:10mm;color:{FAINT}">{esc(r["code"])}</td>'
                       f'<td>{esc(r["label"])[:78]}</td>'
                       f'<td class="num">{tgt}</td>'
                       f'<td class="num"><b>{fmt(r["achieved"])}</b></td>'
                       f'<td class="num">{pill}</td></tr>')
        ind = (f'<div class="blk"><div class="sub">Against the M&amp;E framework</div>'
               f'<h2 style="font-size:15px">Indicator progress</h2>'
               f'<table><tr><th>Code</th><th>Indicator</th><th class="num">Target</th>'
               f'<th class="num">Achieved</th><th class="num">Progress</th></tr>'
               f'{"".join(trs)}</table></div>')
    nar = ''
    if paras:
        body = ''.join(f'<p>{esc(p)}</p>' for p in paras[:4])
        nar = (f'<div class="blk nar"><div class="sub">Narrative</div>{body}'
               f'<span class="ai">✦ {esc(meta_line)}</span></div>')
    return f"""
<div class="page">
  {geo}{ind}{nar}
  <div class="blk" style="font-size:9px;color:{FAINT};line-height:1.6">
    Sources: approved KoboToolbox submissions in SIMPLE. PHD figures from the
    FSW service forms; Bandhu figures from the F-01 wellness logbook (the single
    counted source); CIPRB figures from MPDSR notifications, death reviews, the
    response-action tracker and the fistula case registry. Indicator targets from
    the UNFPA M&amp;E framework. Percentages are omitted where a target is unset
    or last month is not comparable.
  </div>
  <div class="foot"><span>simpledashboard.pro · generated automatically from live data</span><span>Page 3</span></div>
</div>"""


def build_document_html(content: dict, paras: list[str], ai_summary: str,
                        meta_line: str) -> str:
    return (f'<!doctype html><html><head><meta charset="utf-8">{FONT_LINK}'
            f'<style>{_CSS}</style></head><body>'
            f'{_cover(content, ai_summary)}'
            f'{_numbers_page(content)}'
            f'{_detail_page(content, paras, meta_line)}'
            f'</body></html>')


def render_document_pdf(content, paras, ai_summary, meta_line, browser=None) -> bytes:
    from .html_render import html_to_pdf
    html = build_document_html(content, paras, ai_summary, meta_line)
    return html_to_pdf(html, browser=browser, prefer_css_page_size=True,
                       print_background=True)
