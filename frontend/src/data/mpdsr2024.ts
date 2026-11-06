/**
 * MPDSR 2024 community death-review data — all 64 districts.
 *
 * Source: "National MPDSR in Bangladesh — Progress and Highlights: 2019 to
 * 2024" (CIPRB/UNFPA/UNICEF/WHO/DGHS), published December 2025.
 *   • Table 1 — Community Maternal Death (printed pp.9–10): 1,897 notified
 *   • Table 2 — Community Neonatal Death (printed pp.11–12): 8,189 notified
 * These are the community-notification tables Animesh referenced (pp.9–12).
 *
 * Keys are the EXACT district names in public/bangladesh-adm2.geojson. The
 * districts whose report spelling differs from the geojson are reconciled
 * here at data-entry time (e.g. report "Borguna" → geojson "Barguna",
 * "Chapai Nababganj" → "Nawabganj", "Maulavi Bazar" → "Maulvibazar").
 * Percentages are stored exactly as printed (the report's own rounding).
 */

export type Metric = 'maternal' | 'neonatal'
export type Indicator = 'notified' | 'reviewed' | 'pct'

export type Division =
  | 'Barishal' | 'Chattogram' | 'Dhaka' | 'Khulna'
  | 'Mymensingh' | 'Rajshahi' | 'Rangpur' | 'Sylhet'

export interface Counts { notified: number; reviewed: number; pct: number }
export interface DistrictRow {
  district: string        // matches geojson shapeName exactly
  division: Division
  maternal: Counts
  neonatal: Counts
}

const c = (notified: number, reviewed: number, pct: number): Counts => ({ notified, reviewed, pct })

