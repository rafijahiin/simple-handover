import { FormEvent, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Eye, EyeOff } from 'lucide-react'
import { useAuth, apiErrorMessage } from '@/context/AuthContext'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'

export default function Login() {
  const { t } = useTranslation()
  const { login } = useAuth()
  const navigate   = useNavigate()
  const location   = useLocation()
  const from = (location.state as { from?: string })?.from ?? '/'

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw]     = useState(false)
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState('')

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      await login(username, password)
      navigate(from, { replace: true })
    } catch (err) {
      setError(apiErrorMessage(err, t('login.invalid')))
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <style>{`
        .login-page {
          min-height: 100vh;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 24px;
          font-family: var(--ui, system-ui, sans-serif);

          /* Single smooth gradient — UNFPA orange deepening to near-black */
          background:
            radial-gradient(ellipse 80% 60% at 50% 110%,
              rgba(249, 96, 0, 0.55) 0%,
              rgba(196, 78, 0, 0.30) 40%,
              transparent 70%),
            linear-gradient(175deg, #0C0704 0%, #1A0A02 40%, #2E1200 100%);
        }

        /* Glass card */
        .login-card {
          width: 100%;
          max-width: 420px;
          padding: 44px 40px 40px;
          border-radius: 20px;
          background: rgba(255, 255, 255, 0.055);
          backdrop-filter: blur(32px) saturate(140%);
          -webkit-backdrop-filter: blur(32px) saturate(140%);
          border: 1px solid rgba(255, 255, 255, 0.10);
          box-shadow:
            0 0 0 0.5px rgba(255,255,255,0.06) inset,
            0 2px 0 rgba(255,255,255,0.07) inset,
            0 40px 80px rgba(0, 0, 0, 0.55),
            0 12px 30px rgba(0, 0, 0, 0.35);
        }

        /* Input */
        .login-field {
          width: 100%;
          box-sizing: border-box;
          padding: 11px 14px;
          font-size: 14px;
          font-family: inherit;
          color: rgba(255, 255, 255, 0.92);
          background: rgba(255, 255, 255, 0.07);
          border: 1px solid rgba(255, 255, 255, 0.14);
          border-radius: 10px;
          outline: none;
          transition: background 0.15s, border-color 0.15s, box-shadow 0.15s;
        }
        .login-field::placeholder {
          color: rgba(255, 255, 255, 0.28);
        }
        .login-field:focus {
          background: rgba(255, 255, 255, 0.11);
          border-color: rgba(249, 96, 0, 0.65);
          box-shadow: 0 0 0 3px rgba(249, 96, 0, 0.15);
        }

        /* Button */
        .login-submit {
          width: 100%;
          padding: 12px;
          font-size: 14.5px;
          font-weight: 600;
          font-family: inherit;
          letter-spacing: 0.01em;
          color: white;
          background: #F96000;
          border: none;
          border-radius: 10px;
          cursor: pointer;
          transition: background 0.15s, box-shadow 0.15s, transform 0.1s;
          box-shadow: 0 4px 18px rgba(249, 96, 0, 0.38);
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
        }
        .login-submit:hover:not(:disabled) {
          background: #D95300;
          box-shadow: 0 6px 22px rgba(249, 96, 0, 0.48);
          transform: translateY(-1px);
        }
        .login-submit:active:not(:disabled) {
          transform: translateY(0);
        }
        .login-submit:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }
      `}</style>

      <div className="login-page">
        <div className="login-card">

          {/* ── Brand ───────────────────────────────────────────────────── */}
          <div style={{ marginBottom: 32, textAlign: 'center' }}>

            {/* S monogram */}
            <div style={{
              width: 52, height: 52,
              borderRadius: 14,
              background: 'linear-gradient(145deg, #F96000, #C44E00)',
              boxShadow: '0 4px 16px rgba(249,96,0,0.40)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              margin: '0 auto 18px',
            }}>
              <span style={{
                fontSize: 24, fontWeight: 800, color: 'white',
                letterSpacing: '-0.04em', lineHeight: 1,
              }}>S</span>
            </div>

            <h1 style={{
              margin: '0 0 6px',
              fontSize: 30,
              fontWeight: 700,
              letterSpacing: '-0.025em',
              color: 'white',
              lineHeight: 1,
            }}>
              SIMPLE
            </h1>

            <p style={{
              margin: 0,
              fontSize: 11.5,
              color: 'rgba(255,255,255,0.42)',
              lineHeight: 1.5,
              letterSpacing: '0.01em',
            }}>
              <span style={{ color: '#F96000', fontWeight: 600 }}>S</span>trengthening{' '}
              <span style={{ color: '#F96000', fontWeight: 600 }}>I</span>ntegrated{' '}
              <span style={{ color: '#F96000', fontWeight: 600 }}>M</span>onitoring,{' '}
              <span style={{ color: '#F96000', fontWeight: 600 }}>P</span>rogramme{' '}
              <span style={{ color: '#F96000', fontWeight: 600 }}>L</span>earning &amp;{' '}
              <span style={{ color: '#F96000', fontWeight: 600 }}>E</span>vidence for SRHR
            </p>
          </div>

          {/* ── Divider ─────────────────────────────────────────────────── */}
          <div style={{
            height: 1,
            margin: '0 0 28px',
            background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.10), transparent)',
          }} />

          {/* ── Form ────────────────────────────────────────────────────── */}
          <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
              <label style={{
                fontSize: 12.5, fontWeight: 500,
                color: 'rgba(255,255,255,0.58)', letterSpacing: '0.02em',
              }}>
                {t('login.username')}
              </label>
              <input
                className="login-field"
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                required
                autoComplete="username"
                autoFocus
                placeholder={t('login.usernamePlaceholder')}
              />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
              <label style={{
                fontSize: 12.5, fontWeight: 500,
                color: 'rgba(255,255,255,0.58)', letterSpacing: '0.02em',
              }}>
                {t('login.password')}
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  className="login-field"
                  type={showPw ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                  placeholder="••••••••"
                  style={{ paddingRight: 42 }}
                />
                <button
                  type="button"
                  onClick={() => setShowPw(s => !s)}
                  style={{
                    position: 'absolute', right: 12, top: '50%',
                    transform: 'translateY(-50%)',
                    background: 'none', border: 'none', padding: 0,
                    cursor: 'pointer',
                    color: 'rgba(255,255,255,0.38)',
                    display: 'flex', alignItems: 'center',
                    transition: 'color 0.15s',
                  }}
                  onMouseEnter={e => (e.currentTarget.style.color = 'rgba(255,255,255,0.70)')}
                  onMouseLeave={e => (e.currentTarget.style.color = 'rgba(255,255,255,0.38)')}
                >
                  {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            {error && (
              <div style={{
                padding: '10px 14px',
                borderRadius: 8,
                background: 'rgba(241,15,69,0.16)',
                border: '1px solid rgba(241,15,69,0.35)',
                fontSize: 13,
                color: 'rgba(255,160,170,0.95)',
                lineHeight: 1.4,
              }}>
                {error}
              </div>
            )}

            <button
              className="login-submit"
              type="submit"
              disabled={loading}
              style={{ marginTop: 4 }}
            >
              {loading
                ? <LoadingSpinner size="sm" className="text-white" />
                : t('login.signIn')
              }
            </button>
          </form>

          {/* ── Footer ──────────────────────────────────────────────────── */}
          <p style={{
            margin: '24px 0 0',
            textAlign: 'center',
            fontSize: 11,
            color: 'rgba(255,255,255,0.22)',
            letterSpacing: '0.04em',
          }}>
            {t('login.footer')}
          </p>

        </div>
      </div>
    </>
  )
}
