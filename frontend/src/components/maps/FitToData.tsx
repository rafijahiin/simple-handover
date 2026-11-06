/**
 * FitToData — fits the Leaflet view to a GeoJSON layer's bounds once the
 * data loads, and locks panning to that area. Used by the Bangladesh maps so
 * the view frames the country exactly instead of showing the wider region
 * (which made the border bleed into India).
 */
import { useEffect } from 'react'
import { useMap } from 'react-leaflet'
import L from 'leaflet'

export function FitToData({ data }: { data: GeoJSON.FeatureCollection | null }) {
  const map = useMap()

  useEffect(() => {
    if (!data) return
    const bounds = L.geoJSON(data).getBounds()
    if (!bounds.isValid()) return
    // Frame the country with a little breathing room…
    map.fitBounds(bounds, { padding: [10, 10] })
    // …and stop the user panning off into neighbouring countries.
    map.setMaxBounds(bounds.pad(0.12))
    map.setMinZoom(map.getBoundsZoom(bounds) - 0.5)
  }, [data, map])

  return null
}
