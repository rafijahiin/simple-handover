/**
 * CIPRB Dashboard — unified partner page for CIPRB, mirroring the
 * structure of /phd and /bondhu but composing CIPRB-owned surveillance
 * surfaces:
 *
 *   1. Fistula KPI band     (Suspected / Identified / Referred / Surgery Done)
 *   2. Fistula registers    (Corner + Campaign tabs)
 *   3. MPDSR surveillance   (cause panels, place pills, overdue, cases table)
 *
 * Baseline Assessment lives at /baseline so it isn't repeated here.
 *
 * Per Animesh: "MPDSR and Fistula will be in one page. It will be named
 * CIPRB Dashboard, like the other two orgs."
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ClipboardList, Search, Stethoscope, Send, Scissors,
  Clock, MapPin, X, AlertTriangle, HeartHandshake, Info,
} from 'lucide-react'
import { api } from '@/api/client'
import { usePolling } from '@/hooks/usePolling'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { formatDate, formatDateTime } from '@/utils/format'
import { districtsForDonor } from '@/data/donorDistricts'
import { SourceChip } from '@/components/ui/SourceChip'
import { FistulaVisualizations } from '@/components/ciprb/FistulaVisualizations'
import { MPDSRVisualizations } from '@/components/ciprb/MPDSRVisualizations'
import { ActionPlanTracker } from '@/components/ciprb/ActionPlanTracker'
import { NearMissPanel } from '@/components/ciprb/NearMissPanel'
import { SafeSurgeryPanel } from '@/components/ciprb/SafeSurgeryPanel'
import { FistulaIndicators } from '@/components/ciprb/FistulaIndicators'
import { MPDSRDistrictMap } from '@/components/ciprb/MPDSRDistrictMap'
import { DonorMapSheet } from '@/components/ciprb/DonorMapSheet'
import { DataUnavailable } from '@/components/ciprb/DataUnavailable'
import type { MPDSRCase, AuditEntry } from '@/types/index'

// UNFPA branding — every CIPRB page uses UNFPA orange. Partner identity
// comes from the page header / route, not from colour.
const CIPRB_BLUE = '#F96000'

const CAUSE_KEYS = ['pph', 'eclampsia', 'sepsis', 'obstructed_labour', 'other'] as const
const PLACE_KEYS = ['facility', 'home', 'in_transit'] as const

// Reporting period presets — default is the contract window per Animesh.
// Annual cycle is for September annual-reporting needs on MPDSR + Fistula.
// TODO: wire to backend query params (date_from / date_to) in a follow-up.
type ReportingPeriodKey = 'contract' | 'annual'

interface ReportingPeriodDef {
  key: ReportingPeriodKey
  // TODO BN: add Bangla translations via i18n keys when copy is finalised
  shortLabel: string  // pill label
  rangeLabel: string  // human-readable range
  from: string        // ISO date
  to: string          // ISO date
}

const REPORTING_PERIODS: ReportingPeriodDef[] = [
  {
    key: 'contract',
    shortLabel: 'Contract',
    rangeLabel: '21 May 2026 → 20 Nov 2026',
    from: '2026-05-21',
    to: '2026-11-20',
  },
]

// ─── Fistula KPI helpers ─────────────────────────────────────────────────────

interface KPIs {
  suspected: number
  identified: number
  referred: number
  surgeryDone: number
  rehabilitated: number
  rehabPct: number | null
}

function useFistulaKPIs(
  period: ReportingPeriodDef,
  districtFilter: readonly string[] | null,
): { kpis: KPIs; loading: boolean; error: boolean; retry: () => void } {
  const [kpis, setKpis] = useState<KPIs>({ suspected: 0, identified: 0, referred: 0, surgeryDone: 0, rehabilitated: 0, rehabPct: null })
  const [loading, setLoading] = useState(true)
  // A fetch failure — or a 200 whose body is missing the `pipeline` key — must
  // not render as an all-zero KPI band that looks like a real empty programme.
  const [error, setError] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const periodFrom = period.from
  const periodTo = period.to
  const districtsKey = districtFilter ? districtFilter.join(',') : ''

  useEffect(() => {
    let cancelled = false
    setError(false)
    const params: Record<string, string> = { from: periodFrom, to: periodTo }
    if (districtsKey) params.districts = districtsKey
    // The At-a-glance KPI band reads ONLY the monotonic CIPRBFistulaCase
    // pipeline (the canonical CIPRB source). The legacy/demo fallback
    // (campaign-visits / corner-cases / cases roll-ups, seeded by
    // seed_demo_fistula) has been dropped: when the registry is empty every
    // stage is 0 and the band shows zeros instead of fake seed numbers.
    api.get<{ pipeline?: Record<string, number> }>('/fistula/aggregates/', { params })
      .then((aggRes) => {
        if (cancelled) return
        const pipeline = aggRes.data.pipeline
        // Absent key = malformed/partial response, NOT an empty programme (an
        // empty registry still returns pipeline with zero stages). Treat as error.
        if (pipeline == null) {
          setError(true)
          setLoading(false)
          return
        }
        const suspected     = pipeline.suspected     ?? 0
        const identified    = pipeline.diagnosed     ?? 0
        const referred      = pipeline.referred      ?? 0
        const surgeryDone   = pipeline.repaired      ?? 0
        const rehabilitated = pipeline.rehabilitated ?? 0
        // Rehab % uses the previous stage (repaired) as denominator.
        const rehabPct = surgeryDone > 0 ? (rehabilitated / surgeryDone) * 100 : null

        setKpis({ suspected, identified, referred, surgeryDone, rehabilitated, rehabPct })
        setLoading(false)
      })
      .catch(() => { if (!cancelled) { setError(true); setLoading(false) } })
    return () => { cancelled = true }
  }, [periodFrom, periodTo, districtsKey, reloadKey])

  return { kpis, loading, error, retry: () => setReloadKey((k) => k + 1) }
}

function KPITile({
  icon, label, sub, value, pct, pctLabel, pct2, pct2Label,
}: {
  icon: React.ReactNode
  label: string
  sub: string
  value: number | string
  pct?: number | null
  pctLabel?: string
  pct2?: number | null
  pct2Label?: string
}) {
  return (
    <div
      className="card"
      style={{
        padding: '16px 18px',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
      }}
    >
      <div style={{
        display: 'inline-flex', alignItems: 'center', gap: 8,
        fontSize: 11, color: 'var(--muted)',
        textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 500,
      }}>
        <span style={{
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: 24, height: 24, borderRadius: 6,
          background: `${CIPRB_BLUE}1A`, color: CIPRB_BLUE,
        }}>
          {icon}
        </span>
        {label}
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <div style={{
          fontSize: 30, fontWeight: 800, color: 'var(--ink)',
          fontVariantNumeric: 'tabular-nums', lineHeight: 1, letterSpacing: '-0.02em',
        }}>
          {typeof value === 'number' ? value.toLocaleString() : value}
        </div>
        {pct != null && (
          <span style={{
            fontSize: 12, fontWeight: 700, color: CIPRB_BLUE,
            background: `${CIPRB_BLUE}14`, borderRadius: 999, padding: '2px 9px',
            fontVariantNumeric: 'tabular-nums',
          }}>
            {Math.round(pct)}%{pctLabel ? ` ${pctLabel}` : ''}
          </span>
        )}
        {pct2 != null && (
          <span style={{
            fontSize: 12, fontWeight: 700, color: CIPRB_BLUE,
            border: `1px solid ${CIPRB_BLUE}55`, borderRadius: 999, padding: '1px 9px',
            fontVariantNumeric: 'tabular-nums',
          }}>
            {Math.round(pct2)}%{pct2Label ? ` ${pct2Label}` : ''}
          </span>
        )}
      </div>
      <div style={{ fontSize: 12, color: 'var(--ink-3)' }}>{sub}</div>
    </div>
  )
}

// Placeholder variant of KPITile — value is rendered as an em-dash and the
// whole tile uses muted colour + softer surface so it visually reads as
// "metric is on the roadmap, definition pending" rather than "we have data".
function PendingKPITile({
  icon, label, sub,
}: {
  icon: React.ReactNode
  label: string
  sub: string
}) {
  return (
    <div
      className="card"
      style={{
        padding: '16px 18px',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        background: 'var(--surface-2)',
        borderStyle: 'dashed',
      }}
      aria-label={`${label} — definition pending`}
    >
      <div style={{
        display: 'inline-flex', alignItems: 'center', gap: 8,
        fontSize: 11, color: 'var(--muted)',
        textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 500,
      }}>
        <span style={{
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: 24, height: 24, borderRadius: 6,
          background: 'var(--surface-3)', color: 'var(--muted)',
        }}>
          {icon}
        </span>
        {label}
      </div>
      <div style={{
        fontSize: 30, fontWeight: 800, color: 'var(--muted)',
        fontVariantNumeric: 'tabular-nums', lineHeight: 1, letterSpacing: '-0.02em',
      }}>
        —
      </div>
      <div style={{ fontSize: 12, color: 'var(--muted)', fontStyle: 'italic' }}>{sub}</div>
    </div>
  )
}

// ─── MPDSR audit drawer ──────────────────────────────────────────────────────

function pascal(k: string): string {
  return k.split('_').map(p => p[0].toUpperCase() + p.slice(1)).join('')
}

function MPDSRAuditDrawer({ kase, onClose }: { kase: MPDSRCase; onClose: () => void }) {
  const { t } = useTranslation()
  const placeLabel = (k: string) => t(`mpdsr.place${pascal(k)}`, { defaultValue: k })

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 50,
        display: 'flex', justifyContent: 'flex-end',
        background: 'rgba(0,0,0,0.4)',
        backdropFilter: 'blur(8px)',
        WebkitBackdropFilter: 'blur(8px)',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          height: '100%', width: '100%', maxWidth: 440,
          overflowY: 'auto',
          background: 'var(--surface)',
          borderLeft: '1px solid var(--hair)',
          boxShadow: 'var(--sh-3)',
        }}
      >
        <div style={{
          position: 'sticky', top: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '16px 20px',
          background: 'var(--surface)',
          borderBottom: '1px solid var(--hair)',
          zIndex: 1,
        }}>
          <div>
            <h2 style={{ fontWeight: 700, color: 'var(--ink)', fontSize: 15, margin: 0 }}>
              {t('mpdsr.drawerAuditTrail')}
            </h2>
            <p style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>
              {t('mpdsr.drawerCase')} {kase.case_hash.slice(0, 8)}…
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            style={{
              width: 32, height: 32, borderRadius: 999,
              background: 'var(--surface-2)',
              border: '1px solid var(--hair)',
              color: 'var(--ink-3)', cursor: 'pointer',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            }}
          >
            <X size={14} />
          </button>
        </div>

        <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="card" style={{ padding: 16, background: 'var(--surface-2)', fontSize: 13 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <SummaryRow label={t('mpdsr.drawerForm')} value={kase.sub_form_label || kase.sub_form_type} span={2} />
              <SummaryRow label={t('mpdsr.drawerType')} value={kase.death_type_display} />
              <SummaryRow label={t('mpdsr.drawerPlace')} value={placeLabel(kase.place_of_death)} />
              <SummaryRow label={t('mpdsr.drawerDistrict')} value={kase.district} />
              {kase.upazila && <SummaryRow label={t('mpdsr.drawerUpazila')} value={kase.upazila} />}
              {kase.facility_name && <SummaryRow label={t('mpdsr.drawerFacility')} value={kase.facility_name} span={2} />}
              <SummaryRow label={t('mpdsr.drawerDateOfDeath')} value={formatDate(kase.date_of_death) || '—'} />
              {kase.age_years != null && (
                <SummaryRow label={t('mpdsr.drawerAge')} value={t('mpdsr.drawerAgeYears', { years: kase.age_years })} />
              )}
              {kase.cause_of_death && (
                <SummaryRow label={t('mpdsr.drawerCause')} value={kase.cause_of_death.replace(/ /g, ', ')} span={2} />
              )}
            </div>
          </div>

          <div>
            <div className="kicker" style={{ marginBottom: 12 }}>
              <span className="dot" />{t('mpdsr.drawerTimeline')}
            </div>
            {(kase.audit_trail ?? []).length === 0 && (
              <p style={{ fontSize: 13, color: 'var(--muted)' }}>{t('mpdsr.drawerNoAudit')}</p>
            )}
            <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', gap: 16 }}>
              <span aria-hidden style={{
                position: 'absolute', left: 15, top: 6, bottom: 6,
                width: 1, background: 'var(--hair-2)',
              }} />
              {(kase.audit_trail ?? []).map((entry: AuditEntry, i: number) => (
                <div key={i} style={{ display: 'flex', gap: 14, paddingLeft: 36, position: 'relative' }}>
                  <span style={{
                    position: 'absolute', left: 10, top: 6,
                    height: 11, width: 11, borderRadius: 999,
                    background: CIPRB_BLUE,
                    boxShadow: '0 0 0 2px var(--surface)',
                  }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
                      <p style={{ fontSize: 13, fontWeight: 500, color: 'var(--ink)', margin: 0 }}>
                        {entry.action}
                      </p>
                      <span style={{
                        flexShrink: 0,
                        display: 'inline-flex', alignItems: 'center', gap: 4,
                        fontSize: 10, color: 'var(--muted)',
                      }}>
                        <Clock size={11} />
                        {formatDateTime(entry.timestamp)}
                      </span>
                    </div>
                    <p style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 2 }}>{entry.user}</p>
                    {entry.notes && (
                      <p style={{ marginTop: 4, fontSize: 12, color: 'var(--ink-3)', fontStyle: 'italic' }}>
                        {entry.notes}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function SummaryRow({ label, value, span = 1 }: { label: string; value: string; span?: 1 | 2 }) {
  return (
    <div style={{ gridColumn: span === 2 ? 'span 2' : undefined }}>
      <p style={{ fontSize: 11, color: 'var(--muted)', margin: 0 }}>{label}</p>
      <p style={{
        fontSize: 13, fontWeight: 500, color: 'var(--ink)', marginTop: 2,
        wordBreak: 'break-word',
      }}>{value}</p>
    </div>
  )
}

// ─── MPDSR section ───────────────────────────────────────────────────────────

type CauseFilter = 'all' | string

function MPDSRSection({
  period,
  districts,
}: {
  period: ReportingPeriodDef
  districts: readonly string[] | null
}) {
  const { t } = useTranslation()
  const [causeFilter, setCauseFilter] = useState<CauseFilter>('all')
  const [selectedCase, setSelectedCase] = useState<MPDSRCase | null>(null)
  const districtsKey = districts ? districts.join(',') : ''

  const { data: cases, loading } = usePolling<MPDSRCase[]>({
    fetcher: () =>
      api
        .get('/mpdsr/cases/', {
          params: {
            ...(causeFilter !== 'all' ? { cause_of_death: causeFilter } : {}),
            ...(districtsKey ? { districts: districtsKey } : {}),
            from: period.from,
            to: period.to,
          },
        })
        .then((r) => (Array.isArray(r.data) ? r.data : r.data.results ?? [])),
    interval: 60_000,
    // Re-fetch when the reporting period or donor filter changes so the
    // cases table and counts re-derive against the selected window.
    deps: [causeFilter, period.from, period.to, districtsKey],
  })

  const causeCounts: Record<string, number> = {}
  const placeCounts: Record<string, number> = {}
  for (const c of cases ?? []) {
    causeCounts[c.cause_of_death] = (causeCounts[c.cause_of_death] ?? 0) + 1
    placeCounts[c.place_of_death] = (placeCounts[c.place_of_death] ?? 0) + 1
  }
  const overdueCount = (cases ?? []).filter(c => c.is_overdue_committee).length

  const causeLabel = (k: string) => t(`mpdsr.cause${pascal(k)}`, { defaultValue: k })
  const placeLabel = (k: string) => t(`mpdsr.place${pascal(k)}`, { defaultValue: k })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Section header */}
      <div>
        <div className="kicker" style={{ marginBottom: 6 }}>
          <span className="dot" style={{ background: CIPRB_BLUE }} />
          {t('mpdsr.eyebrow', { defaultValue: 'TRACKER · MPDSR' })}
        </div>
        {/* One title, not three stacked restatements of "MPDSR". */}
        <h2 className="section-title" style={{ margin: 0 }}>
          {t('mpdsr.subtitle', { defaultValue: 'Maternal & Perinatal Death tracker' })}
        </h2>

        {/* Overdue-committee-reviews badge removed per Rafi, 4 Aug 2026 —
            the tracker page carries the operational chase list. */}
      </div>

      {/* ─── Geographic coverage map (SIDA / GAC / CP highlight) ─── */}
      <div>
        <MPDSRDistrictMap districts={districts} project="mpdsr" />
      </div>

      {/* ─── Visualizations: Notify vs Review · Cause breakdown · Response Plan ─── */}
      <MPDSRVisualizations cases={cases ?? []} period={{ from: period.from, to: period.to }} districts={districts} />

      {/* Cause panels REMOVED per Rafi 2026-06-02 — Maternal Causes pie
          inside MPDSRVisualizations already shows the same breakdown with
          ICD-10 buckets; these duplicate cards were redundant. */}
      {false && (
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
        gap: 12,
      }}>
        {CAUSE_KEYS.map((key) => {
          const active = causeFilter === key
          return (
            <button
              key={key}
              onClick={() => setCauseFilter(active ? 'all' : key)}
              className="card"
              style={{
                padding: 16,
                textAlign: 'left',
                cursor: 'pointer',
                background: active ? 'rgba(249,96,0,0.08)' : 'var(--surface)',
                borderColor: active ? CIPRB_BLUE : 'var(--hair)',
                transition: 'border-color var(--dur-q), background var(--dur-q)',
              }}
            >
              <div style={{
                fontSize: 26, fontWeight: 700, color: 'var(--ink)',
                fontVariantNumeric: 'tabular-nums', lineHeight: 1,
              }}>
                {causeCounts[key] ?? 0}
              </div>
              <div style={{
                fontSize: 11.5, color: 'var(--muted)', marginTop: 4,
                letterSpacing: '0.02em',
              }}>
                {causeLabel(key)}
              </div>
            </button>
          )
        })}
      </div>

      )}
      {/* Place pills REMOVED — Animesh's 2026-06-02 spec keeps the page
          focused on the MPDSR funnel + Response Plan. Place-of-death is
          a drill-down field on the case audit drawer, not a dashboard tile. */}

      {/* Cases table — collapsed by default so the page isn't too long to scroll */}
      {loading && !cases ? (
        <PageLoader />
      ) : (
        <details style={{
          border: '1px solid var(--hair)', borderRadius: 12,
          background: 'var(--surface)',
        }}>
          <summary style={{
            padding: '14px 18px', cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            fontWeight: 600, fontSize: 14, color: 'var(--ink)',
            listStyle: 'none',
          }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10 }}>
              <ClipboardList size={16} color={CIPRB_BLUE} />
              {t('ciprbExtras.rawMpdsr')}
              <span style={{
                marginLeft: 6,
                fontSize: 11, color: 'var(--muted)', fontWeight: 500,
                fontVariantNumeric: 'tabular-nums',
              }}>
                ({t('ciprbExtras.casesCount', { count: (cases ?? []).length })})
              </span>
            </span>
            <span style={{ fontSize: 11, color: 'var(--muted)', letterSpacing: '0.06em' }}>
              {t('ciprbExtras.clickToExpand')}
            </span>
          </summary>
          <div style={{ overflowX: 'auto', borderTop: '1px solid var(--hair)' }}>
            <table className="tbl">
              <thead>
                <tr>
                  {[
                    t('mpdsr.thCaseId'),
                    t('mpdsr.thForm'),
                    t('mpdsr.thDistrict'),
                    t('mpdsr.thDate'),
                    t('mpdsr.thType'),
                    t('mpdsr.thStatus'),
                    t('mpdsr.thAudit'),
                  ].map((h) => (<th key={h}>{h}</th>))}
                </tr>
              </thead>
              <tbody>
                {(cases ?? []).map((c) => (
                  <tr
                    key={c.id}
                    style={c.is_overdue_committee
                      ? { background: 'rgba(204,106,0,0.08)' }
                      : undefined}
                  >
                    <td>
                      <span className="mono" style={{ fontSize: 11.5, color: 'var(--muted)' }}>
                        {c.case_hash.slice(0, 12)}…
                      </span>
                    </td>
                    <td style={{
                      maxWidth: 160, overflow: 'hidden',
                      textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      color: 'var(--ink-3)', fontSize: 12.5,
                    }} title={c.sub_form_label}>
                      {c.sub_form_label || c.sub_form_type || '—'}
                    </td>
                    <td>
                      <span style={{
                        display: 'inline-flex', alignItems: 'center', gap: 4,
                        color: 'var(--ink-3)',
                      }}>
                        <MapPin size={12} style={{ color: 'var(--muted)' }} />
                        {c.district}{c.upazila ? `, ${c.upazila}` : ''}
                      </span>
                    </td>
                    <td style={{ color: 'var(--ink-3)' }}>{formatDate(c.date_of_death)}</td>
                    <td style={{ color: 'var(--ink-3)' }}>{c.death_type_display}</td>
                    <td><StatusBadge status={c.status} /></td>
                    <td>
                      <button
                        onClick={() => setSelectedCase(c)}
                        style={{
                          fontSize: 12, fontWeight: 500,
                          color: CIPRB_BLUE,
                          background: 'transparent', border: 'none',
                          padding: 0, cursor: 'pointer',
                          textDecoration: 'underline', textUnderlineOffset: 2,
                        }}
                      >
                        {t('mpdsr.view')} ({(c.audit_trail ?? []).length})
                      </button>
                    </td>
                  </tr>
                ))}
                {(cases ?? []).length === 0 && (
                  <tr>
                    <td colSpan={7} style={{
                      textAlign: 'center',
                      padding: '48px 16px',
                      fontSize: 13, color: 'var(--muted)',
                    }}>
                      {t('mpdsr.empty')}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </details>
      )}

      {selectedCase && (
        <MPDSRAuditDrawer kase={selectedCase} onClose={() => setSelectedCase(null)} />
      )}
    </div>
  )
}

