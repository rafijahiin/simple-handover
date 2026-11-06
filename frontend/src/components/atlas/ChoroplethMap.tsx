/**
 * ChoroplethMap — report-grade map for the MPDSR Atlas.
 *
 * Modes:
 *   • value  — shade by a metric+indicator (notified / reviewed / %), as a
 *              quantile choropleth.
 *   • change — diverging map of the 2023→2024 change in notifications.
 *
 * Levels: district (each district its own value) or division (each district
 * shaded by its division aggregate — no adm1 geojson needed).
 *
 * Cartography: ColorBrewer ramps (maternal Reds / neonatal Blues; change uses
 * a diverging RdBu), quantile classes with numeric legend, north arrow,
 * source caption, zoom controls, click-to-zoom drill-down, hover tooltip, and
 * white-background 2× PNG export (Leaflet chrome filtered out). Typeset in
 * Atkinson Hyperlegible for maximum legibility in print/report use.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { MapContainer, GeoJSON } from 'react-leaflet'
import type { Layer, PathOptions } from 'leaflet'
import { domToPng } from 'modern-screenshot'
import { Download } from 'lucide-react'
import 'leaflet/dist/leaflet.css'

import { FitToData } from '@/components/maps/FitToData'
import { normaliseDistrict } from '@/data/partnerDistricts'
import {
  MPDSR_2024, MPDSR_SOURCE, type Metric, type Indicator,
  districtValues, divisionValues, divisionOfDistrict,
} from '@/data/mpdsr2024'
import { NOTIFIED_2023 } from '@/data/mpdsr2023'

const GEOJSON_URL = '/bangladesh-adm2.geojson'
const GEOJSON_ADM1_URL = '/bangladesh-adm1.geojson'
export const ATLAS_FONT = "'Atkinson Hyperlegible', system-ui, -apple-system, Segoe UI, sans-serif"

const RAMPS: Record<Metric, string[]> = {
  maternal: ['#fee5d9', '#fcae91', '#fb6a4a', '#de2d26', '#a50f15'], // Reds
  neonatal: ['#eff3ff', '#bdd7e7', '#6baed6', '#3182bd', '#08519c'], // Blues
}
const DIVERGING = ['#b2182b', '#ef8a62', '#f7f7f7', '#67a9cf', '#2166ac'] // RdBu
const NO_DATA = '#e5e7eb'

const INDICATOR_LABEL: Record<Indicator, string> = {
  notified: 'Deaths notified', reviewed: 'Deaths reviewed', pct: '% of deaths reviewed',
}
const METRIC_LABEL: Record<Metric, string> = { maternal: 'Maternal', neonatal: 'Neonatal' }

function quantileBreaks(values: number[], n: number): number[] {
  const v = values.filter(x => x > 0).sort((a, b) => a - b)
  if (v.length === 0) return [0]
  const breaks: number[] = []
  for (let i = 1; i <= n; i++) breaks.push(v[Math.min(v.length - 1, Math.ceil((i / n) * v.length) - 1)])
  breaks[breaks.length - 1] = v[v.length - 1]
  return [...new Set(breaks)].sort((a, b) => a - b)
}
function classIndex(value: number, breaks: number[]): number {
  for (let i = 0; i < breaks.length; i++) if (value <= breaks[i]) return i
  return breaks.length - 1
}
function rangeLabels(breaks: number[], indicator: Indicator): string[] {
  const sfx = indicator === 'pct' ? '%' : ''
  const out: string[] = []; let lo = 1
  for (const hi of breaks) { out.push(lo === hi ? `${lo}${sfx}` : `${lo}–${hi}${sfx}`); lo = hi + 1 }
  return out
}

export type AtlasMode = 'value' | 'change'

interface Props {
  metric: Metric
  level: 'district' | 'division'
  indicator: Indicator
  mode?: AtlasMode
  geoData: GeoJSON.FeatureCollection | null
  geoError?: boolean
  /** Optional overlay drawn as thin black outlines on top of the fills —
   *  used on division maps to show the 8 division boundaries. */
  boundaryGeo?: GeoJSON.FeatureCollection | null
}

