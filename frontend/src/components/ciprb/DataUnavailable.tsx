/**
 * Explicit "data source unreachable" state for CIPRB panels.
 *
 * Every CIPRB data hook used to collapse a FETCH FAILURE into zeros or a
 * reassuring "no data yet" empty state — so a broken endpoint looked identical
 * to a genuinely empty programme. That is the exact class of bug that let the
 * dashboard show 0 deaths over real data. A failed load must say so, and must
 * never be mistaken for "the number is 0".
 *
 * Render this when a hook reports an error. It is visually distinct from the
 * ordinary empty state (amber, not muted) precisely so the two can never be
 * confused at a glance.
 */
import { AlertTriangle } from 'lucide-react'

export function DataUnavailable({ label, onRetry }: { label: string; onRetry?: () => void }) {
  return (
    <div
      className="card"
      role="alert"
      style={{
        padding: '26px 22px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 10,
        textAlign: 'center',
        border: '1px solid rgba(180, 83, 9, 0.35)',
        background: 'rgba(180, 83, 9, 0.06)',
      }}
    >
      <AlertTriangle size={20} style={{ color: '#B45309', flexShrink: 0 }} />
      <div style={{ fontSize: 13.5, fontWeight: 600, color: '#8A4200' }}>
        {label} could not be loaded
      </div>
      <div style={{ fontSize: 12, color: 'var(--muted)', maxWidth: 460, lineHeight: 1.5 }}>
        The data source did not respond. This is a loading error, not an empty
        result — the figures below are unavailable, not zero.
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          style={{
            marginTop: 4,
            fontSize: 12.5,
            fontWeight: 600,
            color: '#8A4200',
            background: 'transparent',
            border: '1px solid rgba(180, 83, 9, 0.4)',
            borderRadius: 8,
            padding: '5px 14px',
            cursor: 'pointer',
          }}
        >
          Retry
        </button>
      )}
    </div>
  )
}
