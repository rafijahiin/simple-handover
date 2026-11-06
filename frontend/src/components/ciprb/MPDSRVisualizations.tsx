/**
 * MPDSR visualizations per Animesh's spec:
 *
 *   1. NotifyVsReview — bar chart of notified vs reviewed counts, split
 *      Maternal Death (MD) / Neonatal Death (ND).
 *   2. CauseBreakdown — % breakdown of PPH / Eclampsia / Sepsis / Obstructed
 *      Labour / Other, with tab switcher: Cumulative · SIDA · GAC · CP.
 *      (The SIDA/GAC/CP filters require Sayeed's district mapping;
 *       structure is in place so they activate the moment that mapping arrives.)
 *   3. ResponsePlanTracker — planned interventions vs executed, per district.
 *      (Placeholder structure; populates once the MPDSR Action Plan
 *       Excel is ingested.)
 *
 * Each block answers a programmatic question in one glance — no Excel-like
 * tables, no raw-number sprawl.
 */
import React, { Fragment, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Cell, Tooltip,
  PieChart, Pie,
} from 'recharts'
import { Info, Database, AlertTriangle } from 'lucide-react'
import { api } from '@/api/client'
import { DataUnavailable } from '@/components/ciprb/DataUnavailable'
import { SourceChip } from '@/components/ui/SourceChip'
import type { MPDSRCase } from '@/types/index'
import { districtsForDonor } from '@/data/donorDistricts'
import { BarBreakdown, DonutBreakdown, Histogram } from './IndicatorCharts'

// ─── Aggregates fetched from /api/mpdsr/aggregates/ ─────────────────────────

/** Reported maternal deaths against the year's projection, per district.
 *  RCH's request, 6 September 2026. */
export interface MaternalReporting {
  rows: { district: string; reported: number; projected: number | null; pct: number | null }[]
  reported_total: number
  projected_total: number
  basis: string
}

interface FacilityTotals {
  cdn_md?: number; cdn_nd?: number; cdn_sb?: number
  fdn_md: number; fdn_nd: number; fdn_sb: number
  fdr_md: number; fdr_nd: number; fdr_sb: number
}

interface LevelSplit { community: number; facility: number }
interface NotificationByLevel { md: LevelSplit; nd: LevelSplit; sb: LevelSplit }

interface ActionItem {
  section?: string; action?: string; responsible?: string; timeline?: string
  indicator?: string; milestone?: string; considerations?: string; status?: string
}

interface ActionPlanSummary {
  district: string; level: 'DM' | 'UM'
  place_of_meeting: string; meeting_date: string
  participants: number | null
  actions?: ActionItem[]
  meetings_planned: number; activities_planned: number; activities_implemented: number
  completion_pct: number
  source?: string
}

interface DistrictDenominator {
  district: string
  project_deaths_md: number | null
  project_deaths_nd: number | null
  project_deaths_sb: number | null
}

interface ReviewCounts {
  /** Community Maternal Death Reviewed (MPDSR Form 1 / verbal autopsy). */
  sa_md_maternal?: number
  va_md?: number
  /** Community Neonatal Death Reviewed (MPDSR Form 2). */
  va_nd?: number
  /** Social Autopsy (Maternal Death). */
  sa_md?: number
  /** Stillbirths reviewed. The Social Autopsy form is the ONLY route: no
   *  structured review form accepts a stillbirth (F-02 has no stillbirth
   *  field, F-05 records live-born neonates only). */
  sb_reviewed?: number
  /** Facility Maternal Death Reviewed (MPDSR Form 4). */
  f4?: number
  /** Facility Neonatal Death Reviewed (MPDSR Form 5). */
  f5?: number
  /** F1 + F2 notification rows summed — denominator for review rates. */
  notified_md?: number
  notified_nd?: number
  /** Per-sub-form raw counts also returned for transparency. */
  f1?: number
  f2?: number
}

interface LiveAction {
  action_id: string
  district: string
  section: string
  section_label: string
  sub_category: string
  sub_category_label?: string
  activity: string
  responsible: string
  timeline: string | null
  status: string
  status_label: string
  completion_pct: number
  completion_date: string | null
  is_overdue: boolean
}

interface AggregatesPayload {
  denominators: DistrictDenominator[]
  facility_counts: any[]
  facility_totals: FacilityTotals
  notification_by_level?: NotificationByLevel
  action_plan_summaries: ActionPlanSummary[]
  mpdsr_actions?: LiveAction[]
  totals: { mpdsr_cases: number; fistula_corner_cases: number; fistula_campaign_visits: number }
  review_counts?: ReviewCounts
  // CIPRB Phase 3 — the 11 MPDSR major indicators (per-case breakdowns).
  indicators?: Record<string, Record<string, number>>
  // RCH review (17 Aug 2026): MPDSR review records per district.
  records_by_district?: Record<string, number>
  maternal_reporting?: MaternalReporting
  // Facility (Form 04) deep-dive — admission→death interval + review
  // committee progress. Only the facility form carries these.
  facility?: {
    total: number
    admission_to_death: Record<string, number>
    review_status: Record<string, number>
    action_plan_coverage: { with_plan: number; without_plan: number }
  }
  // Phase 2 gap charts — forms that feed the DB but had no chart yet.
  // Neonatal deaths (CIPRB 3 community + CIPRB 5 facility).
  neonatal?: {
    total: number
    cause_of_death: Record<string, number>
    by_level: { community: number; facility: number }
  }
  // Death notification slips (CIPRB 7 + CIPRB 8).
  notifications?: {
    total: number
    by_kind: Record<string, number>
    by_level: { community: number; facility: number }
    by_district: Record<string, number>
  }
  // Social Autopsy (CIPRB 6) — maternal-death re-review. `total` is the
  // MATERNAL subset; `by_kind` carries the whole sa_md cohort, which the
  // by-type chart renders.
  social_autopsy?: {
    total: number
    place_of_death: Record<string, number>
    all_kinds_total?: number
    by_kind?: { maternal: number; neonatal: number; stillbirth: number; unclassified: number }
  }
}

function useAggregates(
  period?: { from: string; to: string },
  districts?: readonly string[] | null,
): { agg: AggregatesPayload | null; aggError: boolean; retryAgg: () => void } {
  const [data, setData] = useState<AggregatesPayload | null>(null)
  // A failed aggregate fetch used to leave data null, and every panel then
  // read `agg?.x ?? 0` — so a broken endpoint rendered zeros, and NotifyVsReview
  // fell back to counting CASES as notifications. Track the error so the panels
  // show an explicit unavailable state instead of fabricated numbers.
  const [aggError, setAggError] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const periodFrom = period?.from
  const periodTo = period?.to
  // Donor filter (GAC / SIDA / All) must reach the aggregate endpoint too,
  // or every aggregate-derived visual (reporting rate, facility deep-dive,
  // 11 indicators, response plan) would silently show ALL-donor totals while
  // the donor pill is set — the bug the audit surfaced. The endpoint already
  // honours ?districts= via apply_donor().
  const districtsKey = districts ? districts.join(',') : ''
  useEffect(() => {
    let cancelled = false
    setAggError(false)
    const params: Record<string, string> = {}
    if (periodFrom) params.from = periodFrom
    if (periodTo) params.to = periodTo
    if (districtsKey) params.districts = districtsKey
    api.get<AggregatesPayload>('/mpdsr/aggregates/', { params })
      .then(r => { if (!cancelled) setData(r.data) })
      .catch(() => { if (!cancelled) setAggError(true) })
    return () => { cancelled = true }
  }, [periodFrom, periodTo, districtsKey, reloadKey])
  return { agg: data, aggError, retryAgg: () => setReloadKey(k => k + 1) }
}

// UNFPA branding — orange across the board.
const CIPRB_BLUE = '#F96000'
const CIPRB_BLUE_SOFT = 'rgba(249,96,0,0.10)'
const CIPRB_BLUE_LIGHT = '#FB904D'   // UNFPA bright (lighter shade for secondary bars)

// ─── 1. Notification vs Review bar chart ─────────────────────────────────────

interface NotifyVsReviewData {
  notifiedMD: number
  reviewedMD: number
  notifiedND: number
  reviewedND: number
}

// A case is "reviewed" once it has progressed past REPORTED to under_review,
// committee_review, action_plan_drafted, or closed.
const REVIEWED_STATUSES = new Set(['under_review', 'committee_review', 'action_plan_drafted', 'closed'])

function computeNotifyVsReview(cases: MPDSRCase[]): NotifyVsReviewData {
  let nM = 0, rM = 0, nN = 0, rN = 0
  for (const c of cases) {
    const isMaternal = c.death_type === 'maternal'
    if (isMaternal) {
      nM++
      if (REVIEWED_STATUSES.has(c.status)) rM++
    } else {
      nN++
      if (REVIEWED_STATUSES.has(c.status)) rN++
    }
  }
  return { notifiedMD: nM, reviewedMD: rM, notifiedND: nN, reviewedND: rN }
}

