/**
 * Baseline studies — CIPRB fieldwork monitoring (D5).
 *
 * Three surfaces on one page:
 *   1. FIELDWORK — pace, per-site/enumerator throughput, duration, quality flags,
 *      over EVERY collected interview. Source: /baseline/responses/monitoring/.
 *   2. SRHR — the major indicators, per questionnaire module.
 *   3. INSIGHTS — the population profile as it builds (age, district, education,
 *      marital, religion, income + NID/mobile KPIs), split by key population.
 *
 * There is no verification queue: baseline is a CIPRB-run research survey, so
 * submissions auto-approve at ingest and there is nothing for a manager to sign
 * off. The /baseline/verification/ endpoints still exist but are unused here.
 *
 * Endpoints (CIPRB-scoped):
 *   GET  /baseline/responses/monitoring/    fieldwork + data quality
 *   GET  /baseline/responses/srhr/          SRHR indicators by module
 *   GET  /baseline/responses/insights/      chart aggregation
 *   GET  /baseline/responses/export/        CSV of every response
 */
import { useMemo, useState } from 'react'
import {
  ShieldCheck, MapPin, CreditCard, Smartphone, CalendarDays,
} from 'lucide-react'
import { api } from '@/api/client'
import { usePolling } from '@/hooks/usePolling'
import { BarBreakdown, DonutBreakdown, ColumnBreakdown, StackedBar } from '@/components/ciprb/IndicatorCharts'
import { BaselineMonitor } from '@/components/baseline/BaselineMonitor'
import { SrhrIndicators, type Srhr } from '@/components/baseline/SrhrIndicators'

type Pop = 'hijra' | 'fsw'
type Lens = 'all' | Pop

interface Bucket { name: string; value: number }
interface PopDim { hijra: Bucket[]; fsw: Bucket[] }
interface Insights {
  total: number
  population: { name: string; key: Pop; value: number }[]
  round: Bucket[]
  kpis: Record<Pop, { n: number; avg_age: number | null; nid_pct: number | null; mobile_pct: number | null }>
  districts_count: number
  age_band: PopDim
  district: PopDim
  education: PopDim
  marital: PopDim
  religion: PopDim
  income_band: PopDim
  hh_income_band: PopDim
  income_covered: Record<Pop, { n: number; hh_n: number; total: number }>
}

const POP_LABEL: Record<string, string> = {
  hijra: 'Hijra / Gender-diverse',
  fsw: 'Female Sex Worker',
}

/** Collapse whitespace and spaces around a slash so near-identical category
 *  labels ("SSC/Dakhil" vs "SSC / Dakhil") merge into one bar instead of two. */
function normName(name: string): string {
  return (name || '').replace(/\s*\/\s*/g, '/').replace(/\s+/g, ' ').trim()
}

// The raw education codes sprawl into ~13 near-duplicate rows ("Class 5–7" vs
// "Grades 5–7", "Bachelor's" vs "Master's"). Fold them into clean ordinal bands
// so the chart reads as an attainment distribution, not a messy code list.
const EDU_BANDS: { match: RegExp; label: string }[] = [
  { match: /no formal|no education|never|illiterate/i, label: 'No formal education' },
  { match: /(^|[^0-9])1\s*[–-]\s*4/i, label: 'Class 1–4' },
  { match: /5\s*[–-]\s*7/i, label: 'Class 5–7' },
  { match: /8\s*[–-]\s*9/i, label: 'Class 8–9' },
  { match: /ssc|dakhil/i, label: 'SSC / Dakhil' },
  { match: /hsc|alim|higher secondary/i, label: 'HSC / Alim' },
  { match: /bachelor|master|honours|graduate|post-?grad|degree/i, label: 'Higher (Bachelor+)' },
  { match: /vocation|technical|trade|diploma/i, label: 'Vocational / technical' },
  { match: /madrasa|qawmi|ebtedayee/i, label: 'Madrasa / other' },
]
const EDU_ORDER = ['No formal education', 'Class 1–4', 'Class 5–7', 'Class 8–9',
  'SSC / Dakhil', 'HSC / Alim', 'Vocational / technical', 'Higher (Bachelor+)', 'Madrasa / other']
function bandEducation(rec: Record<string, number>): Record<string, number> {
  const merged: Record<string, number> = {}
  for (const [k, v] of Object.entries(rec)) {
    const band = EDU_BANDS.find((b) => b.match.test(k))?.label || 'Other'
    merged[band] = (merged[band] || 0) + v
  }
  const out: Record<string, number> = {}
  for (const b of EDU_ORDER) if (merged[b]) out[b] = merged[b]
  if (merged['Other']) out['Other'] = merged['Other']
  return out
}

