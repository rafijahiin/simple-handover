/**
 * PartnerProgress — Implementing Partners at a Glance.
 *
 * Layout matches SIMPLE Homepage.html (3 cards in one row, This Month
 * and Overall stacked as panels INSIDE each card, uniform orange accent,
 * districts footer + View dashboard button). UNFPA Atkinson stays as
 * the font; light/dark mode both work via theme tokens.
 *
 * Progress is sourced from the IndicatorProgress array loaded on home
 * (/api/indicators/progress/). Geography from partnerDistricts.
 */
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { motion, useReducedMotion } from 'motion/react'
import { ArrowRight } from 'lucide-react'

import {
  PARTNER_ROUTES, PARTNER_DISTRICTS, type PartnerCode,
} from '@/data/partnerDistricts'
import type { IndicatorProgress } from '@/types'

const PARTNERS: PartnerCode[] = ['CIPRB', 'Bandhu', 'PHD']

// Focus labels resolved via i18n at render-time. Mapping partner →
// i18n key keeps the component clean and lets the EN/BN toggle work.
const FOCUS_KEY: Record<PartnerCode, string> = {
  CIPRB:  'partnerCard.focusCIPRB',
  Bandhu: 'partnerCard.focusBandhu',
  PHD:    'partnerCard.focusPHD',
}

interface Props { progress: IndicatorProgress[] | null }

interface Rollup {
  hasTargets: boolean
  percentage: number | null
  onTrack: number
  total: number
  totalIndicators: number
  monthlyHasTargets: boolean
  monthlyPercentage: number | null
  monthlyOnTrack: number
  monthlyTotal: number
}

function rollup(partner: PartnerCode, rows: IndicatorProgress[] | null): Rollup {
  const empty: Rollup = {
    hasTargets: false, percentage: null,
    onTrack: 0, total: 0, totalIndicators: 0,
    monthlyHasTargets: false, monthlyPercentage: null, monthlyOnTrack: 0,
    monthlyTotal: 0,
  }
  if (!rows) return empty
  const all = rows.filter(r => r.organisation === partner && !r.unlinked)
  const totalIndicators = all.length
  const withTarget = all.filter(r => r.target_value !== null)
  if (withTarget.length === 0) return { ...empty, totalIndicators }
  // Mean-of-per-indicator-percentages (Animesh's spec, same as
  // CumulativeAverageTile on the org pages). NOT sum(ach)/sum(tgt) —
  // that would let SL5a's 300k condoms target dominate the figure and
  // hide progress on smaller indicators.
  const percentage = Math.round(
    (withTarget.reduce((s, r) => s + (r.percentage ?? 0), 0) / withTarget.length) * 10,
  ) / 10
  const onTrack = withTarget.filter(r => (r.percentage ?? 0) >= 75).length

  const withMonth = all.filter(r => (r.month_target ?? null) !== null)
  let monthlyHasTargets = false
  let monthlyPercentage: number | null = null
  let monthlyOnTrack = 0
  if (withMonth.length > 0) {
    monthlyHasTargets = true
    // Same mean-of-percentages for monthly.
    monthlyPercentage = Math.round(
      (withMonth.reduce((s, r) => s + (r.month_percentage ?? 0), 0) / withMonth.length) * 10,
    ) / 10
    monthlyOnTrack = withMonth.filter(r => (r.month_percentage ?? 0) >= 75).length
  }
  return {
    hasTargets: true, percentage,
    onTrack, total: withTarget.length, totalIndicators,
    monthlyHasTargets, monthlyPercentage, monthlyOnTrack,
    monthlyTotal: withMonth.length,
  }
}

export function PartnerProgress({ progress }: Props) {
  const navigate = useNavigate()
  const reduce = useReducedMotion()
  const { t } = useTranslation()

  return (
    <section className="section partner-progress" style={{ marginTop: 44 }}>
      <div className="section-head">
        <div>
          <div className="kicker" style={{ marginBottom: 8 }}>
            <span className="dot" style={{ background: 'var(--unfpa)' }} />
            {t('partnerCard.sectionKicker')}
          </div>
          <h2 className="section-title">{t('partnerCard.sectionTitle')}</h2>
          <p className="section-sub">{t('partnerCard.sectionSub')}</p>
        </div>
      </div>

      {/* SIMPLE Homepage.html design — 3 cards in one row, uniform orange
          accent, This Month + Overall stacked as panels inside, districts
          footer + View dashboard button. */}
      <div className="partner-grid">
        {PARTNERS.map((p, i) => (
          <PartnerCard
            key={p}
            partner={p}
            data={rollup(p, progress)}
            loading={progress === null}
            delay={i * 0.08}
            reduce={reduce}
            onClick={() => navigate(PARTNER_ROUTES[p])}
          />
        ))}
      </div>
    </section>
  )
}

