/**
 * Partner district coverage — PLACEHOLDER until the validation workshop.
 *
 * The supervisor will confirm the real district lists during the
 * 3–4 June 2026 workshop. Until then these are best-effort lists
 * based on the SIDA frameworks and Spondon project brief:
 *
 *   CIPRB  — RCH programme footprint (CP10 + a few others)
 *   Bandhu — KP/SOGIESC outreach focused on major divisional cities
 *   PHD    — FSW/brothel-based service delivery districts
 *
 * District names are matched case-insensitively against the
 * `shapeName` property in `/bangladesh-adm2.geojson` after stripping
 * non-letter characters. Replace this file (do not edit map logic)
 * once the workshop confirms the canonical lists.
 */
export type PartnerCode = 'CIPRB' | 'Bandhu' | 'PHD'

// Org identity colours — ALL UNFPA orange per the branding rule
// ("this is a UNFPA product, their brand colors are the only thing").
// Partners are identified by their CODE/NAME in the UI, not by hue.
export const PARTNER_COLORS: Record<PartnerCode, string> = {
  CIPRB:  '#F96000',
  Bandhu: '#F96000',
  PHD:    '#F96000',
}

// Coverage-map per-partner tints, drawn from the UNFPA Complex
// Visualisation Palette (https://unfpa.brandkit.host/visual-identity/
// colour/data-viz/). Three distinguishable hues so single-org districts
// read unambiguously, but every one is UNFPA-official:
//   CIPRB  → UNFPA Pastel Blue
//   Bandhu → UNFPA Pastel Green (data-viz only; UNFPA's one approved green)
//   PHD    → UNFPA Orange (primary brand)
// Every other surface on the site uses flat UNFPA orange (PARTNER_COLORS).
export const PARTNER_TINTS: Record<PartnerCode, string> = {
  CIPRB:  '#649BF2',   // UNFPA Pastel Blue (was #0072BC custom)
  Bandhu: '#58968A',   // UNFPA Pastel Green (was #00875A custom)
  PHD:    '#F96000',   // UNFPA Orange
}

// Overlap shading — two-org uses UNFPA amber tint, three-org uses status-off red.
export const OVERLAP_TWO_ORGS  = '#FDCFB3'   // UNFPA Light Orange (data-viz palette)
export const OVERLAP_THREE_ORGS = '#F10F45'  // UNFPA Red
export const NO_COVERAGE = '#E5E7EB'         // light grey

export const PARTNER_DISTRICTS: Record<PartnerCode, string[]> = {
  // CIPRB — the 19 working districts in CIPRB's Kobo form district dropdown
  // (CIPRB_DISTRICTS in build_ciprb_forms.py). Dhaka was added June 2026, so
  // the map now matches the live forms (Fistula, MPDSR, Social Autopsy,
  // Maternal Near Miss). Keep this list in sync with CIPRB_DISTRICTS.
  CIPRB: [
    'Sunamganj', 'Sherpur', 'Bhola', 'Kurigram', 'Gaibandha',
    'Khagrachari', 'Noakhali', 'Patuakhali', 'Sirajganj', 'Barguna',
    'Jamalpur', 'Bagerhat', 'Habiganj', 'Moulavibazar', 'Sylhet',
    'Bandarban', 'Chandpur', 'Rangpur', 'Dhaka',
  ],
  // Bandhu — the 8 working districts confirmed by Bandhu (Ashis K. Acharjee,
  // June 2026), replacing the earlier divisional-city placeholder. 'Chattogram'
  // matches the GeoJSON's 'Chittagong' via the alias table below.
  Bandhu: [
    'Sunamganj', 'Habiganj', 'Manikganj', 'Narayanganj',
    'Chattogram', 'Bandarban', 'Chandpur', 'Noakhali',
  ],
  // PHD = SIDA-funded brothel-based wellness centres.
  // The 9 official wellness centres (Master List, PHD May 2026) sit in
  // these 9 districts (one centre each). Names match the national GeoJSON.
  PHD: [
    'Rajbari',     // R001 Daulatdia Wellness Center (Goalanda)
    'Jessore',     // J002 Maroawary Mandir (GeoJSON uses 'Jessore')
    'Bagerhat',    // B003 Kuchuyapotti
    'Patuakhali',  // P004 Old Hospital Road
    'Faridpur',    // F005 Rathkhola
    'Mymensingh',  // M006 Ganginerpar
    'Jamalpur',    // J007 Raniganj
    'Tangail',     // T008 Kandapara
    'Khulna',      // D009 Banishanta (Dacope)
  ],
}

