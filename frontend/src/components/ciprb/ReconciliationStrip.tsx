/**
 * CIPRB data-integrity health strip.
 *
 * Surfaces — ON the dashboard, never as an alert — the answer to the one
 * question this whole system has to get right: "is every KoboToolbox submission
 * actually showing up in the dashboard?" It reads the stored reconciliation
 * snapshot (written server-side by `manage.py reconcile_ciprb`, which replays
 * every live Kobo payload through the real handlers inside a rolled-back
 * savepoint and counts how many the app was missing). This component only READS
 * that snapshot — it never triggers the replay.
 *
 * Healthy  → one slim green line, easy to ignore.
 * Drift    → a prominent amber panel naming each affected form in plain words,
 *            because a silent gap here is exactly how 90 death records went
 *            missing once.
 *
 * Deliberately no Telegram / email / any alert channel — the strip is the whole
 * surface, per the CIPRB-dashboard-only scope.
 */
import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, RefreshCw, HelpCircle } from 'lucide-react'
import { api } from '@/api/client'

// Plain-language names so a non-technical reader (Nuruzzaman, CIPRB) sees the
// form, not the slug. Keyed by the slug the backend reports.
const FORM_NAMES: Record<string, string> = {
  ciprb_mpdsr_community_maternal_v1: 'MPDSR — community maternal death (F1)',
  ciprb_mpdsr_community_neonatal_v1: 'MPDSR — community neonatal death (F2)',
  ciprb_mpdsr_facility_maternal_v1: 'MPDSR — facility maternal death (F4)',
  ciprb_mpdsr_facility_neonatal_v1: 'MPDSR — facility neonatal death (F5)',
  ciprb_social_autopsy_v1: 'MPDSR — social autopsy',
  ciprb_notification_slip_01_v1: 'Death notification slip 01',
  ciprb_notification_slip_02_v1: 'Death notification slip 02',
  ciprb_near_miss_v1: 'Maternal near-miss',
  ciprb_fistula_questions_v1: 'Fistula case (question bank)',
  ciprb_fistula_campaign_v1: 'Fistula campaign — daily activity',
  ciprb_mpdsr_response_plan_v1: 'MPDSR response-plan action',
}

interface FormHealth {
  slug: string
  uid?: string
  kobo_count?: number
  app_rows?: number
  stranded?: number
  crashes?: number
  hook_active?: boolean | null
  error?: string
}

interface ReconPayload {
  available: boolean
  run_at?: string
  forms: FormHealth[]
  total_stranded?: number
  total_crashes?: number
  all_ok?: boolean
}

function formName(slug: string): string {
  return FORM_NAMES[slug] || slug
}

function timeAgo(iso?: string): string {
  if (!iso) return ''
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const mins = Math.round((Date.now() - then) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 24) return `${hrs} hr ago`
  const days = Math.round(hrs / 24)
  return `${days} day${days === 1 ? '' : 's'} ago`
}

