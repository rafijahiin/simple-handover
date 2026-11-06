# SIMPLE dashboard map sheets

The coverage and donor maps shown on the dashboard are rendered here, not
drawn in the browser. One renderer per family, reading the canonical district
lists, writing output for two different destinations depending on the family.

| Script | Produces | District source |
|---|---|---|
| `make_donor_maps.py` | MPDSR (12), End Obstetric Fistula (14), side-by-side | `donorDistricts.ts` |
| `make_partner_maps.py` | PHD (9), Bandhu (8), SIMPLE all-partners (28) | `partnerDistricts.ts` |

`make_donor_maps.py` writes a PNG into `frontend/public/maps/` (served on the
CIPRB dashboard by `DonorMapSheet`) and a PDF to the Desktop pack.
`make_partner_maps.py` writes to the **Desktop pack only** — the partner
coverage maps are not shown on the dashboard (Home, PHD and Bandhu use the
interactive Leaflet map); these sheets exist only as the printable PDF.

After changing a district list in `src/data/`, rerun the matching script and
commit the regenerated PNG. Paths inside the scripts are absolute to this
machine; adjust `WEBDIR` / `DESK` if the checkout moves.

House style (hard-won, see commit history): fills and strokes are separate
passes or neighbours paint over boundaries; supported districts get a heavier
outline; the Sundarbans boundary is generalised for stroking only or it prints
as a black smear; legend is laid out in inches so a long label cannot overrun.
