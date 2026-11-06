/**
 * MPDSR Atlas — GIS maps of community maternal & neonatal deaths, 2024.
 * Request from Dr Animesh Biswas (UNFPA).
 *
 * Sections:
 *   1. Notification — his 4 maps (district + division × maternal + neonatal),
 *      with an indicator toggle and a choropleth ⇄ proportional-symbol render
 *      toggle, plus a one-click "download all four as one sheet".
 *   2. Year-on-year change — 2023→2024 diverging maps (maternal, neonatal).
 *   3. Response priority — bivariate burden × review-gap maps.
 *   4. Top-10 leaderboard — highest-burden districts.
 *
 * Data: National MPDSR Report 2019–2024 (publ. Dec 2025), community tables.
 */
import { useRef, useState } from 'react'
import { domToPng } from 'modern-screenshot'
import { Download, Info } from 'lucide-react'
import { ChoroplethMap, useDistrictGeo, useDivisionBoundaries, ATLAS_FONT } from '@/components/atlas/ChoroplethMap'
import { BivariateMap } from '@/components/atlas/BivariateMap'
import { MPDSR_2024, MPDSR_TOTALS, type Indicator } from '@/data/mpdsr2024'

const INDICATORS: { key: Indicator; label: string }[] = [
  { key: 'notified', label: 'Deaths notified' },
  { key: 'reviewed', label: 'Deaths reviewed' },
  { key: 'pct',      label: '% reviewed' },
]

function Pill({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick} style={{
      padding: '6px 14px', borderRadius: 999, fontSize: 13, cursor: 'pointer',
      fontWeight: active ? 600 : 500,
      background: active ? 'rgba(249,96,0,0.10)' : 'var(--surface-2)',
      color: active ? 'var(--unfpa, #F96000)' : 'var(--ink-3)',
      border: active ? '1px solid rgba(249,96,0,0.32)' : '1px solid var(--hair)',
      transitionProperty: 'background-color,color,border-color', transitionDuration: '160ms',
    }}>{children}</button>
  )
}

function SectionHead({ kicker, title, sub, read, take }: {
  kicker: string; title: string; sub: string; read?: string; take?: string
}) {
  return (
    <div style={{ margin: '34px 0 14px' }}>
      <div className="kicker" style={{ marginBottom: 6 }}>
        <span className="dot" style={{ background: '#a50f15' }} />{kicker}
      </div>
      <h2 style={{ margin: 0, fontSize: 19, fontWeight: 700, color: 'var(--ink)' }}>{title}</h2>
      <p style={{ margin: '4px 0 0', fontSize: 12.5, color: 'var(--muted)', maxWidth: 820 }}>{sub}</p>
      {(read || take) && (
        <div style={{
          marginTop: 10, display: 'flex', gap: 10, alignItems: 'flex-start',
          background: 'rgba(249,96,0,0.06)', border: '1px solid rgba(249,96,0,0.18)',
          borderRadius: 10, padding: '10px 13px', maxWidth: 820,
        }}>
          <Info size={15} style={{ color: 'var(--unfpa, #F96000)', flexShrink: 0, marginTop: 1 }} />
          <div style={{ fontSize: 12.5, lineHeight: 1.55, color: 'var(--ink-2)' }}>
            {read && <div><b>How to read it:</b> {read}</div>}
            {take && <div style={{ marginTop: read ? 3 : 0 }}><b>What it tells you:</b> {take}</div>}
          </div>
        </div>
      )}
    </div>
  )
}

