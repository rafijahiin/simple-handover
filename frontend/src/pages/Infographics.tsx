/**
 * Infographics — one shareable card per indicator.
 *
 * Solves the spec's "auto-generated infographic cards per indicator"
 * requirement: each card is a designed one-pager with the partner accent,
 * the headline number, target, percentage band, and a small bar. A "Save
 * as PNG" button per card uses modern-screenshot (already in the bundle
 * for the Topbar export) to dump a 1080×1080 PNG ready for WhatsApp
 * or email forwarding.
 *
 * Permission: any authenticated user. Records the card is built from are
 * already filtered server-side by the indicator progress endpoint —
 * managers / focal see only their own partner; supervisors see all.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Download } from 'lucide-react'
import { api } from '@/api/client'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { PARTNER_COLORS, type PartnerCode } from '@/data/partnerDistricts'
import { bnIndicatorLabel, bnUnit } from '@/data/indicatorLabelsBn'
import type { IndicatorProgress } from '@/types'

const PARTNER_LABELS: Record<PartnerCode, string> = {
  CIPRB: 'CIPRB',
  Bandhu: 'Bandhu Social Welfare Society',
  PHD: 'Partners in Health and Development',
}

// Same band thresholds the indicator cards use everywhere else.
function bandColour(pct: number | null): string {
  if (pct == null) return '#9CA3AF'
  if (pct >= 75) return '#00B050'
  if (pct >= 40) return '#FFC000'
  return '#FF0000'
}
function bandLabel(pct: number | null): string {
  if (pct == null) return 'Not Set'
  if (pct >= 75) return 'On Track'
  if (pct >= 40) return 'Behind'
  return 'Critical'
}

// ─── Card ────────────────────────────────────────────────────────────────────
//
// Renders at fixed pixel dimensions (1080×1080) so the PNG export is
// always square and shareable. The visible card on the page is a CSS
// scale-down to ~360px wide; the export captures the underlying full-size
// node so the PNG is high-resolution.

interface CardProps { row: IndicatorProgress; partner: PartnerCode }

function InfographicCard({ row, partner }: CardProps) {
  const { t, i18n } = useTranslation()
  const accent = PARTNER_COLORS[partner]
  const band = bandColour(row.percentage)
  const isBn = i18n.language?.startsWith('bn')
  const indicator = isBn
    ? bnIndicatorLabel(partner, row.activity_code, row.indicator_label)
    : row.indicator_label
  const unitLabel = isBn ? bnUnit(row.unit) : row.unit
  const fmt = (n: number) =>
    n.toLocaleString(isBn ? 'bn-BD' : 'en-US')

  const cardId = `infograph-${partner}-${row.activity_code}`

  const handleExport = async () => {
    const { domToPng } = await import('modern-screenshot')
    const node = document.getElementById(cardId)
    if (!node) return
    const png = await domToPng(node, {
      width: 1080, height: 1080, scale: 1,
      backgroundColor: '#FFFFFF',
    })
    const a = document.createElement('a')
    a.href = png
    a.download = `SIMPLE_${partner}_${row.activity_code}.png`
    a.click()
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {/* Display wrapper — visible card scaled down */}
      <div style={{
        width: 360, height: 360,
        overflow: 'hidden',
        borderRadius: 16,
        border: '1px solid var(--hair)',
        background: 'var(--surface)',
        boxShadow: 'var(--sh-1)',
      }}>
        <div style={{
          width: 1080, height: 1080,
          transform: 'scale(0.333)',
          transformOrigin: '0 0',
        }}>
          {/* The actual high-res card */}
          <div
            id={cardId}
            style={{
              width: 1080, height: 1080,
              background: '#FFFFFF',
              padding: 80,
              display: 'flex', flexDirection: 'column',
              fontFamily: 'Atkinson Hyperlegible, Noto Sans Bengali, sans-serif',
              color: '#131619',
              position: 'relative',
              boxSizing: 'border-box',
            }}
          >
            {/* Top: partner badge + period */}
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              marginBottom: 32,
            }}>
              <span style={{
                display: 'inline-flex', alignItems: 'center', gap: 16,
                padding: '12px 24px',
                borderRadius: 999,
                background: `${accent}15`,
                color: accent,
                fontWeight: 700, fontSize: 28,
                letterSpacing: '0.05em', textTransform: 'uppercase',
              }}>
                <span style={{
                  width: 14, height: 14, borderRadius: 999, background: accent,
                }} />
                {partner}
              </span>
              <span style={{
                fontSize: 22, color: '#686A6C',
                fontFamily: 'JetBrains Mono, monospace',
                letterSpacing: '0.06em', textTransform: 'uppercase',
              }}>
                {row.activity_code}
              </span>
            </div>

            {/* Indicator title */}
            <h2 style={{
              fontSize: 44, lineHeight: 1.15, margin: 0,
              fontWeight: 700, letterSpacing: '-0.02em',
              color: '#131619',
              wordBreak: 'break-word',
            }}>
              {indicator}
            </h2>

            {/* Big number block */}
            <div style={{
              marginTop: 'auto', marginBottom: 'auto',
              display: 'flex', alignItems: 'baseline', gap: 32, flexWrap: 'wrap',
            }}>
              <div style={{
                fontSize: 220, fontWeight: 700, lineHeight: 0.9,
                color: '#131619', fontVariantNumeric: 'tabular-nums',
                letterSpacing: '-0.04em',
              }}>
                {fmt(row.achievement ?? 0)}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {row.target_value != null ? (
                  <>
                    <div style={{ fontSize: 36, color: '#686A6C',
                                  fontVariantNumeric: 'tabular-nums' }}>
                      / {fmt(row.target_value)}
                    </div>
                    <div style={{ fontSize: 22, color: '#9CA1A9',
                                  textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                      {unitLabel}
                    </div>
                  </>
                ) : (
                  <div style={{
                    padding: '8px 16px', borderRadius: 999,
                    background: '#FED7AA', color: '#9A3412',
                    fontWeight: 600, fontSize: 22,
                  }}>
                    Target — Not Set
                  </div>
                )}
              </div>
            </div>

            {/* Percentage + band pill + bar */}
            <div style={{ marginBottom: 48 }}>
              <div style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
                marginBottom: 16,
              }}>
                <span style={{
                  fontSize: 60, fontWeight: 700, color: band,
                  fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.02em',
                }}>
                  {row.percentage != null ? `${Math.round(row.percentage)}%` : '—'}
                </span>
                <span style={{
                  padding: '10px 24px', borderRadius: 999,
                  background: `${band}22`, color: band,
                  fontWeight: 700, fontSize: 24, letterSpacing: '0.05em',
                  textTransform: 'uppercase',
                }}>
                  {bandLabel(row.percentage)}
                </span>
              </div>
              {row.target_value != null && (
                <div style={{
                  width: '100%', height: 12, borderRadius: 999,
                  background: '#EFF1F7', overflow: 'hidden',
                }}>
                  <div style={{
                    width: `${Math.min(row.percentage ?? 0, 100)}%`,
                    height: '100%', background: band,
                  }} />
                </div>
              )}
            </div>

            {/* Footer */}
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end',
              fontSize: 22, color: '#686A6C',
            }}>
              <span style={{ maxWidth: 600, lineHeight: 1.4 }}>
                {PARTNER_LABELS[partner]}
              </span>
              <span style={{
                fontWeight: 700, color: '#F96000',
                fontSize: 32, letterSpacing: '-0.01em',
              }}>
                SIMPLE
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Below-card metadata + export button */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 11, color: 'var(--muted)', fontFamily: 'var(--mono)' }}>
          {partner} · {row.activity_code}
        </span>
        <button
          onClick={handleExport}
          className="no-export"
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '6px 14px', borderRadius: 999,
            border: '1px solid var(--hair-2)', background: 'var(--surface)',
            color: 'var(--ink)', fontSize: 12, fontWeight: 500,
            cursor: 'pointer',
          }}
        >
          <Download size={13} />
          {t('infographics.savePng', { defaultValue: 'Save as PNG' })}
        </button>
      </div>
    </div>
  )
}