// ─── Main page ───────────────────────────────────────────────────────────────

// Donor filter — Animesh asked for one-click GAC and SIDA pills.
// Districts confirmed by Rafi 2026-06-02 (override Sayed's earlier
// 3-district mention in meeting minutes).
// Derived from donorDistricts.ts, the list Dr. Sayeed supplied on 27
// September 2026, so the pills and the maps can never disagree. The list
// hardcoded here before came from the June 2026 Near Miss tool and had gone
// stale three ways: Patuakhali and Barguna sat under SIDA when CP funds
// them, Sunamganj was missing from SIDA, and CP had no pill at all despite
// funding six districts. Because the pills filter every figure below them,
// that was wrong data and not only a wrong colour.
const DONOR_FILTERS = {
  all:  { label: 'All',  districts: null as string[] | null },
  GAC:  { label: 'GAC',  districts: districtsForDonor('GAC') },
  SIDA: { label: 'SIDA', districts: districtsForDonor('SIDA') },
  CP:   { label: 'CP',   districts: districtsForDonor('CP') },
} as const
type DonorKey = keyof typeof DONOR_FILTERS

export default function CIPRBDashboard() {
  const { t } = useTranslation()
  const [donorKey, setDonorKey] = useState<DonorKey>('all')
  // Reporting-period selector retired — everything reports on the contract
  // window. activePeriod is fixed to that window so downstream filters still
  // receive a from/to range.
  const activePeriod = REPORTING_PERIODS.find((p) => p.key === 'contract')!
  const activeDonor = DONOR_FILTERS[donorKey]
  const { kpis, error: kpisError, retry: retryKpis } = useFistulaKPIs(activePeriod, activeDonor.districts)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 40 }}>
      {/* ───────────────── Hero ───────────────── */}
      <section className="hero" style={{ paddingBottom: 8 }}>
        {/* Same eyebrow structure as /phd and /bondhu: role / full name /
            month / demo pill — identical typography across all partners. */}
        <div className="hero-eyebrow anim-rise">
          <span className="live-dot" />
          <span>{t('org.eyebrowImplementingPartner', { defaultValue: 'IMPLEMENTING PARTNER' })}</span>
          <span className="sep">/</span>
          <span>Centre for Injury Prevention and Research, Bangladesh</span>
          <span className="sep">/</span>
          <span>{new Date().toLocaleString('en-US', { month: 'long', year: 'numeric' }).toUpperCase()}</span>
        </div>

        <div className="hero-grid">
          <div>
            {/* Identical treatment to /phd and /bondhu — UNFPA orange italic
                display serif via .figure. Only the text differs per partner. */}
            <h1
              className="hero-headline anim-rise d1"
              style={{
                marginBottom: 6,
                fontSize: 'clamp(56px, 9vw, 132px)',
                letterSpacing: '-0.035em',
              }}
            >
              <span className="figure">CIPRB</span>
            </h1>
            <p style={{
              fontSize: 13, color: 'var(--ink-3)', marginTop: 4, marginBottom: 14,
              letterSpacing: '0.01em', fontWeight: 500,
            }} className="anim-rise d1">
              {t('ciprbExtras.subtitle')}
            </p>
            {/* Partner brief (CIPRB) — RCH Department description supplied by
                CIPRB. Replaces the old technical lede (Kobo form list, form
                numbers, district count) which read as internal jargon in a
                hero. This human-readable brief stands in its place, in the
                same typography as the PHD hero's ABOUT THE PARTNER block. */}
            <div className="anim-rise d2" style={{ marginTop: 12, maxWidth: 640 }}>
              <div className="kicker" style={{ marginBottom: 8 }}><span className="dot" style={{ background: CIPRB_BLUE }} />ABOUT THE PARTNER</div>
              <p style={{ fontSize: 12.5, lineHeight: 1.62, color: 'var(--ink-3)', marginBottom: 0, textWrap: 'pretty' }}>
                Centre for Injury Prevention and Research, Bangladesh (CIPRB) is a nationally recognized development organization with more than 21 years of experience in implementing programme, public health, MNCAH, nutrition, injury prevention, and health systems strengthening programmes across Bangladesh. CIPRB has successfully implemented more than 100 projects in all 64 districts of Bangladesh in collaboration with the Ministry of Health and Family Welfare, DGHS, DGFP, UN agencies, donors, and international academic institutions. The Reproductive and Child Health (RCH) Department of CIPRB aims to improve maternal and newborn health through high-quality research, innovation, and health systems strengthening. In collaboration with UNFPA the department leads key initiatives such as MPDSR, Maternal Near-Miss reviews, and fistula prevention and management programs. Its work generates evidence to inform policy and improve the quality of reproductive, maternal, and newborn healthcare services in Bangladesh.
              </p>
            </div>
          </div>

          <div className="hero-right anim-rise d4">
            <div className="kicker" style={{ marginBottom: 8 }}>
              <span className="dot" style={{ background: CIPRB_BLUE }} />{t('ciprbExtras.coverage')}
            </div>
            {/* Item 1 of Dr. Tanjina's 6 October file: the single merged
                coverage map that used to sit here is replaced by the A3
                sheet showing MPDSR and End Obstetric Fistula side by side.
                That is the point of her note, "show both maps separately":
                one map cannot carry twelve districts and fourteen at once,
                and merging them hid which programme a district belongs to.
                Same sheet CIPRB holds in print, same renderer. */}
            <DonorMapSheet
              src="/maps/Both_maps_side_by_side.png"
              alt="CIPRB and UNFPA supported districts by donor. MPDSR districts, twelve, and End Obstetric Fistula districts, fourteen, side by side."
              maxWidth={720}
            />
          </div>
        </div>

        {/* Jump strip relocated to sit directly above the Fistula "AT A
            GLANCE" band (see below) so the two programmes are reachable
            without scrolling the long hero first. */}

        {/* Reporting-period toggle removed per request — all surfaces report
            on the contract window (activePeriod is fixed to it). */}

        {/* ─── Donor filter pills (Animesh's one-click GAC/SIDA ask) ─── */}
        <div
          role="radiogroup"
          aria-label="Donor filter"
          style={{
            display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10,
            marginTop: 12,
          }}
        >
          <span style={{
            fontSize: 11, color: 'var(--muted)',
            textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600,
          }}>
            {t('ciprbExtras.donor')}
          </span>
          {(Object.keys(DONOR_FILTERS) as DonorKey[]).map((k) => {
            const cfg = DONOR_FILTERS[k]
            const isActive = donorKey === k
            return (
              <button
                key={k}
                role="radio"
                aria-checked={isActive}
                onClick={() => setDonorKey(k)}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  padding: '6px 14px', borderRadius: 999,
                  background: isActive ? 'rgba(249,96,0,0.10)' : 'var(--surface-2)',
                  color: isActive ? CIPRB_BLUE : 'var(--ink-3)',
                  fontSize: 14,
                  fontWeight: isActive ? 600 : 500,
                  border: isActive
                    ? '1px solid rgba(249,96,0,0.32)'
                    : '1px solid var(--hair)',
                  cursor: 'pointer',
                  transitionProperty: 'background-color, color, border-color',
                  transitionDuration: '180ms',
                }}
              >
                <span>{cfg.label}</span>
                {cfg.districts && (
                  <span style={{
                    color: isActive ? CIPRB_BLUE : 'var(--muted)',
                    fontWeight: 500,
                    fontVariantNumeric: 'tabular-nums',
                  }}>
                    · {cfg.districts.length} districts
                  </span>
                )}
              </button>
            )
          })}
        </div>

      </section>

      {/* ─── Programme jump nav (sticky) ───
          Two pills — Fistula + MPDSR — pinned just above the AT A GLANCE
          band. Sticky so they stay reachable while scrolling through the
          long Fistula stack, killing the scroll-back-up problem. */}
      <div style={{
        position: 'sticky', top: 8, zIndex: 30,
        display: 'flex', flexWrap: 'wrap', gap: 8,
        padding: '8px 10px', marginBottom: 12,
        background: 'var(--surface)',
        border: '1px solid var(--hair)', borderRadius: 999,
        boxShadow: '0 4px 14px rgba(0,0,0,0.06)',
        width: 'fit-content',
      }}>
        <a href="#action-plan-section" style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          padding: '6px 16px', borderRadius: 999,
          background: CIPRB_BLUE, color: '#fff',
          fontSize: 13, fontWeight: 700, textDecoration: 'none',
          border: '1px solid rgba(249,96,0,0.22)',
        }}>Action plan</a>
        <a href="#fistula-section" style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          padding: '6px 16px', borderRadius: 999,
          background: 'rgba(249,96,0,0.10)', color: CIPRB_BLUE,
          fontSize: 13, fontWeight: 600, textDecoration: 'none',
          border: '1px solid rgba(249,96,0,0.22)',
        }}>{t('ciprbExtras.jumpFistula')}</a>
        <a href="#mpdsr-section" style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          padding: '6px 16px', borderRadius: 999,
          background: 'rgba(249,96,0,0.10)', color: CIPRB_BLUE,
          fontSize: 13, fontWeight: 600, textDecoration: 'none',
          border: '1px solid rgba(249,96,0,0.22)',
        }}>{t('ciprbExtras.jumpMpdsr')}</a>
        <a href="#nearmiss-section" style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          padding: '6px 16px', borderRadius: 999,
          background: 'rgba(249,96,0,0.10)', color: CIPRB_BLUE,
          fontSize: 13, fontWeight: 600, textDecoration: 'none',
          border: '1px solid rgba(249,96,0,0.22)',
        }}>{t('ciprbExtras.jumpNearMiss')}</a>
        <a href="#safe-surgery-section" style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          padding: '6px 16px', borderRadius: 999,
          background: 'rgba(249,96,0,0.10)', color: CIPRB_BLUE,
          fontSize: 13, fontWeight: 600, textDecoration: 'none',
          border: '1px solid rgba(249,96,0,0.22)',
        }}>{t('ciprbExtras.jumpSafeSurgery', { defaultValue: 'Safe Surgery' })}</a>
      </div>

      {/* ───────────────── MPDSR Response-Plan tracker (headline surface) ─────────────────
          The action plan is the dashboard's lead question — "are the agreed
          maternal-death response actions actually getting done?" — so it sits
          first, above the Fistula band. Live from CIPRB-10 (MPDSRAction). */}
      <section className="section" id="action-plan-section" style={{ marginTop: 0, marginBottom: 8, scrollMarginTop: 80 }}>
        <ActionPlanTracker districts={activeDonor.districts} />
      </section>

      {/* ─── End Obstetric Fistula districts, coloured by donor ───
          Dr. Tanjina, 6 October 2026: "show both maps separately in the
          SIMPLE Dashboard", and in her marked-up file "Add the picture end
          obstetric fistula before this".

          The picture she pasted is the sheet this project already produces
          from scratchpad/make_donor_maps.py, the one printed for Dr. Sayeed
          on 27 September. So the dashboard serves that exact rendering
          rather than drawing the same data a second way: one renderer, one
          appearance in print and on screen, nothing to drift. The file is
          written into public/maps/ by the same script. */}
      <section className="section" style={{ marginTop: 0, marginBottom: 8 }}>
        <DonorMapSheet
          src="/maps/Fistula_districts_by_donor.png"
          alt="End Obstetric Fistula districts, CIPRB and UNFPA supported districts coloured by donor. Fourteen districts."
        />
      </section>

      {/* ───────────────── Fistula KPI band ───────────────── */}
      <section className="section" id="fistula-section" style={{ marginTop: 0, scrollMarginTop: 80 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
          <div className="kicker" style={{ marginBottom: 0 }}>
            <span className="dot" style={{ background: CIPRB_BLUE }} />
            {t('ciprbExtras.fistulaGlance')}
          </div>
          <SourceChip>CIPRB 1 — Fistula Question Bank</SourceChip>
        </div>
        {kpisError ? (
          <DataUnavailable label="The fistula at-a-glance figures" onRetry={retryKpis} />
        ) : (
        <div className="band-5">
          <KPITile icon={<Search size={14} />}     label={t('ciprb.kpiSuspected')}    sub={t('ciprb.kpiSuspectedSub')}    value={kpis.suspected}   />
          <KPITile icon={<Stethoscope size={14} />} label={t('ciprb.kpiIdentified')}  sub={t('ciprb.kpiIdentifiedSub')}   value={kpis.identified}
            pct={kpis.suspected > 0 ? (kpis.identified / kpis.suspected) * 100 : null} pctLabel="of suspected" />
          <KPITile icon={<Send size={14} />}        label={t('ciprb.kpiReferred')}    sub={t('ciprb.kpiReferredSub')}     value={kpis.referred}
            pct={kpis.identified > 0 ? (kpis.referred / kpis.identified) * 100 : null} pctLabel="of diagnosed" />
          <KPITile icon={<Scissors size={14} />}    label={t('ciprb.kpiSurgeryDone')} sub={t('ciprb.kpiSurgeryDoneSub')}  value={kpis.surgeryDone}
            pct={kpis.referred > 0 ? (kpis.surgeryDone / kpis.referred) * 100 : null} pctLabel="of referred"
            pct2={kpis.identified > 0 ? (kpis.surgeryDone / kpis.identified) * 100 : null} pct2Label="of diagnosed" />
          {/* Rehabilitation % — Animesh's definition from the 2026-06-01
              meeting: rehabilitated = any of cash / training / psychosocial /
              reintegration / 5 other support types is Yes. Denominator =
              operated patients (previous funnel stage). */}
          {kpis.rehabPct != null ? (
            <KPITile
              icon={<HeartHandshake size={14} />}
              label={t('ciprb.kpiRehab')}
              sub={t('ciprb.kpiRehabSub')}
              value={kpis.rehabilitated}
              pct={kpis.rehabPct}
              pctLabel="of repaired"
              pct2={kpis.identified > 0 ? (kpis.rehabilitated / kpis.identified) * 100 : null}
              pct2Label="of diagnosed"
            />
          ) : (
            <PendingKPITile
              icon={<HeartHandshake size={14} />}
              label={t('ciprb.kpiRehab')}
              sub={t('ciprb.kpiRehabSub')}
            />
          )}
        </div>
        )}
        {!kpisError && kpis.suspected > 0 && (
          <p style={{ fontSize: 11.5, color: 'var(--muted)', margin: '8px 4px 0', fontStyle: 'italic' }}>
            {t('ciprbExtras.glanceDenoms')}
          </p>
        )}

        {/* The diagnosed-denominator figures live as second pills on the
            repaired and rehabilitated cards above — no separate strip
            (Rafi, 4 Aug 2026). */}
      </section>

      {/* ───────────────── Fistula case-data charts (outcome / diagnosis pies) ───────────────── */}
      <section className="section" style={{ marginTop: 8 }}>
        <FistulaVisualizations only="charts" period={{ from: activePeriod.from, to: activePeriod.to }} districts={activeDonor.districts} />
      </section>

      {/* ───────────────── Fistula 17 major indicators (CIPRB spec) ───────────────── */}
      <section className="section" style={{ marginTop: 8 }}>
        <FistulaIndicators districts={activeDonor.districts} />
      </section>

      {/* ───────────────── Fistula Campaign ─────────────────
          Moved down to sit directly above the MPDSR tracker (RCH, 2 Sep 2026).
          The campaign is community fieldwork, not case data, so it now closes
          the fistula band instead of opening it. */}
      <section className="section" id="fistula-campaign-section" style={{ marginTop: 8, scrollMarginTop: 80 }}>
        <FistulaVisualizations only="campaign" period={{ from: activePeriod.from, to: activePeriod.to }} districts={activeDonor.districts} />
      </section>

      {/* ───────────────── Divider ───────────────── */}
      <div style={{ height: 1, background: 'var(--hair)', margin: '18px 0 4px' }} />

      {/* ───────────────── MPDSR ───────────────── */}
      <section className="section" id="mpdsr-section" style={{ marginTop: 0, marginBottom: 24, scrollMarginTop: 80 }}>
        <MPDSRSection period={activePeriod} districts={activeDonor.districts} />
      </section>

      {/* ───────────────── Maternal Near Miss ───────────────── */}
      <section className="section" id="nearmiss-section" style={{ marginBottom: 24, scrollMarginTop: 80 }}>
        <NearMissPanel districts={activeDonor.districts} />
      </section>

      {/* ───────────────── Safe Surgery Checklist (CIPRB-11) ─────────────────
          Tanjina, 13–19 Oct 2026: visualise the WHO Safe Surgery Checklist in
          SIMPLE — operation + automatic ID, date/time, and the three phases
          (Sign In / Time Out / Sign Out) with completion trackable at a glance. */}
      <section className="section" id="safe-surgery-section" style={{ marginBottom: 80, scrollMarginTop: 80 }}>
        <SafeSurgeryPanel districts={activeDonor.districts} />
      </section>
    </div>
  )
}
