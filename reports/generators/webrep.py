"""
The shareable WEB report — a scrolling page, not a printed layout.

Served publicly at /r/<token>/, so it must be a single self-contained HTML
string: inline CSS/JS, webfonts as the only external fetch, no framework.
English only (Rafi, 2026-08-08). Counters rise once on scroll into view;
sections appear with a soft translate. Degrades to plain static text when
JS is off, and respects prefers-reduced-motion.
"""
from __future__ import annotations

import json

from .brand import (BN_FONT, EN_FONT, FAINT, GREEN, INK, LINE, MUTED, ORANGE,
                    ORANGE_DEEP, PAPER, SOFT, esc, fmt, pct_colour, spark_path)

_FONT = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link href="https://fonts.googleapis.com/css2?'
         'family=Atkinson+Hyperlegible:wght@400;700&'
         'family=Noto+Sans+Bengali:wght@400;600;700&display=swap" rel="stylesheet">')

_CSS = f"""
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:{EN_FONT}; background:{PAPER}; color:{INK}; }}
.wrap {{ max-width:760px; margin:0 auto; padding:0 22px 70px; }}
header {{ position:sticky; top:0; background:{PAPER}ee; backdrop-filter:blur(6px);
          border-bottom:1px solid {LINE}; z-index:5; }}
.hin {{ max-width:760px; margin:0 auto; padding:13px 22px; display:flex;
        justify-content:space-between; align-items:center; }}
.brand {{ display:flex; gap:8px; align-items:center; font-weight:700;
          letter-spacing:3px; font-size:14px; }}
.dot {{ width:10px; height:10px; border-radius:50%; background:{ORANGE}; }}
.eyebrow {{ margin-top:46px; font-size:11px; letter-spacing:3px; color:{ORANGE_DEEP};
            text-transform:uppercase; }}
h1 {{ font-size:clamp(34px,7vw,52px); line-height:1.1; margin-top:8px; }}
.scope {{ color:{MUTED}; margin-top:8px; font-size:15px; }}
.hero {{ display:flex; align-items:flex-end; gap:26px; flex-wrap:wrap; margin-top:34px; }}
.heroNum {{ font-size:clamp(64px,14vw,110px); font-weight:700; color:{ORANGE};
            letter-spacing:-3px; line-height:0.95; }}
.heroLbl {{ max-width:300px; padding-bottom:10px; font-size:16px; line-height:1.4; }}
.heroNote {{ color:{MUTED}; font-size:13px; margin-top:5px; }}
.lead {{ border-left:3px solid {ORANGE}; padding:4px 0 4px 16px; margin-top:26px;
         font-style:italic; color:{INK}; line-height:1.65; font-size:15px; }}
section {{ margin-top:56px; opacity:0; transform:translateY(16px);
           transition:opacity .5s ease, transform .5s ease; }}
section.in {{ opacity:1; transform:none; }}
@media (prefers-reduced-motion: reduce) {{ section {{ opacity:1; transform:none; }} }}
h2 {{ font-size:22px; margin-bottom:4px; }}
.sub {{ font-size:11px; letter-spacing:2.6px; color:{FAINT}; text-transform:uppercase; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr));
         gap:14px; margin-top:18px; }}
.card {{ background:{SOFT}; border-radius:14px; padding:18px 20px; }}
.card b {{ font-size:30px; display:block; letter-spacing:-0.5px; }}
.card span {{ font-size:13px; color:{MUTED}; }}
.br {{ display:flex; align-items:center; gap:14px; padding:9px 0;
       border-bottom:1px solid {LINE}; }}
.brl {{ width:42%; font-size:14.5px; }}
.brt {{ flex:1; height:10px; background:{SOFT}; border-radius:5px; overflow:hidden; }}
.brt i {{ display:block; height:100%; border-radius:5px; width:0;
          background:linear-gradient(90deg,{ORANGE},{ORANGE_DEEP});
          transition:width .8s cubic-bezier(.2,.8,.2,1); }}
section.in .brt i {{ width:var(--w); }}
@media (prefers-reduced-motion: reduce) {{ .brt i {{ width:var(--w); }} }}
.brv {{ width:70px; text-align:right; font-weight:700; font-size:16px; }}
table {{ width:100%; border-collapse:collapse; margin-top:16px; }}
th {{ text-align:left; font-size:10.5px; letter-spacing:1.6px; color:{FAINT};
      text-transform:uppercase; padding:8px 6px; border-bottom:2px solid {INK}; }}
td {{ padding:10px 6px; border-bottom:1px solid {LINE}; font-size:14px; }}
.num {{ text-align:right; }}
.pill {{ display:inline-block; min-width:52px; text-align:center; padding:3px 8px;
         border-radius:12px; color:#fff; font-size:12px; font-weight:700; }}
.cov {{ margin-top:12px; color:{MUTED}; font-size:14px; }}
.ai {{ display:inline-block; background:{SOFT}; border-radius:8px; padding:5px 10px;
       font-size:12px; color:{MUTED}; margin-top:10px; }}
footer {{ margin-top:64px; border-top:1px solid {LINE}; padding-top:16px;
          font-size:12px; color:{FAINT}; display:flex; justify-content:space-between;
          flex-wrap:wrap; gap:6px; }}
.nar p {{ line-height:1.7; margin-bottom:14px; font-size:15px; }}
"""


