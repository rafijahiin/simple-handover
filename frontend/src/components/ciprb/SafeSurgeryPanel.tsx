/**
 * Safe Surgery Checklist panel (CIPRB-11) — the WHO Surgical Safety Checklist
 * surface Tanjina asked for on the SIMPLE dashboard (13–19 Oct 2026):
 *
 *   • each operation's automatic ID + name + date/time
 *   • the three checklist phases — Sign In / Time Out / Sign Out — with a
 *     per-phase completion state so compliance reads at a glance
 *   • an overall compliance rate
 *
 * Backed by `GET /api/mpdsr/safe-surgery/` (mpdsr.views.safe_surgery), which
 * returns APPROVED operations only and never includes patient_name (PII stays
 * in the approval drawer, not the at-a-glance dashboard).
 */
import { useEffect, useState } from 'react'
import { api } from '@/api/client'
import { SourceChip } from '@/components/ui/SourceChip'
import { formatDateTime } from '@/utils/format'
import { Scissors, Info, Check, MapPin } from 'lucide-react'
import { DonutBreakdown, ColumnBreakdown, BarBreakdown } from './IndicatorCharts'

const CIPRB_BLUE = '#F96000'
const OK = '#1E9E6A'      // phase complete (green reads as "compliant")
const MISS = '#C44E00'    // phase incomplete

interface Phase { total: number; done: number; complete: boolean }
interface Operation {
  id: string
  system_ref: string
  operation_name: string
  facility_name: string
  ward_unit: string
  district: string
  op_datetime: string | null
  surgeon: string
  phases: { signin: Phase; timeout: Phase; signout: Phase }
  fully_compliant: boolean
}
interface SurgeryData {
  total: number
  compliant: number
  compliance_pct: number | null
  phase_complete: { signin: number; timeout: number; signout: number }
  by_district: Record<string, number>
  operations: Operation[]
}

const PHASE_ORDER = ['signin', 'timeout', 'signout'] as const
type PhaseKey = typeof PHASE_ORDER[number]
const PHASE_LABEL: Record<PhaseKey, string> = {
  signin: 'Sign In', timeout: 'Time Out', signout: 'Sign Out',
}

/** A single phase indicator: filled dot when complete, hollow ring when not,
 *  with the done/total count so a partially-filled phase is legible. */
function PhaseDot({ label, phase }: { label: string; phase: Phase }) {
  const complete = phase.complete
  return (
    <span
      title={`${label}: ${phase.done}/${phase.total} steps${complete ? ' — complete' : ' — incomplete'}`}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        fontSize: 11.5, color: 'var(--ink-3)', whiteSpace: 'nowrap',
      }}
    >
      <span
        aria-hidden
        style={{
          width: 14, height: 14, borderRadius: 999,
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          background: complete ? OK : 'transparent',
          border: complete ? `1px solid ${OK}` : `1.5px solid ${MISS}`,
          color: '#fff', flexShrink: 0,
        }}
      >
        {complete && <Check size={9} strokeWidth={3.5} />}
      </span>
      <span style={{ fontWeight: 600 }}>{label}</span>
      <span className="mute" style={{ fontVariantNumeric: 'tabular-nums', fontSize: 10.5 }}>
        {phase.done}/{phase.total}
      </span>
    </span>
  )
}

function StatTile({ label, value, pct }: { label: string; value: string | number; pct?: boolean }) {
  return (
    <div className="card" style={{ padding: '14px 18px', flex: '1 1 150px', minWidth: 140 }}>
      <div className="mono" style={{ fontSize: 10, color: 'var(--muted)', letterSpacing: '0.08em' }}>
        {label}
      </div>
      <div style={{
        fontSize: 32, fontWeight: 800, color: CIPRB_BLUE, lineHeight: 1.1,
        fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.02em',
      }}>
        {value}{pct ? '%' : ''}
      </div>
    </div>
  )
}

