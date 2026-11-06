# -*- coding: utf-8 -*-
"""Partner-coverage print sheets for the SIMPLE dashboard.

Same house style and boundary file as make_donor_maps.py. Three sheets:

  PHD      9 wellness-centre districts, one centre each
  Bandhu   8 working districts
  SIMPLE   all three partners on one map, overlaps in their own colour

District names are NOT stamped on the districts. On a crowded map a centroid
label slides off a concave or tiny district and collides with its neighbours.
Instead every supported district is tied by a thin leader to a name in a side
gutter: west districts to the left column, east to the right, each column
sorted north to south so leaders do not cross. A coloured dot on the district
repeats its class, so the gutter list reads as a legend of its own. This
guarantees no overlap however dense the map gets.

Writes a 150-dpi PNG into frontend/public/maps (served on the dashboard) and a
300-dpi PDF + PNG into the Desktop deliverable folder, from one run.
"""
import json
import math
import os
import re

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon as MplPolygon, Rectangle
from shapely.geometry import LineString, Polygon

GEOJSON = r'C:\Users\HP\Documents\spondon_clone\frontend\public\bangladesh-adm2.geojson'
DESK = r'C:\Users\HP\Desktop\SIMPLE_Dashboard_Maps'
WORK = os.path.join(DESK, '_work')
PRINT_DPI = 300
DATED = '11 October 2026'

FONT = 'Atkinson Hyperlegible'
plt.rcParams['font.family'] = FONT
plt.rcParams['pdf.fonttype'] = 42

INK, ASH, HAIR = '#131619', '#686a6c', '#a8aeb4'
SEA, LAND = '#eef3f7', '#ece9e4'
BORDER, BORDER_LW = '#6f777e', 0.85
EDGE, EDGE_LW = '#26292c', 1.30
LEADER = '#8b9096'

TINT = {
    'CIPRB':          '#649BF2',
    'Bandhu':         '#4E9A86',
    'PHD':            '#F96000',
    'CIPRB + Bandhu': '#16697A',
    'CIPRB + PHD':    '#B23A1E',
}

CIPRB = ['Sunamganj', 'Sherpur', 'Bhola', 'Kurigram', 'Gaibandha', 'Khagrachari',
         'Noakhali', 'Patuakhali', 'Sirajganj', 'Barguna', 'Jamalpur', 'Bagerhat',
         'Habiganj', 'Moulavibazar', 'Sylhet', 'Bandarban', 'Chandpur', 'Rangpur', 'Dhaka']
BANDHU = ['Sunamganj', 'Habiganj', 'Manikganj', 'Narayanganj', 'Chattogram',
          'Bandarban', 'Chandpur', 'Noakhali']
PHD = ['Rajbari', 'Jessore', 'Bagerhat', 'Patuakhali', 'Faridpur', 'Mymensingh',
       'Jamalpur', 'Tangail', 'Khulna']


def partner_class(d):
    return ' + '.join(p for p, lst in (('CIPRB', CIPRB), ('Bandhu', BANDHU), ('PHD', PHD)) if d in lst)


ALL = {d: partner_class(d) for d in set(CIPRB) | set(BANDHU) | set(PHD)}

SHEETS = {
    'PHD': {
        'title': 'PHD wellness-centre districts',
        'subtitle': 'SIDA-funded brothel-based wellness centres, one centre per district',
        'file': 'PHD_coverage',
        'classes': {d: 'PHD' for d in PHD},
        'legend': [('PHD', len(PHD))],
    },
    'Bandhu': {
        'title': 'Bandhu working districts',
        'subtitle': 'Bandhu Social Welfare Society service districts',
        'file': 'Bandhu_coverage',
        'classes': {d: 'Bandhu' for d in BANDHU},
        'legend': [('Bandhu', len(BANDHU))],
    },
    'SIMPLE': {
        'title': 'SIMPLE partner coverage',
        'subtitle': 'CIPRB, Bandhu and PHD districts on one map; a district worked by two partners is shown in its own colour',
        'file': 'SIMPLE_all_partners',
        'classes': ALL,
        'legend': [(c, sum(1 for v in ALL.values() if v == c))
                   for c in ('CIPRB', 'Bandhu', 'PHD', 'CIPRB + Bandhu', 'CIPRB + PHD')],
    },
}

ALIASES = {'khagrachari': 'khagrachhari', 'moulavibazar': 'maulvibazar',
           'chattogram': 'chittagong', 'cumilla': 'comilla', 'bogura': 'bogra',
           'jashore': 'jessore', 'barishal': 'barisal'}


def key(name):
    k = re.sub(r'[^a-z]', '', str(name).lower())
    return ALIASES.get(k, k)