export const MPDSR_2024: DistrictRow[] = [
  { district: 'Bagerhat',      division: 'Khulna',     maternal: c(34, 14, 41), neonatal: c(87, 38, 44) },
  { district: 'Bandarban',     division: 'Chattogram', maternal: c(5, 1, 20),   neonatal: c(8, 1, 13) },
  { district: 'Barguna',       division: 'Barishal',   maternal: c(35, 16, 46), neonatal: c(46, 32, 70) },
  { district: 'Barisal',       division: 'Barishal',   maternal: c(31, 7, 23),  neonatal: c(136, 18, 13) },
  { district: 'Bhola',         division: 'Barishal',   maternal: c(41, 15, 37), neonatal: c(166, 69, 42) },
  { district: 'Bogra',         division: 'Rajshahi',   maternal: c(18, 15, 83), neonatal: c(46, 34, 74) },
  { district: 'Brahamanbaria', division: 'Chattogram', maternal: c(36, 7, 19),  neonatal: c(160, 21, 13) },
  { district: 'Chandpur',      division: 'Chattogram', maternal: c(16, 0, 0),   neonatal: c(151, 1, 1) },
  { district: 'Chittagong',    division: 'Chattogram', maternal: c(107, 1, 1),  neonatal: c(545, 3, 1) },
  { district: 'Chuadanga',     division: 'Khulna',     maternal: c(10, 0, 0),   neonatal: c(33, 0, 0) },
  { district: 'Comilla',       division: 'Chattogram', maternal: c(87, 80, 92), neonatal: c(331, 277, 84) },
  { district: "Cox's Bazar",   division: 'Chattogram', maternal: c(31, 5, 16),  neonatal: c(85, 21, 25) },
  { district: 'Dhaka',         division: 'Dhaka',      maternal: c(47, 11, 23), neonatal: c(276, 69, 25) },
  { district: 'Dinajpur',      division: 'Rangpur',    maternal: c(54, 1, 2),   neonatal: c(378, 10, 3) },
  { district: 'Faridpur',      division: 'Dhaka',      maternal: c(4, 0, 0),    neonatal: c(60, 1, 2) },
  { district: 'Feni',          division: 'Chattogram', maternal: c(42, 1, 2),   neonatal: c(39, 3, 8) },
  { district: 'Gaibandha',     division: 'Rangpur',    maternal: c(40, 14, 35), neonatal: c(157, 22, 14) },
  { district: 'Gazipur',       division: 'Dhaka',      maternal: c(31, 21, 68), neonatal: c(197, 103, 52) },
  { district: 'Gopalganj',     division: 'Dhaka',      maternal: c(13, 4, 31),  neonatal: c(8, 3, 38) },
  { district: 'Habiganj',      division: 'Sylhet',     maternal: c(51, 5, 10),  neonatal: c(271, 35, 13) },
  { district: 'Jamalpur',      division: 'Mymensingh', maternal: c(41, 5, 12),  neonatal: c(185, 15, 8) },
  { district: 'Jessore',       division: 'Khulna',     maternal: c(39, 13, 33), neonatal: c(145, 28, 19) },
  { district: 'Jhalokati',     division: 'Barishal',   maternal: c(7, 1, 14),   neonatal: c(34, 1, 3) },
  { district: 'Jhenaidah',     division: 'Khulna',     maternal: c(4, 2, 50),   neonatal: c(22, 3, 14) },
  { district: 'Joypurhat',     division: 'Rajshahi',   maternal: c(7, 1, 14),   neonatal: c(33, 7, 21) },
  { district: 'Khagrachhari',  division: 'Chattogram', maternal: c(5, 0, 0),    neonatal: c(13, 3, 23) },
  { district: 'Khulna',        division: 'Khulna',     maternal: c(17, 7, 41),  neonatal: c(94, 17, 18) },
  { district: 'Kishoreganj',   division: 'Dhaka',      maternal: c(53, 16, 30), neonatal: c(139, 73, 53) },
  { district: 'Kurigram',      division: 'Rangpur',    maternal: c(63, 36, 57), neonatal: c(270, 139, 51) },
  { district: 'Kushtia',       division: 'Khulna',     maternal: c(33, 9, 27),  neonatal: c(145, 8, 6) },
  { district: 'Lakshmipur',    division: 'Chattogram', maternal: c(28, 2, 7),   neonatal: c(72, 1, 1) },
  { district: 'Lalmonirhat',   division: 'Rangpur',    maternal: c(37, 18, 49), neonatal: c(418, 22, 5) },
  { district: 'Madaripur',     division: 'Dhaka',      maternal: c(10, 0, 0),   neonatal: c(15, 0, 0) },
  { district: 'Magura',        division: 'Khulna',     maternal: c(15, 0, 0),   neonatal: c(86, 0, 0) },
  { district: 'Manikganj',     division: 'Dhaka',      maternal: c(19, 0, 0),   neonatal: c(53, 1, 2) },
  { district: 'Maulvibazar',   division: 'Sylhet',     maternal: c(60, 5, 8),   neonatal: c(226, 12, 5) },
  { district: 'Meherpur',      division: 'Khulna',     maternal: c(12, 2, 17),  neonatal: c(26, 4, 15) },
  { district: 'Munshiganj',    division: 'Dhaka',      maternal: c(10, 1, 10),  neonatal: c(47, 5, 11) },
  { district: 'Mymensingh',    division: 'Mymensingh', maternal: c(40, 3, 8),   neonatal: c(270, 5, 2) },
  { district: 'Naogaon',       division: 'Rajshahi',   maternal: c(8, 1, 13),   neonatal: c(27, 1, 4) },
  { district: 'Narail',        division: 'Khulna',     maternal: c(8, 7, 88),   neonatal: c(93, 9, 10) },
  { district: 'Narayanganj',   division: 'Dhaka',      maternal: c(11, 0, 0),   neonatal: c(24, 0, 0) },
  { district: 'Narsingdi',     division: 'Dhaka',      maternal: c(21, 6, 29),  neonatal: c(55, 8, 15) },
  { district: 'Natore',        division: 'Rajshahi',   maternal: c(5, 0, 0),    neonatal: c(190, 1, 1) },
  { district: 'Nawabganj',     division: 'Rajshahi',   maternal: c(46, 1, 2),   neonatal: c(93, 1, 1) },
  { district: 'Netrakona',     division: 'Mymensingh', maternal: c(41, 3, 7),   neonatal: c(205, 15, 7) },
  { district: 'Nilphamari',    division: 'Rangpur',    maternal: c(10, 5, 50),  neonatal: c(47, 0, 0) },
  { district: 'Noakhali',      division: 'Chattogram', maternal: c(23, 20, 87), neonatal: c(284, 73, 26) },
  { district: 'Pabna',         division: 'Rajshahi',   maternal: c(11, 3, 27),  neonatal: c(53, 8, 15) },
  { district: 'Panchagarh',    division: 'Rangpur',    maternal: c(8, 4, 50),   neonatal: c(50, 25, 50) },
  { district: 'Patuakhali',    division: 'Barishal',   maternal: c(21, 4, 19),  neonatal: c(141, 22, 16) },
  { district: 'Pirojpur',      division: 'Barishal',   maternal: c(3, 0, 0),    neonatal: c(13, 0, 0) },
  { district: 'Rajbari',       division: 'Dhaka',      maternal: c(8, 1, 13),   neonatal: c(17, 0, 0) },
  { district: 'Rajshahi',      division: 'Rajshahi',   maternal: c(51, 0, 0),   neonatal: c(53, 8, 15) },
  { district: 'Rangamati',     division: 'Chattogram', maternal: c(10, 1, 10),  neonatal: c(20, 1, 5) },
  { district: 'Rangpur',       division: 'Rangpur',    maternal: c(29, 7, 24),  neonatal: c(99, 20, 20) },
  { district: 'Satkhira',      division: 'Khulna',     maternal: c(20, 13, 65), neonatal: c(137, 81, 59) },
  { district: 'Shariatpur',    division: 'Dhaka',      maternal: c(14, 1, 7),   neonatal: c(72, 1, 1) },
  { district: 'Sherpur',       division: 'Mymensingh', maternal: c(72, 30, 42), neonatal: c(86, 72, 84) },
  { district: 'Sirajganj',     division: 'Rajshahi',   maternal: c(64, 59, 92), neonatal: c(375, 355, 95) },
  { district: 'Sunamganj',     division: 'Sylhet',     maternal: c(91, 35, 38), neonatal: c(228, 78, 34) },
  { district: 'Sylhet',        division: 'Sylhet',     maternal: c(40, 8, 20),  neonatal: c(161, 32, 20) },
  { district: 'Tangail',       division: 'Dhaka',      maternal: c(38, 15, 39), neonatal: c(168, 18, 11) },
  { district: 'Thakurgaon',    division: 'Rangpur',    maternal: c(11, 1, 9),   neonatal: c(25, 3, 12) },
]