function NotifyVsReview({
  cases, totals, denominators, reviewCounts, notificationByLevel,
}: {
  cases: MPDSRCase[]
  totals: FacilityTotals | null
  denominators: DistrictDenominator[]
  reviewCounts: ReviewCounts | null
  notificationByLevel: NotificationByLevel | null
}) {
  const { t } = useTranslation()
  const live = useMemo(() => computeNotifyVsReview(cases), [cases])

  // ONE rule for the whole panel: NOTIFIED comes from the notification slips
  // (notificationByLevel — Excel ingest when present, live slips otherwise);
  // REVIEWED comes from the review forms (reviewCounts: f1/f2/f4/f5/sa_md).
  // The old wiring mixed four sources — the Excel fallback counted REVIEW CASES
  // as "notified" (the bar chart plotted 63 maternal reviews as notifications),
  // while the tiles read backend keys that no longer existed and rendered
  // "0 of 86" where 86 was maternal + NEONATAL reviews mislabelled as MD
  // notified. computeNotifyVsReview survives only as a last-resort fallback
  // when the aggregates payload is missing entirely.
  const lvl = notificationByLevel
  const rcF1 = reviewCounts?.f1 ?? 0
  const rcF2 = reviewCounts?.f2 ?? 0
  const rcF4 = reviewCounts?.f4 ?? 0
  const rcF5 = reviewCounts?.f5 ?? 0
  // Maternal autopsies only — the SA form also re-reviews neonatal deaths,
  // and the tile is titled and denominated maternal.
  const rcSA = reviewCounts?.sa_md_maternal ?? reviewCounts?.sa_md ?? 0
  const rcSB = reviewCounts?.sb_reviewed ?? 0
  const d = lvl ? {
    notifiedMD: lvl.md.community + lvl.md.facility,
    notifiedND: lvl.nd.community + lvl.nd.facility,
    notifiedSB: lvl.sb.community + lvl.sb.facility,
    reviewedMD: rcF1 + rcF4,
    reviewedND: rcF2 + rcF5,
  } : totals ? {
    notifiedMD: totals.fdn_md, reviewedMD: totals.fdr_md,
    notifiedND: totals.fdn_nd, reviewedND: totals.fdr_nd,
    notifiedSB: totals.fdn_sb,
  } : { ...live, notifiedSB: 0 }

  // Estimated maternal/neonatal/stillbirth deaths across all districts —
  // the denominator Animesh asked for to compute the REPORTING RATE
  // (notified / estimated) per Sayeed's 'Project Deaths 2026' column.
  const estimatedMD = denominators.reduce((s, x) => s + (x.project_deaths_md ?? 0), 0)
  const estimatedND = denominators.reduce((s, x) => s + (x.project_deaths_nd ?? 0), 0)
  const estimatedSB = denominators.reduce((s, x) => s + (x.project_deaths_sb ?? 0), 0)

  const chartData = [
    { category: t('mpdsrViz.maternalDeaths'), notified: d.notifiedMD, reviewed: d.reviewedMD },
    { category: t('mpdsrViz.neonatalDeaths'), notified: d.notifiedND, reviewed: d.reviewedND },
  ]

  const reviewRateMD = d.notifiedMD > 0 ? (d.reviewedMD / d.notifiedMD) * 100 : 0
  const reviewRateND = d.notifiedND > 0 ? (d.reviewedND / d.notifiedND) * 100 : 0
  const reportingRateMD = estimatedMD > 0 ? (d.notifiedMD / estimatedMD) * 100 : null
  const reportingRateND = estimatedND > 0 ? (d.notifiedND / estimatedND) * 100 : null
  const reportingRateSB = estimatedSB > 0 ? (d.notifiedSB / estimatedSB) * 100 : null

  return (
    <div>
      <div style={{
        marginBottom: 14,
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
        gap: 8, flexWrap: 'wrap',
      }}>
        <div>
          <div className="kicker">
            <span className="dot" style={{ background: CIPRB_BLUE }} />
            {t('mpdsrViz.notifyKicker')}
          </div>
          <h3 style={{ margin: '6px 0 2px', fontSize: 18, fontWeight: 700, color: 'var(--ink)' }}>
            {t('mpdsrViz.notifyTitle')}
          </h3>
          <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: 0 }}>
            {t('mpdsrViz.notifySub')}
          </p>
        </div>
      </div>

      <div className="card" style={{ padding: 24 }}>
        {/* Reporting-rate tiles — MD / ND / SB (notified ÷ estimated).
            Denominators from Sayeed's Project Deaths 2026. */}
        {(() => {
          const FORMULA = (
            'MD = (Live Birth × 136) / 100,000\n' +
            'ND = (Live Birth × 20) / 1,000\n' +
            'SB = (Live Birth × 21) / 1,000\n\n' +
            'Source: MPDSR M&E Framework · Provided by CIPRB.\n' +
            'Decimals come from per-upazila Live Birth counts × ratio; rounded for display.'
          )
          const rateTile = (label: string, rate: number | null, reported: number, estimated: number) => (
            <div>
              <div className="mono" style={{ fontSize: 9.5, color: 'var(--muted)', letterSpacing: '0.08em', marginBottom: 4 }}>
                {label}
              </div>
              <div style={{ fontSize: 28, fontWeight: 800, color: '#AE4300', fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.02em', lineHeight: 1 }}>
                {rate !== null ? (rate > 100 ? '100%+' : `${rate.toFixed(0)}%`) : '—'}
              </div>
              <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 4, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                {reported.toLocaleString()} reported of {Math.round(estimated).toLocaleString()} estimated
                <span title={FORMULA} aria-label="Show denominator formula" style={{
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  width: 14, height: 14, borderRadius: 999, background: 'var(--surface-3)',
                  color: 'var(--muted)', fontSize: 9, fontWeight: 700, cursor: 'help',
                  border: '1px solid var(--hair)',
                }}>i</span>
              </div>
            </div>
          )
          return (reportingRateMD !== null || reportingRateND !== null || reportingRateSB !== null) ? (
            <div style={{
              display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 18,
              marginBottom: 18, paddingBottom: 18, borderBottom: '1px solid var(--hair)',
            }}>
              {rateTile('MATERNAL DEATH REPORTING RATE', reportingRateMD, d.notifiedMD, estimatedMD)}
              {rateTile('NEONATAL DEATH REPORTING RATE', reportingRateND, d.notifiedND, estimatedND)}
              {rateTile('STILLBIRTH REPORTING RATE', reportingRateSB, d.notifiedSB, estimatedSB)}
            </div>
          ) : null
        })()}

        {/* Notification by level — Animesh: "separated by Community / Facility".
            CDN = community death notification, FDN = facility death notification. */}
        {notificationByLevel && (
          <div style={{
            marginBottom: 18, paddingBottom: 18, borderBottom: '1px solid var(--hair)',
          }}>
            <div className="mono" style={{ fontSize: 9.5, color: 'var(--muted)', letterSpacing: '0.08em', marginBottom: 10 }}>
              NOTIFICATIONS BY LEVEL · COMMUNITY DEATH NOTIFICATION (CDN) vs FACILITY DEATH NOTIFICATION (FDN)
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 18 }}>
              {([['Maternal Death (MD)', notificationByLevel.md], ['Neonatal Death (ND)', notificationByLevel.nd], ['Stillbirth (SB)', notificationByLevel.sb]] as const).map(([lbl, lv]) => (
                <div key={lbl}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink-2)', marginBottom: 6 }}>{lbl}</div>
                  <div style={{ display: 'flex', gap: 14 }}>
                    <div>
                      <div style={{ fontSize: 20, fontWeight: 800, color: CIPRB_BLUE, fontVariantNumeric: 'tabular-nums', lineHeight: 1 }}>{lv.community}</div>
                      <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 2 }}>Community</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 20, fontWeight: 800, color: '#C44E00', fontVariantNumeric: 'tabular-nums', lineHeight: 1 }}>{lv.facility}</div>
                      <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 2 }}>Facility</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* MPDSR review breakdown — 5 tiles, full names per CIPRB:
              · Community Maternal Death Reviewed (MPDSR Form 1)
              · Community Neonatal Death Reviewed (MPDSR Form 2)
              · Facility Maternal Death Reviewed  (MPDSR Form 4)
              · Facility Neonatal Death Reviewed  (MPDSR Form 5)
              · Social Autopsy (Maternal Death)
            MD tiles use MD-notified as the denominator; ND tiles use
            ND-notified. SA shares the MD denominator. */}
        {(() => {
          // MATERNAL is deliberately NOT split by level here. The notification
          // side splits on WHICH SLIP WAS FILED; the review side splits on
          // WHICH FORM WAS USED. Those are different questions wearing the
          // same word. 13 of the 17 notified maternal deaths occurred in a
          // facility but were notified by a CHW on the community slip, so a
          // facility tile reads "3 reviewed · 0 notified" and cannot be read.
          // Maternal coverage is therefore one figure: all maternal reviews
          // (F-01 + F-04) against all maternal notifications (both slips).
          // Neonatal keeps the split because it reconciles on both sides.
          //
          // Social Autopsy is a re-review of maternal deaths, so its base is
          // the maternal REVIEWS, not notifications.
          //
          // Reviews exceeding notifications is real, not an error: maternal
          // deaths are being reviewed for which no notification slip was ever
          // filed. Show both numbers plainly, a capped "100%+" with the true
          // counts beside it, rather than hiding the gap. The gap IS the
          // finding.
          const notifMD = (lvl?.md.community ?? 0) + (lvl?.md.facility ?? 0)
          const bases = {
            md: notifMD,
            cnd: lvl?.nd.community ?? 0, fnd: lvl?.nd.facility ?? 0,
            sa: rcF1 + rcF4,
          }
          const pct = (n: number, base: number) => base > 0 ? (n / base) * 100 : null
          const tile = (label: string, value: number, base: number,
                        color: string, baseWord: string, note?: string) => {
            const p = pct(value, base)
            return (
              <div>
                <div className="mono" style={{
                  fontSize: 9.5, color: 'var(--muted)',
                  letterSpacing: '0.08em', marginBottom: 4,
                  minHeight: 22, lineHeight: 1.2,
                }}>
                  {label}
                </div>
                <div style={{
                  fontSize: 26, fontWeight: 800, color,
                  fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.02em', lineHeight: 1,
                }}>
                  {p !== null ? (p > 100 ? '100%+' : `${p.toFixed(0)}%`) : '—'}
                </div>
                <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 4 }}>
                  {value.toLocaleString()} reviewed · {base.toLocaleString()} {baseWord}
                </div>
                {note && (
                  <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 2 }}>
                    {note}
                  </div>
                )}
                {p !== null && p > 100 && (
                  <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 2 }}>
                    {t('mpdsrViz.reviewExceedsNotified')}
                  </div>
                )}
              </div>
            )
          }
          // Stillbirth gets a real tile, not a caption explaining why it has
          // none. The Social Autopsy form is the only route to reviewing one
          // (sa_death_type = 3, মৃতজন্ম on the paper tool); the four
          // structured forms cannot receive a stillbirth at all. The count
          // used to vanish because ingest folded stillbirth into 'perinatal'.
          const notifSB = (lvl?.sb.community ?? 0) + (lvl?.sb.facility ?? 0)
          return (
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))',
              gap: 18, marginBottom: 24,
            }}>
              {tile(t('mpdsrViz.reviewMaternalAll'), rcF1 + rcF4, bases.md, CIPRB_BLUE,
                    t('mpdsrViz.notifiedWord'),
                    t('mpdsrViz.maternalFormSplit', { f1: rcF1, f4: rcF4 }))}
              {tile(t('mpdsrViz.reviewCommunityNeonatal'), rcF2, bases.cnd, CIPRB_BLUE_LIGHT, t('mpdsrViz.notifiedWord'))}
              {tile(t('mpdsrViz.reviewFacilityNeonatal'),  rcF5, bases.fnd, '#E8881C', t('mpdsrViz.notifiedWord'))}
              {tile(t('mpdsrViz.reviewStillbirth'), rcSB, notifSB, '#C44E00',
                    t('mpdsrViz.notifiedWord'), t('mpdsrViz.stillbirthRoute'))}
              {tile(t('mpdsrViz.reviewSocialAutopsy'),     rcSA, bases.sa, CIPRB_BLUE, t('mpdsrViz.mdReviewsWord'))}
            </div>
          )
        })()}

        {/* Bar chart */}
        {(d.notifiedMD + d.notifiedND) > 0 ? (
          <div style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 8, right: 12, bottom: 4, left: -12 }} barGap={6}>
                <XAxis dataKey="category"
                  tick={{ fontSize: 11.5, fill: 'var(--ink-3)' }}
                  axisLine={{ stroke: 'var(--hair)' }} tickLine={false} />
                <YAxis
                  tick={{ fontSize: 10, fill: 'var(--muted)', fontFamily: 'var(--mono)' }}
                  axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip
                  contentStyle={{
                    background: 'var(--surface)',
                    border: '1px solid var(--hair)',
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  cursor={{ fill: 'rgba(249,96,0,0.04)' }}
                />
                <Bar dataKey="notified" name={t('mpdsrViz.notified')} fill={CIPRB_BLUE_LIGHT}
                     radius={[6, 6, 0, 0]} animationDuration={700} />
                <Bar dataKey="reviewed" name={t('mpdsrViz.reviewed')} fill={CIPRB_BLUE}
                     radius={[6, 6, 0, 0]} animationDuration={700} animationBegin={120} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div style={{ padding: '32px 0', textAlign: 'center', fontSize: 13, color: 'var(--muted)' }}>
            {t('mpdsrViz.barEmpty')}
          </div>
        )}

        <div style={{ display: 'flex', gap: 18, marginTop: 14, fontSize: 12 }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--ink-3)' }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: CIPRB_BLUE_LIGHT }} />
            {t('mpdsrViz.notified')}
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--ink-3)' }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: CIPRB_BLUE }} />
            {t('mpdsrViz.reviewed')}
          </span>
        </div>
      </div>
    </div>
  )
}

