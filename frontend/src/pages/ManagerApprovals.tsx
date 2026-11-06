/**
 * Manager Approvals — editorial light console.
 *
 * Queue spine (left) + focus panel (right) layout.
 * Click to select; click Approve/Reject buttons to act.
 * Preserves both Programs and Legacy API flows.
 */
import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import {
  X, Check, AlertTriangle, FileText, Plus, RefreshCw, Trash2,
} from 'lucide-react'
import { useReducedMotion } from 'motion/react'
import { useTranslation } from 'react-i18next'
import { api, apiErrorMessage } from '@/api/client'
import { bandhuField, isBandhuForm, decodeBandhuValue } from '@/data/bandhuFieldLabels'
import { useAuth } from '@/context/AuthContext'
import { NilReportModal } from '@/components/approvals/NilReportModal'
import { usePolling } from '@/hooks/usePolling'
import { PageLoader, LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { formatDateTime } from '@/utils/format'
import type { Submission, SubmissionDetail, ProgramPendingResponse } from '@/types'

// ─── CountUp hook ─────────────────────────────────────────────────────────────

function useCountUp(target: number, dur = 1300) {
  const [v, setV] = useState(0)
  const reduce = useReducedMotion()
  useEffect(() => {
    if (reduce) { setV(target); return }
    let raf: number
    let start: number | null = null
    const step = (ts: number) => {
      if (!start) start = ts
      const p = Math.min((ts - start) / dur, 1)
      setV(Math.round(target * p * p))
      if (p < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [target, dur, reduce])
  return v
}

function CountUp({ value, dur }: { value: number; dur?: number }) {
  return <>{useCountUp(value, dur).toLocaleString()}</>
}

// ─── Submitted-values grouping ────────────────────────────────────────────────
// Takes the raw_payload / raw_data from a Kobo submission and groups the
// fields into clinically-meaningful sections so the manager reads a clean
// readout instead of a flat alphabetical dump. Prefix-based — no per-field
// config table to maintain.

interface FieldRow { label: string; display: string; isEmpty: boolean; mono?: boolean }
interface FieldGroup { title: string; rows: FieldRow[] }

const _PREFIX_GROUPS: Array<[RegExp, string, string]> = [
  // [match, group title, prefix to strip from label]
  [/^_pull_/,           'Patient (from registry)', '_pull_'],
  [/^clinic_ref_/,      'Referrals',               'clinic_ref_'],
  [/^clinic_diag_/,     'Diagnoses',               'clinic_diag_'],
  [/^clinic_fu_/,       'Follow-up',               'clinic_fu_'],
  [/_screen$/,          'Screenings',              ''],            // suffix match
  [/^clinic_treatment/, 'Treatment',               'clinic_'],
  [/^clinic_contracep/, 'Contraception',           'clinic_'],
  [/^clinic_condom/,    'Treatment',               'clinic_'],
  [/^clinic_/,          'Visit',                   'clinic_'],
  [/^htc_test/,         'HIV test algorithm',      'htc_'],
  [/^htc_/,             'HTC',                     'htc_'],
  [/^ref_/,             'Referral',                'ref_'],
  [/^counsel_/,         'Counselling',             'counsel_'],
  [/^gedu_/,            'Group education',         'gedu_'],
  [/^event_/,           'Event',                   'event_'],
  [/^stock_/,           'Stock',                   'stock_'],
  [/^mat_/,             'Material',                'mat_'],
  [/^gbv_/,             'GBV corner',              'gbv_'],
  [/^record_type$|^service_type$|^activity_type$|^event_subtype$|^gedu_audience$|^client_id$/,
                        'Patient (from registry)', ''],
  [/^enumerator_/,      'Submitted by',            'enumerator_'],
  [/^centre_id$|^organisation$|^location$/, 'Submission info', ''],
]

// Fields we never show. The Kobo /api/v2/data response is full of internal
// metadata (Id, Uuid, InstanceID, _submission_time, _geolocation, Validation
// status, Xform Id string, Submission time, etc.) that means nothing to a
// clinical reviewer. Filter them out so the readout shows ONLY what the
// field worker actually typed.
function _isSystemKey(key: string, rawKey: string): boolean {
  // Anything under formhub/, meta/, __ prefix → Kobo internals
  if (rawKey.startsWith('formhub')) return true
  if (rawKey.startsWith('meta')) return true
  if (key.startsWith('__')) return true
  // Anything starting with single underscore EXCEPT our _pull_* lookups
  // (which are the auto-filled patient identity values we want to show).
  if (key.startsWith('_') && !key.startsWith('_pull_')) return true
  // Explicit Kobo metadata that doesn't start with _ but is still noise
  const koboMeta = new Set([
    'start','end','today','deviceid','username','__version__',
    'instanceID',
    'Id','Uuid','RootUuid','InstanceID',
    'Tags','Notes','Attachments',
    'Geolocation','Status',
    'Submission time','SubmissionTime','submission_time',
    'Xform Id string','XformIdString','xform_id_string',
    'Validation status','ValidationStatus','validation_status',
    'BootUuid',
  ])
  if (koboMeta.has(key)) return true
  // Duplicates of fields already shown in the metadata cards above
  const dupeOfCards = new Set([
    'organisation','centre_id','location','enumerator_phone',
  ])
  if (dupeOfCards.has(key)) return true
  return false
}

function _humanise(key: string, stripPrefix: string): string {
  let s = key
  if (stripPrefix) s = s.replace(stripPrefix, '')
  s = s.replace(/_/g, ' ').trim()
  if (!s) return key
  return s.charAt(0).toUpperCase() + s.slice(1)
}

function _formatValue(v: any): { display: string; isEmpty: boolean; mono?: boolean } {
  // ONLY a genuinely absent answer (null / undefined / "") is "empty" and may
  // be collapsed by default. An explicit "No" or a 0 is real data the worker
  // entered and must stay visible — hiding it loses negative screenings,
  // declined referrals, zero counts, etc. (the reviewer needs to see those).
  if (v === null || v === undefined || v === '') return { display: '—', isEmpty: true }
  if (v === true || v === 'yes' || v === 'true') return { display: '✓ Yes', isEmpty: false }
  if (v === false || v === 'no' || v === 'false') return { display: 'No', isEmpty: false }
  if (typeof v === 'object') return { display: JSON.stringify(v), isEmpty: false, mono: true }
  const s = String(v)
  // Numbers (including 0) are real values — render the figure as-is, never
  // collapse a count to a Yes/No, and never treat it as empty.
  return { display: s, isEmpty: false, mono: /^[\d.\s,:/-]+$/.test(s) }
}

export function groupSubmittedFields(payload: Record<string, any>, formType?: string): FieldGroup[] {
  const bandhu = isBandhuForm(formType)
  const buckets = new Map<string, FieldRow[]>()
  const order: string[] = []   // first-seen group order (used for Bandhu)
  for (const [rawKey, value] of Object.entries(payload)) {
    const key = rawKey.split('/').pop()!
    if (_isSystemKey(key, rawKey)) continue

    let groupTitle = 'Other'
    let label = ''
    // Bandhu fields carry per-tool prefixes — resolve them to the source tool
    // group with abbreviations expanded, instead of the generic "Pr tg".
    const bf = bandhu ? bandhuField(key) : null
    if (bf) {
      groupTitle = bf.group
      label = bf.label
    } else {
      let stripPrefix = ''
      for (const [re, title, strip] of _PREFIX_GROUPS) {
        if (re.test(key)) { groupTitle = title; stripPrefix = strip; break }
      }
      label = _humanise(key, stripPrefix)
    }

    // Decode coded Bandhu values (TG="03"→"FSW", referral codes→labels) so the
    // reviewer reads what was recorded, not a code, before approving.
    const decoded = bandhu ? decodeBandhuValue(key, value) : value
    const fmt = _formatValue(decoded)
    const row: FieldRow = { label, display: fmt.display, isEmpty: fmt.isEmpty, mono: fmt.mono }
    if (!buckets.has(groupTitle)) { buckets.set(groupTitle, []); order.push(groupTitle) }
    buckets.get(groupTitle)!.push(row)
  }
  // Bandhu: group titles already encode their source tool — keep first-seen
  // order (Submission first), 'Other' last.
  if (bandhu) {
    const titles = order.filter(t => t !== 'Other')
    if (buckets.has('Other')) titles.push('Other')
    const submissionFirst = titles.sort((a, b) =>
      (a === 'Submission' ? -1 : 0) - (b === 'Submission' ? -1 : 0))
    return submissionFirst.map(title => ({ title, rows: buckets.get(title)! }))
  }
  // Stable canonical ordering. Patient first, Other last.
  const ORDER = [
    'Patient (from registry)','Submission info','Submitted by',
    'Visit','Screenings','Diagnoses','Treatment','Contraception',
    'Follow-up','Referrals','HIV test algorithm','HTC','Referral',
    'Counselling','Group education','Event','Material','Stock','GBV corner',
    'Other',
  ]
  return ORDER
    .filter(t => buckets.has(t))
    .map(title => ({ title, rows: buckets.get(title)! }))
}

// Keyboard shortcuts were retired entirely — click-only interactions
// across the queue. Removing keyboard handlers means no surprise
// destructive actions (Enter = approve) when a manager focuses an
// element near the queue.

// ─── Stat block ───────────────────────────────────────────────────────────────

function Stat({ label, value, suffix = '', sub }: { label: string; value: number; suffix?: string; sub: string }) {
  return (
    <div>
      <div className="kicker" style={{ marginBottom: 6 }}><span className="dot" />{label}</div>
      <div className="num-display" style={{ fontSize: 38, fontFamily: 'var(--display)', fontStyle: 'italic' }}>
        <CountUp value={value} />{suffix}
      </div>
      <div className="mono mute" style={{ fontSize: 11, marginTop: 2 }}>{sub}</div>
    </div>
  )
}

// ─── Mini location map ────────────────────────────────────────────────────────

const BD_PATHS: Record<string, string> = {
  dhaka:     'M275 50 L370 55 L380 130 L355 180 L300 175 L260 145 L255 95 Z',
  mymensingh:'M165 165 L260 145 L300 175 L295 245 L240 295 L185 280 L150 240 L140 195 Z',
  rajshahi:  'M355 180 L440 175 L460 240 L420 280 L370 270 L355 215 Z',
  rangpur:   'M460 175 L590 165 L630 220 L595 295 L520 285 L460 240 L460 195 Z',
  khulna:    'M295 245 L370 270 L420 280 L450 330 L420 400 L350 390 L300 360 L295 295 Z',
  barishal:  'M150 290 L240 295 L300 360 L290 460 L230 490 L160 460 L140 380 Z',
  sylhet:    'M290 460 L350 390 L420 400 L420 470 L380 510 L320 500 L290 480 Z',
  chattogram:'M420 280 L520 285 L595 295 L605 360 L580 460 L545 540 L500 560 L460 530 L450 470 L420 400 Z',
}

function MiniLocationMap() {
  const cx = 300 + Math.random() * 200
  const cy = 200 + Math.random() * 200
  return (
    <div style={{
      width: '100%', height: 80, background: 'var(--surface-2)',
      border: '1px solid var(--hair)', borderRadius: 10,
      position: 'relative', overflow: 'hidden',
    }}>
      <svg viewBox="100 30 600 540" style={{ width: '100%', height: '100%' }}>
        {Object.values(BD_PATHS).map((p, i) => (
          <path key={i} d={p} fill="rgba(0,145,199,0.04)" stroke="rgba(0,145,199,0.28)" strokeWidth={1} />
        ))}
        <circle cx={cx} cy={cy} r={6} fill="none" stroke="var(--coral)" strokeWidth={2}>
          <animate attributeName="r" values="6;16" dur="1.6s" repeatCount="indefinite" />
          <animate attributeName="opacity" values="0.8;0" dur="1.6s" repeatCount="indefinite" />
        </circle>
        <circle cx={cx} cy={cy} r={5} fill="var(--coral)" stroke="white" strokeWidth={2} />
      </svg>
    </div>
  )
}

// ─── Unified queue item type ──────────────────────────────────────────────────

interface QueueItem {
  id: string
  model_type: string
  model_label: string
  title: string
  summary: string
  organisation: string
  center_name: string
  submitted_by: string
  created_at: string
  kobo_submission_id?: string
  // Human-readable Kobo form name (e.g. "Fistula Campaign") so the manager
  // sees exactly which form they're approving, not a raw slug.
  form_type_display?: string
  kind: 'program' | 'legacy' | 'baseline'
  // For program items: the DRF endpoint slug (e.g. 'referrals',
  // 'clinic-visits') so the detail fetcher can build the right URL.
  endpoint?: string
  // ── D5 baseline verification fields (kind === 'baseline') ──────────────────
  // The baseline queue is CIPRB-conducted and CIPRB/UNFPA-only; these carry the
  // verification-list payload so the focus panel renders without a detail fetch.
  population?: string          // 'hijra' | 'fsw'
  serial?: string              // questionnaire serial
  site_code?: string
  age_display?: string
  gps_missing?: boolean
  duplicate_preview?: boolean
  raw_data?: Record<string, any>
  // Readable, server-resolved detail for the baseline card (real question/answer
  // text, not codes). headline = curated at-a-glance facts; answers = full
  // interview grouped by questionnaire section.
  headline?: { label: string; value: string }[]
  answers?: BaselineAnswerRow[]
  answer_count?: number
  urgent?: boolean
  latitude?: string
  longitude?: string
  // Animesh's baseline duplication warning — true when an earlier baseline
  // survey from the same (district, upazila, day) is already on file.
  is_baseline_duplicate?: boolean
  // Animesh's MPDSR QA-gate flags (deck slide 9). Short stable tag list
  // (e.g. 'AGE_LOW', 'CAUSE_EMPTY'). Renders amber AlertTriangle pill in
  // the queue spine + expanded human-readable list in the focus panel.
  logic_flags?: string[]
  // Two-stage approval (Bandhu): which gate this item is at.
  two_stage?: boolean
  stage?: 'manager' | 'unfpa'
  approval_status?: string
  // One-paragraph plain-language narrative of the activity (UNFPA-only view).
  narrative?: string
}

function toQueueItems(programsData: ProgramPendingResponse | null, submissions: Submission[] | null): QueueItem[] {
  const items: QueueItem[] = []

  // Programs items
  if (programsData?.items) {
    for (const it of programsData.items) {
      items.push({
        id: it.id,
        model_type: it.model_type,
        model_label: it.model_label,
        title: it.model_label,
        summary: it.summary,
        organisation: it.organisation,
        center_name: it.center_name,
        submitted_by: it.submitted_by ?? '',
        created_at: it.created_at,
        kobo_submission_id: it.kobo_submission_id,
        endpoint: (it as any).endpoint,  // DRF route slug from the API
        kind: 'program',
        urgent: it.model_type === 'gbv_case',
        two_stage: (it as any).two_stage,
        stage: (it as any).stage,
        approval_status: (it as any).approval_status,
        narrative: (it as any).narrative,
      })
    }
  }

  // Legacy submissions (pending only)
  if (submissions) {
    // Baseline interviews live in the dedicated Baseline tab (baselineQueueItems)
    // — never render them here as a generic 'legacy' card. The backend already
    // excludes them from /submissions/; this is defence-in-depth.
    for (const s of submissions.filter(s => s.status === 'pending' && s.form_type !== 'baseline')) {
      const formName = s.form_type_display || s.form_type.replace(/_/g, ' ')
      items.push({
        id: s.id,
        model_type: s.form_type,
        model_label: formName,
        title: `${formName} — ${s.worker_name}`,
        summary: `${s.worker_name} submitted the ${formName} form from ${s.district}`,
        organisation: s.partner ?? '',
        center_name: s.district ?? '',
        submitted_by: s.worker_name ?? '',
        created_at: s.submitted_at,
        form_type_display: formName,
        kind: 'legacy',
        latitude: s.latitude?.toString(),
        longitude: s.longitude?.toString(),
        is_baseline_duplicate: (s as any).is_baseline_duplicate ?? false,
        logic_flags: Array.isArray((s as any).logic_flags) ? (s as any).logic_flags : [],
      })
    }
  }

  return items
}

// Map already-reviewed submissions (approved/rejected) into queue items so
// the "Reviewed" tab can show the audit trail. Newest decision first.
function reviewedQueueItems(submissions: Submission[] | null): QueueItem[] {
  if (!submissions) return []
  return submissions
    .filter(s => s.form_type !== 'baseline')  // baseline audit lives in its own area
    .slice()
    .sort((a, b) => (b.reviewed_at ?? '').localeCompare(a.reviewed_at ?? ''))
    .map(s => {
      const formName = s.form_type_display || s.form_type.replace(/_/g, ' ')
      return {
      id: s.id,
      model_type: s.form_type,
      model_label: formName,
      title: `${formName} — ${s.worker_name}`,
      summary: `${s.status_display} by ${s.reviewed_by?.full_name ?? 'manager'}`,
      organisation: s.partner ?? '',
      center_name: s.district ?? '',
      submitted_by: s.worker_name ?? '',
      created_at: s.submitted_at,
      form_type_display: formName,
      kind: 'legacy' as const,
      latitude: s.latitude?.toString(),
      longitude: s.longitude?.toString(),
      logic_flags: Array.isArray((s as any).logic_flags) ? (s as any).logic_flags : [],
    }
    })
}

interface BaselineAnswerRow {
  section: string
  field: string
  question: string
  value: string
  answer: string
}

// Group readable answers by questionnaire section, in section order.
function groupBaselineAnswers(rows: BaselineAnswerRow[]): [string, BaselineAnswerRow[]][] {
  const m = new Map<string, BaselineAnswerRow[]>()
  for (const r of rows) {
    if (!m.has(r.section)) m.set(r.section, [])
    m.get(r.section)!.push(r)
  }
  return Array.from(m.entries())
}

// Map PENDING D5 baseline verification rows into queue items so the Baseline
// tab reuses the same spine/selection machinery. The verification list already
// carries everything the focus panel needs (headline + answers + dup/gps flags),
// so these items never trigger a detail fetch (skipped in the detail effect by kind).
function baselineQueueItems(rows: any[] | null): QueueItem[] {
  if (!rows) return []
  return rows.map((r) => {
    const popLabel = r.population === 'hijra' ? 'Hijra'
      : r.population === 'fsw' ? 'FSW' : '—'
    const serial = (r.serial || '').trim()
    return {
      id: String(r.submission_id),
      model_type: 'baseline',
      model_label: `Baseline · ${popLabel}`,
      title: `Baseline ${serial || '(no serial)'} · ${popLabel}`,
      summary: [r.district, r.site_code].filter(Boolean).join(' · '),
      organisation: 'CIPRB',
      center_name: r.district || r.site_code || '',
      submitted_by: r.interviewer || '',
      created_at: r.submitted_at,
      kind: 'baseline' as const,
      population: r.population || '',
      serial,
      site_code: r.site_code || '',
      age_display: r.age != null ? String(r.age) : '',
      gps_missing: !!r.gps_missing,
      duplicate_preview: !!r.duplicate_preview,
      is_baseline_duplicate: !!r.duplicate_preview,
      headline: Array.isArray(r.headline) ? r.headline : [],
      answers: Array.isArray(r.answers) ? r.answers : [],
      answer_count: r.answer_count ?? (Array.isArray(r.answers) ? r.answers.length : 0),
      raw_data: r.raw_data || {},
    }
  })
}

// ─── Toast ────────────────────────────────────────────────────────────────────

function Toast({ action, item, onClose }: {
  action: 'approve' | 'reject'
  item: QueueItem
  onClose: () => void
}) {
  const isApprove = action === 'approve'
  return (
    <div style={{
      position: 'fixed', bottom: 28, right: 28, zIndex: 200,
      background: 'var(--ink)', color: 'white',
      borderRadius: 12, padding: '14px 16px',
      display: 'flex', alignItems: 'center', gap: 14,
      boxShadow: '0 16px 40px rgba(20, 32, 43, 0.30)',
      animation: 'rise 320ms var(--ease) backwards',
      minWidth: 340,
    }}>
      <span style={{
        width: 30, height: 30, borderRadius: '50%',
        background: isApprove ? 'rgba(31,154,109,0.20)' : 'rgba(233,69,96,0.20)',
        color: isApprove ? 'var(--emerald)' : 'var(--rose)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {isApprove ? <Check size={14} /> : <X size={14} />}
      </span>
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 500, fontSize: 13.5 }}>{isApprove ? 'Approved' : 'Rejected'} · <span className="mono">{item.id.slice(0, 8)}</span></div>
        <div className="mono" style={{ fontSize: 11, color: 'rgba(255,255,255,0.55)' }}>{item.center_name}</div>
      </div>
      <button onClick={onClose} style={{
        background: 'none', border: 'none', color: 'rgba(255,255,255,0.5)',
        cursor: 'pointer', padding: 4,
      }}>
        <X size={12} />
      </button>
    </div>
  )
}

// ─── UNFPA final sign-off digest ──────────────────────────────────────────────
// One breakdown column (centre / form / date). Pulled out so UnfpaSummaryBanner
// stays small and the column isn't re-declared on every render.
function DigestColumn({ title, rows, oldestKey }: {
  title: string; rows: [string, number][]; oldestKey?: string | null
}) {
  return (
    <div style={{ minWidth: 150 }}>
      <div style={{
        fontSize: 11, fontWeight: 700, letterSpacing: '0.08em',
        textTransform: 'uppercase', color: 'var(--ink-3)', marginBottom: 6,
      }}>{title}</div>
      {rows.slice(0, 5).map(([k, n]) => (
        <div key={k} style={{
          display: 'flex', justifyContent: 'space-between', gap: 14,
          fontSize: 13, padding: '2px 0',
          color: k === oldestKey ? 'var(--rose, #e5484d)' : 'var(--ink-2)',
        }}>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 170 }}>{k}</span>
          <span style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>{n}</span>
        </div>
      ))}
    </div>
  )
}

// At-a-glance triage summary shown ONLY to a UNFPA stage-2 reviewer (gated at
// the mount site). UNFPA performs the final sign-off on Bandhu records a manager
// already approved; this digest shows the shape of that queue — total, and
// breakdowns by centre, form, and waiting date (oldest first) — so they can
// triage before opening every record.
function UnfpaSummaryBanner({ items }: { items: QueueItem[] }) {
  const digest = useMemo(() => {
    const byCentre = new Map<string, number>()
    const byForm = new Map<string, number>()
    const byDate = new Map<string, number>()
    let nilAwaiting = 0
    for (const it of items) {
      const centre = it.center_name || '—'
      byCentre.set(centre, (byCentre.get(centre) ?? 0) + 1)
      const form = it.model_label || it.model_type || '—'
      byForm.set(form, (byForm.get(form) ?? 0) + 1)
      // Group by the Dhaka calendar day, not the raw UTC slice — otherwise
      // submissions just after midnight Dhaka land in the previous day's bucket.
      // (F2 residual.)
      const _d = new Date(it.created_at || '')
      const day = isNaN(_d.getTime()) ? '—' : _d.toLocaleDateString('en-CA', { timeZone: 'Asia/Dhaka' })
      byDate.set(day, (byDate.get(day) ?? 0) + 1)
      if (it.model_type === 'nil_report') nilAwaiting++
    }
    const desc = (m: Map<string, number>) => [...m.entries()].sort((a, b) => b[1] - a[1])
    const dates = [...byDate.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1)) // oldest first
    return {
      total: items.length,
      byCentre: desc(byCentre), byForm: desc(byForm), byDate: dates,
      nilAwaiting, oldest: dates[0]?.[0] ?? null,
    }
  }, [items])

  if (digest.total === 0) return null

  return (
    <div className="card" style={{
      margin: '0 0 18px', padding: '16px 20px', borderRadius: 14,
      border: '1px solid rgba(124,108,240,0.5)',
    }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 12 }}>
        <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: '0.1em', color: 'var(--violet, #7c6cf0)' }}>STAGE 2 / 2 · UNFPA</span>
        <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--ink)' }}>Final sign-off digest</span>
      </div>
      <div style={{ display: 'flex', gap: 30, alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <div style={{ minWidth: 120 }}>
          <div style={{ fontSize: 36, fontWeight: 800, lineHeight: 1, color: 'var(--ink)', fontVariantNumeric: 'tabular-nums' }}>{digest.total}</div>
          <div style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 2 }}>awaiting final approval</div>
          {digest.nilAwaiting > 0 && (
            <div style={{
              marginTop: 8, display: 'inline-block', fontSize: 12, fontWeight: 600,
              color: 'var(--violet, #7c6cf0)', background: 'rgba(124,108,240,0.12)',
              padding: '3px 9px', borderRadius: 999,
            }}>
              {digest.nilAwaiting} nil-report{digest.nilAwaiting > 1 ? 's' : ''} awaiting
            </div>
          )}
        </div>
        <DigestColumn title="By centre" rows={digest.byCentre} />
        <DigestColumn title="By form" rows={digest.byForm} />
        <DigestColumn title="By date (oldest first)" rows={digest.byDate} oldestKey={digest.oldest} />
      </div>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function ManagerApprovals() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [nilOpen, setNilOpen] = useState(false)
  // Nil-report ("No reporting today") is a per-org manager action — a manager
  // or org-lead of any AUTHORING org (Bandhu/PHD/CIPRB) logs one for their OWN
  // org, plus super roles. UNFPA approves Bandhu's in the queue; they don't
  // author them. Each org only ever sees/logs its own centres (org isolation).
  const canLogNil = !!user && (
    (['Bandhu', 'PHD'].includes(user.organisation) && ['manager', 'org_lead'].includes(user.role))
    || ['developer', 'supervisor'].includes(user.role)
  )
  // Baseline no longer needs approval (Rafi 2026-07-09: the D5 baseline
  // auto-approves at ingest — every completed interview counts immediately), so
  // its verification tab is retired: nothing ever pends here now. Forced false so
  // the tab, the /baseline/verification/ fetch and the queue all drop out without
  // unpicking every reference.
  const canSeeBaseline = false
  const canApproveBaseline = false
  // Filter state persisted to localStorage so navigating away and
  // back restores the user's last selected filter (§9 state-preservation).
  const FILTER_KEY = 'approvals.filter'
  type FilterKey = 'all' | 'urgent' | 'phd' | 'bondhu' | 'ciprb' | 'reviewed' | 'baseline'
  const [filter, setFilter] = useState<FilterKey>(() => {
    if (typeof window === 'undefined') return 'all'
    const stored = window.localStorage.getItem(FILTER_KEY)
    if (stored === 'all' || stored === 'urgent' || stored === 'phd' || stored === 'bondhu' || stored === 'ciprb' || stored === 'reviewed') {
      return stored
    }
    return 'all'
  })
  useEffect(() => {
    try { window.localStorage.setItem(FILTER_KEY, filter) } catch {}
  }, [filter])
  const [error, setError] = useState('')
  // Ref to the reviewer-note box so a blocked rejection jumps the manager
  // straight to it (the note is required to reject).
  const noteRef = useRef<HTMLTextAreaElement>(null)
  const [approving, setApproving] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  // Deleting is irreversible, so the button asks a second time rather than
  // acting on the first click. Cleared whenever the selection changes.
  const [deleting, setDeleting] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  // Reviewer note (Animesh: permanent reviewer notes as evidence). Captured
  // here, sent on approve (as `note`) or reject (as `rejection_reason`),
  // then persisted server-side into the immutable review_history trail.
  const [reviewerNote, setReviewerNote] = useState('')
  // Full detail (raw_data clinical variables + review_history) for the
  // selected legacy submission. Lets the manager check actual field values
  // (e.g. age=14) before deciding, per Animesh's variable-checking spec.
  const [detail, setDetail] = useState<SubmissionDetail | null>(null)
  // Toggle for the full raw-submission JSON (every field incl. Kobo metadata).
  const [showRaw, setShowRaw] = useState(false)
  const [toast, setToast] = useState<{ action: 'approve' | 'reject'; item: QueueItem } | null>(null)

  // ── API data ────────────────────────────────────────────────────────────────

  const { data: programsData, loading: programsLoading, refetch: refetchPrograms } =
    usePolling<ProgramPendingResponse>({
      fetcher: () => api.get('/programs/pending-approvals/').then((r) => r.data),
      // 10s so a Kobo submission surfaces quickly once its webhook lands
      // (Kobo's own hook delivery adds a few seconds we can't control).
      interval: 10_000,
    })

  const { data: submissions, loading: legacyLoading, refetch: refetchLegacy } =
    usePolling<Submission[]>({
      fetcher: () =>
        api.get('/submissions/', { params: { status: 'pending' } })
           .then((r) => (Array.isArray(r.data) ? r.data : r.data.results ?? [])),
      interval: 15_000,
    })

  // Reviewed (approved/rejected) submissions — for the "Reviewed" tab so the
  // audit trail (who decided, when, with what note) stays visible after the
  // item leaves the pending queue. Animesh: full visibility, no manipulation.
  // Fetch approved + rejected in parallel (backend filters status by exact
  // match, so there is no single "reviewed" value to query).
  const { data: reviewedSubs } = usePolling<Submission[]>({
    fetcher: () =>
      Promise.all([
        api.get('/submissions/', { params: { status: 'approved' } }),
        api.get('/submissions/', { params: { status: 'rejected' } }),
      ]).then(([a, r]) => {
        const rows = (res: any) => (Array.isArray(res.data) ? res.data : res.data.results ?? [])
        return [...rows(a), ...rows(r)] as Submission[]
      }),
    interval: 60_000,
  })

  // Programs-model decisions (registrations excluded; clinic visits, referrals,
  // GBV, outreach, etc. that a manager/UNFPA actually approved or rejected) so
  // the Reviewed tab shows the real audit trail, not just legacy submissions.
  const { data: reviewedProgramsData } = usePolling<ProgramPendingResponse>({
    fetcher: () =>
      api.get('/programs/pending-approvals/', { params: { status: 'reviewed' } })
         .then((r) => r.data),
    interval: 60_000,
  })

  // D5 baseline pending verification queue — CIPRB/UNFPA/developer only. PHD and
  // Bandhu users skip the fetch entirely (the backend would 403 them anyway), so
  // the tab never appears and the endpoint is never called for them.
  const { data: baselinePending, refetch: refetchBaseline } = usePolling<any[]>({
    fetcher: () => canSeeBaseline
      ? api.get('/baseline/verification/').then((r) =>
          Array.isArray(r.data) ? r.data : (r.data?.results ?? []))
      : Promise.resolve([]),
    interval: 30_000,
  })

  // ── Queue ───────────────────────────────────────────────────────────────────

  const allItems = toQueueItems(programsData ?? null, submissions ?? null)

  // Tab badges count the TRUE pre-cap backlog, not the returned page. The
  // programs queue is capped at 200 rows/model, so counting the returned list
  // left the partner badge stuck ("Bandhu 317 won't drop even after I approve"
  // — approving one just back-filled a hidden row). counts_by_org is the real
  // per-partner total from the server; legacy KoboSubmission rows (near-zero for
  // PHD/Bandhu/CIPRB field data) are added from the returned list.
  const progOrgCounts = programsData?.counts_by_org ?? {}
  const legacyItems = allItems.filter(x => x.kind === 'legacy')
  const orgCount = (orgs: string[]) =>
    orgs.reduce((s, o) => s + (progOrgCounts[o] ?? 0), 0) +
    legacyItems.filter(x => orgs.includes(x.organisation)).length
  const allCount = (programsData?.total ?? 0) + legacyItems.length
  const reviewedItems = [
    ...toQueueItems(reviewedProgramsData ?? null, null),
    ...reviewedQueueItems(reviewedSubs ?? null),
  ].sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''))
  const baselineItems = canSeeBaseline ? baselineQueueItems(baselinePending ?? null) : []

  const _baseList = filter === 'reviewed' ? reviewedItems
    : filter === 'baseline' ? baselineItems
    : allItems
  const filtered = _baseList.filter(it => {
    if (filter === 'urgent') return it.urgent
    if (filter === 'phd') return it.organisation === 'PHD'
    if (filter === 'bondhu') return it.organisation === 'Bandhu' || it.organisation === 'Bondhu'
    if (filter === 'ciprb') return it.organisation === 'CIPRB'
    return true
  })

  const selected = filtered.find(x => x.id === selectedId) ?? filtered[0] ?? null

  // Auto-select first item
  useEffect(() => {
    if (!selectedId && filtered.length > 0) {
      setSelectedId(filtered[0].id)
    }
  }, [filtered, selectedId])

  // When the selection changes, clear the draft note and pull the full
  // submission detail. For legacy KoboSubmission rows that means
  // /submissions/<id>/; for programs records (PHD/Bandhu ClinicVisit,
  // Referral, etc.) it's /programs/<endpoint>/<id>/ — both shapes carry
  // raw_data / raw_payload + review_history, which the readout below
  // groups into Patient / Visit / Screenings / etc.
  // Previously program items were skipped here, so the Manager Approvals
  // page rendered the metadata cards but never the actual form fields.
  const [detailError, setDetailError] = useState(false)
  const [detailRetryKey, setDetailRetryKey] = useState(0)
  useEffect(() => {
    setReviewerNote('')
    setDetail(null)
    // Managers (the stage-1 reviewers) see the COMPLETE uploaded submission —
    // every field as it came from Kobo, nothing collapsed — so they verify the
    // raw data, not a summary. UNFPA (stage-2) keeps the curated view + the
    // plain-language narrative for the final sign-off.
    setShowRaw(user?.organisation !== 'UNFPA')
    setDetailError(false)
    if (!selected) return
    // Baseline items carry their full raw_data on the queue item itself (from the
    // verification list endpoint) — no per-item detail fetch, and no /submissions
    // or /programs URL to hit.
    if (selected.kind === 'baseline') return
    let cancelled = false
    const url = selected.kind === 'legacy'
      ? `/submissions/${selected.id}/`
      : `/programs/${selected.endpoint}/${selected.id}/`
    api.get(url)
      .then((r) => { if (!cancelled) setDetail(r.data as SubmissionDetail) })
      .catch(() => { if (!cancelled) { setDetail(null); setDetailError(true) } })
    return () => { cancelled = true }
  }, [selected?.id, selected?.kind, selected?.endpoint, detailRetryKey])

  // ── Actions ─────────────────────────────────────────────────────────────────

  // Remove a record from SIMPLE for good. Rejecting takes a record out of
  // every figure but keeps it visible; deleting is for data that should never
  // have been submitted. Programme records only: the legacy and baseline
  // queues have no delete endpoint.
  const removeRecord = useCallback(async (item: QueueItem) => {
    const note = reviewerNote.trim()
    if (!note) {
      setError('Say why this record is being deleted. The reason is the only record of what was removed.')
      noteRef.current?.focus()
      noteRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      return
    }
    setError('')
    setDeleting(true)
    try {
      await api.post('/programs/pending-approvals/', {
        id: item.id, model_type: item.model_type, action: 'delete', reason: note,
      })
      refetchPrograms()
      setReviewerNote('')
      setConfirmDelete(false)
      const idx = filtered.findIndex(x => x.id === item.id)
      if (idx < filtered.length - 1) setSelectedId(filtered[idx + 1].id)
      else if (idx > 0) setSelectedId(filtered[idx - 1].id)
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setDeleting(false)
    }
  }, [filtered, refetchPrograms, reviewerNote])

  useEffect(() => { setConfirmDelete(false) }, [selectedId])

  const decide = useCallback(async (item: QueueItem, action: 'approve' | 'reject') => {
    // A rejection must say why — the field worker needs to know what to fix,
    // and the reason is permanently recorded as audit evidence. Applies to
    // BOTH legacy KoboSubmissions AND program items (PHD/Bandhu/CIPRB).
    // Previously this guard only checked legacy and program rejections went
    // through with an empty reason — the field worker got "No reason
    // provided" in their email.
    if (action === 'reject' && !reviewerNote.trim()) {
      setError('Add a reviewer note explaining what to correct before rejecting.')
      noteRef.current?.focus()
      noteRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      return
    }
    setError('')
    const setter = action === 'approve' ? setApproving : setRejecting
    setter(true)
    try {
      const note = reviewerNote.trim()
      if (item.kind === 'baseline') {
        // CIPRB baseline verification. Approve materialises the verified
        // BaselineResponse server-side (post_save signal); reject carries the
        // reason. Backend re-checks CanApproveBaseline (developer / CIPRB
        // manager) — UNFPA/Sayeed get 403 even if they reach this path.
        await api.post(`/baseline/verification/${item.id}/${action}/`,
          action === 'reject' ? { reason: note } : { note })
        refetchBaseline()
      } else if (item.kind === 'program') {
        // Pass the note as the `reason` so the backend stamps
        // obj.rejected_reason and the rejection email carries it.
        // Approves also send the note for the audit trail.
        await api.post('/programs/pending-approvals/', {
          id: item.id,
          model_type: item.model_type,
          action,
          reason: note,
        })
        refetchPrograms()
      } else {
        if (action === 'reject') {
          // Backend requires a non-blank rejection reason — it becomes the
          // worker-facing "what to fix" note and the audit-trail entry.
          await api.post(`/submissions/${item.id}/reject/`, { rejection_reason: note })
        } else {
          await api.post(`/submissions/${item.id}/approve/`, { note })
        }
        refetchLegacy()
      }
      setReviewerNote('')
      setToast({ action, item })
      setTimeout(() => setToast(null), 4500)
      // Select next item
      const idx = filtered.findIndex(x => x.id === item.id)
      if (idx < filtered.length - 1) setSelectedId(filtered[idx + 1].id)
      else if (idx > 0) setSelectedId(filtered[idx - 1].id)
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setter(false)
    }
  }, [filtered, refetchPrograms, refetchLegacy, refetchBaseline, reviewerNote])

  // Manual "Refresh now" — pulls the queue immediately instead of waiting for
  // the next poll tick. Kobo's webhook delivery is async, so a just-submitted
  // form can take a few seconds to arrive; this lets a manager pull on demand.
  const [refreshing, setRefreshing] = useState(false)
  const refreshNow = useCallback(async () => {
    setRefreshing(true)
    try { await Promise.all([refetchPrograms(), refetchLegacy()]) }
    finally { setRefreshing(false) }
  }, [refetchPrograms, refetchLegacy])

  // ── Keyboard navigation ─────────────────────────────────────────────────────

  // Keyboard shortcuts removed — click-only interactions only. See the
  // comment block above for the rationale.

  const loading = programsLoading && legacyLoading && !programsData && !submissions

  if (loading) return <PageLoader />

  const dateStr = new Date().toLocaleString('en-US', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Dhaka' })

  return (
    <>
      {/* ═══════════════════════════════════════════════════════════════
           HERO
           ═══════════════════════════════════════════════════════════════ */}
      <section className="hero" style={{ paddingBottom: 28 }}>
        <div className="hero-eyebrow anim-rise">
          <span className="live-dot" />
          <span>{t('approvals.eyebrowConsole')}</span>
          <span className="sep">/</span>
          <span>{t('approvals.eyebrowQueueItems', { count: allItems.length })}</span>
          <span className="sep">/</span>
          <span>{dateStr} GMT+6</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 32 }} className="anim-rise d1">
          <div>
            <h1 className="hero-headline" style={{ fontSize: 'clamp(40px, 6vw, 76px)', marginBottom: 6 }}>
              <span className="figure"><CountUp value={allItems.length} /></span>{' '}
              <span>{t('approvals.headlineSuffix')}</span>
            </h1>
            <div style={{
              fontFamily: 'var(--display)', fontStyle: 'italic',
              fontSize: 'clamp(22px, 2.6vw, 34px)',
              lineHeight: 1.1, color: 'var(--ink-2)',
              letterSpacing: '-0.012em', marginBottom: 16,
            }}>{t('approvals.headlineSub')}</div>
            {canLogNil && (
              <button className="btn ghost" onClick={() => setNilOpen(true)}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 13 }}>
                <Plus size={15} /> Log “no reporting today”
              </button>
            )}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, auto)', gap: 24, flexShrink: 0 }}>
            <Stat label={t('approvals.statQueue')}    value={allItems.length}                 sub={t('approvals.statQueueSub',    { count: filtered.length })} />
            <Stat label={t('approvals.statPrograms')} value={programsData?.total ?? 0}        sub={t('approvals.statProgramsSub')} />
          </div>
        </div>
      </section>

      {/* UNFPA final-sign-off digest — only for a genuine stage-2 UNFPA reviewer
          (org = UNFPA AND every queued program item is at the UNFPA gate). Hidden
          for Bandhu stage-1 managers, single-stage PHD/CIPRB, and super/developer
          (whose merged lane carries mixed stages, so .every() is false). */}
      {user?.organisation === 'UNFPA'
        && (programsData?.items?.length ?? 0) > 0
        && programsData!.items.every((it: any) => it.stage === 'unfpa') && (
          <UnfpaSummaryBanner items={allItems.filter((i) => i.kind === 'program')} />
        )}

      <NilReportModal open={nilOpen} onClose={() => setNilOpen(false)} onSaved={refetchPrograms} />

      {/* ═══════════════════════════════════════════════════════════════
           ERROR BAR
           ═══════════════════════════════════════════════════════════════ */}
      {error && (
        <div className="card" style={{
          background: 'rgba(233,69,96,0.08)', borderColor: 'rgba(233,69,96,0.25)',
          padding: '12px 18px', marginBottom: 18,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          fontSize: 13, color: 'var(--rose)',
        }}>
          {error}
          <button onClick={() => setError('')} style={{
            background: 'none', border: 'none', color: 'var(--rose)',
            cursor: 'pointer', textDecoration: 'underline', fontSize: 12,
          }}>{t('approvals.dismissError')}</button>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════
           QUEUE + FOCUS PANEL
           ═══════════════════════════════════════════════════════════════ */}
      <section className="section" style={{ marginBottom: 80 }}>
        <div className="appr-layout">

          {/* ── QUEUE SPINE ────────────────────────────────────────── */}
          <div className="card flush appr-spine">
            <div className="card-head" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 10, paddingBottom: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div className="card-title" style={{ fontSize: 14, fontWeight: 600 }}>{t('approvals.queueHeading')}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span className="mono mute" style={{ fontSize: 11 }}>{t('approvals.queueCount', { visible: filtered.length, total: allItems.length })}</span>
                  {programsData?.truncated && filter !== 'baseline' && filter !== 'reviewed' && (
                    <span title="More items are pending than are shown — the queue is capped per form type." style={{ fontSize: 11, color: 'var(--amber, #b56a00)', fontWeight: 600 }}>
                      · showing {programsData.returned ?? allItems.length} of {programsData.total}
                    </span>
                  )}
                  <button
                    onClick={refreshNow}
                    disabled={refreshing}
                    title="Refresh now — pull just-submitted forms without waiting for the auto-refresh"
                    aria-label="Refresh queue now"
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: 5,
                      background: 'none', border: '1px solid var(--hair)', borderRadius: 8,
                      padding: '3px 8px', fontSize: 11, color: 'var(--ink-2)',
                      cursor: refreshing ? 'default' : 'pointer', opacity: refreshing ? 0.6 : 1,
                    }}
                  >
                    <RefreshCw size={12} className={refreshing ? 'animate-spin' : undefined} />
                    {refreshing ? 'Refreshing…' : 'Refresh'}
                  </button>
                </div>
              </div>
              <div className="pills">
                {([
                  { key: 'all'    as const, label: t('approvals.filterAll'),    count: allCount },
                  { key: 'urgent' as const, label: t('approvals.filterUrgent'), count: allItems.filter(x => x.urgent).length },
                  { key: 'phd'    as const, label: t('approvals.filterPHD'),    count: orgCount(['PHD']) },
                  { key: 'bondhu' as const, label: t('approvals.filterBondhu'), count: orgCount(['Bandhu', 'Bondhu']) },
                  { key: 'ciprb'  as const, label: 'CIPRB', count: orgCount(['CIPRB']) },
                  ...(canSeeBaseline ? [{ key: 'baseline' as const, label: 'Baseline', count: baselineItems.length }] : []),
                  { key: 'reviewed' as const, label: 'Reviewed', count: reviewedItems.length },
                ]).map(f => (
                  <button
                    key={f.key}
                    className={`pill ${filter === f.key ? 'on' : ''}`}
                    onClick={() => setFilter(f.key)}
                  >
                    {f.label}
                    {f.count > 0 && <span className="count">{f.count}</span>}
                  </button>
                ))}
              </div>
            </div>

            <div style={{
              padding: '8px 8px 12px',
              maxHeight: 'calc(100vh - 220px)',
              overflowY: 'auto',
            }} className="scroll-thin">
              {filtered.length === 0 && (
                <div style={{ padding: 28, textAlign: 'center', color: 'var(--muted)' }}>
                  <div style={{
                    width: 36, height: 36, margin: '0 auto 6px', borderRadius: '50%',
                    background: 'rgba(31,154,109,0.10)', color: 'var(--emerald)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <Check size={18} />
                  </div>
                  {t('approvals.queueClear')}
                </div>
              )}
              {filtered.map((it, i) => (
                <button
                  key={`${it.kind}-${it.id}`}
                  className={`appr-spine-item ${selected?.id === it.id ? 'active' : ''}`}
                  onClick={() => setSelectedId(it.id)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    width: '100%', textAlign: 'left',
                    padding: '10px 12px', borderRadius: 10,
                    border: 'none', cursor: 'pointer',
                    background: selected?.id === it.id ? 'var(--unfpa)' : 'transparent',
                    color: selected?.id === it.id ? '#fff' : 'var(--ink)',
                    transition: 'background 150ms, color 150ms',
                    marginBottom: 2,
                  }}
                >
                  <span style={{
                    fontFamily: 'var(--mono)', fontSize: 10,
                    color: selected?.id === it.id ? 'rgba(255,255,255,0.6)' : 'var(--muted)',
                    flexShrink: 0,
                  }}>
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontSize: 13, fontWeight: 500,
                      whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                    }}>{it.title}</div>
                    <div style={{
                      fontSize: 11,
                      color: selected?.id === it.id ? 'rgba(255,255,255,0.6)' : 'var(--muted)',
                      whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                    }}>
                      {it.center_name} · {formatDateTime(it.created_at).split(',')[0]}
                    </div>
                  </div>
                  {it.logic_flags && it.logic_flags.length > 0 && (
                    <span
                      title={it.logic_flags
                        .map(tag => t(`approvals.logicFlag.${tag}`, { defaultValue: tag }))
                        .join(' · ')}
                      style={{
                        display: 'inline-flex', alignItems: 'center', gap: 3,
                        height: 18, padding: '0 6px', fontSize: 9.5,
                        borderRadius: 999, flexShrink: 0,
                        background: selected?.id === it.id
                          ? 'rgba(255,255,255,0.16)'
                          : 'rgba(233,151,10,0.14)',
                        color: selected?.id === it.id ? '#fff' : 'var(--amber)',
                        border: '1px solid rgba(233,151,10,0.35)',
                        fontFamily: 'var(--mono)', letterSpacing: '0.02em',
                      }}
                    >
                      <AlertTriangle size={9} strokeWidth={2.5} />
                      {t('approvals.logicFlag.badge', { count: it.logic_flags.length, defaultValue: '{{count}} review' })}
                    </span>
                  )}
                  {it.urgent && (
                    <span className="tag coral" style={{ height: 18, padding: '0 6px', fontSize: 9.5, flexShrink: 0 }}>!</span>
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* ── FOCUS PANEL ────────────────────────────────────────── */}
          {selected && selected.kind === 'baseline' ? (
            <div key={selected.id} style={{ animation: 'rise 500ms var(--ease) backwards' }}>
              <div className="card shimmer">
                {/* Header */}
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, marginBottom: 18 }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12, flexWrap: 'wrap' }}>
                      <span className="mono" style={{ fontSize: 11, color: 'var(--muted)', letterSpacing: '0.04em' }}>
                        {selected.id.slice(0, 8)}
                      </span>
                      <span className="tag violet">CIPRB</span>
                      <span className="tag">{selected.population === 'hijra' ? 'Hijra / Gender-diverse' : selected.population === 'fsw' ? 'Female Sex Worker' : 'Baseline'}</span>
                      {selected.duplicate_preview && <span className="tag coral">Possible duplicate</span>}
                      {selected.gps_missing && <span className="tag amber">No GPS</span>}
                    </div>
                    <h2 style={{
                      fontFamily: 'var(--display)', fontStyle: 'italic', fontWeight: 400,
                      fontSize: 38, lineHeight: 1.05, letterSpacing: '-0.02em',
                      margin: 0, color: 'var(--ink)',
                    }}>
                      Baseline interview {selected.serial || '(no serial)'}
                    </h2>
                  </div>
                </div>

                {/* Key facts */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12, marginBottom: 18 }}>
                  {[
                    ['Population', selected.population === 'hijra' ? 'Hijra' : selected.population === 'fsw' ? 'FSW' : '—'],
                    ['Serial', selected.serial || '—'],
                    ['District', selected.center_name || '—'],
                    ['Site code', selected.site_code || '—'],
                    ['Age', selected.age_display || '—'],
                    ['Interviewer', selected.submitted_by || '—'],
                    ['Submitted', selected.created_at ? formatDateTime(selected.created_at) : '—'],
                  ].map(([k, v]) => (
                    <div key={k} style={{ padding: '10px 12px', borderRadius: 10, background: 'var(--surface-2, rgba(0,0,0,0.02))', border: '1px solid var(--hair)' }}>
                      <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--muted)' }}>{k}</div>
                      <div style={{ fontSize: 14, color: 'var(--ink)', marginTop: 3, wordBreak: 'break-word' }}>{v}</div>
                    </div>
                  ))}
                </div>

                {selected.duplicate_preview && (
                  <div style={{ marginBottom: 14, padding: '12px 16px', borderRadius: 12, background: 'rgba(224,90,27,0.07)', border: '1px solid rgba(224,90,27,0.3)', fontSize: 13, color: 'var(--ink)' }}>
                    Another baseline submission with the same serial and population is already on file. Confirm this is not a re-submission before approving.
                  </div>
                )}

                {/* Respondent profile — readable at-a-glance facts (real labels, not codes) */}
                {selected.headline && selected.headline.length > 0 && (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 10, marginBottom: 16 }}>
                    {selected.headline.map((h) => (
                      <div key={h.label} style={{ background: 'var(--surface-2, rgba(0,0,0,0.02))', border: '1px solid var(--hair)', borderRadius: 10, padding: '8px 11px', minWidth: 0 }}>
                        <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase', color: 'var(--muted)' }}>{h.label}</div>
                        <div style={{ fontSize: 13, color: 'var(--ink)', marginTop: 2, wordBreak: 'break-word' }}>{h.value || '—'}</div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Full interview — readable question/answer, grouped by section */}
                <button
                  onClick={() => setShowRaw(v => !v)}
                  style={{ background: 'none', border: '1px solid var(--hair)', borderRadius: 8, padding: '4px 10px', fontSize: 11, color: 'var(--ink-2)', cursor: 'pointer', marginBottom: 10 }}
                >
                  {showRaw ? 'Hide' : 'Review'} full interview ({selected.answer_count ?? (selected.answers?.length ?? 0)})
                </button>
                {showRaw && (
                  <div className="scroll-thin" style={{ maxHeight: 360, overflow: 'auto', border: '1px solid var(--hair)', borderRadius: 10, padding: 12, marginBottom: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
                    {(selected.answers && selected.answers.length > 0) ? (
                      groupBaselineAnswers(selected.answers).map(([section, rows]) => (
                        <div key={section}>
                          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase', color: 'var(--unfpa, #F96000)', marginBottom: 8 }}>{section}</div>
                          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '8px 18px' }}>
                            {rows.map((r) => (
                              <div key={r.field} style={{ fontSize: 12.5, minWidth: 0 }}>
                                <div style={{ color: 'var(--muted)', lineHeight: 1.3 }}>{r.question}</div>
                                <div style={{ color: 'var(--ink)', fontWeight: 600, wordBreak: 'break-word', marginTop: 1 }}>{r.answer || r.value}</div>
                              </div>
                            ))}
                          </div>
                        </div>
                      ))
                    ) : (
                      <div style={{ fontSize: 12.5, color: 'var(--muted)' }}>No answers recorded for this interview.</div>
                    )}
                  </div>
                )}

                {/* Decision */}
                {canApproveBaseline ? (
                  <>
                    <textarea
                      ref={noteRef}
                      value={reviewerNote}
                      onChange={(e) => setReviewerNote(e.target.value)}
                      placeholder="Reviewer note (required to reject — tells the field team what to correct)"
                      rows={2}
                      style={{ width: '100%', borderRadius: 10, border: '1px solid var(--hair)', padding: '10px 12px', fontSize: 13, resize: 'vertical', marginBottom: 12 }}
                    />
                    {error && <div style={{ color: 'var(--coral, #e05a1b)', fontSize: 12, marginBottom: 10 }}>{error}</div>}
                    <div style={{ display: 'flex', gap: 10 }}>
                      <button
                        className="btn btn-primary"
                        disabled={approving || rejecting}
                        onClick={() => decide(selected, 'approve')}
                      >
                        {approving ? 'Approving…' : 'Approve interview'}
                      </button>
                      <button
                        className="btn"
                        disabled={approving || rejecting}
                        onClick={() => decide(selected, 'reject')}
                        style={{ borderColor: 'rgba(224,90,27,0.4)', color: 'var(--coral, #e05a1b)' }}
                      >
                        {rejecting ? 'Rejecting…' : 'Reject'}
                      </button>
                    </div>
                  </>
                ) : (
                  <div style={{ padding: '12px 16px', borderRadius: 12, background: 'var(--surface-2, rgba(0,0,0,0.03))', border: '1px solid var(--hair)', fontSize: 13, color: 'var(--muted)' }}>
                    View only — baseline verification is done by the CIPRB manager. You can review every interview here but cannot approve or reject.
                  </div>
                )}
              </div>
            </div>
          ) : selected ? (
            <div key={selected.id} style={{ animation: 'rise 500ms var(--ease) backwards' }}>
              <div className={`card ${selected.model_type === 'gbv_case' ? 'shimmer-coral' : 'shimmer'}`}>
                {/* Header */}
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, marginBottom: 18 }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                      <span className="mono" style={{ fontSize: 11, color: 'var(--muted)', letterSpacing: '0.04em' }}>
                        {selected.id.slice(0, 8)}
                      </span>
                      <span className={`tag ${selected.organisation === 'PHD' ? 'blue' : 'violet'}`}>
                        {selected.organisation}
                      </span>
                      <span className="tag">{selected.model_label}</span>
                      {selected.urgent && <span className="tag coral">{t('approvals.tagUrgent')}</span>}
                    </div>
                    <h2 style={{
                      fontFamily: 'var(--display)', fontStyle: 'italic', fontWeight: 400,
                      fontSize: 38, lineHeight: 1.05, letterSpacing: '-0.02em',
                      margin: 0, color: 'var(--ink)',
                    }}>
                      {selected.title}
                    </h2>

                    {/* PATIENT IDENTITY BANNER — reads the SERVER-HYDRATED
                        client summary nested on the submission via
                        ClientSummarySerializer (client_id, name, mother_name,
                        birth_year, current_address, current_status,
                        target_group_label). Manager Approvals only ever sees
                        submissions whose Client FK is resolved server-side —
                        unregistered submissions never reach this queue, so we
                        render nothing when patient is absent (Stock / Event
                        / IEC etc.). No raw-payload sniffing. */}
                    {(() => {
                      const p = (detail as any)?.patient;
                      if (!p || (!p.name && !p.client_id)) return null;
                      const currentYear = new Date().getFullYear();
                      // Guard the year-subtraction: birth_year may arrive as a
                      // full date string or junk, which would render "Age NaN"
                      // or an absurd value on a PII card. Only show a plausible
                      // human age. (Fault F7.)
                      const _by = Number(String(p.birth_year ?? '').slice(0, 4));
                      const _age = currentYear - _by;
                      const age = Number.isFinite(_age) && _age >= 0 && _age <= 120 ? _age : null;
                      const isActive = p.current_status === '1';
                      // Webhook creates a STUB_* placeholder Client when the
                      // worker types an ID that isn't in the master list — FK
                      // satisfied, but name/mother/age are all empty. Surface
                      // that as an amber warning so the manager knows to ask
                      // for a proper registration before approving.
                      const isStub = !p.name || /^STUB[_-]/i.test(String(p.client_id || ''));
                      if (isStub) {
                        const _rd = (detail as any)?.raw_data ?? (detail as any)?.raw_payload ?? {};
                        const typedId = String(_rd.client_id || _rd.id_no || _rd.ref_id_no || _rd.clinic_id_no || _rd.htc_client_id || p.client_id || '').trim();
                        return (
                          <div style={{
                            marginTop: 18,
                            padding: '20px 24px',
                            borderRadius: 14,
                            background: 'linear-gradient(180deg, rgba(233,151,10,0.08) 0%, rgba(233,151,10,0.02) 100%)',
                            border: '1px solid rgba(233,151,10,0.32)',
                            maxWidth: 760,
                          }}>
                            <div style={{
                              fontSize: 22, fontWeight: 700, color: 'var(--amber)',
                              marginBottom: 8, letterSpacing: '-0.01em',
                            }}>
                              ⚠ Patient not in Master List
                            </div>
                            <div style={{ fontSize: 15.5, color: 'var(--ink)', lineHeight: 1.5 }}>
                              The field worker typed ID{' '}
                              <span className="mono" style={{
                                background: 'var(--surface)', padding: '3px 11px',
                                borderRadius: 6, fontWeight: 600,
                                border: '1px solid var(--hair)', fontSize: 15,
                              }}>{typedId}</span>{' '}
                              but no client with this ID exists in the registry.
                            </div>
                            <div style={{ fontSize: 14, color: 'var(--ink-3)', marginTop: 10, lineHeight: 1.5 }}>
                              Ask the field team to register this client through{' '}
                              <b style={{ color: 'var(--ink-2)' }}>{
                                selected.organisation === 'PHD'
                                  ? 'PHD 1 — FSW Registration'
                                  : (selected.organisation === 'Bandhu' || selected.organisation === 'Bondhu')
                                    ? 'Bandhu 0 — Mother List'
                                    : 'the registration form'
                              }</b>{' '}
                              before approving this service record.
                            </div>
                          </div>
                        );
                      }
                      return (
                        <div style={{
                          marginTop: 18,
                          padding: '20px 24px',
                          borderRadius: 14,
                          background: 'linear-gradient(180deg, rgba(249,96,0,0.06) 0%, rgba(249,96,0,0.02) 100%)',
                          border: '1px solid rgba(249,96,0,0.22)',
                          maxWidth: 760,
                        }}>
                          <div style={{
                            display: 'flex', alignItems: 'baseline', flexWrap: 'wrap',
                            gap: 16, marginBottom: 10,
                          }}>
                            <div style={{
                              fontSize: 28, fontWeight: 700,
                              color: 'var(--ink)', lineHeight: 1.1,
                              letterSpacing: '-0.01em',
                            }}>
                              {p.name || 'Unnamed patient'}
                            </div>
                            {p.status_label && (
                              <span className={`tag ${isActive ? 'emerald' : 'amber'}`}
                                style={{ fontSize: 12 }}>
                                {p.status_label}
                              </span>
                            )}
                            {p.target_group_label && (
                              <span className="tag" style={{ fontSize: 12 }}>
                                {p.target_group_label}
                              </span>
                            )}
                          </div>
                          <div style={{
                            fontSize: 15.5, color: 'var(--ink-2)',
                            display: 'flex', flexWrap: 'wrap', gap: '6px 16px',
                            alignItems: 'center',
                          }}>
                            {p.client_id && (
                              <span className="mono" style={{
                                background: 'var(--surface)', padding: '3px 11px',
                                borderRadius: 6, fontWeight: 600,
                                border: '1px solid var(--hair)',
                                fontSize: 15,
                              }}>{p.client_id}</span>
                            )}
                            {age !== null && (
                              <span>Age <b>{age}</b>{p.birth_year ? ` (born ${p.birth_year})` : ''}</span>
                            )}
                            {p.current_address && <span style={{ color: 'var(--ink-3)' }}>{p.current_address}</span>}
                          </div>
                          {p.mother_name && (
                            <div style={{ fontSize: 14, color: 'var(--ink-3)', marginTop: 8 }}>
                              Mother: <b style={{ color: 'var(--ink-2)' }}>{p.mother_name}</b>
                            </div>
                          )}
                        </div>
                      );
                    })()}

                    <p className="hero-lede" style={{ marginTop: 14, maxWidth: 720 }}>
                      {selected.summary}
                    </p>
                    {/* Two-stage approval banner (Bandhu): tells the reviewer
                        which gate this is and what approving does. */}
                    {selected.two_stage && (
                      <div style={{
                        marginTop: 14, display: 'flex', alignItems: 'center', gap: 10,
                        padding: '10px 14px', borderRadius: 10,
                        background: 'var(--violet)14', border: '1px solid var(--violet)',
                        maxWidth: 720,
                      }}>
                        <span style={{
                          fontSize: 11, fontWeight: 700, color: '#fff', background: 'var(--violet)',
                          borderRadius: 999, padding: '2px 9px', whiteSpace: 'nowrap',
                        }}>
                          {selected.stage === 'unfpa' ? 'STAGE 2 / 2' : 'STAGE 1 / 2'}
                        </span>
                        <span style={{ fontSize: 13, color: 'var(--ink-2)' }}>
                          {selected.stage === 'unfpa'
                            ? 'UNFPA final approval — approving releases this to the dashboard.'
                            : 'Bandhu manager review — after you approve, it goes to UNFPA for final sign-off.'}
                        </span>
                      </div>
                    )}
                    {/* Which Kobo form is being approved — the manager must
                        see the form name + its KoboToolbox id, read-only. */}
                    {selected.kind === 'legacy' && (
                      <div style={{
                        marginTop: 14, display: 'inline-flex', alignItems: 'center', gap: 10,
                        padding: '8px 14px', borderRadius: 10,
                        background: 'var(--surface-2)', border: '1px solid var(--hair)',
                      }}>
                        <FileText size={14} style={{ color: 'var(--unfpa)' }} />
                        <span style={{ fontSize: 13, color: 'var(--ink)', fontWeight: 600 }}>
                          {selected.form_type_display || selected.model_label}
                        </span>
                        {Boolean(detail?.raw_data?._xform_id_string) && (
                          <span className="mono mute" style={{ fontSize: 11 }}>
                            · {String(detail!.raw_data._xform_id_string)}
                          </span>
                        )}
                      </div>
                    )}
                    {/* Animesh's baseline duplication warning — yellow card
                        when an earlier baseline from same place+day already
                        exists. Manager can still approve, but is forced to
                        notice the collision first. */}
                    {/* MPDSR QA-gate logic-error flags (Animesh deck slide 9).
                        Amber advisory listing implausible field values so the
                        manager can scrutinise + reject with a note. Does NOT
                        gate the approve/reject buttons. */}
                    {selected.logic_flags && selected.logic_flags.length > 0 && (
                      <div style={{
                        marginTop: 14,
                        padding: '10px 14px',
                        borderRadius: 8,
                        background: 'rgba(233,151,10,0.10)',
                        border: '1px solid rgba(233,151,10,0.35)',
                        color: '#7A4400',
                        fontSize: 13,
                        display: 'flex', gap: 10, alignItems: 'flex-start',
                      }}>
                        <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 1, color: 'var(--amber)' }} />
                        <div>
                          <b>{t('approvals.logicFlag.title', { count: selected.logic_flags.length, defaultValue: '{{count}} review' })}</b>
                          {' — '}
                          {t('approvals.logicFlag.body', {
                            defaultValue: 'Automated checks flagged implausible values. Verify before approving.',
                          })}
                          <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                            {selected.logic_flags.map(tag => (
                              <li key={tag} style={{ marginTop: 2 }}>
                                {t(`approvals.logicFlag.${tag}`, { defaultValue: tag })}
                              </li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    )}
                    {selected.is_baseline_duplicate && (
                      <div style={{
                        marginTop: 14,
                        padding: '10px 14px',
                        borderRadius: 8,
                        background: 'rgba(204,106,0,0.10)',
                        border: '1px solid rgba(204,106,0,0.35)',
                        color: '#7A4400',
                        fontSize: 13,
                        display: 'flex', gap: 10, alignItems: 'flex-start',
                      }}>
                        <span style={{ fontSize: 16, lineHeight: 1 }}>⚠</span>
                        <span>
                          <b>{t('approvals.duplicateWarning', { defaultValue: 'Possible duplicate' })}</b>
                          {' — '}
                          {t('approvals.duplicateBody', {
                            defaultValue: 'An earlier baseline survey from the same location and day is already on file. Verify before approving.',
                          })}
                        </span>
                      </div>
                    )}
                  </div>
                  <div style={{ textAlign: 'right', flexShrink: 0 }}>
                    <div className="kicker"><span className="dot" />{t('approvals.submittedAt')}</div>
                    <div className="mono" style={{ fontSize: 13, marginTop: 4 }}>
                      {formatDateTime(selected.created_at)}
                    </div>
                  </div>
                </div>

                {/* Submitter + centre + map preview. Location card only renders
                    when GPS was actually captured — an empty grey block helps
                    no one. Grid collapses to 2-col in that case. */}
                {(() => {
                  const hasGps = Number.isFinite(parseFloat(String(selected.latitude ?? ''))) && Number.isFinite(parseFloat(String(selected.longitude ?? '')));
                  const _rd = (detail as any)?.raw_data ?? (detail as any)?.raw_payload ?? {};
                  const submitterName =
                    selected.submitted_by
                    || _rd?._pull_name
                    || _rd?.submitted_by_kobo_user
                    || _rd?.staff_name
                    || _rd?.fw_name
                    || _rd?.name
                    || t('approvals.unknownUser');
                  return (
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: hasGps ? '1fr 1fr 1.2fr' : '1fr 1.4fr',
                  gap: 18,
                  padding: '18px 0',
                  borderTop: '1px solid var(--hair)',
                  borderBottom: '1px solid var(--hair)',
                }}>
                  <div>
                    <div className="kicker" style={{ marginBottom: 8 }}><span className="dot" />{t('approvals.submittedBy')}</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div className="stream-avatar blue" style={{ width: 40, height: 40, fontSize: 13 }}>
                        {String(submitterName).split(' ').map(p => p[0]).join('').slice(0, 2).toUpperCase()}
                      </div>
                      <div>
                        <div style={{ fontSize: 14, fontWeight: 500 }}>{submitterName}</div>
                        <div className="mute" style={{ fontSize: 11.5 }}>{selected.organisation}</div>
                      </div>
                    </div>
                  </div>
                  <div>
                    <div className="kicker" style={{ marginBottom: 8 }}><span className="dot" />CENTRE</div>
                    <div style={{ fontSize: 14, fontWeight: 500 }}>{selected.center_name}</div>
                    {(() => {
                      // Only render coordinates that actually parse to finite
                      // numbers — a non-empty but non-numeric lat/lng string
                      // would otherwise show "NaN, NaN". (Fault F8.)
                      const lat = parseFloat(String(selected.latitude ?? ''));
                      const lng = parseFloat(String(selected.longitude ?? ''));
                      if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
                      return (
                        <div className="mute" style={{ fontSize: 11.5 }}>
                          GPS: <span className="mono">{lat.toFixed(4)}, {lng.toFixed(4)}</span>
                        </div>
                      );
                    })()}
                  </div>
                  {hasGps && (
                  <div>
                    <div className="kicker" style={{ marginBottom: 8 }}><span className="dot" />LOCATION</div>
                    <MiniLocationMap />
                  </div>
                  )}
                </div>
                  );
                })()}

                {/* One-line gate strip — replaces the old 2-column 'CHECKS AT
                    INGEST' + 'FIELD-LEVEL DIFF' panels. Both were over-styled
                    and the diff was redundant with the SUBMITTED BY / CENTRE
                    cards above. A manager just needs to know "did the ingest
                    rules pass" — yes/no per gate, one line. */}
                <div style={{
                  display: 'flex', flexWrap: 'wrap', gap: 18,
                  padding: '14px 0',
                  borderBottom: '1px solid var(--hair)',
                  fontSize: 13,
                }}>
                  {([
                    ['Form recognised', true],
                    ['Unique', !!selected.kobo_submission_id],
                    ['GPS captured', Number.isFinite(parseFloat(String(selected.latitude ?? ''))) && Number.isFinite(parseFloat(String(selected.longitude ?? '')))],
                    [`Partner: ${selected.organisation || '—'}`, !!selected.organisation],
                  ] as [string, boolean][]).map(([label, ok]) => (
                    <span key={label} style={{
                      display: 'inline-flex', alignItems: 'center', gap: 6,
                      color: ok ? 'var(--emerald)' : 'var(--amber)',
                    }}>
                      {ok ? <Check size={14} /> : <AlertTriangle size={14} />}
                      <span style={{ color: 'var(--ink)' }}>{label}</span>
                    </span>
                  ))}
                </div>

                {/* Plain-language narrative of the activity — shown ONLY to the
                    UNFPA stage-2 reviewer (not Bandhu managers), so the approver
                    reads what happened before signing off, on top of the field
                    table below. */}
                {user?.organisation === 'UNFPA' && selected?.narrative && (
                  <div style={{
                    padding: '15px 18px', margin: '6px 0',
                    borderRadius: 12, border: '1px solid rgba(124,108,240,0.4)',
                    background: 'rgba(124,108,240,0.06)',
                  }}>
                    <div style={{
                      fontSize: 11, fontWeight: 700, letterSpacing: '0.08em',
                      textTransform: 'uppercase', color: 'var(--violet, #7c6cf0)',
                      marginBottom: 6,
                    }}>In plain language</div>
                    <p style={{
                      margin: 0, fontSize: 14.5, lineHeight: 1.6,
                      color: 'var(--ink)', textWrap: 'pretty' as any,
                    }}>{selected.narrative}</p>
                  </div>
                )}

                {/* The clinical readout — single column, semantically grouped
                    so the manager scans the right fields in the right order
                    (Patient → Visit → Screenings → Diagnoses → Treatment →
                    Referrals → Follow-up). No 2-column compression, no
                    'View full record' toggle, no system-field clutter. */}
                {(() => {
                  const _rd = (detail as any)?.raw_data ?? (detail as any)?.raw_payload;
                  if (detailError) return (
                    <div style={{
                      padding: '20px 0', display: 'flex', alignItems: 'center', gap: 12,
                      color: 'var(--coral)', fontSize: 13,
                    }}>
                      <AlertTriangle size={16} />
                      <span>Failed to load submission details.</span>
                      <button
                        onClick={() => setDetailRetryKey(k => k + 1)}
                        style={{
                          marginLeft: 'auto', fontSize: 12,
                          padding: '4px 12px', borderRadius: 8,
                          border: '1px solid var(--hair)',
                          background: 'var(--surface)', cursor: 'pointer',
                          color: 'var(--ink)',
                        }}
                      >
                        Retry
                      </button>
                    </div>
                  );
                  if (!detail) return (
                    <div style={{ padding: '20px 0', color: 'var(--muted)', fontSize: 13 }}>
                      Loading submitted values…
                    </div>
                  );
                  if (!_rd || Object.keys(_rd).length === 0) return (
                    <div style={{ padding: '20px 0', color: 'var(--muted)', fontSize: 13 }}>
                      This submission carries no payload data — only the metadata above.
                    </div>
                  );
                  // When the patient identity banner is rendering above, hide
                  // the same fields from the readout — name, ID, mother,
                  // birth year, address are already prominent up top, no
                  // point repeating them in the field-by-field grid.
                  const hasPatientBanner = !!(detail as any)?.patient;
                  const DUP_KEYS = new Set([
                    'name', '_pull_name',
                    'mother_name', '_pull_mother',
                    'birth_year', '_pull_birth', '_pull_age',
                    'permanent_address', 'current_address', '_pull_address',
                    'client_id',
                    'id_no', 'clinic_id_no', 'htc_client_id', 'ref_id_no',
                    '_pull_status',
                  ]);
                  const _rdForReadout = hasPatientBanner
                    ? Object.fromEntries(Object.entries(_rd).filter(([k]) => !DUP_KEYS.has(k)))
                    : _rd;
                  const groups = groupSubmittedFields(_rdForReadout, selected.organisation);
                  return (
                    <div style={{ padding: '20px 0', borderBottom: '1px solid var(--hair)' }}>
                      <div style={{
                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                        marginBottom: 14,
                      }}>
                        <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--ink)' }}>
                          What was submitted
                        </div>
                        <button
                          onClick={() => setShowRaw(v => !v)}
                          style={{
                            fontSize: 12, color: 'var(--ink-3)',
                            background: 'none', border: 'none', cursor: 'pointer',
                            padding: 0, fontFamily: 'var(--ui)',
                          }}
                        >
                          {showRaw ? 'Hide blanks' : 'Show empty fields too'}
                        </button>
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
                        {groups.map(({ title, rows }) => {
                          const visible = showRaw ? rows : rows.filter(r => !r.isEmpty);
                          if (visible.length === 0) return null;
                          return (
                            <div key={title}>
                              <div style={{
                                fontSize: 12.5, fontWeight: 600,
                                color: 'var(--ink-3)',
                                letterSpacing: '0.10em',
                                textTransform: 'uppercase',
                                marginBottom: 8,
                              }}>{title}</div>
                              {/* Register-style table (rows × columns) so the
                                  reviewer reads the data exactly like the paper
                                  form before approving. */}
                              <table style={{
                                width: '100%', borderCollapse: 'collapse',
                                fontSize: 14.5, border: '1px solid var(--hair)',
                                borderRadius: 8, overflow: 'hidden',
                              }}>
                                <tbody>
                                  {visible.map((r, i) => (
                                    <tr key={i} style={{
                                      borderTop: i === 0 ? 'none' : '1px solid var(--hair)',
                                      background: i % 2 ? 'var(--surface-2)' : 'transparent',
                                    }}>
                                      <th style={{
                                        textAlign: 'left', verticalAlign: 'top',
                                        width: 230, padding: '8px 14px',
                                        color: 'var(--ink-3)', fontWeight: 500,
                                        borderRight: '1px solid var(--hair)',
                                      }}>{r.label}</th>
                                      <td style={{
                                        padding: '8px 14px',
                                        color: r.isEmpty ? 'var(--muted)' : 'var(--ink)',
                                        fontFamily: r.mono ? 'var(--mono)' : 'inherit',
                                        fontVariantNumeric: 'tabular-nums',
                                      }}>{r.display}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })()}

                {/* Review history — immutable audit trail (who, what, when, note). */}
                {detail && detail.review_history && detail.review_history.length > 0 && (
                  <div style={{ padding: '22px 0', borderBottom: '1px solid var(--hair)' }}>
                    <div className="kicker" style={{ marginBottom: 12 }}><span className="dot" />REVIEW HISTORY</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                      {detail.review_history.map((e, i) => (
                        <div key={i} style={{
                          display: 'flex', gap: 10, fontSize: 12.5,
                          padding: '8px 12px', borderRadius: 8,
                          background: 'var(--surface-2)', border: '1px solid var(--hair)',
                        }}>
                          <span style={{
                            color: e.action === 'approved' ? 'var(--emerald)' : 'var(--coral)',
                            fontWeight: 600, textTransform: 'capitalize', minWidth: 64,
                          }}>{e.action}</span>
                          <div style={{ flex: 1 }}>
                            <div style={{ color: 'var(--ink)' }}>{e.reviewer || 'Manager'}</div>
                            {e.note && <div className="mute" style={{ marginTop: 2 }}>"{e.note}"</div>}
                          </div>
                          <span className="mono mute" style={{ fontSize: 11, whiteSpace: 'nowrap' }}>
                            {e.timestamp ? new Date(e.timestamp).toLocaleString('en-US', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Dhaka' }) : ''}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {filter === 'reviewed' ? (
                  /* Already-decided item — show the outcome, no action controls. */
                  <div style={{ paddingTop: 18, fontSize: 13, color: 'var(--muted)' }}>
                    {detail?.reviewed_by
                      ? <>Decided by <strong style={{ color: 'var(--ink)' }}>{detail.reviewed_by.full_name}</strong>
                          {detail.reviewed_at && <> on {new Date(detail.reviewed_at).toLocaleString('en-US', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Dhaka' })}</>}.</>
                      : 'This submission has already been reviewed.'}
                  </div>
                ) : (
                  <>
                    {/* Reviewer note */}
                    <div style={{ padding: '22px 0', borderBottom: '1px solid var(--hair)' }}>
                      <div className="kicker" style={{ marginBottom: 10 }}><span className="dot" />{t('approvals.reviewerNote')}</div>
                      <textarea
                        ref={noteRef}
                        value={reviewerNote}
                        onChange={(e) => { setReviewerNote(e.target.value); if (error) setError('') }}
                        placeholder={t('approvals.reviewerPlaceholder')}
                        style={{
                          width: '100%', minHeight: 64, padding: '10px 12px',
                          border: `1px solid ${error ? 'var(--coral)' : 'var(--hair)'}`, borderRadius: 10,
                          background: 'var(--surface-2)', fontSize: 13, color: 'var(--ink)',
                          resize: 'vertical', fontFamily: 'var(--ui)',
                        }}
                      />
                      <div style={{ fontSize: 11, marginTop: 6, color: error ? 'var(--coral)' : 'var(--muted)' }}>
                        {error
                          ? '⚠ A note is required to delete — type the reason above, then click Delete.'
                          : 'Required to delete. It is the only record of what was removed and why.'}
                      </div>
                    </div>

                    {/* Actions. Two outcomes only: keep it or remove it.
                        Reject was dropped at Bandhu's request (2026-08-26); the
                        backend action still exists, so restoring the button is
                        one block if the send-it-back-to-be-corrected step is
                        ever wanted again. Delete is programme records only,
                        because the legacy and baseline queues have no delete
                        endpoint. */}
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 8, paddingTop: 20, flexWrap: 'wrap' }}>
                      <div style={{ display: 'flex', gap: 8 }}>
                        {selected.kind === 'program' && (
                        <button
                          className="btn danger filled lg"
                          onClick={() => (confirmDelete ? removeRecord(selected) : setConfirmDelete(true))}
                          onBlur={() => setConfirmDelete(false)}
                          disabled={deleting || !reviewerNote.trim()}
                          title={!reviewerNote.trim()
                            ? 'Say why it is being deleted first — the note is the only record of what was removed'
                            : 'Remove this record from SIMPLE for good. The KoboToolbox copy is kept.'}
                          style={{ display: 'flex', alignItems: 'center', gap: 6 }}
                        >
                          {deleting ? <LoadingSpinner size="sm" /> : (
                            <><Trash2 size={14} /> {confirmDelete ? 'Click again to delete' : 'Delete'}</>
                          )}
                        </button>
                        )}
                        <button
                          className="btn success lg"
                          onClick={() => decide(selected, 'approve')}
                          disabled={approving}
                          style={{ display: 'flex', alignItems: 'center', gap: 6 }}
                        >
                          {approving ? <LoadingSpinner size="sm" /> : (
                            <><Check size={14} /> {
                              selected.two_stage
                                ? (selected.stage === 'unfpa' ? 'Final approve (UNFPA)' : 'Approve → send to UNFPA')
                                : t('approvals.btnApprove')
                            }</>
                          )}
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>
          ) : (
            <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--muted)' }}>
              <div style={{ fontSize: 18, color: 'var(--ink)', fontFamily: 'var(--display)', fontStyle: 'italic' }}>
                {t('approvals.queueClearMain')}
              </div>
              <p style={{ marginTop: 6 }}>{t('approvals.queueClearSub')}</p>
            </div>
          )}
        </div>
      </section>

      {/* Toast */}
      {toast && (
        <Toast
          action={toast.action}
          item={toast.item}
          onClose={() => setToast(null)}
        />
      )}
    </>
  )
}