export function ReconciliationStrip() {
  const [data, setData] = useState<ReconPayload | null>(null)
  const [error, setError] = useState(false)
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    setError(false)
    api
      .get<ReconPayload>('/mpdsr/reconciliation/')
      .then((res) => setData(res.data))
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // The endpoint itself failed — do not imply health. Say it plainly.
  if (error) {
    return (
      <Bar tone="unknown" icon={<HelpCircle size={15} />}>
        <span>
          Data-integrity check couldn't be reached. This does not mean data is
          missing — the health check itself did not load.
        </span>
        <RetryButton onClick={load} />
      </Bar>
    )
  }

  if (loading && !data) {
    return (
      <Bar tone="unknown" icon={<RefreshCw size={15} />}>
        <span>Checking that every KoboToolbox submission is in the dashboard…</span>
      </Bar>
    )
  }

  if (!data) return null

  // No snapshot has ever been written — the server-side check has not run yet.
  if (!data.available) {
    return (
      <Bar tone="unknown" icon={<HelpCircle size={15} />}>
        <span>
          Data-integrity check has not run yet. Once it runs on the server, this
          strip will confirm every Kobo submission is represented here.
        </span>
        <RetryButton onClick={load} />
      </Bar>
    )
  }

  const stranded = data.total_stranded || 0
  const crashes = data.total_crashes || 0
  const hooksDown = (data.forms || []).filter((f) => f.hook_active === false)
  const problemForms = (data.forms || []).filter(
    (f) => (f.stranded || 0) > 0 || (f.crashes || 0) > 0,
  )
  const healthy = stranded === 0 && crashes === 0 && hooksDown.length === 0 && !data.forms.some((f) => f.error)

  if (healthy) {
    return (
      <Bar tone="ok" icon={<CheckCircle2 size={15} />}>
        <span>
          All CIPRB forms reconciled — every KoboToolbox submission is showing in
          the dashboard.
        </span>
        <Meta runAt={data.run_at} onRefresh={load} />
      </Bar>
    )
  }

  // Drift — surface it prominently and in plain language.
  return (
    <div
      role="alert"
      className="card"
      style={{
        border: '1px solid rgba(180, 83, 9, 0.4)',
        background: 'rgba(180, 83, 9, 0.06)',
        padding: '14px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <AlertTriangle size={17} style={{ color: '#B45309', flexShrink: 0 }} />
        <strong style={{ fontSize: 13.5, color: '#8A4200' }}>
          Data-integrity check found a gap between KoboToolbox and the dashboard
        </strong>
        <span style={{ flex: 1 }} />
        <Meta runAt={data.run_at} onRefresh={load} dark />
      </div>

      <ul style={{ margin: 0, paddingLeft: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 7 }}>
        {problemForms.map((f) => (
          <li key={f.slug} style={{ fontSize: 12.5, color: '#7A3A00', lineHeight: 1.5 }}>
            <strong style={{ color: '#8A4200' }}>{formName(f.slug)}:</strong>{' '}
            {(f.stranded || 0) > 0 && (
              <span>
                {f.stranded} submission{f.stranded === 1 ? '' : 's'} in Kobo{' '}
                {f.stranded === 1 ? 'is' : 'are'} not showing in the dashboard
                {' '}({f.kobo_count ?? '?'} in Kobo, {f.app_rows ?? '?'} here).
              </span>
            )}
            {(f.crashes || 0) > 0 && (
              <span>
                {' '}
                {f.crashes} submission{f.crashes === 1 ? '' : 's'} fail to import
                (the handler errors on them).
              </span>
            )}
          </li>
        ))}
        {hooksDown.map((f) => (
          <li key={`hook-${f.slug}`} style={{ fontSize: 12.5, color: '#7A3A00', lineHeight: 1.5 }}>
            <strong style={{ color: '#8A4200' }}>{formName(f.slug)}:</strong>{' '}
            automatic sync from Kobo is turned off — new submissions will not
            arrive until it is re-enabled.
          </li>
        ))}
        {data.forms
          .filter((f) => f.error)
          .map((f) => (
            <li key={`err-${f.slug}`} style={{ fontSize: 12.5, color: '#7A3A00', lineHeight: 1.5 }}>
              <strong style={{ color: '#8A4200' }}>{formName(f.slug)}:</strong>{' '}
              could not be checked ({f.error}).
            </li>
          ))}
      </ul>

      <div style={{ fontSize: 11.5, color: 'var(--muted)', lineHeight: 1.5 }}>
        A gap means live data collected in the field is not represented above.
        Re-running the server reconciliation recovers stranded submissions.
      </div>
    </div>
  )
}

/* ── small presentational helpers ─────────────────────────────────────────── */

function Bar({
  tone,
  icon,
  children,
}: {
  tone: 'ok' | 'unknown'
  icon: React.ReactNode
  children: React.ReactNode
}) {
  const palette =
    tone === 'ok'
      ? { fg: '#15803D', bd: 'rgba(21, 128, 61, 0.28)', bg: 'rgba(21, 128, 61, 0.06)' }
      : { fg: 'var(--ink-3)', bd: 'var(--hair)', bg: 'var(--surface-2)' }
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        flexWrap: 'wrap',
        padding: '9px 14px',
        borderRadius: 10,
        border: `1px solid ${palette.bd}`,
        background: palette.bg,
        color: palette.fg,
        fontSize: 12.5,
        fontWeight: 500,
        lineHeight: 1.45,
      }}
    >
      <span style={{ flexShrink: 0, display: 'inline-flex' }}>{icon}</span>
      {children}
    </div>
  )
}

function Meta({ runAt, onRefresh, dark }: { runAt?: string; onRefresh: () => void; dark?: boolean }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
      {runAt && (
        <span style={{ fontSize: 11, color: dark ? 'var(--muted)' : 'inherit', opacity: 0.85 }}>
          checked {timeAgo(runAt)}
        </span>
      )}
      <button
        type="button"
        onClick={onRefresh}
        title="Reload the latest health check"
        aria-label="Reload the latest health check"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 4,
          background: 'transparent',
          border: 'none',
          color: dark ? '#8A4200' : 'inherit',
          cursor: 'pointer',
          fontSize: 11.5,
          fontWeight: 600,
          padding: 2,
        }}
      >
        <RefreshCw size={12} />
      </button>
    </span>
  )
}

function RetryButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        marginLeft: 'auto',
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        background: 'transparent',
        border: '1px solid var(--hair)',
        borderRadius: 8,
        color: 'inherit',
        cursor: 'pointer',
        fontSize: 11.5,
        fontWeight: 600,
        padding: '3px 10px',
      }}
    >
      <RefreshCw size={12} /> Retry
    </button>
  )
}
