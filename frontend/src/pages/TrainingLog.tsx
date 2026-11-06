/**
 * Training Log — training / orientation / workshop events.
 *
 * Source of truth: programs.TrainingEvent, fed by the KF-20 Training Kobo
 * form via the /webhook/programs/ pipeline and surfaced once a manager
 * approves it. (The page previously read training.TrainingSession, which is
 * a separate in-app model the Kobo form never wrote to — hence the blank tab.)
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Users, ChevronDown } from 'lucide-react'
import { api } from '@/api/client'
import { usePolling } from '@/hooks/usePolling'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { formatDate } from '@/utils/format'

interface TrainingEvent {
  id: string
  organisation: string
  event_date: string
  event_end_date: string | null
  event_type: string
  participant_type: string
  topic: string
  location_text: string
  district: string
  total_participants: number
  male_participants: number
  female_participants: number
  tg_participants: number
  participants_doctors: number
  participants_nurses: number
  participants_midwives: number
  participants_other: number
  facilitator: string
  notes: string
  approval_status: string
  submitted_by_kobo_user: string
}

const EVENT_TYPE_LABELS: Record<string, string> = {
  training: 'Training', orientation: 'Orientation', workshop: 'Workshop',
  meeting: 'Meeting', refresher: 'Refresher',
}
const titleize = (s: string) =>
  (s || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

const PARTNER_ACCENT: Record<string, string> = {
  CIPRB: '#F96000', PHD: '#F96000', Bandhu: '#F96000',
}

function EventRow({ ev }: { ev: TrainingEvent }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const org = ev.organisation || 'CIPRB'
  const accent = PARTNER_ACCENT[org] ?? 'var(--unfpa)'
  const place = ev.district || ev.location_text || '—'
  const breakdown = [
    ['Male', ev.male_participants], ['Female', ev.female_participants],
    ['Transgender', ev.tg_participants],
    ['Doctors', ev.participants_doctors], ['Nurses', ev.participants_nurses],
    ['Midwives', ev.participants_midwives], ['Other', ev.participants_other],
  ].filter(([, n]) => Number(n) > 0) as [string, number][]

  return (
    <div className="card flush" style={{ overflow: 'hidden' }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          display: 'flex', alignItems: 'center', gap: 16, width: '100%',
          padding: '16px 20px', textAlign: 'left', background: 'transparent',
          border: 'none', cursor: 'pointer', color: 'var(--ink)',
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10, marginBottom: 6 }}>
            <span style={{ fontWeight: 600, color: 'var(--ink)', fontSize: 14 }}>
              {ev.topic || EVENT_TYPE_LABELS[ev.event_type] || 'Training'}
            </span>
            <span style={{
              borderRadius: 999, padding: '2px 8px', fontSize: 10, fontWeight: 600,
              background: `${accent}1A`, color: accent, letterSpacing: '0.02em',
            }}>{org}</span>
            <span style={{
              borderRadius: 999, padding: '2px 8px', fontSize: 10, fontWeight: 600,
              background: 'var(--surface-2)', color: 'var(--ink-3)',
            }}>{EVENT_TYPE_LABELS[ev.event_type] || titleize(ev.event_type)}</span>
          </div>
          <div style={{
            display: 'flex', flexWrap: 'wrap', gap: 10, fontSize: 11.5,
            color: 'var(--muted)', fontVariantNumeric: 'tabular-nums',
          }}>
            <span>{formatDate(ev.event_date)}</span>
            <span>·</span>
            <span>{place}</span>
            <span>·</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <Users size={11} />{ev.total_participants} {t('training.participants', { defaultValue: 'participants' })}
            </span>
            {ev.facilitator && (<><span>·</span><span>{ev.facilitator}</span></>)}
          </div>
        </div>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 14, flexShrink: 0 }}>
          <div style={{ textAlign: 'right' }}>
            <p style={{ fontSize: 11, color: 'var(--muted)', margin: 0 }}>
              {t('training.participants', { defaultValue: 'Participants' })}
            </p>
            <p style={{ fontWeight: 700, color: 'var(--ink)', margin: 0, fontVariantNumeric: 'tabular-nums', fontSize: 16 }}>
              {ev.total_participants}
            </p>
          </div>
          <ChevronDown size={16} style={{
            color: 'var(--muted)', transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform var(--dur-q)',
          }} />
        </div>
      </button>

      {open && (
        <div style={{ borderTop: '1px solid var(--hair)', padding: '14px 20px' }}>
          {breakdown.length === 0 ? (
            <p style={{ fontSize: 13, color: 'var(--muted)', margin: 0 }}>
              {t('training.noBreakdown', { defaultValue: 'No participant breakdown recorded.' })}
            </p>
          ) : (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
              {breakdown.map(([label, n]) => (
                <div key={label} style={{
                  display: 'flex', flexDirection: 'column', minWidth: 90,
                  padding: '8px 12px', borderRadius: 8,
                  background: 'var(--surface-2)', border: '1px solid var(--hair)',
                }}>
                  <span style={{ fontSize: 18, fontWeight: 700, color: 'var(--ink)', fontVariantNumeric: 'tabular-nums' }}>{n}</span>
                  <span style={{ fontSize: 11, color: 'var(--muted)' }}>{label}</span>
                </div>
              ))}
            </div>
          )}
          {ev.notes && (
            <p style={{ marginTop: 12, fontSize: 12.5, color: 'var(--ink-2)' }}>{ev.notes}</p>
          )}
          <p style={{ marginTop: 10, fontSize: 11, color: 'var(--muted)' }}>
            Submitted by {ev.submitted_by_kobo_user || '—'} · {ev.approval_status}
          </p>
        </div>
      )}
    </div>
  )
}

type Filter = 'all' | 'CIPRB' | 'PHD' | 'Bandhu'

export default function TrainingLog() {
  const { t, i18n } = useTranslation()
  const [filter, setFilter] = useState<Filter>('all')

  const fmtNum = (n: number) =>
    n.toLocaleString(i18n.language?.startsWith('bn') ? 'bn-BD' : 'en-US')

  const { data: events, loading } = usePolling<TrainingEvent[]>({
    fetcher: () =>
      api.get('/programs/training-events/')
        .then((r) => (Array.isArray(r.data) ? r.data : r.data.results ?? [])),
    interval: 120_000,
  })

  // Only approved events appear in the log (same gate as the dashboards).
  const approved = (events ?? []).filter((e) => e.approval_status === 'APPROVED')
  const shown = approved.filter((e) => filter === 'all' || (e.organisation || 'CIPRB') === filter)

  const totalParticipants = shown.reduce((s, e) => s + (e.total_participants || 0), 0)
  const totalFemale = shown.reduce((s, e) => s + (e.female_participants || 0), 0)

  const stats = [
    { label: t('training.statSessions', { defaultValue: 'Events' }), value: fmtNum(shown.length) },
    { label: t('training.statParticipants', { defaultValue: 'Participants' }), value: fmtNum(totalParticipants) },
    { label: t('training.statFemale', { defaultValue: 'Female' }), value: fmtNum(totalFemale) },
    {
      label: t('training.statFemalePct', { defaultValue: 'Female %' }),
      value: totalParticipants > 0 ? `${((totalFemale / totalParticipants) * 100).toFixed(0)}%` : '—',
    },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
      <section className="hero" style={{ paddingBottom: 8 }}>
        <div className="hero-eyebrow">
          <span className="live-dot" />
          <span>{t('training.eyebrow', { defaultValue: 'CAPACITY · TRAINING' })}</span>
        </div>
        <h1 className="hero-headline" style={{ fontSize: 'clamp(40px, 5.5vw, 64px)', letterSpacing: '-0.03em', marginBottom: 10 }}>
          {t('training.title', { defaultValue: 'Training Log' })}
        </h1>
        <p className="hero-lede" style={{ maxWidth: 640 }}>
          {t('training.subtitle', { defaultValue: 'Training, orientation and workshop events — fed live from the KF-20 Kobo form once approved.' })}
        </p>
      </section>

      <section className="section" style={{ marginTop: -8 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
          {stats.map((s) => (
            <div key={s.label} className="card" style={{ padding: 18 }}>
              <p style={{ fontSize: 30, fontWeight: 700, color: 'var(--ink)', fontVariantNumeric: 'tabular-nums', lineHeight: 1, margin: 0 }}>{s.value}</p>
              <p style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 6, letterSpacing: '0.02em' }}>{s.label}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="section" style={{ marginTop: 0 }}>
        <div role="tablist" style={{
          display: 'inline-flex', gap: 4, padding: 4, background: 'var(--surface-2)',
          border: '1px solid var(--hair)', borderRadius: 999,
        }}>
          {(['all', 'CIPRB', 'PHD', 'Bandhu'] as Filter[]).map((p) => {
            const active = filter === p
            return (
              <button key={p} role="tab" aria-selected={active} onClick={() => setFilter(p)}
                style={{
                  padding: '6px 14px', borderRadius: 999, fontSize: 13, fontWeight: 500,
                  border: 'none', cursor: 'pointer',
                  background: active ? 'var(--unfpa)' : 'transparent',
                  color: active ? '#fff' : 'var(--ink-3)',
                }}>
                {p === 'all' ? t('training.allPartners', { defaultValue: 'All Partners' }) : p}
              </button>
            )
          })}
        </div>
      </section>

      <section className="section" style={{ marginTop: 0, marginBottom: 48 }}>
        {loading && !events ? (
          <PageLoader />
        ) : shown.length === 0 ? (
          <div className="card" style={{ padding: '48px 16px', textAlign: 'center', borderStyle: 'dashed', borderColor: 'var(--hair-2)' }}>
            <p style={{ color: 'var(--muted)', fontSize: 13, margin: 0 }}>
              {t('training.empty', { defaultValue: 'No approved training events yet. Submit the KF-20 form and approve it to see it here.' })}
            </p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {shown.map((ev) => <EventRow key={ev.id} ev={ev} />)}
          </div>
        )}
      </section>
    </div>
  )
}
