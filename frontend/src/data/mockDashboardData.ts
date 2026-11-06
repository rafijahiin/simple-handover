/**
 * ⚠️  MOCK DATA — SAFE TO DELETE
 *
 * This file contains illustrative demo data for the PHD and Bondhu dashboards.
 * It is used when the programs API returns zero submissions (i.e. no real data yet).
 *
 * When real field submissions start flowing in, delete this entire file and
 * remove the mockDashboardData import from OrgDashboard.tsx.
 *
 * Numbers are consistent with a UNFPA SRHR programme operating at typical
 * field scale in Bangladesh (CPE 2026 reference context).
 */

// ─── Type mirrors ────────────────────────────────────────────────────────────

export interface MockProgramsSummary {
  partner: string
  year: number
  month: number
  total: number
  prev_total: number
  mom_change: number
  categories: { Clinical: number; Community: number; Operations: number }
  counts: Record<string, { count: number; label: string; label_bn: string; category: string }>
  monthly_trend: Array<{
    month: number
    year: number
    month_name: string
    clinical: number
    community: number
    operations: number
    total: number
  }>
  top_forms: Array<{ key: string; count: number; label: string; label_bn: string; category: string }>
}

export interface MockCentresResponse {
  month: string
  districts: Array<{ district: string; count: number; rank: number }>
}

export interface MockPartnerKPIs {
  submissions_this_month: number
  pending: number
  active_workers: number
  fistula_cases: number
  mpdsr_cases: number
}

// ─── PHD ─────────────────────────────────────────────────────────────────────
// Brothel-based FSW SRHR programme (SIDA-funded, 11 brothels, 9 wellness centres).
// Form types are the 9 actually produced by the 3 consolidated PHD Kobo forms.
// Areas: Daulatdia (Rajbari), Tangail, Jessore, Faridpur, Mymensingh, etc.

const PHD_COUNTS: MockProgramsSummary['counts'] = {
  // Clinical — from Patient Services form
  client_registration:{ count: 0,  label: 'FSW Registrations',     label_bn: 'যৌনকর্মী নিবন্ধন',   category: 'Clinical'   },
  clinic_visit:       { count: 0,  label: 'Clinic Visits',         label_bn: 'ক্লিনিক পরিদর্শন',   category: 'Clinical'   },
  hiv_sti_test:       { count: 0,  label: 'HIV / STI Tests',       label_bn: 'এইচআইভি পরীক্ষা',    category: 'Clinical'   },
  // Community — from Patient Services + Activity & Ops
  referral:           { count: 0,  label: 'Referrals',             label_bn: 'রেফারেল',             category: 'Community'  },
  group_education:    { count: 0,  label: 'Group Education',       label_bn: 'দলগত স্বাস্থ্য শিক্ষা', category: 'Community'  },
  // Operations — from Activity & Ops form
  training_event:     { count: 0,  label: 'Events & Trainings',    label_bn: 'ইভেন্ট ও প্রশিক্ষণ',  category: 'Operations' },
  iec_material:       { count: 0,  label: 'IEC Materials',         label_bn: 'আইইসি উপকরণ',         category: 'Operations' },
  stock_entry:        { count: 0,  label: 'Stock Entries',         label_bn: 'স্টক এন্ট্রি',         category: 'Operations' },
  gbv_corner:         { count: 0,  label: 'GBV Corners',           label_bn: 'জিবিভি কর্নার',        category: 'Operations' },
}

