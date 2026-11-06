/**
 * ProgrammeHealthFlags — per-partner activity-compliance + anomaly surface.
 *
 * Animesh's spec:
 *   - Three cards, one per implementing partner (PHD, Bandhu, CIPRB).
 *   - Alert if a partner hasn't uploaded anything in the past 74 hours.
 *   - Field users must submit daily — even a '0' on zero-patient days.
 *   - REPLACES the old Activity Feed entirely.
 *   - UNFPA-only surface: only supervisors (and developers, for support)
 *     see this block.
 *
 * Renders nothing for non-UNFPA roles, so partner managers don't see
 * the cross-partner compliance picture.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CheckCircle2, AlertTriangle, Clock } from 'lucide-react'
import { api } from '@/api/client'
import { useAuth } from '@/context/AuthContext'
import { PARTNER_COLORS, type PartnerCode } from '@/data/partnerDistricts'

interface PartnerFlag {
  partner: string
  total_centres: number
  submitted_today: number
  silent_count: number
  submissions_today: number
  zero_reports_today?: number
  recent_submissions: number
  last_submission_at: string | null
  partner_silent_hours: number | null
  is_silent: boolean
  silent_centres: { name: string; district: string; hours_silent: number | null }[]
}

interface HealthFlagPayload {
  as_of: string
  alert_threshold_hours: number
  partners: PartnerFlag[]
}

function useHealthFlags() {
  const [data, setData] = useState<HealthFlagPayload | null>(null)
  useEffect(() => {
    let cancelled = false
    api.get<HealthFlagPayload>('/dashboard/health-flags/')
      .then(r => { if (!cancelled) setData(r.data) })
      .catch(() => { /* silently fail — block hides */ })
    return () => { cancelled = true }
  }, [])
  return data
}

function PartnerFlagTile({ flag, thresholdHours }: { flag: PartnerFlag; thresholdHours: number }) {
  const { t } = useTranslation()
  const partner = flag.partner as PartnerCode
  const color = PARTNER_COLORS[partner] ?? '#999'
  const isCompliant = !flag.is_silent

  return (
    <div
      className="card"
      style={{
        padding: 20,
        display: 'flex', flexDirection: 'column', gap: 12,
        // SIMPLE Homepage.html design — amber top accent on daily
        // reporting cards (not partner colour). Conveys 'attention
        // surface', consistent across all three partner tiles.
        borderTop: '3px solid #F1B566',
      }}
    >
      {/* Partner header + compliance pill */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div>
          <div style={{
            fontSize: 18, fontWeight: 700, color: 'var(--ink)',
            letterSpacing: '-0.01em',
            display: 'inline-flex', alignItems: 'center', gap: 9,
          }}>
            {/* Partner colour dot — design carries CIPRB blue / Bandhu
                green / PHD orange here even though the rest of the site
                is UNFPA orange. Pure identification, no editing happens
                from this dot. */}
            <span style={{
              width: 9, height: 9, borderRadius: '50%', background: color,
            }} />
            {flag.partner}
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 2 }}>
            {flag.total_centres > 0
              ? t('health.centresActive', { count: flag.total_centres })
              : t('health.registryPending')}
          </div>
        </div>
        {isCompliant ? (
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 5,
            padding: '4px 10px', borderRadius: 999,
            background: 'rgba(26,122,90,0.10)',
            color: '#58968A',
            fontSize: 11, fontWeight: 600,
          }}>
            <CheckCircle2 size={12} /> {t('health.active')}
          </span>
        ) : (
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 5,
            padding: '4px 10px', borderRadius: 999,
            background: 'rgba(204,106,0,0.10)',
            color: '#AE4300',
            fontSize: 11, fontWeight: 600,
          }}>
            <AlertTriangle size={12} /> {t('health.silent')}
          </span>
        )}
      </div>

      {/* Big number — amber (#E8870B) per design, signals attention.
          Partner-coloured dot above handles identification; this
          number signals 'how many in 24h'. */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{
          fontSize: 36, fontWeight: 600,
          color: '#E8870B',
          fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.02em', lineHeight: 1,
        }}>
          {flag.recent_submissions.toLocaleString()}
        </span>
        <span style={{
          fontSize: 13, color: 'var(--ink-3)',
        }}>
          {t('health.submissionsInWindow', { hours: thresholdHours })}
        </span>
      </div>

      {/* Today + last touched */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
        <div style={{ color: 'var(--ink-3)' }}>
          <b style={{ color: 'var(--ink-2)', fontVariantNumeric: 'tabular-nums' }}>
            {flag.submissions_today.toLocaleString()}
          </b>
          {' '}{t('health.today')}
          {flag.total_centres > 0 && (
            <>
              {' · '}
              <b style={{ color: 'var(--ink-2)', fontVariantNumeric: 'tabular-nums' }}>
                {flag.submitted_today}/{flag.total_centres}
              </b>
              {' '}{t('health.centresLabel')}
            </>
          )}
          {(flag.zero_reports_today ?? 0) > 0 && (
            <span style={{ color: 'var(--muted)' }}>
              {' · '}{flag.zero_reports_today} no-activity report{flag.zero_reports_today === 1 ? '' : 's'}
            </span>
          )}
        </div>
        {flag.partner_silent_hours !== null ? (
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 5,
            color: flag.partner_silent_hours > thresholdHours ? '#F10F45'
                 : flag.partner_silent_hours > 24 ? '#AE4300'
                 : 'var(--muted)',
            fontSize: 11.5,
          }}>
            <Clock size={11} />
            {flag.partner_silent_hours.toFixed(1)}{t('health.hoursSinceLastTouch')}
          </div>
        ) : (
          <div style={{ fontSize: 11.5, color: 'var(--muted)' }}>
            {t('health.noSubmissionsYet')}
          </div>
        )}
      </div>

      {/* Per-centre silent drill-down removed — it was extra detail for the
          homepage. The compliance card above (status pill, recent count,
          today, hours-since-last-touch) carries the daily-reporting signal;
          the granular silent-centre list belongs on the tracker, not here. */}
    </div>
  )
}

