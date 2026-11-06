"""The two CIPRB donor maps, drawn for print.

Same district lists (Dr. Sayeed, 27 September 2026), same five UNFPA orange
tones and the same boundary file as the live dashboard. A4 portrait at 300 dpi,
plus a landscape sheet with both maps side by side.
"""
import json
import math
import os
import re

import matplotlib
matplotlib.use('Agg')
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon as MplPolygon, Rectangle

GEOJSON = r'C:\Users\HP\Documents\spondon_clone\frontend\public\bangladesh-adm2.geojson'
OUTDIR = r'C:\Users\HP\Desktop\CIPRB_Donor_Maps'
# The SIMPLE dashboard shows these same sheets, so the web copies are written
# straight into the frontend's static folder. Dr. Tanjina's 6 Oct file asked
# for these maps on the dashboard, not for a separate rendering of the same
# data, so there is one renderer and the dashboard serves its output.
WEBDIR = r'C:\Users\HP\Documents\spondon_clone\frontend\public\maps'
WEB_DPI = 150
DATED = '27 September 2026'

FONT = 'Atkinson Hyperlegible'
plt.rcParams['font.family'] = FONT
plt.rcParams['pdf.fonttype'] = 42      # real text in the PDF, not outlines

INK, ASH, HAIR = '#131619', '#686a6c', '#a8aeb4'
SEA, LAND = '#eef3f7', '#ece9e4'
# Print weights. Hairlines below ~0.5pt wash out on an office printer, so every
# boundary is stroked in its own pass at a weight that survives toner.
BORDER, BORDER_LW = '#6f777e', 0.85      # district boundaries
EDGE, EDGE_LW = '#26292c', 1.30          # outline of a supported district
TINT = {
    'GAC + SIDA': '#7A2E00',
    'SIDA + CP': '#FF8A3D',
    'SIDA': '#C44E00',
    'GAC': '#F96000',
    'CP': '#FDCFB3',
}
LEGEND_ORDER = ['GAC + SIDA', 'SIDA + CP', 'SIDA', 'GAC', 'CP']

# Donor lists exactly as the email gave them. Noakhali is recorded as SIDA + CP:
# the MPDSR table lists it under SIDA and again under Common (SIDA+CP).
PROJECTS = {
    'MPDSR': {
        'title': 'MPDSR districts',
        'file': 'MPDSR_districts_by_donor',
        'districts': {
            'Sherpur': ['GAC'], 'Bhola': ['GAC'],
            'Chandpur': ['SIDA'],
            'Patuakhali': ['CP'], 'Barguna': ['CP'], 'Bagerhat': ['CP'],
            'Gaibandha': ['CP'], 'Jamalpur': ['CP'], 'Sirajganj': ['CP'],
            'Sunamganj': ['GAC', 'SIDA'],
            'Noakhali': ['SIDA', 'CP'], 'Bandarban': ['SIDA', 'CP'],
        },
    },
    'Fistula': {
        'title': 'End Obstetric Fistula districts',
        'file': 'Fistula_districts_by_donor',
        'districts': {
            'Sherpur': ['GAC'], 'Bhola': ['GAC'], 'Kurigram': ['GAC'],
            'Khagrachari': ['GAC'],
            'Chandpur': ['SIDA'],
            'Patuakhali': ['CP'], 'Barguna': ['CP'], 'Bagerhat': ['CP'],
            'Gaibandha': ['CP'], 'Jamalpur': ['CP'], 'Sirajganj': ['CP'],
            'Sunamganj': ['GAC', 'SIDA'],
            'Noakhali': ['SIDA', 'CP'], 'Bandarban': ['SIDA', 'CP'],
        },
    },
}

# Where a name cannot sit on its own district: offset in degrees, with a
# leader line back to the district.
LEADERS = {
    'Bhola':      (-0.46, -0.46),
    'Barguna':    (-0.40, -0.22),
    'Patuakhali': (-0.58, 0.02),
    'Chandpur': (-0.62, 0.26),
    'Sherpur':  (0.02, 0.34),
    'Jamalpur': (-0.58, -0.06),
    'Noakhali': (0.60, -0.26),
}
ALIASES = {'khagrachari': 'khagrachhari', 'moulavibazar': 'maulvibazar',
           'chattogram': 'chittagong', 'cumilla': 'comilla', 'bogura': 'bogra',
           'jashore': 'jessore', 'barishal': 'barisal'}


def key(name):
    k = re.sub(r'[^a-z]', '', str(name).lower())
    return ALIASES.get(k, k)


def donor_key(donors):
    return ' + '.join(d for d in ('GAC', 'SIDA', 'CP') if d in donors)


def rings(geom):
    if geom['type'] == 'Polygon':
        return [geom['coordinates'][0]]
    if geom['type'] == 'MultiPolygon':
        return [poly[0] for poly in geom['coordinates']]
    return []


def biggest_ring(feat):
    best, best_area = None, 0.0
    for ring in rings(feat['geometry']):
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        area = (max(xs) - min(xs)) * (max(ys) - min(ys))
        if area > best_area:
            best, best_area = ring, area
    return best


