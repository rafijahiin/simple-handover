/**
 * AnomalyCards — render the current findings from /api/tracker/anomalies/
 *
 * Used on the homepage (no partner filter → cross-org view) and on each
 * org dashboard (partner-filtered automatically by the backend, since
 * single-org users can only see their own anyway).
 *
 * Empty state: a quiet "All clear" pill. Loading: shimmer skeleton.
 * Error: small inline retry. Each card is colour-banded by severity
 * using UNFPA accent palette:
 *   critical → UNFPA Red    (#F10F45)
 *   warning  → UNFPA Orange (#F96000)  ← brand primary at low alpha
 *   info     → UNFPA Blue   (#2171EC)
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { motion, useReducedMotion } from 'motion/react'
import {
  AlertOctagon, AlertTriangle, Info, CheckCircle2, RefreshCw,
} from 'lucide-react'
import { api } from '@/api/client'

interface Finding {
  type: 'mom_drop' | 'pace_behind' | 'submission_gap' | 'backlog'
  severity: 'info' | 'warning' | 'critical'
  partner: string | null
  indicator: string | null
  title: string
  message: string
  value: number | string
  baseline: number | string
  detected_at: string
}

interface Props {
  /** Optional partner filter. If omitted, the backend returns findings
   *  for whichever partners the user can see. */
  partner?: 'PHD' | 'Bandhu' | 'CIPRB'
}

const SEVERITY_META: Record<Finding['severity'], {
  color: string
  bg: string
  icon: React.ReactNode
  label: string
}> = {
  critical: {
    color: '#F10F45',
    bg: 'rgba(241, 15, 69, 0.08)',
    icon: <AlertOctagon size={14} />,
    label: 'CRITICAL',
  },
  warning: {
    color: '#AE4300',
    bg: 'rgba(204, 106, 0, 0.10)',
    icon: <AlertTriangle size={14} />,
    label: 'WARNING',
  },
  info: {
    color: '#2171EC',
    bg: 'rgba(33, 113, 236, 0.08)',
    icon: <Info size={14} />,
    label: 'INFO',
  },
}

