import { useEffect, useRef } from 'react'
import { MapContainer, GeoJSON, CircleMarker, Popup } from 'react-leaflet'
import type { Layer, PathOptions } from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { ActivityItem, ServiceCenter } from '@/types'
import { useState } from 'react'
import { FitToData } from './FitToData'
import { PARTNER_DISTRICTS, normaliseDistrict, type PartnerCode } from '@/data/partnerDistricts'

// GeoJSON bundled in frontend/public — avoids GitHub LFS CDN CORS issues
const GEOJSON_URL = '/bangladesh-adm2.geojson'

// Fallback highlight set (CIPRB CP10) when no partner is specified.
const CP10_DISTRICTS = new Set([
  'coxsbazar', 'bandarban', 'noakhali', 'dhaka',
  'sirajganj', 'jamalpur', 'gaibandha', 'patuakhali',
  'barguna', 'bagerhat',
])

// UNFPA branding — every service-type pin uses the brand orange family.
// The pin shape / icon does the type identification, not colour.
const CENTER_COLORS: Record<string, string> = {
  DIC:     '#F96000',   // UNFPA primary
  BROTHEL: '#C44E00',   // UNFPA deep
  SUB_DIC: '#FB904D',   // UNFPA bright
  MOBILE:  '#FDCFB3',   // UNFPA pale
}

// Per-partner choropleth tints — all share the UNFPA orange family.
// Three distinguishable shades so multi-partner overlaps stay readable,
// but no foreign hues. Partner code on the legend does the identification.
const PARTNER_TINTS: Record<string, { active: string; cp10: string; stroke: string }> = {
  PHD:    { active: '#F96000', cp10: '#FFD9B8', stroke: '#7A2E00' },
  Bandhu: { active: '#F96000', cp10: '#FFD9B8', stroke: '#7A2E00' },
  CIPRB:  { active: '#F96000', cp10: '#FFD9B8', stroke: '#7A2E00' },
}

interface Props {
  activityFeed: ActivityItem[]
  centers?: ServiceCenter[]
  className?: string
  /** Partner code — colours the choropleth in that partner's brand
   *  hue instead of the default UNFPA blue. Falls back to UNFPA blue
   *  when omitted (homepage / cross-org dashboards). */
  partner?: 'PHD' | 'Bandhu' | 'CIPRB'
}

function normalize(name: string) {
  return name.toLowerCase().replace(/[^a-z]/g, '')
}

