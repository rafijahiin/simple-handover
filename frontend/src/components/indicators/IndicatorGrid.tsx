"use client"
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { motion, AnimatePresence, useReducedMotion } from 'motion/react'
import { RefreshCw } from 'lucide-react'
import { api } from '@/api/client'
import { IndicatorCard } from './IndicatorCard'
import type { IndicatorProgress } from '@/types'

interface Props {
  org: 'PHD' | 'Bandhu' | 'CIPRB'
  periodStart?: string
  periodEnd?: string
}

/** Resolve an objective_number to an i18n key under `indicator.*`.
 *  Unknown objective numbers fall back to `indicator.objectiveOther`. */
function objectiveI18nKey(n: number): string {
  if (n >= 0 && n <= 4) return `indicator.objective${n}`
  return 'indicator.objectiveOther'
}

/** Natural-sort key for activity codes.
 *  Handles SL1, SL2 … SL16 (numeric ordering, not lexicographic which puts
 *  SL10 before SL2) plus the SL5a/b/c sub-row suffix and legacy "1.1", "1.5a". */
function codeKey(code: string): [number, number, string] {
  const m = code.match(/^(?:SL)?(\d+)(?:\.(\d+))?([a-z]*)$/i)
  if (m) {
    return [parseInt(m[1], 10), m[2] ? parseInt(m[2], 10) : 0, (m[3] || '').toLowerCase()]
  }
  return [Number.MAX_SAFE_INTEGER, 0, code]
}

function compareCodes(a: string, b: string): number {
  const [a1, a2, a3] = codeKey(a)
  const [b1, b2, b3] = codeKey(b)
  if (a1 !== b1) return a1 - b1
  if (a2 !== b2) return a2 - b2
  return a3.localeCompare(b3)
}

function groupByObjective(indicators: IndicatorProgress[]): Map<number, IndicatorProgress[]> {
  const groups = new Map<number, IndicatorProgress[]>()
  for (const ind of indicators) {
    const key = ind.objective_number
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(ind)
  }
  // Sort rows within each objective by natural activity-code order
  // (SL1 → SL5a → SL5b → ... SL10 → SL16, not lexicographic).
  for (const rows of groups.values()) {
    rows.sort((a, b) => compareCodes(a.activity_code, b.activity_code))
  }
  // Numeric sort that naturally renders PHD 0 → 1 → 2 and Bandhu 1 → 2 → 4
  // (no auto-renumbering of the missing Bandhu Obj 3).
  return new Map([...groups.entries()].sort((a, b) => a[0] - b[0]))
}

