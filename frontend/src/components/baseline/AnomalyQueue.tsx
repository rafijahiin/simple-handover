/**
 * Data quality & anomalies — three components, per the redesign spec:
 *   A. compact anomaly KPI row (flag counts kept separate from unique-interview
 *      counts on purpose — one record with five problems is five flags),
 *   B. priority anomaly rules (click → filters the queue),
 *   C. fixed-height, paginated review queue with a side drawer.
 *
 * Review decisions POST to /baseline/fsw-anomalies/review/ and live in a
 * separate audit table — raw Kobo responses are never edited here.
 */
import React, { useMemo, useState } from 'react'
import {
  AlertOctagon, AlertTriangle, Info, PencilLine, ShieldCheck, X, Check, Ban,
  Search, ChevronLeft, ChevronRight, MapPinned,
} from 'lucide-react'
import { api, apiErrorMessage } from '@/api/client'

export type Sev = 'critical' | 'high' | 'medium' | 'low'
type ReviewStatus = 'new' | 'confirmed' | 'corrected' | 'false_positive' | 'needs_verification'

export interface Anomaly {
  rule_id: string
  severity: Sev
  category: string
  message: string
  record_id: string | null
  enumerator: string | null
  site: string
  date: string
  population: string
  fields: string[]
  observed: unknown
  expected: unknown
  action: string | null
  review_status: ReviewStatus
  review_note: string
  reviewed_by: string | null
  reviewed_at: string | null
}
export interface AnomalyReport {
  records_scanned: number
  anomaly_count: number
  current_version: Record<string, string | null>
  summary: { by_severity: Record<Sev, number>; top_rules: Record<string, number> }
  kpis: {
    critical: number; high: number; medium: number; low: number
    interviews_affected: number; flags_reviewed: number; flags_total: number
  }
  anomalies: Anomaly[]
}

const SEV_CLS: Record<Sev, string> = {
  critical: 'tag-crit', high: 'tag-high', medium: 'tag-warn', low: 'tag-neutral',
}
const SEV_ICON: Record<Sev, React.ReactNode> = {
  critical: <AlertOctagon size={13} />, high: <AlertTriangle size={13} />,
  medium: <Info size={13} />, low: <Info size={13} />,
}
/* Each label says what the reviewer decided, in their words. 'New' told the
   reader nothing about what was, or was not, done to the record. */
const STATUS_LABEL: Record<ReviewStatus, string> = {
  new: 'Not yet reviewed',
  confirmed: 'Checked — a real error',
  corrected: 'Fixed in KoboToolbox',
  false_positive: 'Checked — the answer is right',
  needs_verification: 'Asked the field team',
}
const STATUS_TONE: Record<ReviewStatus, string> = {
  new: 'var(--muted)', confirmed: 'var(--high)', corrected: 'var(--ok)',
  false_positive: 'var(--muted)', needs_verification: 'var(--warn)',
}
const PAGE_SIZE = 20

/* Action-oriented labels; the technical rule ID appears only in the drawer. */
const RULE_LABEL: Record<string, string> = {
  MUTUALLY_EXCLUSIVE_MULTISELECT: 'Conflicting answers selected',
  SEX_WORK_YEARS_IMPOSSIBLE: 'Work-history duration impossible',
  SEX_WORK_START_AFTER_CURRENT_AGE: 'Work started after current age',
  INTERVIEW_TOO_SHORT: 'Interview under 40 minutes',
  END_BEFORE_START: 'End time before start time',
  LIKELY_MISSING_ZERO_IN_INCOME: 'Income under BDT 100 for a month',
  LIKELY_MISSING_ZERO_IN_EXPENSE: 'Expense under BDT 100 for a month',
  CHILDREN_WITH_RESPONDENT_EXCEED_TOTAL: 'Child counts contradict',
  CHILD_DETAILS_WHEN_TOTAL_ZERO: 'Child details but zero children',
  OTHER_CHILD_LOCATION_MISSING: "Other children's location missing",
  NEGATIVE_CHILD_COUNT: 'Negative child count',
  AGE_MISMATCH: 'Screening and demographic age differ',
  AGE_OUT_OF_RANGE: 'Age outside eligible range',
  CONSENT_NO_BUT_INTERVIEW_COMPLETED: 'Interview recorded without consent',
  DUPLICATE_SUBMISSION_ID: 'Duplicate submission ID',
  EXACT_DUPLICATE_ANSWER_PATTERN: 'Identical answer pattern',
  INVALID_GPS: 'Invalid GPS coordinates',
  INCOMPLETE_GPS: 'Incomplete GPS coordinates',
}
const humanRule = (id: string) =>
  RULE_LABEL[id] ?? id.toLowerCase().replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
