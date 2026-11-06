/**
 * Local render harness for the 23 Aug 2026 RCH correction round.
 *
 * It mounts the REAL components (not copies) and feeds them fixtures through
 * the shared axios instance, so what renders here is what the dashboard
 * renders. Fixtures carry the LIVE production figures, read from the API in
 * an authenticated session, so a panel shot here matches the dashboard.
 *
 * Dev-only: reachable at /preview.html under `npm run dev`. It is not linked
 * from the app and never ships to Railway (vite builds index.html only).
 */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '../index.css'
import '../i18n'
import { api } from '@/api/client'
import { ThemeProvider } from '@/context/ThemeContext'
import { ActionPlanTracker } from '@/components/ciprb/ActionPlanTracker'
import { FistulaIndicators } from '@/components/ciprb/FistulaIndicators'
import { MPDSRVisualizations } from '@/components/ciprb/MPDSRVisualizations'

const dist = (pairs: [string, number, number][]) =>
  pairs.map(([key, n, pct]) => ({ key, n, pct }))

const ACTION_AGGREGATES = {
  overall_pct: 40,
  total: 81,
  overdue: 51,
  by_status: [
    { status: 'pending', label: 'Pending / not started', count: 1 },
    { status: 'in_progress', label: 'In progress', count: 63 },
    { status: 'implemented', label: 'Implemented', count: 17 },
    { status: 'delayed', label: 'Delayed', count: 0 },
    { status: 'dropped', label: 'Dropped', count: 0 },
  ],
  // Live production figures, read from the API in an authenticated session.
  by_district: dist([
    ['Kurigram', 29, 72], ['Sirajganj', 3, 67], ['Gaibandha', 8, 62],
    ['Noakhali', 5, 60], ['Sunamganj', 22, 9], ['Bhola', 3, 0],
    ['Sherpur', 11, 0],
  ]),
  by_section: dist([
    ['Common Modifiable Factor (Community)', 13, 50],
    ['MPDSR System Strengthening', 59, 40],
    ['Common Modifiable Factor (Facility)', 9, 31],
  ]),
  actions: [],
}

const FISTULA_AGGREGATES = {
  total: 162,
  age: { '20-24': 31, '25-29': 44, '30-34': 38, '35+': 36 },
  education: { no_education: 51, primary: 44, secondary: 38, higher_secondary: 16 },
  marital_status: { married: 118, separated: 14, divorced: 9, widowed: 8 },
  age_at_marriage: { '<15': 41, '15-17': 62, '18-20': 33, '21+': 13 },
  age_at_first_delivery: { '<16': 28, '16-18': 57, '19-21': 44, '22+': 20 },
  number_of_children: { '1': 34, '2': 48, '3': 41, '4+': 26 },
  mode_of_last_delivery: { nvd: 96, csection: 41, assisted_vaginal: 12 },
  place_of_last_delivery: { gov_facility: 62, private_facility: 33, home: 54 },
  conducted_last_delivery: { doctor: 47, nurse: 22, midwife: 19, tba: 41, relatives: 20 },
  reasons_no_institutional_delivery: { financial: 38, transport: 27, traditional: 21, no_idea: 12, other: 8 },
  time_duration_fistula_occurrence: { '<1 week': 63, '1-4 weeks': 48, '>1 month': 38 },
  duration_suffering: { '<1 year': 44, '1-5 years': 61, '>5 years': 44 },
  // The panel RCH asked to turn into a pie.
  delivery_outcome: { stillbirth: 74, livebirth: 81 },
  fistula_type_v2: { obstetric: 108, iatrogenic: 27, traumatic: 9, congenital: 5 },
  iatrogenic_cause: { hysterectomy: 14, csection: 10, laparoscopy: 3 },
  genital_fistula_type: { vvf: 91, rvf: 32, ureterovaginal: 14, urethrovaginal: 12 },
  surgery_outcome_v2: { success_dry: 74, success_not_dry: 19, failed: 8 },
}

