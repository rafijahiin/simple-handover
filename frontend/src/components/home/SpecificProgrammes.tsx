/**
 * SpecificProgrammes — homepage block surfacing CIPRB's three flagship
 * surveillance programmes side-by-side: Fistula · MPDSR · Baseline
 * Assessment. Replaces the older Clinical/Community/Operations donut
 * per Animesh ("read as filler at our data volume").
 *
 * Each tile is a clickable jump-in into the relevant dedicated page.
 */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowRight, HeartPulse, ShieldAlert, ClipboardList } from 'lucide-react'
import { api } from '@/api/client'

// Home-page accents follow UNFPA brand orange. The block surfaces CIPRB
// programmes by name, but the home page is the UNFPA executive view, so the
// accents pull from the brand token instead of CIPRB's partner colour.
const BRAND_ORANGE = 'var(--unfpa)'
const BRAND_ORANGE_SOFT = 'rgba(249,96,0,0.10)'

interface FistulaRow { id: string }
interface MPDSRRow {
  id: string
  cause_of_death: string
  is_overdue_committee?: boolean
}

interface Counts {
  fistulaSuspected: number
  fistulaIdentified: number
  mpdsrCases: number
  mpdsrOverdue: number
}

function useCounts(): Counts {
  const [c, setC] = useState<Counts>({
    fistulaSuspected: 0,
    fistulaIdentified: 0,
    mpdsrCases: 0,
    mpdsrOverdue: 0,
  })

  useEffect(() => {
    let cancelled = false
    Promise.allSettled([
      api.get<{ results?: FistulaRow[] } | FistulaRow[]>('/fistula/campaign-visits/'),
      api.get<{ results?: { identification_date?: string | null; diagnosis_date?: string | null }[] } | { identification_date?: string | null; diagnosis_date?: string | null }[]>('/fistula/corner-cases/'),
      api.get<{ results?: MPDSRRow[] } | MPDSRRow[]>('/mpdsr/cases/'),
    ]).then(([campaignRes, cornerRes, mpdsrRes]) => {
      if (cancelled) return

      const rows = <T,>(res: PromiseSettledResult<any>): T[] =>
        res.status === 'fulfilled'
          ? (Array.isArray(res.value.data) ? res.value.data : res.value.data.results ?? [])
          : []

      const campaign = rows<FistulaRow>(campaignRes)
      const corner = rows<{ identification_date?: string | null; diagnosis_date?: string | null }>(cornerRes)
      const mpdsr  = rows<MPDSRRow>(mpdsrRes)

      setC({
        fistulaSuspected: campaign.length,
        fistulaIdentified: corner.filter(c => c.identification_date || c.diagnosis_date).length,
        mpdsrCases: mpdsr.length,
        mpdsrOverdue: mpdsr.filter(m => m.is_overdue_committee).length,
      })
    })
    return () => { cancelled = true }
  }, [])

  return c
}

interface TileProps {
  icon: React.ReactNode
  title: string
  subtitle: string
  metricLabel: string
  metricValue: string | number
  meta?: string
  to: string
}

function ProgrammeTile({ icon, title, subtitle, metricLabel, metricValue, meta, to }: TileProps) {
  const navigate = useNavigate()
  return (
    <button
      onClick={() => navigate(to)}
      className="card"
      style={{
        padding: 24,
        textAlign: 'left',
        cursor: 'pointer',
        display: 'flex',
        flexDirection: 'column',
        gap: 18,
        minHeight: 200,
        transitionProperty: 'transform, box-shadow, border-color',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.borderColor = 'var(--unfpa)'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderColor = 'var(--hair)'
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: 38, height: 38, borderRadius: 10,
          background: BRAND_ORANGE_SOFT, color: BRAND_ORANGE,
        }}>
          {icon}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--ink)', letterSpacing: '-0.01em' }}>
            {title}
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 1 }}>
            {subtitle}
          </div>
        </div>
      </div>

      {/* Metric */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
        <div className="mono" style={{
          fontSize: 9.5, color: 'var(--muted)',
          letterSpacing: '0.1em', marginBottom: 4,
          textTransform: 'uppercase',
        }}>
          {metricLabel}
        </div>
        <div style={{
          fontSize: 36, fontWeight: 800, color: 'var(--ink)',
          lineHeight: 1, letterSpacing: '-0.02em', fontVariantNumeric: 'tabular-nums',
        }}>
          {metricValue}
        </div>
        {meta && (
          <div style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 6 }}>
            {meta}
          </div>
        )}
      </div>

      {/* Footer link */}
      <div style={{
        display: 'inline-flex', alignItems: 'center', gap: 4,
        fontSize: 12, color: BRAND_ORANGE, fontWeight: 600,
      }}>
        Open <ArrowRight size={13} />
      </div>
    </button>
  )
}

export function SpecificProgrammes() {
  const { t } = useTranslation()
  const counts = useCounts()

  return (
    <section className="section specific-programmes" style={{ marginTop: 36 }}>
      <div className="section-head">
        <div>
          <div className="kicker" style={{ marginBottom: 8 }}>
            <span className="dot" style={{ background: BRAND_ORANGE }} />
            {t('home.specificProgrammesKicker', { defaultValue: 'CIPRB · SPECIFIC PROGRAMMES' })}
          </div>
          <h2 className="section-title">
            {t('home.specificProgrammesTitle', { defaultValue: 'Fistula, MPDSR, and Baseline Assessment' })}
          </h2>
          <p className="section-sub">
            {t('home.specificProgrammesSub', {
              defaultValue: 'CIPRB-owned surveillance surfaces. Each tile jumps into its dedicated page.',
            })}
          </p>
        </div>
      </div>

      <div
        className="specific-programmes-grid"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: 16,
        }}
      >
        <ProgrammeTile
          icon={<HeartPulse size={18} />}
          title="Fistula"
          subtitle="Corner Register + Campaign Visits"
          metricLabel="Suspected · Identified"
          metricValue={`${counts.fistulaSuspected} · ${counts.fistulaIdentified}`}
          meta={counts.fistulaSuspected === 0
            ? 'Awaiting campaign submissions'
            : `${counts.fistulaIdentified} formally diagnosed`}
          to="/ciprb"
        />
        <ProgrammeTile
          icon={<ShieldAlert size={18} />}
          title="MPDSR"
          subtitle="Maternal & Perinatal Death tracker"
          metricLabel="Cases · Overdue Reviews"
          metricValue={`${counts.mpdsrCases} · ${counts.mpdsrOverdue}`}
          meta={counts.mpdsrOverdue > 0
            ? `${counts.mpdsrOverdue} committee review${counts.mpdsrOverdue === 1 ? '' : 's'} overdue`
            : 'All committee reviews on schedule'}
          to="/ciprb"
        />
        <ProgrammeTile
          icon={<ClipboardList size={18} />}
          title="Baseline Assessment"
          subtitle="CIPRB baseline & endline instrument"
          metricLabel="Survey Status"
          metricValue="—"
          meta="Awaiting variable confirmation at validation workshop"
          to="/baseline"
        />
      </div>

      <style>{`
        @media (max-width: 900px) {
          .specific-programmes-grid { grid-template-columns: 1fr !important; }
        }
      `}</style>
    </section>
  )
}