def centroid(ring):
    return (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))


def thinned(ring, tol):
    """The ring, generalised for stroking only.

    The Sundarbans boundary is fractal: stroked vertex for vertex it prints as a
    black smear rather than a line. The fill underneath keeps every vertex, so
    the shape and its colour stay exact.
    """
    from shapely.geometry import LineString
    if len(ring) < 5:
        return ring
    return list(LineString(ring).simplify(tol).coords)


def draw_map(ax, spec, geo, *, label_size=8.2, legend=True, compact=False):
    """One map onto one axes. Returns nothing; the caller owns the page."""
    groups = {key(d): donor_key(v) for d, v in spec['districts'].items()}
    pretty = {key(d): d for d in spec['districts']}
    seen = set()

    ax.set_facecolor(SEA)
    labels, shaded_rings = [], []
    scale = max(0.75, label_size / 8.2)      # thinner paper, thinner lines

    for feat in geo['features']:
        name = feat['properties'].get('shapeName', '')
        group = groups.get(key(name))
        shaded = group is not None
        if shaded:
            seen.add(key(name))
        for ring in rings(feat['geometry']):
            ax.add_patch(MplPolygon(ring, closed=True, edgecolor='none',
                                    facecolor=TINT[group] if shaded else LAND,
                                    zorder=2))
            # every district boundary, one weight, drawn over the fills
            ax.plot(*zip(*thinned(ring, 0.004)), color=BORDER, linewidth=BORDER_LW * scale,
                    solid_joinstyle='round', zorder=3)
            if shaded:
                shaded_rings.append(ring)   # filtered below: chars stay hairline
        if shaded:
            labels.append((centroid(biggest_ring(feat)), pretty[key(name)]))

    for ring in shaded_rings:                # supported districts read first
        bx = [p[0] for p in ring]
        by = [p[1] for p in ring]
        if (max(bx) - min(bx)) * (max(by) - min(by)) < 0.0012:
            continue                         # a delta char, too small to outline heavily
        ax.plot(*zip(*thinned(ring, 0.009)), color=EDGE, linewidth=EDGE_LW * scale,
                solid_joinstyle='round', zorder=4)

    missing = set(groups) - seen
    if missing:
        raise SystemExit(f'{spec["title"]}: districts not on the map file: {missing}')

    for (cx, cy), name in labels:
        dx, dy = LEADERS.get(name, (0.0, 0.0))
        tx, ty = cx + dx, cy + dy
        if dx or dy:
            ax.annotate('', xy=(cx, cy), xytext=(tx, ty), zorder=7,
                        arrowprops=dict(arrowstyle='-', color='#7a7a7a', linewidth=0.7,
                                        shrinkA=1, shrinkB=1))
        ax.text(tx, ty, name, ha='center', va='center', fontsize=label_size,
                color='#1a1a1a', zorder=8, fontweight='bold',
                path_effects=[pe.withStroke(linewidth=2.8, foreground='white')])

    xs = [p[0] for f in geo['features'] for r in rings(f['geometry']) for p in r]
    ys = [p[1] for f in geo['features'] for r in rings(f['geometry']) for p in r]
    ax.set_xlim(min(xs) - 0.12, max(xs) + 0.12)
    ax.set_ylim(min(ys) - 0.12, max(ys) + 0.12)
    ax.set_aspect(1 / math.cos(math.radians(23.7)))   # equirectangular at this latitude
    ax.set_xticks([])
    ax.set_yticks([])
    for side in ax.spines.values():
        side.set_edgecolor(HAIR)
        side.set_linewidth(1.0)

    # north arrow
    ax.annotate('N', xy=(0.962, 0.93), xytext=(0.962, 0.875),
                xycoords='axes fraction', textcoords='axes fraction',
                ha='center', va='center', fontsize=9.5, fontweight='bold', color=INK,
                arrowprops=dict(arrowstyle='-|>', color=INK, linewidth=1.1))

    # scale bar, 100 km at this latitude
    km_per_deg = 111.32 * math.cos(math.radians(23.7))
    bar = 100 / km_per_deg
    x0, y0 = max(xs) - 0.05 - bar, min(ys) + 0.24
    for i in range(2):
        ax.add_patch(Rectangle((x0 + i * bar / 2, y0), bar / 2, 0.055,
                               facecolor=INK if i == 0 else 'white',
                               edgecolor=INK, linewidth=0.7, zorder=9))
    for frac, lab in ((0, '0'), (0.5, '50'), (1, '100 km')):
        ax.text(x0 + bar * frac, y0 - 0.1, lab, ha='center', va='top',
                fontsize=7, color=ASH, zorder=9)

    if not legend:
        return

    counts = {}
    for d, v in spec['districts'].items():
        counts.setdefault(donor_key(v), []).append(d)
    return [(g, len(counts[g])) for g in LEGEND_ORDER if g in counts] + [('Not supported', 0)]