export function ChoroplethMap({ metric, level, indicator, mode = 'value', geoData, geoError, boundaryGeo }: Props) {
  const exportRef = useRef<HTMLDivElement>(null)
  const [busy, setBusy] = useState(false)

  const rowByKey = useMemo(() => {
    const o: Record<string, typeof MPDSR_2024[number]> = {}
    for (const r of MPDSR_2024) o[normaliseDistrict(r.district)] = r
    return o
  }, [])

  const valueByKey = useMemo(() => {
    const o: Record<string, number> = {}
    if (mode === 'change') {
      if (level === 'district') {
        for (const r of MPDSR_2024) {
          const prev = NOTIFIED_2023[r.district]?.[metric] ?? 0
          o[normaliseDistrict(r.district)] = r[metric].notified - prev
        }
      } else {
        const byDiv = divisionOfDistrict()
        const cur: Record<string, number> = {}, prev: Record<string, number> = {}
        for (const r of MPDSR_2024) {
          cur[r.division] = (cur[r.division] ?? 0) + r[metric].notified
          prev[r.division] = (prev[r.division] ?? 0) + (NOTIFIED_2023[r.district]?.[metric] ?? 0)
        }
        for (const [name, d] of Object.entries(byDiv)) o[normaliseDistrict(name)] = (cur[d] ?? 0) - (prev[d] ?? 0)
      }
      return o
    }
    if (level === 'district') {
      const dv = districtValues(metric, indicator)
      for (const [name, val] of Object.entries(dv)) o[normaliseDistrict(name)] = val
    } else {
      const dv = divisionValues(metric, indicator); const map = divisionOfDistrict()
      for (const [name, div] of Object.entries(map)) o[normaliseDistrict(name)] = dv[div]
    }
    return o
  }, [metric, level, indicator, mode])

  const breaks = useMemo(() => {
    if (mode === 'change') return [0]
    const vals = level === 'district'
      ? Object.values(districtValues(metric, indicator))
      : Object.values(divisionValues(metric, indicator))
    return quantileBreaks(vals, 5)
  }, [metric, level, indicator, mode])

  const changeThresholds = useMemo(() => {
    if (mode !== 'change') return { small: 0, big: 0 }
    const abs = Object.values(valueByKey).map(Math.abs).filter(x => x > 0).sort((a, b) => a - b)
    if (abs.length === 0) return { small: 1, big: 2 }
    const q = (p: number) => abs[Math.min(abs.length - 1, Math.floor(p * abs.length))]
    return { small: Math.max(1, q(0.34)), big: Math.max(2, q(0.67)) }
  }, [valueByKey, mode])

  const ramp = RAMPS[metric]
  const labels = rangeLabels(breaks, indicator)

  const colorFor = (key: string): string => {
    const v = valueByKey[key]
    if (v === undefined || v === null) return NO_DATA
    if (mode === 'change') {
      const { small, big } = changeThresholds
      if (v <= -big) return DIVERGING[0]
      if (v <= -small) return DIVERGING[1]
      if (v < small) return DIVERGING[2]
      if (v < big) return DIVERGING[3]
      return DIVERGING[4]
    }
    if (v === 0) return NO_DATA
    return ramp[Math.min(ramp.length - 1, classIndex(v, breaks))]
  }

  const styleFeature = (feature?: GeoJSON.Feature): PathOptions => {
    const key = normaliseDistrict((feature?.properties?.shapeName as string) ?? '')
    return {
      fillColor: colorFor(key), fillOpacity: 0.92,
      color: '#ffffff', weight: level === 'division' ? 0.5 : 0.7,
    }
  }

  const onEach = (feature: GeoJSON.Feature, layer: Layer) => {
    const name = (feature.properties?.shapeName as string) ?? 'Unknown'
    const key = normaliseDistrict(name)
    const row = rowByKey[key]
    let html: string
    if (mode === 'change' && row) {
      const cur = row[metric].notified
      const prev = NOTIFIED_2023[row.district]?.[metric] ?? 0
      const d = cur - prev
      html = `<b>${name}</b> · ${row.division}<br/>2023: <b>${prev}</b> → 2024: <b>${cur}</b> (${d >= 0 ? '+' : ''}${d})`
    } else if (row) {
      const c = row[metric]
      html = `<b>${name}</b> · ${row.division}<br/>Notified: <b>${c.notified}</b> · Reviewed: <b>${c.reviewed}</b> · ${c.pct}% reviewed`
    } else html = `<b>${name}</b><br/>No data`
    ;(layer as unknown as { bindTooltip: (s: string, o: object) => void })
      .bindTooltip(html, { direction: 'top', sticky: true, className: 'leaflet-tooltip-custom' })
    ;(layer as unknown as { on: (e: string, fn: () => void) => void }).on('click', () => {
      const lyr = layer as unknown as { getBounds: () => any; _map?: any }
      if (lyr._map && lyr.getBounds) lyr._map.fitBounds(lyr.getBounds().pad(0.25))
    })
  }

  const title = mode === 'change'
    ? `${METRIC_LABEL[metric]} deaths — change in notifications, 2023→2024`
    : `${METRIC_LABEL[metric]} deaths — ${INDICATOR_LABEL[indicator]} (2024)`
  const subtitle = mode === 'change'
    ? 'Blue = more reported than 2023 · Red = fewer · Grey = little change'
    : level === 'district' ? 'By district · 64 districts' : 'By division · 8 divisions'

  const handleExport = async () => {
    if (!exportRef.current) return
    setBusy(true)
    try {
      const png = await domToPng(exportRef.current, {
        scale: 2, backgroundColor: '#ffffff',
        filter: (n) => {
          if (n instanceof HTMLElement) {
            if (n.dataset?.noExport === 'true') return false
            if (n.classList?.contains('leaflet-control')) return false
          }
          return true
        },
      })
      const a = document.createElement('a')
      a.href = png
      a.download = `MPDSR2024_${metric}_${level}_${mode === 'change' ? 'change' : indicator}.png`
      a.click()
    } finally { setBusy(false) }
  }

  return (
    <div className="card" style={{ padding: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', fontFamily: ATLAS_FONT }}>
      <div ref={exportRef} style={{ background: '#ffffff', padding: 16, color: '#111827', fontFamily: ATLAS_FONT }}>
        <div style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: '#111827' }}>{title}</div>
          <div style={{ fontSize: 11.5, color: '#6b7280' }}>{subtitle}</div>
        </div>

        <div style={{ position: 'relative', height: 460, borderRadius: 8, overflow: 'hidden', background: '#ffffff' }}>
          {geoError ? (
            <div style={{ display: 'flex', height: '100%', alignItems: 'center', justifyContent: 'center', color: '#6b7280', fontSize: 13 }}>
              Map unavailable — could not load district boundaries.
            </div>
          ) : (
            <MapContainer
              center={[23.7, 90.4]} zoom={6} minZoom={6} maxZoom={10}
              zoomControl={true} scrollWheelZoom={false} doubleClickZoom={true}
              dragging={true} attributionControl={false}
              style={{ height: '100%', width: '100%', background: '#ffffff' }}
            >
              {geoData && (
                <>
                  <FitToData data={geoData} />
                  <GeoJSON key={`${metric}-${level}-${indicator}-${mode}`} data={geoData} style={styleFeature} onEachFeature={onEach} />
                  {boundaryGeo && (
                    <GeoJSON
                      key="div-bounds"
                      data={boundaryGeo}
                      style={{ color: '#000000', weight: 1, opacity: 0.9, fill: false, interactive: false } as PathOptions}
                    />
                  )}
                </>
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
              {mode === 'change' ? 'Δ notifications' : INDICATOR_LABEL[indicator]}
            </div>
            {mode === 'change' ? (
              [
                [DIVERGING[0], `↓ −${changeThresholds.big}+`],
                [DIVERGING[1], `↓ small`],
                [DIVERGING[2], `≈ no change`],
                [DIVERGING[3], `↑ small`],
                [DIVERGING[4], `↑ +${changeThresholds.big}+`],
              ].map(([col, lab], i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                  <span style={{ width: 14, height: 12, background: col as string, border: '1px solid rgba(0,0,0,0.15)', borderRadius: 2 }} />
                  <span>{lab}</span>
                </div>
              ))
            ) : (
              <>
                {ramp.slice(0, labels.length).map((col, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                    <span style={{ width: 14, height: 12, background: col, border: '1px solid rgba(0,0,0,0.15)', borderRadius: 2 }} />
                    <span style={{ fontVariantNumeric: 'tabular-nums' }}>{labels[i]}</span>
                  </div>
                ))}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 2 }}>
                  <span style={{ width: 14, height: 12, background: NO_DATA, border: '1px solid rgba(0,0,0,0.15)', borderRadius: 2 }} />
                  <span>0 / none</span>
                </div>
              </>
            )}
          </div>
        </div>

        <div style={{ marginTop: 8, fontSize: 9.5, color: '#9ca3af', lineHeight: 1.4 }}>
          Source: {MPDSR_SOURCE}.{mode === 'change' ? ' Δ vs MPDSR 2023 report (community notified).' : ` Classes: quantile (5).`}
          {level === 'division' ? ' Districts shaded by division aggregate.' : ''}
        </div>
      </div>

      <div data-no-export="true" style={{ padding: '8px 16px', borderTop: '1px solid var(--hair)', display: 'flex', justifyContent: 'flex-end' }}>
        <button onClick={handleExport} disabled={busy} style={{
          display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12.5, fontWeight: 600,
          color: 'var(--ink-2)', background: 'var(--surface-2)', border: '1px solid var(--hair)',
          borderRadius: 8, padding: '6px 12px', cursor: busy ? 'wait' : 'pointer', fontFamily: ATLAS_FONT,
        }}>
          <Download size={13} /> {busy ? 'Exporting…' : 'Download PNG'}
        </button>
      </div>
    </div>
  )
}

function useGeo(url: string) {
  const [geoData, setGeoData] = useState<GeoJSON.FeatureCollection | null>(null)
  const [geoError, setGeoError] = useState(false)
  useEffect(() => {
    let cancelled = false
    fetch(url)
      .then(r => { if (!r.ok) throw new Error('geojson'); return r.json() })
      .then(d => { if (!cancelled) setGeoData(d) })
      .catch(() => { if (!cancelled) setGeoError(true) })
    return () => { cancelled = true }
  }, [url])
  return { geoData, geoError }
}

/** District (adm2) boundaries — the choropleth fill layer. */
export const useDistrictGeo = () => useGeo(GEOJSON_URL)
/** Division (adm1) outlines — overlaid as thin black boundaries. */
export const useDivisionBoundaries = () => useGeo(GEOJSON_ADM1_URL).geoData