function PartnerCard({
  partner, data, loading, onClick, reduce, delay,
}: {
  partner: PartnerCode
  data: Rollup
  loading: boolean
  onClick: () => void
  reduce: boolean | null
  delay: number
}) {
  const { t } = useTranslation()
  const focus = t(FOCUS_KEY[partner])
  const districtList = PARTNER_DISTRICTS[partner]
  const districts = districtList.length
  const MAX_NAMES = 6
  const districtNames = districts <= MAX_NAMES
    ? districtList.join(', ')
    : (
      <>
        {districtList.slice(0, MAX_NAMES).join(', ')}{' '}
        <b>{t('partnerCard.moreDistricts', { count: districts - MAX_NAMES })}</b>
      </>
    )

  return (
    <motion.div
      initial={{ opacity: 0, y: reduce ? 0 : 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: reduce ? 0 : delay, ease: [0.22, 1, 0.36, 1] }}
      className="pcard"
    >
      {/* Top header band — orange wash, partner name + focus + districts chip */}
      <div className="pcard-top">
        <div>
          <div className="pcard-name"><i />{partner}</div>
          <div className="pcard-focus">{focus}</div>
        </div>
        <span className="pcard-dcount">
          {t('partnerCard.districtsCount', { count: districts })}
        </span>
      </div>

      {/* This Month panel */}
      <ThisMonthPanel data={data} loading={loading} t={t} />

      {/* Overall panel */}
      <OverallPanel data={data} loading={loading} t={t} />

      {/* Footer — districts + View dashboard button */}
      <div className="pcard-foot">
        <div className="foot-lbl">{t('partnerCard.districtsLabel')}</div>
        <div className="foot-districts">{districtNames}</div>
        <a
          className="view-link"
          href="#"
          onClick={(e) => { e.preventDefault(); onClick() }}
        >
          {t('partnerCard.viewDashboard')} <ArrowRight size={13} />
        </a>
      </div>
    </motion.div>
  )
}

type TFn = (key: string, opts?: Record<string, unknown>) => string

function ThisMonthPanel({ data, loading, t }: { data: Rollup; loading: boolean; t: TFn }) {
  return (
    <div className="tf">
      <div className="tf-head">
        <span className="tf-lbl">{t('partnerCard.thisMonth')}</span>
        {!loading && !data.monthlyHasTargets && (
          <span className="b-notset">{t('partnerCard.notSet')}</span>
        )}
      </div>
      <div className="tf-desc">{t('partnerCard.thisMonthDesc')}</div>
      {loading ? (
        <div className="tf-row"><span className="tf-stat pending">{t('partnerCard.loading')}</span></div>
      ) : data.monthlyHasTargets ? (
        <>
          <div className="tf-row">
            <span className="tf-stat">
              {t('partnerCard.indicatorsOnTrack', { onTrack: data.monthlyOnTrack, total: data.monthlyTotal })}
            </span>
            <span className="tf-pct">{data.monthlyPercentage}%</span>
          </div>
          <div className="bar">
            <b style={{ width: `${Math.min(data.monthlyPercentage ?? 0, 100)}%` }} />
          </div>
        </>
      ) : (
        <>
          <div className="tf-row">
            <span className="tf-stat pending">
              {t('partnerCard.indicatorsPending', { count: data.totalIndicators })}
            </span>
          </div>
          <div className="bar striped" />
        </>
      )}
    </div>
  )
}

function OverallPanel({ data, loading, t }: { data: Rollup; loading: boolean; t: TFn }) {
  return (
    <div className="tf">
      <div className="tf-head">
        <span className="tf-lbl">{t('partnerCard.overall')}</span>
        {!loading && !data.hasTargets && (
          <span className="b-pending">{t('partnerCard.targetsPending')}</span>
        )}
      </div>
      <div className="tf-desc">{t('partnerCard.overallDesc')}</div>
      {loading ? (
        <div className="tf-row"><span className="tf-stat pending">{t('partnerCard.loading')}</span></div>
      ) : data.hasTargets ? (
        <>
          <div className="tf-row">
            <span className="tf-stat">
              {t('partnerCard.indicatorsOnTrack', { onTrack: data.onTrack, total: data.total })}
            </span>
            <span className="tf-pct">{data.percentage}%</span>
          </div>
          <div className="bar">
            <b style={{ width: `${Math.min(data.percentage ?? 0, 100)}%` }} />
          </div>
        </>
      ) : (
        <>
          <div className="tf-row">
            <span className="tf-stat pending">
              {t('partnerCard.indicatorsPending', { count: data.totalIndicators })}
            </span>
          </div>
          <div className="bar striped" />
        </>
      )}
    </div>
  )
}
