/**
 * Maternal Near Miss panel — feeds the CIPRB dashboard with the 6
 * indicators CIPRB asked for (severe maternal complications, critical
 * interventions, life-threatening conditions, mode of delivery, causes,
 * contributory conditions).
 *
 * Backed by `GET /api/mpdsr/mnm/aggregates/` (mpdsr.views.mnm_aggregates).
 * Empty-state when zero submissions have landed — keeps the dashboard
 * honest until Phase 2 data starts flowing.
 */
import { useEffect, useState } from 'react'
import { api } from '@/api/client'
import { SourceChip } from '@/components/ui/SourceChip'
import { useTranslation } from 'react-i18next'
import { ShieldAlert, Activity, HeartPulse, Info } from 'lucide-react'
import { DonutBreakdown } from './IndicatorCharts'

const CIPRB_BLUE = '#F96000'
const CIPRB_BLUE_LIGHT = '#FB904D'

// The 17 screening flags are 3-state: Yes / No / Unknown counts per flag.
interface FlagCounts {
  yes: number
  no: number
  unknown: number
}

interface MNMAggregates {
  total: number
  by_district: Record<string, number>
  severe_complications: Record<string, FlagCounts>
  critical_interventions: Record<string, FlagCounts>
  life_threatening: Record<string, FlagCounts>
  mode_of_delivery: Record<string, number>
  causes: Record<string, number>
  contributory_conditions?: string[]
}

const MODE_LABELS: Record<string, string> = {
  nvd: 'NVD', csection: 'C-section', assisted_vaginal: 'Assisted vaginal', undelivered: 'Undelivered',
}
const CAUSE_LABELS: Record<string, string> = {
  haemorrhage: 'Haemorrhage', eclampsia: 'Eclampsia / pre-eclampsia', sepsis: 'Sepsis',
  obstructed_labour: 'Obstructed labour', abortion_related: 'Abortion-related',
  embolism: 'Embolism', indirect: 'Indirect cause', other: 'Other',
}

const SEVERE_LABELS: Record<string, string> = {
  sev_pph:      'Severe PPH',
  sev_preec:    'Severe pre-eclampsia',
  eclampsia:    'Eclampsia',
  sepsis:       'Sepsis / severe infection',
  rupt_uterus:  'Ruptured uterus',
  sev_abortion: 'Severe abortion complication',
}
const CRITICAL_LABELS: Record<string, string> = {
  crit_blood:   'Blood products',
  crit_radiol:  'Interventional radiology',
  crit_laparot: 'Laparotomy / hysterectomy',
  crit_icu:     'ICU admission',
}
const LIFE_LABELS: Record<string, string> = {
  life_cardio:  'Cardiovascular',
  life_resp:    'Respiratory',
  life_renal:   'Renal',
  life_coag:    'Coagulation',
  life_hepatic: 'Hepatic',
  life_neuro:   'Neurological',
  life_uterine: 'Uterine / hysterectomy',
}

// Normalise a flag value to {yes, no, unknown}. Tolerates the legacy plain
// number shape (treated as the Yes count) so an old API response still renders.
function toFlagCounts(v: FlagCounts | number | undefined): FlagCounts {
  if (typeof v === 'number') return { yes: v, no: 0, unknown: 0 }
  return { yes: v?.yes ?? 0, no: v?.no ?? 0, unknown: v?.unknown ?? 0 }
}

