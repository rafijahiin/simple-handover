/**
 * Two-button pill toggle [EN | বাং] for switching the entire UI
 * language without a page reload. Persists selection to localStorage
 * (see `setLanguage` in src/i18n/index.ts).
 */
import { useTranslation } from 'react-i18next'
import { setLanguage, type Lang } from '@/i18n'

const OPTIONS: { code: Lang; label: string }[] = [
  { code: 'en', label: 'EN' },
  { code: 'bn', label: 'বাং' },
]

export function LanguageToggle() {
  const { i18n, t } = useTranslation()
  // i18n.language reflects the active selection synchronously after
  // changeLanguage(); i18n.resolvedLanguage lags by one render under
  // some fallback configurations and made the active-state visual
  // appear stuck on the previous language.
  const current = ((i18n.language || 'en').split('-')[0] as Lang)

  return (
    <div
      role="group"
      aria-label="Language"
      style={{
        display: 'inline-flex',
        gap: 2,
        padding: 2,
        background: 'var(--surface-2)',
        border: '1px solid var(--hair)',
        borderRadius: 999,
      }}
    >
      {OPTIONS.map((o) => {
        const active = current === o.code
        return (
          <button
            key={o.code}
            type="button"
            onClick={() => setLanguage(o.code)}
            title={t('language.switchTo', { lang: o.label })}
            aria-pressed={active}
            // Inner padding sized so the rendered pill is ≥32px tall +
            // each button is ≥36px wide. Hit-area then expands to 44pt
            // via the .lang-toggle-btn :focus-visible / hit-area CSS
            // (see index.css). Meets §2 touch-target-size on mobile.
            className="lang-toggle-btn"
            style={{
              padding: '6px 12px',
              fontSize: 12,
              fontWeight: active ? 600 : 500,
              lineHeight: 1.2,
              color: active ? '#fff' : 'var(--ink-2)',
              background: active ? 'var(--unfpa)' : 'transparent',
              border: 'none',
              borderRadius: 999,
              cursor: active ? 'default' : 'pointer',
              transitionProperty: 'background-color, color, box-shadow',
              transitionDuration: '150ms',
              minHeight: 32,
              minWidth: 36,
            }}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}
