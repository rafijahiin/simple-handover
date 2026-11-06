/**
 * FistulaCampaignMap — ONE full-country map in the MPDSR Atlas's visual
 * language: white background, grey no-data districts, hover tooltip with the
 * numbers, click-to-zoom, north arrow, classed legend, Atkinson type.
 *
 * The campaign upazilas are shaded by households visited on top of the grey
 * district base, so the country gives context and the colour answers "where
 * and how much". Placement is by the REPORTED upazila, never device GPS
 * (30 of 71 reports carry coordinates from the wrong district).
 */
import { useEffect, useMemo, useState } from 'react'
import { MapContainer, GeoJSON, ScaleControl, useMap } from 'react-leaflet'
import L from 'leaflet'
import type { Layer, PathOptions } from 'leaflet'
import 'leaflet/dist/leaflet.css'

const ADM2_URL = '/bangladesh-adm2.geojson'
const ADM3_URL = '/bangladesh-adm3.geojson'
const ATLAS_FONT = "'Atkinson Hyperlegible', system-ui, -apple-system, Segoe UI, sans-serif"

// Sequential oranges (ColorBrewer), light → dark, same family as the CIPRB
// dashboard. Atlas uses Reds/Blues for MPDSR; the campaign gets its own hue.
const RAMP = ['#feedde', '#fdbe85', '#fd8d3c', '#e6550d', '#a63603']
const NO_DATA = '#eceae4'          // warm paper, land without activity
const SEA = '#e7eef4'              // soft cool wash so the landmass reads as land
const HAIR = '#c3cdd4'             // district hairlines (was invisible white)

export interface CampaignUpazila {
  key: string
  dkey: string
  district: string
  upazila: string
  spellings: string[]
  reports: number
  households: number
  population: number
  source?: 'live' | 'archive'
  quarters?: string[]
  suspected: number
  confirmed: number
  referred: number
  gps_lat: number | null
  gps_lng: number | null
  gps_rows: number
  date_from: string | null
  date_to: string | null
}

interface UProps { key?: string; dkey?: string; name?: string; district?: string }
type UFeature = GeoJSON.Feature<GeoJSON.Geometry, UProps>

/** Latin-only mirror of fistula.geo_names.canon(), used ONLY to match the
 *  adm2 district shapeNames (always Latin) against the API's dkey. */
function canonLatin(name: string): string {
  let s = (name || '').toLowerCase().replace(/[^a-z0-9]/g, '')
  if (!s) return ''
  s = s[0] + s.slice(1).replace(/h/g, '')
  s = s[0] + s.slice(1).replace(/[aeiou]/g, '')
  let out = ''
  for (const ch of s) if (!out.endsWith(ch)) out += ch
  return out
}

function FitCountry({ data }: { data: GeoJSON.FeatureCollection | null }) {
  const map = useMap()
  useEffect(() => {
    if (!data) return
    const b = L.geoJSON(data as never).getBounds()
    if (!b.isValid()) return
    map.fitBounds(b, { padding: [10, 10] })
    // Leaflet blanks vectors outside its clip region on container resizes.
    const ro = new ResizeObserver(() => map.invalidateSize({ animate: false }))
    ro.observe(map.getContainer())
    return () => ro.disconnect()
  }, [map, data])
  return null
}

