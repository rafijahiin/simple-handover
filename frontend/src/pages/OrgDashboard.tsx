/**
 * OrgDashboard — editorial light console for PHD and Bondhu.
 *
 * Matches the design prototype: hero section with partner headline,
 * KPI tiles, stacked area chart, and form grid.
 *
 * Data hierarchy:
 *  1. Real programs API (/api/dashboard/programs-summary/) — used when total > 0
 *  2. Mock data from mockDashboardData.ts — used while no real submissions exist
 */
import { useState, useEffect } from 'react'
import { useReducedMotion } from 'motion/react'
import { useTranslation } from 'react-i18next'
import {
  AreaChart, Area,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import {
  Activity, TrendingUp, TrendingDown,
  Stethoscope, HeartHandshake, Megaphone,
  FileText, Heart,
  Info,
} from 'lucide-react'
import { api } from '@/api/client'
import { usePolling } from '@/hooks/usePolling'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { BangladeshMap } from '@/components/maps/BangladeshMap'
import { PartnerOverlapMap } from '@/components/maps/PartnerOverlapMap'
import { SourceChip } from '@/components/ui/SourceChip'
import { IndicatorGrid } from '@/components/indicators/IndicatorGrid'
import { CumulativeAverageTile } from '@/components/indicators/CumulativeAverageTile'
import { PhdHeadlineCards } from '@/components/phd/PhdHeadlineCards'
import { BandhuHeadlineCards } from '@/components/bandhu/BandhuHeadlineCards'
import { formatDate } from '@/utils/format'
import type { PartnerKPIs, Alert, ProgramsSummary } from '@/types'
import {
  MOCK_PROGRAMS, MOCK_KPIS,
} from '@/data/mockDashboardData'

type Partner = 'PHD' | 'Bandhu'

interface OrgSummaryResponse {
  partner: Partner
  period: string
  ai_summary: string
  generated_at: string
}

// ─── CountUp hook ─────────────────────────────────────────────────────────────

function useCountUp(target: number, dur = 1500) {
  const [v, setV] = useState(0)
  const reduce = useReducedMotion()
  useEffect(() => {
    if (reduce) { setV(target); return }
    let raf: number
    let start: number | null = null
    const step = (ts: number) => {
      if (!start) start = ts
      const p = Math.min((ts - start) / dur, 1)
      setV(Math.round(target * p * p))
      if (p < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [target, dur, reduce])
  return v
}

function CountUp({ value, dur }: { value: number; dur?: number }) {
  return <>{useCountUp(value, dur).toLocaleString()}</>
}

// ─── Sparkline SVG ────────────────────────────────────────────────────────────

function Sparkline({ data, color = 'var(--unfpa)', w = 90, h = 28 }: {
  data: number[]; color?: string; w?: number; h?: number
}) {
  if (!data || data.length < 2) return null
  const max = Math.max(...data, 1)
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - (v / max) * h * 0.85}`).join(' ')
  const areaD = `M0,${h} L${pts.split(' ').map(p => p).join(' L')} L${w},${h}Z`
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ overflow: 'visible' }}>
      <defs>
        <linearGradient id={`sg-${color.replace(/[^a-z0-9]/gi, '')}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.18} />
          <stop offset="100%" stopColor={color} stopOpacity={0.02} />
        </linearGradient>
      </defs>
      <path d={areaD} fill={`url(#sg-${color.replace(/[^a-z0-9]/gi, '')})`} />
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// ─── KPI Tile ─────────────────────────────────────────────────────────────────

interface TileProps {
  label: string
  sub: string
  value: number
  delta?: number
  color: string
  icon: React.ReactNode
  spark?: number[]
}

function Tile({ label, sub, value, delta, color, icon, spark }: TileProps) {
  const colorVar = `var(--${color})`
  return (
    <div className="tile">
      <div className="tile-head">
        <div className="tile-ico" style={{ background: `${colorVar}1A`, color: colorVar }}>
          {icon}
        </div>
        <div>
          <div className="tile-label">{label}</div>
          <div className="tile-sub">{sub}</div>
        </div>
      </div>
      <div className="tile-num" style={{ color: colorVar }}>
        <CountUp value={value} />
      </div>
      {delta != null && delta !== 0 && (
        <div className={`tile-delta ${delta > 0 ? 'up' : 'down'}`}>
          {delta > 0 ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
          {delta > 0 ? '+' : ''}{delta.toFixed(1)}%
        </div>
      )}
      {spark && spark.length > 1 && (
        <div className="tile-spark">
          <Sparkline data={spark} color={colorVar} />
        </div>
      )}
    </div>
  )
}

// ─── SectionHead ──────────────────────────────────────────────────────────────

function SectionHead({ kicker, title, sub, right }: {
  kicker: string; title: string; sub?: string; right?: React.ReactNode
}) {
  return (
    <div className="section-head">
      <div>
        <div className="kicker"><span className="dot" />{kicker}</div>
        <h2 className="section-title">{title}</h2>
        {sub && <p className="section-sub">{sub}</p>}
      </div>
      {right}
    </div>
  )
}

// ─── Chart tooltip ────────────────────────────────────────────────────────────

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="card" style={{
      padding: '10px 14px', fontSize: 12, minWidth: 140,
      boxShadow: '0 8px 30px rgba(0,0,0,.12)', border: '1px solid var(--hair)',
    }}>
      <div style={{ fontWeight: 600, marginBottom: 6, fontFamily: 'var(--mono)', fontSize: 10.5, color: 'var(--muted)' }}>{label}</div>
      {payload.map((p: any) => (
        <div key={p.name} style={{ display: 'flex', justifyContent: 'space-between', gap: 18, marginTop: 3 }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: p.color }} />
            {p.name}
          </span>
          <b style={{ fontVariantNumeric: 'tabular-nums' }}>{(p.value ?? 0).toLocaleString()}</b>
        </div>
      ))}
    </div>
  )
}

// ─── Form box ─────────────────────────────────────────────────────────────────

function FormBox({ form }: { form: { key: string; label: string; label_bn?: string; count: number; category: string } }) {
  const catColor =
    form.category === 'Clinical' ? 'var(--unfpa-bright)' :
    form.category === 'Community' ? 'var(--coral)' :
    form.category === 'Operations' ? 'var(--amber)' : 'var(--violet)'
  const CatIcon =
    form.category === 'Clinical' ? Stethoscope :
    form.category === 'Community' ? Megaphone :
    form.category === 'Operations' ? HeartHandshake : Activity
  return (
    <div className="card snug" style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
      <span style={{
        width: 40, height: 40, borderRadius: 11,
        background: `${catColor}1A`, color: catColor,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0,
      }}>
        <CatIcon size={18} />
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13.5, fontWeight: 500 }}>{form.label}</div>
      </div>
      <div className="num-display" style={{ fontSize: 26, color: catColor, fontFamily: 'var(--display)', fontStyle: 'italic' }}>
        {form.count}
      </div>
    </div>
  )
}