// ─── 2. Cause of Death breakdown (with district-grouping tabs) ───────────────

type DistrictGroup = 'cumulative' | 'sida' | 'gac' | 'cp'

// Labels are translated at render-time via t() — see CauseBreakdown.
const GROUP_TAB_KEYS: DistrictGroup[] = ['cumulative', 'sida', 'gac', 'cp']
const GROUP_LABEL_KEY: Record<DistrictGroup, string> = {
  cumulative: 'mpdsrViz.tabCumulative',
  sida: 'mpdsrViz.tabSida',
  gac: 'mpdsrViz.tabGac',
  cp: 'mpdsrViz.tabCp',
}

// Cause-of-death pie — UNFPA orange tonal scale, all sitting inside the
// brand family. Other stays neutral so it doesn't read as a partner colour.
// GoB ICD-10 cause groupings — per the MPDSR Form 01 PDF Sayed shared
// (2026-06-02). Six buckets cover all 15 maternal-death cause codes:
//
//   haemorrhage         PPH (O72) · APH (O46) · Early Pregnancy (O20) ·
//                        Placenta Previa (O44) · Abruptio (O45) ·
//                        Rupture Uterus (O71)
//   eclampsia           Eclampsia (O15)
//   sepsis              Puerperal Sepsis (O85)
//   obstructed_labour   Obstructed Labour due to malposition (O64)
//   abortion_related    Ectopic (O00) · Failed abortion (O07) ·
//                        Medical abortion (O04)
//   other_direct        Anaesthesia complications (O74, O29) ·
//                        Obstetric Embolism (O88) · Malnutrition (O25) ·
//                        Death from sequel (O97) · everything else
const CAUSE_PALETTE: Record<string, string> = {
  haemorrhage:       '#F96000',  // UNFPA orange (primary)
  eclampsia:         '#C44E00',  // UNFPA deep
  sepsis:            '#FB904D',  // UNFPA bright
  obstructed_labour: '#FDCFB3',  // UNFPA pale
  abortion_related:  '#8B3700',  // UNFPA darker
  other_direct:      'var(--muted-3)',
}

// Map any free-text cause string to one of the 6 buckets. Matches are
// case-insensitive substrings so both ICD code labels and verbose
// English / Bangla cause strings classify cleanly.
function bucketForCause(raw: string): string {
  const c = (raw ?? '').toLowerCase().trim()
  if (!c) return 'other_direct'
  if (c.includes('pph') || c.includes('aph') || c.includes('haemorr') ||
      c.includes('placenta previa') || c.includes('abruptio') ||
      c.includes('rupture')) return 'haemorrhage'
  if (c.includes('eclampsia') || c.includes('hypertens')) return 'eclampsia'
  if (c.includes('sepsis')) return 'sepsis'
  if (c.includes('obstructed') || c.includes('labour') || c.includes('labor'))
    return 'obstructed_labour'
  if (c.includes('abortion') || c.includes('ectopic'))
    return 'abortion_related'
  return 'other_direct'
}