def rings(geom):
    if geom['type'] == 'Polygon':
        return [geom['coordinates'][0]]
    if geom['type'] == 'MultiPolygon':
        return [poly[0] for poly in geom['coordinates']]
    return []


def biggest_ring(feat):
    best, best_area = None, 0.0
    for ring in rings(feat['geometry']):
        xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
        area = (max(xs) - min(xs)) * (max(ys) - min(ys))
        if area > best_area:
            best, best_area = ring, area
    return best


def anchor_point(feat):
    """A point guaranteed inside the district, for the leader dot."""
    ring = biggest_ring(feat)
    try:
        p = Polygon(ring).representative_point()
        return (p.x, p.y)
    except Exception:
        return (sum(q[0] for q in ring) / len(ring), sum(q[1] for q in ring) / len(ring))


def thinned(ring, tol):
    if len(ring) < 5:
        return ring
    return list(LineString(ring).simplify(tol).coords)


def draw_map(ax, spec, geo):
    """Fills, boundaries, supported outlines, frame, north arrow, scale bar.

    Returns the list of (name, (lon, lat), class) for the gutter labeller.
    """
    classes = {key(d): c for d, c in spec['classes'].items()}
    pretty = {key(d): d for d in spec['classes']}
    seen, anchors, shaded_rings = set(), [], []
    ax.set_facecolor(SEA)

    for feat in geo['features']:
        name = feat['properties'].get('shapeName', '')
        cls = classes.get(key(name))
        shaded = cls is not None
        if shaded:
            seen.add(key(name))
        for ring in rings(feat['geometry']):
            ax.add_patch(MplPolygon(ring, closed=True, edgecolor='none',
                                    facecolor=TINT[cls] if shaded else LAND, zorder=2))
            ax.plot(*zip(*thinned(ring, 0.004)), color=BORDER, linewidth=BORDER_LW,
                    solid_joinstyle='round', zorder=3)
            if shaded:
                shaded_rings.append(ring)
        if shaded:
            anchors.append((pretty[key(name)], anchor_point(feat), cls))

    for ring in shaded_rings:
        bx = [p[0] for p in ring]; by = [p[1] for p in ring]
        if (max(bx) - min(bx)) * (max(by) - min(by)) < 0.0012:
            continue
        ax.plot(*zip(*thinned(ring, 0.009)), color=EDGE, linewidth=EDGE_LW,
                solid_joinstyle='round', zorder=4)

    missing = set(classes) - seen
    if missing:
        raise SystemExit(f'{spec["title"]}: not on the map file: {missing}')

    xs = [p[0] for f in geo['features'] for r in rings(f['geometry']) for p in r]
    ys = [p[1] for f in geo['features'] for r in rings(f['geometry']) for p in r]
    ax.set_xlim(min(xs) - 0.12, max(xs) + 0.12)
    ax.set_ylim(min(ys) - 0.12, max(ys) + 0.12)
    ax.set_aspect(1 / math.cos(math.radians(23.7)))
    ax.set_xticks([]); ax.set_yticks([])
    for side in ax.spines.values():
        side.set_edgecolor(HAIR); side.set_linewidth(1.0)

    ax.annotate('N', xy=(0.955, 0.94), xytext=(0.955, 0.885),
                xycoords='axes fraction', textcoords='axes fraction',
                ha='center', va='center', fontsize=9.5, fontweight='bold', color=INK,
                arrowprops=dict(arrowstyle='-|>', color=INK, linewidth=1.1))

    km_per_deg = 111.32 * math.cos(math.radians(23.7))
    bar = 100 / km_per_deg
    x0, y0 = max(xs) - 0.05 - bar, min(ys) + 0.22
    for i in range(2):
        ax.add_patch(Rectangle((x0 + i * bar / 2, y0), bar / 2, 0.055,
                               facecolor=INK if i == 0 else 'white',
                               edgecolor=INK, linewidth=0.7, zorder=9))
    for frac, lab in ((0, '0'), (0.5, '50'), (1, '100 km')):
        ax.text(x0 + bar * frac, y0 - 0.1, lab, ha='center', va='top',
                fontsize=7, color=ASH, zorder=9)
    return anchors