export function IndicatorGrid({ org, periodStart = '2026-05-21', periodEnd = '2026-11-20' }: Props) {
  const { t } = useTranslation()
  const reduce = useReducedMotion()
  const [indicators, setIndicators] = useState<IndicatorProgress[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  async function fetchIndicators() {
    setLoading(true)
    setError(null)
    try {
      const res = await api.get<IndicatorProgress[]>(
        `/indicators/progress/?org=${org}&period_start=${periodStart}&period_end=${periodEnd}`
      )
      // Hide the "Condoms distributed" (SL5a) card on the PHD dashboard — not a
      // tracked PHD target (per Rafi, 2026-06-20).
      setIndicators(res.data.filter(i => !(org === 'PHD' && i.activity_code === 'SL5a')))
      setLastRefresh(new Date())
    } catch {
      setError(t('indicator.loadError'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchIndicators()
    // Refresh every 60s so a manager's approval shows on the target-vs-actual
    // cards within a minute (the backend invalidates this partner's indicator
    // cache on approval; 15 min here made the dashboard feel "stuck" even after
    // the server data was fresh). Mount also fires an immediate fetch, so
    // navigating to the dashboard right after approving shows the new totals at
    // once. Cached server-side, so frequent polls are cheap until the next bump.
    const timer = setInterval(fetchIndicators, 60 * 1000)
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [org, periodStart, periodEnd])

  const grouped = groupByObjective(indicators)

  // Aggregate stats — Step 3 colour bands.
  const withTargets = indicators.filter(i => i.target_value !== null)
  const onTrackCount = withTargets.filter(i => (i.percentage ?? 0) >= 75).length
  const behindCount = withTargets.filter(i => (i.percentage ?? 0) < 40).length
  const totalWithTargets = withTargets.length
  const avgPct =
    totalWithTargets > 0
      ? Math.round(
          withTargets.reduce((sum, i) => sum + (i.percentage ?? 0), 0) / totalWithTargets
        )
      : null

  return (
    <div className="space-y-6">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-semibold text-gray-900 dark:text-white">
            {t('indicator.title')}
          </h2>
          <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
            {t('indicator.programmePeriod', { start: periodStart, end: periodEnd })}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Summary pills */}
          {!loading && totalWithTargets > 0 && (
            <div className="hidden sm:flex items-center gap-2">
              {avgPct !== null && (
                <span className="rounded-full bg-unfpa-blue/10 px-3 py-1 text-xs font-semibold text-unfpa-blue dark:bg-unfpa-blue/20 dark:text-blue-300 tabular-nums">
                  {t('indicator.avg', { pct: avgPct })}
                </span>
              )}
              <span
                className="rounded-full px-3 py-1 text-xs font-semibold tabular-nums"
                style={{ backgroundColor: '#D1FAE5', color: '#065F46' }}
              >
                {t('indicator.onTrack', { count: onTrackCount })}
              </span>
              {behindCount > 0 && (
                <span
                  className="rounded-full px-3 py-1 text-xs font-semibold tabular-nums"
                  style={{ backgroundColor: '#FEE2E2', color: '#991B1B' }}
                >
                  {t('indicator.behind', { count: behindCount })}
                </span>
              )}
            </div>
          )}
          <button
            onClick={fetchIndicators}
            disabled={loading}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-gray-200 dark:border-gray-700 text-gray-500 hover:text-unfpa-blue hover:border-unfpa-blue/50 transition-colors disabled:opacity-40"
            title={t('indicator.refresh')}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Error */}
      <AnimatePresence mode="wait">
        {error && (
          <motion.p
            key="error"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="text-sm text-red-500 dark:text-red-400"
          >
            {error}
          </motion.p>
        )}
      </AnimatePresence>

      {/* Skeleton */}
      {loading && indicators.length === 0 && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <motion.div
              key={i}
              className="h-24 rounded-xl bg-gray-100 dark:bg-gray-800"
              animate={{ opacity: [0.5, 1, 0.5] }}
              transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut', delay: i * 0.1 }}
            />
          ))}
        </div>
      )}

      {/* Grouped by objective_number — natural sort preserves Bandhu's
          1 → 2 → 4 ordering without auto-filling a placeholder Obj 3. */}
      {!loading && indicators.length > 0 && [...grouped.entries()].map(([objNum, rows]) => (
        <div key={objNum} className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
            {/* PHD's new SIDA scheme is flat (all objective_number=0).
                Show the SIDA banner; Bandhu keeps its 1/2/4 objective grouping. */}
            {org === 'PHD'
              ? 'SIDA Framework — SL1 through SL16'
              : t(objectiveI18nKey(objNum), { n: objNum })}
          </h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {rows.map((ind, idx) => (
              <IndicatorCard
                key={ind.activity_code}
                indicator={ind}
                partner={org}
                delay={reduce ? 0 : idx * 0.05}
              />
            ))}
          </div>
        </div>
      ))}

      {/* Last refresh */}
      {lastRefresh && (
        <p className="text-[10px] text-gray-400 dark:text-gray-600">
          {t('indicator.lastRefreshed', { time: lastRefresh.toLocaleTimeString('en-GB') })}
        </p>
      )}
    </div>
  )
}