// District groupings per Sayeed (delivered 1 Jun 2026):
//   GAC  — 5 focused intervention districts
//   SIDA — 6 focused intervention districts
//   CP   — the broader Country Programme footprint = all MPDSR districts
//
// Note: Sunamganj sits in BOTH GAC and SIDA (intentional regional overlap
// Sayeed flagged). Multi-set membership is handled naturally — a Sunamganj
// case counts in both tabs.
//
// Matching uses a normalised form (lowercase, alphanumeric only) so
// "Cox's Bazar" / "Coxsbazar" / "Cox Bazar" all collapse to the same key.
// Derived from donorDistricts.ts, the list Dr. Sayeed supplied on 27
// September 2026, so these tabs cannot disagree with the donor pills or the
// maps. The lists hardcoded here before came from the June 2026 Near Miss
// tool and were wrong in two ways:
//
//   sida  carried Patuakhali and Barguna, which CP funds, and was missing
//         Sunamganj, which SIDA co-funds with GAC.
//   cp    was not the CP donor list at all. It was the whole CIPRB working
//         footprint (18 districts including Habiganj, Sylhet, Rangpur and
//         Moulavibazar, none of which CP funds), which made the CP tab
//         almost identical to Cumulative and therefore meaningless.
//
// gac was already correct and is unchanged.
const DISTRICT_MAPPING: Record<DistrictGroup, string[] | null> = {
  cumulative: null,    // null = no filter (all districts)
  gac:  districtsForDonor('GAC'),
  sida: districtsForDonor('SIDA'),
  cp:   districtsForDonor('CP'),
}

function normaliseDistrict(s: string): string {
  return (s ?? '').toLowerCase().replace(/[^a-z0-9]/g, '')
}

/** A single cause-of-death donut. Used twice side-by-side by
 *  CauseBreakdown — left = Community deaths (MPDSR Form 1),
 *  right = Facility deaths (MPDSR Form 4). */
function CauseDonut({
  cases, title, sub,
}: {
  cases: MPDSRCase[]
  title: string
  sub: string
}) {
  const { t } = useTranslation()
  const counts: Record<string, number> = {}
  for (const c of cases) {
    const k = bucketForCause(c.cause_of_death ?? '')
    counts[k] = (counts[k] ?? 0) + 1
  }
  const total = Object.values(counts).reduce((s, v) => s + v, 0)
  // GoB ICD-10 ordering — most-common first, "other direct" last.
  const causeKeys = ['haemorrhage', 'eclampsia', 'sepsis', 'obstructed_labour', 'abortion_related', 'other_direct']
  const causeLabels: Record<string, string> = {
    haemorrhage:       'Haemorrhage (PPH/APH)',
    eclampsia:         'Eclampsia',
    sepsis:            'Sepsis',
    obstructed_labour: 'Obstructed Labour',
    abortion_related:  'Abortion-related',
    other_direct:      'Other Direct',
  }
  const pieData = causeKeys.map(k => ({
    name: causeLabels[k],
    value: counts[k] ?? 0,
    color: CAUSE_PALETTE[k],
  }))

  return (
    <div className="card" style={{
      padding: 22, flex: '1 1 360px', minWidth: 320,
      display: 'flex', flexDirection: 'column',
    }}>
      <div style={{ marginBottom: 14 }}>
        <h4 style={{
          margin: '0 0 4px', fontSize: 15, fontWeight: 700, color: 'var(--ink)',
        }}>{title}</h4>
        <div className="mono" style={{
          fontSize: 10.5, color: 'var(--muted)', letterSpacing: '0.08em',
          textTransform: 'uppercase',
        }}>{sub}</div>
      </div>

      {total > 0 ? (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'flex-start',
          gap: 24, flexWrap: 'wrap', flex: 1,
        }}>
          <div style={{ width: 180, height: 180, flexShrink: 0 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%"
                  innerRadius={0} outerRadius={86} paddingAngle={1}
                  stroke="#fff" strokeWidth={1}
                  startAngle={90} endAngle={-270} animationDuration={800}>
                  {pieData.map((d) => <Cell key={d.name} fill={d.color} />)}
                </Pie>
                {/* Tooltip lifted above the centre total via wrapperStyle
                    zIndex — the earlier bleed-through was a pure z-order bug,
                    not a dead tooltip. Opaque card so nothing shows through. */}
                <Tooltip
                  wrapperStyle={{ zIndex: 50, outline: 'none' }}
                  contentStyle={{
                    background: 'var(--surface)', border: '1px solid var(--hair)',
                    borderRadius: 8, fontSize: 12, color: 'var(--ink)',
                    boxShadow: '0 6px 20px rgba(0,0,0,0.18)',
                  }}
                  itemStyle={{ color: 'var(--ink)' }}
                  labelStyle={{ color: 'var(--ink)' }}
                  formatter={(value: number, name: string) =>
                    [`${value} (${total ? Math.round((value / total) * 100) : 0}%)`, name]}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div style={{
            display: 'flex', flexDirection: 'column', gap: 8,
            fontSize: 12.5, minWidth: 200, flex: 1,
          }}>
            <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 2 }}>
              <b style={{ fontSize: 18, color: 'var(--ink)', fontVariantNumeric: 'tabular-nums' }}>{total.toLocaleString()}</b> {t('mpdsrViz.mdCases')}
            </div>
            {pieData.map(d => (
              <div key={d.name} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 10, height: 10, borderRadius: 3, background: d.color, flexShrink: 0 }} />
                <span style={{ flex: 1, color: 'var(--ink-2)' }}>{d.name}</span>
                <b style={{ fontVariantNumeric: 'tabular-nums' }}>{d.value.toLocaleString()}</b>
                <span className="mute" style={{ fontSize: 11, width: 38, textAlign: 'right' }}>
                  {total ? Math.round((d.value / total) * 100) : 0}%
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div style={{ padding: '40px 16px', textAlign: 'center', fontSize: 12.5, color: 'var(--muted)' }}>
          {t('mpdsrViz.causeEmpty')}
        </div>
      )}
    </div>
  )
}

/** Two cause-of-death donuts side-by-side, split by death location:
 *  Community (MPDSR Form 1) vs Facility (MPDSR Form 4). The shared
 *  district-group tabs (Cumulative / SIDA / GAC / CP) filter BOTH.
 *  Per CIPRB correction: "two pie charts are needed — Causes of
 *  Maternal Deaths and Distribution of Causes of Maternal Deaths,
 *  Source: Form 1 & Form 4". */
