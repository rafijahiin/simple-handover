// Mirrors backend DRF serializers. Keep in sync with the corresponding *.py files.

export type Organisation = 'CIPRB' | 'UNFPA' | 'PHD' | 'Bandhu'

// Role taxonomy per IDMS Developer Handoff (May 2026).
export type Role =
  | 'developer'
  | 'supervisor'
  | 'org_lead'
  | 'manager'
  | 'field_staff'
  | 'ciprb_baseline'
  | 'focal'

/** True for the roles that see cross-org dashboards / can manage users. */
export function isAdminRole(role: Role): boolean {
  return role === 'developer' || role === 'supervisor'
}

/** True for roles that have read access to other orgs' aggregated dashboards.
 *  Includes org_lead (CIPRB-style — full own org, read-only on others). */
export function canReadOtherOrgs(role: Role): boolean {
  return isAdminRole(role) || role === 'org_lead'
}
export type FormType = 'mpdsr' | 'fistula' | 'activity' | 'baseline'

// ─── Partner registry (Step 2) ────────────────────────────────────────────
// Mirrors partners/serializers.py.PartnerSerializer.
export interface Partner {
  id: string
  code: 'CIPRB' | 'Bandhu' | 'PHD'
  name: string
  name_bangla: string
  color_hex: string
  is_active: boolean
}

// ─── Indicator Targets (Step 2) ───────────────────────────────────────────
// Mirrors indicators/serializers.py.IndicatorTargetSerializer.
export interface IndicatorTarget {
  id: string
  partner: string                     // FK uuid (write)
  partner_code: 'CIPRB' | 'Bandhu' | 'PHD'  // denormalised (read-only)
  partner_color: string               // hex color from partner (read-only)
  objective_number: number            // 0 = overall, 1/2/3/4 per SIDA
  activity_code: string               // e.g. '1.1' or '1.5a' or 'OVERALL'
  activity_label: string
  indicator_label: string
  target_value: string | null         // DRF DecimalField — comes as string. Null = "Not Set".
  unit: string
  // Animesh spec — UNFPA-set monthly splits. List of {month, target} entries.
  // Same model as target_value (null/empty = "Not Set"). Editable in Target Config.
  monthly_targets: { month: string; target: number }[]
  source_form: string | null
  source_form_slug: string | null
  notes: string
  is_active: boolean
  created_at: string
  updated_at: string
  updated_by: string | null
  updated_by_email: string | null
}
export type SubmissionStatus = 'pending' | 'approved' | 'rejected'

export interface User {
  id: string
  email: string
  full_name: string
  first_name?: string
  last_name?: string
  organisation: Organisation
  role: Role
  date_joined: string
}

export interface AdminUser extends User {
  username: string
  is_active: boolean
  last_login: string | null
}

export interface LoginResponse {
  user: User
}

export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface KPIs {
  submissions_this_month: number
  submissions_pending: number
  active_workers: number
  fistula_cases_this_month: number
  mpdsr_cases_this_month: number
  gbv_cases_this_month: number
  previous_month_submissions: number
  mom_change_percent: number
  target_attainment: number | null
  // Cumulative programme totals (Animesh's high-level executive numbers)
  total_md_notified?: number
  total_md_reviewed?: number
  total_nd_notified?: number
  total_nd_reviewed?: number
  total_fistula_patients?: number
  total_fistula_referred?: number
  total_stillbirths_notified?: number
  total_stillbirths_reviewed?: number
  fistula_repaired?: number
  fistula_reintegrated?: number
  near_miss_total?: number
  as_of: string
}

export interface MonthlyRow {
  month: number
  month_name: string
  mpdsr: number
  fistula: number
  activity: number
  baseline: number
}

export interface MonthlyResponse {
  year: number
  months: MonthlyRow[]
}

export interface ActivityItem {
  id: string
  form_type: FormType
  form_type_display: string
  partner: string
  worker_name: string
  district: string
  submitted_at: string
  time_ago: string
}

export interface CentresResponse {
  month: string
  districts: { district: string; count: number; rank: number; trend?: number[] }[]
  total_centres?: number
}

export interface PartnerKPIs {
  submissions_this_month: number
  pending: number
  /** Bandhu two-stage: manager-approved, awaiting UNFPA final sign-off. Still
   *  uncounted by indicators. 0 for single-stage orgs (PHD). */
  pending_unfpa?: number
  active_workers: number
  fistula_cases: number
  mpdsr_cases: number
}
export type PartnerSummary = Record<'PHD' | 'Bandhu', PartnerKPIs>

export interface MapPoint {
  id: string
  lat: number
  lng: number
  form_type: FormType
  partner: string
  district: string
  submitted_at: string
}

