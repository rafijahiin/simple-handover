/**
 * Baseline Monitoring — the compact upper half of /baseline.
 *
 * One sticky filter bar drives every component here via SERVER-side filters on
 * GET /baseline/responses/monitoring/ and GET /baseline/fsw-anomalies/.
 * Sections: compact header → filters+anchors → 6 overview KPIs → collection
 * progress (one toggleable trend + Interview outcomes) → enumerator table →
 * data quality (AnomalyQueue) → collapsed "More diagnostics".
 *
 * These filters are for THIS monitoring surface only — the SRHR/insights
 * sections below keep their own verified-interview queryset untouched.
 */
import { useEffect, useMemo, useState } from 'react'
import {
  Download, RefreshCw, TrendingUp, AlertTriangle,
  CheckCircle2, Search, ChevronDown, X,
} from 'lucide-react'
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid,
} from 'recharts'
import { api, apiErrorMessage } from '@/api/client'
import { BarBreakdown, Histogram } from '@/components/ciprb/IndicatorCharts'
import { AnomalyQueue, type AnomalyReport, type Sev } from './AnomalyQueue'

const ORANGE = '#F96000'   // population: Hijra (also the brand)
const TEAL = '#0E8F8F'     // population: FSW / healthy
const AMBER = 'var(--warn)'

type Pop = 'hijra' | 'fsw'
interface Bucket { name: string; value: number }
interface Collector {
  code: string; n: number; avg_min: number | null
  valid_timing: number; valid_timing_pct: number; median_min: number | null
  completion_pct: number; short: number; long: number; hijra: number; fsw: number
}
export interface Monitoring {
  total: number
  progress: { population: Pop; collected: number; target: number | null; pct: number | null }[]
  outcomes: Bucket[]
  districts: Bucket[]
  sites: Bucket[]
  versions: Bucket[]
  daily: { date: string; hijra: number; fsw: number; total: number }[]
  hourly: { hour: string; hijra: number; fsw: number; total: number }[]
  duration: {
    bands: Bucket[]
    valid_timing_n: number; valid_timing_pct: number
    valid_median_min: number | null; valid_median_n: number
    valid_iqr: (number | null)[]
  }
  collectors: Collector[]
  quality: { gps_pct: number; gps_missing: number; duplicates: number }
}

export interface Filters {
  population: 'all' | Pop
  enumerator: string
  site: string
  version: string
  dateFrom: string
  dateTo: string
  severity: '' | Sev
}
const EMPTY_FILTERS: Filters = {
  population: 'all', enumerator: '', site: '', version: '',
  dateFrom: '', dateTo: '', severity: '',
}

const fmt = (n: number) => n.toLocaleString('en-US')

/* ── small building blocks ────────────────────────────────────────────────── */

function Kpi({ label, value, sub, sub2, title, valueColor }: {
  label: string; value: React.ReactNode; sub?: React.ReactNode
  sub2?: React.ReactNode; title?: string; valueColor?: string
}) {
  return (
    <div className="kpi" title={title} style={{ flex: '1 1 200px', minWidth: 178 }}>
      <div className="kpi-l">{label}</div>
      <div className="kpi-v" style={valueColor ? { color: valueColor } : undefined}>{value}</div>
      {sub && <div className="kpi-s">{sub}</div>}
      {sub2 && <div className="kpi-s2">{sub2}</div>}
    </div>
  )
}

function HBar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 9, fontSize: 13 }}>
      <span style={{ width: 96, color: 'var(--muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
      <span style={{ flex: 1, height: 10, borderRadius: 5, background: 'var(--hair)', overflow: 'hidden' }}>
        <span style={{ display: 'block', height: '100%', width: `${max ? (100 * value) / max : 0}%`, background: color, borderRadius: 5 }} />
      </span>
      <span style={{ width: 38, textAlign: 'right', fontWeight: 700, color: 'var(--ink)', fontVariantNumeric: 'tabular-nums' }}>{fmt(value)}</span>
    </div>
  )
}

function ChartTip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--hair)', borderRadius: 8, padding: '7px 10px', fontSize: 12, boxShadow: '0 6px 18px rgba(0,0,0,.12)' }}>
      <div style={{ fontWeight: 700, marginBottom: 2 }}>{label}</div>
      {payload.map((p: any) => <div key={p.name} style={{ color: p.color }}>{p.name}: <b>{p.value}</b></div>)}
    </div>
  )
}