export function BangladeshMap({ activityFeed, centers = [], className, partner }: Props) {
  const [geoData, setGeoData] = useState<GeoJSON.FeatureCollection | null>(null)
  const [error, setError] = useState(false)
  const geoJsonRef = useRef<L.GeoJSON | null>(null)

  // Resolve tint from partner prop; default to UNFPA blue.
  const tint = (partner && PARTNER_TINTS[partner]) || {
    active: '#2171EC', cp10: '#f59e0b', stroke: '#004A66',
  }

  // The set of districts to highlight: this partner's own coverage when a
  // partner is given (so PHD's map shows PHD's districts, not CIPRB's), else
  // the CIPRB CP10 fallback.
  const highlightSet: Set<string> =
    partner && PARTNER_DISTRICTS[partner as PartnerCode]
      ? new Set(PARTNER_DISTRICTS[partner as PartnerCode].map(normaliseDistrict))
      : CP10_DISTRICTS

  // Count submissions per district
  const districtCounts: Record<string, number> = {}
  for (const item of activityFeed) {
    const key = normalize(item.district)
    districtCounts[key] = (districtCounts[key] ?? 0) + 1
  }

  const maxCount = Math.max(1, ...Object.values(districtCounts))

  useEffect(() => {
    fetch(GEOJSON_URL)
      .then((r) => {
        if (!r.ok) throw new Error('GeoJSON fetch failed')
        return r.json()
      })
      .then((data) => setGeoData(data))
      .catch(() => setError(true))
  }, [])

  function districtStyle(name: string, count: number): PathOptions {
    // No basemap behind the choropleth (so the border can't bleed into
    // India), which means every district needs a visible body or the
    // country silhouette breaks apart. White hairline strokes draw the
    // district + national outline crisply.
    if (count > 0) {
      // Activity intensity — strong, fully opaque at the top of the range.
      return {
        fillColor: tint.active,
        fillOpacity: 0.55 + (count / maxCount) * 0.45,
        color: '#ffffff',
        weight: 1,
      }
    }
    if (highlightSet.has(name)) {
      // This partner's coverage districts — bold, solid brand colour so
      // they clearly stand out from the rest of the country.
      return { fillColor: tint.active, fillOpacity: 0.85, color: '#ffffff', weight: 1 }
    }
    // Rest of the country — neutral body so the national silhouette holds.
    return { fillColor: '#d4dae2', fillOpacity: 0.7, color: '#ffffff', weight: 0.8 }
  }

  // Re-style when activityFeed changes
  useEffect(() => {
    if (!geoJsonRef.current) return
    geoJsonRef.current.eachLayer((layer: Layer) => {
      const f = (layer as unknown as { feature: GeoJSON.Feature }).feature
      const name = normalize((f.properties?.shapeName as string) ?? '')
      ;(layer as unknown as { setStyle: (s: PathOptions) => void }).setStyle(
        districtStyle(name, districtCounts[name] ?? 0)
      )
    })
  }, [activityFeed]) // eslint-disable-line react-hooks/exhaustive-deps

  const styleFeature = (feature?: GeoJSON.Feature): PathOptions => {
    const name = normalize((feature?.properties?.shapeName as string) ?? '')
    return districtStyle(name, districtCounts[name] ?? 0)
  }

  const onEachFeature = (feature: GeoJSON.Feature, layer: Layer) => {
    const name = (feature.properties?.shapeName as string) ?? 'Unknown'
    const count = districtCounts[normalize(name)] ?? 0
    ;(layer as unknown as { bindTooltip: (s: string, o: object) => void }).bindTooltip(
      `${name}: ${count} submission${count !== 1 ? 's' : ''}`,
      { direction: 'top', className: 'leaflet-tooltip-custom' }
    )
  }

  const mappableCenters = centers.filter(
    (c) => c.latitude !== null && c.longitude !== null
  )

  return (
    <div className={className} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {error && (
        <div className="flex h-80 items-center justify-center rounded-xl bg-gray-100 dark:bg-gray-800 text-gray-400 text-sm">
          Map unavailable — check internet connection
        </div>
      )}
      {!error && (
        <>
          <MapContainer
            center={[23.7, 90.4]}
            zoom={6}
            maxZoom={10}
            scrollWheelZoom={true}
            zoomControl={true}
            attributionControl={false}
            // No tile basemap — keeps the view to Bangladesh only, so the
            // border never mixes with India. Fills its frame (was a fixed
            // 320px box leaving a large empty band below).
            className="w-full rounded-xl"
            style={{ background: 'var(--surface-2, #eef1f4)', flex: 1, minHeight: 340 }}
          >
            {geoData && (
              <>
                <FitToData data={geoData} />
                <GeoJSON
                  key={JSON.stringify(districtCounts)}
                  data={geoData}
                  style={styleFeature}
                  onEachFeature={onEachFeature}
                  ref={(r) => { if (r) geoJsonRef.current = r }}
                />
              </>
            )}
            {/* Service center markers */}
            {mappableCenters.map((c) => (
              <CircleMarker
                key={c.id}
                center={[c.latitude!, c.longitude!]}
                radius={7}
                pathOptions={{
                  fillColor: CENTER_COLORS[c.center_type] ?? '#6b7280',
                  fillOpacity: 0.9,
                  color: '#fff',
                  weight: 2,
                }}
              >
                <Popup>
                  <div className="text-sm">
                    <p className="font-semibold">{c.name}</p>
                    {c.name_bangla && <p className="font-bangla text-xs text-gray-500">{c.name_bangla}</p>}
                    <p className="mt-1 text-xs text-gray-600">{c.center_type} · {c.district}</p>
                    <p className="text-xs text-gray-500">{c.organisation}</p>
                  </div>
                </Popup>
              </CircleMarker>
            ))}
          </MapContainer>
          {/* Map legend */}
          {mappableCenters.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-3 text-[10px] text-gray-500 dark:text-gray-400">
              {Object.entries(CENTER_COLORS).map(([type, color]) => (
                <span key={type} className="flex items-center gap-1">
                  <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
                  {type}
                </span>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
