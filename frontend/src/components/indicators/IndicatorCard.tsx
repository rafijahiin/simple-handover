"use client"
import { motion, useReducedMotion } from 'motion/react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { cn } from '@/utils/cn'
import { bnIndicatorLabel, bnUnit } from '@/data/indicatorLabelsBn'
import type { IndicatorProgress } from '@/types'

interface Props {
  indicator: IndicatorProgress
  /** Partner code used to resolve the Bengali label overlay. */
  partner?: 'PHD' | 'Bandhu' | 'CIPRB'
  delay?: number
}

// Step 3 spec colour bands.
//   ≥ 75       → green  #00B050
//   40 .. 74.9 → yellow #FFC000
//   <  40      → red    #FF0000
//   null target → grey "Not Set"
const COLOUR_GREEN  = '#58968A'   // on track  — deep teal-green
const COLOUR_YELLOW = '#AE4300'   // behind    — deep amber
const COLOUR_RED    = '#F10F45'   // critical  — deep red
const COLOUR_GREY   = '#9CA3AF'   // no target — neutral grey

function bandColour(percentage: number | null): string {
  // 0% at programme start = no data yet, not a failure — render neutral grey.
  // Critical red only fires for genuine attainment < 40% with actual submissions.
  if (percentage === null || percentage === 0) return COLOUR_GREY
  if (percentage >= 75) return COLOUR_GREEN
  if (percentage >= 40) return COLOUR_YELLOW
  return COLOUR_RED
}

function fmt(n: number, unit: string): string {
  if (unit === 'pcs' || unit === 'individuals' || unit === 'materials') {
    return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)
  }
  return String(n)
}

