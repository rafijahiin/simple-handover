/**
 * BandhuHeadlineCards — the five marquee indicators for the Bandhu page.
 *
 * Replaces the legacy generic hero tiles (Submissions / Outreach / Active
 * workers / GBV) with Bandhu's flagship MIS indicators:
 *
 *   1. KP individuals served            → 1.1            (number, /4,000)
 *   2. HIV testing services             → 1.5b           (number, /2,000)
 *   3. GBV survivors supported          → 1.2            (number, /120)
 *   4. Drop-in centres                  → 1.8            (ring,   /8)
 *   5. Providers & leaders trained      → 2.1+2.2+2.5    (number, summed)
 *
 * Same indicator engine as PhdHeadlineCards (/api/indicators/progress/?org=
 * Bandhu) so org isolation, period scoping and the monthly cadence come for
 * free. Toggle flips cumulative ↔ this-month.
 */
import { useEffect, useState } from 'react'
import { useReducedMotion } from 'motion/react'
import { HeartPulse, Activity, Home, GraduationCap } from 'lucide-react'
import { api } from '@/api/client'
import { SourceChip } from '@/components/ui/SourceChip'
import type { IndicatorProgress } from '@/types'

// Accent colour — unified with the PHD dashboard (var(--unfpa)); was var(--violet).
const VIOLET = 'var(--unfpa)'

type Mode = 'cumulative' | 'monthly'

interface CardDef {
  key: string
  kind: 'number' | 'ring'
  codes: string[]
  label: string
  sub: string
  sl: string
  icon: React.ReactNode
}

const CARDS: CardDef[] = [
  { key: 'served',    kind: 'number', codes: ['1.1'],               label: 'Key Population Reached',    sub: 'Registered in the Mother List',        sl: '1.1',          icon: <HeartPulse size={15} /> },
  { key: 'dic',       kind: 'ring',   codes: ['1.8'],               label: 'Wellness Centres',          sub: 'Established & strengthened',            sl: '1.8',          icon: <Home size={15} /> },
  { key: 'outreach',  kind: 'number', codes: ['1.4a'],              label: 'Outreach Sessions',         sub: 'Outreach & health-education sessions',  sl: '1.4a',         icon: <Activity size={15} /> },
  { key: 'providers', kind: 'number', codes: ['2.1', '2.2', '2.5'], label: 'Service Providers Trained', sub: 'Managers, midwives & peer educators',   sl: '2.1·2.2·2.5', icon: <GraduationCap size={15} /> },
]

interface Metric {
  value: number
  target: number | null
  pct: number | null
  pending: boolean
  missing: boolean
}

function metricFor(card: CardDef, byCode: Map<string, IndicatorProgress>, mode: Mode): Metric {
  const rows = card.codes.map((c) => byCode.get(c)).filter(Boolean) as IndicatorProgress[]
  if (rows.length === 0) return { value: 0, target: null, pct: null, pending: true, missing: true }
  let value = 0
  let target = 0
  let hasTarget = false
  let anyPending = false
  for (const r of rows) {
    if (r.unlinked) anyPending = true
    if (mode === 'cumulative') {
      value += r.achievement ?? 0
      if (r.target_value != null) { target += Number(r.target_value); hasTarget = true }
    } else {
      value += r.month_achievement ?? 0
      if (r.month_target != null) { target += Number(r.month_target); hasTarget = true }
    }
  }
  const tgt = hasTarget ? target : null
  const pct = tgt && tgt > 0 ? (value / tgt) * 100 : null
  return { value, target: tgt, pct, pending: anyPending && value === 0, missing: false }
}

function useCountUp(target: number, dur = 1100) {
  const [v, setV] = useState(0)
  const reduce = useReducedMotion()
  useEffect(() => {
    if (reduce) { setV(target); return }
    let raf: number
    let start: number | null = null
    const step = (ts: number) => {
      if (start === null) start = ts
      const p = Math.min((ts - start) / dur, 1)
      setV(Math.round(target * (1 - Math.pow(1 - p, 3))))
      if (p < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [target, dur, reduce])
  return v
}

function Chip({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 8,
      fontSize: 11, color: 'var(--muted)',
      textTransform: 'uppercase', letterSpacing: '0.07em', fontWeight: 600,
    }}>
      <span style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: 26, height: 26, borderRadius: 7, background: `${VIOLET}14`, color: VIOLET,
      }}>
        {icon}
      </span>
      {label}
    </div>
  )
}