function CountSection({
  title, kicker, icon, data, labels, total,
}: {
  title: string
  kicker: string
  icon: React.ReactNode
  data: Record<string, FlagCounts>
  labels: Record<string, string>
  total: number
}) {
  const entries = Object.entries(labels)
    .map(([k, label]) => ({ k, label, ...toFlagCounts(data[k]) }))
    .sort((a, b) => b.yes - a.yes)
  const max = Math.max(1, ...entries.map(e => e.yes))
  return (
    <div className="card" style={{ padding: 20, flex: '1 1 280px', minWidth: 260 }}>
      <div style={{ marginBottom: 12 }}>
        <div className="kicker">
          <span className="dot" style={{ background: CIPRB_BLUE }} />
          {kicker}
        </div>
        <h4 style={{
          margin: '4px 0 2px', fontSize: 15, fontWeight: 700,
          color: 'var(--ink)', display: 'flex', alignItems: 'center', gap: 8,
        }}>
          {icon} {title}
        </h4>
      </div>
      <div style={{
        display: 'flex', flexDirection: 'column', gap: 8, fontSize: 12.5,
      }}>
        {entries.map(e => {
          const pct = total > 0 ? Math.round((e.yes / total) * 100) : 0
          return (
            <div key={e.k} style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <span style={{ color: 'var(--ink-2)' }}>{e.label}</span>
                <span style={{ whiteSpace: 'nowrap' }}>
                  <b style={{ fontVariantNumeric: 'tabular-nums' }}>{e.yes}</b>
                  <span className="mute" style={{ marginLeft: 6, fontSize: 11 }}>
                    {total > 0 ? `${pct}%` : '—'}
                  </span>
                  {e.unknown > 0 && (
                    <span
                      className="mute"
                      title={`${e.unknown} unknown · ${e.no} no`}
                      style={{ marginLeft: 8, fontSize: 10.5, fontStyle: 'italic' }}
                    >
                      ?{e.unknown}
                    </span>
                  )}
                </span>
              </div>
              <div style={{
                height: 6, borderRadius: 3,
                background: 'var(--surface-3)', overflow: 'hidden',
              }}>
                <div style={{
                  width: `${(e.yes / max) * 100}%`,
                  height: '100%', background: CIPRB_BLUE,
                  borderRadius: 3,
                  transition: 'width 400ms ease',
                }} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function NearMissPanel({ districts }: { districts?: readonly string[] | null }) {
  const { t } = useTranslation()
  const [data, setData] = useState<MNMAggregates | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  // Thread the donor district filter to the endpoint so the Near Miss panel
  // scopes with the GAC / SIDA / All pill like the rest of the dashboard.
  const districtsKey = districts ? districts.join(',') : ''
  useEffect(() => {
    let cancelled = false
    const params: Record<string, string> = {}
    if (districtsKey) params.districts = districtsKey
    api.get<MNMAggregates>('/mpdsr/mnm/aggregates/', { params })
      .then(r => { if (!cancelled) { setData(r.data); setLoading(false) } })
      .catch(e => { if (!cancelled) { setErr(String(e?.message || e)); setLoading(false) } })
    return () => { cancelled = true }
  }, [districtsKey])

  if (loading) {
    return (
      <div style={{ padding: '40px 16px', textAlign: 'center', color: 'var(--muted)' }}>
        {t('nearMiss.loading', { defaultValue: 'Loading Maternal Near Miss data…' })}
      </div>
    )
  }
  if (err) {
    return (
      <div className="card" style={{ padding: 16, fontSize: 13, color: 'var(--coral)' }}>
        {t('nearMiss.loadError', { defaultValue: 'Could not load Near Miss aggregates:' })} {err}
      </div>
    )
  }

  const total = data?.total ?? 0

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
            MATERNAL NEAR MISS AUDIT · CIPRB-9
          </div>
          <h3 style={{ margin: '6px 0 2px', fontSize: 18, fontWeight: 700, color: 'var(--ink)' }}>
            Maternal Near Miss surveillance
          </h3>
          <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: 0 }}>
            Women who survived a severe complication of pregnancy, childbirth or the puerperium. Six indicators per CIPRB request — severe complications, critical interventions, life-threatening conditions, mode of delivery, causes, contributory conditions.
          </p>
        </div>
        <SourceChip>CIPRB 9 — Near Miss</SourceChip>
      </div>

      {/* ─── Total + by-district top row ─── */}
      <div className="card" style={{ padding: 22, marginBottom: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap' }}>
          <div>
            <div className="mono" style={{ fontSize: 10, color: 'var(--muted)', letterSpacing: '0.08em' }}>
              TOTAL NEAR MISS CASES
            </div>
            <div style={{
              fontSize: 44, fontWeight: 800, color: CIPRB_BLUE, lineHeight: 1,
              fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.02em',
            }}>
              {total.toLocaleString()}
            </div>
          </div>
          <div style={{ flex: 1, minWidth: 220 }}>
            <div className="mono" style={{ fontSize: 10, color: 'var(--muted)', letterSpacing: '0.08em', marginBottom: 6 }}>
              BY DISTRICT
            </div>
            {Object.keys(data?.by_district ?? {}).length === 0 ? (
              <div style={{
                fontSize: 12.5, color: 'var(--ink-3)',
                display: 'flex', alignItems: 'center', gap: 8,
              }}>
                <Info size={14} style={{ color: CIPRB_BLUE }} />
                No near-miss cases recorded yet. Submissions to CIPRB 9 — Maternal Near Miss audit will populate this surface.
              </div>
            ) : (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {Object.entries(data!.by_district)
                  .sort((a, b) => b[1] - a[1])
                  .slice(0, 18)
                  .map(([d, n]) => (
                    <span key={d} className="tag" style={{ fontSize: 11.5 }}>
                      {d} <b style={{ marginLeft: 4, fontVariantNumeric: 'tabular-nums' }}>{n}</b>
                    </span>
                  ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {total === 0 ? (
        <div className="card" style={{
          padding: 24, textAlign: 'center', color: 'var(--ink-3)',
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10,
        }}>
          <Info size={20} style={{ color: CIPRB_BLUE }} />
          <div style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--ink-2)' }}>
            No Maternal Near Miss audits recorded yet
          </div>
          <div style={{ fontSize: 12, maxWidth: 480, color: 'var(--muted)', lineHeight: 1.55 }}>
            Once CIPRB field teams submit through <b>CIPRB 9 — Maternal Near Miss audit</b>, the 17 WHO screening flags will populate here (severe complications · critical interventions · life-threatening conditions).
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'flex-start' }}>
          <CountSection
            kicker="SECTION 1"
            title="Severe maternal complications"
            icon={<ShieldAlert size={14} style={{ color: CIPRB_BLUE }} />}
            data={data?.severe_complications ?? {}}
            labels={SEVERE_LABELS}
            total={total}
          />
          <CountSection
            kicker="SECTION 2"
            title="Critical interventions"
            icon={<Activity size={14} style={{ color: CIPRB_BLUE_LIGHT }} />}
            data={data?.critical_interventions ?? {}}
            labels={CRITICAL_LABELS}
            total={total}
          />
          <CountSection
            kicker="SECTION 3"
            title="Life-threatening conditions"
            icon={<HeartPulse size={14} style={{ color: '#C44E00' }} />}
            data={data?.life_threatening ?? {}}
            labels={LIFE_LABELS}
            total={total}
          />
        </div>
      )}

      {/* Indicators 4, 5 — mode of delivery, causes.
          The old indicator 6 ("Contributory / associated conditions") was
          removed: it rendered a raw, repeating free-text list (e.g. "Severe
          anemia" three times over) that carried no analytical value on the
          dashboard. The field is still captured on the Kobo form and remains
          available in the case register for narrative review. */}
      {total > 0 && (
        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginTop: 14 }}>
          <DonutBreakdown title="4. Mode of delivery" data={data?.mode_of_delivery ?? {}} labels={MODE_LABELS} />
          <DonutBreakdown title="5. Causes of near miss" data={data?.causes ?? {}} labels={CAUSE_LABELS} />
        </div>
      )}
    </div>
  )
}