function CauseBreakdown({ cases, donorActive = false }: { cases: MPDSRCase[]; donorActive?: boolean }) {
  const { t } = useTranslation()
  const [group, setGroup] = useState<DistrictGroup>('cumulative')
  // When a donor pill (GAC/SIDA) is active the parent already scoped `cases`
  // to that donor's districts, so the internal SIDA/GAC/CP tabs would
  // DOUBLE-filter to an empty chart (donor=SIDA + tab=GAC → nothing). Force
  // 'cumulative' (= the donor-scoped set) and disable the tabs while it's on.
  const effectiveGroup: DistrictGroup = donorActive ? 'cumulative' : group

  const filtered = useMemo(() => {
    const allow = DISTRICT_MAPPING[effectiveGroup]
    let pool = cases
    if (allow !== null) {
      if (allow.length === 0) pool = []
      else {
        const set = new Set(allow.map(normaliseDistrict))
        pool = cases.filter(c => set.has(normaliseDistrict(c.district ?? '')))
      }
    }
    // MD-only — cause analysis is maternal-death-specific.
    return pool.filter(c => c.death_type === 'maternal')
  }, [cases, effectiveGroup])

  // Split by SOURCE FORM, not death location: Form 01 (f1) = community
  // review, Form 04 (f4) = facility review (CIPRB spec "Source: Form 1 &
  // Form 4"). Splitting by place_of_death misclassified in-transit
  // community deaths and any facility-form home death.
  const community = filtered.filter(c => c.sub_form_type === 'f1')
  const facility  = filtered.filter(c => c.sub_form_type === 'f4')

  const noCasesInGroup = effectiveGroup !== 'cumulative' && filtered.length === 0

  return (
    <div>
      <div style={{
        marginBottom: 14,
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
        gap: 8, flexWrap: 'wrap',
      }}>
        <div>
          <div className="kicker">
            <span className="dot" style={{ background: CIPRB_BLUE }} />
            {t('mpdsrViz.causeKicker')}
          </div>
          <h3 style={{ margin: '6px 0 2px', fontSize: 18, fontWeight: 700, color: 'var(--ink)' }}>
            {t('mpdsrViz.causeTitle')}
          </h3>
          <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: 0 }}>
            {t('mpdsrViz.causeSub')}
          </p>
        </div>
        <SourceChip>CIPRB 2 (Form 01) + CIPRB 4 (Form 04)</SourceChip>
      </div>

      {/* Group tabs — filter both donuts at once. */}
      <div style={{
        display: 'flex', flexWrap: 'wrap', gap: 6,
        padding: 5,
        background: 'var(--surface-2)',
        borderRadius: 12,
        border: '1px solid var(--hair)',
        width: 'fit-content',
        marginBottom: 16,
      }} role="tablist">
        {GROUP_TAB_KEYS.map(key => {
          const isActive = effectiveGroup === key
          return (
            <button
              key={key}
              onClick={() => { if (!donorActive) setGroup(key) }}
              disabled={donorActive}
              title={donorActive ? 'District tabs are off while the donor filter above is active' : undefined}
              role="tab"
              aria-selected={isActive}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 8,
                padding: '6px 12px',
                fontSize: 12.5,
                fontWeight: isActive ? 600 : 500,
                color: isActive ? '#fff' : 'var(--ink-2)',
                background: isActive ? CIPRB_BLUE : 'transparent',
                border: 'none', borderRadius: 8,
                cursor: donorActive ? 'default' : 'pointer',
                opacity: donorActive && !isActive ? 0.4 : 1,
                transitionProperty: 'background-color, color',
                transitionDuration: '180ms',
              }}
            >
              {t(GROUP_LABEL_KEY[key])}
            </button>
          )
        })}
      </div>

      {noCasesInGroup ? (
        <div className="card" style={{ padding: 24 }}>
          <div style={{
            padding: '40px 16px', textAlign: 'center',
            color: 'var(--ink-3)',
            display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10,
          }}>
            <Info size={20} style={{ color: CIPRB_BLUE }} />
            <div style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--ink-2)' }}>
              {t('mpdsrViz.groupEmpty')}
            </div>
            <div style={{ fontSize: 12, maxWidth: 480, color: 'var(--muted)', lineHeight: 1.55 }}
              dangerouslySetInnerHTML={{ __html: t('mpdsrViz.groupEmptySub', { group: group.toUpperCase() }) }}
            />
          </div>
        </div>
      ) : (
        // Two donuts, one row. Wraps to stacked on narrow screens.
        <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap' }}>
          <CauseDonut
            cases={community}
            title={t('mpdsrViz.causeCommunityTitle')}
            sub={t('mpdsrViz.causeCommunitySub')}
          />
          <CauseDonut
            cases={facility}
            title={t('mpdsrViz.causeFacilityTitle')}
            sub={t('mpdsrViz.causeFacilitySub')}
          />
        </div>
      )}
    </div>
  )
}

function pascal(k: string): string {
  return k.split('_').map(p => p[0].toUpperCase() + p.slice(1)).join('')
}

