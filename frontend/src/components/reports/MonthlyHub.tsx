import { useMemo, useState, type CSSProperties } from 'react'
import {
  FileText, Image as ImageIcon, MonitorPlay, Globe,
  Download, Copy, Check, RefreshCw, Sparkles, CalendarClock,
} from 'lucide-react'
import { api, apiErrorMessage } from '@/api/client'
import { usePolling } from '@/hooks/usePolling'
import { useAuth } from '@/context/AuthContext'
import { isAdminRole } from '@/types'

/** One generated piece, as returned by GET /api/reports/hub/. */
interface HubReport {
  id: string
  report_type: string
  format: string
  partner: string          // '' = overall / all partners
  year: number
  month: number
  period_start: string
  title: string
  share_token: string
  web_url: string
  created_at: string
}

const SCOPES: { key: string; label: string }[] = [
  { key: '', label: 'Overall' },
  { key: 'PHD', label: 'PHD' },
  { key: 'Bandhu', label: 'Bandhu' },
  { key: 'CIPRB', label: 'CIPRB' },
]

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December']

function pieceMeta(r: HubReport): { label: string; Icon: typeof FileText } {
  if (r.report_type === 'one_pager') return { label: 'Infographic', Icon: ImageIcon }
  if (r.report_type === 'web_report') return { label: 'Web report', Icon: Globe }
  if (r.format === 'pptx') return { label: 'Deck', Icon: MonitorPlay }
  return { label: 'Report', Icon: FileText }
}

