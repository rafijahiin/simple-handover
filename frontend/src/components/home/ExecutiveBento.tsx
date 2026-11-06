/**
 * ExecutiveBento — homepage bento-grid summary for senior decision-makers.
 *
 * Audience: UNFPA + CIPRB leadership (Dr. Animesh, Dr. Sayeed) and partner
 * org leads. They open this to answer one question: "is the programme on
 * track, and is anything on fire?" — NOT to count individual submissions.
 *
 * So the grid LEADS with programme target attainment (the decision metric),
 * then surfaces what needs attention (open alerts, awaiting review,
 * indicators on track), then the headline outcome counts (GBV, fistula,
 * MPDSR) and field activity (submissions, active workers).
 *
 * Everything is real:
 *   - Attainment + indicators on track  ← IndicatorProgress (already loaded)
 *   - Submissions / pending / workers / outcomes  ← /api/dashboard/kpis/
 *   - Open alerts  ← /api/dashboard/alerts/?acknowledged=false
 * No hardcoded placeholders, no synthetic sparkline.
 *
 * Partner-by-partner attainment lives in the Partner Roll-up section below
 * this component, so the Bento deliberately does NOT repeat per-partner %.
 *
 * Collapses to a single column under 720px.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { motion, useReducedMotion } from 'motion/react'
import {
  Users, Heart, TrendingUp, TrendingDown, Target,
} from 'lucide-react'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import { api } from '@/api/client'
import { PARTNER_COLORS, type PartnerCode } from '@/data/partnerDistricts'
import type { KPIs, IndicatorProgress } from '@/types'

const PARTNERS: PartnerCode[] = ['PHD', 'Bandhu', 'CIPRB']

interface Props {
  progress: IndicatorProgress[] | null
}

// Status band colour for an attainment percentage (UNFPA data-viz palette).
function bandColor(pct: number | null): string {
  if (pct == null || pct === 0) return 'var(--muted)'   // no data / not started
  if (pct >= 75) return '#58968A'
  if (pct >= 40) return '#AE4300'
  return '#F10F45'
}

// ─── Bento card primitive ─────────────────────────────────────────────────────

interface CardProps {
  kicker: React.ReactNode
  value: string
  sub?: string
  trend?: number | null
  icon?: React.ReactNode
  span?: { col?: number; row?: number }
  emphasis?: 'headline' | 'standard' | 'muted'
  valueColor?: string
  progressPct?: number | null    // headline progress bar (0–100)
  progressColor?: string
  footer?: React.ReactNode       // extra content (e.g. per-partner breakdown)
  delay?: number
}

function Card({
  kicker, value, sub, trend, icon, span, emphasis = 'standard',
  valueColor, progressPct, progressColor, footer, delay = 0,
}: CardProps) {
  const reduce = useReducedMotion()
  const isHeadline = emphasis === 'headline'

  return (
    <motion.div
      initial={{ opacity: 0, y: reduce ? 0 : 12 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={reduce ? undefined : { scale: 1.012 }}
      transition={{
        duration: 0.4, delay: reduce ? 0 : delay,
        ease: [0.22, 1, 0.36, 1],
      }}
      className="card"
      style={{
        gridColumn: span?.col ? `span ${span.col} / span ${span.col}` : undefined,
        gridRow:    span?.row ? `span ${span.row} / span ${span.row}` : undefined,
        padding: isHeadline ? '24px 26px' : '16px 18px',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        position: 'relative',
        background: emphasis === 'muted' ? 'var(--surface-2)' : 'var(--surface)',
        ...(isHeadline ? { borderTop: '3px solid var(--unfpa)' } : {}),
      }}
    >
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        color: 'var(--muted)', fontSize: 10.5, fontWeight: 600,
        textTransform: 'uppercase', letterSpacing: '0.08em',
      }}>
        {icon}
        <span>{kicker}</span>
      </div>
      <div style={{
        fontSize: isHeadline ? 'clamp(48px, 6vw, 80px)' : 'clamp(28px, 3vw, 38px)',
        fontWeight: 700,
        lineHeight: 1,
        color: valueColor ?? 'var(--ink)',
        letterSpacing: '-0.025em',
        fontVariantNumeric: 'tabular-nums',
        marginTop: isHeadline ? 4 : 2,
      }}>
        {value}
      </div>
      {(sub || trend != null) && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          fontSize: 12, color: 'var(--ink-3)',
          fontVariantNumeric: 'tabular-nums',
        }}>
          {trend != null && trend !== 0 && (
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: 2,
              padding: '2px 6px', borderRadius: 999,
              fontWeight: 600, fontSize: 11,
              color: trend > 0 ? '#015A28' : '#9A3412',
              background: trend > 0 ? 'rgba(88,150,138,0.15)' : 'rgba(241,15,69,0.10)',
            }}>
              {trend > 0 ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
              {trend > 0 ? '+' : ''}{trend.toFixed(1)}%
            </span>
          )}
          {sub && <span>{sub}</span>}
        </div>
      )}
      {footer}
      {progressPct != null && (
        <div style={{
          marginTop: 'auto', paddingTop: 16,
          height: 8, background: 'var(--surface-3)',
          borderRadius: 999, overflow: 'hidden',
        }}>
          <motion.div
            style={{ height: '100%', background: progressColor ?? 'var(--unfpa)', borderRadius: 999 }}
            initial={{ width: 0 }}
            animate={{ width: `${Math.min(progressPct, 100)}%` }}
            transition={{ duration: 0.9, delay: reduce ? 0 : delay + 0.1, ease: [0.22, 1, 0.36, 1] }}
          />
        </div>
      )}
    </motion.div>
  )
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export function ExecutiveBento({ progress }: Props) {
  const { t, i18n } = useTranslation()
  const [kpis, setKpis] = useState<KPIs | null>(null)
  const [now, setNow] = useState(new Date())

  const fmtNum = (n: number) =>
    n.toLocaleString(i18n.language?.startsWith('bn') ? 'bn-BD' : 'en-US')

  // Fetch KPIs (the CIPRB fistula counts for the cards below), re-polling every
  // 30s so the numbers stay live and the elapsed-to-date clock (now) advances.
  useEffect(() => {
    let cancelled = false
    const fetchAll = () => {
      api.get<KPIs>('/dashboard/kpis/')
        .then((r) => { if (!cancelled) setKpis(r.data) })
        .catch(() => { /* fallback handled by ?? 0 in render */ })
    }
    fetchAll()
    const id = setInterval(() => { fetchAll(); setNow(new Date()) }, 30_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  // ── Programme attainment + indicators on track (the decision metrics) ──
  // Status bands feed the headline pie chart per Animesh's preference for
  // graphical breakdowns over a single raw percentage.
  const stats = (() => {
    const empty = {
      onTrack: 0, behind: 0, critical: 0, notStarted: 0, pending: 0,
      total: 0, totalIndicators: 0,
      avgPct: null as number | null, overallPct: null as number | null,
    }
    if (!progress) return empty
    const all = progress.filter((p) => !p.unlinked)
    const withTarget = all.filter((p) => p.target_value !== null)
    const pending = all.length - withTarget.length
    if (withTarget.length === 0) return { ...empty, pending, totalIndicators: all.length }

    // Pace-to-date: "on track" means an indicator has achieved at least the
    // share of its target that the contract period (21 May – 20 Nov 2026) has
    // elapsed — i.e. it's on pace for today, not measured against the full
    // six-month target (which nothing can reach in month one).
    const CONTRACT_START = new Date('2026-05-21').getTime()
    const CONTRACT_END = new Date('2026-11-20').getTime()
    const elapsedPct = Math.max(0, Math.min(100,
      ((now.getTime() - CONTRACT_START) / (CONTRACT_END - CONTRACT_START)) * 100,
    ))
    let onTrack = 0, behind = 0, critical = 0, notStarted = 0
    for (const p of withTarget) {
      const pct = p.percentage ?? 0
      if (pct === 0) notStarted++
      else if (pct >= elapsedPct) onTrack++
      else if (pct >= elapsedPct * 0.5) behind++
      else critical++
    }
    const avgPct = Math.round(withTarget.reduce((s, p) => s + (p.percentage ?? 0), 0) / withTarget.length)
    const totalAch = withTarget.reduce((s, p) => s + (p.achievement ?? 0), 0)
    const totalTgt = withTarget.reduce((s, p) => s + (p.target_value ?? 0), 0)
    const overallPct = totalTgt > 0 ? Math.round((totalAch / totalTgt) * 1000) / 10 : null
    return {
      onTrack, behind, critical, notStarted, pending,
      total: withTarget.length, totalIndicators: all.length,
      avgPct, overallPct,
    }
  })()

  // Per-partner breakdown so "whose indicators?" is answered in place.
  const perPartner = PARTNERS.map((code) => {
    const rows = (progress ?? []).filter((p) => p.organisation === code && !p.unlinked)
    const withTarget = rows.filter((p) => p.target_value !== null)
    const onTrack = withTarget.filter((p) => (p.percentage ?? 0) >= 75).length
    return {
      code,
      totalIndicators: rows.length,
      withTarget: withTarget.length,
      onTrack,
      hasTargets: withTarget.length > 0,
    }
  })

  const fmtSync = (() => {
    const diff = (Date.now() - now.getTime()) / 1000
    if (diff < 60) return t('bento.syncJustNow', { defaultValue: 'just now' })
    return t('bento.syncMinutes', { count: Math.floor(diff / 60), defaultValue: `${Math.floor(diff / 60)}m ago` })
  })()

  // Render a PHD/Bandhu major-indicator card from the loaded progress array:
  // cumulative achievement vs the programme target, with a status-banded bar.
  const indCard = (
    org: PartnerCode,
    code: string | string[],
    label: string,
    note: string,
    delay: number,
  ) => {
    // Accept one code or many (summed) — mirrors the partner dashboards' marquee
    // cards, where "Service Providers Trained" aggregates several codes
    // (PHD SL10–13, Bandhu 2.1+2.2+2.5) into one number + target.
    const codes = Array.isArray(code) ? code : [code]
    const rows = (progress ?? []).filter(
      r => r.organisation === org && codes.includes(r.activity_code),
    )
    let ach = 0
    let tgt: number | null = null
    for (const r of rows) {
      ach += typeof r.achievement === 'number' ? r.achievement : 0
      if (r.target_value != null) tgt = (tgt ?? 0) + Number(r.target_value)
    }
    // Single code → trust the server's percentage; summed → recompute from the
    // aggregated achievement/target so the bar matches the combined number.
    const pct = rows.length === 1
      ? (rows[0].percentage ?? null)
      : (tgt && tgt > 0 ? (ach / tgt) * 100 : null)
    return (
      <Card
        key={`${org}-${codes.join('-')}`}
        kicker={label.toUpperCase()}
        value={fmtNum(ach)}
        sub={tgt != null ? `of ${fmtNum(tgt)} · ${note}` : note}
        progressPct={pct}
        progressColor={bandColor(pct)}
        delay={delay}
      />
    )
  }

  return (
    <section className="section bento-section" style={{ marginTop: 36 }}>
      {/* ── MAJOR INDICATORS · ALL PARTNERS · TILL DATE ──────────────────
          The programme's signature numbers, one block. Mirrors each partner
          dashboard's marquee: PHD (SL1 reached · SL8 centres · SL4 outreach ·
          SL10–13 providers · SL16 GBV corners) and Bandhu (1.1 reached · 1.8
          centres · 1.4a outreach · 2.1+2.2+2.5 providers), each cumulative vs
          target with a bar; plus CIPRB's two fistula outcome counts (CIPRB
          targets are not set). The old "Executive summary" KPI cards (open
          alerts / awaiting review / indicators on track / submissions) were
          removed per Rafi — the awaiting-review count disagreed with the
          approval-queue badge and the block was redundant. */}
      <div className="section-head" style={{ marginBottom: 12 }}>
        <div>
          <div className="kicker" style={{ marginBottom: 8 }}>
            <span className="dot" style={{ background: 'var(--unfpa)' }} />
            {t('bento.majorKicker', { defaultValue: 'MAJOR INDICATORS · ALL PARTNERS · TILL DATE' })}
          </div>
          <h2 className="section-title">
            {t('bento.title', { defaultValue: 'Executive summary' })}
          </h2>
          <p className="section-sub">
            {t('bento.subtitle', { defaultValue: 'The headline numbers across all three partners.' })}
          </p>
        </div>
      </div>
      <div
        className="bento-grid"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
          gridAutoRows: 'minmax(120px, auto)',
          gap: 14,
        }}
      >
        {/* PHD — SIDA marquee indicators (mirror the PHD dashboard) */}
        {indCard('PHD', 'SL1', 'PHD · FSWs reached', 'HIV/STI screening & FP', 0.05)}
        {indCard('PHD', 'SL8', 'PHD · Wellness centres', 'providing SRHR services', 0.08)}
        {indCard('PHD', 'SL4', 'PHD · Outreach sessions', 'SRHR / HIV / GBV awareness', 0.11)}
        {indCard('PHD', ['SL10', 'SL11', 'SL12', 'SL13'], 'PHD · Providers trained', 'gender-sensitive SRHR training', 0.14)}
        {indCard('PHD', 'SL16', 'PHD · GBV corners', 'established & operational', 0.17)}
        {/* Bandhu — UNFPA marquee indicators (mirror the Bandhu dashboard) */}
        {indCard('Bandhu', '1.1', 'Bandhu · KP reached', 'registered in the Mother List', 0.2)}
        {indCard('Bandhu', '1.8', 'Bandhu · Wellness centres', 'established & strengthened', 0.23)}
        {indCard('Bandhu', '1.4a', 'Bandhu · Outreach sessions', 'outreach & health-education', 0.26)}
        {indCard('Bandhu', ['2.1', '2.2', '2.5'], 'Bandhu · Providers trained', 'managers, midwives & peers', 0.29)}
        {/* CIPRB — fistula outcomes (counts; CIPRB targets are not set) */}
        <Card
          kicker="CIPRB · FISTULA REPAIRED"
          value={fmtNum(kpis?.fistula_repaired ?? 0)}
          sub={t('bento.fistulaRepairedSub', { defaultValue: 'surgically repaired (dry + not-dry)' })}
          icon={<Heart size={12} />}
          delay={0.32}
        />
        <Card
          kicker="CIPRB · REHABILITATED"
          value={fmtNum(kpis?.fistula_reintegrated ?? 0)}
          sub={t('bento.fistulaReintegratedSub', { defaultValue: '& reintegrated' })}
          icon={<Users size={12} />}
          delay={0.35}
        />
      </div>

      <div style={{
        marginTop: 10, fontSize: 11, color: 'var(--muted)',
        display: 'flex', alignItems: 'center', gap: 8,
        fontVariantNumeric: 'tabular-nums',
      }}>
        <span className="live-dot" style={{ background: 'var(--unfpa)' }} />
        <span>{t('bento.lastSync', { defaultValue: 'last sync' })} · {fmtSync}</span>
      </div>

      {/* Responsive — single column under 720px so phones get a tall stack. */}
      <style>{`
        @media (max-width: 720px) {
          .bento-grid {
            grid-template-columns: 1fr !important;
            grid-auto-rows: auto !important;
          }
          .bento-grid > * {
            grid-column: span 1 / span 1 !important;
            grid-row: auto !important;
          }
        }
      `}</style>
    </section>
  )
}