export function ProgrammeHealthFlags() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const data = useHealthFlags()

  // Daily reporting compliance. Every authenticated reviewer sees it now
  // (the backend scopes which partners are returned): UNFPA/CIPRB see all
  // three, a PHD/Bandhu manager or focal sees only their own card — which
  // is what lets a manager confirm their own daily reporting duty was met.
  if (!user) {
    return null
  }

  if (!data || data.partners.length === 0) {
    return null
  }

  const allCompliant = data.partners.every(p => !p.is_silent)
  const thresholdHours = data.alert_threshold_hours
  // A manager/focal sees a single card (their own org); UNFPA sees all three.
  const cols = Math.min(3, Math.max(1, data.partners.length))

  return (
    <section className="section programme-health-flags" style={{ marginTop: 44 }}>
      <div className="section-head" style={{ marginBottom: 20 }}>
        <div>
          <div className="kicker" style={{ marginBottom: 8 }}>
            <span className="dot" style={{
              background: allCompliant ? 'var(--unfpa)' : '#AE4300',
            }} />
            {t('health.kicker', { hours: thresholdHours })}
          </div>
          <h2 className="section-title">
            {allCompliant ? t('health.titleAllSteady') : t('health.titleSilent')}
          </h2>
          <p className="section-sub">
            {t('health.sub', { hours: thresholdHours })}
          </p>
        </div>
      </div>

      <div
        className="health-flags-grid"
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${cols}, 1fr)`,
          gap: 16,
        }}
      >
        {data.partners.map(p => (
          <PartnerFlagTile key={p.partner} flag={p} thresholdHours={thresholdHours} />
        ))}
      </div>

      <style>{`
        @media (max-width: 900px) {
          .health-flags-grid { grid-template-columns: 1fr !important; }
        }
      `}</style>
    </section>
  )
}
