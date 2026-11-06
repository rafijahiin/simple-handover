/**
 * NilReportModal — a manager logs a "No reporting today" entry for a centre +
 * date + reason, scoped strictly to their OWN organisation. Bandhu is two-stage
 * (the entry is created at the manager gate, then flows to the UNFPA approval
 * queue); PHD and CIPRB are single-stage (the authoring manager is
 * authoritative, so the entry is recorded immediately). No team ever sees or
 * writes another team's centres — the centre list is filtered to the user's
 * org and the server derives the organisation from the session, not the client.
 */
import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { api } from '@/api/client'
import { useAuth } from '@/context/AuthContext'

interface Centre { code: string; name: string; organisation: string }

interface Props {
  open: boolean
  onClose: () => void
  onSaved?: () => void
}

const todayISO = () => new Date().toISOString().slice(0, 10)

export function NilReportModal({ open, onClose, onSaved }: Props) {
  const { user } = useAuth()
  const org = user?.organisation || ''
  // Bandhu is two-stage (manager → UNFPA); PHD/CIPRB record immediately.
  const isTwoStage = org === 'Bandhu'

  const [centres, setCentres] = useState<Centre[]>([])
  const [centreCode, setCentreCode] = useState('')
  const [date, setDate] = useState(todayISO())
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)

  useEffect(() => {
    if (!open) return
    setError(''); setDone(false)
    api.get('/programs/centers/')
      .then((r) => {
        const list: Centre[] = (Array.isArray(r.data) ? r.data : r.data?.results ?? [])
          // Only ever list the user's OWN org's centres — strict isolation.
          .filter((c: Centre) => c.organisation === org)
        setCentres(list)
      })
      .catch(() => setCentres([]))
  }, [open, org])

  if (!open) return null

  const submit = async () => {
    if (!date || !reason.trim()) { setError('Date and reason are required.'); return }
    setBusy(true); setError('')
    try {
      // The server derives the organisation strictly from the logged-in user;
      // the client never sends it (org-isolation boundary).
      await api.post('/programs/nil-reports/', {
        center_id: centreCode || null,
        report_date: date,
        reason: reason.trim(),
      })
      setDone(true)
      onSaved?.()
      setTimeout(onClose, 900)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Could not save the nil-report.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      role="dialog" aria-modal="true"
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 300,
        background: 'rgba(20,32,43,0.45)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
      }}
    >
      <div onClick={(e) => e.stopPropagation()} className="card" style={{
        width: 'min(460px, 100%)', padding: 22, borderRadius: 16,
      }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 4 }}>
          <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--ink)' }}>No reporting today</div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)' }}>
            <X size={18} />
          </button>
        </div>
        <p style={{ fontSize: 13, color: 'var(--ink-3)', marginTop: 0, marginBottom: 16 }}>
          Record a day a centre had no submissions, with the reason.{' '}
          {isTwoStage ? 'It will go to UNFPA for approval.' : 'It will be recorded for your organisation.'}
        </p>

        {done ? (
          <div style={{ padding: '16px 0', color: 'var(--emerald)', fontWeight: 600 }}>
            {isTwoStage ? '✓ Logged — sent to UNFPA.' : '✓ Recorded.'}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <label style={{ fontSize: 13, color: 'var(--ink-2)' }}>
              Centre
              <select value={centreCode} onChange={(e) => setCentreCode(e.target.value)}
                style={{ width: '100%', marginTop: 4, padding: '8px 10px', borderRadius: 8, border: '1px solid var(--hair)', background: 'var(--surface)', color: 'var(--ink)' }}>
                <option value="">All centres</option>
                {centres.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
              </select>
            </label>
            <label style={{ fontSize: 13, color: 'var(--ink-2)' }}>
              Date
              <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
                style={{ width: '100%', marginTop: 4, padding: '8px 10px', borderRadius: 8, border: '1px solid var(--hair)', background: 'var(--surface)', color: 'var(--ink)' }} />
            </label>
            <label style={{ fontSize: 13, color: 'var(--ink-2)' }}>
              Reason
              <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3}
                placeholder="Why was there no reporting? (e.g. centre closed, holiday, staff absent)"
                style={{ width: '100%', marginTop: 4, padding: '8px 10px', borderRadius: 8, border: '1px solid var(--hair)', background: 'var(--surface)', color: 'var(--ink)', resize: 'vertical' }} />
            </label>
            {error && <div style={{ fontSize: 12.5, color: 'var(--rose)' }}>{error}</div>}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 4 }}>
              <button className="btn ghost" onClick={onClose} disabled={busy}>Cancel</button>
              <button className="btn success" onClick={submit} disabled={busy || !reason.trim()}>
                {busy ? 'Saving…' : (isTwoStage ? 'Log & send to UNFPA' : 'Record nil-report')}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
