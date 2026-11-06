/**
 * RecordList — per-indicator record drill-down.
 *
 * Reached by clicking any IndicatorCard on /phd, /bondhu, or /tracker.
 * URL: /records?partner={PHD|Bandhu|CIPRB}&activity_code={code}
 *
 * Backend (audit FIX 6.5): GET /api/indicators/records/?partner=...&
 * activity_code=... returns the indicator definition + approved record
 * list. Until KoboFormMapping rows are wired at the validation workshop,
 * the record list is empty and a "wired at workshop" notice is shown.
 *
 * Access (defence-in-depth, also enforced server-side):
 *   PASS — developer, supervisor, org_lead, manager
 *   BLOCK — field_staff, focal, ciprb_baseline → bounced to /
 */
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, AlertCircle } from 'lucide-react'

import { api } from '@/api/client'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { bnIndicatorLabel, bnUnit } from '@/data/indicatorLabelsBn'
import type { PartnerCode } from '@/data/partnerDistricts'

interface RecordsResponse {
  partner: string
  activity_code: string
  activity_label: string
  indicator_label: string
  target_value: number | null
  unit: string
  achievement?: number
  percentage?: number | null
  module_pending: boolean
  awaiting_workshop_wiring?: boolean
  count: number
  results: Array<Record<string, unknown>>
}

export default function RecordList() {
  const navigate = useNavigate()
  const { t, i18n } = useTranslation()
  const [params] = useSearchParams()
  const partner = (params.get('partner') ?? '') as PartnerCode
  const activityCode = params.get('activity_code') ?? ''

  const [data, setData] = useState<RecordsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!partner || !activityCode) {
      setError(t('records.missingParams', { defaultValue: 'Missing partner or activity_code in URL.' }))
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    api.get<RecordsResponse>('/indicators/records/', {
      params: { partner, activity_code: activityCode },
    })
      .then((r) => setData(r.data))
      .catch((e) => setError(e?.response?.data?.detail || 'Could not load records.'))
      .finally(() => setLoading(false))
  }, [partner, activityCode, t])

  if (loading) return <PageLoader />

  const isBn = i18n.language?.startsWith('bn')
  const displayLabel = (data && isBn && partner)
    ? bnIndicatorLabel(partner, data.activity_code, data.indicator_label)
    : data?.indicator_label
  const displayUnit = (data && isBn) ? bnUnit(data.unit) : data?.unit

  return (
    <div className="space-y-6">
      {/* Back button */}
      <button
        onClick={() => navigate(-1)}
        className="inline-flex items-center gap-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-unfpa-blue"
      >
        <ArrowLeft className="h-4 w-4" />
        {t('records.back', { defaultValue: 'Back' })}
      </button>

      {/* Header */}
      {data && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs text-gray-400 font-mono">
            <span>{data.partner}</span>
            <span>·</span>
            <span>{data.activity_code}</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white text-balance">
            {displayLabel}
          </h1>
          {data.activity_label && data.activity_label !== data.indicator_label && (
            <p className="text-sm text-gray-500 dark:text-gray-400 text-pretty">
              {data.activity_label}
            </p>
          )}

          {/* Achievement banner */}
          {!data.module_pending && (
            <div className="rounded-xl bg-gray-50 dark:bg-gray-800 border border-gray-100 dark:border-gray-700 p-4 flex items-baseline gap-3 mt-4">
              <span className="text-3xl font-bold tabular-nums text-unfpa-blue">
                {data.achievement ?? 0}
              </span>
              <span className="text-sm text-gray-500 dark:text-gray-400 tabular-nums">
                / {data.target_value ?? '—'} {displayUnit}
                {data.percentage != null && (
                  <span className="ml-2">({Math.round(data.percentage)}%)</span>
                )}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="card p-4 flex items-start gap-3 border border-red-200 bg-red-50 dark:bg-red-900/20 rounded-xl">
          <AlertCircle className="h-5 w-5 text-red-500 mt-0.5 shrink-0" />
          <div>
            <p className="font-semibold text-red-700 dark:text-red-300">
              {t('records.errTitle', { defaultValue: 'Could not load records' })}
            </p>
            <p className="text-sm text-red-600 dark:text-red-400 mt-1">{error}</p>
          </div>
        </div>
      )}

      {/* Module pending */}
      {data?.module_pending && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 dark:bg-amber-900/20 p-6">
          <h2 className="font-semibold text-amber-900 dark:text-amber-200">
            {t('records.modulePendingTitle', { defaultValue: 'Compute module pending' })}
          </h2>
          <p className="text-sm text-amber-700 dark:text-amber-300 mt-2 text-pretty">
            {t('records.modulePendingBody', {
              defaultValue:
                'This indicator does not yet have an automated compute function wired. Once the KoboToolbox form ' +
                'is linked at the 3–4 June 2026 validation workshop, this page will show the contributing records.',
            })}
          </p>
        </div>
      )}

      {/* Records table — currently always empty (wired at workshop) */}
      {data && !data.module_pending && (
        <div className="rounded-xl bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-700/40 border-b border-gray-100 dark:border-gray-700">
              <tr>
                {[
                  t('records.thDate',        { defaultValue: 'Date' }),
                  t('records.thCenter',      { defaultValue: 'Center' }),
                  t('records.thCount',       { defaultValue: 'Count' }),
                  t('records.thSubmittedBy', { defaultValue: 'Submitted by' }),
                ].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.results.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-12 text-center text-sm text-gray-400">
                    {t('records.empty', {
                      defaultValue:
                        'Per-record drill-down activates after the validation workshop wires Kobo forms to indicators. ' +
                        'The achievement count above remains accurate via the compute function.',
                    })}
                  </td>
                </tr>
              ) : (
                data.results.map((r, i) => (
                  <tr key={i} className="border-t border-gray-50 dark:border-gray-700/50">
                    <td className="px-4 py-3 tabular-nums">{String(r.date ?? '—')}</td>
                    <td className="px-4 py-3">{String(r.center ?? '—')}</td>
                    <td className="px-4 py-3 tabular-nums">{String(r.count ?? '—')}</td>
                    <td className="px-4 py-3 text-gray-500">{String(r.submitted_by ?? '—')}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