function ResponsePlanTracker({ summaries }: { summaries: ActionPlanSummary[] }) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState<number | null>(null)
  // Action Plan Progress ingestion is live — rows show per-district
  // planned-vs-executed counts with completion %. Bar colour reflects
  // completion health: green ≥ 75%, amber 40-74%, red < 40%.
  const colorFor = (pct: number) => {
    if (pct >= 75) return '#58968A'  // status-on
    if (pct >= 40) return '#AE4300'  // status-mid
    return '#F10F45'                 // status-off
  }
  // Per-action deadline-based status (Animesh's spec): implemented = green;
  // past deadline & not implemented = red; otherwise (still within timeline)
  // = amber/pending.
  const today = new Date().toISOString().slice(0, 10)
  const actionStatus = (a: ActionItem): { label: string; color: string } => {
    const st = (a.status || '').toLowerCase()
    if (st === 'implemented') return { label: 'Implemented', color: '#1A7A5A' }
    const overdue = a.timeline && a.timeline < today
    if (overdue) return { label: 'Overdue', color: '#F10F45' }
    return { label: st === 'in_progress' ? 'In progress' : 'Pending', color: '#AE4300' }
  }

  return (
    <div>
      <div style={{
        marginBottom: 14,
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
        gap: 8, flexWrap: 'wrap',
      }}>
        <div>
          <div className="kicker">
            <span className="dot" style={{ background: CIPRB_BLUE }} />
            {t('mpdsrViz.responseKicker')}
          </div>
          <h3 style={{ margin: '6px 0 2px', fontSize: 18, fontWeight: 700, color: 'var(--ink)' }}>
            {t('mpdsrViz.responseTitle')}
          </h3>
          <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: 0 }}>
            {t('mpdsrViz.responseSub')}
          </p>
        </div>
        <SourceChip>CIPRB 10 — Response Plan</SourceChip>
      </div>

      {/* Interim-data caveat — shown ONLY while seed/Excel placeholder rows are
          present (executed ≈ planned/2). Real Kobo submissions carry true
          implemented counts (source 'kobo_response_plan'), so this auto-hides
          once the tracker is driven entirely by live field data. */}
      {summaries.some(s => s.source && s.source !== 'kobo_response_plan') && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          margin: '0 0 14px', padding: '8px 12px',
          background: 'rgba(249,96,0,0.08)', border: '1px solid rgba(249,96,0,0.22)',
          borderRadius: 8, fontSize: 11.5, color: 'var(--ink-3)',
        }}>
          <Info size={13} style={{ color: CIPRB_BLUE, flexShrink: 0 }} />
          {t('mpdsrViz.responseDataNote', {
            defaultValue: 'Interim data — implemented counts are placeholders until the Kobo executed-activity form ships; treat as indicative, not confirmed.',
          })}
        </div>
      )}

      {/* OVERALL IMPLEMENTATION summary tile — Animesh's accountability ask
          (2026-06-02 spec): if 10 actions planned and 6 implemented, show
          60%. Aggregates across every row in the table below. */}
      {summaries.length > 0 && (() => {
        const totalPlanned = summaries.reduce((s, x) => s + (x.activities_planned ?? 0), 0)
        const totalImpl = summaries.reduce((s, x) => s + (x.activities_implemented ?? 0), 0)
        const overallPct = totalPlanned > 0 ? Math.round((totalImpl / totalPlanned) * 100) : 0
        const overallColor = colorFor(overallPct)
        return (
          <div
            className="card"
            style={{
              padding: '16px 22px',
              marginBottom: 14,
              display: 'flex', alignItems: 'center', gap: 18,
              borderLeft: `4px solid ${overallColor}`,
            }}
          >
            <div style={{
              flex: 1,
            }}>
              <div className="mono" style={{
                fontSize: 10, color: 'var(--muted)',
                letterSpacing: '0.08em', fontWeight: 700, marginBottom: 4,
              }}>
                OVERALL IMPLEMENTATION
              </div>
              <div style={{ fontSize: 13.5, color: 'var(--ink-2)' }}>
                <b style={{ color: 'var(--ink)', fontVariantNumeric: 'tabular-nums' }}>
                  {totalImpl}
                </b>
                {' of '}
                <b style={{ color: 'var(--ink)', fontVariantNumeric: 'tabular-nums' }}>
                  {totalPlanned}
                </b>
                {' actions implemented across all districts'}
              </div>
            </div>
            <div style={{
              fontSize: 34, fontWeight: 800, color: overallColor,
              fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.02em',
              lineHeight: 1,
            }}>
              {overallPct}%
            </div>
          </div>
        )
      })()}

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <table className="tbl">
          <thead>
            <tr>
              <th>{t('mpdsrViz.thDistrict')}</th>
              <th>{t('mpdsrViz.thLevel')}</th>
              <th>{t('mpdsrViz.thPlace')}</th>
              <th style={{ textAlign: 'right' }}>{t('mpdsrViz.thPlanned')}</th>
              <th style={{ textAlign: 'right' }}>{t('mpdsrViz.thExecuted')}</th>
              <th style={{ textAlign: 'right', minWidth: 160 }}>{t('mpdsrViz.thCompletion')}</th>
            </tr>
          </thead>
          <tbody>
            {summaries.length === 0 ? (
              <tr>
                <td colSpan={6} style={{
                  textAlign: 'center', padding: '48px 16px',
                  color: 'var(--ink-3)',
                }}>
                  <div style={{
                    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10,
                  }}>
                    <Info size={20} style={{ color: CIPRB_BLUE }} />
                    <div style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--ink-2)' }}>
                      {t('mpdsrViz.responseEmpty')}
                    </div>
                  </div>
                </td>
              </tr>
            ) : summaries.map((s, i) => {
              const hasActions = (s.actions?.length ?? 0) > 0
              const isOpen = expanded === i
              return (
              <React.Fragment key={`${s.district}-${s.level}-${i}`}>
              <tr
                onClick={() => hasActions && setExpanded(isOpen ? null : i)}
                style={{ cursor: hasActions ? 'pointer' : 'default' }}
              >
                <td style={{ fontWeight: 500, color: 'var(--ink)' }}>
                  {hasActions && (
                    <span style={{ display: 'inline-block', width: 14, color: 'var(--muted)', transition: 'transform 150ms', transform: isOpen ? 'rotate(90deg)' : 'none' }}>▸</span>
                  )}
                  {s.district}
                </td>
                <td>
                  <span style={{
                    display: 'inline-block', padding: '2px 8px', borderRadius: 4,
                    background: 'rgba(249,96,0,0.08)', color: CIPRB_BLUE,
                    fontSize: 11, fontWeight: 600, letterSpacing: '0.04em',
                  }}>
                    {s.level === 'DM' ? t('mpdsrViz.levelDistrict') : t('mpdsrViz.levelUpazila')}
                  </span>
                </td>
                <td style={{ color: 'var(--ink-3)', fontSize: 12.5 }}>
                  {s.place_of_meeting || '—'}
                </td>
                <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums', color: 'var(--ink-2)' }}>
                  {s.activities_planned.toLocaleString()}
                </td>
                <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums', color: 'var(--ink-2)' }}>
                  {s.activities_implemented.toLocaleString()}
                </td>
                <td style={{ textAlign: 'right' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'flex-end' }}>
                    <div style={{
                      width: 80, height: 6, borderRadius: 999,
                      background: 'var(--surface-3)', overflow: 'hidden',
                    }}>
                      <div style={{
                        width: `${Math.min(100, s.completion_pct)}%`, height: '100%',
                        background: colorFor(s.completion_pct), borderRadius: 999,
                      }} />
                    </div>
                    <span style={{
                      minWidth: 40, fontVariantNumeric: 'tabular-nums',
                      fontWeight: 600, fontSize: 12.5, color: colorFor(s.completion_pct),
                    }}>
                      {s.completion_pct > 100 ? '100%+' : `${s.completion_pct.toFixed(0)}%`}
                    </span>
                  </div>
                </td>
              </tr>
              {isOpen && hasActions && (
                <tr>
                  <td colSpan={6} style={{ padding: 0, background: 'var(--surface-2)' }}>
                    <div style={{ padding: '12px 18px' }}>
                      <div className="mono" style={{ fontSize: 9.5, color: 'var(--muted)', letterSpacing: '0.08em', marginBottom: 8 }}>
                        ACTION ITEMS · {s.meeting_date || 'meeting date n/a'}
                      </div>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                        <thead>
                          <tr style={{ color: 'var(--muted)', textAlign: 'left' }}>
                            <th style={{ padding: '4px 8px', fontWeight: 600 }}>Action</th>
                            <th style={{ padding: '4px 8px', fontWeight: 600 }}>Responsible</th>
                            <th style={{ padding: '4px 8px', fontWeight: 600 }}>Timeline</th>
                            <th style={{ padding: '4px 8px', fontWeight: 600 }}>Indicator</th>
                            <th style={{ padding: '4px 8px', fontWeight: 600 }}>Milestone</th>
                            <th style={{ padding: '4px 8px', fontWeight: 600 }}>Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {s.actions!.map((a, ai) => {
                            const st = actionStatus(a)
                            return (
                              <tr key={ai} style={{ borderTop: '1px solid var(--hair)' }}>
                                <td style={{ padding: '6px 8px', color: 'var(--ink)' }}>{a.action || '—'}</td>
                                <td style={{ padding: '6px 8px', color: 'var(--ink-3)' }}>{a.responsible || '—'}</td>
                                <td style={{ padding: '6px 8px', color: 'var(--ink-3)', fontVariantNumeric: 'tabular-nums' }}>{a.timeline || '—'}</td>
                                <td style={{ padding: '6px 8px', color: 'var(--ink-3)' }}>{a.indicator || '—'}</td>
                                <td style={{ padding: '6px 8px', color: 'var(--ink-3)' }}>{a.milestone || '—'}</td>
                                <td style={{ padding: '6px 8px' }}>
                                  <span style={{
                                    display: 'inline-flex', alignItems: 'center', gap: 5,
                                    padding: '2px 9px', borderRadius: 999, fontSize: 11, fontWeight: 600,
                                    color: st.color, background: `${st.color}1A`,
                                    border: `1px solid ${st.color}40`,
                                  }}>
                                    <span style={{ width: 6, height: 6, borderRadius: 999, background: st.color }} />
                                    {st.label}
                                  </span>
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  </td>
                </tr>
              )}
              </React.Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─── Main export ─────────────────────────────────────────────────────────────


export interface ReportingPeriod {
  from: string
  to: string
}

export function MPDSRVisualizations({
  cases,
  period,
  districts,
}: {
  cases: MPDSRCase[]
  period?: ReportingPeriod
  districts?: readonly string[] | null
}) {
  // Threading reporting-period AND the donor district filter through to the
  // aggregate endpoint so the MPDSR visualisations follow the CIPRB
  // Dashboard's Contract / Annual toggle and the GAC / SIDA / All pill.
  // NotifyVsReview and ReportingRatePerDistrict re-derive from `cases`
  // (already period- + donor-filtered by the parent) and the scoped
  // aggregates returned here.
  const { agg, aggError, retryAgg } = useAggregates(period, districts)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 36 }}>
      {/* CauseBreakdown and ReportingRatePerDistrict derive ONLY from `cases`
          (already period/donor-filtered by the parent), so they stay correct
          even when the aggregate endpoint is down. Everything else below is
          aggregate-driven; if that fetch failed, show one explicit unavailable
          card rather than a screen of fabricated zeros or a cases-as-notified
          fallback. */}
      {aggError ? (
        <DataUnavailable
          label="MPDSR notification, review, facility & indicator panels"
          onRetry={retryAgg}
        />
      ) : (
        <>
          <div>
            <NotifyVsReview
              cases={cases}
              totals={agg?.facility_totals ?? null}
              denominators={agg?.denominators ?? []}
              reviewCounts={agg?.review_counts ?? null}
              notificationByLevel={agg?.notification_by_level ?? null}
            />
          </div>
          {agg?.facility && agg.facility.total > 0 && (
            <div>
              <FacilityDeepDive facility={agg.facility} />
            </div>
          )}
          <div>
            <NeonatalDeaths neonatal={agg?.neonatal ?? null} />
          </div>
          <div>
            <MaternalReportingRate data={agg?.maternal_reporting ?? null} />
          </div>
          <div>
            <DeathNotifications notifications={agg?.notifications ?? null} />
          </div>
          <div>
            <SocialAutopsy socialAutopsy={agg?.social_autopsy ?? null} />
          </div>
          <div>
            <MPDSRIndicators indicators={agg?.indicators ?? null} />
          </div>
        </>
      )}
      <div>
      </div>
      <div>
        <CauseBreakdown cases={cases} donorActive={!!(districts && districts.length)} />
      </div>
    </div>
  )
}

// ─── Facility (Form 04) deep-dive ────────────────────────────────────────────
// The facility maternal-death form carries richer review data than the
// community form. Two breakdowns the community form can't provide:
//   • Admission→death interval — how long after admission the woman died
//     (a care-timeliness signal). Ordered histogram.
//   • Facility review committee progress — where each death sits in the
//     review pipeline, plus what share has a documented action plan.
const REVIEW_STATUS_LABELS: Record<string, string> = {
  reported: 'Reported',
  under_review: 'Under review',
  committee_review: 'Committee review',
  action_plan_drafted: 'Action plan drafted',
  closed: 'Closed',
}

function FacilityDeepDive({ facility }: {
  facility: {
    total: number
    admission_to_death: Record<string, number>
    review_status: Record<string, number>
    action_plan_coverage: { with_plan: number; without_plan: number }
  }
}) {
  return (
    <div>
      <div style={{
        marginBottom: 14,
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
        gap: 8, flexWrap: 'wrap',
      }}>
        <div>
          <div className="kicker">
            <span className="dot" style={{ background: CIPRB_BLUE }} />
            FACILITY DEATHS · MPDSR FORM 4
          </div>
          <h3 style={{ margin: '6px 0 2px', fontSize: 18, fontWeight: 700, color: 'var(--ink)' }}>
            Facility review deep-dive
          </h3>
          <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: 0 }}>
            The extra detail Form 4 captures beyond cause of death — how quickly
            deaths followed admission, and how far each has moved through the
            facility review committee. Based on {facility.total.toLocaleString()} facility maternal {facility.total === 1 ? 'death' : 'deaths'}.
          </p>
        </div>
        <SourceChip>CIPRB 4</SourceChip>
      </div>
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
        <Histogram
          title="Admission → death interval"
          kicker="Care timeliness"
          data={facility.admission_to_death}
        />
        <DonutBreakdown
          title="Review committee progress"
          kicker="Review pipeline"
          data={facility.review_status}
          labels={REVIEW_STATUS_LABELS}
        />
        {/* "Action plan documented" removed at RCH's request (23 Aug 2026).
            Form 4 has no field the committees actually fill for it, so it sat
            at 0% permanently and read as a programme failure rather than a
            missing question. action_plan_coverage still ships in the aggregate
            for the monthly report. */}
      </div>
    </div>
  )
}

// ─── Phase 2 gap charts: Neonatal · Notifications · Social Autopsy ───────────
//
// Three CIPRB Kobo forms feed the DB but had no dedicated chart. Each chart
// is fed by an aggregate key already computed server-side and degrades to an
// empty state when no data has landed.

// Neonatal cause-of-death labels — the `cod_neonatal` choice list (CIPRB 3 +
// CIPRB 5). Bangla reused verbatim from build_ciprb_forms.py choices.
const NEO_CAUSE_LABELS: Record<string, string> = {
  preterm_lbw: 'Preterm / low birth weight',
  asphyxia: 'Birth asphyxia',
  sepsis: 'Neonatal sepsis',
  pneumonia: 'Pneumonia / respiratory infection',
  congenital: 'Congenital anomaly',
  diarrhoea: 'Diarrhoea',
  other: 'Other',
  unknown: 'Unknown',
}

const NEO_LEVEL_LABELS: Record<string, string> = {
  community: 'Community (CIPRB 3)',
  facility: 'Facility (CIPRB 5)',
}

const NOTIF_KIND_LABELS: Record<string, string> = {
  maternal: 'Maternal death',
  neonatal: 'Neonatal death',
  stillbirth: 'Stillbirth',
}

const NOTIF_LEVEL_LABELS: Record<string, string> = {
  community: 'Community / home',
  facility: 'Health facility',
}

// Social-autopsy place of death is decoded server-side alongside every other
// place field (mpdsr/code_labels.py), so the local map that used to live here
// is gone. One vocabulary, one place to change it.

/** Neonatal death surveillance — CIPRB 3 (community) + CIPRB 5 (facility).
 *  Cause-of-death breakdown + community-vs-facility split. */
function NeonatalDeaths({ neonatal }: {
  neonatal: { total: number; cause_of_death: Record<string, number>; by_level: { community: number; facility: number }; danger_signs?: Record<string, number>; place_of_death?: Record<string, number> } | null
}) {
  const { t } = useTranslation()
  const data = neonatal ?? { total: 0, cause_of_death: {}, by_level: { community: 0, facility: 0 }, danger_signs: {}, place_of_death: {} }
  const z = {} as Record<string, number>
  return (
    <div>
      <div style={{
        marginBottom: 14,
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
        gap: 8, flexWrap: 'wrap',
      }}>
        <div>
          <div className="kicker">
            <span className="dot" style={{ background: CIPRB_BLUE }} />
            {t('mpdsrViz.neoKicker')}
          </div>
          <h3 style={{ margin: '6px 0 2px', fontSize: 18, fontWeight: 700, color: 'var(--ink)' }}>
            {t('mpdsrViz.neoTitle')}
          </h3>
          <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: 0 }}>
            {t('mpdsrViz.neoSub', { count: data.total })}
          </p>
        </div>
        <SourceChip>CIPRB 3 + CIPRB 5</SourceChip>
      </div>
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
        <DonutBreakdown
          title={t('mpdsrViz.neoCauseTitle')}
          kicker={t('mpdsrViz.neoCauseKicker')}
          data={data.cause_of_death ?? z}
          labels={NEO_CAUSE_LABELS}
        />
        <DonutBreakdown
          title={t('mpdsrViz.neoLevelTitle')}
          kicker={t('mpdsrViz.neoLevelKicker')}
          data={data.by_level ?? z}
          labels={NEO_LEVEL_LABELS}
        />
        {/* RCH review additions (17 Aug 2026): Form 05 Q11 + Q1. */}
        <BarBreakdown title="Newborn danger signs (Form 05)" data={data.danger_signs ?? z} />
        <BarBreakdown title="Place of neonatal death (Form 05)" data={data.place_of_death ?? z} />
      </div>
    </div>
  )
}