export default function MpdsrAtlas() {
  const [indicator, setIndicator] = useState<Indicator>('notified')
  const { geoData, geoError } = useDistrictGeo()
  const divBounds = useDivisionBoundaries()
  const sheetRef = useRef<HTMLDivElement>(null)
  const [sheetBusy, setSheetBusy] = useState(false)

  const downloadSheet = async () => {
    if (!sheetRef.current) return
    setSheetBusy(true)
    try {
      const png = await domToPng(sheetRef.current, {
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
      a.download = `MPDSR2024_notification_4maps.png`; a.click()
    } finally { setSheetBusy(false) }
  }

  const topMaternal = [...MPDSR_2024].sort((a, b) => b.maternal.notified - a.maternal.notified).slice(0, 10)
  const topNeonatal = [...MPDSR_2024].sort((a, b) => b.neonatal.notified - a.neonatal.notified).slice(0, 10)

  return (
    <div className="mx-auto max-w-7xl px-4 pt-6 sm:px-6 lg:px-8" style={{ paddingBottom: 72, fontFamily: ATLAS_FONT }}>
      {/* Header */}
      <div style={{ marginBottom: 16 }}>
        <div className="kicker" style={{ marginBottom: 8 }}>
          <span className="dot" style={{ background: '#a50f15' }} />NATIONAL MPDSR · GIS ATLAS · 2024
        </div>
        <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800, color: 'var(--ink)', letterSpacing: '-0.02em' }}>
          Maternal &amp; neonatal death mapping
        </h1>
        <p style={{ margin: '6px 0 0', fontSize: 13.5, color: 'var(--muted)', maxWidth: 780, lineHeight: 1.5 }}>
          Community-level death notification across all 64 districts and 8 divisions of Bangladesh, 2024.
          Maternal in red, neonatal in blue. Source: National MPDSR Report 2019–2024 (community review tables).
        </p>
        <div style={{ display: 'flex', gap: 16, marginTop: 12, flexWrap: 'wrap', fontSize: 12.5, color: 'var(--ink-3)' }}>
          <span><b style={{ color: '#a50f15' }}>{MPDSR_TOTALS.maternal.notified.toLocaleString()}</b> maternal deaths notified</span>
          <span><b style={{ color: '#08519c' }}>{MPDSR_TOTALS.neonatal.notified.toLocaleString()}</b> neonatal deaths notified</span>
        </div>
      </div>

      {/* What's on this page — plain guide */}
      <div style={{
        background: 'var(--surface-2)', border: '1px solid var(--hair)', borderRadius: 12,
        padding: '14px 16px', marginTop: 6, fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.6,
      }}>
        <div style={{ fontWeight: 700, color: 'var(--ink)', marginBottom: 4 }}>What's on this page</div>
        Four sections, simplest first:
        <b> 1) Death notification</b> — where deaths were reported (the 4 maps requested).
        <b> 2) What changed since 2023</b> — did reporting go up or down vs last year.
        <b> 3) Where to act first</b> — districts with many deaths but very few reviewed.
        <b> 4) Top-10 districts</b> — the highest-burden districts in a list.
        Every map has a legend (bottom-left) and a <b>Download PNG</b> button for your reports.
      </div>

      {/* ── Section 1: Notification (the 4 requested maps) ── */}
      <SectionHead
        kicker="REQUESTED · 4 MAPS"
        title="Death notification"
        sub="District and divisional notification — the four maps requested. Use the toggle to shade by deaths notified, reviewed, or % reviewed."
        read="Each area is shaded by how many deaths were reported there in 2024. Darker = more deaths reported. Maternal maps are red, neonatal maps are blue. Hover any district for its exact numbers."
        take="Where the most maternal / neonatal deaths are being reported across the country."
      />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, alignItems: 'center', marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600 }}>Shade by</span>
          {INDICATORS.map(({ key, label }) => <Pill key={key} active={indicator === key} onClick={() => setIndicator(key)}>{label}</Pill>)}
        </div>
        <button onClick={downloadSheet} disabled={sheetBusy} style={{
          marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12.5, fontWeight: 600,
          color: '#fff', background: 'var(--unfpa, #F96000)', border: 'none', borderRadius: 8, padding: '7px 14px', cursor: sheetBusy ? 'wait' : 'pointer',
        }}>
          <Download size={14} /> {sheetBusy ? 'Building sheet…' : 'Download all 4 (one sheet)'}
        </button>
      </div>

      <div ref={sheetRef} className="atlas-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 18 }}>
        <ChoroplethMap metric="maternal" level="district" indicator={indicator} geoData={geoData} geoError={geoError} />
        <ChoroplethMap metric="neonatal" level="district" indicator={indicator} geoData={geoData} geoError={geoError} />
        <ChoroplethMap metric="maternal" level="division" indicator={indicator} geoData={geoData} geoError={geoError} boundaryGeo={divBounds} />
        <ChoroplethMap metric="neonatal" level="division" indicator={indicator} geoData={geoData} geoError={geoError} boundaryGeo={divBounds} />
      </div>

      {/* ── Section 2: Year-on-year change ── */}
      <SectionHead
        kicker="INNOVATION · PROGRESS"
        title="What changed since 2023"
        sub="The same districts, but coloured by how this year's reporting compares with last year's."
        read="We subtracted each district's 2023 reported deaths from its 2024 number. BLUE = more deaths were reported in 2024 than 2023 (usually means reporting / surveillance improved). RED = fewer were reported this year. GREY = little change. Hover a district to see '2023 → 2024'."
        take="Blue districts are reporting better than last year; red districts reported fewer than last year — worth asking whether deaths are being missed there."
      />
      <div className="atlas-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 18 }}>
        <ChoroplethMap metric="maternal" level="district" indicator="notified" mode="change" geoData={geoData} geoError={geoError} />
        <ChoroplethMap metric="neonatal" level="district" indicator="notified" mode="change" geoData={geoData} geoError={geoError} />
      </div>

      {/* ── Section 3: Response priority (bivariate) ── */}
      <SectionHead
        kicker="INNOVATION · TARGETING"
        title="Where to act first"
        sub="One map that combines two things at once: how many deaths a district has, and how few of them are being reviewed."
        read="Colour mixes two scales. Going UP = more deaths (bigger problem). Going RIGHT = fewer of those deaths reviewed (bigger gap). So the DARK-BLUE corner = many deaths AND almost none reviewed. Pale grey = few deaths and most reviewed. The little 3×3 key (bottom-left) shows the mix."
        take="Dark-blue districts are where review is weakest relative to need — act there first. Example: Chittagong had 107 maternal deaths but only ~1% reviewed."
      />
      <div className="atlas-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 18 }}>
        <BivariateMap metric="maternal" geoData={geoData} geoError={geoError} />
        <BivariateMap metric="neonatal" geoData={geoData} geoError={geoError} />
      </div>

      {/* ── Section 4: Leaderboard ── */}
      <SectionHead kicker="HIGHEST BURDEN" title="Top-10 districts by deaths notified (2024)" sub="The districts carrying the most notified deaths." />
      <div className="atlas-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 18 }}>
        <LeaderTable title="Maternal" color="#a50f15" rows={topMaternal.map(r => ({ d: r.district, n: r.maternal.notified, p: r.maternal.pct }))} />
        <LeaderTable title="Neonatal" color="#08519c" rows={topNeonatal.map(r => ({ d: r.district, n: r.neonatal.notified, p: r.neonatal.pct }))} />
      </div>

      <style>{`@media (max-width: 920px){ .atlas-grid{ grid-template-columns: 1fr !important; } }`}</style>
    </div>
  )
}