const fmtVal = (v: unknown) =>
  v == null ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v)

/* Kobo names a select_multiple field "Question text/Choice label", so a flag on
   three choices of one question repeated that question three times. Take the
   question once, and keep only the choice labels. */
const splitField = (f: string): [string, string | null] => {
  const i = f.lastIndexOf('/')
  return i < 0 ? [f, null] : [f.slice(0, i), f.slice(i + 1)]
}
const describeFields = (fields?: string[]): { question: string; choices: string[] } | null => {
  if (!fields?.length) return null
  const parts = fields.map(splitField)
  const questions = [...new Set(parts.map(([q]) => q))]
  if (questions.length !== 1) return null
  const choices = parts.map(([, c]) => c).filter(Boolean) as string[]
  return { question: questions[0], choices }
}

/* What the engine's scalar `observed` actually IS, per rule. It was captioned
   "Recorded answer" for every rule, so INTERVIEW_TOO_SHORT — the largest rule on
   the board — read "Recorded answer: 23.4", presenting a computed duration as if
   the respondent had said "23.4". The unit belongs beside the number, not two
   paragraphs away in the message text. */
const OBSERVED_CAPTION: Record<string, (v: string) => string> = {
  INTERVIEW_TOO_SHORT: (v) => `Interview length: ${v} minutes`,
  END_BEFORE_START: (v) => `Interview length: ${v} minutes`,
  AGE_OUT_OF_RANGE: (v) => `Age recorded: ${v}`,
  LIKELY_MISSING_ZERO_IN_INCOME: (v) => `Amount recorded: ৳${v}`,
  LIKELY_MISSING_ZERO_IN_EXPENSE: (v) => `Amount recorded: ৳${v}`,
  NEGATIVE_CHILD_COUNT: (v) => `Number recorded: ${v}`,
}

/* Anything the engine reports as a key/value shape — {current_age, start_age,
   duration_answer} on the work-history rule, {site, distance_km} on GPS — is the
   evidence itself. Show every value as a labelled row: dropping them left the
   drawer stating a problem it never showed. */
const OBSERVED_LABEL: Record<string, string> = {
  current_age: 'Age now',
  start_age: 'Age when she started',
  duration_answer: 'Years of sex work (as answered)',
  income: 'Income', expenses: 'Expenses', ratio: 'Expenses ÷ income',
  latitude: 'Latitude', longitude: 'Longitude',
  site: 'Site', distance_km: 'Distance from the site (km)',
}
const observedRows = (o: unknown): [string, string][] | null => {
  if (o == null || typeof o !== 'object' || Array.isArray(o)) return null
  const r = o as Record<string, unknown>
  if (r.exclusive || r.also_selected) return null   // has its own sentence
  const rows = Object.entries(r)
    .filter(([, v]) => v != null && v !== '')
    .map(([k, v]) => [
      OBSERVED_LABEL[k] ?? k.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase()),
      String(v),
    ] as [string, string])
  return rows.length ? rows : null
}