/** Death notification slips — CIPRB 7 (Slip 01) + CIPRB 8 (Slip 02).
 *  By death type, by level, by district. */
function DeathNotifications({ notifications }: {
  notifications: {
    total: number
    by_kind: Record<string, number>
    by_level: { community: number; facility: number }
    by_district: Record<string, number>
  } | null
}) {
  const { t } = useTranslation()
  const data = notifications ?? { total: 0, by_kind: {}, by_level: { community: 0, facility: 0 }, by_district: {} }
  const z = {} as Record<string, number>
  return (
    <div>
      <div style={{
        marginBottom: 14,
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
        gap: 8, flexWrap: 'wrap',
      }}>
        <div>
          <div className="kicker">
            <span className="dot" style={{ background: CIPRB_BLUE }} />
            {t('mpdsrViz.notifSlipKicker')}
          </div>
          <h3 style={{ margin: '6px 0 2px', fontSize: 18, fontWeight: 700, color: 'var(--ink)' }}>
            {t('mpdsrViz.notifSlipTitle')}
          </h3>
          <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: 0 }}>
            {t('mpdsrViz.notifSlipSub', { count: data.total })}
          </p>
        </div>
        <SourceChip>CIPRB 7 + CIPRB 8</SourceChip>
      </div>
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
        <DonutBreakdown
          title={t('mpdsrViz.notifKindTitle')}
          kicker={t('mpdsrViz.notifKindKicker')}
          data={data.by_kind ?? z}
          labels={NOTIF_KIND_LABELS}
        />
        <DonutBreakdown
          title={t('mpdsrViz.notifLevelTitle')}
          kicker={t('mpdsrViz.notifLevelKicker')}
          data={data.by_level ?? z}
          labels={NOTIF_LEVEL_LABELS}
        />
        <BarBreakdown
          title={t('mpdsrViz.notifDistrictTitle')}
          kicker={t('mpdsrViz.notifDistrictKicker')}
          data={data.by_district ?? z}
        />
      </div>
    </div>
  )
}

/** Maternal death notification against the 2026 projection, district by
 *  district. RCH asked for this to be given real prominence: the point is not
 *  how many slips a district filed but how many of the deaths it is expected
 *  to see were ever reported at all.
 *
 *  The bar is the percentage, so the eye reads performance rather than size,
 *  and the two counts sit beside it so nobody has to trust the bar alone. */
