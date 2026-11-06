import { useEffect, useState } from 'react'
import { ListChecks } from 'lucide-react'
import { api } from '@/api/client'
import { SourceChip } from '@/components/ui/SourceChip'
import { DataUnavailable } from '@/components/ciprb/DataUnavailable'

const CIPRB_ORANGE = '#F96000'

// ── Types mirror /api/mpdsr/action-aggregates/ ──────────────────────────────
interface LiveAction {
  action_id: string
  district: string
  section_label: string
  sub_category: string
  sub_category_label?: string
  activity: string
  responsible: string
  timeline: string | null
  status: string
  status_label: string
  completion_pct: number
  completion_date: string | null
  is_overdue: boolean
}
interface Rollup { key: string; pct: number; n: number }
interface StatusRow { status: string; label: string; count: number }
interface ActionAggregates {
  overall_pct: number
  total: number
  overdue: number
  by_status: StatusRow[]
  by_district: Rollup[]
  by_section: Rollup[]
  actions: LiveAction[]
}

// Completion-health colour, on the UNFPA data-viz palette: green ≥75,
// orange 40-74, coral <40 (cohesive with the rest of the CIPRB dashboard).
const compColor = (pct: number) => (pct >= 75 ? '#58968A' : pct >= 40 ? '#FB904D' : '#ED5B7E')

// Per-status palette for the breakdown bar — the form (CIPRB-10) carries FIVE
// statuses, so each gets a distinct UNFPA-palette hue. Active states (done /
// active / slipping) read in colour; inactive states stay quiet and apart:
// pending = light silver ("not started", recedes), dropped = muted violet
// ("set aside") — a different HUE from pending so the two never blur together.
const STATUS_COLOR: Record<string, string> = {
  implemented: '#58968A', // UNFPA viz green  — done
  in_progress: '#649BF2', // UNFPA viz blue   — active
  delayed:     '#FB904D', // UNFPA viz orange — slipping
  pending:     '#C3C8D2', // light silver     — not started
  dropped:     '#A37FB4', // muted violet     — set aside
}

function Bars({ rows }: { rows: Rollup[] }) {
  if (!rows.length) return <div style={{ fontSize: 12.5, color: 'var(--muted)' }}>—</div>
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {rows.map((r) => (
        <div key={r.key} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 140, fontSize: 12.5, color: 'var(--ink-2)', textAlign: 'right', flexShrink: 0 }}>
            {r.key} <span style={{ color: 'var(--muted)' }}>({r.n})</span>
          </div>
          <div style={{ flex: 1, height: 16, background: 'var(--hair-2)', borderRadius: 4, overflow: 'hidden' }}>
            <div style={{ width: `${r.pct}%`, height: '100%', background: compColor(r.pct), transition: 'width .4s ease' }} />
          </div>
          <div style={{ width: 42, fontSize: 12.5, fontWeight: 700, color: compColor(r.pct), textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
            {r.pct}%
          </div>
        </div>
      ))}
    </div>
  )
}

// BY DISTRICT is a plain bar chart of the number of actions each district has
// recorded (RCH review, 23 Aug 2026). One bar carries ONE variable: the count.
//
// The first pass kept the old full-width grey track and tinted the bar by
// completion. That read as a percentage bar with two variables fighting inside
// it: a district on 22 actions and 9% completion showed a part-filled pink bar
// that looked like "9% done" measured against a whole. No track, one colour,
// and completion demoted to a coloured number on the right, so the bar means
// exactly what the caption says it means.
function CountBars({ rows }: { rows: Rollup[] }) {
  if (!rows.length) return <div style={{ fontSize: 12.5, color: 'var(--muted)' }}>—</div>
  const ranked = [...rows].sort((a, b) => b.n - a.n)
  const max = Math.max(...ranked.map((r) => r.n), 1)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
      {ranked.map((r) => (
        <div key={r.key} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 106, fontSize: 12.5, color: 'var(--ink-2)', textAlign: 'right', flexShrink: 0 }}>
            {r.key}
          </div>
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
            {/* minWidth keeps a one-action district visible instead of a sliver. */}
            <div style={{
              width: `${(r.n / max) * 100}%`, minWidth: 4, height: 15,
              background: CIPRB_ORANGE, borderRadius: 3, transition: 'width .4s ease',
            }} />
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--ink)', fontVariantNumeric: 'tabular-nums' }}>
              {r.n}
            </div>
          </div>
          <div style={{ width: 42, fontSize: 11.5, color: compColor(r.pct), textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
            {r.pct}%
          </div>
        </div>
      ))}
    </div>
  )
}