/** Route each partner tile points to from the homepage. */
export const PARTNER_ROUTES: Record<PartnerCode, string> = {
  CIPRB:  '/fistula',   // CIPRB's primary owned module
  Bandhu: '/bondhu',
  PHD:    '/phd',
}

// Partner display names. Sources:
//   PHD    — phd-bd.com  → "Partners in Health and Development"
//   Bandhu — bdplatform4sdgs.net → "Bandhu Social Welfare Society"
//   CIPRB  — Centre for Injury Prevention and Research, Bangladesh
// Keep these in sync with i18n org.eyebrow*Full and any hero copy.
export const PARTNER_NAMES: Record<PartnerCode, { en: string; bn: string }> = {
  CIPRB:  { en: 'CIPRB',                              bn: 'সিআইপিআরবি' },
  Bandhu: { en: 'Bandhu Social Welfare Society',      bn: 'বন্ধু সোশ্যাল ওয়েলফেয়ার সোসাইটি' },
  PHD:    { en: 'Partners in Health and Development', bn: 'পার্টনার্স ইন হেলথ অ্যান্ড ডেভেলপমেন্ট' },
}

/** Aliases for districts whose GeoJSON shapeName differs from the GoB
 *  spelling commonly used in app data and Sayed's Excel files. Add new
 *  rows here whenever a district fails to highlight on the map. */
const DISTRICT_ALIASES: Record<string, string> = {
  khagrachari:    'khagrachhari',     // GeoJSON has the double-h spelling
  patuakahli:     'patuakhali',       // common typo in Sayed's data
  chittagong:     'chattogram',       // GoB renamed in 2018
  barishal:       'barisal',          // GeoJSON uses old spelling
  cumilla:        'comilla',
  bogura:         'bogra',
  jashore:        'jessore',
  noakhli:        'noakhali',
  moulavibazar:   'maulvibazar',      // CIPRB/MPDSR data 'Moulavibazar' vs GeoJSON 'Maulvibazar'
}

/** Normalise a district name for matching against GeoJSON shapeName.
 *  Strips non-letters, lowercases, and applies the alias table so common
 *  alternate spellings map to the GeoJSON canonical form. */
export function normaliseDistrict(name: string): string {
  const base = (name ?? '').toLowerCase().replace(/[^a-z]/g, '')
  return DISTRICT_ALIASES[base] ?? base
}

/** Build a Map: districtKey → array of PartnerCodes covering it. */
export function buildCoverageMap(): Map<string, PartnerCode[]> {
  const map = new Map<string, PartnerCode[]>()
  for (const partner of ['CIPRB', 'Bandhu', 'PHD'] as PartnerCode[]) {
    for (const dist of PARTNER_DISTRICTS[partner]) {
      const key = normaliseDistrict(dist)
      const existing = map.get(key) ?? []
      existing.push(partner)
      map.set(key, existing)
    }
  }
  return map
}

/**
 * Resolve a district's fill colour from the partner list covering it.
 *   0 orgs → light grey
 *   1 org  → that partner's brand colour
 *   2 orgs → yellow (#FFC000)
 *   3 orgs → red    (#FF0000)
 */
export function fillForPartners(partners: PartnerCode[] | undefined): string {
  if (!partners || partners.length === 0) return NO_COVERAGE
  // Coverage map exception (Animesh: "homepage map should have different
  // colours like before"). Use the PARTNER_TINTS scale so single-partner
  // districts are visually distinguishable. The rest of the site still
  // uses the flat UNFPA orange from PARTNER_COLORS.
  if (partners.length === 1) return PARTNER_TINTS[partners[0]]
  if (partners.length === 2) return OVERLAP_TWO_ORGS
  return OVERLAP_THREE_ORGS
}