function MaternalReportingRate({ data }: { data: MaternalReporting | null }) {
  if (!data || !data.rows.length) return null
  const overall = data.projected_total
    ? (data.reported_total / data.projected_total) * 100 : null
  // Deliberately no red/amber/green banding. These are shares of a FULL YEAR
  // projection read eight months in, so a district "on track" would sit near
  // 67 per cent and every district here is far below that. Thresholds at 25 or
  // 50 would have put Bhola on 28 per cent in a different colour from
  // Sunamganj on 21 and implied a difference in performance that does not
  // exist. One colour for anything reported; the figure carries the message,
  // and only a district reporting nothing at all is called out.
  return (
    <div>
      <div style={{
        marginBottom: 14, display: 'flex', alignItems: 'flex-start',
        justifyContent: 'space-between', gap: 8, flexWrap: 'wrap',
      }}>
        <div>
          <div className="kicker">
            <span className="dot" style={{ background: CIPRB_BLUE }} />
            MATERNAL DEATH NOTIFICATION · REPORTED AGAINST PROJECTED
          </div>
          <h3 style={{ margin: '6px 0 2px', fontSize: 18, fontWeight: 700, color: 'var(--ink)' }}>
            How much of each district&rsquo;s expected maternal mortality is reaching the system
          </h3>
          <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: 0 }}>
            {data.basis}. One notification slip per death, so a death reviewed twice is still counted once.
          </p>
        </div>
        <SourceChip>CIPRB 7 + CIPRB 8 · RCH projections 2026</SourceChip>
      </div>

      {overall != null && (
        <div style={{
          display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap',
          marginBottom: 16,
        }}>
          <span style={{
            fontSize: 34, fontWeight: 800, color: CIPRB_BLUE, lineHeight: 1,
            fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.02em',
          }}>{overall.toFixed(0)}%</span>
          <span style={{ fontSize: 13, color: 'var(--ink-3)' }}>
            of the projected maternal deaths in these districts have been notified
            &mdash; {data.reported_total.toLocaleString()} of {data.projected_total.toLocaleString()}
          </span>
        </div>
      )}

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(96px, 128px) minmax(0, 1fr) 62px 74px',
        rowGap: 11, columnGap: 12, alignItems: 'center',
      }}>
        <span className="mono" style={{ fontSize: 9.5, letterSpacing: '0.08em', color: 'var(--muted)' }}>DISTRICT</span>
        <span className="mono" style={{ fontSize: 9.5, letterSpacing: '0.08em', color: 'var(--muted)' }}>REPORTED AS A SHARE OF PROJECTED</span>
        <span className="mono" style={{ fontSize: 9.5, letterSpacing: '0.08em', color: 'var(--muted)', textAlign: 'right' }}>REPORTED</span>
        <span className="mono" style={{ fontSize: 9.5, letterSpacing: '0.08em', color: 'var(--muted)', textAlign: 'right' }}>PROJECTED</span>
        {data.rows.map((r) => (
          <Fragment key={r.district}>
            <span style={{ fontSize: 13, color: 'var(--ink)', textTransform: 'capitalize' }}>
              {r.district}
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
              <div style={{ flex: 1, height: 11, borderRadius: 3, background: 'var(--hair)' }}>
                <div style={{
                  width: `${Math.min(100, r.pct ?? 0)}%`, height: 11, borderRadius: 3,
                  minWidth: (r.reported > 0 ? 3 : 0), background: CIPRB_BLUE,
                  transition: 'width .4s ease',
                }} />
              </div>
              <span style={{
                flex: '0 0 44px', textAlign: 'right', fontSize: 13, fontWeight: 700,
                color: r.reported === 0 ? '#A32E1C' : CIPRB_BLUE,
                fontVariantNumeric: 'tabular-nums',
              }}>{r.pct == null ? '—' : `${r.pct.toFixed(0)}%`}</span>
            </div>
            <span style={{ textAlign: 'right', fontSize: 13, fontWeight: 700, color: 'var(--ink)', fontVariantNumeric: 'tabular-nums' }}>
              {r.reported.toLocaleString()}
            </span>
            <span style={{ textAlign: 'right', fontSize: 13, color: 'var(--muted)', fontVariantNumeric: 'tabular-nums' }}>
              {r.projected == null ? '—' : r.projected.toLocaleString()}
            </span>
          </Fragment>
        ))}
      </div>

      <p style={{ fontSize: 11, color: 'var(--muted)', margin: '14px 0 0', lineHeight: 1.55 }}>
        Projections are for the whole of 2026, so a district reporting steadily
        all year would still be well under 100 per cent part way through it. A
        district at a few per cent this late in the year is not reporting most
        of the deaths it is expected to see. CIPRB working districts only:
        a district with a projection but no notification is shown at zero
        rather than left out, because that is the gap this panel exists for.
      </p>
    </div>
  )
}

/** Social Autopsy — CIPRB 6 (sa_md). Maternal-death re-review. Count +
 *  place-of-death breakdown. Data is thin and cause is free-text, so this is
 *  a stat-tile-style count alongside a small place-of-death donut. */
function SocialAutopsy({ socialAutopsy }: {
  socialAutopsy: {
    total: number
    place_of_death: Record<string, number>
    /** Whole sa_md cohort. `total` above is the MATERNAL subset, matching
     *  this section's title and the review tile. The two used to disagree
     *  (15 vs 18) because only the tile filtered to maternal. */
    all_kinds_total?: number
    by_kind?: { maternal: number; neonatal: number; stillbirth: number; unclassified: number }
  } | null
}) {
  const { t } = useTranslation()
  const data = socialAutopsy ?? { total: 0, place_of_death: {} }
  return (
    <div>
      <div style={{
        marginBottom: 14,
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
        gap: 8, flexWrap: 'wrap',
      }}>
        <div>
          <div className="kicker">
            <span className="dot" style={{ background: CIPRB_BLUE }} />
            {t('mpdsrViz.saKicker')}
          </div>
          <h3 style={{ margin: '6px 0 2px', fontSize: 18, fontWeight: 700, color: 'var(--ink)' }}>
            {t('mpdsrViz.saTitle')}
          </h3>
          <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: 0 }}>
            {t('mpdsrViz.saSub')}
          </p>
        </div>
        <SourceChip>CIPRB 6 — Social Autopsy</SourceChip>
      </div>
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
        <DonutBreakdown
          title={t('mpdsrViz.saKindTitle')}
          kicker={t('mpdsrViz.saKindKicker')}
          data={{
            maternal: data.by_kind?.maternal ?? data.total,
            neonatal: data.by_kind?.neonatal ?? 0,
            stillbirth: data.by_kind?.stillbirth ?? 0,
            unclassified: data.by_kind?.unclassified ?? 0,
          }}
          labels={{
            maternal: t('mpdsrViz.saKindMaternal'),
            neonatal: t('mpdsrViz.saKindNeonatal'),
            stillbirth: t('mpdsrViz.saKindStillbirth'),
            unclassified: t('mpdsrViz.saKindUnclassified'),
          }}
        />
      </div>
    </div>
  )
}

// ─── MPDSR 11 major indicators (CIPRB corrections doc) ───────────────────────
// The label map that used to live here was a hand-written guess at the form
// vocabulary. It did not match what the verbatim CIPRB forms actually emit, so
// unmapped values fell through and rendered as raw database codes
// ('doctor_mbbs', 'upazila_hc', 'vaginal_spontaneous') on a dashboard read by
// CIPRB and UNFPA. Decoding now happens once in mpdsr/code_labels.py, checked
// against the deployed forms by mpdsr/test_code_labels.py.

function MPDSRIndicators({ indicators }: {
  indicators: Record<string, Record<string, number>> | null
}) {
  const ind = indicators ?? {}
  const z = {} as Record<string, number>
  return (
    <div>
      <div style={{
        marginBottom: 14,
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
        gap: 8, flexWrap: 'wrap',
      }}>
        <div>
          <div className="kicker"><span className="dot" style={{ background: CIPRB_BLUE }} />MPDSR · 11 MAJOR INDICATORS</div>
          <h3 style={{ margin: '6px 0 2px', fontSize: 18, fontWeight: 700, color: 'var(--ink)' }}>
            Maternal death indicator breakdown
          </h3>
          <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: 0 }}>
            The 11 dashboard indicators CIPRB specified, from MPDSR Form 01 (Community Maternal) + Form 04 (Facility Maternal).
          </p>
        </div>
        <SourceChip>CIPRB 2 (Form 01) + CIPRB 4 (Form 04)</SourceChip>
      </div>
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
        {/* Indicators 1, 2, 4, 6, 7, 8 and 9 arrive already decoded and merged
            by mpdsr/code_labels.py, so no label map is applied here. Doing it
            in the backend means the monthly report and any export get the same
            vocabulary as the dashboard instead of each mapping its own. */}
        <DonutBreakdown title="1. Place of death"          data={ind.place_of_death ?? z} />
        {/* 24h clock donut removed; Annual Report Figure-6 periods instead
            (RCH review, confirmed 17 Aug 2026). */}
        <Histogram      title="2. Time of maternal death"  data={ind.death_period ?? z} />
        <Histogram      title="3. Gestational week at death" data={ind.gestational_weeks ?? z} />
        <BarBreakdown   title="4. Antenatal care visits"   data={ind.anc_visits_count ?? z} ordered />
        {/* A visit COUNT, not a yes/no. The stat tile it used to use looked
            for a 'yes' key that never existed, so it reported "Received: 0 of
            22" while the breakdown below it showed 19 women with visits. */}
        <BarBreakdown   title="5. Postnatal care visits"   data={ind.pnc_received ?? z} ordered />
        <DonutBreakdown title="6. Mode of delivery"        data={ind.mode_of_delivery ?? z} />
        {/* Was a single-ratio stat tile; RCH asked for a graphical split
            instead of the numeric ratio (23 Aug 2026). All five outcomes
            are mutually exclusive, so they read as one whole. */}
        <DonutBreakdown title="7. Delivery outcome"        data={ind.delivery_outcome ?? z} />
        <BarBreakdown   title="8. Place of delivery"       data={ind.place_of_delivery ?? z} />
        <BarBreakdown   title="9. Person assisted delivery" data={ind.person_assisted_delivery ?? z} />
        <Histogram      title="10. Maternal age distribution" data={ind.maternal_age ?? z} />
        {/* No F-01/F-04 field feeds this yet, so it rendered as a
            permanently all-zero chart; shown only once real data exists. */}
        {Object.values(ind.time_death_after_birth_hours ?? {}).some((v) => v > 0) && (
          <Histogram title="11. Time of death after birth" data={ind.time_death_after_birth_hours ?? z} />
        )}
        {/* 12 (review records by district) moved beside the coverage map, where
            it fills the width a portrait map cannot use. Removed here rather
            than shown twice on one page. */}
      </div>
    </div>
  )
}