export function SafeSurgeryPanel({ districts }: { districts?: readonly string[] | null }) {
  const [data, setData] = useState<SurgeryData | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  const districtsKey = districts ? districts.join(',') : ''
  useEffect(() => {
    let cancelled = false
    const params: Record<string, string> = {}
    if (districtsKey) params.districts = districtsKey
    api.get<SurgeryData>('/mpdsr/safe-surgery/', { params })
      .then(r => { if (!cancelled) { setData(r.data); setLoading(false) } })
      .catch(e => { if (!cancelled) { setErr(String(e?.message || e)); setLoading(false) } })
    return () => { cancelled = true }
  }, [districtsKey])

  if (loading) {
    return (
      <div style={{ padding: '40px 16px', textAlign: 'center', color: 'var(--muted)' }}>
        Loading Safe Surgery checklist data…
      </div>
    )
  }
  if (err) {
    return (
      <div className="card" style={{ padding: 16, fontSize: 13, color: 'var(--coral)' }}>
        Could not load Safe Surgery data: {err}
      </div>
    )
  }

  const total = data?.total ?? 0
  const compliant = data?.compliant ?? 0
  const pct = data?.compliance_pct
  const ops = data?.operations ?? []

  return (
    <div>
      {/* ─── Header ─── */}
      <div style={{
        marginBottom: 14,
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
        gap: 8, flexWrap: 'wrap',
      }}>
        <div>
          <div className="kicker">
            <span className="dot" style={{ background: CIPRB_BLUE }} />
            SAFE SURGERY CHECKLIST · CIPRB-11
          </div>
          <h3 style={{ margin: '6px 0 2px', fontSize: 18, fontWeight: 700, color: 'var(--ink)' }}>
            WHO Surgical Safety Checklist
          </h3>
          <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: 0, maxWidth: 620 }}>
            One checklist per operation, with an automatic operation ID. Each operation shows the three WHO phases — Sign In (before anaesthesia), Time Out (before incision), Sign Out (before the patient leaves the OT) — so checklist compliance is trackable at a glance.
          </p>
        </div>
        <SourceChip>CIPRB 11 — Safe Surgery Checklist</SourceChip>
      </div>

      {/* ─── Compliance summary ─── */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
        <StatTile label="OPERATIONS" value={total.toLocaleString()} />
        <StatTile label="FULLY COMPLIANT" value={compliant.toLocaleString()} />
        <StatTile label="COMPLIANCE RATE" value={pct == null ? '—' : pct} pct={pct != null} />
        <div className="card" style={{ padding: '14px 18px', flex: '2 1 280px', minWidth: 240 }}>
          <div className="mono" style={{ fontSize: 10, color: 'var(--muted)', letterSpacing: '0.08em', marginBottom: 8 }}>
            PHASES COMPLETE
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {PHASE_ORDER.map(k => {
              const n = data?.phase_complete?.[k] ?? 0
              const p = total > 0 ? Math.round((n / total) * 100) : 0
              return (
                <div key={k} style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                    <span style={{ color: 'var(--ink-2)', fontWeight: 600 }}>{PHASE_LABEL[k]}</span>
                    <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                      <b>{n}</b>
                      <span className="mute" style={{ marginLeft: 6, fontSize: 11 }}>
                        {total > 0 ? `${p}%` : '—'}
                      </span>
                    </span>
                  </div>
                  <div style={{ height: 6, borderRadius: 3, background: 'var(--surface-3)', overflow: 'hidden' }}>
                    <div style={{ width: `${p}%`, height: '100%', background: CIPRB_BLUE, borderRadius: 3, transition: 'width 400ms ease' }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* ─── Charts: compliance split · phase completion · by district ─── */}
      {total > 0 && (
        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 18 }}>
          <DonutBreakdown
            kicker="COMPLIANCE"
            title="Fully compliant vs incomplete"
            data={{ compliant, incomplete: Math.max(0, total - compliant) }}
            labels={{ compliant: 'Fully compliant', incomplete: 'Incomplete' }}
          />
          <ColumnBreakdown
            kicker="BY PHASE"
            title="Operations completing each phase"
            data={{
              signin: data?.phase_complete?.signin ?? 0,
              timeout: data?.phase_complete?.timeout ?? 0,
              signout: data?.phase_complete?.signout ?? 0,
            }}
            labels={{ signin: 'Sign In', timeout: 'Time Out', signout: 'Sign Out' }}
          />
          <BarBreakdown
            kicker="GEOGRAPHY"
            title="Operations by district"
            data={data?.by_district ?? {}}
          />
        </div>
      )}

      {/* ─── Operations table ─── */}
      {total === 0 ? (
        <div className="card" style={{
          padding: 24, textAlign: 'center', color: 'var(--ink-3)',
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10,
        }}>
          <Info size={20} style={{ color: CIPRB_BLUE }} />
          <div style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--ink-2)' }}>
            No operations recorded yet
          </div>
          <div style={{ fontSize: 12, maxWidth: 480, color: 'var(--muted)', lineHeight: 1.55 }}>
            Once CIPRB teams submit through <b>CIPRB 11 — Safe Surgery Checklist</b> and the record is approved, each operation and its Sign In / Time Out / Sign Out status will appear here.
          </div>
        </div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th>Operation ID</th>
                  <th>Operation</th>
                  <th>Facility</th>
                  <th>When</th>
                  <th>Checklist phases</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {ops.map(o => (
                  <tr key={o.id} style={o.fully_compliant ? undefined : { background: 'rgba(196,78,0,0.05)' }}>
                    <td>
                      <span className="mono" style={{ fontSize: 11.5, color: CIPRB_BLUE, fontWeight: 700 }}>
                        {o.system_ref || '—'}
                      </span>
                    </td>
                    <td style={{ color: 'var(--ink-2)', fontWeight: 500, maxWidth: 200 }}>
                      {o.operation_name}
                      {o.ward_unit && (
                        <span className="mute" style={{ marginLeft: 6, fontSize: 11 }}>· {o.ward_unit}</span>
                      )}
                    </td>
                    <td style={{ color: 'var(--ink-3)', fontSize: 12.5 }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        <MapPin size={12} style={{ color: 'var(--muted)' }} />
                        {o.facility_name || o.district || '—'}
                      </span>
                    </td>
                    <td style={{ color: 'var(--ink-3)', fontSize: 12.5, whiteSpace: 'nowrap' }}>
                      {o.op_datetime ? formatDateTime(o.op_datetime) : '—'}
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
                        {PHASE_ORDER.map(k => (
                          <PhaseDot key={k} label={PHASE_LABEL[k]} phase={o.phases[k]} />
                        ))}
                      </div>
                    </td>
                    <td>
                      {o.fully_compliant ? (
                        <span style={{
                          display: 'inline-flex', alignItems: 'center', gap: 4,
                          fontSize: 11.5, fontWeight: 700, color: OK,
                          background: 'rgba(30,158,106,0.12)', borderRadius: 999, padding: '2px 9px',
                        }}>
                          <Check size={11} strokeWidth={3} /> Compliant
                        </span>
                      ) : (
                        <span style={{
                          fontSize: 11.5, fontWeight: 700, color: MISS,
                          background: 'rgba(196,78,0,0.12)', borderRadius: 999, padding: '2px 9px',
                        }}>
                          Incomplete
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <p style={{ fontSize: 11, color: 'var(--muted)', margin: '10px 4px 0', fontStyle: 'italic', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        <Scissors size={12} style={{ color: CIPRB_BLUE }} />
        A phase counts as complete when every checklist step was carried out (none marked “Not done”). Patient names are not shown here; they stay in the approval record.
      </p>
    </div>
  )
}