export interface Submission {
  id: string
  kobo_id: string
  form_type: FormType
  form_type_display: string
  partner: string
  worker_name: string
  district: string
  region: string
  latitude: number | null
  longitude: number | null
  submitted_at: string
  received_at: string
  status: SubmissionStatus
  status_display: string
  reviewed_by: User | null
  reviewed_at: string | null
  rejection_reason: string
  /** Animesh baseline-duplication warning — only meaningful for BASELINE submissions. */
  is_baseline_duplicate?: boolean
  /**
   * MPDSR logic-error flag tags (Animesh QA-gate, deck slide 9). Stable
   * short identifiers like 'AGE_LOW', 'CAUSE_EMPTY'. Empty list when no
   * issues are detected or when the form is not MPDSR. The manager
   * approval queue renders an amber AlertTriangle pill when non-empty.
   */
  logic_flags?: string[]
  /**
   * Immutable audit trail of every review decision (Animesh: permanent
   * reviewer notes as evidence). Each entry records who, what action, an
   * optional note, and when. Appended on approve/reject; never edited.
   */
  review_history?: ReviewEntry[]
}

export interface ReviewEntry {
  reviewer: string
  reviewer_email: string
  action: string
  note: string
  timestamp: string
}

export interface SubmissionDetail extends Submission {
  raw_data: Record<string, unknown>
}

export type FistulaStatus =
  | 'identified'
  | 'action_required'
  | 'followup_pending'
  | 'referral_completed'

export interface FistulaCampaign {
  id: string
  case_hash: string
  partner: string
  district: string
  upazila: string
  union: string
  village: string
  facility_name: string
  region: string
  campaign_date: string
  women_screened: number
  women_reached_awareness: number
  men_reached_awareness: number
  community_sessions: number
  suspected_fistula_cases: number
  confirmed_fistula_cases: number
  new_cases: number
  repeat_cases: number
  fistula_type: string
  fistula_cause: string
  cases_referred: number
  cases_accepted_referral: number
  cases_reached_facility: number
  cases_surgery_completed: number
  cases_surgery_pending: number
  cases_surgery_not_eligible: number
  cases_followup_due: number
  cases_followup_completed: number
  cases_lost_followup: number
  cases_counselling_provided: number
  cases_social_reintegration: number
  main_barriers: string
  notes: string
  latitude: number | null
  longitude: number | null
  created_at: string
  updated_at: string
}

export type MPDSRStatus =
  | 'reported'
  | 'under_review'
  | 'committee_review'
  | 'action_plan_drafted'
  | 'closed'
export type DeathType = 'maternal' | 'perinatal'

export type PlaceOfDeath = 'facility' | 'home' | 'in_transit'

export interface AuditEntry {
  timestamp: string
  user: string
  action: string
  notes?: string
}

export interface MPDSRCase {
  id: string
  case_hash: string
  partner: string
  sub_form_type: string
  sub_form_label: string
  district: string
  upazila: string
  union: string
  region: string
  date_of_death: string
  death_type: DeathType
  death_type_display: string
  cause_of_death: string
  place_of_death: PlaceOfDeath
  facility_name: string
  age_years: number | null
  status: MPDSRStatus
  status_display: string
  committee_date: string | null
  action_plan: string
  notes: string
  is_overdue_committee: boolean
  audit_trail: AuditEntry[]
  latitude: number | null
  longitude: number | null
  created_at: string
  updated_at: string
}

export interface MonthlyTarget {
  id: string
  partner: string
  form_type: FormType
  year: number
  month: number
  target: number
  created_at: string
  updated_at: string
}

export type AlertSeverity = 'info' | 'warning' | 'critical'

export interface Alert {
  id: string
  partner: string
  alert_type: string
  alert_type_display: string
  severity: AlertSeverity
  severity_display: string
  title: string
  message: string
  acknowledged: boolean
  acknowledged_at: string | null
  created_at: string
}

export interface ForecastPoint {
  year: number
  month: number
  actual?: number
  forecast?: number
}

export interface ForecastResponse {
  partner: string
  form_type: FormType
  history: ForecastPoint[]
  attainment_percent: number | null
}

export type ReportFormat = 'pdf' | 'docx' | 'pptx'
export type ReportType = 'monthly_summary' | 'one_pager' | 'newsletter'

export interface Report {
  id: string
  report_type: ReportType
  report_type_display: string
  format: ReportFormat
  format_display: string
  partner: string
  year: number
  month: number
  title: string
  narrative: string
  file: string | null
  generated_by: string | null
  created_at: string
}

export type SurveyType = 'baseline' | 'endline'

