/**
 * Profile page — view own account info and change password.
 *
 * Everyone has this page (focal, manager, supervisor, developer). It hits
 * /api/auth/password-change/ which validates the current password and
 * enforces Django's password validators on the new one.
 */
import { FormEvent, useState } from 'react'
import { Eye, EyeOff, User as UserIcon, Mail, Building2, ShieldCheck, Check } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { api, apiErrorMessage } from '@/api/client'
import { useAuth } from '@/context/AuthContext'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'

const ROLE_LABEL: Record<string, string> = {
  developer:      'Developer',
  supervisor:     'UNFPA Supervisor',
  org_lead:       'Organisation Lead',
  manager:        'Wellness Centre Manager',
  field_staff:    'Field Staff',
  ciprb_baseline: 'CIPRB Baseline Entry',
  focal:          'Focal Person',
}

export default function Profile() {
  const { user } = useAuth()
  const { t } = useTranslation()

  const [current, setCurrent] = useState('')
  const [next, setNext]       = useState('')
  const [confirm, setConfirm] = useState('')

  const [showCurrent, setShowCurrent] = useState(false)
  const [showNext, setShowNext]       = useState(false)

  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')
  const [success, setSuccess] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccess(false)

    if (next.length < 8) {
      setError('New password must be at least 8 characters.')
      return
    }
    if (next !== confirm) {
      setError('New password and confirmation do not match.')
      return
    }
    if (next === current) {
      setError('New password must differ from the current password.')
      return
    }

    setLoading(true)
    try {
      await api.post('/accounts/password-change/', {
        current_password: current,
        new_password: next,
      })
      setSuccess(true)
      setCurrent('')
      setNext('')
      setConfirm('')
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not change password.'))
    } finally {
      setLoading(false)
    }
  }

  if (!user) return null

  return (
    <div style={{
      maxWidth: 720,
      margin: '0 auto',
      padding: '40px 24px 96px',
    }}>

      {/* ── Header ────────────────────────────────────────────────────── */}
      <div style={{ marginBottom: 36 }}>
        <div className="kicker" style={{ marginBottom: 8 }}>
          <span className="dot" />{t('profile.kicker', { defaultValue: 'YOUR ACCOUNT' })}
        </div>
        <h1 className="section-title" style={{ fontSize: 32, margin: 0 }}>
          {t('profile.title', { defaultValue: 'Profile & security' })}
        </h1>
        <p className="section-sub" style={{ marginTop: 6 }}>
          {t('profile.subtitle', { defaultValue: 'Review your account details and update your password.' })}
        </p>
      </div>

      {/* ── Account details card ──────────────────────────────────────── */}
      <div className="card" style={{ padding: 24, marginBottom: 28 }}>
        <h2 style={{
          margin: '0 0 18px', fontSize: 15, fontWeight: 600,
          color: 'var(--ink)', letterSpacing: '-0.005em',
        }}>
          Account details
        </h2>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18 }}>
          <DetailRow icon={<UserIcon size={15} />} label="Full name"   value={user.full_name} />
          <DetailRow icon={<Mail size={15} />}      label="Email"       value={user.email} />
          <DetailRow icon={<Building2 size={15} />} label="Organisation" value={user.organisation} />
          <DetailRow icon={<ShieldCheck size={15} />} label="Role"      value={ROLE_LABEL[user.role] ?? user.role} />
        </div>
      </div>

      {/* ── Password change card ──────────────────────────────────────── */}
      <div className="card" style={{ padding: 24 }}>
        <h2 style={{
          margin: '0 0 6px', fontSize: 15, fontWeight: 600,
          color: 'var(--ink)', letterSpacing: '-0.005em',
        }}>
          Change password
        </h2>
        <p style={{ margin: '0 0 22px', fontSize: 12.5, color: 'var(--muted)' }}>
          Choose a password at least 8 characters long. After saving you will
          stay signed in on this device.
        </p>

        <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

          <Field
            label="Current password"
            type={showCurrent ? 'text' : 'password'}
            value={current}
            onChange={setCurrent}
            autoComplete="current-password"
            toggle={() => setShowCurrent(s => !s)}
            toggled={showCurrent}
          />
          <Field
            label="New password"
            type={showNext ? 'text' : 'password'}
            value={next}
            onChange={setNext}
            autoComplete="new-password"
            toggle={() => setShowNext(s => !s)}
            toggled={showNext}
          />
          <Field
            label="Confirm new password"
            type={showNext ? 'text' : 'password'}
            value={confirm}
            onChange={setConfirm}
            autoComplete="new-password"
          />

          {error && (
            <div style={{
              padding: '10px 14px', borderRadius: 8,
              background: 'rgba(241,15,69,0.08)',
              border: '1px solid rgba(241,15,69,0.22)',
              fontSize: 13, color: '#F10F45',
            }}>
              {error}
            </div>
          )}

          {success && (
            <div style={{
              padding: '10px 14px', borderRadius: 8,
              background: 'rgba(26,122,90,0.08)',
              border: '1px solid rgba(26,122,90,0.22)',
              fontSize: 13, color: '#58968A',
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <Check size={15} /> Password updated.
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 4 }}>
            <button
              type="submit"
              disabled={loading || !current || !next || !confirm}
              className="btn primary"
              style={{
                background: 'var(--unfpa)',
                color: 'white',
                border: 'none',
                padding: '10px 20px',
                borderRadius: 8,
                fontSize: 13.5,
                fontWeight: 600,
                cursor: loading ? 'wait' : 'pointer',
                opacity: (!current || !next || !confirm) ? 0.55 : 1,
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              {loading
                ? <LoadingSpinner size="sm" className="text-white" />
                : 'Update password'
              }
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Sub-components ──────────────────────────────────────────────────────

function DetailRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div>
      <div className="mono" style={{
        fontSize: 10, letterSpacing: '0.08em', color: 'var(--muted)',
        textTransform: 'uppercase', marginBottom: 4,
        display: 'inline-flex', alignItems: 'center', gap: 5,
      }}>
        {icon} {label}
      </div>
      <div style={{ fontSize: 14, color: 'var(--ink)', fontWeight: 500 }}>
        {value || '—'}
      </div>
    </div>
  )
}

function Field({
  label, type, value, onChange, autoComplete, toggle, toggled,
}: {
  label: string
  type: string
  value: string
  onChange: (v: string) => void
  autoComplete: string
  toggle?: () => void
  toggled?: boolean
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <label style={{
        fontSize: 12.5, fontWeight: 500, color: 'var(--ink-2)',
        letterSpacing: '0.01em',
      }}>
        {label}
      </label>
      <div style={{ position: 'relative' }}>
        <input
          type={type}
          value={value}
          onChange={e => onChange(e.target.value)}
          required
          autoComplete={autoComplete}
          style={{
            width: '100%', boxSizing: 'border-box',
            padding: '10px 14px',
            paddingRight: toggle ? 42 : 14,
            fontSize: 14,
            border: '1.5px solid var(--hair-2)',
            borderRadius: 8,
            background: 'var(--surface)',
            color: 'var(--ink)',
            outline: 'none',
            fontFamily: 'inherit',
            transition: 'border-color 0.15s, box-shadow 0.15s',
          }}
          onFocus={e => {
            e.target.style.borderColor = 'var(--unfpa)'
            e.target.style.boxShadow = '0 0 0 3px rgba(249,96,0,0.12)'
          }}
          onBlur={e => {
            e.target.style.borderColor = 'var(--hair-2)'
            e.target.style.boxShadow = 'none'
          }}
        />
        {toggle && (
          <button
            type="button"
            onClick={toggle}
            style={{
              position: 'absolute', right: 12, top: '50%',
              transform: 'translateY(-50%)',
              background: 'none', border: 'none', padding: 0,
              cursor: 'pointer', color: 'var(--muted-2)',
              display: 'flex', alignItems: 'center',
            }}
          >
            {toggled ? <EyeOff size={15} /> : <Eye size={15} />}
          </button>
        )}
      </div>
    </div>
  )
}
