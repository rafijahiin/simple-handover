/**
 * Dark/light mode toggle. State lives in ThemeContext (already wired);
 * this is just the button. Visually matches the language-toggle pill
 * style for chrome consistency — same 32-tall, same rounded shape,
 * same on-brand focus ring.
 *
 * The icon morphs (Sun ↔ Moon) on toggle. Both icons sized to 14px so
 * the pill stays compact next to the language toggle in the Topbar.
 */
import { Sun, Moon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useTheme } from '@/context/ThemeContext'

export function DarkModeToggle() {
  const { theme, toggle } = useTheme()
  const { t } = useTranslation()
  const isDark = theme === 'dark'

  return (
    <button
      type="button"
      onClick={toggle}
      className="lang-toggle-btn"
      aria-label={isDark
        ? t('theme.switchToLight', { defaultValue: 'Switch to light mode' })
        : t('theme.switchToDark',  { defaultValue: 'Switch to dark mode' })}
      title={isDark
        ? t('theme.switchToLight', { defaultValue: 'Switch to light mode' })
        : t('theme.switchToDark',  { defaultValue: 'Switch to dark mode' })}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 0,
        padding: 0,
        minHeight: 32,
        minWidth: 32,
        width: 32,
        height: 32,
        borderRadius: 999,
        background: 'var(--surface-2)',
        border: '1px solid var(--hair)',
        color: 'var(--ink-3)',
        cursor: 'pointer',
        transitionProperty: 'background-color, color, transform',
        transitionDuration: '180ms',
        transitionTimingFunction: 'cubic-bezier(0.22, 1, 0.36, 1)',
      }}
    >
      {/* lucide-react renders SVG with currentColor — re-tints with the
          ink ramp automatically when the dark class flips. */}
      {isDark ? <Sun size={14} /> : <Moon size={14} />}
    </button>
  )
}