function StatusBreakdown({ rows, total }: { rows: StatusRow[]; total: number }) {
  const shown = rows.filter((r) => r.count > 0)
  if (!total) return null
  return (
    <div>
      <div className="mono" style={{ fontSize: 10, color: 'var(--muted)', letterSpacing: '0.08em', fontWeight: 700, marginBottom: 10 }}>
        STATUS MIX
      </div>
      <div style={{ display: 'flex', gap: 2, height: 22, borderRadius: 6, overflow: 'hidden', background: 'var(--hair-2)' }}>
        {shown.map((r) => (
          <div
            key={r.status}
            title={`${r.label}: ${r.count}`}
            style={{ width: `${(r.count / total) * 100}%`, background: STATUS_COLOR[r.status] ?? '#94A3B8' }}
          />
        ))}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '7px 16px', marginTop: 11 }}>
        {shown.map((r) => (
          <div key={r.status} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
            <span style={{ width: 9, height: 9, borderRadius: '50%', background: STATUS_COLOR[r.status] ?? '#94A3B8', flexShrink: 0 }} />
            <span style={{ color: 'var(--ink-2)' }}>{r.label}</span>
            <b style={{ color: 'var(--ink)', fontVariantNumeric: 'tabular-nums' }}>{r.count}</b>
          </div>
        ))}
      </div>
    </div>
  )
}