export function AnomalyCards({ partner }: Props) {
  const { t } = useTranslation()
  const reduce = useReducedMotion()
  const [findings, setFindings] = useState<Finding[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchFindings = async () => {
    setLoading(true)
    setError(null)
    try {
      const url = partner
        ? `/tracker/anomalies/?partner=${partner}`
        : `/tracker/anomalies/`
      const resp = await api.get<{ results: Finding[] }>(url)
      setFindings(resp.data.results || [])
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Could not load anomalies.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchFindings()
    // Refresh every 5 minutes.
    const id = setInterval(fetchFindings, 5 * 60_000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [partner])

  return (
    <section className="section" style={{ marginTop: 36 }}>
      <div className="section-head" style={{ marginBottom: 16 }}>
        <div>
          <div className="kicker" style={{ marginBottom: 6 }}>
            <span className="dot" style={{ background: 'var(--unfpa)' }} />
            {t('anomalies.kicker', { defaultValue: 'ANOMALY DETECTION' })}
          </div>
          <h2 className="section-title">
            {t('anomalies.title', { defaultValue: 'Programme health flags' })}
          </h2>
          <p className="section-sub">
            {t('anomalies.subtitle', {
              defaultValue:
                "Automated checks for submission drops, indicators behind pace, and review backlogs.",
            })}
          </p>
        </div>
        <button
          onClick={fetchFindings}
          disabled={loading}
          className="lang-toggle-btn"
          title={t('anomalies.refresh', { defaultValue: 'Refresh' })}
          style={{
            width: 32, height: 32, borderRadius: 999,
            background: 'var(--surface-2)',
            border: '1px solid var(--hair)',
            color: 'var(--ink-3)', cursor: 'pointer',
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          }}
        >
          <RefreshCw size={13} />
        </button>
      </div>

      {/* Loading skeleton */}
      {loading && findings === null && (
        <div style={{ display: 'grid', gap: 10 }}>
          {[0, 1, 2].map((i) => (
            <div key={i} className="ai-skeleton" style={{ height: 64, borderRadius: 12 }} />
          ))}
        </div>
      )}

      {/* Error */}
      {!loading && error && (
        <div
          className="card"
          style={{
            padding: 16, fontSize: 13, color: '#9A1131',
            background: 'rgba(241, 15, 69, 0.05)',
            border: '1px solid rgba(241, 15, 69, 0.18)',
          }}
        >
          {error}
          <button
            onClick={fetchFindings}
            style={{
              marginLeft: 8, padding: '4px 10px', fontSize: 12,
              border: '1px solid var(--hair)', borderRadius: 6,
              background: 'var(--surface)', color: 'var(--ink)',
              cursor: 'pointer',
            }}
          >
            {t('anomalies.retry', { defaultValue: 'Retry' })}
          </button>
        </div>
      )}

      {/* Empty state — "all clear" */}
      {!loading && !error && findings !== null && findings.length === 0 && (
        <div
          className="card"
          style={{
            padding: '18px 22px', display: 'flex', alignItems: 'center', gap: 12,
            background: 'rgba(88, 150, 138, 0.08)',
            border: '1px solid rgba(88, 150, 138, 0.20)',
          }}
        >
          <CheckCircle2 size={18} style={{ color: '#015A28', flexShrink: 0 }} />
          <div>
            <div style={{ fontWeight: 600, color: 'var(--ink)' }}>
              {t('anomalies.clearTitle', { defaultValue: 'All systems clear' })}
            </div>
            <div style={{ fontSize: 12.5, color: 'var(--ink-3)', marginTop: 2 }}>
              {t('anomalies.clearSub', {
                defaultValue: 'No anomalies detected. Submissions, indicator pace, and approval queues are healthy.',
              })}
            </div>
          </div>
        </div>
      )}

      {/* Finding cards */}
      {!loading && !error && findings !== null && findings.length > 0 && (
        <div style={{ display: 'grid', gap: 10 }}>
          {findings.map((f, i) => {
            const meta = SEVERITY_META[f.severity]
            return (
              <motion.div
                key={`${f.type}-${f.partner}-${f.indicator || ''}-${i}`}
                initial={{ opacity: 0, y: reduce ? 0 : 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{
                  duration: 0.3, delay: reduce ? 0 : i * 0.04,
                  ease: [0.22, 1, 0.36, 1],
                }}
                className="card"
                style={{
                  padding: '14px 18px',
                  borderLeft: `3px solid ${meta.color}`,
                  background: meta.bg,
                  display: 'grid',
                  gridTemplateColumns: 'auto 1fr auto',
                  gap: 14, alignItems: 'flex-start',
                }}
              >
                <span style={{
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  width: 28, height: 28, borderRadius: 8,
                  background: 'var(--surface)', color: meta.color,
                  flexShrink: 0, marginTop: 1,
                }}>
                  {meta.icon}
                </span>

                <div style={{ minWidth: 0 }}>
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4,
                    flexWrap: 'wrap',
                  }}>
                    <span style={{
                      fontSize: 10, fontWeight: 700, color: meta.color,
                      letterSpacing: '0.08em', textTransform: 'uppercase',
                    }}>
                      {meta.label}
                    </span>
                    {f.partner && (
                      <span style={{
                        fontSize: 10, fontWeight: 600, color: 'var(--ink-3)',
                        letterSpacing: '0.04em',
                      }}>
                        · {f.partner}
                      </span>
                    )}
                    {f.indicator && (
                      <span style={{
                        fontSize: 10, fontWeight: 600, color: 'var(--ink-3)',
                        fontFamily: 'var(--mono)',
                      }}>
                        · {f.indicator}
                      </span>
                    )}
                  </div>
                  <div style={{
                    fontSize: 14, fontWeight: 700, color: 'var(--ink)',
                    marginBottom: 4,
                  }}>
                    {f.title}
                  </div>
                  <div style={{
                    fontSize: 12.5, color: 'var(--ink-3)', lineHeight: 1.5,
                    textWrap: 'pretty',
                  } as React.CSSProperties}>
                    {f.message}
                  </div>
                </div>

                <span style={{
                  fontSize: 10, color: 'var(--muted)', flexShrink: 0,
                  fontVariantNumeric: 'tabular-nums',
                }}>
                  {new Date(f.detected_at).toLocaleTimeString('en-GB', {
                    hour: '2-digit', minute: '2-digit',
                  })}
                </span>
              </motion.div>
            )
          })}
        </div>
      )}
    </section>
  )
}
