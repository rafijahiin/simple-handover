/**
 * ProgrammeBreakdown — the activity-by-category donut (Clinical / Community /
 * Operations), fed by /dashboard/activity-breakdown/.
 *
 * Per-partner attainment lives only in the "Three partners at a glance" cards;
 * it is not repeated here. No time-series (this is a short, ~5-month
 * programme). Sits with the Executive Summary, lower on the page.
 *
 * Degrades to a calm empty state before real data exists.
 */
import { useEffect, useState } from 'react'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import { useTranslation } from 'react-i18next'
import { api } from '@/api/client'

const CATEGORY_COLORS: Record<string, string> = {
  Clinical:   '#F96000',   // UNFPA orange — brand primary
  Community:  '#ED5B7E',   // coral — warm secondary
  Operations: '#2171EC',   // UNFPA teal-blue — distinct hue
}

function DonutTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null
  const p = payload[0]
  return (
    <div className="card" style={{ padding: '8px 12px', fontSize: 12, border: '1px solid var(--hair)' }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        <span style={{ width: 8, height: 8, borderRadius: '50%', background: p.payload.color }} />
        {p.name}: <b style={{ fontVariantNumeric: 'tabular-nums' }}>{(p.value ?? 0).toLocaleString()}</b>
      </span>
    </div>
  )
}

export function ProgrammeBreakdown() {
  const { t } = useTranslation()
  const [cats, setCats] = useState<Record<string, number> | null>(null)

  useEffect(() => {
    api.get('/dashboard/activity-breakdown/')
      .then((r) => setCats(r.data?.categories ?? {}))
      .catch(() => setCats({}))
  }, [])

  const donutData = ['Clinical', 'Community', 'Operations'].map((name) => ({
    name, value: cats?.[name] ?? 0, color: CATEGORY_COLORS[name],
  }))
  const donutTotal = donutData.reduce((s, d) => s + d.value, 0)

  return (
    <section className="section programme-breakdown" style={{ marginTop: 36 }}>
      <div className="section-head">
        <div>
          <div className="kicker" style={{ marginBottom: 8 }}>
            <span className="dot" style={{ background: 'var(--unfpa)' }} />
            {t('home.breakdownKicker', { defaultValue: 'PROGRAMME BREAKDOWN' })}
          </div>
          <h2 className="section-title">{t('home.breakdownTitle', { defaultValue: 'Where activity sits' })}</h2>
          <p className="section-sub">
            {t('home.breakdownSub', { defaultValue: 'Approved & pending submissions across the programme, by service category.' })}
          </p>
        </div>
      </div>

      <div className="card" style={{ padding: 24 }}>
        {donutTotal > 0 ? (
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            gap: 36, flexWrap: 'wrap',
          }}>
            <div style={{ position: 'relative', width: 196, height: 196, flexShrink: 0 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={donutData} dataKey="value" nameKey="name" cx="50%" cy="50%"
                    innerRadius={64} outerRadius={92} paddingAngle={2} stroke="none"
                    startAngle={90} endAngle={-270} animationDuration={800}>
                    {donutData.map((d) => <Cell key={d.name} fill={d.color} />)}
                  </Pie>
                  <Tooltip content={<DonutTooltip />} />
                </PieChart>
              </ResponsiveContainer>
              <div style={{
                position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
                alignItems: 'center', justifyContent: 'center', pointerEvents: 'none',
              }}>
                <span style={{ fontSize: 34, fontWeight: 700, lineHeight: 1, color: 'var(--ink)', fontVariantNumeric: 'tabular-nums' }}>
                  {donutTotal.toLocaleString()}
                </span>
                <span className="mono" style={{ fontSize: 9.5, color: 'var(--muted)', letterSpacing: '0.08em', marginTop: 2 }}>TOTAL</span>
              </div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, minWidth: 220, maxWidth: 320, flex: 1 }}>
              {donutData.map((d) => (
                <div key={d.name} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 14 }}>
                  <span style={{ width: 11, height: 11, borderRadius: 3, background: d.color, flexShrink: 0 }} />
                  <span style={{ flex: 1, color: 'var(--ink-2)' }}>{d.name}</span>
                  <b style={{ fontVariantNumeric: 'tabular-nums' }}>{d.value.toLocaleString()}</b>
                  <span className="mute" style={{ fontSize: 11.5, width: 40, textAlign: 'right' }}>
                    {donutTotal ? Math.round((d.value / donutTotal) * 100) : 0}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <EmptyState
            label={cats === null ? '' : t('home.breakdownEmpty', { defaultValue: 'No service activity recorded yet' })}
            sub={cats === null ? '' : t('home.breakdownEmptySub', { defaultValue: 'The donut fills as clinical, community and operations submissions arrive.' })}
          />
        )}
      </div>
    </section>
  )
}

function EmptyState({ label, sub }: { label: string; sub: string }) {
  return (
    <div style={{
      height: 196, display: 'flex', flexDirection: 'column', gap: 6,
      alignItems: 'center', justifyContent: 'center', textAlign: 'center',
      color: 'var(--muted)', padding: '0 12px',
    }}>
      {label && <span style={{ fontSize: 13.5, color: 'var(--ink-3)' }}>{label}</span>}
      {sub && <span style={{ fontSize: 12 }}>{sub}</span>}
    </div>
  )
}