export function FistulaCampaignMap({ rows }: { rows: CampaignUpazila[] }) {
  const [adm2, setAdm2] = useState<GeoJSON.FeatureCollection | null>(null)
  const [adm3, setAdm3] = useState<GeoJSON.FeatureCollection | null>(null)
  const [geoError, setGeoError] = useState(false)

  useEffect(() => {
    let cancelled = false
    Promise.all([
      fetch(ADM2_URL).then((r) => r.json()),
      fetch(ADM3_URL).then((r) => r.json()),
    ]).then(([d2, d3]) => {
      if (cancelled) return
      setAdm2(d2)
      setAdm3(d3)
    }).catch(() => { if (!cancelled) setGeoError(true) })
    return () => { cancelled = true }
  }, [])

  const byKey = useMemo(() => {
    const m = new Map<string, CampaignUpazila>()
    rows.forEach((r) => m.set(r.key, r))
    return m
  }, [rows])
  const activeDkeys = useMemo(() => new Set(rows.map((r) => r.dkey)), [rows])

  // Shaded by POPULATION covered across Q1+Q2+live (RCH request, 17 Aug 2026).
  const maxPop = Math.max(1, ...rows.map((r) => r.population || 0))
  const classOf = (v: number) =>
    Math.min(RAMP.length - 1, Math.floor(((v || 0) / maxPop) * RAMP.length))

  // Upazila overlay: only the campaign's upazilas are drawn on top.
  const overlay = useMemo(() => {
    if (!adm3) return null
    const features = (adm3.features as UFeature[])
      .filter((f) => byKey.has(String(f.properties?.key ?? '')))
    return { type: 'FeatureCollection', features } as GeoJSON.FeatureCollection
  }, [adm3, byKey])

  const missing = useMemo(() => {
    if (!overlay) return []
    const drawn = new Set(
      overlay.features.map((f) => String((f.properties as UProps)?.key ?? '')))
    return rows.filter((r) => !drawn.has(r.key))
  }, [overlay, rows])

  const fmt = (n: number) => (n || 0).toLocaleString()

  const baseStyle = (feature?: GeoJSON.Feature): PathOptions => {
    const active = activeDkeys.has(
      canonLatin((feature?.properties?.shapeName as string) ?? ''))
    return {
      fillColor: active ? '#fdf1e3' : NO_DATA,
      fillOpacity: 1,
      color: HAIR, weight: 0.6,
    }
  }

  const baseEach = (feature: GeoJSON.Feature, layer: Layer) => {
    const name = (feature.properties?.shapeName as string) ?? ''
    const active = activeDkeys.has(canonLatin(name))
    layer.on('mouseover', () => (layer as L.Path).setStyle({ weight: 1.4, color: '#8fa0ac' }))
    layer.on('mouseout', () => (layer as L.Path).setStyle({ weight: 0.6, color: HAIR }))
    // No permanent labels — hover carries the names (Rafi, 2026-08-09).
    ;(layer as L.Path).bindTooltip(
      `<b>${name}</b><br/>${active ? 'Campaign district · hover the shaded upazilas' : 'No campaign activity'}`,
      { direction: 'top', sticky: true, className: 'leaflet-tooltip-custom' })
    layer.on('click', () => {
      const lyr = layer as unknown as { getBounds: () => L.LatLngBounds; _map?: L.Map }
      if (lyr._map && lyr.getBounds) lyr._map.fitBounds(lyr.getBounds().pad(0.25))
    })
  }

  const overlayStyle = (feature?: GeoJSON.Feature): PathOptions => {
    const row = byKey.get(String((feature?.properties as UProps)?.key ?? ''))
    return {
      fillColor: row ? RAMP[classOf(row.population)] : NO_DATA,
      fillOpacity: 0.95,
      color: '#7a3300', weight: 1.1,
    }
  }

  const overlayEach = (feature: GeoJSON.Feature, layer: Layer) => {
    const row = byKey.get(String((feature.properties as UProps)?.key ?? ''))
    if (!row) return
    layer.on('mouseover', () => (layer as L.Path).setStyle({ weight: 2.2, color: '#5c2500' }))
    layer.on('mouseout', () => (layer as L.Path).setStyle({ weight: 1.1, color: '#7a3300' }))
    ;(layer as L.Path).bindTooltip(
      `<b>${row.upazila}</b> · ${row.district}<br/>`
      + `Population covered: <b>${fmt(row.population)}</b> · Households: <b>${fmt(row.households)}</b><br/>`
      + `${(row as { quarters?: string[] }).quarters?.length ? 'Quarter: <b>' + (row as { quarters?: string[] }).quarters!.join('+') + '</b> · ' : ''}Suspected: <b>${row.suspected || 0}</b>`
      + (row.spellings.length > 1
        ? `<br/><span style="color:#6b7280">Recorded as: ${row.spellings.join(', ')}</span>`
        : ''),
      { direction: 'top', sticky: true, className: 'leaflet-tooltip-custom' })
    layer.on('click', () => {
      const lyr = layer as unknown as { getBounds: () => L.LatLngBounds; _map?: L.Map }
      if (lyr._map && lyr.getBounds) lyr._map.fitBounds(lyr.getBounds().pad(0.6))
    })
  }

  // Legend classes: even breaks of households up to the max, like the atlas's
  // classed swatch rows.
  const legend = RAMP.map((c, i) => ({
    color: c,
    label: `${fmt(Math.round((i / RAMP.length) * maxPop) + (i ? 1 : 0))}-${fmt(Math.round(((i + 1) / RAMP.length) * maxPop))}`,
  }))

  return (
    <div className="card campaign-atlas" style={{ padding: 0, overflow: 'hidden', fontFamily: ATLAS_FONT }}>
      {/* The atlas is deliberately light in BOTH themes: the choropleth ramp,
          grey no-data fill and cartographic labels are designed for a white
          ground, and a dark sea under a white card read as a broken panel.
          Everything inside therefore uses fixed light colours, never theme
          variables, and index.css re-whitens .leaflet-container in dark mode. */}
      <div style={{ background: '#ffffff', padding: 16, color: '#111827' }}>
        <div style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 15, fontWeight: 700 }}>
            Campaign coverage · population covered, by upazila (Q1 + Q2 + live)
          </div>
          <div style={{ fontSize: 11.5, color: '#6b7280' }}>
            Hover an upazila for its numbers · click to zoom · grey districts had no campaign activity
          </div>
        </div>

        {/* maxWidth tracks the height: Bangladesh is taller than it is wide, so
            a container wider than this fills with sea, not country. */}
        <div style={{ position: 'relative', height: 560, maxWidth: 540,
                      margin: '0 auto', width: '100%',
                      borderRadius: 8, overflow: 'hidden',
                      background: SEA, border: '1px solid #dbe3e9' }}>
          {geoError ? (
            <div style={{ display: 'flex', height: '100%', alignItems: 'center', justifyContent: 'center', color: '#6b7280', fontSize: 13 }}>
              Map unavailable — could not load boundaries.
            </div>
          ) : (
            <MapContainer
              center={[23.7, 90.4]} zoom={6} minZoom={6} maxZoom={11}
              zoomControl={true} scrollWheelZoom={false} doubleClickZoom={true}
              dragging={true} attributionControl={false}
              style={{ height: '100%', width: '100%', background: SEA }}
            >
              <ScaleControl position="bottomright" imperial={false} />
              {adm2 && (
                <>
                  <FitCountry data={adm2} />
                  <GeoJSON data={adm2 as never} style={baseStyle} onEachFeature={baseEach} />
                </>
              )}
              {overlay && (
                <GeoJSON
                  key={rows.map((r) => r.key + r.households).join('|')}
                  data={overlay as never}
                  style={overlayStyle}
                  onEachFeature={overlayEach}
                />
              )}
            </MapContainer>
          )}

          <div style={{ position: 'absolute', top: 10, right: 12, zIndex: 500, textAlign: 'center', color: '#374151', fontSize: 10, fontWeight: 700 }}>
            <div style={{ fontSize: 16, lineHeight: 1 }}>↑</div>N
          </div>

          <div style={{
            position: 'absolute', bottom: 10, left: 12, zIndex: 500,
            background: 'rgba(255,255,255,0.94)', border: '1px solid #e5e7eb',
            borderRadius: 8, padding: '8px 10px', fontSize: 11, color: '#111827',
            boxShadow: '0 1px 4px rgba(0,0,0,0.12)',
          }}>
            <div style={{ fontWeight: 700, marginBottom: 5, fontSize: 10.5, color: '#374151' }}>
              Population covered
            </div>
            {legend.map((c) => (
              <div key={c.color} style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 2 }}>
                <span style={{ width: 16, height: 11, background: c.color, border: '1px solid rgba(0,0,0,.08)', borderRadius: 2 }} />
                <span style={{ fontVariantNumeric: 'tabular-nums' }}>{c.label}</span>
              </div>
            ))}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4, color: '#6b7280' }}>
              <span style={{ width: 16, height: 11, background: NO_DATA, border: '1px solid rgba(0,0,0,.08)', borderRadius: 2 }} />
              <span>No activity</span>
            </div>
          </div>
        </div>

      {missing.length > 0 && (
        <p style={{ fontSize: 11.5, color: '#6b7280', margin: '8px 2px 0' }}>
          Not drawn: {missing.map((m) => `${m.upazila} (recorded under ${m.district})`).join(', ')}.
          The national boundary file has no matching shape — either a newer
          upazila (Guimara was created in 2014 from parts of Ramgarh, Matiranga
          and Mahalchhari) or a district recorded incorrectly in the field.
          Its figures are still counted in the totals and in the district
          funnel beside the map.
        </p>
      )}
      </div>
    </div>
  )
}
