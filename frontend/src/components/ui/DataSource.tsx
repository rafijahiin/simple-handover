/**
 * DataSource — small italic footnote naming the Kobo form(s) feeding a
 * dashboard surface. Renders inline below the chart/table.
 *
 * Animesh asked for provenance on every visualisation so reviewers can
 * trace any number on screen back to the exact field-form it comes from.
 * Keep it ~10px, muted, italic — informative without competing for
 * attention with the data itself.
 */
import React from 'react'

export function DataSource({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <p
      style={{
        fontSize: 10,
        color: 'var(--muted)',
        fontStyle: 'italic',
        margin: '6px 2px 0',
        opacity: 0.75,
        ...style,
      }}
    >
      <span style={{ fontWeight: 600 }}>Source:</span> {children}
    </p>
  )
}