/* The engine's `observed` is a plain value for most rules and a shape like
   {exclusive:[...], also_selected:[...]} for the conflict rule. Rendering it as
   raw JSON made the reader parse a data structure to learn what the person
   answered. State it as a sentence instead. */
const describeObserved = (o: unknown): string | null => {
  if (o == null || typeof o !== 'object' || Array.isArray(o)) return null
  const r = o as Record<string, unknown>
  const list = (v: unknown) => (Array.isArray(v) ? v.map(String) : [])
  if (r.exclusive || r.also_selected) {
    const ex = list(r.exclusive), also = list(r.also_selected)
    if (!ex.length || !also.length) return null
    return `The respondent is recorded as answering “${ex.join(', ')}” and, on the same question, also “${also.join('” and “')}”. These cannot both be true.`
  }
  return null
}

/* Compact form for the queue column, where a JSON blob truncated at 180px told
   the reader nothing at all. */
const briefObserved = (o: unknown): string => {
  if (o == null) return '—'
  if (typeof o !== 'object') return String(o)
  const r = o as Record<string, unknown>
  const list = (v: unknown) => (Array.isArray(v) ? v.map(String) : [])
  const ex = list(r.exclusive), also = list(r.also_selected)
  if (ex.length && also.length) {
    return `“${ex[0]}” + ${also.length} other${also.length === 1 ? '' : 's'}`
  }
  return Object.entries(r).map(([k, v]) => `${k.replace(/_/g, ' ')} ${v}`).join(', ')
}

function MiniKpi({ label, value, tone, onClick, active, sub }: {
  label: string; value: React.ReactNode; tone: string
  onClick?: () => void; active?: boolean; sub?: string
}) {
  return (
    <button onClick={onClick} disabled={!onClick}
      aria-pressed={onClick ? !!active : undefined}
      title={onClick ? 'Filter the queue to this severity' : undefined}
      style={{
        flex: '1 1 130px', minWidth: 118, minHeight: 80, textAlign: 'left',
        cursor: onClick ? 'pointer' : 'default', fontFamily: 'var(--ui)',
        background: active ? 'var(--brand-soft)' : 'var(--surface)',
        border: `1px solid ${active ? 'var(--unfpa)' : 'var(--hair)'}`,
        borderRadius: 'var(--r-md)', padding: '10px 12px', boxShadow: 'var(--sh-1)',
      }}>
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.03em', textTransform: 'uppercase', color: tone }}>{label}</div>
      <div style={{ fontFamily: 'var(--display)', fontSize: 24, fontWeight: 700, color: 'var(--ink)', fontVariantNumeric: 'tabular-nums', lineHeight: 1.2 }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: 'var(--muted)' }}>{sub}</div>}
    </button>
  )
}

