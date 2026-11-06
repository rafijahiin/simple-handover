/**
 * Target Config — /admin/targets
 *
 * Editable indicator-target registry. Loads 44 rows from /api/indicators/
 * targets/ (or fewer when filtered for org_lead). Groups by Partner →
 * Objective → Activity. Each row's `target_value` is editable inline
 * via a click-to-edit pattern; saves PATCH the row and stamp updated_by
 * server-side.
 *
 * Permissions (enforced server-side via CanConfigureTargets):
 *   Developer + Supervisor → edit any partner
 *   Org Lead               → edit only own partner
 *   Manager / focal / etc. → 403 on PATCH; this page is route-gated
 *                            in App.tsx to only admins + org_lead.
 *
 * Visual rules:
 *   - target_value === null  →  orange "Not Set" pill (click to edit)
 *   - target_value === 0     →  shows literal "0"
 *   - Bandhu objectives render 1 → 2 → 4 with no placeholder for Obj 3
 *   - PHD objective_number=0 ("Overall") renders ABOVE Objective 1,
 *     not inside it
 */
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, Edit3, X, AlertCircle, Calendar } from 'lucide-react'
import { api, apiErrorMessage } from '@/api/client'
import { useAuth } from '@/context/AuthContext'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { bnIndicatorLabel, bnActivityLabel, bnUnit } from '@/data/indicatorLabelsBn'
import type { IndicatorTarget } from '@/types'

interface Grouped {
  partnerCode: string
  partnerColor: string
  objectives: {
    number: number
    activities: {
      code: string
      label: string
      rows: IndicatorTarget[]
    }[]
  }[]
}

/** Natural-sort key for activity codes.
 *  Handles SL1, SL2 … SL16 (numeric ordering instead of lexicographic
 *  which puts SL10 before SL2) and the SL5a/b/c sub-row suffix.
 *  Also handles legacy "1.1", "1.5a" codes. */