// ─── Meta block ───────────────────────────────────────────────────────────────

function Meta({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div>
      <div className="kicker" style={{ marginBottom: 4 }}><span className="dot" />{label}</div>
      <div style={{ fontSize: 14, fontWeight: 500 }}>{value}</div>
      <div className="mono mute" style={{ fontSize: 11, marginTop: 2 }}>{sub}</div>
    </div>
  )
}

// ─── HeroMap (Leaflet) ────────────────────────────────────────────────────────
// Uses the shared BangladeshMap component with GeoJSON + OpenStreetMap tiles.

// ─── Main component ───────────────────────────────────────────────────────────

interface Props {
  partner: Partner
}

export function OrgDashboard({ partner }: Props) {
  const isPHD = partner === 'PHD'
  const { t } = useTranslation()

  // ── Real API data ──────────────────────────────────────────────────────────

  // null = let the backend open on the latest month that actually has data
  // (a partner whose data is all from last month must not land on an empty
  // current month). Once the user picks from the selector, it pins that month.
  const [period, setPeriod] = useState<{ year: number; month: number } | null>(null)

  const { data: programs, loading: programsLoading } = usePolling<ProgramsSummary>({
    fetcher: () => {
      const q = period ? `&year=${period.year}&month=${period.month}` : ''
      return api.get(`/dashboard/programs-summary/?partner=${partner}${q}`).then((r) => r.data)
    },
    interval: 60_000,
    deps: [partner, period?.year, period?.month],
  })

  const { data: kpis, loading: kpisLoading } = usePolling<PartnerKPIs>({
    fetcher: () =>
      api.get(`/dashboard/partner-kpis/?partner=${partner}`).then((r) => r.data),
    interval: 30_000,
  })

  const { data: summary } = usePolling<OrgSummaryResponse>({
    fetcher: () =>
      api.get(`/dashboard/org-summary/?partner=${partner}`).then((r) => r.data),
    interval: 5 * 60_000,
  })

  usePolling<Alert[]>({
    fetcher: () =>
      api
        .get(`/dashboard/alerts/?partner=${partner}&acknowledged=false`)
        .then((r) => (Array.isArray(r.data) ? r.data : (r.data?.results ?? []))),
    interval: 60_000,
  })

  // ── Mock fallback ──────────────────────────────────────────────────────────

  // Demo fallback retired — the system is live, so the dashboard shows REAL
  // data even when it's zero/sparse. Showing illustrative numbers (e.g.
  // "1,156 submissions") behind a small badge is misleading in a partner
  // review. The mock structures remain only as a transient shape-default
  // while the very first request is still in flight (programs/kpis null).
  const usingMock = false
  const displayPrograms: ProgramsSummary = programs ?? MOCK_PROGRAMS[partner]
  const displayKpis: PartnerKPIs = kpis ?? MOCK_KPIS[partner]

  const categories = displayPrograms.categories ?? {}
  const monthlyTrend = displayPrograms.monthly_trend ?? []
  // Form grid always uses the LIVE programs data (never the mock fallback), so
  // it shows this org's REAL form types — at 0 before launch — instead of the
  // generic demo list. Empty only while the first request is still loading.
  const topForms = programs?.top_forms ?? []
  const availableMonths = programs?.available_months ?? []
  // The month the panel is currently showing (backend echoes it back). Drives
  // the selector's value so it reflects the auto-picked latest-with-data month.
  const selectedMonthKey =
    programs?.year && programs?.month ? `${programs.year}-${programs.month}` : ''

  const sparkClinical = monthlyTrend.map((m) => m.clinical)
  const sparkCommunity = monthlyTrend.map((m) => m.community)

  const totalSubmissions = displayPrograms.total
  const momChange = displayPrograms.mom_change

  if (kpisLoading && !kpis && programsLoading) return <PageLoader />

  const dateStr = new Date().toLocaleString('en-US', { month: 'long', year: 'numeric' }).toUpperCase()

  return (
    <>
      {/* ═══════════════════════════════════════════════════════════════
           HERO
           ═══════════════════════════════════════════════════════════════ */}
      <section className="hero" style={{ paddingBottom: 20 }}>
        <div className="hero-eyebrow anim-rise">
          <span className="live-dot" />
          <span>{t('org.eyebrowImplementingPartner')}</span>
          <span className="sep">/</span>
          <span>{isPHD ? t('org.eyebrowPhdFull') : t('org.eyebrowBondhuFull')}</span>
          <span className="sep">/</span>
          <span>{dateStr}</span>
          {usingMock && (
            <>
              <span className="sep">/</span>
              <span className="tag amber" style={{ marginLeft: 4, fontSize: 10.5 }}>
                <Info size={10} style={{ marginRight: 3 }} />{t('org.demoData')}
              </span>
            </>
          )}
        </div>

        <div className="hero-grid">
          <div>
            {/* Headline treatment is identical across all partners (UNFPA
                orange italic display serif via .figure) — only the text
                differs. Matches CIPRB and PHD heroes. */}
            <h1 className="hero-headline anim-rise d1" style={{ marginBottom: 6, fontSize: 'clamp(56px, 9vw, 132px)', letterSpacing: '-0.035em' }}>
              <span className="figure">{partner}</span>
            </h1>
            <p className="hero-tagline anim-rise d1" style={{
              fontSize: 13, color: 'var(--ink-3)', marginTop: 4, marginBottom: 14,
              letterSpacing: '0.01em', fontWeight: 500,
            }}>
              {isPHD
                ? 'Partners in Health and Development'
                : 'Key Population SRHR, HIV & GBV Response'}
            </p>
            {!isPHD && (
              <p className="hero-lede anim-rise d2">
                Bandhu implements essential Sexual and Reproductive Health and Rights (SRHR) related
                activities including HIV/AIDS prevention, legal support, capacity building and policy
                advocacy to bring positive changes and address social, religious, cultural and legal
                impediments to the protection of human rights. Bandhu mainly works to support the{' '}
                <b>Gender Diverse Population (GDP)</b> who often face serious difficulties in accessing
                citizen services. The principles, activities and approaches of Bandhu correspond to
                national priorities for health care interventions and are directly linked with the
                current National Strategic Plan for HIV/AIDS response. All of Bandhu&rsquo;s work is
                being carried out within the framework of health as a fundamental human right as
                outlined in the National Health Policy.
              </p>
            )}

            {/* Partner & project brief (PHD) — supplied by PHD Project Director
                K.S.M. Tarique. Fills the hero's left column and gives context
                next to the live numbers. PHD-only; Bandhu's partner descriptor
                is rendered as its hero lede above (no ABOUT/PROJECT split). */}
            {isPHD && (
              <div className="anim-rise d3" style={{ marginTop: 20, paddingTop: 18, borderTop: '1px solid var(--hair)', maxWidth: 560 }}>
                <div className="kicker" style={{ marginBottom: 8 }}><span className="dot" />ABOUT THE PARTNER</div>
                <p style={{ fontSize: 12.5, lineHeight: 1.62, color: 'var(--ink-3)', marginBottom: 16, textWrap: 'pretty' }}>
                  Partner in Health and Development (PHD) is a non-profit that has spent over three
                  decades improving the lives of marginalized communities in Bangladesh. Through
                  strategic partnerships, they implement development and livelihood programs, provide
                  humanitarian response, and deliver technical assistance to strengthen government and
                  development sectors. Their core expertise includes fund management, systems
                  strengthening, HR development, capacity building, and research.
                </p>
                <div className="kicker" style={{ marginBottom: 8 }}><span className="dot" />THE PROJECT</div>
                <p style={{ fontSize: 12.5, lineHeight: 1.62, color: 'var(--ink-3)', marginBottom: 0, textWrap: 'pretty' }}>
                  PHD, with support from <b style={{ color: 'var(--ink-2)' }}>UNFPA&nbsp;|&nbsp;Sida</b>, is
                  implementing a project titled{' '}
                  <span style={{ color: 'var(--ink-2)', fontStyle: 'italic' }}>&ldquo;Strengthening access
                  to integrated Sexual and Reproductive Health and Rights (SRHR) services for
                  brothel-based female sex workers (FSWs) in selected districts of Bangladesh.&rdquo;</span>{' '}
                  Operating across <b style={{ color: 'var(--ink-2)' }}>11 brothels in 9 districts</b>{' '}
                  (Rajbari, Faridpur, Khulna, Tangail, Jashore, Jamalpur, Mymensingh, Bagerhat, and
                  Patuakhali), the initiative aims to improve health outcomes for marginalized FSWs. To
                  achieve this, the project will establish <b style={{ color: 'var(--ink-2)' }}>9
                  community-led wellness centers</b> and <b style={{ color: 'var(--ink-2)' }}>44
                  Gender-Based Violence (GBV) Corners</b> within public facilities, delivering integrated,
                  rights-based, and stigma-free services covering SRHR, HIV/STI prevention, mental health,
                  and GBV response. Ultimately, the intervention leverages peer-led outreach and enhanced
                  government linkages to build an equitable, survivor-centered healthcare support system.
                </p>
              </div>
            )}

          </div>

          <div className="hero-right anim-rise d4">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
              <div className="kicker" style={{ marginBottom: 0 }}>
                <span className="dot" />COVERAGE
              </div>
            </div>
            <div className="card shimmer" style={{ padding: 10 }}>
              <PartnerOverlapMap height={340} partner={partner} />
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════
           KPI TILES
           PHD → the five SIDA headline indicators (FSWs / centres / outreach
           / providers / GBV corners) via the indicator engine. Bandhu keeps
           its legacy programme tiles until its own headline set is confirmed.
           ═══════════════════════════════════════════════════════════════ */}
      <section className="section" style={{ marginTop: 24 }}>
        {/* Approval visibility: field data is PENDING until approved and the
            figures below count APPROVED only — without this, a manager who
            never opens /approvals sees permanent zeros and thinks it's broken.
            (Bandhu needs a 2nd UNFPA sign-off before anything counts.) */}
        {((kpis?.pending ?? 0) > 0 || (kpis?.pending_unfpa ?? 0) > 0) && (
          <a href="/approvals" style={{
            display: 'block', textDecoration: 'none', marginBottom: 16,
            padding: '12px 16px', borderRadius: 12,
            background: 'rgba(233,151,10,0.08)', border: '1px solid rgba(233,151,10,0.32)',
            color: 'var(--ink)', fontSize: 13.5, lineHeight: 1.5,
          }}>
            {isPHD ? (
              <>
                ⏳ <b>{kpis?.pending}</b> submission{(kpis?.pending ?? 0) === 1 ? '' : 's'} awaiting approval
                {' '}— <b>not counted</b> in the figures below until approved. Open Approvals →
              </>
            ) : (
              // Bandhu two-stage: show BOTH gates so a manager approval visibly
              // moves work from the manager bucket to the UNFPA bucket, instead
              // of the number dropping to zero while the data is still frozen.
              <>
                ⏳ Awaiting approval (nothing below counts until <b>UNFPA</b> signs off):
                <span style={{ display: 'block', marginTop: 4 }}>
                  • <b>{kpis?.pending ?? 0}</b> awaiting <b>Bandhu manager</b> review
                </span>
                <span style={{ display: 'block' }}>
                  • <b>{kpis?.pending_unfpa ?? 0}</b> manager-approved — awaiting <b>UNFPA</b> final sign-off
                </span>
                <span style={{ display: 'block', marginTop: 4, color: 'var(--muted)' }}>
                  Open Approvals →
                </span>
              </>
            )}
          </a>
        )}
        {isPHD ? <PhdHeadlineCards /> : <BandhuHeadlineCards />}
        <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 12, fontStyle: 'italic' }}>
          These figures count <b>approved records only</b>{isPHD ? '' : ' (after manager + UNFPA sign-off)'}.
        </p>
      </section>

      {/* "Programme delivery" stacked area removed per Animesh — categories
          were synthetic (Clinical/Community/Operations) and the chart didn't
          tell a programmatic story at our data volume. Monthly trend lives in
          the indicator-level monthly target view instead. */}

      {/* ═══════════════════════════════════════════════════════════════
           FORM GRID
           ═══════════════════════════════════════════════════════════════ */}
      {(topForms.length > 0 || availableMonths.length > 0) && (
        <section className="section" style={{ marginTop: 56 }}>
          <SectionHead
            kicker={t('org.sectionFormsKicker')}
            title={t('org.sectionFormsTitle')}
            sub={t('org.sectionFormsSub')}
            right={
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                {availableMonths.length > 0 && (
                  <select
                    aria-label="Month"
                    value={selectedMonthKey}
                    onChange={(e) => {
                      const [y, m] = e.target.value.split('-').map(Number)
                      setPeriod({ year: y, month: m })
                    }}
                    style={{
                      appearance: 'none', cursor: 'pointer',
                      background: 'var(--surface)', color: 'var(--ink)',
                      border: '1px solid var(--hair)', borderRadius: 10,
                      padding: '6px 12px', fontSize: 13, fontWeight: 600,
                    }}
                  >
                    {availableMonths.map((mo) => (
                      <option key={`${mo.year}-${mo.month}`} value={`${mo.year}-${mo.month}`}>
                        {mo.label}
                      </option>
                    ))}
                  </select>
                )}
                <SourceChip>{isPHD ? 'PHD 1 + PHD 2' : 'Bandhu 1 + Bandhu 2'}</SourceChip>
              </div>
            }
          />
          {topForms.length > 0 ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14 }}>
              {topForms.map((f) => (
                <FormBox key={f.key} form={f} />
              ))}
            </div>
          ) : (
            <div className="card" style={{ padding: '28px 20px', color: 'var(--muted)', fontSize: 14 }}>
              No submissions recorded for this month.
            </div>
          )}
        </section>
      )}

      {/* Anomaly Detection lives on the home page only — the partner
          dashboards already show submission counts, indicator progress
          and review backlogs through their own KPI tiles. Repeating it
          here also hit a 403 for focal-role users who don't have access
          to /api/dashboard/alerts/. */}

      {/* ═══════════════════════════════════════════════════════════════
           M&E INDICATOR PROGRESS
           ═══════════════════════════════════════════════════════════════ */}
      <section className="section" style={{ marginTop: 56 }}>
        <SectionHead
          kicker={t('org.sectionIndicatorKicker')}
          title={t('org.sectionIndicatorTitle')}
          sub={t('org.sectionIndicatorSub')}
        />
        {/* Cumulative average tile — Animesh's "single unified progress %"
            for the whole partner. Simple mean of every indicator's %.
            Bandhu (18 indicators) gets the most value here, but PHD also
            sees its 22-indicator average at a glance. */}
        <CumulativeAverageTile
          org={partner}
          periodStart="2026-05-21"
          periodEnd="2026-11-20"
        />
        <div className="card shimmer">
          <IndicatorGrid
            org={partner}
            periodStart="2026-05-21"
            periodEnd="2026-11-20"
          />
        </div>
      </section>

      {/* Centres / "active districts" table removed 2026-06-30: the 14-day
          trend sparkline was synthesised from the current count (not real
          history), and the "KoboSubmissions" source label was inaccurate -
          PHD/Bandhu field data lives in the programs models, not the legacy
          KoboSubmission table. */}

      {/* AI Weekly Summary card removed per Animesh — placeholder narrative
          at low data volume read as filler; the indicator grid + KPI tiles
          carry the programmatic story. */}
    </>
  )
}

// ─── Legend dot helper ────────────────────────────────────────────────────────

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--muted)' }}>
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: color }} />
      {label}
    </span>
  )
}
