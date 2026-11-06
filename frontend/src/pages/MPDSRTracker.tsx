/**
 * MPDSR Tracker — Maternal & Perinatal Death Surveillance.
 *
 * CIPRB-owned page. Per Animesh (Wednesday demo prep):
 *   - Partner column removed — page is CIPRB-only, ownership chip already says it
 *   - All hardcoded labels routed through i18n (EN + BN parity)
 *   - Cause + place panels stay visible at 0 counts when empty so the page
 *     never reads as "raw" during a leadership demo
 *   - Overdue committee review count surfaced as a hero badge
 *
 * Access (per audit FIX 1.9):
 *   developer + supervisor + (org_lead AND organisation=CIPRB) → 200
 *   manager / field_staff / focal                              → 403 (server)
 *                                                              → bounced (client)
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Clock, MapPin, X, AlertTriangle } from 'lucide-react'
import { api } from '@/api/client'
import { usePolling } from '@/hooks/usePolling'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { formatDate, formatDateTime } from '@/utils/format'
import type { MPDSRCase, AuditEntry } from '@/types/index'

// UNFPA branding — orange across all partner surfaces.
const CIPRB_BLUE = '#F96000'

// Cause keys returned by the API. Display labels come from i18n.
const CAUSE_KEYS = ['pph', 'eclampsia', 'sepsis', 'obstructed_labour', 'other'] as const
const PLACE_KEYS = ['facility', 'home', 'in_transit'] as const

// ─── Audit drawer ─────────────────────────────────────────────────────────────

function AuditDrawer({ kase, onClose }: { kase: MPDSRCase; onClose: () => void }) {
  const { t } = useTranslation()

  // Cause/place labels via i18n with a graceful fallback to the raw key.
  const causeLabel = (k: string) => t(`mpdsr.cause${pascal(k)}`, { defaultValue: k })
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
        <div
          style={{
            position: 'sticky', top: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '16px 20px',
            background: 'var(--surface)',
            borderBottom: '1px solid var(--hair)',
            zIndex: 1,
          }}
        >
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
            className="lang-toggle-btn"
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
          {/* Case summary */}
          <div
            className="card"
            style={{ padding: 16, background: 'var(--surface-2)', fontSize: 13 }}
          >
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <SummaryRow label={t('mpdsr.drawerForm')}     value={kase.sub_form_label || kase.sub_form_type} span={2} />
              <SummaryRow label={t('mpdsr.drawerType')}     value={kase.death_type_display} />
              <SummaryRow label={t('mpdsr.drawerPlace')}    value={placeLabel(kase.place_of_death)} />
              <SummaryRow label={t('mpdsr.drawerDistrict')} value={kase.district} />
              {kase.upazila && <SummaryRow label={t('mpdsr.drawerUpazila')} value={kase.upazila} />}
              {kase.facility_name && <SummaryRow label={t('mpdsr.drawerFacility')} value={kase.facility_name} span={2} />}
              <SummaryRow label={t('mpdsr.drawerDateOfDeath')} value={formatDate(kase.date_of_death) || '—'} />
              {kase.age_years != null && (
                <SummaryRow label={t('mpdsr.drawerAge')} value={t('mpdsr.drawerAgeYears', { years: kase.age_years })} />
              )}
              {kase.cause_of_death && (
                <SummaryRow
                  label={t('mpdsr.drawerCause')}
                  value={kase.cause_of_death.replace(/ /g, ', ')}
                  span={2}
                />
              )}
            </div>
          </div>

          {/* Audit timeline */}
          <div>
            <div className="kicker" style={{ marginBottom: 12 }}>
              <span className="dot" />{t('mpdsr.drawerTimeline')}
            </div>
            {(kase.audit_trail ?? []).length === 0 && (
              <p style={{ fontSize: 13, color: 'var(--muted)' }}>{t('mpdsr.drawerNoAudit')}</p>
            )}
            <div
              style={{
                position: 'relative',
                display: 'flex', flexDirection: 'column', gap: 16,
              }}
            >
              <span
                aria-hidden
                style={{
                  position: 'absolute', left: 15, top: 6, bottom: 6,
                  width: 1, background: 'var(--hair-2)',
                }}
              />
              {(kase.audit_trail ?? []).map((entry: AuditEntry, i: number) => (
                <div
                  key={i}
                  style={{ display: 'flex', gap: 14, paddingLeft: 36, position: 'relative' }}
                >
                  <span
                    style={{
                      position: 'absolute', left: 10, top: 6,
                      height: 11, width: 11, borderRadius: 999,
                      background: CIPRB_BLUE,
                      boxShadow: '0 0 0 2px var(--surface)',
                    }}
                  />
                  <div style={{ flex: 1 }}>
                    <div style={{
                      display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8,
                    }}>
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
                    <p style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 2 }}>
                      {entry.user}
                    </p>
                    {entry.notes && (
                      <p style={{
                        marginTop: 4, fontSize: 12, color: 'var(--ink-3)',
                        fontStyle: 'italic',
                      }}>
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

  // Local helper: pascalCase a snake_case key for i18n keys like
  // `mpdsr.causeObstructedLabour`.
  function pascal(k: string): string {
    return k.split('_').map(p => p[0].toUpperCase() + p.slice(1)).join('')
  }
}

function SummaryRow({ label, value, span = 1 }: { label: string; value: string; span?: 1 | 2 }) {
  return (
    <div style={{ gridColumn: span === 2 ? 'span 2' : undefined }}>
      <p style={{ fontSize: 11, color: 'var(--muted)', margin: 0 }}>{label}</p>
      <p style={{
        fontSize: 13, fontWeight: 500, color: 'var(--ink)', marginTop: 2,
        wordBreak: 'break-word',
      }}>
        {value}
      </p>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

type CauseFilter = 'all' | string

export default function MPDSRTracker() {
  const { t } = useTranslation()
  const [causeFilter, setCauseFilter] = useState<CauseFilter>('all')
  const [selectedCase, setSelectedCase] = useState<MPDSRCase | null>(null)

  const { data: cases, loading } = usePolling<MPDSRCase[]>({
    fetcher: () =>
      api
        .get('/mpdsr/cases/', {
          params: {
            ...(causeFilter !== 'all' ? { cause_of_death: causeFilter } : {}),
          },
        })
        .then((r) => (Array.isArray(r.data) ? r.data : r.data.results ?? [])),
    interval: 60_000,
  })

  // Disaggregation summary
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
    <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
      {/* ───────────────── Hero ───────────────── */}
      <section className="hero" style={{ paddingBottom: 8 }}>
        <div className="hero-eyebrow">
          <span className="live-dot" />
          <span>{t('mpdsr.eyebrow', { defaultValue: 'TRACKER · MPDSR' })}</span>
        </div>
        <h1
          className="hero-headline"
          style={{
            fontSize: 'clamp(40px, 5.5vw, 64px)',
            letterSpacing: '-0.03em',
            marginBottom: 10,
            fontStyle: 'normal',
            fontWeight: 800,
            color: CIPRB_BLUE,
          }}
        >
          {t('mpdsr.title', { defaultValue: 'MPDSR Tracker' })}
        </h1>
        <p className="hero-lede" style={{ maxWidth: 640 }}>
          {t('mpdsr.subtitle', { defaultValue: 'Maternal & Perinatal Death Surveillance' })}
        </p>

        {/* Hero stat strip — committee overdue badge surfaces directly */}
        {overdueCount > 0 && (
          <div style={{ marginTop: 14 }}>
            <span
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '6px 12px', borderRadius: 999,
                background: 'rgba(204,106,0,0.10)',
                border: '1px solid rgba(204,106,0,0.32)',
                color: '#AE4300',
                fontSize: 12.5, fontWeight: 500,
              }}
            >
              <AlertTriangle size={13} />
              {t('mpdsr.overdueBadge', {
                count: overdueCount,
                defaultValue: `${overdueCount} overdue committee review${overdueCount === 1 ? '' : 's'}`,
              })}
            </span>
          </div>
        )}
      </section>

      {/* ───────────────── Disaggregation cards (always visible) ─────────────────
          Always rendered with 0 counts when empty so the page never reads
          as "raw" during a leadership demo. */}
      <section className="section">
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
            gap: 12,
          }}
        >
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
                  background: active ? 'rgba(0,114,188,0.08)' : 'var(--surface)',
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
      </section>

      {/* ───────────────── Place of death pills (always visible) ───────────────── */}
      <section className="section" style={{ marginTop: -16 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
          {PLACE_KEYS.map((key) => (
            <div
              key={key}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13,
              }}
            >
              <span
                style={{
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  width: 22, height: 22, borderRadius: 999,
                  background: 'rgba(0,114,188,0.10)',
                  color: CIPRB_BLUE,
                  fontSize: 11, fontWeight: 700,
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {placeCounts[key] ?? 0}
              </span>
              <span style={{ color: 'var(--ink-3)' }}>{placeLabel(key)}</span>
            </div>
          ))}
        </div>
      </section>

      {/* CIPRB ownership chip — page is CIPRB-only, no partner filter. */}
      <section className="section" style={{ marginTop: 0 }}>
        <span
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 8,
            padding: '6px 14px', borderRadius: 999,
            background: 'var(--surface-2)', border: '1px solid var(--hair)',
            fontSize: 13, fontWeight: 500, color: 'var(--ink-2)',
          }}
        >
          <span style={{ width: 8, height: 8, borderRadius: 2, background: CIPRB_BLUE }} />
          {t('mpdsr.ciprbOwned')}
        </span>
      </section>

      {/* ───────────────── Cases table ───────────────── */}
      <section className="section" style={{ marginTop: 0, marginBottom: 48 }}>
        {loading && !cases ? (
          <PageLoader />
        ) : (
          <div className="card flush" style={{ overflow: 'hidden' }}>
            <div style={{ overflowX: 'auto' }}>
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
                    ].map((h) => (
                      <th key={h}>{h}</th>
                    ))}
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
                      <td
                        style={{
                          maxWidth: 160, overflow: 'hidden',
                          textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                          color: 'var(--ink-3)', fontSize: 12.5,
                        }}
                        title={c.sub_form_label}
                      >
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
          </div>
        )}
      </section>

      {selectedCase && (
        <AuditDrawer kase={selectedCase} onClose={() => setSelectedCase(null)} />
      )}
    </div>
  )
}

// pascalCase a snake_case key — module-level utility for the i18n cause/place
// label resolver on the main page.
function pascal(k: string): string {
  return k.split('_').map(p => p[0].toUpperCase() + p.slice(1)).join('')
}
