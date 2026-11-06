/**
 * CumulativeAverageTile — Animesh's "single unified progress %" for a partner.
 *
 * Calculation is a SIMPLE MEAN of each indicator's percentage (confirmed
 * with the user). For a partner like Bandhu with 18 indicators at 20%,
 * 15%, 10%, 25%, ... the tile averages them and shows one figure for
 * the whole project.
 *
 * Sits above the IndicatorGrid as the executive summary number.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Target } from 'lucide-react'
import { api } from '@/api/client'
import type { IndicatorProgress } from '@/types'

const BAND_COLOR = (pct: number | null) => {
  if (pct === null || pct === 0) return 'var(--muted)'
  if (pct >= 75) return '#58968A'
  if (pct >= 40) return '#AE4300'
  return '#F10F45'
}

interface Props {
  org: 'PHD' | 'Bandhu' | 'CIPRB'
  periodStart: string
  periodEnd: string
}

export function CumulativeAverageTile({ org, periodStart, periodEnd }: Props) {
  const { t } = useTranslation()
  const [data, setData] = useState<IndicatorProgress[] | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .get<IndicatorProgress[]>(
        `/indicators/progress/?org=${org}&period_start=${periodStart}&period_end=${periodEnd}`,
      )
      .then(r => { if (!cancelled) setData(r.data) })
      .catch(() => { /* tile renders skeleton until live */ })
    return () => { cancelled = true }
  }, [org, periodStart, periodEnd])

  // Compute three numbers:
  //   1. avgPct — simple mean of per-indicator percentages (Animesh's spec)
  //   2. onTrack / total — IndicatorGrid uses this; we mirror it here too
  //   3. Total indicators (with and without targets) for context
  const withTargets = (data ?? []).filter(i => i.target_value !== null && !i.unlinked)
  const allIndicators = (data ?? []).filter(i => !i.unlinked)
  const total = withTargets.length
  // Aggregate the actual programme-to-date achievement, not just the percent.
  // When every indicator is still at 0 the mean is mathematically 0% but
  // semantically "no field submissions yet" — show that state explicitly
  // instead of a misleading red 0.0% / 7.1% on an empty programme.
  const totalAchievement = withTargets.reduce((s, i) => s + (i.achievement || 0), 0)
  const awaitingFirstSubmission = total > 0 && totalAchievement === 0
  const avgPct =
    total > 0
      ? withTargets.reduce((s, i) => s + (i.percentage ?? 0), 0) / total
      : null
  const onTrack = withTargets.filter(i => (i.percentage ?? 0) >= 75).length
  const color = awaitingFirstSubmission ? 'var(--muted)' : BAND_COLOR(avgPct)

  return (
    <section
      className="card shimmer"
      style={{
        padding: 24,
        marginBottom: 24,
        display: 'grid',
        gridTemplateColumns: 'minmax(220px, 1fr) minmax(220px, 1fr) minmax(180px, 1fr)',
        gap: 24,
        alignItems: 'center',
      }}
    >
      {/* Cumulative average */}
      <div>
        <div className="kicker" style={{ marginBottom: 8 }}>
          <span className="dot" style={{ background: 'var(--unfpa)' }} />
          OVERALL CUMULATIVE ACHIEVEMENT
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <span style={{
            fontSize: awaitingFirstSubmission ? 18 : 48,
            fontWeight: awaitingFirstSubmission ? 600 : 800,
            color,
            lineHeight: 1,
            fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.025em',
            fontStyle: awaitingFirstSubmission ? 'italic' : 'normal',
          }}>
            {awaitingFirstSubmission
              ? 'Awaiting first submissions'
              : (avgPct === null ? '—' : `${avgPct.toFixed(1)}%`)}
          </span>
        </div>
        <div style={{ fontSize: 12.5, color: 'var(--ink-3)', marginTop: 6 }}>
          {awaitingFirstSubmission
            ? `${total} indicators ready · 0 records approved yet`
            : avgPct === null
              ? 'Awaiting targets'
              : `Mean of ${total} indicator${total === 1 ? '' : 's'} (with targets)`}
        </div>
      </div>

      {/* Indicators on track */}
      <div style={{
        paddingLeft: 24,
        borderLeft: '1px solid var(--hair)',
      }}>
        <div className="kicker" style={{ marginBottom: 8 }}>
          <span className="dot" />
          INDICATORS ON TRACK
        </div>
        <div style={{
          fontSize: 32, fontWeight: 700,
          color: awaitingFirstSubmission ? 'var(--muted)' : 'var(--ink)',
          fontVariantNumeric: 'tabular-nums', lineHeight: 1, letterSpacing: '-0.02em',
        }}>
          {awaitingFirstSubmission
            ? `0 / ${total}`
            : (total > 0 ? `${onTrack} / ${total}` : '—')}
        </div>
        <div style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 6 }}>
          ≥ 75 % of own target
        </div>
      </div>

      {/* Total indicator count */}
      <div style={{
        paddingLeft: 24,
        borderLeft: '1px solid var(--hair)',
        display: 'flex', flexDirection: 'column', gap: 8,
      }}>
        <div className="kicker">
          <span className="dot" />
          PROGRAMME SCOPE
        </div>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          fontSize: 13.5, color: 'var(--ink-2)',
        }}>
          <Target size={14} style={{ color: 'var(--unfpa)' }} />
          <span><b>{allIndicators.length}</b> indicators tracked</span>
        </div>
        <div style={{ fontSize: 12, color: 'var(--ink-3)' }}>
          {total} have targets · {allIndicators.length - total} awaiting target setup
        </div>
      </div>
    </section>
  )
}