function NumberCard({ card, metric, mode }: { card: CardDef; metric: Metric; mode: Mode }) {
  const shown = useCountUp(metric.value)
  const pct = metric.pct
  const barW = pct == null ? 0 : Math.max(2, Math.min(100, pct))
  return (
    <div className="card" style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 10, minHeight: 156 }}>
      <Chip icon={card.icon} label={card.label} />
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <div style={{ fontSize: 34, fontWeight: 800, color: 'var(--ink)', fontVariantNumeric: 'tabular-nums', lineHeight: 1, letterSpacing: '-0.02em' }}>
          {shown.toLocaleString()}
        </div>
        {metric.target != null ? (
          <span style={{ fontSize: 12, fontWeight: 700, color: VIOLET, background: `${VIOLET}14`, borderRadius: 999, padding: '2px 9px', fontVariantNumeric: 'tabular-nums' }}>
            {pct == null ? '—' : `${Math.round(pct)}%`} of {metric.target.toLocaleString()}
          </span>
        ) : (
          <span style={{ fontSize: 11.5, color: 'var(--muted)', fontStyle: 'italic' }}>
            {mode === 'monthly' ? 'this month' : 'target not set'}
          </span>
        )}
      </div>
      {metric.target != null && (
        <div style={{ height: 6, borderRadius: 999, background: 'var(--hair)', overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${barW}%`, borderRadius: 999, background: VIOLET, transition: 'width 700ms cubic-bezier(0.22,1,0.36,1)' }} />
        </div>
      )}
      <div style={{ marginTop: 'auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>{card.sub}</span>
        <span className="mono" style={{ fontSize: 10, color: 'var(--muted)', letterSpacing: '0.04em' }}>
          {(mode === 'monthly' ? 'This month' : 'To date')} · {card.sl}
        </span>
      </div>
    </div>
  )
}

function Ring({ pct, color, dashed }: { pct: number | null; color: string; dashed?: boolean }) {
  const size = 84
  const stroke = 9
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const p = Math.max(0, Math.min(100, pct ?? 0))
  const dash = (p / 100) * c
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--hair-2)" strokeWidth={stroke}
        strokeDasharray={dashed ? '3 5' : undefined} />
      {pct != null && (
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
          strokeDasharray={`${dash} ${c}`} strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{ transition: 'stroke-dasharray 700ms cubic-bezier(0.22,1,0.36,1)' }} />
      )}
    </svg>
  )
}

function RingCard({ card, metric }: { card: CardDef; metric: Metric }) {
  const pending = metric.pending || metric.missing
  return (
    <div className="card" style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 10, minHeight: 156 }}>
      <Chip icon={card.icon} label={card.label} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <div style={{ position: 'relative', flexShrink: 0, width: 84, height: 84 }}>
          <Ring pct={pending ? 0 : metric.pct} color={VIOLET} dashed={pending} />
          <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', lineHeight: 1.05 }}>
            <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--ink)', fontVariantNumeric: 'tabular-nums' }}>
              {metric.value}<span style={{ color: 'var(--muted)', fontWeight: 600 }}>/{metric.target ?? '—'}</span>
            </div>
            <div style={{ fontSize: 10.5, fontWeight: 700, color: pending ? 'var(--muted)' : VIOLET }}>
              {metric.pct == null ? '—' : `${Math.round(metric.pct)}%`}
            </div>
          </div>
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 12.5, color: 'var(--ink-3)', fontWeight: 500 }}>{card.sub}</div>
          {pending && (
            <div style={{ fontSize: 10.5, color: VIOLET, marginTop: 4, fontStyle: 'italic' }}>
              awaiting submissions
            </div>
          )}
          <div className="mono" style={{ fontSize: 10, color: 'var(--muted)', marginTop: 6, letterSpacing: '0.04em' }}>{card.sl}</div>
        </div>
      </div>
    </div>
  )
}

export function BandhuHeadlineCards() {
  const [rows, setRows] = useState<IndicatorProgress[]>([])
  const [mode, setMode] = useState<Mode>('cumulative')

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const res = await api.get<IndicatorProgress[]>('/indicators/progress/?org=Bandhu')
        if (!cancelled) setRows(Array.isArray(res.data) ? res.data : [])
      } catch {
        if (!cancelled) setRows([])
      }
    }
    load()
    const t = setInterval(load, 60_000)
    return () => { cancelled = true; clearInterval(t) }
  }, [])

  const byCode = new Map(rows.map((r) => [r.activity_code, r]))

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, marginBottom: 14 }}>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <div className="kicker"><span className="dot" />UNFPA KEY INDICATORS</div>
          <SourceChip>Bandhu 0 / 1 / 2</SourceChip>
        </div>
        <div role="radiogroup" aria-label="Reporting mode" style={{
          display: 'inline-flex', gap: 4, padding: 4,
          background: 'var(--surface-2)', borderRadius: 999, border: '1px solid var(--hair)',
        }}>
          {(['cumulative', 'monthly'] as Mode[]).map((m) => {
            const on = mode === m
            return (
              <button key={m} role="radio" aria-checked={on} onClick={() => setMode(m)} style={{
                padding: '5px 14px', borderRadius: 999, border: 'none', cursor: 'pointer',
                fontSize: 12.5, fontWeight: on ? 700 : 500,
                color: on ? '#fff' : 'var(--ink-3)', background: on ? VIOLET : 'transparent',
                transitionProperty: 'background-color, color', transitionDuration: '180ms',
              }}>
                {m === 'cumulative' ? 'Cumulative' : 'This month'}
              </button>
            )
          })}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(205px, 1fr))', gap: 16 }}>
        {CARDS.map((card) => {
          const m = metricFor(card, byCode, mode)
          return card.kind === 'number'
            ? <NumberCard key={card.key} card={card} metric={m} mode={mode} />
            : <RingCard key={card.key} card={card} metric={m} />
        })}
      </div>

    </div>
  )
}