def gutter_labels(fig, ax, anchors, *, size=8.4):
    """Tie every district to a name in a side gutter by a leader line.

    West districts go left, east go right, each column sorted north to south
    so the leaders fan out without crossing. The name never sits on the map,
    so nothing can slide off or collide.
    """
    inv = fig.transFigure.inverted()

    def to_fig(xy):
        return inv.transform(ax.transData.transform(xy))

    box = ax.get_position()
    xmid = box.x0 + box.width / 2
    ytop, ybot = box.y0 + box.height - 0.015, box.y0 + 0.02

    pts = [(name, to_fig(xy), cls) for name, xy, cls in anchors]
    left = sorted([p for p in pts if p[1][0] < xmid], key=lambda p: -p[1][1])
    right = sorted([p for p in pts if p[1][0] >= xmid], key=lambda p: -p[1][1])

    def column(items, text_x, lead_x, align):
        n = len(items)
        if not n:
            return
        ys = ([(ytop + ybot) / 2] if n == 1
              else [ytop - (ytop - ybot) * i / (n - 1) for i in range(n)])
        for (name, (fx, fy), cls), gy in zip(items, ys):
            fig.add_artist(Line2D([fx, lead_x], [fy, gy], color=LEADER, linewidth=0.55,
                                  zorder=5, transform=fig.transFigure, alpha=0.9))
            fig.add_artist(Line2D([fx], [fy], marker='o', markersize=3.0,
                                  markerfacecolor=TINT.get(cls, '#555'),
                                  markeredgecolor='white', markeredgewidth=0.5,
                                  zorder=6, transform=fig.transFigure))
            fig.text(text_x, gy, name, fontsize=size, color=INK, va='center', ha=align,
                     zorder=7)

    column(left, text_x=box.x0 - 0.035, lead_x=box.x0 - 0.028, align='right')
    column(right, text_x=box.x0 + box.width + 0.035, lead_x=box.x0 + box.width + 0.028, align='left')


def draw_legend(fig, rows, *, y, x0=0.06, x1=0.955, size=9.2):
    width_in = fig.get_size_inches()[0]
    sw, pad, gap = 0.26, 0.11, 0.34
    char = 0.56 * size / 72
    rows2 = list(rows) + [('Not covered', None)]
    texts = [f'{lab}  ({n})' if n is not None else lab for lab, n in rows2]
    widths = [sw + pad + char * len(t) for t in texts]
    avail = (x1 - x0) * width_in
    span = sum(widths) + gap * (len(rows2) - 1)
    if span > avail:
        k = avail / span
        size, sw, pad, gap = size * k, sw * k, pad * k, gap * k
        widths = [w * k for w in widths]; span = avail
    x = (x0 * width_in) + (avail - span) / 2
    for (label, _), text, w in zip(rows2, texts, widths):
        fig.patches.append(Rectangle((x / width_in, y - 0.006), sw / width_in, 0.013,
                                     transform=fig.transFigure, figure=fig,
                                     facecolor=TINT.get(label, LAND),
                                     edgecolor='#00000022', linewidth=0.6))
        fig.text((x + sw + pad) / width_in, y, text, fontsize=size, color=INK, va='center')
        x += w + gap


def page(spec, geo):
    fig = plt.figure(figsize=(8.27, 11.69))     # A4 portrait
    fig.patch.set_facecolor('white')
    # Narrower map, centred, leaving a gutter each side for the name columns.
    ax = fig.add_axes([0.235, 0.11, 0.53, 0.75])
    anchors = draw_map(ax, spec, geo)
    gutter_labels(fig, ax, anchors)
    draw_legend(fig, spec['legend'], y=0.068)

    fig.text(0.06, 0.945, spec['title'], fontsize=21, fontweight='bold', color=INK)
    fig.text(0.06, 0.925, spec['subtitle'], fontsize=10.2, color=ASH)
    fig.add_artist(plt.Line2D([0.06, 0.94], [0.912, 0.912], color='#F96000',
                              linewidth=1.6, transform=fig.transFigure))
    n = len(spec['classes'])
    fig.text(0.06, 0.886, f'{n} districts', fontsize=10, color=INK, fontweight='bold')
    fig.text(0.94, 0.886, f'SIMPLE dashboard  ·  {DATED}', fontsize=9, color=ASH, ha='right')
    fig.text(0.06, 0.022, 'Boundaries: Bangladesh district boundaries (ADM2). '
             'Each name is tied by a leader to its district; a two-partner district is shown in its own colour.',
             fontsize=8, color=ASH)

    out = []
    # Desktop pack only. The partner coverage maps are NOT served on the
    # dashboard (Home, PHD and Bandhu use the interactive Leaflet map); only
    # the CIPRB donor sheets go into frontend/public/maps. So this writes the
    # print PDF and a raster into the Desktop folder and nothing into the app.
    fig.savefig(os.path.join(WORK, f'{spec["file"]}.png'), dpi=PRINT_DPI, facecolor='white')
    pdf = os.path.join(DESK, f'{spec["file"]}.pdf')
    fig.savefig(pdf, dpi=PRINT_DPI, facecolor='white'); out.append(pdf)
    plt.close(fig)
    return out


os.makedirs(WORK, exist_ok=True)
geo = json.load(open(GEOJSON, encoding='utf-8'))
written = []
for spec in SHEETS.values():
    written += page(spec, geo)
for p in written:
    print(f'{os.path.getsize(p) / 1024:7.0f} KB  {p}')
