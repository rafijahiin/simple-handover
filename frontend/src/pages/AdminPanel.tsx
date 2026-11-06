/**
 * Admin Panel — user management surface, developer-only (audit FIX 1.4).
 *
 * Rewritten to use the editorial design tokens (var(--surface), var(--ink),
 * var(--hair), var(--unfpa)) instead of the Tailwind dark-mode utilities
 * that were rendering a slate-blue panel. Matches MPDSR / FistulaTracker
 * / OrgDashboard chrome.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Pencil, UserX, UserCheck, X } from 'lucide-react'
import { api, apiErrorMessage } from '@/api/client'
import { usePolling } from '@/hooks/usePolling'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { PageLoader, LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { formatDateTime } from '@/utils/format'
import type { AdminUser, Organisation, Role } from '@/types'

const ORGS: Organisation[] = ['CIPRB', 'UNFPA', 'PHD', 'Bandhu']

const ROLES: Role[] = [
  'developer',
  'supervisor',
  'org_lead',
  'manager',
  'field_staff',
  'ciprb_baseline',
  'focal',
]

const ROLE_LABELS: Record<string, string> = {
  developer:      'Developer',
  supervisor:     'UNFPA / Supervisor',
  org_lead:       'Org Lead',
  manager:        'Wellness Center Manager',
  field_staff:    'Field Staff / Lab Tech',
  ciprb_baseline: 'CIPRB Baseline Entry',
  focal:          'Focal Person (view-only)',
}

// UNFPA branding — all org accents collapse to UNFPA orange. Partner
// identity is shown by the org code label, not by colour.
const ORG_ACCENT: Record<Organisation, string> = {
  CIPRB:  '#F96000',
  UNFPA:  '#F96000',
  PHD:    '#F96000',
  Bandhu: '#F96000',
}

interface UserFormData {
  username: string
  email: string
  first_name: string
  last_name: string
  organisation: Organisation
  role: Role
  password?: string
}

// ─── User modal ──────────────────────────────────────────────────────────────

function UserModal({
  user,
  onClose,
  onSuccess,
}: {
  user?: AdminUser
  onClose: () => void
  onSuccess: () => void
}) {
  const { t } = useTranslation()
  const isEdit = !!user
  const [form, setForm] = useState<UserFormData>({
    username: user?.username ?? '',
    email: user?.email ?? '',
    first_name: user?.first_name ?? '',
    last_name: user?.last_name ?? '',
    organisation: (user?.organisation as Organisation) ?? 'PHD',
    role: (user?.role as Role) ?? 'manager',
    password: '',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      const payload = isEdit
        ? { ...form, ...(form.password ? {} : { password: undefined }) }
        : form
      if (isEdit) {
        await api.patch(`/admin/users/${user!.id}/`, payload)
      } else {
        await api.post('/admin/users/', payload)
      }
      onSuccess()
      onClose()
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const Field = ({
    keyName, label, type = 'text', required = true,
  }: { keyName: keyof UserFormData; label: string; type?: string; required?: boolean }) => (
    <div>
      <label style={{
        display: 'block',
        fontSize: 11, fontWeight: 500,
        color: 'var(--ink-3)', marginBottom: 4,
        textTransform: 'uppercase', letterSpacing: '0.04em',
      }}>
        {label}
      </label>
      <input
        type={type}
        value={(form[keyName] as string) ?? ''}
        onChange={(e) => setForm((f) => ({ ...f, [keyName]: e.target.value }))}
        required={required && keyName !== 'password'}
        autoComplete={type === 'password' ? 'new-password' : undefined}
        placeholder={keyName === 'password' && isEdit ? 'Leave blank to keep current' : undefined}
        style={{
          width: '100%',
          borderRadius: 8,
          border: '1px solid var(--hair-2)',
          background: 'var(--surface)',
          color: 'var(--ink)',
          padding: '8px 12px',
          fontSize: 13,
          outline: 'none',
        }}
      />
    </div>
  )

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 50,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 16,
        background: 'rgba(0,0,0,0.45)',
        backdropFilter: 'blur(8px)',
        WebkitBackdropFilter: 'blur(8px)',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="card"
        style={{
          width: '100%', maxWidth: 460, padding: 24,
          maxHeight: '90vh', overflowY: 'auto',
          boxShadow: 'var(--sh-3)',
        }}
      >
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          marginBottom: 20,
        }}>
          <h2 style={{
            fontSize: 17, fontWeight: 700, color: 'var(--ink)', margin: 0,
          }}>
            {isEdit
              ? t('admin.editTitle', { defaultValue: 'Edit user', name: user?.username })
              : t('admin.createTitle', { defaultValue: 'Create user' })}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            style={{
              width: 30, height: 30, borderRadius: 999,
              background: 'var(--surface-2)',
              border: '1px solid var(--hair)',
              color: 'var(--ink-3)', cursor: 'pointer',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            }}
          >
            <X size={14} />
          </button>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Field keyName="first_name" label={t('admin.fldFirst',  { defaultValue: 'First Name' })} />
            <Field keyName="last_name"  label={t('admin.fldLast',   { defaultValue: 'Last Name' })} />
          </div>
          <Field keyName="username" label={t('admin.fldUsername', { defaultValue: 'Username' })} />
          <Field keyName="email"    label={t('admin.fldEmail',    { defaultValue: 'Email' })} type="email" />
          <Field keyName="password" label={t('admin.fldPassword', { defaultValue: 'Password' })} type="password" required={!isEdit} />

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={{
                display: 'block', fontSize: 11, fontWeight: 500,
                color: 'var(--ink-3)', marginBottom: 4,
                textTransform: 'uppercase', letterSpacing: '0.04em',
              }}>
                {t('admin.thOrg', { defaultValue: 'Organisation' })}
              </label>
              <select
                value={form.organisation}
                onChange={(e) => setForm((f) => ({ ...f, organisation: e.target.value as Organisation }))}
                style={{
                  width: '100%', borderRadius: 8,
                  border: '1px solid var(--hair-2)',
                  background: 'var(--surface)', color: 'var(--ink)',
                  padding: '8px 12px', fontSize: 13, outline: 'none',
                }}
              >
                {ORGS.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
            <div>
              <label style={{
                display: 'block', fontSize: 11, fontWeight: 500,
                color: 'var(--ink-3)', marginBottom: 4,
                textTransform: 'uppercase', letterSpacing: '0.04em',
              }}>
                {t('admin.thRole', { defaultValue: 'Role' })}
              </label>
              <select
                value={form.role}
                onChange={(e) => setForm((f) => ({ ...f, role: e.target.value as Role }))}
                style={{
                  width: '100%', borderRadius: 8,
                  border: '1px solid var(--hair-2)',
                  background: 'var(--surface)', color: 'var(--ink)',
                  padding: '8px 12px', fontSize: 13, outline: 'none',
                }}
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>{ROLE_LABELS[r] ?? r}</option>
                ))}
              </select>
            </div>
          </div>

          {error && (
            <p style={{ fontSize: 12.5, color: 'var(--coral-deep)', margin: 0 }}>{error}</p>
          )}

          <div style={{ display: 'flex', gap: 10, paddingTop: 4 }}>
            <button
              type="button"
              onClick={onClose}
              style={{
                flex: 1,
                borderRadius: 8,
                border: '1px solid var(--hair-2)',
                background: 'var(--surface-2)',
                color: 'var(--ink-3)',
                padding: '10px 14px',
                fontSize: 13, fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              {t('admin.cancel', { defaultValue: 'Cancel' })}
            </button>
            <button
              type="submit"
              disabled={saving}
              style={{
                flex: 1,
                borderRadius: 8,
                border: 'none',
                background: 'var(--unfpa)',
                color: '#fff',
                padding: '10px 14px',
                fontSize: 13, fontWeight: 600,
                cursor: saving ? 'wait' : 'pointer',
                opacity: saving ? 0.6 : 1,
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              }}
            >
              {saving
                ? <LoadingSpinner size="sm" className="text-white" />
                : isEdit
                  ? t('admin.save', { defaultValue: 'Save Changes' })
                  : t('admin.createSubmit', { defaultValue: 'Create User' })}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ─── Main ────────────────────────────────────────────────────────────────────

export default function AdminPanel() {
  const { t, i18n } = useTranslation()
  const [modal, setModal] = useState<{ open: boolean; user?: AdminUser }>({ open: false })

  const fmtNum = (n: number) =>
    n.toLocaleString(i18n.language?.startsWith('bn') ? 'bn-BD' : 'en-US')

  const { data: users, loading, refetch } = usePolling<AdminUser[]>({
    fetcher: () =>
      api.get('/admin/users/').then((r) => (Array.isArray(r.data) ? r.data : r.data.results ?? [])),
    interval: 120_000,
  })

  const toggleActive = async (user: AdminUser) => {
    await api.patch(`/admin/users/${user.id}/`, { is_active: !user.is_active })
    refetch()
  }

  const stats = [
    { label: t('admin.totalUsers',  { defaultValue: 'Total Users' }),  value: (users ?? []).length },
    { label: t('admin.active',      { defaultValue: 'Active' }),       value: (users ?? []).filter((u) => u.is_active).length },
    { label: t('admin.managers',    { defaultValue: 'Managers' }),     value: (users ?? []).filter((u) => u.role === 'manager').length },
    { label: t('admin.supervisors', { defaultValue: 'Supervisors' }),  value: (users ?? []).filter((u) => u.role === 'supervisor').length },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
      {/* ───────── Hero ───────── */}
      <section className="hero" style={{ paddingBottom: 8 }}>
        <div style={{
          display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between',
          flexWrap: 'wrap', gap: 16,
        }}>
          <div>
            <div className="hero-eyebrow">
              <span className="live-dot" />
              <span>{t('admin.eyebrow', { defaultValue: 'SYSTEM · ADMIN' })}</span>
            </div>
            <h1
              className="hero-headline"
              style={{
                fontSize: 'clamp(40px, 5.5vw, 64px)',
                letterSpacing: '-0.03em',
                marginBottom: 10,
              }}
            >
              {t('admin.title', { defaultValue: 'Admin Panel' })}
            </h1>
            <p className="hero-lede" style={{ maxWidth: 640 }}>
              {t('admin.subtitle', { defaultValue: 'User Management' })}
            </p>
          </div>
          <button
            onClick={() => setModal({ open: true })}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 8,
              borderRadius: 999,
              border: 'none',
              background: 'var(--unfpa)',
              color: '#fff',
              padding: '10px 18px',
              fontSize: 13, fontWeight: 600,
              cursor: 'pointer',
              boxShadow: 'var(--sh-1)',
            }}
          >
            <Plus size={15} />
            {t('admin.addUser', { defaultValue: 'Add User' })}
          </button>
        </div>
      </section>

      {/* ───────── Stats grid ───────── */}
      <section className="section" style={{ marginTop: -8 }}>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
          gap: 12,
        }}>
          {stats.map((s) => (
            <div key={s.label} className="card" style={{ padding: 18 }}>
              <p style={{
                fontSize: 30, fontWeight: 700, color: 'var(--ink)',
                fontVariantNumeric: 'tabular-nums', lineHeight: 1, margin: 0,
              }}>
                {fmtNum(s.value)}
              </p>
              <p style={{
                fontSize: 11.5, color: 'var(--muted)', marginTop: 6,
                letterSpacing: '0.02em',
              }}>
                {s.label}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* ───────── Users table ───────── */}
      <section className="section" style={{ marginTop: 0, marginBottom: 48 }}>
        {loading && !users ? (
          <PageLoader />
        ) : (
          <div className="card flush" style={{ overflow: 'hidden' }}>
            <div style={{ overflowX: 'auto' }}>
              <table className="tbl">
                <thead>
                  <tr>
                    {[
                      t('admin.thUser',      { defaultValue: 'User' }),
                      t('admin.thOrg',       { defaultValue: 'Organisation' }),
                      t('admin.thRole',      { defaultValue: 'Role' }),
                      t('admin.thStatus',    { defaultValue: 'Status' }),
                      t('admin.thLastLogin', { defaultValue: 'Last Login' }),
                      t('admin.thActions',   { defaultValue: 'Actions' }),
                    ].map((h) => (
                      <th key={h}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(users ?? []).map((user) => {
                    const accent = ORG_ACCENT[user.organisation as Organisation] ?? 'var(--unfpa)'
                    return (
                      <tr key={user.id} style={!user.is_active ? { opacity: 0.55 } : undefined}>
                        <td>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                            <span style={{
                              width: 30, height: 30, borderRadius: 999,
                              background: `${accent}1F`,
                              color: accent,
                              fontWeight: 700, fontSize: 11.5,
                              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                              flexShrink: 0,
                            }}>
                              {(user.first_name?.[0] ?? user.username[0] ?? '?').toUpperCase()}
                            </span>
                            <div>
                              <div style={{ fontWeight: 500, color: 'var(--ink)', fontSize: 13 }}>
                                {user.first_name ? `${user.first_name} ${user.last_name}` : user.username}
                              </div>
                              <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 1 }}>
                                {user.email}
                              </div>
                            </div>
                          </div>
                        </td>
                        <td style={{ color: accent, fontWeight: 500 }}>
                          {user.organisation}
                        </td>
                        <td style={{ color: 'var(--ink-3)' }}>
                          {ROLE_LABELS[user.role] ?? user.role.replace('_', ' ')}
                        </td>
                        <td>
                          <StatusBadge
                            status={user.is_active ? 'approved' : 'rejected'}
                            overrideLabel={user.is_active
                              ? t('admin.statusActive',   { defaultValue: 'Active' })
                              : t('admin.statusInactive', { defaultValue: 'Inactive' })}
                          />
                        </td>
                        <td style={{ fontSize: 11.5, color: 'var(--muted)' }}>
                          {formatDateTime(user.last_login) || t('admin.never', { defaultValue: 'Never' })}
                        </td>
                        <td>
                          <div style={{ display: 'inline-flex', gap: 6 }}>
                            <button
                              onClick={() => setModal({ open: true, user })}
                              title={t('admin.edit', { defaultValue: 'Edit' })}
                              aria-label={t('admin.edit', { defaultValue: 'Edit' })}
                              style={{
                                width: 28, height: 28, borderRadius: 6,
                                background: 'transparent', border: 'none', cursor: 'pointer',
                                color: 'var(--ink-3)',
                                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                              }}
                            >
                              <Pencil size={14} />
                            </button>
                            <button
                              onClick={() => toggleActive(user)}
                              title={user.is_active
                                ? t('admin.deactivate', { defaultValue: 'Deactivate' })
                                : t('admin.activate',   { defaultValue: 'Activate' })}
                              aria-label={user.is_active
                                ? t('admin.deactivate', { defaultValue: 'Deactivate' })
                                : t('admin.activate',   { defaultValue: 'Activate' })}
                              style={{
                                width: 28, height: 28, borderRadius: 6,
                                background: 'transparent', border: 'none', cursor: 'pointer',
                                color: user.is_active ? '#9A1131' : '#015A28',
                                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                              }}
                            >
                              {user.is_active ? <UserX size={14} /> : <UserCheck size={14} />}
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                  {!(users ?? []).length && (
                    <tr>
                      <td colSpan={6} style={{
                        textAlign: 'center', padding: '48px 16px',
                        fontSize: 13, color: 'var(--muted)',
                      }}>
                        {t('admin.empty', { defaultValue: 'No users found.' })}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      {modal.open && (
        <UserModal
          user={modal.user}
          onClose={() => setModal({ open: false })}
          onSuccess={refetch}
        />
      )}
    </div>
  )
}