// ─── Programme Attainment pie chart (replaces the big-percent headline) ──────

interface AttainStats {
  onTrack: number
  behind: number
  critical: number
  notStarted: number
  pending: number
  total: number
  totalIndicators: number
  overallPct: number | null
}

interface PartnerRow {
  code: PartnerCode
  totalIndicators: number
  withTarget: number
  onTrack: number
  hasTargets: boolean
}

const STATUS_COLORS = {
  onTrack:    '#58968A',  // deep green
  behind:     '#AE4300',  // deep amber
  critical:   '#F10F45',  // deep red
  notStarted: '#9CA3AF',  // neutral grey
  pending:    'var(--muted-3)', // very faint — no target yet
}

function ProgrammeAttainmentPie({
  stats, perPartner, t,
}: {
  stats: AttainStats
  perPartner: PartnerRow[]
  t: (key: string, opts?: any) => string
}) {
  const reduce = useReducedMotion()
  const total = stats.onTrack + stats.behind + stats.critical + stats.notStarted + stats.pending
  const slices = [
    { name: 'On track (≥ 75%)',      value: stats.onTrack,    color: STATUS_COLORS.onTrack },
    { name: 'Behind (40–74%)',       value: stats.behind,     color: STATUS_COLORS.behind },
    { name: 'Critical (< 40%)',      value: stats.critical,   color: STATUS_COLORS.critical },
    { name: 'Not yet started (0%)',  value: stats.notStarted, color: STATUS_COLORS.notStarted },
    { name: 'Targets pending',       value: stats.pending,    color: STATUS_COLORS.pending },
  ].filter(s => s.value > 0)

  return (
    <motion.div
      initial={{ opacity: 0, y: reduce ? 0 : 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className="card"
      style={{
        gridColumn: 'span 2 / span 2',
        gridRow: 'span 2 / span 2',
        padding: '24px 26px',
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        background: 'var(--surface)',
        borderTop: '3px solid var(--unfpa)',
      }}
    >
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        color: 'var(--muted)', fontSize: 10.5, fontWeight: 600,
        textTransform: 'uppercase', letterSpacing: '0.08em',
      }}>
        <Target size={12} />
        <span>{t('bento.attainment', { defaultValue: 'PROGRAMME ATTAINMENT · ALL PARTNERS' })}</span>
      </div>

      {/* Pie + legend */}
      {total > 0 ? (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 24, flexWrap: 'wrap',
        }}>
          {/* Donut */}
          <div style={{ position: 'relative', width: 180, height: 180, flexShrink: 0 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={slices}
                  dataKey="value"
                  nameKey="name"
                  cx="50%" cy="50%"
                  innerRadius={56} outerRadius={86}
                  paddingAngle={2} stroke="none"
                  startAngle={90} endAngle={-270}
                  animationDuration={reduce ? 0 : 800}
                >
                  {slices.map((s) => <Cell key={s.name} fill={s.color} />)}
                </Pie>
                <Tooltip
                  contentStyle={{
                    background: 'var(--surface)',
                    border: '1px solid var(--hair)',
                    borderRadius: 8, fontSize: 12,
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
            <div style={{
              position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center', pointerEvents: 'none',
            }}>
              <span style={{
                fontSize: 30, fontWeight: 800, lineHeight: 1, color: 'var(--ink)',
                fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.025em',
              }}>
                {stats.totalIndicators}
              </span>
              <span className="mono" style={{
                fontSize: 9, color: 'var(--muted)',
                letterSpacing: '0.08em', marginTop: 4,
              }}>
                INDICATORS
              </span>
            </div>
          </div>

          {/* Legend */}
          <div style={{ flex: 1, minWidth: 200, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {slices.map(s => (
              <div key={s.name} style={{
                display: 'flex', alignItems: 'center', gap: 10,
                fontSize: 12.5,
              }}>
                <span style={{
                  width: 11, height: 11, borderRadius: 3,
                  background: s.color, flexShrink: 0,
                }} />
                <span style={{ flex: 1, color: 'var(--ink-2)' }}>{s.name}</span>
                <b style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--ink)' }}>
                  {s.value}
                </b>
                <span className="mute" style={{
                  fontSize: 11, width: 40, textAlign: 'right',
                  color: 'var(--muted)', fontVariantNumeric: 'tabular-nums',
                }}>
                  {total ? Math.round((s.value / total) * 100) : 0}%
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div style={{
          height: 180, display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: 'var(--muted)', fontSize: 13,
        }}>
          Targets confirmed in the workshop — pie chart lights up once set.
        </div>
      )}

      {/* Per-partner footer */}
      <div style={{
        display: 'flex', flexDirection: 'column', gap: 7,
        paddingTop: 14, borderTop: '1px solid var(--hair)', marginTop: 'auto',
      }}>
        {perPartner.map((p) => (
          <div key={p.code} style={{
            display: 'flex', alignItems: 'center', gap: 8,
            fontSize: 12.5, color: 'var(--ink-2)',
          }}>
            <span style={{
              width: 8, height: 8, borderRadius: 2, flexShrink: 0,
              background: PARTNER_COLORS[p.code],
            }} />
            <span style={{ fontWeight: 600, minWidth: 54, color: 'var(--ink)' }}>{p.code}</span>
            <span style={{ fontVariantNumeric: 'tabular-nums' }}>
              {p.hasTargets
                ? `${p.onTrack} / ${p.withTarget} indicators on track`
                : `${p.totalIndicators} indicators · targets pending`}
            </span>
          </div>
        ))}
      </div>
    </motion.div>
  )
}