/** array[{name,value}] -> Record<name, value>; 'all' merges both pops by name. */
function toRecord(dim: PopDim | undefined, lens: Lens): Record<string, number> {
  if (!dim) return {}
  const src = lens === 'all' ? [...dim.hijra, ...dim.fsw] : dim[lens] || []
  const out: Record<string, number> = {}
  for (const b of src) {
    const k = normName(b.name)
    out[k] = (out[k] || 0) + b.value
  }
  return out
}


/** Small KPI chip with an icon — used inside the insights strip. */
function KpiChip({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="card snug" style={{ display: 'flex', alignItems: 'center', gap: 11, minWidth: 168, flex: '1 1 168px' }}>
      <span style={{ display: 'grid', placeItems: 'center', width: 34, height: 34, borderRadius: 9, background: 'rgba(249,96,0,0.10)', color: 'var(--unfpa)', flexShrink: 0 }}>{icon}</span>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 17, fontWeight: 800, color: 'var(--ink)', fontVariantNumeric: 'tabular-nums', lineHeight: 1.1 }}>{value}</div>
        <div style={{ fontSize: 11, color: 'var(--muted)' }}>{label}</div>
      </div>
    </div>
  )
}

export default function BaselineEndline() {
  const { data: insights } = usePolling<Insights>({
    fetcher: () => api.get('/baseline/responses/insights/').then((r) => r.data),
    interval: 60_000,
  })
  const { data: srhr } = usePolling<Srhr>({
    fetcher: () => api.get('/baseline/responses/srhr/').then((r) => r.data),
    interval: 60_000,
  })
  const [lens, setLens] = useState<Lens>('all')

  /** "Taka per month · 42 of 370 answered". A relevance-gated income question is
   *  answered by one branch only, so the band's denominator is NOT the population.
   *  Printing the coverage is what stops a gated field silently shrinking a
   *  published figure the way B104 did. */
  const incomeKicker = (key: 'n' | 'hh_n') => {
    const cov = insights?.income_covered
    if (!cov) return 'Taka per month (banded)'
    const pops: Pop[] = key === 'hh_n' ? ['hijra'] : (lens === 'all' ? ['hijra', 'fsw'] : [lens])
    const answered = pops.reduce((s, p) => s + (cov[p]?.[key] ?? 0), 0)
    const total = pops.reduce((s, p) => s + (cov[p]?.total ?? 0), 0)
    return `Taka per month · ${answered} of ${total} answered`
  }

  // KPI figures for the selected lens.
  const lensKpi = useMemo(() => {
    if (!insights) return { n: 0, avg_age: null as number | null, nid_pct: null as number | null, mobile_pct: null as number | null }
    if (lens === 'all') {
      const h = insights.kpis.hijra, f = insights.kpis.fsw
      const n = h.n + f.n
      const wavg = (a: number | null, an: number, b: number | null, bn: number) =>
        (a == null && b == null) ? null : Math.round(((a || 0) * an + (b || 0) * bn) / Math.max(1, (a != null ? an : 0) + (b != null ? bn : 0)))
      return {
        n,
        avg_age: wavg(h.avg_age, h.n, f.avg_age, f.n),
        nid_pct: wavg(h.nid_pct, h.n, f.nid_pct, f.n),
        mobile_pct: wavg(h.mobile_pct, h.n, f.mobile_pct, f.n),
      }
    }
    return insights.kpis[lens]
  }, [insights, lens])

  const hasInsights = (insights?.total ?? 0) > 0

  return (
    <>
      {/* ── Part 1 · fieldwork monitoring & data quality (compact) ────────── */}
      <section className="section">
        <BaselineMonitor />
      </section>

      {/* ── clean transition into Part 2 · verified baseline results ──────── */}
      <div id="srhr" aria-hidden style={{ scrollMarginTop: 110, margin: '48px 0 0',
        height: 1, background: 'linear-gradient(90deg, transparent, var(--hair) 20%, var(--hair) 80%, transparent)' }} />

      {/* ── Major SRHR indicators, by questionnaire module ────────────────── */}
      {srhr && <SrhrIndicators data={srhr} />}

      {/* ── Insights ─────────────────────────────────────────────────────── */}
      <section className="section" style={{ marginTop: 40 }}>
        <div className="dsec">
          <div>
            <h2 className="dsec-h">Baseline respondent profile</h2>
            <p className="dsec-sub">Who was interviewed — age, income, education, marital status and more, from verified interviews.</p>
          </div>
          <div className="pills">
            {([['all', 'Both'], ['hijra', 'Hijra'], ['fsw', 'FSW']] as const).map(([v, label]) => (
              <button key={v} className={`pill ${lens === v ? 'on' : ''}`} onClick={() => setLens(v as Lens)}>{label}</button>
            ))}
          </div>
        </div>

        {!hasInsights ? (
          <div className="card" style={{ padding: 32, textAlign: 'center', color: 'var(--muted)' }}>
            <ShieldCheck size={26} style={{ opacity: 0.5 }} />
            <p style={{ marginTop: 10, fontSize: 14 }}>No interviews yet. The population profile builds here automatically as interviews arrive.</p>
          </div>
        ) : (
          <>
            {/* KPI strip for the selected lens */}
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
              <KpiChip icon={<ShieldCheck size={17} />} label={lens === 'all' ? 'verified interviews' : `${POP_LABEL[lens]}`} value={String(lensKpi.n)} />
              <KpiChip icon={<MapPin size={17} />} label="districts covered" value={String(insights?.districts_count ?? 0)} />
              <KpiChip icon={<CalendarDays size={17} />} label="average age (years)" value={lensKpi.avg_age != null ? String(lensKpi.avg_age) : '—'} />
              <KpiChip icon={<CreditCard size={17} />} label="have a National ID" value={lensKpi.nid_pct != null ? `${lensKpi.nid_pct}%` : '—'} />
              <KpiChip icon={<Smartphone size={17} />} label="own a mobile phone" value={lensKpi.mobile_pct != null ? `${lensKpi.mobile_pct}%` : '—'} />
            </div>

            {/* Chart grid — a deliberate mix of four distinct shapes so no two
                neighbouring cards read as the same visual: vertical columns for
                ordered bands, ranked horizontal bars for the many-category
                dimensions, solid pies for the few-category splits, and a 100%
                stacked bar. Every card carries counts + percentages. */}
            {/* Feature row: age + income stacked in a narrow left column so the
                marital pie (long, many-category legend) gets a wide slot to
                breathe beside them. */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, alignItems: 'flex-start' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14, flex: '1 1 300px', minWidth: 280 }}>
                <div><ColumnBreakdown title="Age distribution" kicker="Completed age (years)" data={toRecord(insights?.age_band, lens)} /></div>
                {/* Income is not one question. FSW B108 asks earnings FROM SEX WORK;
                    Hijra asks personal income (B106) of dera residents only and
                    HOUSEHOLD earnings (B107) of everyone else. Each card names the
                    quantity it shows and how many respondents answered it — the old
                    single "Monthly income" card banded a Hijra gross share that only
                    42 of 370 were ever asked, and said nothing about the other 328. */}
                <div><ColumnBreakdown
                  title={lens === 'fsw' ? 'Income from sex work'
                    : lens === 'hijra' ? 'Personal income · lives in a dera'
                      : 'Personal income'}
                  kicker={incomeKicker('n')}
                  data={toRecord(insights?.income_band, lens)} /></div>
                {lens !== 'fsw' && (insights?.income_covered?.hijra?.hh_n ?? 0) > 0 && (
                  <div><ColumnBreakdown
                    title="Household income · does not live in a dera"
                    kicker={incomeKicker('hh_n')}
                    data={toRecord(insights?.hh_income_band, lens === 'all' ? 'hijra' : lens)} /></div>
                )}
              </div>
              {/* Marital status has many categories — ranked horizontal bars read
                  far more clearly than a pie with a long legend. */}
              <div style={{ flex: '1.6 1 360px', minWidth: 320, display: 'flex' }}>
                <BarBreakdown title="Marital / partnership status" kicker="Current status" data={toRecord(insights?.marital, lens)} ordered />
              </div>
            </div>

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, marginTop: 14 }}>
              <BarBreakdown title="Highest education" kicker="Educational attainment" data={bandEducation(toRecord(insights?.education, lens))} ordered />
              <StackedBar title="Religion" kicker="Reported religion" data={toRecord(insights?.religion, lens)} />
              {lens === 'all' && (
                /* Two-category split — a donut is fine and reads cleanly here. */
                <DonutBreakdown title="Population reached" kicker="Key population split"
                  data={Object.fromEntries((insights?.population ?? []).map((p) => [normName(p.name), p.value]))} />
              )}
            </div>
          </>
        )}
      </section>

      <div style={{ marginBottom: 80 }} />
    </>
  )
}

/** Full interview answers, grouped by questionnaire section, in plain language. */