function codeKey(code: string): [number, number, string] {
  // Strip "SL" prefix → number + optional letter
  const m = code.match(/^(?:SL)?(\d+)(?:\.(\d+))?([a-z]*)$/i)
  if (m) {
    const major = parseInt(m[1], 10)
    const minor = m[2] ? parseInt(m[2], 10) : 0
    const suffix = (m[3] || '').toLowerCase()
    return [major, minor, suffix]
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

function groupTargets(rows: IndicatorTarget[]): Grouped[] {
  const byPartner = new Map<string, IndicatorTarget[]>()
  for (const r of rows) {
    if (!byPartner.has(r.partner_code)) byPartner.set(r.partner_code, [])
    byPartner.get(r.partner_code)!.push(r)
  }

  // Stable partner order per spec.
  const partnerOrder = ['CIPRB', 'Bandhu', 'PHD']
  const result: Grouped[] = []

  for (const code of partnerOrder) {
    const rs = byPartner.get(code)
    if (!rs || rs.length === 0) continue
    const color = rs[0].partner_color

    // Group by objective_number — sort numerically. Bandhu's set is {1,2,4};
    // PHD's new SIDA scheme is all objective_number=0 (one big group).
    const objNums = Array.from(new Set(rs.map(r => r.objective_number))).sort((a, b) => a - b)

    const objectives = objNums.map(num => {
      const objRows = rs.filter(r => r.objective_number === num)
      // Group rows under the same activity_label so commodity-split
      // activities like SL5 (5 commodity rows) collapse under one header.
      const byAct = new Map<string, IndicatorTarget[]>()
      for (const r of objRows) {
        if (!byAct.has(r.activity_label)) byAct.set(r.activity_label, [])
        byAct.get(r.activity_label)!.push(r)
      }
      const activities = Array.from(byAct.entries()).map(([label, list]) => {
        // Sort sub-rows naturally within each activity (SL5a, SL5b, ... SL5e)
        const sorted = [...list].sort((a, b) => compareCodes(a.activity_code, b.activity_code))
        return {
          // Parent code = the smallest code in this activity (e.g. "SL5" for SL5a-e group)
          code: sorted[0].activity_code.replace(/[a-z]+$/i, ''),
          label,
          rows: sorted,
        }
      })
      // Sort activities themselves by their first row's code (naturally)
      activities.sort((a, b) => compareCodes(a.rows[0].activity_code, b.rows[0].activity_code))
      return { number: num, activities }
    })

    result.push({ partnerCode: code, partnerColor: color, objectives })
  }
  return result
}

/** Pick the i18n key for this objective number — keeps the row label in
 *  sync with IndicatorGrid's group header. Bandhu's missing Obj 3 is
 *  not auto-renumbered; an unknown number falls back to the generic key. */
function objectiveI18nKey(num: number): string {
  if (num >= 0 && num <= 4) return `indicator.objective${num}`
  return 'indicator.objectiveOther'
}

// ─── Monthly target editor (Animesh's spec — UNFPA sets monthly splits) ────
//
// Contract window: 21 May 2026 → 20 Nov 2026 → 6 calendar months.
// One numeric input per month. Save PATCHes the whole monthly_targets list
// so partially-set rows are honoured (the row's month_target falls back to
// "Not set" if its YYYY-MM is missing from the JSON).
const PROGRAMME_MONTHS_LIST: { key: string; label: string }[] = [
  { key: '2026-05', label: 'May 2026' },
  { key: '2026-06', label: 'Jun 2026' },
  { key: '2026-07', label: 'Jul 2026' },
  { key: '2026-08', label: 'Aug 2026' },
  { key: '2026-09', label: 'Sep 2026' },
  { key: '2026-10', label: 'Oct 2026' },
  { key: '2026-11', label: 'Nov 2026' },
]

interface MonthlyButtonProps {
  row: IndicatorTarget
  canEdit: boolean
  onSaved: (updated: IndicatorTarget) => void
}

function MonthlyTargetsButton({ row, canEdit, onSaved }: MonthlyButtonProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const setCount = (row.monthly_targets ?? []).length
  return (
    <>
      <button
        onClick={() => canEdit && setOpen(true)}
        disabled={!canEdit}
        className="inline-flex items-center gap-1 rounded border border-gray-200 bg-white px-2 py-0.5 text-[11px] font-medium text-gray-700 hover:border-unfpa-blue/40 hover:text-unfpa-blue disabled:cursor-not-allowed disabled:opacity-50 dark:bg-gray-800 dark:text-gray-300 dark:border-gray-600"
        title={canEdit
          ? t('targetConfig.editMonthly', { defaultValue: 'Edit monthly splits' })
          : t('targetConfig.readOnlyMonthly', { defaultValue: 'Read-only' })
        }
      >
        <Calendar className="h-3 w-3" />
        {setCount === 0
          ? t('targetConfig.monthlyNotSet', { defaultValue: 'Set monthly' })
          : t('targetConfig.monthlyCount', {
              defaultValue: '{{set}}/{{total}} months',
              set: setCount, total: PROGRAMME_MONTHS_LIST.length,
            })}
      </button>
      {open && (
        <MonthlyTargetsModal
          row={row}
          onClose={() => setOpen(false)}
          onSaved={(u) => { onSaved(u); setOpen(false) }}
        />
      )}
    </>
  )
}

interface MonthlyModalProps {
  row: IndicatorTarget
  onClose: () => void
  onSaved: (updated: IndicatorTarget) => void
}

function MonthlyTargetsModal({ row, onClose, onSaved }: MonthlyModalProps) {
  const { t } = useTranslation()
  // Seed the modal with whatever's already saved; missing months stay blank
  // (= "Not set"). Map keyed by YYYY-MM.
  const initial: Record<string, string> = {}
  for (const e of row.monthly_targets ?? []) {
    initial[e.month] = String(e.target ?? '')
  }
  const [draft, setDraft] = useState<Record<string, string>>(initial)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const setMonth = (key: string, value: string) =>
    setDraft(d => ({ ...d, [key]: value }))

  const sumPlanned = PROGRAMME_MONTHS_LIST.reduce((s, m) => {
    const n = parseFloat(draft[m.key] ?? '')
    return s + (Number.isFinite(n) ? n : 0)
  }, 0)
  const overall = parseFloat(String(row.target_value ?? '0')) || 0

  const handleSave = async () => {
    setSaving(true)
    setError('')
    try {
      const payload = PROGRAMME_MONTHS_LIST
        .map(m => ({ month: m.key, target: parseFloat(draft[m.key] ?? '') }))
        .filter(e => Number.isFinite(e.target))
      const resp = await api.patch<IndicatorTarget>(
        `/indicators/targets/${row.id}/`,
        { monthly_targets: payload },
      )
      onSaved(resp.data)
    } catch (e) {
      setError(apiErrorMessage(e, 'Save failed.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md rounded-xl bg-white p-6 shadow-2xl dark:bg-gray-800"
      >
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h3 className="text-base font-bold text-gray-900 dark:text-gray-100">
              {t('targetConfig.monthlyModalTitle', { defaultValue: 'Monthly target splits' })}
            </h3>
            <p className="mt-1 text-xs text-gray-500 line-clamp-2">{row.indicator_label}</p>
            <p className="mt-1 text-[11px] font-mono text-gray-400">
              {row.activity_code} · {t('targetConfig.overall', { defaultValue: 'Overall' })} = {overall.toLocaleString()} {row.unit}
            </p>
          </div>
          <button onClick={onClose} className="rounded p-1 text-gray-400 hover:bg-gray-100">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-2">
          {PROGRAMME_MONTHS_LIST.map(m => (
            <div key={m.key} className="grid grid-cols-2 items-center gap-3">
              <label className="text-sm text-gray-700 dark:text-gray-300">{m.label}</label>
              <input
                type="number"
                inputMode="numeric"
                value={draft[m.key] ?? ''}
                onChange={(e) => setMonth(m.key, e.target.value)}
                placeholder={t('targetConfig.notSetPill')}
                className="rounded border border-gray-300 px-2 py-1 text-sm font-mono focus:border-unfpa-blue focus:outline-none focus:ring-1 focus:ring-unfpa-blue/40 dark:bg-gray-700 dark:border-gray-600"
              />
            </div>
          ))}
        </div>

        <div className="mt-4 rounded bg-gray-50 p-3 text-xs text-gray-600 dark:bg-gray-900 dark:text-gray-400">
          <div className="flex justify-between">
            <span>{t('targetConfig.plannedSum', { defaultValue: 'Sum of months' })}</span>
            <b className="font-mono">{sumPlanned.toLocaleString()}</b>
          </div>
          <div className="flex justify-between">
            <span>{t('targetConfig.overallTarget', { defaultValue: 'Overall target' })}</span>
            <b className="font-mono">{overall.toLocaleString()}</b>
          </div>
          {sumPlanned !== overall && overall > 0 && (
            <div className="mt-1 text-amber-600">
              ⚠ {t('targetConfig.sumMismatch', {
                defaultValue: 'Monthly sum doesn\'t match overall target — review before saving.',
              })}
            </div>
          )}
        </div>

        {error && <p className="mt-3 text-xs text-red-600">{error}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            disabled={saving}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 dark:bg-gray-700 dark:text-gray-200 dark:border-gray-600"
          >
            {t('targetConfig.cancel')}
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="rounded bg-unfpa-blue px-3 py-1.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            {saving
              ? t('targetConfig.saving', { defaultValue: 'Saving…' })
              : t('targetConfig.save')
            }
          </button>
        </div>
      </div>
    </div>
  )
}


interface TargetCellProps {
  row: IndicatorTarget
  canEdit: boolean
  onSaved: (updated: IndicatorTarget) => void
}

function TargetCell({ row, canEdit, onSaved }: TargetCellProps) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(row.target_value ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const isNull = row.target_value === null

  const handleSave = async () => {
    setSaving(true)
    setError('')
    try {
      const trimmed = String(draft).trim()
      // Guard non-numeric input — without this a stray letter round-trips to
      // the backend and re-renders as "NaN".
      if (trimmed !== '' && (isNaN(Number(trimmed)) || Number(trimmed) < 0)) {
        setError('Enter a non-negative number.')
        setSaving(false)
        return
      }
      const value = trimmed === '' ? null : trimmed
      const resp = await api.patch<IndicatorTarget>(
        `/indicators/targets/${row.id}/`,
        { target_value: value },
      )
      onSaved(resp.data)
      setEditing(false)
    } catch (e) {
      setError(apiErrorMessage(e, 'Save failed.'))
    } finally {
      setSaving(false)
    }
  }

  const handleCancel = () => {
    setDraft(row.target_value ?? '')
    setEditing(false)
    setError('')
  }

  if (!editing) {
    if (isNull) {
      return (
        <button
          onClick={() => canEdit && setEditing(true)}
          disabled={!canEdit}
          className="inline-flex items-center gap-1.5 rounded-full bg-orange-50 px-2.5 py-0.5 text-xs font-medium text-orange-700 ring-1 ring-orange-300 hover:bg-orange-100 disabled:cursor-not-allowed disabled:opacity-60"
          title={canEdit ? 'Click to set target' : 'Read-only — no permission to edit'}
        >
          <AlertCircle className="h-3 w-3" />
          {t('targetConfig.notSetPill')}
        </button>
      )
    }
    return (
      <button
        onClick={() => canEdit && setEditing(true)}
        disabled={!canEdit}
        className="inline-flex items-center gap-1.5 text-sm font-mono text-gray-900 dark:text-gray-100 hover:text-unfpa-blue disabled:cursor-default disabled:hover:text-gray-900"
        title={canEdit ? 'Click to edit' : ''}
      >
        {Number(row.target_value).toLocaleString()}
        {canEdit && <Edit3 className="h-3 w-3 opacity-40" />}
      </button>
    )
  }

  return (
    <div className="flex items-center gap-1.5">
      <input
        type="number"
        min={0}
        step={1}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        autoFocus
        className="w-24 rounded border border-gray-300 px-2 py-0.5 text-sm font-mono focus:border-unfpa-blue focus:outline-none focus:ring-1 focus:ring-unfpa-blue/40"
        placeholder="value"
        onKeyDown={(e) => {
          if (e.key === 'Enter') handleSave()
          if (e.key === 'Escape') handleCancel()
        }}
      />
      <button
        onClick={handleSave}
        disabled={saving}
        className="rounded p-1 text-green-600 hover:bg-green-50 disabled:opacity-50"
        title={t('targetConfig.save')}
      >
        <Check className="h-4 w-4" />
      </button>
      <button
        onClick={handleCancel}
        disabled={saving}
        className="rounded p-1 text-gray-500 hover:bg-gray-50"
        title={t('targetConfig.cancel')}
      >
        <X className="h-4 w-4" />
      </button>
      {error && <span className="text-xs text-red-600">{error}</span>}
    </div>
  )
}

export { TargetConfig as default, TargetConfig as ProgrammeTargetsTab }

function TargetConfig() {
  const { user } = useAuth()
  const { t, i18n } = useTranslation()
  const isBn = i18n.language?.startsWith('bn')
  const [rows, setRows] = useState<IndicatorTarget[] | null>(null)
  const [error, setError] = useState('')

  const canEditRow = (_row: IndicatorTarget): boolean => {
    // UNFPA Supervisor + Developer (Rafi) only — org leads cannot edit
    // their own targets any more (Animesh's 2026-06-01 directive).
    if (!user) return false
    return user.role === 'developer' || user.role === 'supervisor'
  }

  useEffect(() => {
    let cancelled = false
    api.get('/indicators/targets/?page_size=200')
      .then(r => {
        if (cancelled) return
        const data = Array.isArray(r.data) ? r.data : r.data?.results ?? []
        setRows(data)
      })
      .catch(e => { if (!cancelled) setError(apiErrorMessage(e, 'Failed to load targets.')) })
    return () => { cancelled = true }
  }, [])

  // Org Lead scope — they're allowed to view the page READ-ONLY but
  // only their own partner's indicators. Developer + Supervisor see
  // everything. The API still returns all rows to org_lead (because
  // can_read_other_orgs is True for them); the filter here is the UI
  // restriction.
  const visibleRows = useMemo(() => {
    if (!rows) return null
    if (user?.role === 'org_lead') {
      return rows.filter(r => r.partner_code === user.organisation)
    }
    return rows
  }, [rows, user])

  const grouped = useMemo(() => (visibleRows ? groupTargets(visibleRows) : []), [visibleRows])

  const handleRowSaved = (updated: IndicatorTarget) => {
    setRows(prev => prev?.map(r => r.id === updated.id ? updated : r) ?? null)
  }

  if (rows === null) return <PageLoader />

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('targetConfig.title')}</h1>
        <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
          {t('targetConfig.subtitle')}
        </p>
        {user?.role === 'org_lead' && (
          <p className="mt-2 rounded-md bg-blue-50 px-3 py-2 text-xs text-blue-800 dark:bg-blue-900/20 dark:text-blue-200">
            {t('targetConfig.scopeBannerOrgLead', { org: user.organisation })}
          </p>
        )}
      </div>

      {error && (
        <div className="mb-4 rounded-md bg-red-50 px-4 py-3 text-sm text-red-700 ring-1 ring-red-200">
          {error}
        </div>
      )}

      <div className="space-y-10">
        {grouped.map(g => (
          <section key={g.partnerCode} className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-gray-200 dark:bg-gray-800 dark:ring-gray-700">
            <header className="mb-4 flex items-center gap-3">
              <span
                className="inline-block h-3 w-3 rounded-full"
                style={{ backgroundColor: g.partnerColor }}
                aria-hidden
              />
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">{g.partnerCode}</h2>
              <span className="text-sm text-gray-500">
                {g.objectives.reduce((n, o) => n + o.activities.reduce((m, a) => m + a.rows.length, 0), 0)} indicators
              </span>
            </header>

            {g.objectives.map(obj => (
              <div key={obj.number} className="mb-6 last:mb-0">
                <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                  {/* PHD uses the SIDA SL1–SL16 scheme — no objective subdivisions.
                      All PHD rows have objective_number=0 ⇒ show one banner. */}
                  {g.partnerCode === 'PHD'
                    ? 'SIDA Framework — Activities & Indicators (SL1–SL16)'
                    : t(objectiveI18nKey(obj.number), { n: obj.number })}
                </h3>
                <div className="overflow-x-auto rounded-lg border border-gray-100 dark:border-gray-700">
                  <table className="min-w-full divide-y divide-gray-100 dark:divide-gray-700">
                    <thead className="bg-gray-50/60 dark:bg-gray-900/40">
                      <tr>
                        <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">{t('targetConfig.tableActivity')}</th>
                        <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">{t('targetConfig.tableIndicator')}</th>
                        <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">{t('targetConfig.tableTarget')}</th>
                        <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">{t('targetConfig.tableUnit')}</th>
                        <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">{t('targetConfig.tableMonthly', { defaultValue: 'Monthly Splits' })}</th>
                        <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">{t('targetConfig.tableSource', { defaultValue: 'Source Form' })}</th>
                        <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">{t('targetConfig.tableLastUpdated')}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50 dark:divide-gray-700/50">
                      {obj.activities.map(act => (
                        act.rows.map((row, idx) => (
                          <tr key={row.id} className="hover:bg-gray-50/60 dark:hover:bg-gray-700/30">
                            <td className="whitespace-nowrap px-3 py-2 text-sm font-mono text-gray-700 dark:text-gray-300">
                              {row.activity_code}
                            </td>
                            <td className="px-3 py-2 text-sm text-gray-900 dark:text-gray-100">
                              {idx === 0 && (
                                <div className="text-[11px] font-medium uppercase tracking-wide text-gray-500 mb-0.5">
                                  {isBn
                                    ? bnActivityLabel(row.partner_code, row.activity_code, act.label)
                                    : act.label}
                                </div>
                              )}
                              {isBn
                                ? bnIndicatorLabel(row.partner_code, row.activity_code, row.indicator_label)
                                : row.indicator_label}
                            </td>
                            <td className="px-3 py-2 text-right">
                              <TargetCell row={row} canEdit={canEditRow(row)} onSaved={handleRowSaved} />
                            </td>
                            <td className="px-3 py-2 text-sm text-gray-600 dark:text-gray-400">
                              {isBn ? bnUnit(row.unit) : row.unit}
                            </td>
                            <td className="px-3 py-2">
                              <MonthlyTargetsButton row={row} canEdit={canEditRow(row)} onSaved={handleRowSaved} />
                            </td>
                            <td className="px-3 py-2 text-[11px] font-mono text-gray-600 dark:text-gray-400">
                              {row.source_form_slug ? (
                                <span
                                  title={row.source_form_slug}
                                  className="inline-block max-w-[180px] truncate rounded bg-gray-100 px-1.5 py-0.5 dark:bg-gray-700"
                                >
                                  {row.source_form_slug.replace(/^spondon_/, '').replace(/_v\d+$/, '')}
                                </span>
                              ) : (
                                <span className="text-gray-400" title={t('targetConfig.notKoboSourced', { defaultValue: 'Computed from registry / stock — no Kobo form' })}>—</span>
                              )}
                            </td>
                            <td className="px-3 py-2 text-xs text-gray-500">
                              {row.updated_by_email ? (
                                <>
                                  {row.updated_by_email}
                                  <br />
                                  <span className="text-gray-400">{new Date(row.updated_at).toLocaleString()}</span>
                                </>
                              ) : (
                                <span className="text-gray-400">—</span>
                              )}
                            </td>
                          </tr>
                        ))
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </section>
        ))}
      </div>
    </div>
  )
}
