/**
 * Drug-quantity caps mirror pharmacy/models.py.DRUG_LIMITS exactly.
 *
 * Any prescription-entry form MUST consume `maxQuantityFor()` to set the
 * `<input type="number" max=...>` attribute AND disable the submit
 * button when `qty > max`. The server enforces the same cap (model +
 * serializer); these constants exist so the UI fails the user fast,
 * before a 400 round-trip.
 *
 * Keep in sync with the backend by reading the Python module on
 * every backend edit — there is no auto-generated bridge.
 */

export type DrugCode =
  | 'metronidazole' | 'doxycycline'
  | 'b_complex' | 'ibuprofen' | 'paracetamol'
  | 'ranitidine' | 'antacid'
  | 'ors'

export type ConditionType = 'STI' | 'GENERAL' | 'SEVERE'

interface DrugCapEntry {
  unit: string
  /** null key = single limit, ignores condition_type. */
  caps: Partial<Record<ConditionType | 'ANY', number>>
}

export const DRUG_LIMITS: Record<DrugCode, DrugCapEntry> = {
  metronidazole: { unit: 'tablets',  caps: { STI: 14, GENERAL: 10 } },
  doxycycline:   { unit: 'capsules', caps: { STI: 20, GENERAL: 10 } },
  b_complex:     { unit: 'tablets',  caps: { ANY: 10 } },
  ibuprofen:     { unit: 'tablets',  caps: { ANY: 10 } },
  paracetamol:   { unit: 'tablets',  caps: { ANY: 10 } },
  ranitidine:    { unit: 'tablets',  caps: { ANY: 10 } },
  antacid:       { unit: 'tablets',  caps: { ANY: 10 } },
  ors:           { unit: 'sachets',  caps: { GENERAL: 3, SEVERE: 5 } },
}

/**
 * Returns the maximum quantity allowed for this (drug, condition) pair,
 * along with the dispense unit. Returns null when the drug code is
 * unknown — caller should treat that as a hard error.
 */
export function maxQuantityFor(
  drug: DrugCode,
  condition: ConditionType,
): { max: number; unit: string } | null {
  const entry = DRUG_LIMITS[drug]
  if (!entry) return null
  if (entry.caps.ANY !== undefined) {
    return { max: entry.caps.ANY, unit: entry.unit }
  }
  // ORS: treat STI as GENERAL/STANDARD (sit-eq).
  let key: ConditionType = condition
  if (drug === 'ors' && condition !== 'GENERAL' && condition !== 'SEVERE') {
    key = 'GENERAL'
  }
  const cap = entry.caps[key]
  return cap !== undefined ? { max: cap, unit: entry.unit } : null
}

/**
 * Photo-upload cap shared by meeting + training reports.
 * Mirrors programs/models/operations.MAX_PHOTO_BYTES.
 */
export const PHOTO_MAX_BYTES = 2 * 1024 * 1024

/** Format-friendly variant. */
export const PHOTO_MAX_LABEL = '2 MiB'