async function downloadPiece(r: HubReport) {
  const resp = await api.get(`/reports/${r.id}/download/`, { responseType: 'blob' })
  const url = URL.createObjectURL(resp.data as Blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${r.report_type}_${r.partner || 'all'}_${r.year}-${String(r.month).padStart(2, '0')}.${r.format}`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export default function MonthlyHub() {
  const { user } = useAuth()
  const canGenerate = !!user && isAdminRole(user.role)

  const { data, refetch } = usePolling<HubReport[]>({
    fetcher: () =>
      api.get('/reports/hub/').then((r) =>
        Array.isArray(r.data) ? r.data : (r.data?.results ?? [])),
    interval: 45_000,
  })

  const now = new Date()
  const [genYear, setGenYear] = useState(now.getFullYear())
  const [genMonth, setGenMonth] = useState(now.getMonth() + 1)
  const [generating, setGenerating] = useState(false)
  const [msg, setMsg] = useState('')

  const months = useMemo(() => {
    const map = new Map<string, HubReport[]>()
    for (const r of data ?? []) {
      const key = `${r.year}-${String(r.month).padStart(2, '0')}`
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(r)
    }
    return [...map.entries()]
      .sort((a, b) => b[0].localeCompare(a[0]))
      .map(([key, items]) => ({ key, items }))
  }, [data])

  async function generate() {
    setGenerating(true)
    setMsg('')
    try {
      const r = await api.post('/reports/generate-monthly/', { year: genYear, month: genMonth })
      setMsg(r.data?.detail || 'Generating…')
      window.setTimeout(refetch, 60_000)
    } catch (e) {
      setMsg(apiErrorMessage(e))
    } finally {
      setGenerating(false)
    }
  }

  return (
    <section style={{ marginBottom: 36 }}>
      <div className="kicker"><span className="dot" /> Monthly hub</div>
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between',
        flexWrap: 'wrap', gap: 16, marginBottom: 18 }}>
        <div>
          <h2 className="section-title" style={{ margin: 0 }}>Monthly report sets</h2>
          <p style={{ color: 'var(--muted)', fontSize: 14, marginTop: 4, maxWidth: '56ch' }}>
            Each month the data is pulled fresh and rendered into a branded kit — an infographic and
            report per partner, plus an overall report, deck and a shareable web report.
          </p>
        </div>
        {canGenerate && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <select value={genMonth} onChange={(e) => setGenMonth(+e.target.value)} style={selectStyle}>
              {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
            </select>
            <select value={genYear} onChange={(e) => setGenYear(+e.target.value)} style={selectStyle}>
              {[now.getFullYear(), now.getFullYear() - 1].map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
            <button onClick={generate} disabled={generating}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 7, padding: '8px 14px',
                borderRadius: 'var(--r-sm)', border: 'none', cursor: generating ? 'wait' : 'pointer',
                background: 'var(--unfpa)', color: '#fff', fontWeight: 700, fontSize: 13.5 }}>
              <Sparkles size={15} /> {generating ? 'Starting…' : 'Generate set'}
            </button>
            <button onClick={refetch} title="Refresh"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 11px',
                borderRadius: 'var(--r-sm)', border: '1px solid var(--hair)', cursor: 'pointer',
                background: 'var(--surface)', color: 'var(--ink-2)', fontWeight: 700, fontSize: 13.5 }}>
              <RefreshCw size={15} />
            </button>
          </div>
        )}
      </div>

      {msg && (
        <div style={{ marginBottom: 16, padding: '10px 14px', borderRadius: 'var(--r-sm)',
          background: 'var(--unfpa-light)', color: 'var(--unfpa-deep)', fontSize: 13.5, fontWeight: 600 }}>
          {msg}
        </div>
      )}

      {months.length === 0 ? (
        <div className="card" style={{ padding: 28, textAlign: 'center', color: 'var(--muted)' }}>
          <CalendarClock size={26} style={{ opacity: 0.5 }} />
          <p style={{ marginTop: 10, fontSize: 14 }}>
            No monthly sets yet.{canGenerate ? ' Pick a month above and generate the first one.'
              : ' They appear here once generated.'}
          </p>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: 16 }}>
          {months.map(({ key, items }) => (
            <MonthCard key={key} items={items} />
          ))}
        </div>
      )}
    </section>
  )
}

function MonthCard({ items }: { items: HubReport[] }) {
  const first = items[0]
  const title = new Date(first.year, first.month - 1, 1)
    .toLocaleString('en-US', { month: 'long', year: 'numeric' })

  return (
    <div className="card" style={{ padding: 22 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
        marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
        <h3 style={{ margin: 0, fontFamily: 'var(--display)', fontSize: 22, letterSpacing: '-0.01em' }}>
          {title}
        </h3>
        <span style={{ fontSize: 12, color: 'var(--muted)', fontWeight: 700 }}>
          {items.length} piece{items.length === 1 ? '' : 's'}
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 12 }}>
        {SCOPES.map((scope) => {
          const pieces = items.filter((r) => r.partner === scope.key)
          if (pieces.length === 0) return null
          const isOverall = scope.key === ''
          return (
            <div key={scope.label} style={{ border: '1px solid var(--hair)', borderRadius: 'var(--r-md)',
              padding: 14, background: isOverall ? 'var(--surface-2)' : 'var(--surface)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 10 }}>
                <span style={{ width: 7, height: 7, borderRadius: 2,
                  background: isOverall ? 'var(--unfpa)' : 'var(--muted-2)' }} />
                <span style={{ fontWeight: 700, fontSize: 13.5, color: 'var(--ink)' }}>{scope.label}</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {pieces
                  .sort((a, b) => a.report_type.localeCompare(b.report_type) || a.format.localeCompare(b.format))
                  .map((r) => <PieceRow key={r.id} r={r} />)}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function PieceRow({ r }: { r: HubReport }) {
  const { label, Icon } = pieceMeta(r)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)

  if (r.report_type === 'web_report') {
    return (
      <div style={rowStyle}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
          <Icon size={15} style={{ color: 'var(--unfpa)' }} /> {label}
        </span>
        <span style={{ display: 'inline-flex', gap: 4 }}>
          <a href={r.web_url} target="_blank" rel="noreferrer" title="Open" style={iconBtn}>
            <Globe size={14} />
          </a>
          <button title="Copy share link" style={iconBtn}
            onClick={() => { navigator.clipboard?.writeText(r.web_url); setCopied(true); window.setTimeout(() => setCopied(false), 1500) }}>
            {copied ? <Check size={14} style={{ color: 'var(--emerald)' }} /> : <Copy size={14} />}
          </button>
        </span>
      </div>
    )
  }

  return (
    <button
      onClick={async () => { setBusy(true); try { await downloadPiece(r) } finally { setBusy(false) } }}
      disabled={busy}
      style={{ ...rowStyle, border: 'none', cursor: busy ? 'wait' : 'pointer', width: '100%',
        background: 'transparent', textAlign: 'left' }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
        <Icon size={15} style={{ color: 'var(--ink-3)' }} /> {label}
      </span>
      <Download size={14} style={{ color: 'var(--muted)', opacity: busy ? 0.4 : 1 }} />
    </button>
  )
}

const rowStyle: CSSProperties = {
  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
  fontSize: 13, color: 'var(--ink-2)', fontWeight: 600,
  padding: '5px 8px', borderRadius: 'var(--r-xs)', background: 'var(--surface-2)',
}
const iconBtn: CSSProperties = {
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  width: 26, height: 24, borderRadius: 'var(--r-xs)', border: '1px solid var(--hair)',
  background: 'var(--surface)', color: 'var(--ink-2)', cursor: 'pointer',
}
const selectStyle: CSSProperties = {
  padding: '8px 10px', borderRadius: 'var(--r-sm)', border: '1px solid var(--hair)',
  background: 'var(--surface)', color: 'var(--ink)', fontWeight: 600, fontSize: 13.5,
  fontFamily: 'var(--ui)', cursor: 'pointer',
}
