/**
 * ProgrammeTotals — Animesh's "till date" headline numbers.
 *
 * One consolidated band sitting just above the Executive Bento. Shows
 * the major programme-wide counts that a manager needs to see in one
 * glance, without scrolling and without separate Fistula / MPDSR tiles
 * scattered across the page.
 *
 * Numbers shown:
 *   - Total Fistula patients
 *   - Total MD notified / reviewed (paired tile)
 *   - Total ND notified / reviewed (paired tile)
 *   - Total stillbirths notified / reviewed (paired tile)
 *   - Total cases referred  (Fistula referrals + MPDSR onward referrals)
 *
 * All counts are cumulative-to-date from the KPI endpoint.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { HeartPulse, Activity, Baby, ShieldAlert, Send } from 'lucide-react'
import { api } from '@/api/client'

interface KPIs {
  total_fistula_patients?: number
  total_fistula_referred?: number
  total_md_notified?: number
  total_md_reviewed?: number
  total_nd_notified?: number
  total_nd_reviewed?: number
  total_stillbirths_notified?: number
  total_stillbirths_reviewed?: number
}

const ORANGE = 'var(--unfpa)'
const ORANGE_SOFT = 'rgba(249,96,0,0.10)'

function fmt(n: number | undefined): string {
  if (n == null) return '—'
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return n.toLocaleString()
}

function PairedTile({
  icon, label, notified, reviewed, notifiedLabel, reviewedLabel,
}: {
  icon: React.ReactNode
  label: string
  notified: number | undefined
  reviewed: number | undefined
  notifiedLabel: string
  reviewedLabel: string
}) {
  return (
    <div className="card" style={{
      padding: '16px 18px',
      display: 'flex', flexDirection: 'column', gap: 10,
    }}>
      <div style={{
        display: 'inline-flex', alignItems: 'center', gap: 8,
        fontSize: 10.5, color: 'var(--muted)',
        textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 500,
      }}>
        <span style={{
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: 22, height: 22, borderRadius: 6,
          background: ORANGE_SOFT, color: ORANGE,
        }}>
          {icon}
        </span>
        {label}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <div>
          <div style={{
            fontSize: 24, fontWeight: 800, color: 'var(--ink)',
            fontVariantNumeric: 'tabular-nums', lineHeight: 1,
          }}>
            {fmt(notified)}
          </div>
          <div className="mono" style={{
            fontSize: 9, color: 'var(--muted)', letterSpacing: '0.06em',
            marginTop: 4, textTransform: 'uppercase',
          }}>
            {notifiedLabel}
          </div>
        </div>
        <div>
          <div style={{
            fontSize: 24, fontWeight: 800, color: 'var(--ink-2)',
            fontVariantNumeric: 'tabular-nums', lineHeight: 1,
          }}>
            {fmt(reviewed)}
          </div>
          <div className="mono" style={{
            fontSize: 9, color: 'var(--muted)', letterSpacing: '0.06em',
            marginTop: 4, textTransform: 'uppercase',
          }}>
            {reviewedLabel}
          </div>
        </div>
      </div>
    </div>
  )
}

function SoloTile({
  icon, label, value, sub,
}: {
  icon: React.ReactNode
  label: string
  value: number | undefined
  sub: string
}) {
  return (
    <div className="card" style={{
      padding: '16px 18px',
      display: 'flex', flexDirection: 'column', gap: 8,
    }}>
      <div style={{
        display: 'inline-flex', alignItems: 'center', gap: 8,
        fontSize: 10.5, color: 'var(--muted)',
        textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 500,
      }}>
        <span style={{
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: 22, height: 22, borderRadius: 6,
          background: ORANGE_SOFT, color: ORANGE,
        }}>
          {icon}
        </span>
        {label}
      </div>
      <div style={{
        fontSize: 30, fontWeight: 800, color: 'var(--ink)',
        fontVariantNumeric: 'tabular-nums', lineHeight: 1, letterSpacing: '-0.02em',
      }}>
        {fmt(value)}
      </div>
      <div style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>{sub}</div>
    </div>
  )
}

export function ProgrammeTotals() {
  const { t } = useTranslation()
  const [kpis, setKpis] = useState<KPIs | null>(null)

  useEffect(() => {
    let cancelled = false
    api.get<KPIs>('/dashboard/kpis/')
      .then(r => { if (!cancelled) setKpis(r.data) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])

  return (
    <section className="section programme-totals" style={{ marginTop: 36 }}>
      <div className="section-head" style={{ marginBottom: 16 }}>
        <div>
          <div className="kicker" style={{ marginBottom: 8 }}>
            <span className="dot" style={{ background: ORANGE }} />
            {t('totals.kicker', { defaultValue: 'PROGRAMME TOTALS · TILL DATE' })}
          </div>
          <h2 className="section-title">
            {t('totals.title', { defaultValue: 'Major indicators across all partners' })}
          </h2>
          <p className="section-sub">
            {t('totals.sub', {
              defaultValue: 'Cumulative figures for Fistula, MPDSR, and onward referrals — Fistula patients, maternal & newborn deaths, stillbirths, and total cases managed or referred.',
            })}
          </p>
        </div>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
        gap: 14,
      }}>
        <SoloTile
          icon={<HeartPulse size={13} />}
          label={t('totals.fistulaPatients', { defaultValue: 'Fistula Patients' })}
          value={kpis?.total_fistula_patients}
          sub={t('totals.fistulaSub', { defaultValue: 'Total identified at the Fistula Corner' })}
        />
        <PairedTile
          icon={<ShieldAlert size={13} />}
          label={t('totals.maternalDeaths', { defaultValue: 'Maternal Deaths' })}
          notified={kpis?.total_md_notified}
          reviewed={kpis?.total_md_reviewed}
          notifiedLabel={t('totals.notified', { defaultValue: 'Notified' })}
          reviewedLabel={t('totals.reviewed', { defaultValue: 'Reviewed' })}
        />
        <PairedTile
          icon={<Baby size={13} />}
          label={t('totals.newbornDeaths', { defaultValue: 'Newborn Deaths' })}
          notified={kpis?.total_nd_notified}
          reviewed={kpis?.total_nd_reviewed}
          notifiedLabel={t('totals.notified', { defaultValue: 'Notified' })}
          reviewedLabel={t('totals.reviewed', { defaultValue: 'Reviewed' })}
        />
        <PairedTile
          icon={<Activity size={13} />}
          label={t('totals.stillbirths', { defaultValue: 'Stillbirths' })}
          notified={kpis?.total_stillbirths_notified}
          reviewed={kpis?.total_stillbirths_reviewed}
          notifiedLabel={t('totals.notified', { defaultValue: 'Notified' })}
          reviewedLabel={t('totals.reviewed', { defaultValue: 'Reviewed' })}
        />
        <SoloTile
          icon={<Send size={13} />}
          label={t('totals.referred', { defaultValue: 'Cases Referred' })}
          value={kpis?.total_fistula_referred}
          sub={t('totals.referredSub', { defaultValue: 'Fistula patients sent for surgery / treatment' })}
        />
      </div>
    </section>
  )
}