export function ActionPlanTracker({ districts }: { districts?: readonly string[] | null }) {
  const [data, setData] = useState<ActionAggregates | null>(null)
  const [loading, setLoading] = useState(true)
  // A fetch FAILURE must not read as "no actions yet". Track it separately so
  // the render shows an explicit unavailable state instead of the empty copy.
  const [error, setError] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  // Drives the drawer hint only, so it never reads "CLICK TO EXPAND" on an
  // already-open list. Declared with the other hooks, above the early returns.
  const [listOpen, setListOpen] = useState(false)
  const districtsKey = districts && districts.length ? districts.join(',') : ''

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(false)
    const params: Record<string, string> = {}
    if (districtsKey) params.districts = districtsKey
    api
      .get<ActionAggregates>('/mpdsr/action-aggregates/', { params })
      .then((res) => { if (!cancelled) { setData(res.data); setLoading(false) } })
      .catch(() => { if (!cancelled) { setError(true); setLoading(false) } })
    return () => { cancelled = true }
  }, [districtsKey, reloadKey])

  const header = (
    <div style={{ marginBottom: 14, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
      <div>
        <div className="kicker">
          <span className="dot" style={{ background: CIPRB_ORANGE }} />
          MPDSR RESPONSE PLAN · IMPLEMENTATION TRACKER
        </div>
        <h2 className="section-title" style={{ margin: '8px 0 2px', display: 'flex', alignItems: 'center', gap: 10 }}>
          <ListChecks size={22} style={{ color: CIPRB_ORANGE, flexShrink: 0 }} />
          MPDSR Response Plan · Implementation Tracker
        </h2>
        <p className="section-sub" style={{ margin: 0 }}>
          Every action a district committee agrees in CIPRB-10 is tracked by its own ID; completion advances as they update it.
        </p>
      </div>
      <SourceChip>CIPRB 10 — Action Plan (live)</SourceChip>
    </div>
  )

  if (loading) {
    return (
      <div>
        {header}
        <div className="card" style={{ padding: '30px 22px', textAlign: 'center', fontSize: 13.5, color: 'var(--muted)' }}>
          Loading action plan…
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div>
        {header}
        <DataUnavailable label="The response-plan tracker" onRetry={() => setReloadKey((k) => k + 1)} />
      </div>
    )
  }

  if (!data || data.total === 0) {
    return (
      <div>
        {header}
        <div className="card" style={{ padding: '30px 22px', textAlign: 'center', fontSize: 13.5, color: 'var(--muted)' }}>
          No approved response-plan actions yet — each agreed action appears here with its completion % as committees
          submit and CIPRB approves them via Form 10 (CIPRB-10).
        </div>
      </div>
    )
  }

  const { overall_pct, total, by_status, by_district, by_section, actions } = data

  return (
    <div>
      {header}

      {/* Headline band — cumulative completion + counts */}
      <div className="card" style={{ padding: '18px 24px', marginBottom: 14, display: 'grid', gridTemplateColumns: 'auto 1fr auto', gap: 22, alignItems: 'center', borderLeft: `5px solid ${compColor(overall_pct)}` }}>
        <div>
          <div className="mono" style={{ fontSize: 10, color: 'var(--muted)', letterSpacing: '0.08em', fontWeight: 700, marginBottom: 4 }}>
            CUMULATIVE COMPLETION OF RESPONSE PLAN
          </div>
          <div style={{ fontSize: 46, fontWeight: 800, color: compColor(overall_pct), fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.02em', lineHeight: 1 }}>
            {overall_pct}%
          </div>
        </div>
        <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 26, fontWeight: 800, color: 'var(--ink)', fontVariantNumeric: 'tabular-nums', lineHeight: 1 }}>{total}</div>
            <div style={{ fontSize: 12, color: 'var(--muted)' }}>actions tracked</div>
          </div>
        </div>
        <div style={{ minWidth: 220, maxWidth: 340, paddingLeft: 22, borderLeft: '1px solid var(--hair)' }}>
          <StatusBreakdown rows={by_status} total={total} />
        </div>
      </div>

      {/* By district + by section */}
      <div className="pair-2" style={{ marginBottom: 14 }}>
        <div className="card" style={{ padding: '14px 18px' }}>
          <div className="mono" style={{ fontSize: 10, color: 'var(--muted)', letterSpacing: '0.08em', fontWeight: 700, marginBottom: 3 }}>BY DISTRICT</div>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 12 }}>
            Bar length is the number of actions recorded. The percentage on the right is that district&rsquo;s completion, and is not what the bar measures.
          </div>
          <CountBars rows={by_district} />
        </div>
        <div className="card" style={{ padding: '14px 18px' }}>
          <div className="mono" style={{ fontSize: 10, color: 'var(--muted)', letterSpacing: '0.08em', fontWeight: 700, marginBottom: 12 }}>BY SECTION</div>
          <Bars rows={by_section} />
        </div>
      </div>

      {/* Per-action table, collapsed by default. There are 55 actions today
          and the list only grows, so leaving it open pushed Fistula, MPDSR and
          Near Miss far below the fold. The summary carries the counts that
          matter, so nobody has to open it to know whether to. Matches the raw
          MPDSR case register drawer on the same page. */}
      <details className="card" style={{ padding: 0, overflow: 'hidden' }}
               onToggle={(e) => setListOpen((e.currentTarget as HTMLDetailsElement).open)}>
        <summary style={{
          padding: '14px 18px', cursor: 'pointer', listStyle: 'none',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          gap: 12, flexWrap: 'wrap',
          fontWeight: 600, fontSize: 14, color: 'var(--ink)',
        }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10 }}>
            Every action, district by district
            <span style={{
              fontSize: 11, color: 'var(--muted)', fontWeight: 500,
              fontVariantNumeric: 'tabular-nums',
            }}>
              ({actions.length.toLocaleString()} tracked
              )
            </span>
          </span>
          <span className="mono" style={{
            fontSize: 11, color: 'var(--muted)', letterSpacing: '0.06em',
          }}>
            {listOpen ? 'CLICK TO COLLAPSE' : 'CLICK TO EXPAND'}
          </span>
        </summary>
        <table className="tbl" style={{ borderTop: '1px solid var(--hair)' }}>
          <thead>
            <tr>
              <th>ID</th>
              <th>District</th>
              <th>Action</th>
              <th style={{ width: 170 }}>Completion</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {actions.map((a) => (
              <tr key={a.action_id} style={a.is_overdue ? { background: 'rgba(237,91,126,0.07)' } : undefined}>
                <td style={{ fontFamily: 'monospace', fontWeight: 700, whiteSpace: 'nowrap' }}>{a.action_id}</td>
                <td style={{ whiteSpace: 'nowrap' }}>{a.district}</td>
                <td style={{ maxWidth: 320 }}>
                  {a.activity}
                  {a.sub_category_label ? (
                    <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--accent)' }}>
                      {a.sub_category_label}
                    </div>
                  ) : null}
                  <div style={{ fontSize: 11, color: 'var(--muted)' }}>
                    {a.section_label}{a.timeline ? ` · due ${a.timeline}` : ''}{a.responsible ? ` · ${a.responsible}` : ''}
                  </div>
                </td>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ flex: 1, height: 10, background: 'var(--hair-2)', borderRadius: 3, overflow: 'hidden' }}>
                      <div style={{ width: `${a.completion_pct}%`, height: '100%', background: compColor(a.completion_pct) }} />
                    </div>
                    <span style={{ fontSize: 12, fontWeight: 700, color: compColor(a.completion_pct), fontVariantNumeric: 'tabular-nums', width: 34, textAlign: 'right' }}>
                      {a.completion_pct}%
                    </span>
                  </div>
                </td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  {a.is_overdue
                    ? <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: '#ED5B7E', fontWeight: 700 }}>
                        <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#ED5B7E', flexShrink: 0 }} />Overdue
                      </span>
                    : <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ width: 8, height: 8, borderRadius: '50%', background: STATUS_COLOR[a.status] ?? '#C3C8D2', flexShrink: 0 }} />{a.status_label}
                      </span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  )
}