def draw_legend(fig, rows, *, y, x0=0.06, x1=0.955, size=9.2):
    """A horizontal key under the map, outside the frame so nothing is hidden.

    Laid out in inches and sized to the text, so a long label such as
    "GAC + SIDA (1)" can never run into the next swatch.
    """
    width_in = fig.get_size_inches()[0]
    sw, pad, gap = 0.26, 0.11, 0.34          # swatch, swatch-to-text, item-to-item
    char = 0.56 * size / 72                  # a workable width per character

    texts = [lab if not n else f'{lab}  ({n})' for lab, n in rows]
    widths = [sw + pad + char * len(t) for t in texts]
    avail = (x1 - x0) * width_in
    span = sum(widths) + gap * (len(rows) - 1)
    if span > avail:                         # narrow column: shrink to fit, don't overrun
        k = avail / span
        size, sw, pad, gap = size * k, sw * k, pad * k, gap * k
        widths = [w * k for w in widths]
        span = avail
    x = (x0 * width_in) + (avail - span) / 2   # centred under the map

    for (label, _), text, w in zip(rows, texts, widths):
        fig.patches.append(Rectangle((x / width_in, y - 0.006), sw / width_in, 0.013,
                                     transform=fig.transFigure, figure=fig,
                                     facecolor=TINT.get(label, LAND),
                                     edgecolor='#00000022', linewidth=0.6))
        fig.text((x + sw + pad) / width_in, y, text, fontsize=size, color=INK, va='center')
        x += w + gap


def page(spec, geo):
    fig = plt.figure(figsize=(8.27, 11.69))
    fig.patch.set_facecolor('white')
    ax = fig.add_axes([0.06, 0.105, 0.88, 0.755])
    rows = draw_map(ax, spec, geo)
    draw_legend(fig, rows, y=0.072)

    fig.text(0.06, 0.945, spec['title'], fontsize=21, fontweight='bold', color=INK)
    fig.text(0.06, 0.925, 'CIPRB and UNFPA supported districts, coloured by donor',
             fontsize=11.5, color=ASH)
    fig.add_artist(plt.Line2D([0.06, 0.94], [0.912, 0.912], color='#F96000',
                              linewidth=1.6, transform=fig.transFigure))
    fig.text(0.06, 0.886, f'{len(spec["districts"])} districts', fontsize=10,
             color=INK, fontweight='bold')
    fig.text(0.94, 0.886, f'SIMPLE dashboard  ·  district list provided by CIPRB, {DATED}',
             fontsize=9, color=ASH, ha='right')
    fig.text(0.06, 0.022, 'Boundaries: Bangladesh district boundaries (ADM2). '
             'A district funded by two donors is shown in its own colour.',
             fontsize=8, color=ASH)

    out = []
    for ext in ('png', 'pdf'):
        path = os.path.join(OUTDIR, f'{spec["file"]}.{ext}')
        fig.savefig(path, dpi=300, facecolor='white')
        out.append(path)
    web = os.path.join(WEBDIR, f'{spec["file"]}.png')
    fig.savefig(web, dpi=WEB_DPI, facecolor='white')
    out.append(web)
    plt.close(fig)
    return out


def side_by_side(geo):
    fig = plt.figure(figsize=(16.54, 11.69))     # A3 landscape, two maps
    fig.patch.set_facecolor('white')
    fig.text(0.04, 0.945, 'CIPRB and UNFPA supported districts, by donor',
             fontsize=23, fontweight='bold', color=INK)
    fig.text(0.04, 0.922, 'MPDSR and End Obstetric Fistula, side by side',
             fontsize=12.5, color=ASH)
    fig.add_artist(plt.Line2D([0.04, 0.96], [0.908, 0.908], color='#F96000',
                              linewidth=1.8, transform=fig.transFigure))
    fig.text(0.96, 0.925, f'SIMPLE dashboard  ·  district list provided by CIPRB, {DATED}',
             fontsize=9.5, color=ASH, ha='right')

    for i, spec in enumerate(PROJECTS.values()):
        ax = fig.add_axes([0.04 + i * 0.48, 0.10, 0.44, 0.78])
        rows = draw_map(ax, spec, geo, label_size=7.6)
        draw_legend(fig, rows, y=0.055, x0=0.04 + i * 0.48, x1=0.04 + i * 0.48 + 0.44,
                    size=9)
        ax.set_title(f'{spec["title"]}   ({len(spec["districts"])} districts)',
                     loc='left', fontsize=14, fontweight='bold', color=INK, pad=10)

    out = []
    for ext in ('png', 'pdf'):
        path = os.path.join(OUTDIR, f'Both_maps_side_by_side.{ext}')
        fig.savefig(path, dpi=300, facecolor='white')
        out.append(path)
    web = os.path.join(WEBDIR, 'Both_maps_side_by_side.png')
    fig.savefig(web, dpi=WEB_DPI, facecolor='white')
    out.append(web)
    plt.close(fig)
    return out


os.makedirs(OUTDIR, exist_ok=True)
os.makedirs(WEBDIR, exist_ok=True)
geo = json.load(open(GEOJSON, encoding='utf-8'))
written = []
for spec in PROJECTS.values():
    written += page(spec, geo)
written += side_by_side(geo)
for path in written:
    print(f'{os.path.getsize(path) / 1024:7.0f} KB  {path}')
