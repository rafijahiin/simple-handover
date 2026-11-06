/**
 * Bandhu submission-readout labels for the Manager Approvals "What was
 * submitted" card.
 *
 * Bandhu's Kobo field names are prefixed per tool (pr_ = Patient Record F-05,
 * htc_ = HTC F-06, or_ = Daily Outreach F-04, …). The generic readout strips
 * "_" and title-cases, which turns `pr_tg` into the meaningless "Pr tg". This
 * helper instead (a) groups each field under its source tool and (b) humanises
 * the leaf with the project's real abbreviations expanded (STI, HIV, TG, IEC,
 * ART, GBV, …). Nothing is invented — labels are derived from the tool columns.
 */

// prefix → human group title (source tool). Order matters: first match wins.
const PREFIX_GROUPS: [string, string][] = [
  ['ml_',  'Mother List (F-1.1)'],
  ['log_', 'Wellness Logbook (F-01)'],
  ['pr_',  'Patient Record (F-05)'],
  ['htc_', 'HTC Register (F-06)'],
  ['gbv_', 'GBV Register (F-02)'],
  ['mh_',  'Mental Health Counseling (F-03)'],
  ['cn_',  'Daily Counseling'],
  ['rf_',  'Referral Register'],
  ['hv_',  'HIV Identified (F-08)'],
  ['or_',  'Daily Outreach (F-04)'],
  ['mc_',  'Mobile Health Camp (F-10)'],
  ['at_',  'Attendance (F-11)'],
  ['ev_',  'Event Report (F-12)'],
  ['st_',  'Stock Register (F-13)'],
  ['eb_',  'e-Billboard (F-14)'],
]

// tokens that should render upper-cased (programme abbreviations)
const UPPER = new Set([
  'sti', 'hiv', 'tg', 'gh', 'iec', 'bcc', 'art', 'gbv', 'fp', 'htc',
  'hts', 'psd', 'mhpss', 'kp', 'uid', 'dic', 'tb', 'id', 'mh',
])

function humanise(leaf: string): string {
  const words = leaf.split('_').filter(Boolean)
  if (words.length === 0) return leaf
  const out = words.map((w) =>
    UPPER.has(w.toLowerCase())
      ? w.toUpperCase()
      : w.charAt(0).toUpperCase() + w.slice(1),
  )
  return out.join(' ')
}

/**
 * Resolve a Bandhu field key to its readout label + group, or null if the key
 * isn't a Bandhu field (caller falls back to the generic humaniser).
 */
export function bandhuField(key: string): { label: string; group: string } | null {
  if (key === 'record_type') return { label: 'Record type', group: 'Submission' }
  for (const [prefix, group] of PREFIX_GROUPS) {
    if (key.startsWith(prefix)) {
      return { label: humanise(key.slice(prefix.length)), group }
    }
  }
  return null
}

/**
 * True when a submission belongs to Bandhu — accepts either the organisation
 * ("Bandhu") or a Bandhu form slug ("bandhu_service_log_v1").
 */
export function isBandhuForm(orgOrForm?: string): boolean {
  return !!orgOrForm && (orgOrForm === 'Bandhu' || orgOrForm.startsWith('bandhu_'))
}

// ─── Value decoding ───────────────────────────────────────────────────────────
// Kobo stores coded answers (TG="03", referral="htc_hts sti_kp"). A reviewer
// can't approve what they can't read, so decode the known coded values to their
// real labels for the submission readout. Unknown values pass through unchanged.

const TG_CODES: Record<string, string> = {
  '01': 'MSM', '02': 'MSW', '03': 'FSW', '04': 'EVA',
  '05': 'TG / Hijra', '06': 'Others',
}

const RECORD_TYPES: Record<string, string> = {
  patient_record: 'Patient Record (F-05)', htc: 'HTC Register (F-06)',
  gbv: 'GBV Register (F-02)', mh_counseling: 'Mental Health Counselling (F-03)',
  counseling_daily: 'Daily Counselling', referral: 'Referral',
  hiv_identified: 'HIV Identified (F-08)', wellness_logbook: 'Wellness Logbook (F-01)',
}

const REFERRAL_CODES: Record<string, string> = {
  tb: 'TB', sti_kp: 'STI (KP clinic)', general_health: 'General health',
  htc_hts: 'HIV testing (HTC/HTS)', mental_health: 'Mental health',
  gbv: 'GBV', fp: 'Family planning',
}

// F-01 Wellness Logbook referral codes (select_multiple f01_referral, field
// log_referral). Numeric 01-08 per build_bandhu_forms.py.
const F01_REFERRAL_CODES: Record<string, string> = {
  '01': 'STI', '02': 'General health', '03': 'Counseling',
  '04': 'Mental health', '05': 'Family planning', '06': 'Legal',
  '07': 'Lab test', '08': 'Other',
}

// Mother List coded demographics (build_bandhu_forms.py choice lists).
const EDUCATION_CODES: Record<string, string> = {
  '1': 'Illiterate', '2': 'Primary', '3': 'Secondary',
  '4': 'Higher Secondary', '5': 'Graduate / Masters',
}

const MARITAL_CODES: Record<string, string> = {
  '1': 'Single (never married)', '2': 'Married', '3': 'Widowed',
  '4': 'Separated', '5': 'Divorced / Others',
}

// Mother List col 17 — current status (ml_current_status).
const ML_STATUS_CODES: Record<string, string> = {
  '1': 'Not found', '2': 'In jail', '3': 'Left the place',
  '4': 'Others', '5': 'Dead',
}

/** Wrap a decoded label with its raw code, e.g. "Married (2)". */
function withCode(label: string, code: string): string {
  return `${label} (${code})`
}

/**
 * Decode a coded Bandhu field VALUE to a readable label, given the leaf field
 * key (e.g. 'pr_tg', 'record_type', 'pr_referral'). Returns the value unchanged
 * when no decode rule applies, so it is always safe to wrap.
 */
export function decodeBandhuValue(key: string, value: any): any {
  if (value === null || value === undefined || value === '') return value
  const v = String(value).trim()
  if (key === 'record_type') return RECORD_TYPES[v] || value
  // Target-group code fields: pr_tg, htc_tg, hv_tg, mc_tg, … plus the Mother
  // List gender field (ml_gender), which uses the same unified tg_code list.
  if (/(^|_)tg$/.test(key) || key === 'target_group' || key === 'ml_gender') {
    return TG_CODES[v] ? withCode(TG_CODES[v], v) : value
  }
  // F-01 Wellness Logbook referral (log_referral) — select_multiple of numeric
  // f01_referral codes, Kobo-joined by spaces. Checked before the generic
  // *_referral rule below so the numeric codes decode correctly.
  if (key === 'log_referral') {
    const labels = v.split(/\s+/).filter(Boolean).map((c) => F01_REFERRAL_CODES[c] || c)
    return labels.length ? labels.join(', ') : value
  }
  // Referral select_multiple — Kobo joins selected codes with spaces.
  if (key === 'pr_referral' || key.endsWith('_referral') || key.endsWith('referral')) {
    const labels = v.split(/\s+/).filter(Boolean).map((c) => REFERRAL_CODES[c] || c)
    return labels.length ? labels.join(', ') : value
  }
  // Mother List coded demographics.
  if (key === 'ml_education') return EDUCATION_CODES[v] ? withCode(EDUCATION_CODES[v], v) : value
  if (key === 'ml_marital') return MARITAL_CODES[v] ? withCode(MARITAL_CODES[v], v) : value
  if (key === 'ml_current_status') return ML_STATUS_CODES[v] ? withCode(ML_STATUS_CODES[v], v) : value
  return value
}