export function IndicatorCard({ indicator, partner, delay = 0 }: Props) {
  const reduce = useReducedMotion()
  const navigate = useNavigate()
  const { t, i18n } = useTranslation()
  const {
    target_value, achievement, percentage, unlinked,
    month_label, month_target, month_achievement, month_percentage,
  } = indicator

  // Audit FIX 6.5 — click navigates to the record drill-down for this
  // (partner, activity_code) pair. Module-pending rows aren't navigable
  // (no records exist yet for unlinked indicators).
  const handleClick = () => {
    if (unlinked) return
    const p = partner ?? (indicator as { organisation?: string }).organisation
    if (!p) return
    const params = new URLSearchParams({
      partner: p,
      activity_code: indicator.activity_code,
    })
    navigate(`/records?${params.toString()}`)
  }
  const interactive = Boolean(!unlinked && (partner ?? (indicator as { organisation?: string }).organisation))
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      handleClick()
    }
  }

  // Bengali overlay — falls back to the DB English label when no
  // Bengali variant exists or when the language is English.
  const isBn = i18n.language?.startsWith('bn')
  const displayLabel = (isBn && partner)
    ? bnIndicatorLabel(partner, indicator.activity_code, indicator.indicator_label)
    : indicator.indicator_label
  const displayUnit = isBn ? bnUnit(indicator.unit) : indicator.unit
  const hasTarget = target_value !== null
  const ringColor = bandColour(percentage)
  const displayPct = percentage ?? 0

  const size = 80
  const strokeWidth = 7
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference * (1 - Math.min(displayPct / 100, 1))

  return (
    <motion.div
      initial={{ opacity: 0, y: reduce ? 0 : 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: reduce ? 0 : delay, ease: [0.22, 1, 0.36, 1] }}
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
      onClick={interactive ? handleClick : undefined}
      onKeyDown={interactive ? onKeyDown : undefined}
      aria-label={interactive ? `View records for ${displayLabel}` : undefined}
      className={cn(
        'flex items-center gap-4 rounded-xl border p-4 shadow-sm transition-colors',
        'bg-white dark:bg-gray-800',
        'border-gray-100 dark:border-gray-700',
        'hover:border-unfpa-blue/30 dark:hover:border-unfpa-blue/40',
        interactive && 'cursor-pointer focus-visible:outline-2 focus-visible:outline-unfpa-blue',
      )}
    >
      {/* Mini progress ring */}
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          className="-rotate-90"
        >
          <circle
            cx={size / 2} cy={size / 2} r={radius}
            fill="none" stroke="currentColor"
            strokeWidth={strokeWidth}
            className="text-gray-100 dark:text-gray-700"
          />
          {hasTarget && (
            <circle
              cx={size / 2} cy={size / 2} r={radius}
              fill="none" stroke={ringColor}
              strokeWidth={strokeWidth}
              strokeDasharray={circumference}
              strokeDashoffset={offset}
              strokeLinecap="round"
              style={{ transition: 'stroke-dashoffset 0.8s ease' }}
            />
          )}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span
            className="text-sm font-bold leading-none tabular-nums"
            style={{ color: ringColor }}
          >
            {hasTarget ? `${Math.round(displayPct)}%` : '–'}
          </span>
        </div>
      </div>

      {/* Label + numbers */}
      <div className="min-w-0 flex-1">
        <p
          className="text-xs font-medium text-gray-700 dark:text-gray-300 leading-snug"
          style={{ textWrap: 'pretty' } as React.CSSProperties}
        >
          {displayLabel}
        </p>

        {/* Dual progress: OVERALL (programme) and MONTHLY (this calendar
            month). Animesh's spec — both are UNFPA-set, no auto-derivation. */}
        <div className="mt-2 grid grid-cols-2 gap-3">
          {/* OVERALL tile */}
          <div>
            <div className="text-[10px] uppercase tracking-wider text-gray-400 font-mono mb-0.5">
              {t('indicator.overall', { defaultValue: 'Overall' })}
            </div>
            <div className="flex items-baseline gap-1 flex-wrap">
              <span className="text-base font-bold tabular-nums text-gray-900 dark:text-white leading-none">
                {fmt(achievement, indicator.unit)}
              </span>
              {hasTarget ? (
                <span className="text-[11px] text-gray-400 tabular-nums">
                  / {fmt(target_value!, indicator.unit)} {displayUnit}
                </span>
              ) : (
                <span
                  className="rounded-full px-1.5 py-0.5 text-[9px] font-semibold tracking-wide uppercase"
                  style={{ backgroundColor: '#FED7AA', color: '#9A3412' }}
                >
                  {t('indicator.notSet')}
                </span>
              )}
            </div>
            {hasTarget && (
              <div className="mt-1 h-1 w-full rounded-full bg-gray-100 dark:bg-gray-700 overflow-hidden">
                <motion.div
                  className="h-1 rounded-full"
                  style={{ backgroundColor: ringColor }}
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.min(displayPct, 100)}%` }}
                  transition={{ duration: 0.8, delay: reduce ? 0 : delay + 0.1, ease: [0.22, 1, 0.36, 1] }}
                />
              </div>
            )}
          </div>

          {/* MONTHLY tile */}
          <div>
            <div className="text-[10px] uppercase tracking-wider text-gray-400 font-mono mb-0.5">
              {t('indicator.thisMonth', { defaultValue: 'This month' })}
              {month_label && <span className="text-gray-300 ml-1">· {month_label}</span>}
            </div>
            {month_target != null ? (
              <>
                <div className="flex items-baseline gap-1 flex-wrap">
                  <span className="text-base font-bold tabular-nums text-gray-900 dark:text-white leading-none">
                    {fmt(month_achievement ?? 0, indicator.unit)}
                  </span>
                  <span className="text-[11px] text-gray-400 tabular-nums">
                    / {fmt(month_target, indicator.unit)} {displayUnit}
                  </span>
                </div>
                <div className="mt-1 h-1 w-full rounded-full bg-gray-100 dark:bg-gray-700 overflow-hidden">
                  <motion.div
                    className="h-1 rounded-full"
                    style={{ backgroundColor: bandColour(month_percentage ?? 0) }}
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(month_percentage ?? 0, 100)}%` }}
                    transition={{ duration: 0.8, delay: reduce ? 0 : delay + 0.15, ease: [0.22, 1, 0.36, 1] }}
                  />
                </div>
              </>
            ) : (
              <span
                className="inline-block rounded-full px-1.5 py-0.5 text-[9px] font-semibold tracking-wide uppercase"
                style={{ backgroundColor: '#FED7AA', color: '#9A3412' }}
              >
                {t('indicator.notSet')}
              </span>
            )}
          </div>
        </div>

        <div className="mt-1.5 flex items-center gap-2">
          <span className="text-[10px] text-gray-400 dark:text-gray-600 font-mono">
            {indicator.activity_code}
          </span>
          {unlinked && (
            <span
              className="text-[10px] font-semibold uppercase tracking-wide rounded-full px-1.5 py-0.5"
              style={{ backgroundColor: '#E5E7EB', color: '#6B7280' }}
              title={t('indicator.modulePendingTooltip')}
            >
              {t('indicator.modulePending')}
            </span>
          )}
        </div>
      </div>
    </motion.div>
  )
}
