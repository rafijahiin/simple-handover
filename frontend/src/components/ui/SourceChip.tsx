import React from 'react'

/** Prominent provenance chip shown in a chart's header — names the Kobo form
 *  that feeds the chart. Replaces the old bottom-of-chart DataSource footnote. */
export function SourceChip({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <span
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 4,
        fontSize: 10.5, fontWeight: 600, lineHeight: 1.4,
        color: 'var(--ink-3, #6B7280)',
        background: 'var(--chip-bg, rgba(127,127,127,0.10))',
        border: '1px solid var(--hairline, rgba(127,127,127,0.16))',
        borderRadius: 999, padding: '2px 9px', whiteSpace: 'nowrap',
        ...style,
      }}
    >
      <span aria-hidden>📄</span>
      <span style={{ opacity: 0.65 }}>Source:</span>
      <span>{children}</span>
    </span>
  )
}