export const MOCK_PHD: MockProgramsSummary = {
  partner: 'PHD',
  year: 2026,
  month: 5,
  // No mock totals — the dashboard will show "awaiting submissions" until real
  // submissions land on Railway. Don't display fake numbers on a programme dashboard.
  total: 0,
  prev_total: 0,
  mom_change: 0,
  categories: { Clinical: 0, Community: 0, Operations: 0 },
  counts: PHD_COUNTS,
  monthly_trend: [
    { month: 12, year: 2025, month_name: 'Dec', clinical: 0, community: 0, operations: 0, total: 0 },
    { month:  1, year: 2026, month_name: 'Jan', clinical: 0, community: 0, operations: 0, total: 0 },
    { month:  2, year: 2026, month_name: 'Feb', clinical: 0, community: 0, operations: 0, total: 0 },
    { month:  3, year: 2026, month_name: 'Mar', clinical: 0, community: 0, operations: 0, total: 0 },
    { month:  4, year: 2026, month_name: 'Apr', clinical: 0, community: 0, operations: 0, total: 0 },
    { month:  5, year: 2026, month_name: 'May', clinical: 0, community: 0, operations: 0, total: 0 },
  ],
  // top_forms intentionally empty so the "What's being submitted" grid hides
  // until real form submissions exist. The 16-indicator panel still renders.
  top_forms: [],
}

export const MOCK_PHD_KPIS: MockPartnerKPIs = {
  submissions_this_month: 0,
  pending: 0,
  active_workers: 0,
  fistula_cases: 0,
  mpdsr_cases: 0,
}

export const MOCK_PHD_CENTRES: MockCentresResponse = {
  month: 'June 2026',
  // Empty so the "active districts" table shows the empty-state, not stale data
  districts: [],
}

// ─── Bandhu: Bandhu Social Welfare Society ────────────────────────────────────
// Focus: key populations (FSW, transgender, MSM), HIV/STI, GBV, urban outreach
// Areas: Dhaka, Chittagong, Sylhet, Narayanganj, Comilla

const BONDHU_COUNTS: MockProgramsSummary['counts'] = {
  // Clinical (no antenatal_card — PHD only)
  hiv_sti_test:       { count: 203, label: 'HIV/STI Tests',         label_bn: 'এইচআইভি পরীক্ষা',     category: 'Clinical'   },
  clinic_visit:       { count: 156, label: 'Clinic Visits',         label_bn: 'ক্লিনিক পরিদর্শন',    category: 'Clinical'   },
  htc_counselling:    { count: 112, label: 'HTC Counselling',       label_bn: 'এইচটিসি পরামর্শ',     category: 'Clinical'   },
  mh_screening:       { count: 45,  label: 'MH Screenings',         label_bn: 'মানসিক স্বাস্থ্য',    category: 'Clinical'   },
  adr_record:         { count: 14,  label: 'ADR Records',           label_bn: 'পার্শ্বপ্রতিক্রিয়া', category: 'Clinical'   },
  autoclave_log:      { count: 7,   label: 'Autoclave Logs',        label_bn: 'অটোক্লেভ লগ',         category: 'Clinical'   },
  // Community (hygiene_kit is Bondhu only; no mobile_camp — PHD only)
  outreach_session:   { count: 134, label: 'Outreach Sessions',     label_bn: 'আউটরিচ সেশন',         category: 'Community'  },
  individual_counselling: { count: 189, label: 'Individual Counselling',label_bn: 'ব্যক্তিগত পরামর্শ',   category: 'Community'  },
  group_education:    { count: 78,  label: 'Group Education',       label_bn: 'গ্রুপ শিক্ষা',        category: 'Community'  },
  referral:           { count: 56,  label: 'Referrals',             label_bn: 'রেফারেল',              category: 'Community'  },
  gbv_case:           { count: 38,  label: 'GBV Cases',             label_bn: 'জিবিভি কেস',          category: 'Community'  },
  hygiene_kit:        { count: 112, label: 'Hygiene Kits',          label_bn: 'হাইজিন কিট',          category: 'Community'  },  // Bondhu only
  // Operations
  training_event:     { count: 5,   label: 'Training Events',       label_bn: 'প্রশিক্ষণ',           category: 'Operations' },
  coord_meeting:      { count: 4,   label: 'Coord. Meetings',       label_bn: 'সমন্বয় সভা',         category: 'Operations' },
}

