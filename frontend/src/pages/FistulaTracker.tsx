/**
 * CIPRB Fistula Tracker — Corner Register + Campaign Visit registers.
 *
 * Per Animesh (Wednesday demo prep):
 *   - Hero + active tab use CIPRB blue (#0072BC), not UNFPA orange —
 *     CIPRB owns this page, so the partner accent should reflect that.
 *   - A KPI tile band above the tabs gives Animesh's four headline
 *     numbers at a glance: Suspected · Identified · Referred · Surgery Done.
 *     Sourced client-side from /fistula/campaign-visits/ (field screening
 *     count) + /fistula/corner-cases/ (hospital register).
 *
 * Once Sayeed signs off the variable list at the validation workshop
 * the panels below activate and these tiles fill with live numbers.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { motion, AnimatePresence, useReducedMotion } from 'motion/react'
import { ClipboardList, Megaphone, Search, Stethoscope, Send, Scissors } from 'lucide-react'
import { api } from '@/api/client'
import { FistulaCornerPanel, FistulaCampaignPanel } from '@/components/fistula/FistulaPanels'
import { DonorDistrictMap } from '@/components/ciprb/MPDSRDistrictMap'

// UNFPA branding — orange across the board, no partner-specific hues.
const CIPRB_BLUE = '#F96000'

type TabKey = 'corner' | 'campaign'

interface TabDef {
  key: TabKey
  labelKey: string
  labelBnKey: string
  icon: React.ReactNode
}

const TABS: TabDef[] = [
  { key: 'corner',   labelKey: 'ciprb.tabCorner',   labelBnKey: 'ciprb.tabCornerBn',   icon: <ClipboardList size={16} /> },
  { key: 'campaign', labelKey: 'ciprb.tabCampaign', labelBnKey: 'ciprb.tabCampaignBn', icon: <Megaphone size={16} /> },
]

// ─── KPI band ────────────────────────────────────────────────────────────────

interface KPIs {
  suspected: number
  identified: number
  referred: number
  surgeryDone: number
}

interface CornerCaseRow {
  identification_date?: string | null
  diagnosis_date?: string | null
  referral_date?: string | null
  referral_outcome?: string
  surgery_performed?: 'yes' | 'no' | 'pending' | ''
}

interface CampaignVisitRow {
  id: string
}

function useFistulaKPIs(): { kpis: KPIs; loading: boolean } {
  const [kpis, setKpis] = useState<KPIs>({ suspected: 0, identified: 0, referred: 0, surgeryDone: 0 })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    Promise.allSettled([
      api.get<{ results?: CampaignVisitRow[] } | CampaignVisitRow[]>('/fistula/campaign-visits/'),
      api.get<{ results?: CornerCaseRow[]    } | CornerCaseRow[]>('/fistula/corner-cases/'),
    ]).then(([campaignRes, cornerRes]) => {
      if (cancelled) return

      const campaignRows: CampaignVisitRow[] =
        campaignRes.status === 'fulfilled'
          ? (Array.isArray(campaignRes.value.data)
              ? campaignRes.value.data
              : campaignRes.value.data.results ?? [])
          : []

      const cornerRows: CornerCaseRow[] =
        cornerRes.status === 'fulfilled'
          ? (Array.isArray(cornerRes.value.data)
              ? cornerRes.value.data
              : cornerRes.value.data.results ?? [])
          : []

      // Suspected = field screening (every campaign visit is a screening attempt).
      // Identified = corner cases with a confirmed identification/diagnosis date.
      // Referred = corner cases with a referral date OR non-empty referral outcome.
      // Surgery Done = corner cases where surgery_performed === 'yes'.
      const suspected   = campaignRows.length
      const identified  = cornerRows.filter(c => c.identification_date || c.diagnosis_date).length
      const referred    = cornerRows.filter(c => c.referral_date || (c.referral_outcome ?? '').trim() !== '').length
      const surgeryDone = cornerRows.filter(c => c.surgery_performed === 'yes').length

      setKpis({ suspected, identified, referred, surgeryDone })
      setLoading(false)
    })

    return () => { cancelled = true }
  }, [])

  return { kpis, loading }
}

function KPITile({
  icon, label, sub, value, accent = CIPRB_BLUE,
}: {
  icon: React.ReactNode
  label: string
  sub: string
  value: number
  accent?: string
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
          background: `${accent}1A`, color: accent,
        }}>
          {icon}
        </span>
        {label}
      </div>
      <div style={{
        fontSize: 30, fontWeight: 800, color: 'var(--ink)',
        fontVariantNumeric: 'tabular-nums', lineHeight: 1, letterSpacing: '-0.02em',
      }}>
        {value.toLocaleString()}
      </div>
      <div style={{ fontSize: 12, color: 'var(--ink-3)' }}>
        {sub}
      </div>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function FistulaTracker() {
  const { t } = useTranslation()
  const [active, setActive] = useState<TabKey>('corner')
  const reduce = useReducedMotion()
  const activeTab = TABS.find((tab) => tab.key === active)!
  const { kpis } = useFistulaKPIs()

  return (
    <>
      {/* ───────────────── Hero ───────────────── */}
      <section className="hero" style={{ paddingBottom: 24 }}>
        <div className="hero-eyebrow anim-rise">
          <span className="live-dot" />
          <span>{t('ciprb.heroEyebrow')}</span>
          <span className="sep">/</span>
          <span>{t('ciprb.heroEyebrowSub')}</span>
        </div>
        <h1
          className="hero-headline anim-rise d1"
          style={{
            marginBottom: 14,
            fontSize: 'clamp(48px, 7vw, 96px)',
            letterSpacing: '-0.035em',
            fontStyle: 'normal',
            fontWeight: 800,
            color: CIPRB_BLUE,
          }}
        >
          {t('ciprb.heroHeadline')}
        </h1>
        <p className="hero-lede anim-rise d2" style={{ maxWidth: 720 }}>
          {t('ciprb.heroLede')}
        </p>
      </section>

      {/* ───────────────── KPI band (4 tiles) ───────────────── */}
      <section className="section" style={{ marginTop: 0, marginBottom: 12 }}>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: 12,
          }}
        >
          <KPITile
            icon={<Search size={14} />}
            label={t('ciprb.kpiSuspected')}
            sub={t('ciprb.kpiSuspectedSub')}
            value={kpis.suspected}
          />
          <KPITile
            icon={<Stethoscope size={14} />}
            label={t('ciprb.kpiIdentified')}
            sub={t('ciprb.kpiIdentifiedSub')}
            value={kpis.identified}
          />
          <KPITile
            icon={<Send size={14} />}
            label={t('ciprb.kpiReferred')}
            sub={t('ciprb.kpiReferredSub')}
            value={kpis.referred}
          />
          <KPITile
            icon={<Scissors size={14} />}
            label={t('ciprb.kpiSurgeryDone')}
            sub={t('ciprb.kpiSurgeryDoneSub')}
            value={kpis.surgeryDone}
          />
        </div>
      </section>

      {/* ───── Donor coverage map (Dr. Sayeed, 27 September 2026) ───── */}
      <section className="section" style={{ marginTop: 8 }}>
        <DonorDistrictMap project="fistula" />
      </section>

      {/* ───────────────── Tabs ───────────────── */}
      <section className="section" style={{ marginTop: 8 }}>
        <div
          role="tablist"
          aria-label="CIPRB registers"
          style={{
            display: 'flex', flexWrap: 'wrap', gap: 8,
            padding: 6,
            background: 'var(--surface-2)',
            borderRadius: 14,
            border: '1px solid var(--hair)',
            width: 'fit-content',
            marginBottom: 24,
          }}
        >
          {TABS.map((tab) => {
            const isActive = active === tab.key
            return (
              <button
                key={tab.key}
                role="tab"
                aria-selected={isActive}
                onClick={() => setActive(tab.key)}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 8,
                  padding: '8px 14px',
                  fontSize: 13.5,
                  fontWeight: isActive ? 600 : 500,
                  color: isActive ? '#fff' : 'var(--ink-2)',
                  background: isActive ? CIPRB_BLUE : 'transparent',
                  border: 'none',
                  borderRadius: 10,
                  cursor: 'pointer',
                  transitionProperty: 'background-color, color',
                  transitionDuration: '180ms',
                }}
              >
                {tab.icon}
                <span>{t(tab.labelKey)}</span>
              </button>
            )
          })}
        </div>

        {/* ───────────── Tab body ───────────── */}
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab.key}
            initial={{ opacity: 0, y: reduce ? 0 : 8 }}
            animate={{
              opacity: 1, y: 0,
              transition: { duration: 0.25, ease: [0.22, 1, 0.36, 1] },
            }}
            exit={{
              opacity: 0, y: reduce ? 0 : -6,
              transition: { duration: 0.16, ease: [0.4, 0, 1, 1] },
            }}
          >
            {activeTab.key === 'corner'
              ? <FistulaCornerPanel />
              : <FistulaCampaignPanel />}
          </motion.div>
        </AnimatePresence>
      </section>

      <div style={{ height: 80 }} />
    </>
  )
}
