/**
 * Donor coverage by district, for the two CIPRB maps Dr. Sayeed requested
 * on 27 September 2026 (email: "Request for two District Maps: MPDSR and
 * Fistula Project"):
 *
 *   MPDSR Map (CIPRB-UNFPA supported districts)
 *   End Obstetric Fistula Map (CIPRB-UNFPA supported districts)
 *
 * The lists below are written out district by district, exactly as the email
 * gave them, so the map can be checked against the source without reading the
 * map code. A district may carry more than one donor.
 *
 * One point was resolved when transcribing: the MPDSR table lists Noakhali
 * under SIDA and again under "Common (SIDA+CP)". It is recorded here as
 * SIDA + CP, which is the fuller of the two statements. CONFIRMED by
 * Dr. Tanjina Pervin, RCH CIPRB, 6 October 2026: "Noakhali will be a common
 * district under both SIDA and CP."
 *
 * These lists are the donor split only. They are narrower than the 19 working
 * districts in PARTNER_DISTRICTS.CIPRB (the Kobo form dropdown), which stays
 * the source for programme coverage.
 */
export type Donor = 'GAC' | 'SIDA' | 'CP'
export type DonorProject = 'mpdsr' | 'fistula'

export interface DonorDistrict {
  district: string
  donors: Donor[]
}

export const DONOR_DISTRICTS: Record<DonorProject, DonorDistrict[]> = {
  mpdsr: [
    { district: 'Sherpur', donors: ['GAC'] },
    { district: 'Bhola', donors: ['GAC'] },
    { district: 'Chandpur', donors: ['SIDA'] },
    { district: 'Patuakhali', donors: ['CP'] },
    { district: 'Barguna', donors: ['CP'] },
    { district: 'Bagerhat', donors: ['CP'] },
    { district: 'Gaibandha', donors: ['CP'] },
    { district: 'Jamalpur', donors: ['CP'] },
    { district: 'Sirajganj', donors: ['CP'] },
    { district: 'Sunamganj', donors: ['GAC', 'SIDA'] },
    { district: 'Noakhali', donors: ['SIDA', 'CP'] },
    { district: 'Bandarban', donors: ['SIDA', 'CP'] },
  ],
  fistula: [
    { district: 'Sherpur', donors: ['GAC'] },
    { district: 'Bhola', donors: ['GAC'] },
    { district: 'Kurigram', donors: ['GAC'] },
    { district: 'Khagrachari', donors: ['GAC'] },
    { district: 'Chandpur', donors: ['SIDA'] },
    { district: 'Patuakhali', donors: ['CP'] },
    { district: 'Barguna', donors: ['CP'] },
    { district: 'Bagerhat', donors: ['CP'] },
    { district: 'Gaibandha', donors: ['CP'] },
    { district: 'Jamalpur', donors: ['CP'] },
    { district: 'Sirajganj', donors: ['CP'] },
    { district: 'Sunamganj', donors: ['GAC', 'SIDA'] },
    { district: 'Noakhali', donors: ['SIDA', 'CP'] },
    { district: 'Bandarban', donors: ['SIDA', 'CP'] },
  ],
}

/** The five fills the two maps use, in the UNFPA orange family. Single-donor
 *  districts read as one flat tone each; a shared district takes a tone of its
 *  own rather than a blend, so the legend can name it. */
export const DONOR_TINT: Record<string, string> = {
  'GAC': '#F96000',          // UNFPA primary orange
  'SIDA': '#C44E00',         // UNFPA deep orange
  'CP': '#FDCFB3',           // UNFPA pale tint
  'GAC + SIDA': '#7A2E00',   // deepest, for the one district both fund
  'SIDA + CP': '#FF8A3D',    // light mid orange
}

/** Legend order, darkest-funded first so the eye reads the overlaps first. */
export const DONOR_LEGEND = ['GAC + SIDA', 'SIDA + CP', 'SIDA', 'GAC', 'CP'] as const

/** "GAC + SIDA" from ['GAC','SIDA']; the key used for colour and legend. */
export function donorKey(donors: Donor[]): string {
  const order: Donor[] = ['GAC', 'SIDA', 'CP']
  return order.filter(d => donors.includes(d)).join(' + ')
}

export function donorCounts(project: DonorProject): { donor: string; districts: string[] }[] {
  const out = new Map<string, string[]>()
  for (const row of DONOR_DISTRICTS[project]) {
    const key = donorKey(row.donors)
    out.set(key, [...(out.get(key) ?? []), row.district])
  }
  return DONOR_LEGEND
    .filter(k => out.has(k))
    .map(k => ({ donor: k, districts: (out.get(k) ?? []).sort() }))
}

/** Every donor district across both projects, merged.
 *
 *  The CIPRB partner page shows one coverage map for the whole partnership,
 *  not one per project, so a district carries the union of its donors: the
 *  four GAC districts that only the fistula project adds (Kurigram,
 *  Khagrachhari) count as GAC here too.
 */
export function donorUnion(): DonorDistrict[] {
  const merged = new Map<string, Set<Donor>>()
  for (const project of ['mpdsr', 'fistula'] as DonorProject[]) {
    for (const row of DONOR_DISTRICTS[project]) {
      const set = merged.get(row.district) ?? new Set<Donor>()
      row.donors.forEach(d => set.add(d))
      merged.set(row.district, set)
    }
  }
  return [...merged].map(([district, donors]) => ({
    district,
    donors: (['GAC', 'SIDA', 'CP'] as Donor[]).filter(d => donors.has(d)),
  }))
}

/** Every district this donor funds, across both projects.
 *
 *  A district shared with another donor belongs to BOTH donors' lists, which
 *  is the difference between this and `donorUnionGroups()`: the groups there
 *  are disjoint because a map district can only take one colour, whereas a
 *  filter asking "what does SIDA fund" must include Sunamganj (GAC + SIDA)
 *  and Noakhali (SIDA + CP).
 *
 *  This is the source for the dashboard's donor filter pills. They used to
 *  carry a list hardcoded from the June 2026 Near Miss tool which had gone
 *  stale: it put Patuakhali and Barguna under SIDA when CIPRB funds them
 *  through CP, dropped Sunamganj from SIDA, and had no CP pill at all.
 */
export function districtsForDonor(donor: Donor): string[] {
  return donorUnion()
    .filter(row => row.donors.includes(donor))
    .map(row => row.district)
    .sort()
}

/** The same union as map subgroups: one group per tint, groups disjoint.
 *
 *  A district funded by two donors sits in its own group ("GAC + SIDA")
 *  rather than in both single-donor groups, so every district takes exactly
 *  one colour and the legend counts add up to the districts on the map.
 */
export function donorUnionGroups(): { name: string; color: string; districts: string[] }[] {
  const byKey = new Map<string, string[]>()
  for (const row of donorUnion()) {
    const k = donorKey(row.donors)
    byKey.set(k, [...(byKey.get(k) ?? []), row.district])
  }
  return DONOR_LEGEND
    .filter(k => byKey.has(k))
    .map(k => ({
      name: k,
      color: DONOR_TINT[k],
      districts: (byKey.get(k) ?? []).sort(),
    }))
}