export const MOCK_BONDHU: MockProgramsSummary = {
  partner: 'Bandhu',
  year: 2026,
  month: 5,
  total: 1156,
  prev_total: 1074,
  mom_change: 7.6,
  categories: { Clinical: 537, Community: 607, Operations: 9 },  // No Operations mobile_camp; 537 = 555-18
  counts: BONDHU_COUNTS,
  monthly_trend: [
    { month: 12, year: 2025, month_name: 'Dec', clinical: 285, community: 234, operations: 14, total: 533  },
    { month:  1, year: 2026, month_name: 'Jan', clinical: 307, community: 256, operations: 16, total: 579  },
    { month:  2, year: 2026, month_name: 'Feb', clinical: 328, community: 278, operations: 17, total: 623  },
    { month:  3, year: 2026, month_name: 'Mar', clinical: 350, community: 302, operations: 18, total: 670  },
    { month:  4, year: 2026, month_name: 'Apr', clinical: 497, community: 556, operations: 21, total: 1074 },
    { month:  5, year: 2026, month_name: 'May', clinical: 537, community: 607, operations:  9, total: 1156 },
  ],
  top_forms: [
    { key: 'hiv_sti_test',       count: 203, label: 'HIV/STI Tests',          label_bn: 'এইচআইভি পরীক্ষা',     category: 'Clinical'  },
    { key: 'individual_counselling', count: 189, label: 'Individual Counselling', label_bn: 'ব্যক্তিগত পরামর্শ',   category: 'Community' },
    { key: 'clinic_visit',       count: 156, label: 'Clinic Visits',          label_bn: 'ক্লিনিক পরিদর্শন',    category: 'Clinical'  },
    { key: 'outreach_session',   count: 134, label: 'Outreach Sessions',      label_bn: 'আউটরিচ সেশন',         category: 'Community' },
    { key: 'htc_counselling',    count: 112, label: 'HTC Counselling',        label_bn: 'এইচটিসি পরামর্শ',     category: 'Clinical'  },
    { key: 'hygiene_kit',        count: 112, label: 'Hygiene Kits',           label_bn: 'হাইজিন কিট',          category: 'Community' },
    { key: 'group_education',    count: 78,  label: 'Group Education',        label_bn: 'গ্রুপ শিক্ষা',        category: 'Community' },
    { key: 'gbv_case',           count: 38,  label: 'GBV Cases',              label_bn: 'জিবিভি কেস',          category: 'Community' },
  ],
}

export const MOCK_BONDHU_KPIS: MockPartnerKPIs = {
  submissions_this_month: 1156,
  pending: 18,
  active_workers: 31,
  fistula_cases: 7,
  mpdsr_cases: 2,
}

// Bandhu's 8 confirmed working districts (Ashis K. Acharjee, June 2026).
// Demo fallback only — shown behind the "demo data" badge until real Bandhu
// submissions arrive. Kept consistent with PARTNER_DISTRICTS.Bandhu.
export const MOCK_BONDHU_CENTRES: MockCentresResponse = {
  month: 'May 2026',
  districts: [
    { district: 'Narayanganj', count: 198, rank: 1 },
    { district: 'Chattogram',  count: 167, rank: 2 },
    { district: 'Noakhali',    count: 134, rank: 3 },
    { district: 'Chandpur',    count: 98,  rank: 4 },
    { district: 'Manikganj',   count: 76,  rank: 5 },
    { district: 'Habiganj',    count: 61,  rank: 6 },
    { district: 'Sunamganj',   count: 47,  rank: 7 },
    { district: 'Bandarban',   count: 29,  rank: 8 },
  ],
}

// ─── Convenience lookup ───────────────────────────────────────────────────────

export const MOCK_PROGRAMS: Record<'PHD' | 'Bandhu', MockProgramsSummary> = {
  PHD: MOCK_PHD,
  Bandhu: MOCK_BONDHU,
}

export const MOCK_KPIS: Record<'PHD' | 'Bandhu', MockPartnerKPIs> = {
  PHD: MOCK_PHD_KPIS,
  Bandhu: MOCK_BONDHU_KPIS,
}

export const MOCK_CENTRES: Record<'PHD' | 'Bandhu', MockCentresResponse> = {
  PHD: MOCK_PHD_CENTRES,
  Bandhu: MOCK_BONDHU_CENTRES,
}