def _t(en, bn=None):
    """Historically a bilingual node; the report is English-only now, but the
    call sites keep their second argument so the strings stay paired in code
    if the decision is ever reversed."""
    return esc(en)


def build_web_report(c: dict, paras: list[str], ai_summary: str,
                     meta_line: str) -> str:
    hero = c['hero']

    kpis = ''.join(
        f'<div class="card"><b class="cnt" data-v="{k["value"]}">{fmt(k["value"])}</b>'
        f'<span>{_t(k["en"], k["bn"])}</span></div>'
        for k in c['kpis'])

    blocks = []
    for b in c['blocks']:
        rows = b['rows']
        top = max((r['value'] for r in rows), default=0) or 1
        brs = ''.join(
            f'<div class="br"><span class="brl">{_t(r["en"], r["bn"])}</span>'
            f'<span class="brt"><i style="--w:{round(r["value"]/top*100,1)}%"></i></span>'
            f'<span class="brv">{fmt(r["value"])}</span></div>'
            for r in rows)
        blocks.append(f'<section><div class="sub">{_t("Programme detail", "কর্মসূচির বিস্তারিত")}</div>'
                      f'<h2>{_t(b["en"], b["bn"])}</h2>{brs}</section>')

    partners = ''
    if c.get('partners'):
        cards = []
        for p in c['partners']:
            d = p['data']
            cards.append(
                f'<div class="card" style="border-top:4px solid {p["accent"]}">'
                f'<b class="cnt" data-v="{d["hero"]["value"]}">{fmt(d["hero"]["value"])}</b>'
                f'<span><b style="font-size:13px;display:block">{esc(d["org_label"])}</b>'
                f'{_t(d["hero"]["en"], d["hero"]["bn"])}</span></div>')
        partners = (f'<section><div class="sub">{_t("By partner", "পার্টনার অনুযায়ী")}</div>'
                    f'<h2>{_t("Three partners, one programme", "তিন পার্টনার, এক কর্মসূচি")}</h2>'
                    f'<div class="grid">{"".join(cards)}</div></section>')

    geo = ''
    if c['geo']['rows']:
        top = max((v for _, v in c['geo']['rows']), default=0) or 1
        brs = ''.join(
            f'<div class="br"><span class="brl">{esc(n)}</span>'
            f'<span class="brt"><i style="--w:{round(v/top*100,1)}%"></i></span>'
            f'<span class="brv">{fmt(v)}</span></div>'
            for n, v in c['geo']['rows'])
        cov = (f'<div class="cov">{esc(c["geo"]["coverage"])}</div>'
               if c['geo']['coverage'] else '')
        geo = (f'<section><div class="sub">{_t("Where", "কোথায়")}</div>'
               f'<h2>{_t(c["geo"]["en"], c["geo"]["bn"])}</h2>{brs}{cov}</section>')

    ind = ''
    if c['indicators']:
        trs = []
        for r in c['indicators']:
            pill = (f'<span class="pill" style="background:{pct_colour(r["pct"])}">'
                    f'{r["pct"]:.0f}%</span>' if r['pct'] is not None else
                    f'<span style="color:{FAINT};font-size:12px">{_t("no target","লক্ষ্য নেই")}</span>')
            tgt = fmt(r['target']) if r['target'] is not None else '—'
            trs.append(f'<tr><td style="color:{FAINT}">{esc(r["code"])}</td>'
                       f'<td>{esc(r["label"])[:80]}</td><td class="num">{tgt}</td>'
                       f'<td class="num"><b>{fmt(r["achieved"])}</b></td>'
                       f'<td class="num">{pill}</td></tr>')
        ind = (f'<section><div class="sub">{_t("Against the M&E framework", "এমঅ্যান্ডই ফ্রেমওয়ার্ক অনুযায়ী")}</div>'
               f'<h2>{_t("Indicator progress", "সূচকের অগ্রগতি")}</h2>'
               f'<table><tr><th>{_t("Code","কোড")}</th><th>{_t("Indicator","সূচক")}</th>'
               f'<th class="num">{_t("Target","লক্ষ্য")}</th>'
               f'<th class="num">{_t("Achieved","অর্জন")}</th>'
               f'<th class="num">{_t("Progress","অগ্রগতি")}</th></tr>{"".join(trs)}</table></section>')

    nar = ''
    if paras:
        body = ''.join(f'<p>{esc(p)}</p>' for p in paras[:4])
        nar = (f'<section class="nar"><div class="sub">{_t("Narrative", "বিবরণ")}</div>'
               f'{body}<span class="ai">✦ {esc(meta_line)}</span></section>')

    pts = spark_path(c['trend'], w=300, h=54)
    spark = (f'<svg width="300" height="54" style="margin-top:20px">'
             f'<polyline points="{pts}" fill="none" stroke="{ORANGE}" '
             f'stroke-width="3" stroke-linejoin="round"/></svg>') if pts else ''

    mom = ''
    if c.get('mom_pct') is not None:
        up = c['mom_pct'] >= 0
        mom = (f'<span class="ai" style="color:{GREEN if up else ORANGE_DEEP}">'
               f'{"▲" if up else "▼"} {abs(c["mom_pct"])}% '
               f'{_t("vs previous month", "আগের মাসের তুলনায়")}</span>')

    lead = f'<div class="lead">{esc(ai_summary)}</div>' if ai_summary else ''

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{esc(c['org_label'])} — {esc(c['period_label'])}</title>
{_FONT}<style>{_CSS}</style></head><body>
<header><div class="hin">
  <div class="brand"><span class="dot"></span>SIMPLE</div>