const MPDSR_AGGREGATES = {
  denominators: [],
  facility_counts: [],
  facility_totals: { fdn_md: 34, fdn_nd: 41, fdn_sb: 12, fdr_md: 22, fdr_nd: 18, fdr_sb: 3 },
  notification_by_level: {
    md: { community: 42, facility: 34 },
    nd: { community: 29, facility: 41 },
    sb: { community: 9, facility: 12 },
  },
  action_plan_summaries: [],
  totals: { mpdsr_cases: 139, fistula_corner_cases: 149, fistula_campaign_visits: 0 },
  review_counts: { va_md: 31, va_nd: 24, sa_md: 45, f4: 22, f5: 18, notified_md: 76, notified_nd: 70 },
  records_by_district: {
    Kurigram: 38, Sunamganj: 29, Sherpur: 21, Gaibandha: 18,
    Noakhali: 14, Sirajganj: 11, Bhola: 8,
  },
  facility: {
    total: 8,
    admission_to_death: { '<1 day': 6, '1-2 days': 2, '3-7 days': 0, '7+ days': 0, Unknown: 0 },
    review_status: { reported: 8 },
    // Still returned by the API; the tile that displayed it has been removed.
    action_plan_coverage: { with_plan: 0, without_plan: 8 },
  },
  neonatal: {
    total: 59,
    cause_of_death: { preterm_lbw: 21, asphyxia: 17, sepsis: 14, other: 7 },
    by_level: { community: 29, facility: 30 },
  },
  notifications: {
    total: 148,
    by_kind: { maternal: 76, neonatal: 51, stillbirth: 21 },
    by_level: { community: 80, facility: 68 },
    by_district: { Kurigram: 41, Sunamganj: 32, Sherpur: 22, Gaibandha: 19, Noakhali: 15, Sirajganj: 11, Bhola: 8 },
  },
  // The panel RCH asked to split by type.
  social_autopsy: {
    total: 46,
    place_of_death: { 'Health facility': 46 },
    all_kinds_total: 72,
    by_kind: { maternal: 46, neonatal: 23, stillbirth: 3, unclassified: 0 },
  },
  indicators: {
    place_of_death: { Home: 31, 'Government facility': 24, 'Private facility': 12, 'On the way': 9 },
    death_period: { Antepartum: 19, Intrapartum: 28, 'Postpartum (within 42 days)': 29 },
    gestational_weeks: { '<28': 8, '28-33': 17, '34-36': 21, '37+': 30 },
    anc_visits_count: { '0': 11, '1-3': 27, '4-7': 29, '8+': 9 },
    pnc_received: { '0': 24, '1-2': 31, '3+': 21 },
    mode_of_delivery: { 'Normal vaginal': 44, 'Caesarean section': 26, 'Assisted vaginal': 6 },
    // The stat tile RCH asked to render graphically.
    delivery_outcome: {
      Stillbirth: 12, 'Live birth': 45, 'Not delivered': 18, Abortion: 3, Other: 2,
    },
    place_of_delivery: { Home: 29, 'Upazila health complex': 21, 'District hospital': 17, 'Private clinic': 9 },
    person_assisted_delivery: { Doctor: 27, Nurse: 18, Midwife: 14, TBA: 17 },
    maternal_age: { '<20': 12, '20-24': 24, '25-29': 21, '30-34': 14, '35+': 5 },
    time_death_after_birth_hours: {},
  },
}

// Serve every panel from fixtures. Replacing the adapter on the shared `api`
// instance means the components run their real fetch path — same URLs, same
// state transitions — with no network and no login.
const FIXTURES: [string, unknown][] = [
  ['/mpdsr/action-aggregates/', ACTION_AGGREGATES],
  ['/fistula/aggregates/', FISTULA_AGGREGATES],
  ['/mpdsr/aggregates/', MPDSR_AGGREGATES],
]
api.defaults.adapter = async (config) => {
  const url = config.url || ''
  const hit = FIXTURES.find(([path]) => url.startsWith(path))
  if (!hit) throw new Error('preview harness: no fixture for ' + url)
  return {
    data: hit[1], status: 200, statusText: 'OK',
    headers: {}, config, request: {},
  } as never
}

function Section({ id, title, ask, children }: {
  id: string; title: string; ask: string; children: React.ReactNode
}) {
  return (
    <section style={{ marginBottom: 46 }}>
      <div style={{
        display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap',
        marginBottom: 12, paddingBottom: 8, borderBottom: '2px solid var(--hair)',
      }}>
        <span className="mono" style={{
          fontSize: 11, fontWeight: 700, color: '#fff', background: '#F96000',
          borderRadius: 4, padding: '2px 7px',
        }}>{id}</span>
        <h2 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: 'var(--ink)' }}>{title}</h2>
        <span style={{ fontSize: 12.5, color: 'var(--muted)' }}>{ask}</span>
      </div>
      {children}
    </section>
  )
}

function Preview() {
  return (
    <div style={{ maxWidth: 1180, margin: '0 auto', padding: '28px 24px 80px' }}>
      <h1 style={{ fontSize: 22, fontWeight: 800, color: 'var(--ink)', margin: '0 0 4px' }}>
        RCH correction round, 23 August 2026
      </h1>
      <p style={{ fontSize: 13, color: 'var(--muted)', margin: '0 0 30px' }}>
        Fixture-driven render of every corrected panel. Numbers match the review screenshots.
      </p>

      <Section id="1 + 2" title="Response plan tracker"
        ask="By district as a count bar chart; section labels without VA / DR.">
        <ActionPlanTracker />
      </Section>

      <Section id="3" title="Fistula indicator 13"
        ask="Outcome of last delivery as a pie.">
        <FistulaIndicators />
      </Section>

      <Section id="4 + 5 + 6" title="MPDSR panels"
        ask="Delivery outcome graphical; action plan documented removed; social autopsy split by type.">
        <MPDSRVisualizations cases={[]} />
      </Section>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <Preview />
    </ThemeProvider>
  </StrictMode>
)