// ─── Main page ───────────────────────────────────────────────────────────────

export default function Infographics() {
  const { t } = useTranslation()
  const [rows, setRows] = useState<(IndicatorProgress & { organisation: PartnerCode })[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [partnerFilter, setPartnerFilter] = useState<'all' | PartnerCode>('all')

  useEffect(() => {
    api.get<(IndicatorProgress & { organisation: PartnerCode })[]>(
      '/indicators/progress/?period_start=2026-05-21&period_end=2026-11-20'
    )
      .then((r) => setRows(r.data))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <PageLoader />

  const filtered = (rows ?? []).filter((r) =>
    partnerFilter === 'all' ? true : r.organisation === partnerFilter
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
      {/* Hero */}
      <section className="hero" style={{ paddingBottom: 8 }}>
        <div className="hero-eyebrow">
          <span className="live-dot" />
          <span>{t('infographics.eyebrow', { defaultValue: 'REPORTS · INFOGRAPHIC CARDS' })}</span>
        </div>
        <h1 className="hero-headline" style={{
          fontSize: 'clamp(40px, 5.5vw, 64px)',
          letterSpacing: '-0.03em', marginBottom: 10,
        }}>
          {t('infographics.title', { defaultValue: 'Shareable Indicator Cards' })}
        </h1>
        <p className="hero-lede" style={{ maxWidth: 640 }}>
          {t('infographics.subtitle', {
            defaultValue: 'One designed card per indicator — click Save as PNG and forward via WhatsApp or email.',
          })}
        </p>
      </section>

      {/* Partner filter */}
      <section className="section" style={{ marginTop: -8 }}>
        <div role="tablist" aria-label="Partner filter" style={{
          display: 'inline-flex', gap: 4, padding: 4,
          background: 'var(--surface-2)', border: '1px solid var(--hair)', borderRadius: 999,
        }}>
          {(['all', 'CIPRB', 'PHD', 'Bandhu'] as const).map((p) => {
            const active = partnerFilter === p
            return (
              <button
                key={p} role="tab" aria-selected={active}
                onClick={() => setPartnerFilter(p)}
                style={{
                  padding: '6px 14px', borderRadius: 999,
                  fontSize: 13, fontWeight: 500, border: 'none', cursor: 'pointer',
                  background: active ? 'var(--unfpa)' : 'transparent',
                  color: active ? '#fff' : 'var(--ink-3)',
                }}
              >
                {p === 'all' ? t('infographics.allPartners', { defaultValue: 'All Partners' }) : p}
              </button>
            )
          })}
        </div>
      </section>

      {/* Grid of cards */}
      <section className="section" style={{ marginTop: 0, marginBottom: 48 }}>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))',
          gap: 24,
        }}>
          {filtered.map((r) => (
            <InfographicCard
              key={`${r.organisation}-${r.activity_code}`}
              row={r}
              partner={r.organisation as PartnerCode}
            />
          ))}
        </div>
        {filtered.length === 0 && (
          <div className="card" style={{
            padding: '48px 16px', textAlign: 'center',
            borderStyle: 'dashed', borderColor: 'var(--hair-2)',
          }}>
            <p style={{ color: 'var(--muted)', fontSize: 13, margin: 0 }}>
              {t('infographics.empty', { defaultValue: 'No indicators to show for this partner.' })}
            </p>
          </div>
        )}
      </section>
    </div>
  )
}