</div></header>
<div class="wrap">
  <div class="eyebrow">{_t("Monthly programme report", "মাসিক কর্মসূচি প্রতিবেদন")}</div>
  <h1>{esc(c['period_label'])}</h1>
  <div class="scope">{esc(c['org_label'])} · {_t("Reproductive & Child Health", "প্রজনন ও শিশু স্বাস্থ্য")}</div>
  <div class="hero">
    <div class="heroNum cnt" data-v="{hero['value']}">{fmt(hero['value'])}</div>
    <div class="heroLbl">{_t(hero['en'], hero['bn'])}
      <div class="heroNote">{esc(hero['note'])} {mom}</div>{spark}</div>
  </div>
  {lead}
  <section><div class="sub">{_t("At a glance", "এক নজরে")}</div>
    <h2>{_t("The month in numbers", "সংখ্যায় এই মাস")}</h2>
    <div class="grid">{kpis}</div></section>
  {partners}{''.join(blocks)}{geo}{ind}{nar}
  <footer>
    <span>{_t("SIMPLE — Integrated Digital M&E System", "সিম্পল — সমন্বিত ডিজিটাল এমঅ্যান্ডই সিস্টেম")}</span>
    <span>CIPRB · UNFPA Bangladesh</span>
  </footer>
</div>
<script>
(function () {{
  var re = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var io = ('IntersectionObserver' in window) && !re
    ? new IntersectionObserver(function (es) {{
        es.forEach(function (e) {{
          if (e.isIntersecting) {{ e.target.classList.add('in'); io.unobserve(e.target); }}
        }});
      }}, {{ threshold: 0.15 }})
    : null;
  var secs = document.querySelectorAll('section');
  for (var i = 0; i < secs.length; i++)
    io ? io.observe(secs[i]) : secs[i].classList.add('in');

  if (!re) {{
    var cs = document.querySelectorAll('.cnt');
    var seen = new WeakSet();
    var cio = ('IntersectionObserver' in window)
      ? new IntersectionObserver(function (es) {{
          es.forEach(function (e) {{
            if (!e.isIntersecting || seen.has(e.target)) return;
            seen.add(e.target);
            var el = e.target, v = parseInt(el.getAttribute('data-v') || '0', 10);
            var t0 = null;
            function step(ts) {{
              if (!t0) t0 = ts;
              var k = Math.min(1, (ts - t0) / 900);
              k = 1 - Math.pow(1 - k, 3);
              el.textContent = Math.round(v * k).toLocaleString('en-US');
              if (k < 1) requestAnimationFrame(step);
            }}
            requestAnimationFrame(step);
          }});
        }}, {{ threshold: 0.4 }})
      : null;
    if (cio) for (var j = 0; j < cs.length; j++) cio.observe(cs[j]);
  }}
}})();
</script></body></html>"""