function LeaderTable({ title, color, rows }: { title: string; color: string; rows: { d: string; n: number; p: number }[] }) {
  const max = Math.max(1, ...rows.map(r => r.n))
  return (
    <div className="card" style={{ padding: 16 }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--ink)', marginBottom: 10 }}>
        <span style={{ display: 'inline-block', width: 9, height: 9, borderRadius: 2, background: color, marginRight: 7 }} />{title}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
        {rows.map((r, i) => (
          <div key={r.d} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 12.5 }}>
            <span style={{ width: 16, color: 'var(--muted)', fontVariantNumeric: 'tabular-nums' }}>{i + 1}</span>
            <span style={{ width: 110, color: 'var(--ink-2)' }}>{r.d}</span>
            <div style={{ flex: 1, height: 8, background: 'var(--surface-3)', borderRadius: 4, overflow: 'hidden' }}>
              <div style={{ width: `${(r.n / max) * 100}%`, height: '100%', background: color, borderRadius: 4 }} />
            </div>
            <span style={{ width: 34, textAlign: 'right', fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{r.n}</span>
            <span style={{ width: 42, textAlign: 'right', fontSize: 11, color: 'var(--muted)' }}>{r.p}% rev</span>
          </div>
        ))}
      </div>
    </div>
  )
}
