/**
 * BivariateMap — the "priority" map for the MPDSR Atlas.
 *
 * Shades each district by a 3×3 matrix of BURDEN (deaths notified) × REVIEW
 * GAP (100 − % reviewed). Dark corner = high burden + low review = where the
 * MPDSR response is weakest and UNFPA should act first. District level only.
 */
import { useMemo, useRef, useState } from 'react'
import { MapContainer, GeoJSON } from 'react-leaflet'
import type { Layer, PathOptions } from 'leaflet'
import { domToPng } from 'modern-screenshot'
import { Download } from 'lucide-react'
import 'leaflet/dist/leaflet.css'

import { FitToData } from '@/components/maps/FitToData'
import { ATLAS_FONT } from '@/components/atlas/ChoroplethMap'
import { normaliseDistrict } from '@/data/partnerDistricts'
import { MPDSR_2024, MPDSR_SOURCE, type Metric } from '@/data/mpdsr2024'

// 3×3 bivariate palette (teal × purple). Index [burden][gap], 0=low..2=high.
const BIV = [
  ['#e8e8e8', '#dfb0d6', '#be64ac'],
  ['#ace4e4', '#a5add3', '#8c62aa'],
  ['#5ac8c8', '#5698b9', '#3b4994'],
]
const NO_DATA = '#eef0f2'
const METRIC_LABEL: Record<Metric, string> = { maternal: 'Maternal', neonatal: 'Neonatal' }

function terciles(values: number[]): [number, number] {
  const v = values.slice().sort((a, b) => a - b)
  const q = (p: number) => v[Math.min(v.length - 1, Math.floor(p * v.length))]
  return [q(0.34), q(0.67)]
}
function bucket(value: number, [t1, t2]: [number, number]): 0 | 1 | 2 {
  if (value <= t1) return 0
  if (value <= t2) return 1
  return 2
}

interface Props {
  metric: Metric
  geoData: GeoJSON.FeatureCollection | null
  geoError?: boolean
}

