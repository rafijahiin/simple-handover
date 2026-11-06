/**
 * Topbar — breadcrumb header bar with live sync indicator and date.
 *
 * Sticky, frosted-glass background, mono typography.
 */
import { Link, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { RefreshCw } from 'lucide-react'
import { LanguageToggle } from './LanguageToggle'
import { DarkModeToggle } from './DarkModeToggle'
import { AIInsightsDrawer } from './AIInsightsDrawer'
import { ExportButton } from './ExportButton'

/** Each crumb is { i18nKey, to }. `to: null` means non-clickable
 *  (currently used for category labels like "DASHBOARDS" that don't
 *  have their own page). Last crumb is always the current page and
 *  rendered bold + non-clickable. */
interface Crumb { key: string; to: string | null }
const CRUMB_KEYS: Record<string, Crumb[]> = {
  '/':          [{ key: 'topbar.brand', to: '/' }, { key: 'topbar.programmeOverview', to: null }],
  '/phd':       [{ key: 'topbar.brand', to: '/' }, { key: 'topbar.dashboards', to: null }, { key: 'topbar.phd', to: null }],
  '/bondhu':    [{ key: 'topbar.brand', to: '/' }, { key: 'topbar.dashboards', to: null }, { key: 'topbar.bondhu', to: null }],
  '/approvals': [{ key: 'topbar.brand', to: '/' }, { key: 'topbar.managerApprovals', to: null }],
  '/reports':   [{ key: 'topbar.brand', to: '/' }, { key: 'topbar.reportingHub', to: null }],
  '/fistula':   [{ key: 'topbar.brand', to: '/' }, { key: 'topbar.trackers', to: null }, { key: 'topbar.fistula', to: null }],
  '/mpdsr':     [{ key: 'topbar.brand', to: '/' }, { key: 'topbar.trackers', to: null }, { key: 'topbar.mpdsr', to: null }],
  '/tracker':   [{ key: 'topbar.brand', to: '/' }, { key: 'topbar.trackers', to: null }, { key: 'topbar.progress', to: null }],
  '/baseline':  [{ key: 'topbar.brand', to: '/' }, { key: 'topbar.reports',  to: null }, { key: 'topbar.baseline', to: null }],
  '/training':  [{ key: 'topbar.brand', to: '/' }, { key: 'topbar.reports',  to: null }, { key: 'topbar.training', to: null }],
  '/admin':     [{ key: 'topbar.brand', to: '/' }, { key: 'topbar.adminPanel', to: null }],
}

export function Topbar() {
  const { t, i18n } = useTranslation()
  const { pathname } = useLocation()
  const crumbs: Crumb[] = CRUMB_KEYS[pathname] ?? [{ key: 'topbar.brand', to: '/' }]

  // Format the date using the active language's locale so বাং shows
  // Bengali numerals + month name.
  const localeForDate = i18n.language?.startsWith('bn') ? 'bn-BD' : 'en-GB'
  const dateStr = new Date().toLocaleDateString(localeForDate, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }).toUpperCase()

  return (
    <header className="topbar">
      <div className="crumb">
        {crumbs.map((c, i) => {
          const isLast = i === crumbs.length - 1
          const label = t(c.key)
          return (
            <span key={c.key}>
              {i > 0 && <span className="crumb-sep"> / </span>}
              {isLast ? (
                <b>{label}</b>
              ) : c.to ? (
                <Link to={c.to} className="crumb-link">{label}</Link>
              ) : (
                <span>{label}</span>
              )}
            </span>
          )
        })}
      </div>

      <div className="top-spacer" />

      <div className="top-pill hide-md">
        <span className="live-dot" />
        <span>{t('topbar.syncLive')}</span>
      </div>

      <div className="top-pill hide-md">
        <span>{dateStr}</span>
      </div>

      <button className="top-btn no-export" title={t('topbar.refresh')}>
        <RefreshCw size={14} />
      </button>

      {/* Export current view as PDF/PNG. Self-marked .no-export so the
          button + dropdown don't appear in the captured image. */}
      <ExportButton />

      {/* AI Insights — slide-out drawer; only appears on routes
          with AI context (home, /phd, /bondhu). */}
      <div className="no-export"><AIInsightsDrawer /></div>

      {/* Dark mode — persisted in ThemeContext localStorage */}
      <div className="no-export"><DarkModeToggle /></div>

      {/* Global language toggle — persists to localStorage, no reload. */}
      <div className="no-export"><LanguageToggle /></div>
    </header>
  )
}