export interface BaselineSurvey {
  id: string
  partner: string
  district: string
  upazila: string
  union: string
  facility_name: string
  region: string
  survey_type: SurveyType
  survey_type_display: string
  survey_date: string
  participant_code: string
  respondent_age: number | null
  sex: string
  education: string
  ses: string
  fp_use: string
  fp_method: string
  currently_pregnant: string
  anc_4visits: string
  skilled_birth_attendant: string
  danger_signs_knowledge: string
  fistula_awareness: string
  mpdsr_awareness: string
  gbv_awareness: string
  child_marriage_knowledge: string
  health_facility_distance: string
  srh_service_satisfaction: string
  is_duplicate: boolean
  duplicate_of: string | null
  created_at: string
  updated_at: string
}

// ─── Programs summary (from /api/dashboard/programs-summary/) ─────────────────

export interface ProgramsFormCount {
  count: number
  label: string
  label_bn: string
  category: string
}

export interface ProgramsMonthPoint {
  month: number
  year: number
  month_name: string
  clinical: number
  community: number
  operations: number
  total: number
}

export interface ProgramsSummary {
  partner: string
  year: number
  month: number
  total: number
  prev_total: number
  mom_change: number
  categories: { Clinical?: number; Community?: number; Operations?: number }
  counts: Record<string, ProgramsFormCount>
  monthly_trend: ProgramsMonthPoint[]
  top_forms: Array<ProgramsFormCount & { key: string }>
  available_months?: Array<{ year: number; month: number; label: string }>
  counts_all_submissions?: boolean
}

// ─── Indicator types (programs / indicators apps) ────────────────────────────

// Step 3 progress shape — one entry per IndicatorTarget row.
// Emitted by /api/indicators/progress/ via IndicatorProgressSerializer.
export interface IndicatorProgress {
  activity_code: string          // e.g. '1.4a', 'OVERALL'
  objective_number: number       // 0 (PHD overall), 1, 2, 3, 4 — no Bandhu 3
  activity_label: string
  indicator_label: string
  target_value: number | null    // null = "Not Set"
  unit: string
  achievement: number            // always a number; 0 if no records yet
  percentage: number | null      // null when target_value is null
                                 // 0 when target > 0 and achievement = 0
                                 // round(achievement / target * 100, 1) otherwise
  unlinked: boolean              // true if no compute fn yet for this code
  organisation?: string          // added by the view layer on the all-orgs roll-up

  // Monthly cadence (Animesh spec). UNFPA-set, same model as target_value:
  //   month_target null    → "Not set" pill, UNFPA hasn't configured this month
  //   month_target > 0     → render the monthly tile next to the overall tile
  // month_label is the YYYY-MM of the current calendar month.
  month_label?: string | null
  month_target?: number | null
  month_achievement?: number | null
  month_percentage?: number | null
}

export interface ServiceCenter {
  id: string
  organisation: string
  name: string
  name_bangla: string
  code: string
  center_type: 'DIC' | 'BROTHEL' | 'SUB_DIC' | 'MOBILE'
  district: string
  upazila: string
  address: string
  latitude: number | null
  longitude: number | null
  is_active: boolean
}

export type ApprovalStatus = 'PENDING' | 'APPROVED' | 'REJECTED'

export interface ApprovalItem {
  id: string
  organisation: string
  approval_status: ApprovalStatus
  submitted_by_kobo_user: string
  created_at: string
  // model-specific fields added at runtime
  [key: string]: unknown
}

export interface ProgramPendingItem {
  id: string
  model_type: string
  model_label: string
  endpoint: string
  organisation: string
  approval_status: ApprovalStatus
  submitted_by: string
  center_name: string
  center_code: string
  created_at: string
  summary: string
  latitude: number | null
  longitude: number | null
  kobo_submission_id: string
}

export interface ProgramPendingResponse {
  total: number                 // true backlog (pre display-cap)
  returned?: number             // rows actually carried in `items`
  truncated?: boolean           // true when total > returned (queue capped)
  counts_by_type: Record<string, number>
  /** TRUE pre-cap backlog per partner. Drives the queue's partner tab badges so
   *  they reflect the real total and drop on every approval — not the capped
   *  page (which back-fills a hidden row and leaves the badge stuck). */
  counts_by_org?: Record<string, number>
  items: ProgramPendingItem[]
}

export type ParticipantRole = 'community_worker' | 'supervisor' | 'health_staff' | 'other'

export interface TrainingAttendance {
  id: string
  participant_name: string
  role: ParticipantRole
  role_display: string
  attended: boolean
  notes: string
}

export interface TrainingSession {
  id: string
  partner: string
  district: string
  region: string
  topic: string
  facilitator: string
  date: string
  duration_hours: number | null
  expected_participants: number
  actual_participants: number
  attendance_rate: number | null
  notes: string
  attendances: TrainingAttendance[]
  created_at: string
  updated_at: string
}