export function AnomalyQueue({ report, severity, onSeverity, onReviewSaved }: {
  report: AnomalyReport | null
  severity: '' | Sev
  onSeverity: (s: '' | Sev) => void
  onReviewSaved: () => void
}) {
  const [rule, setRule] = useState('')
  const [reviewStatus, setReviewStatus] = useState<'' | ReviewStatus>('')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(0)
  const [active, setActive] = useState<Anomaly | null>(null)
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  const anomalies = report?.anomalies ?? []

  /* B — priority rules, over the server-filtered set (before local queue filters) */
  const priorityRules = useMemo(() => {
    const groups: Record<string, { severity: Sev; records: Set<string>; enums: Set<string>; action: string }> = {}
    const rank: Record<Sev, number> = { critical: 4, high: 3, medium: 2, low: 1 }
    for (const a of anomalies) {
      const g = (groups[a.rule_id] ??= { severity: a.severity, records: new Set(), enums: new Set(), action: a.action || '' })
      if (rank[a.severity] > rank[g.severity]) g.severity = a.severity
      if (a.record_id) g.records.add(a.record_id)
      if (a.enumerator) g.enums.add(a.enumerator)
    }
    return Object.entries(groups)
      .map(([id, g]) => ({ id, ...g, affected: g.records.size || 0 }))
      .sort((a, b) => rank[b.severity] - rank[a.severity] || b.affected - a.affected)
      .slice(0, 6)
  }, [anomalies])

  /* C — queue rows after local filters. Severity narrows THIS list only: the KPI
     cards, the priority rules and the enumerator table must keep counting every
     severity, or the filter would rewrite the figures rather than filter the view. */
  const rows = useMemo(() => anomalies.filter((a) =>
    (!severity || a.severity === severity) &&
    (!rule || a.rule_id === rule) &&
    (!reviewStatus || a.review_status === reviewStatus) &&
    (!q || (a.rule_id + ' ' + a.message + ' ' + (a.record_id || '') + ' ' + (a.enumerator || ''))
      .toLowerCase().includes(q.toLowerCase()))
  ), [anomalies, severity, rule, reviewStatus, q])

  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE))
  const pageRows = rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const setLocal = (fn: () => void) => { fn(); setPage(0) }

  async function review(a: Anomaly, status: ReviewStatus) {
    setSaving(true); setErr('')
    try {
      await api.post('/baseline/fsw-anomalies/review/', {
        submission_id: a.record_id, rule_id: a.rule_id, status, note,
      })
      setActive((prev) => prev ? { ...prev, review_status: status, review_note: note } : prev)
      onReviewSaved()
    } catch (e) {
      setErr(apiErrorMessage(e, 'Could not save the review.'))
    } finally {
      setSaving(false)
    }
  }

  if (!report) {
    return <div className="card" style={{ padding: 22, textAlign: 'center', color: 'var(--muted)' }}>Scanning for anomalies…</div>
  }
  const k = report.kpis

  return (
    <div>
      <div className="dsec">
        <div>
          <h2 className="dsec-h">Data quality &amp; anomalies</h2>
          <p className="dsec-sub">
            {k.flags_total.toLocaleString()} flags across {k.interviews_affected.toLocaleString()} interviews
            of {report.records_scanned.toLocaleString()} scanned. Pick a priority rule to focus the queue.
          </p>
        </div>
      </div>

      {/* A — compact KPI row */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 16 }}>
        <MiniKpi label="Critical" value={k.critical} tone="var(--crit)"
          active={severity === 'critical'} onClick={() => onSeverity(severity === 'critical' ? '' : 'critical')} sub="flags" />
        <MiniKpi label="High" value={k.high} tone="var(--high)"
          active={severity === 'high'} onClick={() => onSeverity(severity === 'high' ? '' : 'high')} sub="flags" />
        <MiniKpi label="Medium" value={k.medium} tone="var(--warn)"
          active={severity === 'medium'} onClick={() => onSeverity(severity === 'medium' ? '' : 'medium')} sub="flags" />
        <MiniKpi label="Interviews affected" value={k.interviews_affected} tone="var(--accent)"
          sub="unique records" />
        <MiniKpi label="Flags reviewed" value={`${k.flags_reviewed} of ${k.flags_total}`} tone="var(--ok)"
          sub="decisions on flags" />
      </div>

      {/* B + C — one workspace: priority rules (span 4) beside the queue (span 8) */}
      <div style={{ display: 'flex', gap: 14, alignItems: 'stretch', flexWrap: 'wrap' }}>
        <div className="card" style={{ flex: '1 1 300px', minWidth: 280, padding: '14px 16px' }}>
          <div style={{ fontFamily: 'var(--display)', fontWeight: 700, fontSize: 15, color: 'var(--ink)' }}>Priority rules</div>
          <div style={{ fontSize: 12.5, color: 'var(--muted)', marginBottom: 6 }}>Click to focus the review queue</div>
          {priorityRules.length ? priorityRules.map((r) => (
            <button key={r.id} className={`prow ${rule === r.id ? 'on' : ''}`}
              onClick={() => setLocal(() => setRule(rule === r.id ? '' : r.id))} title={r.action}>
              <span className={`tagchip ${SEV_CLS[r.severity]}`} style={{ flexShrink: 0 }}>{SEV_ICON[r.severity]}{r.severity}</span>
              <span style={{ flex: 1, minWidth: 0 }}>
                <span style={{ display: 'block', fontWeight: 700, color: 'var(--ink)' }}>{humanRule(r.id)}</span>
                <span style={{ fontSize: 12.5, color: 'var(--muted)' }}>{r.affected} interview{r.affected === 1 ? '' : 's'} · {r.enums.size} enumerator{r.enums.size === 1 ? '' : 's'}</span>
              </span>
              <ChevronRight size={16} style={{ color: rule === r.id ? 'var(--unfpa)' : 'var(--muted)', flexShrink: 0 }} />
            </button>
          )) : <div style={{ padding: '18px 0', color: 'var(--muted)', fontSize: 13 }}>No anomalies in the current filter.</div>}
        </div>

        <div className="card" style={{ flex: '2 1 520px', minWidth: 320, padding: '14px 16px', display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
            <div style={{ position: 'relative' }}>
              <Search size={14} style={{ position: 'absolute', left: 9, top: 11, color: 'var(--muted)' }} />
              <input aria-label="Search anomalies" className="field" value={q}
                onChange={(e) => setLocal(() => setQ(e.target.value))}
                placeholder="Search rule / submission / enumerator…"
                style={{ paddingLeft: 28, width: 220 }} />
            </div>
            <select aria-label="Filter by rule" className="field" value={rule}
              onChange={(e) => setLocal(() => setRule(e.target.value))} style={{ maxWidth: 200 }}>
              <option value="">All rules</option>
              {Object.keys(report.summary.top_rules).map((r) => <option key={r} value={r}>{humanRule(r)}</option>)}
            </select>
            <select aria-label="Filter by review status" className="field" value={reviewStatus}
              onChange={(e) => setLocal(() => setReviewStatus(e.target.value as '' | ReviewStatus))}>
              <option value="">Any review status</option>
              {(Object.keys(STATUS_LABEL) as ReviewStatus[]).map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
            </select>
            <span style={{ flex: 1 }} />
            <span style={{ fontSize: 13, color: 'var(--muted)' }}>
              {rows.length ? `${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, rows.length)} of ${rows.length.toLocaleString()} flags` : '0 flags'}
            </span>
          </div>

          {err && <div style={{ color: 'var(--high)', fontSize: 13, marginBottom: 8 }}>{err}</div>}

          <div className="tscroll" style={{ maxHeight: 520 }}>
            <table className="dtable">
              <thead>
                <tr>
                  {[['Severity', 92], ['Anomaly', 250], ['Submission', 108], ['Enumerator', 132], ['Site', 52], ['Observed', 170], ['Review', 96]].map(([h, w]) => (
                    <th key={h as string} style={{ width: w as number }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {pageRows.map((a, i) => (
                  <tr key={`${a.record_id}-${a.rule_id}-${i}`} tabIndex={0} role="button"
                    aria-label={`Open ${humanRule(a.rule_id)}`}
                    onClick={() => { setActive(a); setNote(a.review_note || '') }}
                    onKeyDown={(e) => e.key === 'Enter' && (setActive(a), setNote(a.review_note || ''))}
                    style={{ height: 46 }}>
                    <td><span className={`tagchip ${SEV_CLS[a.severity]}`}>{SEV_ICON[a.severity]}{a.severity}</span></td>
                    <td style={{ fontWeight: 700 }}>{humanRule(a.rule_id)}</td>
                    <td className="mono" style={{ fontSize: 11.5, color: 'var(--muted)', maxWidth: 108, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.record_id || '—'}</td>
                    <td style={{ color: 'var(--muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 140 }}>{a.enumerator || '—'}</td>
                    <td style={{ color: 'var(--muted)' }}>{a.site || '—'}</td>
                    <td style={{ color: 'var(--muted)', maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={fmtVal(a.observed)}>{briefObserved(a.observed)}</td>
                    <td><span style={{ fontSize: 12, fontWeight: 700, color: STATUS_TONE[a.review_status] }}>{STATUS_LABEL[a.review_status]}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!rows.length && <div style={{ padding: 22, textAlign: 'center', color: 'var(--muted)', fontSize: 13 }}>No anomalies match the current filters. Reset filters or choose a wider date range.</div>}
          </div>

          {pages > 1 && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 10, marginTop: 10, fontSize: 13 }}>
              <button className="pill" aria-label="Previous page" disabled={page === 0} onClick={() => setPage(page - 1)}><ChevronLeft size={14} /></button>
              <span style={{ color: 'var(--muted)' }}>Page {page + 1} of {pages}</span>
              <button className="pill" aria-label="Next page" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}><ChevronRight size={14} /></button>
            </div>
          )}
        </div>
      </div>

      {/* side drawer */}
      {active && (
        <div onClick={() => setActive(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)', zIndex: 120, display: 'flex', justifyContent: 'flex-end' }}>
          <div onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Anomaly detail"
            style={{ width: 'min(520px, 100%)', height: '100%', background: 'var(--surface)', boxShadow: '-8px 0 30px rgba(0,0,0,0.18)', overflowY: 'auto', padding: '22px 24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
              <span className={`tagchip ${SEV_CLS[active.severity]}`}>{SEV_ICON[active.severity]}{active.severity} · {active.category}</span>
              <button onClick={() => setActive(null)} aria-label="Close anomaly detail" style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)', display: 'grid', placeItems: 'center', width: 36, height: 36, borderRadius: 8 }}><X size={19} /></button>
            </div>
            <h3 style={{ fontFamily: 'var(--display)', fontSize: 19, fontWeight: 700, color: 'var(--ink)', margin: '10px 0 5px' }}>{humanRule(active.rule_id)}</h3>
            <p style={{ fontSize: 14, color: 'var(--muted)', lineHeight: 1.5, margin: '0 0 16px' }}>{active.message}</p>

            {(() => {
              const fd = describeFields(active.fields)
              // A field is only worth showing if it is the questionnaire's own wording.
              // Some rules carry the raw column name ('b108') instead — printing that
              // as "Question asked" just swaps one piece of jargon for another.
              const question = fd && /\s/.test(fd.question) ? fd.question : null
              const sentence = describeObserved(active.observed)
              const scalar = active.observed != null && typeof active.observed !== 'object'
                ? String(active.observed) : null
              const rows = observedRows(active.observed)
              if (!question && !sentence && !scalar && !rows) return null
              return (
                <div style={{ marginBottom: 16, padding: '12px 14px', background: 'var(--brand-soft)', borderRadius: 'var(--r-md)' }}>
                  {question && (
                    <div style={{ fontSize: 13.5, color: 'var(--ink)', lineHeight: 1.5, marginBottom: 8 }}>
                      <span style={{ color: 'var(--muted)' }}>Question asked: </span>{question}
                    </div>
                  )}
                  {sentence && (
                    <p style={{ fontSize: 14, color: 'var(--ink)', lineHeight: 1.55, margin: 0 }}>{sentence}</p>
                  )}
                  {!sentence && scalar && (
                    <div style={{ fontSize: 14, color: 'var(--ink)' }}>
                      {OBSERVED_CAPTION[active.rule_id]
                        ? <strong>{OBSERVED_CAPTION[active.rule_id](scalar)}</strong>
                        : <><span style={{ color: 'var(--muted)' }}>Recorded answer: </span>
                          <strong>{scalar}</strong></>}
                    </div>
                  )}
                  {!sentence && rows && (
                    <div style={{ display: 'grid', gap: 4 }}>
                      {rows.map(([k, v]) => (
                        <div key={k} style={{ fontSize: 14, color: 'var(--ink)' }}>
                          <span style={{ color: 'var(--muted)' }}>{k}: </span><strong>{v}</strong>
                        </div>
                      ))}
                    </div>
                  )}
                  {!sentence && active.expected && (
                    <div style={{ fontSize: 13.5, color: 'var(--muted)', marginTop: 6 }}>
                      Expected: {fmtVal(active.expected)}
                    </div>
                  )}
                </div>
              )
            })()}

            {([
              ['What to do', [['Action', active.action]]],
              ['This interview', [['Enumerator', active.enumerator], ['Site', active.site], ['Interview date', active.date]]],
            ] as const).map(([group, pairs]) => {
              const rows = pairs.filter(([, v]) => v)
              if (!rows.length) return null
              return (
                <div key={group} style={{ marginBottom: 16 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.04em', color: 'var(--muted)', marginBottom: 7 }}>{group}</div>
                  <dl className="ddl">
                    {rows.map(([label, val]) => (<React.Fragment key={label}><dt>{label}</dt><dd>{val}</dd></React.Fragment>))}
                  </dl>
                </div>
              )
            })}

            {/* The identifiers still matter — you need the submission ID to open the
                record in KoboToolbox — but they are for looking something up, not for
                understanding the flag, so they no longer lead. */}
            <details style={{ marginBottom: 16 }}>
              <summary style={{ fontSize: 12, color: 'var(--muted)', cursor: 'pointer' }}>
                Record details for KoboToolbox
              </summary>
              <dl className="ddl" style={{ marginTop: 8 }}>
                <dt>Submission</dt><dd style={{ wordBreak: 'break-all' }}>{active.record_id}</dd>
                {active.fields?.length ? (<><dt>Fields</dt><dd style={{ wordBreak: 'break-word' }}>
                  {active.fields.map((f) => splitField(f)[1] ?? f).join(', ')}
                </dd></>) : null}
                <dt>Rule</dt><dd>{active.rule_id}</dd>
              </dl>
            </details>

            <div style={{ marginTop: 4, paddingTop: 16, borderTop: '1px solid var(--hair)' }}>
              <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.04em', color: 'var(--muted)', marginBottom: 8 }}>
                Your decision · currently <span style={{ color: STATUS_TONE[active.review_status] }}>{STATUS_LABEL[active.review_status]}</span>
                {active.reviewed_by && <span style={{ fontWeight: 400 }}> by {active.reviewed_by}</span>}
              </div>
              <textarea value={note} onChange={(e) => setNote(e.target.value)}
                placeholder="Note (optional): what you checked, what you found…"
                style={{ width: '100%', minHeight: 66, fontSize: 14, padding: 10, resize: 'vertical', borderRadius: 'var(--r-sm)', border: '1px solid var(--hair-2)', background: 'var(--surface)', color: 'var(--ink)', fontFamily: 'var(--ui)' }} />
              <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
                <button disabled={saving} onClick={() => review(active, 'confirmed')} className="btn"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 5, height: 38, background: 'var(--high)', color: '#fff', borderColor: 'var(--high)' }}><Check size={15} />It is a real error</button>
                <button disabled={saving} onClick={() => review(active, 'corrected')} className="btn"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 5, height: 38 }}><PencilLine size={15} />I fixed it in Kobo</button>
                <button disabled={saving} onClick={() => review(active, 'false_positive')} className="btn"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 5, height: 38 }}><Ban size={15} />The answer is right</button>
                <button disabled={saving} onClick={() => review(active, 'needs_verification')} className="btn"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 5, height: 38 }}><MapPinned size={15} />Ask the field team</button>
              </div>
              <p style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 12, lineHeight: 1.5, display: 'flex', gap: 6 }}>
                <ShieldCheck size={14} style={{ flexShrink: 0, marginTop: 1 }} />
                Corrections are made in KoboToolbox. This records your verdict only — the raw survey data is never edited here.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