/* ── the monitor ──────────────────────────────────────────────────────────── */

export function BaselineMonitor() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS)
  const [m, setM] = useState<Monitoring | null>(null)
  const [anoms, setAnoms] = useState<AnomalyReport | null>(null)
  const [lastSync, setLastSync] = useState<Date | null>(null)
  const [err, setErr] = useState('')
  const [exporting, setExporting] = useState(false)
  const [trendMode, setTrendMode] = useState<'daily' | 'cumulative'>('daily')
  const [enumSearch, setEnumSearch] = useState('')
  const [enumSort, setEnumSort] = useState<'n' | 'flags'>('flags')

  const set = (patch: Partial<Filters>) => setFilters((f) => ({ ...f, ...patch }))

  async function load() {
    setErr('')
    const rec = {
      ...(filters.population !== 'all' && { population: filters.population }),
      ...(filters.enumerator && { enumerator: filters.enumerator }),
      ...(filters.site && { site: filters.site }),
      ...(filters.version && { version: filters.version }),
      ...(filters.dateFrom && { date_from: filters.dateFrom }),
      ...(filters.dateTo && { date_to: filters.dateTo }),
    }
    try {
      const [mon, an] = await Promise.all([
        api.get<Monitoring>('/baseline/responses/monitoring/', { params: rec }),
        // `severity` is deliberately NOT sent. The server applies it to the whole
        // report, and that one list feeds three consumers: the enumerator table's
        // flag counts, the severity KPI cards, and the priority-rule list. Filtering
        // it server-side made picking "medium" report every enumerator as "None
        // flagged" and zeroed the other severity cards — the filter was silently
        // rewriting the numbers instead of narrowing the queue. Severity is a QUEUE
        // filter and is applied there, locally.
        api.get<AnomalyReport>('/baseline/fsw-anomalies/', {
          params: { population: filters.population, ...rec },
        }),
      ])
      setM(mon.data)
      setAnoms(an.data)
      setLastSync(new Date())
    } catch (e) {
      setErr(apiErrorMessage(e, 'Could not load monitoring data.'))
    }
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load() }, [JSON.stringify(filters)])

  async function exportCsv() {
    setExporting(true)
    try {
      const r = await api.get('/baseline/responses/export/', {
        responseType: 'blob',
        params: filters.population !== 'all' ? { population: filters.population } : {},
      })
      const url = URL.createObjectURL(r.data as Blob)
      const a = document.createElement('a')
      a.href = url; a.download = 'baseline_responses.csv'
      document.body.appendChild(a); a.click(); a.remove()
      URL.revokeObjectURL(url)
    } catch (e) {
      setErr(apiErrorMessage(e, 'Export failed.'))
    } finally {
      setExporting(false)
    }
  }

  const jump = (id: string) =>
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })

  /* derived series — adaptive resolution: 1 day -> hourly, <=31 days -> daily,
     <=120 -> weekly, longer -> monthly. Empty periods are not connected. */
  const { trend, trendUnit } = useMemo(() => {
    const daily = m?.daily ?? []
    if (daily.length === 1 && (m?.hourly?.length ?? 0) > 0) {
      return { trend: m!.hourly.map((h) => ({ date: h.hour, hijra: h.hijra, fsw: h.fsw, total: h.total })), trendUnit: 'hourly' as const }
    }
    let series = daily
    if (daily.length > 31) {
      const bucket = (d: string) => {
        if (daily.length > 120) return d.slice(0, 7)                     // month
        const dt = new Date(d + 'T00:00:00')
        dt.setDate(dt.getDate() - dt.getDay())                            // week start
        return dt.toLocaleDateString('sv-SE')
      }
      const agg: Record<string, { date: string; hijra: number; fsw: number; total: number }> = {}
      for (const d of daily) {
        const k = bucket(d.date)
        const g = (agg[k] ??= { date: k, hijra: 0, fsw: 0, total: 0 })
        g.hijra += d.hijra; g.fsw += d.fsw; g.total += d.total
      }
      series = Object.values(agg).sort((a, b) => a.date.localeCompare(b.date))
    }
    if (trendMode === 'cumulative') {
      let h = 0, f = 0
      series = series.map((d) => ({ ...d, hijra: (h += d.hijra), fsw: (f += d.fsw), total: h + f }))
    }
    return { trend: series, trendUnit: daily.length > 120 ? 'monthly' as const : daily.length > 31 ? 'weekly' as const : 'daily' as const }
  }, [m, trendMode])

  const todayIso = new Date().toLocaleDateString('sv-SE')
  const collectedToday = m?.daily.find((d) => d.date === todayIso)?.total ?? 0
  const last7 = useMemo(() => {
    const cut = new Date(); cut.setDate(cut.getDate() - 6)
    const cutIso = cut.toLocaleDateString('sv-SE')
    return (m?.daily ?? []).filter((d) => d.date >= cutIso).reduce((s, d) => s + d.total, 0)
  }, [m])

  /* Per-enumerator flag counts AND the distinct interviews those flags sit on
     (same filtered scope). The two differ: one interview with three contradicting
     answers raises three flags. Reporting flags as if they were interviews
     overstates how much of someone's work is affected, so the table shows
     interviews and keeps the raw flag count only for sorting. */
  const flagsByEnum = useMemo(() => {
    const out: Record<string, {
      critical: number; high: number; medium: number; records: Set<string>
    }> = {}
    for (const a of anoms?.anomalies ?? []) {
      if (!a.enumerator) continue
      const g = (out[a.enumerator] ??= { critical: 0, high: 0, medium: 0, records: new Set() })
      if (a.severity === 'critical') g.critical += 1
      else if (a.severity === 'high') g.high += 1
      else if (a.severity === 'medium') g.medium += 1
      if ((a.severity === 'critical' || a.severity === 'high') && a.record_id) {
        g.records.add(a.record_id)
      }
    }
    return out
  }, [anoms])

  const enumerators = useMemo(() => {
    const rows = (m?.collectors ?? []).map((c) => {
      const fl = flagsByEnum[c.code] ?? { critical: 0, high: 0, medium: 0, records: new Set<string>() }
      // Status reflects FLAGGED ANSWERS only. Recorded-length coverage is deliberately
      // NOT part of it: a low figure means the device served an older form version
      // that never saved an end time — not the enumerator's doing.
      //
      // The measure is the SHARE OF THEIR INTERVIEWS that carry a flag, not a count.
      // `high >= 5` marked everyone Urgent: 45 interviews reach 5 flags at an 11%
      // rate while 6 interviews never trip it at 66% — that ranked workload, not
      // data quality. MIN_N stops 1-of-2 reading as 50%.
      // The displayed share and the status GATE are separate. Forcing the rate to 0
      // below MIN_N printed "2/3" beside "0%" — the cell contradicting the count next
      // to it. The share is always the true one; MIN_N only withholds the Urgent
      // verdict, because 1 flag in 2 interviews is not evidence of a 50% fault rate.
      const MIN_N = 5
      const flagged = fl.records.size
      const rate = c.n ? flagged / c.n : 0
      const status: 'urgent' | 'review' | 'good' =
        c.n >= MIN_N && rate >= 0.25 ? 'urgent'
          : flagged >= 1 ? 'review'
            : 'good'
      return { ...c, flags: fl, flagged, rate, status }
    })
    const q = enumSearch.trim().toLowerCase()
    const filtered = q ? rows.filter((r) => r.code.toLowerCase().includes(q)) : rows
    return filtered.sort((a, b) => enumSort === 'n'
      ? b.n - a.n
      // Rank by the same share the status uses, else the top of the table and the
      // Status beside it would disagree about who most needs attention.
      : b.rate - a.rate || b.flagged - a.flagged || b.n - a.n)
  }, [m, flagsByEnum, enumSearch, enumSort])

  // Interviews with at least one HIGH or CRITICAL flag — not "any flag", which
  // would inflate the card (documentation warnings affect most records).
  const affectedHighCrit = useMemo(() => {
    const ids = new Set<string>()
    for (const a of anoms?.anomalies ?? []) {
      if ((a.severity === 'critical' || a.severity === 'high') && a.record_id) ids.add(a.record_id)
    }
    return ids.size
  }, [anoms])

  const target = (m?.progress ?? []).reduce((s, p) => s + (p.target || 0), 0)
  const rangeActive = !!(filters.dateFrom || filters.dateTo)
  const iqr = m?.duration.valid_iqr ?? [null, null]

  const STATUS_STYLE = {
    // The label states the finding rather than grading the person: "Review" named
    // no threshold and meant only "not clean, not urgent". These say what the
    // number is, so the column explains itself without a tooltip.
    good: { label: 'None flagged', cls: 'tag-ok', icon: <CheckCircle2 size={12} /> },
    review: { label: 'Some flagged', cls: 'tag-warn', icon: <AlertTriangle size={12} /> },
    urgent: { label: 'Many flagged', cls: 'tag-crit', icon: <AlertTriangle size={12} /> },
  } as const
  const POP_LABEL: Record<string, string> = { all: 'All populations', hijra: 'Hijra / Gender-diverse', fsw: 'Female Sex Worker' }
  const activeChips: { key: string; label: string; clear: () => void }[] = [
    ...(filters.population !== 'all' ? [{ key: 'pop', label: POP_LABEL[filters.population], clear: () => set({ population: 'all' as const }) }] : []),
    ...(filters.site ? [{ key: 'site', label: `Site ${filters.site}`, clear: () => set({ site: '' }) }] : []),
    ...(filters.enumerator ? [{ key: 'enum', label: filters.enumerator, clear: () => set({ enumerator: '' }) }] : []),
    ...(filters.dateFrom ? [{ key: 'df', label: `From ${filters.dateFrom}`, clear: () => set({ dateFrom: '' }) }] : []),
    ...(filters.dateTo ? [{ key: 'dt', label: `To ${filters.dateTo}`, clear: () => set({ dateTo: '' }) }] : []),
    ...(filters.version ? [{ key: 'ver', label: `Form ${filters.version.slice(0, 10)}…`, clear: () => set({ version: '' }) }] : []),
    ...(filters.severity ? [{ key: 'sev', label: `${filters.severity[0].toUpperCase()}${filters.severity.slice(1)} severity`, clear: () => set({ severity: '' }) }] : []),
  ]

  return (
    <div>
      {/* ── 1 · header ─────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', padding: '20px 0 16px' }}>
        <div style={{ minWidth: 260 }}>
          <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--unfpa)' }}>
            Baseline Evaluation · Monitoring Dashboard
          </div>
          <h1 style={{ fontFamily: 'var(--display)', fontWeight: 700, fontSize: 'clamp(26px, 3.2vw, 34px)', lineHeight: 1.1, margin: '5px 0 4px', color: 'var(--ink)' }}>
            Baseline Monitoring Dashboard
          </h1>
          <p style={{ fontSize: 14, color: 'var(--muted)', margin: 0, maxWidth: 620 }}>
            Fieldwork pace, enumerator performance and data quality for the Hijra and FSW baseline —
            verified results follow in the SRHR section below.
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          {lastSync && (
            <span style={{ fontSize: 13, color: 'var(--muted)', display: 'inline-flex', alignItems: 'center', gap: 5 }}>
              <RefreshCw size={13} style={{ color: 'var(--ok)' }} /> Synced {lastSync.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
          <button className="btn" onClick={exportCsv} disabled={exporting}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 38 }}>
            <Download size={15} /> {exporting ? 'Exporting…' : 'Export CSV'}
          </button>
        </div>
      </div>

      {/* ── filter toolbar + anchors ───────────────────────────────────── */}
      <div className="filterbar">
        <div className="filterbar-row">
          <select aria-label="Population" className="field" value={filters.population}
            onChange={(e) => set({ population: e.target.value as Filters['population'], enumerator: '', site: '' })}>
            <option value="all">All populations</option>
            <option value="hijra">Hijra / Gender-diverse</option>
            <option value="fsw">Female Sex Worker</option>
          </select>
          <select aria-label="Site" className="field" value={filters.site}
            onChange={(e) => set({ site: e.target.value })}>
            <option value="">All sites</option>
            {(m?.sites ?? []).map((s) => <option key={s.name} value={s.name}>Site {s.name}</option>)}
          </select>
          <select aria-label="Enumerator" className="field" value={filters.enumerator}
            onChange={(e) => set({ enumerator: e.target.value })}>
            <option value="">All enumerators</option>
            {(m?.collectors ?? []).map((c) => <option key={c.code} value={c.code}>{c.code}</option>)}
          </select>
          <input aria-label="Interview date from" type="date" className="field" value={filters.dateFrom}
            onChange={(e) => set({ dateFrom: e.target.value })} />
          <input aria-label="Interview date to" type="date" className="field" value={filters.dateTo}
            onChange={(e) => set({ dateTo: e.target.value })} />
          <select aria-label="Form version" className="field" value={filters.version}
            onChange={(e) => set({ version: e.target.value })}>
            <option value="">All form versions</option>
            {(m?.versions ?? []).map((v) => <option key={v.name} value={v.name}>{v.name.slice(0, 12)}… ({v.value})</option>)}
          </select>
          <select aria-label="Anomaly severity" className="field" value={filters.severity}
            onChange={(e) => set({ severity: e.target.value as Filters['severity'] })}>
            <option value="">Any severity</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <span style={{ flex: 1 }} />
          <nav aria-label="Jump to section" className="pills">
            {[['mon-overview', 'Overview'], ['mon-enum', 'Enumerators'],
              ['mon-quality', 'Data quality'], ['srhr', 'SRHR indicators']].map(([id, label]) => (
              <button key={id} className="pill" onClick={() => jump(id)}>{label}</button>
            ))}
          </nav>
        </div>
        {activeChips.length > 0 && (
          <div className="filterbar-row" style={{ gap: 8 }}>
            <span style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--muted)' }}>Active filters:</span>
            {activeChips.map((c) => (
              <span key={c.key} className="chip">{c.label}
                <button aria-label={`Remove filter ${c.label}`} onClick={c.clear}><X size={13} /></button>
              </span>
            ))}
            <button className="pill" onClick={() => setFilters(EMPTY_FILTERS)}>Reset all</button>
          </div>
        )}
      </div>

      {err && (
        <div className="card" style={{ background: 'var(--high-soft)', borderColor: 'var(--high)', color: 'var(--high)', padding: '10px 14px', fontSize: 13, marginBottom: 12 }}>{err}</div>
      )}

      {!m ? (
        <div className="card" style={{ padding: 28, textAlign: 'center', color: 'var(--muted)' }}>Loading fieldwork monitor…</div>
      ) : (
        <>
          {/* ── 2 · fieldwork overview: 6 KPI cards ─────────────────────── */}
          <div id="mon-overview" style={{ display: 'flex', flexWrap: 'wrap', gap: 14, scrollMarginTop: 110 }}>
            <Kpi label="Total interviews"
              value={fmt(m.total)}
              sub={<><TrendingUp size={12} style={{ verticalAlign: -2 }} /> {rangeActive
                ? 'within the selected date range'
                : `+${fmt(last7)} in the last 7 days`}</>} />
            {filters.population === 'all' ? (
              <Kpi label="Population breakdown"
                value={
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingTop: 4 }}>
                    {m.progress.map((p) => (
                      <HBar key={p.population} label={p.population === 'hijra' ? 'Hijra' : 'FSW'}
                        value={p.collected} max={Math.max(...m.progress.map((x) => x.collected), 1)}
                        color={p.population === 'hijra' ? ORANGE : TEAL} />
                    ))}
                  </div>
                } />
            ) : (
              <Kpi label="Sites covered"
                value={fmt(m.sites.length)}
                sub={m.sites.slice(0, 3).map((sx) => `Site ${sx.name} · ${sx.value}`).join('   ')}
                sub2={m.sites.length > 3 ? `+ ${m.sites.length - 3} more sites` : undefined} />
            )}
            {target ? (
              <Kpi label="Fieldwork completion"
                value={`${Math.round((100 * m.total) / target)}%`}
                sub={`${fmt(m.total)} of ${fmt(target)} target`} />
            ) : (
              <Kpi label="Active enumerators"
                value={fmt(m.collectors.length)} />
            )}
            <Kpi label="Valid timing coverage"
              valueColor={m.duration.valid_timing_pct >= 80 ? 'var(--ok)' : 'var(--warn)'}
              title="Records with a usable start AND in-form end time ÷ all filtered submitted interviews. Missing end times stay in the denominator but are never treated as zero-minute interviews."
              value={`${m.duration.valid_timing_pct}%`}
              sub={`${fmt(m.duration.valid_timing_n)} of ${fmt(m.total)} interviews`} />
            <Kpi label="Median interview"
              title="Calculated only from interviews with valid timing, after excluding extreme form-left-open durations."
              value={m.duration.valid_median_min != null ? `${m.duration.valid_median_min}m` : '—'}
              sub={iqr[0] != null ? `IQR ${iqr[0]}–${iqr[1]}m` : undefined}
              sub2={`${fmt(m.duration.valid_median_n)} valid interviews`} />
            <Kpi label="High & critical flags"
              valueColor={(anoms?.kpis.critical ?? 0) > 0 ? 'var(--crit)' : (anoms?.kpis.high ?? 0) > 0 ? 'var(--high)' : 'var(--ink)'}
              value={fmt((anoms?.kpis.critical ?? 0) + (anoms?.kpis.high ?? 0))}
              sub={`${fmt(anoms?.kpis.critical ?? 0)} critical · ${fmt(anoms?.kpis.high ?? 0)} high`}
              sub2={`${fmt(affectedHighCrit)} interviews affected`} />
          </div>

          {/* ── 3 · collection progress ─────────────────────────────────── */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, marginTop: 20 }}>
            <div className="card" style={{ flex: '2 1 460px', minWidth: 320, padding: 18 }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10, marginBottom: 10 }}>
                <div>
                  <div style={{ fontFamily: 'var(--display)', fontWeight: 700, fontSize: 16, color: 'var(--ink)' }}>Interviews collected</div>
                  <div style={{ fontSize: 13, color: 'var(--muted)' }}>{trendMode === 'cumulative' ? 'Cumulative' : 'Per-period'} submissions during the selected range</div>
                </div>
                {trend.length > 1 && (
                  <div className="pills">
                    {(['daily', 'cumulative'] as const).map((mode) => (
                      <button key={mode} className={`pill ${trendMode === mode ? 'on' : ''}`}
                        onClick={() => setTrendMode(mode)}>
                        {mode === 'daily'
                          ? (trendUnit === 'hourly' ? 'Hourly' : trendUnit === 'weekly' ? 'Weekly' : trendUnit === 'monthly' ? 'Monthly' : 'Daily')
                          : 'Cumulative'}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              {trend.length < 2 ? (
                <div style={{ height: 200, display: 'grid', placeItems: 'center', textAlign: 'center', color: 'var(--muted)', fontSize: 13.5, padding: '0 20px' }}>
                  No trend is available for this range. Expand the date range, or a single day shows hourly collection when data exists.
                </div>
              ) : (
              <div style={{ height: 200 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={trend} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                    <defs>
                      <linearGradient id="tH" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={ORANGE} stopOpacity={0.35} /><stop offset="100%" stopColor={ORANGE} stopOpacity={0.02} /></linearGradient>
                      <linearGradient id="tF" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={TEAL} stopOpacity={0.3} /><stop offset="100%" stopColor={TEAL} stopOpacity={0.02} /></linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--hair)" vertical={false} />
                    <XAxis dataKey="date" tick={{ fontSize: 12, fill: 'var(--muted)' }} tickFormatter={(d) => String(d).slice(5)} interval="preserveStartEnd" />
                    <YAxis tick={{ fontSize: 12, fill: 'var(--muted)' }} allowDecimals={false} width={34} />
                    <Tooltip content={<ChartTip />} />
                    {filters.population !== 'fsw' && <Area type="monotone" dataKey="hijra" name="Hijra" stackId="1" stroke={ORANGE} fill="url(#tH)" strokeWidth={2} isAnimationActive={false} />}
                    {filters.population !== 'hijra' && <Area type="monotone" dataKey="fsw" name="FSW" stackId="1" stroke={TEAL} fill="url(#tF)" strokeWidth={2} isAnimationActive={false} />}
                  </AreaChart>
                </ResponsiveContainer>
              </div>
              )}
            </div>

            <div className="card" style={{ flex: '1 1 250px', minWidth: 240, padding: 18 }}>
              <div style={{ fontFamily: 'var(--display)', fontWeight: 700, fontSize: 16, color: 'var(--ink)' }}>Interview outcomes</div>
              <div style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 12 }}>How interviews ended</div>
              {(() => {
                const rec: Record<string, number> = Object.fromEntries(m.outcomes.map((o) => [o.name, o.value]))
                const rows = ['Completed', 'Partial', 'Refused', 'Interrupted']
                  .map((name) => ({ name, value: rec[name] ?? 0 }))
                  .filter((o, i) => i < 3 || o.value > 0)
                const nonzero = rows.filter((o) => o.value > 0).length
                return (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                    {rows.map((o) => nonzero > 1 ? (
                      <HBar key={o.name} label={o.name} value={o.value}
                        max={Math.max(...rows.map((x) => x.value), 1)}
                        color={o.name === 'Completed' ? TEAL : o.name === 'Partial' ? AMBER : 'var(--muted)'} />
                    ) : (
                      <div key={o.name} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}>
                        <span style={{ color: 'var(--muted)' }}>{o.name}</span>
                        <span style={{ fontWeight: 700, color: o.value ? 'var(--ink)' : 'var(--muted)', fontVariantNumeric: 'tabular-nums' }}>{fmt(o.value)}</span>
                      </div>
                    ))}
                  </div>
                )
              })()}
              <div style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid var(--hair)', fontSize: 13, color: 'var(--muted)' }}>
                Today <b style={{ color: 'var(--ink)' }}>{fmt(collectedToday)}</b> · Last 7 days <b style={{ color: 'var(--ink)' }}>{fmt(last7)}</b>
              </div>
            </div>
          </div>

          {/* ── 4 · enumerator performance ──────────────────────────────── */}
          <div id="mon-enum" className="card" style={{ marginTop: 22, padding: 18, scrollMarginTop: 110 }}>
            <div className="dsec">
              <div>
                <h2 className="dsec-h">Enumerator performance</h2>
                <p className="dsec-sub">What each enumerator has collected, and what share of their interviews carry a flag to review. Click a row to filter everything below to that enumerator.</p>
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <div style={{ position: 'relative' }}>
                  <Search size={14} style={{ position: 'absolute', left: 9, top: 11, color: 'var(--muted)' }} />
                  <input aria-label="Search enumerator" className="field" value={enumSearch} onChange={(e) => setEnumSearch(e.target.value)}
                    placeholder="Search…" style={{ paddingLeft: 28, width: 160 }} />
                </div>
                <select aria-label="Sort enumerators" className="field" value={enumSort}
                  onChange={(e) => setEnumSort(e.target.value as 'n' | 'flags')}>
                  <option value="flags">Highest flagged share</option>
                  <option value="n">Most interviews</option>
                </select>
              </div>
            </div>
            <div className="tscroll" style={enumerators.length > 10 ? { maxHeight: 480 } : undefined}>
              <table className="dtable">
                <thead>
                  <tr>
                    {([
                      ['Enumerator', ''],
                      ['Interviews', 'Interviews collected, within the filters set above.'],
                      ['Length recorded', 'Interviews whose length we can measure, out of their total. Where this is low, the device was running an older form version that never saved an end time — so those interviews have no measurable duration. It is a form-version issue, not the enumerator’s.'],
                      ['Median length', 'Median duration, over the interviews whose length we can measure. Interviews left open in draft are excluded so they do not stretch the figure.'],
                      ['Flagged interviews', 'Interviews carrying at least one high or critical flag — a contradiction between answers, an income missing a zero, an out-of-range age. Counted as interviews, not flags: one interview can raise several.'],
                      ['Status', 'The share of an enumerator’s interviews that are flagged. Many = a quarter or more, once they have at least 5 interviews; Some = at least one flag; None = clean. A share, not a total, so a heavier workload alone never worsens it. Recorded-length coverage is never counted here.'],
                    ] as [string, string][]).map(([h, tip], i) => (
                      <th key={h} className={i ? 'num' : ''} title={tip || undefined}
                        style={tip ? { cursor: 'help', textDecoration: 'underline dotted', textUnderlineOffset: 3, textDecorationColor: 'var(--hair-2)' } : undefined}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {enumerators.map((r) => {
                    const st = STATUS_STYLE[r.status]
                    const active = filters.enumerator === r.code
                    return (
                      <tr key={r.code} tabIndex={0} role="button"
                        aria-label={`Filter by ${r.code}`}
                        onClick={() => set({ enumerator: active ? '' : r.code })}
                        onKeyDown={(e) => e.key === 'Enter' && set({ enumerator: active ? '' : r.code })}
                        style={{ height: 48, background: active ? 'var(--brand-soft)' : undefined }}>
                        <td>
                          <div style={{ fontWeight: 700, color: 'var(--ink)' }}>{r.code}</div>
                          <div style={{ fontSize: 12.5, color: 'var(--muted)' }}>
                            {r.hijra ? `${r.hijra} Hijra` : ''}{r.hijra && r.fsw ? ' · ' : ''}{r.fsw ? `${r.fsw} FSW` : ''}
                          </div>
                        </td>
                        <td className="num" style={{ fontWeight: 700 }}>{r.n}</td>
                        <td className="num">
                          <div style={{ fontWeight: 700, color: r.valid_timing_pct >= 80 ? 'var(--ok)' : r.valid_timing_pct >= 50 ? 'var(--warn)' : 'var(--high)' }}>{r.valid_timing}/{r.n}</div>
                          <div style={{ fontSize: 12.5, color: 'var(--muted)' }}>{r.valid_timing_pct}%</div>
                        </td>
                        <td className="num">{r.median_min != null ? `${r.median_min}m` : '—'}</td>
                        <td className="num">
                          <div style={{ fontWeight: 700, color: r.flagged > 0 ? 'var(--high)' : 'var(--muted)' }}>
                            {r.flagged ? `${r.flagged}/${r.n}` : '—'}
                          </div>
                          {r.flagged > 0 && (
                            <div style={{ fontSize: 12.5, color: 'var(--muted)' }}>
                              {Math.round(100 * r.rate)}%
                            </div>
                          )}
                        </td>
                        <td className="num">
                          <span className={`tagchip ${st.cls}`}
                            title={r.status === 'good'
                              ? `None of ${r.code}’s ${r.n} interviews carry a flag.`
                              : `${r.flagged} of ${r.code}’s ${r.n} interviews carry a flag (${Math.round(100 * r.rate)}%), raising ${r.flags.critical + r.flags.high} flag${r.flags.critical + r.flags.high === 1 ? '' : 's'} in total — one interview can raise several. Status is set on the share, not the total, so a heavier workload alone never worsens it. Recorded-length coverage is not counted here: a low figure means an older form version, not this enumerator.`}>
                            {st.icon}{st.label}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              {!enumerators.length && <div style={{ padding: 20, textAlign: 'center', color: 'var(--muted)', fontSize: 13 }}>No enumerators match.</div>}
            </div>
          </div>

          {/* ── 5 · data quality & anomalies ────────────────────────────── */}
          <div id="mon-quality" style={{ marginTop: 16, scrollMarginTop: 110 }}>
            <AnomalyQueue
              report={anoms}
              severity={filters.severity}
              onSeverity={(s) => set({ severity: s })}
              onReviewSaved={load}
            />
          </div>

          {/* ── collapsed diagnostics ───────────────────────────────────── */}
          <details className="card" style={{ marginTop: 16, padding: '12px 16px' }}>
            <summary style={{ cursor: 'pointer', fontSize: 13, fontWeight: 700, color: 'var(--ink)', display: 'flex', alignItems: 'center', gap: 7, listStyle: 'none' }}>
              <ChevronDown size={15} style={{ color: 'var(--muted)' }} /> More diagnostics
              <span style={{ fontSize: 11.5, fontWeight: 500, color: 'var(--muted)' }}>
                · duration distribution, districts, GPS {m.quality.gps_pct}%, duplicates {m.quality.duplicates}
              </span>
            </summary>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginTop: 12 }}>
              <Histogram kicker="Interview duration" title="Length distribution (valid timing)"
                data={Object.fromEntries(m.duration.bands.map((b) => [b.name, b.value]))} />
              <BarBreakdown kicker="Coverage" title="Interviews by district"
                data={Object.fromEntries(m.districts.map((b) => [b.name, b.value]))} />
            </div>
          </details>
        </>
      )}
    </div>
  )
}