export const MPDSR_YEAR = 2024
export const MPDSR_SOURCE =
  'National MPDSR Report 2019–2024 (DGHS/CIPRB/UNFPA, publ. Dec 2025) · community death review, 2024'

// National totals as printed in the report (for captions / validation).
export const MPDSR_TOTALS = {
  maternal: { notified: 1897, reviewed: 564,  pct: 30 },
  neonatal: { notified: 8189, reviewed: 1937, pct: 24 },
}

export const DIVISIONS: Division[] = [
  'Barishal', 'Chattogram', 'Dhaka', 'Khulna',
  'Mymensingh', 'Rajshahi', 'Rangpur', 'Sylhet',
]

/** Per-district value for a metric+indicator, keyed by geojson shapeName. */
export function districtValues(metric: Metric, indicator: Indicator): Record<string, number> {
  const out: Record<string, number> = {}
  for (const r of MPDSR_2024) out[r.district] = r[metric][indicator]
  return out
}

/** division → its districts (geojson names). */
export function districtsByDivision(): Record<Division, string[]> {
  const out = {} as Record<Division, string[]>
  for (const d of DIVISIONS) out[d] = []
  for (const r of MPDSR_2024) out[r.division].push(r.district)
  return out
}

/** Division-level aggregate. notified/reviewed → sum; pct → reviewed/notified
 *  across the division (a true division rate, not a mean of district %s). */
export function divisionValues(metric: Metric, indicator: Indicator): Record<Division, number> {
  const sums = {} as Record<Division, { n: number; r: number }>
  for (const d of DIVISIONS) sums[d] = { n: 0, r: 0 }
  for (const row of MPDSR_2024) {
    sums[row.division].n += row[metric].notified
    sums[row.division].r += row[metric].reviewed
  }
  const out = {} as Record<Division, number>
  for (const d of DIVISIONS) {
    if (indicator === 'notified') out[d] = sums[d].n
    else if (indicator === 'reviewed') out[d] = sums[d].r
    else out[d] = sums[d].n > 0 ? Math.round((sums[d].r / sums[d].n) * 100) : 0
  }
  return out
}

/** For a district (geojson name), the division it belongs to. */
export function divisionOfDistrict(): Record<string, Division> {
  const out: Record<string, Division> = {}
  for (const r of MPDSR_2024) out[r.district] = r.division
  return out
}
