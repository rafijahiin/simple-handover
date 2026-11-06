/**
 * The donor district map for a CIPRB programme, with its live review-record
 * counts beside it.
 *
 * The map itself is the printed A4 sheet this project produces from
 * scratchpad/make_donor_maps.py, the one CIPRB holds on paper. Dr. Tanjina's
 * 6 October file asked for those sheets in SIMPLE, so there is one renderer
 * and one appearance in print and on screen. The Leaflet choropleth that used
 * to sit here drew the same district lists a second way, which meant two
 * pictures of one fact that could drift apart, and it carried its own legend
 * duplicating the legend printed on the sheet.
 *
 * Re-render the sheets (make_donor_maps.py) after any change to the donor
 * lists in donorDistricts.ts. The PNG is a build artefact, not a drawing.
 *
 * What the sheet cannot show is live data, so the review-record counts per
 * district stay, and that is the reason this is still a component rather than
 * a bare image.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '@/api/client'
import type { DonorProject } from '@/data/donorDistricts'

const CIPRB_BLUE = '#F96000'

/** Written by make_donor_maps.py into public/maps in the same run that
 *  produces the print PDFs. */
const SHEET: Record<DonorProject, { src: string; alt: string }> = {
  mpdsr: {
    src: '/maps/MPDSR_districts_by_donor.png',
    alt: 'MPDSR districts. CIPRB and UNFPA supported districts coloured by donor. Twelve districts.',
  },
  fistula: {
    src: '/maps/Fistula_districts_by_donor.png',
    alt: 'End Obstetric Fistula districts. CIPRB and UNFPA supported districts coloured by donor. Fourteen districts.',
  },
}

export function MPDSRDistrictMap({ districts, project = 'mpdsr' }: {
  districts?: readonly string[] | null
  project?: DonorProject
} = {}) {
  const { t } = useTranslation()
  const [records, setRecords] = useState<Record<string, number> | null>(null)

  // The sheet is portrait, so a card wide enough for it leaves space beside
  // it whatever its size. Rather than pad that with nothing, the review
  // records per district sit there: same geography, read as numbers instead
  // of colour. Honours ?districts= so the panel never disagrees with the
  // donor pill above it.
  const districtsKey = districts ? districts.join(',') : ''
  useEffect(() => {
    if (project !== 'mpdsr') return      // the fistula sheet has no review records
    let cancelled = false
    const params: Record<string, string> = {}
    if (districtsKey) params.districts = districtsKey
    api.get<{ records_by_district?: Record<string, number> }>(
      '/mpdsr/aggregates/', { params })
      .then(r => { if (!cancelled) setRecords(r.data?.records_by_district ?? null) })
      .catch(() => { /* the sheet still stands on its own */ })
    return () => { cancelled = true }
  }, [districtsKey, project])

  const sheet = SHEET[project]

  return (
    <div>
      <div className="card campaign-atlas" style={{ padding: 0, overflow: 'hidden' }}>
      {/* Always-light atlas panel, same treatment as the campaign map. */}
      <div style={{ background: '#ffffff', padding: 16, color: '#111827' }}>
        {/* Only the kicker here. The sheet carries its own title, subtitle,
            district count and legend, so repeating them around it would read
            as a mistake. */}
        <div className="kicker" style={{ marginBottom: 12 }}>
          <span className="dot" style={{ background: CIPRB_BLUE }} />
          {t('mpdsrMap.kicker')}
        </div>

        <div style={{
          display: 'flex', gap: 28, alignItems: 'flex-start',
          justifyContent: 'center', flexWrap: 'wrap',
        }}>
          <a href={sheet.src} target="_blank" rel="noopener noreferrer"
             title="Open the full-size sheet"
             style={{ flex: '0 0 auto', maxWidth: '100%', display: 'block' }}>
            <img
              src={sheet.src}
              alt={sheet.alt}
              loading="lazy"
              style={{
                display: 'block', width: 420, maxWidth: '100%', height: 'auto',
                borderRadius: 8,
                // Without this the white sheet dissolves into the white panel.
                outline: '1px solid rgba(0,0,0,0.10)', outlineOffset: -1,
              }}
            />
          </a>

          {/* Review records per district: what the sheet cannot show. */}
          {records && Object.keys(records).length > 0 && (
            <div style={{ flex: '1 1 300px', minWidth: 260, maxWidth: 460 }}>
              <div className="mono" style={{
                fontSize: 10, letterSpacing: '0.08em', color: '#6b7280',
                textTransform: 'uppercase', marginBottom: 10,
              }}>Review records by district</div>
              {(() => {
                const rows = Object.entries(records)
                  .filter(([, v]) => v > 0)
                  .sort((a, b) => b[1] - a[1])
                const total = rows.reduce((sum, [, v]) => sum + v, 0)
                const top = rows.length ? rows[0][1] : 1
                return rows.map(([name, value]) => (
                  <div key={name} style={{
                    display: 'flex', alignItems: 'center', gap: 10, marginBottom: 7,
                  }}>
                    <span style={{
                      flex: '0 0 84px', fontSize: 12, color: '#111827',
                      textTransform: 'capitalize',
                    }}>{name}</span>
                    <div style={{ flex: 1, height: 9, borderRadius: 3, background: '#eceae4' }}>
                      <div style={{
                        width: `${(value / top) * 100}%`, height: 9, minWidth: 3,
                        borderRadius: 3, background: CIPRB_BLUE,
                      }} />
                    </div>
                    <span style={{
                      flex: '0 0 34px', textAlign: 'right', fontSize: 12.5,
                      fontWeight: 700, color: '#111827',
                      fontVariantNumeric: 'tabular-nums',
                    }}>{value.toLocaleString()}</span>
                    <span style={{
                      flex: '0 0 34px', textAlign: 'right', fontSize: 11,
                      color: '#6b7280', fontVariantNumeric: 'tabular-nums',
                    }}>{total ? `${Math.round((value / total) * 100)}%` : ''}</span>
                  </div>
                ))
              })()}
            </div>
          )}
        </div>
      </div>
      </div>
    </div>
  )
}

/** The same card, named for what it draws. Used for the End Obstetric Fistula
 *  donor map on the fistula page, and readable for the MPDSR one. */
export const DonorDistrictMap = MPDSRDistrictMap