export function BivariateMap({ metric, geoData, geoError }: Props) {
  const exportRef = useRef<HTMLDivElement>(null)
  const [busy, setBusy] = useState(false)

  const rowByKey = useMemo(() => {
    const o: Record<string, typeof MPDSR_2024[number]> = {}
    for (const r of MPDSR_2024) o[normaliseDistrict(r.district)] = r
    return o
  }, [])

  const { burdenT, gapT } = useMemo(() => {
    const notified = MPDSR_2024.map(r => r[metric].notified)
    const gaps = MPDSR_2024.map(r => 100 - r[metric].pct) // higher = worse review
    return { burdenT: terciles(notified), gapT: terciles(gaps) }
  }, [metric])

  const classOf = (key: string): { color: string; b: number; g: number } | null => {
    const row = rowByKey[key]
    if (!row) return null
    const b = bucket(row[metric].notified, burdenT)
    const g = bucket(100 - row[metric].pct, gapT)
    return { color: BIV[b][g], b, g }
  }

  const styleFeature = (feature?: GeoJSON.Feature): PathOptions => {
    const key = normaliseDistrict((feature?.properties?.shapeName as string) ?? '')
    const c = classOf(key)
    return { fillColor: c?.color ?? NO_DATA, fillOpacity: 0.92, color: '#ffffff', weight: 0.7 }
  }

  const onEach = (feature: GeoJSON.Feature, layer: Layer) => {
    const name = (feature.properties?.shapeName as string) ?? 'Unknown'
    const key = normaliseDistrict(name)
    const row = rowByKey[key]
    const c = classOf(key)
    const priority = c ? (c.b === 2 && c.g === 2 ? 'TOP PRIORITY' : c.b + c.g >= 3 ? 'High' : c.b + c.g >= 2 ? 'Moderate' : 'Lower') : '—'
    const html = row
      ? `<b>${name}</b> · ${row.division}<br/>Notified: <b>${row[metric].notified}</b> · Reviewed: <b>${row[metric].pct}%</b><br/>Priority: <b>${priority}</b>`
      : `<b>${name}</b><br/>No data`
    ;(layer as unknown as { bindTooltip: (s: string, o: object) => void })
      .bindTooltip(html, { direction: 'top', sticky: true, className: 'leaflet-tooltip-custom' })
    ;(layer as unknown as { on: (e: string, fn: () => void) => void }).on('click', () => {
      const lyr = layer as unknown as { getBounds: () => any; _map?: any }
      if (lyr._map && lyr.getBounds) lyr._map.fitBounds(lyr.getBounds().pad(0.25))
    })
  }

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
      const a = document.createElement('a'); a.href = png
      a.download = `MPDSR2024_${metric}_priority_bivariate.png`; a.click()
    } finally { setBusy(false) }
  }

  return (
    <div className="card" style={{ padding: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', fontFamily: ATLAS_FONT }}>
      <div ref={exportRef} style={{ background: '#ffffff', padding: 16, color: '#111827', fontFamily: ATLAS_FONT }}>
        <div style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: '#111827' }}>
            {METRIC_LABEL[metric]} — response priority (burden × review gap, 2024)
          </div>
          <div style={{ fontSize: 11.5, color: '#6b7280' }}>By district · dark = many deaths + low review</div>
        </div>

        <div style={{ position: 'relative', height: 460, borderRadius: 8, overflow: 'hidden', background: '#ffffff' }}>
          {geoError ? (
            <div style={{ display: 'flex', height: '100%', alignItems: 'center', justifyContent: 'center', color: '#6b7280', fontSize: 13 }}>
              Map unavailable — could not load district boundaries.
            </div>
          ) : (
            <MapContainer
              center={[23.7, 90.4]} zoom={6} minZoom={6} maxZoom={10}
              zoomControl={true} scrollWheelZoom={false} dragging={true} attributionControl={false}
              style={{ height: '100%', width: '100%', background: '#ffffff' }}
            >
              {geoData && (
                <>
                  <FitToData data={geoData} />
                  <GeoJSON key={`biv-${metric}`} data={geoData} style={styleFeature} onEachFeature={onEach} />
                </>
              )}
            </MapContainer>
          )}

          <div style={{ position: 'absolute', top: 10, right: 12, zIndex: 500, textAlign: 'center', color: '#374151', fontSize: 10, fontWeight: 700 }}>
            <div style={{ fontSize: 16, lineHeight: 1 }}>↑</div>N
          </div>

          {/* 3×3 bivariate legend */}
          <div style={{
            position: 'absolute', bottom: 10, left: 12, zIndex: 500,
            background: 'rgba(255,255,255,0.94)', border: '1px solid #e5e7eb',
            borderRadius: 8, padding: '8px 10px', color: '#111827',
            boxShadow: '0 1px 4px rgba(0,0,0,0.12)',
          }}>
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6 }}>
              <div style={{ display: 'flex', flexDirection: 'column-reverse' }}>
                {[0, 1, 2].map(b => (
                  <div key={b} style={{ display: 'flex' }}>
                    {[0, 1, 2].map(g => (
                      <span key={g} style={{ width: 16, height: 16, background: BIV[b][g], border: '1px solid rgba(255,255,255,0.6)' }} />
                    ))}
                  </div>
                ))}
              </div>
            </div>
            <div style={{ fontSize: 8.5, color: '#6b7280', marginTop: 3 }}>→ review gap (worse) · ↑ burden (more deaths)</div>
            <div style={{ fontSize: 8.5, color: '#3b4994', fontWeight: 700, marginTop: 1 }}>■ dark corner = act first</div>
          </div>
        </div>

        <div style={{ marginTop: 8, fontSize: 9.5, color: '#9ca3af', lineHeight: 1.4 }}>
          Source: {MPDSR_SOURCE}. Burden = deaths notified; review gap = 100 − % reviewed; both split into terciles.
        </div>
      </div>

      <div data-no-export="true" style={{ padding: '8px 16px', borderTop: '1px solid var(--hair)', display: 'flex', justifyContent: 'flex-end' }}>
        <button onClick={handleExport} disabled={busy} style={{
          display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12.5, fontWeight: 600,
          color: 'var(--ink-2)', background: 'var(--surface-2)', border: '1px solid var(--hair)',
          borderRadius: 8, padding: '6px 12px', cursor: busy ? 'wait' : 'pointer',
        }}>
          <Download size={13} /> {busy ? 'Exporting…' : 'Download PNG'}
        </button>
      </div>
    </div>
  )
}
