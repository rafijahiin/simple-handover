/**
 * Spine — 64→220px collapsible left rail navigation.
 *
 * Matches the editorial light console design: minimal vertical strip,
 * UNFPA blue active indicator bar, live badge for pending approvals.
 * S logo toggles expanded/collapsed. Includes KoboToolbox form links panel.
 */
import { useState, useRef, useEffect } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  Home, Building2, HeartHandshake, ClipboardCheck, FileBarChart2,
  ShieldAlert, LogOut, ExternalLink,
  HeartPulse, ClipboardList, Smartphone,
  Target, Settings, UserCog, X, Menu, Map,
} from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { api } from '@/api/client'

import type { Role, Organisation } from '@/types'
import { isAdminRole } from '@/types'

interface SpineItemDef {
  to: string
  /** i18n key under the `nav.*` namespace — resolved at render time. */
  i18nKey: string
  icon: React.ReactNode
  badge?: number | null
  /** Per-item visibility predicate. If omitted, item is visible to all
   *  authenticated users. Receives current role+org for fine-grained gating. */
  visible?: (role: Role, organisation: Organisation) => boolean
}

// Manager role is approvals-only per the IDMS handoff. They never see
// dashboards, the tracker, reports hub, MPDSR, baseline, or training —
// only the Approvals queue. Helper below makes the visibility predicate
// explicit and short.
const notManager = (r: Role) => r !== 'manager'

const PRIMARY_NAV: SpineItemDef[] = [
  // Home: every role except manager. Managers land directly on /approvals
  // (default redirect handled in App.tsx).
  { to: '/',         i18nKey: 'nav.programmeOverview', icon: <Home size={18} />,
    visible: (r) => notManager(r) },
  { to: '/ciprb',    i18nKey: 'nav.ciprbDashboard',    icon: <HeartPulse size={18} />,
    visible: (r, o) => isAdminRole(r) || r === 'org_lead' || o === 'CIPRB' },
  // National MPDSR GIS Atlas (2024 district/division death maps).
  { to: '/atlas',    i18nKey: 'nav.mpdsrAtlas',        icon: <Map size={18} />,
    visible: (r, o) => isAdminRole(r) || r === 'org_lead' || o === 'CIPRB' },
  // Org dashboard: visible to anyone in that org (manager, focal, org_lead)
  // plus cross-org admin roles. Managers see their own org's KPIs so they
  // can spot-check trends before approving submissions.
  { to: '/phd',      i18nKey: 'nav.phdDashboard',      icon: <Building2 size={18} />,
    visible: (r, o) => isAdminRole(r) || r === 'org_lead' || o === 'PHD' },
  { to: '/bondhu',   i18nKey: 'nav.bondhuDashboard',   icon: <HeartHandshake size={18} />,
    visible: (r, o) => isAdminRole(r) || r === 'org_lead' || o === 'Bandhu' },
  // Approvals: managers + above. This is the ONLY nav item a manager sees.
  { to: '/approvals',i18nKey: 'nav.managerApprovals',  icon: <ClipboardCheck size={18} />,
    visible: (r) => ['developer','supervisor','org_lead','manager'].includes(r) },
  { to: '/reports',  i18nKey: 'nav.reportingHub',      icon: <FileBarChart2 size={18} />,
    visible: (r) => ['developer','supervisor','org_lead'].includes(r) },
  { to: '/infographics', i18nKey: 'nav.infographics',  icon: <FileBarChart2 size={18} />,
    visible: (r) => ['developer','supervisor','org_lead','manager'].includes(r) },
]

const SECONDARY_NAV: SpineItemDef[] = [
  // Fistula + MPDSR moved into the unified CIPRB Dashboard (above).
  { to: '/tracker',  i18nKey: 'nav.progressTracker',  icon: <Target size={18} />,
    visible: (r) => ['developer','supervisor','org_lead'].includes(r) },
  { to: '/baseline', i18nKey: 'nav.baselineEndline',  icon: <ClipboardList size={18} />,
    visible: (r, o) => isAdminRole(r) || (r === 'org_lead' && o === 'CIPRB') || o === 'CIPRB' },
]

/** Filter a nav array by the current user's role + org. */
function filterByVisibility(items: SpineItemDef[], user: { role: Role; organisation: Organisation } | null) {
  if (!user) return [] as SpineItemDef[]
  return items.filter((i) => (i.visible ? i.visible(user.role, user.organisation as Organisation) : true))
}

// ─── KoboToolbox form links ──────────────────────────────────────────────────

interface KoboForm {
  url: string
  label: string
  labelBn: string
}

interface KoboGroup {
  heading: string
  forms: KoboForm[]
  /** Optional visibility predicate. When omitted, the group is visible
   *  to every authenticated user. When set, returns true only for users
   *  who should see this group. */
  visible?: (role: string, organisation: string) => boolean
}

// Allow CIPRB monitoring users (UNFPA supervisors + Developer) to see PHD's
// dashboard. PHD-specific forms are visible to PHD organisations + UNFPA
// supervisors + Developer (the same 'monitoring + own-org' rule applied
// elsewhere). Bandhu and CIPRB org members never see PHD forms.
const isPhdVisible = (role: string, organisation: string): boolean => {
  if (role === 'developer' || role === 'supervisor') return true
  if (organisation === 'PHD') return true
  if (organisation === 'UNFPA') return true
  return false
}

// CIPRB Phase 2 — 9 new forms (Fistula QB + MPDSR 1/2/4/5 + Social Autopsy
// + 2 notification slips + Maternal Near Miss). Visible to CIPRB org
// users + UNFPA monitoring + Developer; never shown to PHD/Bandhu.
const isCiprbVisible = (role: string, organisation: string): boolean => {
  if (role === 'developer' || role === 'supervisor') return true
  if (organisation === 'CIPRB') return true
  if (organisation === 'UNFPA') return true
  return false
}

// Bandhu's 2 consolidated forms (Service Log + Activity & Operations). Visible
// to Bandhu org users + UNFPA monitoring + Developer; never shown to PHD/CIPRB.
const isBandhuVisible = (role: string, organisation: string): boolean => {
  if (role === 'developer' || role === 'supervisor') return true
  if (organisation === 'Bandhu') return true
  if (organisation === 'UNFPA') return true
  return false
}

const KOBO_GROUPS: KoboGroup[] = [
  {
    heading: 'CIPRB — MPDSR & Fistula',
    visible: isCiprbVisible,
    forms: [
      // Phase 2 — the 9 new CIPRB XLSForms (bilingual Bangla + English).
      // Offline Enketo URLs so they work without a constant network.
      { url: 'https://ee.kobotoolbox.org/x/fgFVgdrF',
        label: 'CIPRB 1 — Fistula Question Bank',
        labelBn: 'সিআইপিআরবি ১ — ফিস্টুলা প্রশ্নাবলী' },
      { url: 'https://ee.kobotoolbox.org/x/DwFp6Nhx',
        label: 'CIPRB 2 — MPDSR Form 01 (Community Maternal)',
        labelBn: 'সিআইপিআরবি ২ — এমপিডিএসআর ফর্ম-১ (কমিউনিটি মাতৃমৃত্যু)' },
      { url: 'https://ee.kobotoolbox.org/x/ipUTJ9qH',
        label: 'CIPRB 3 — MPDSR Form 02 (Community Neonatal)',
        labelBn: 'সিআইপিআরবি ৩ — এমপিডিএসআর ফর্ম-২ (কমিউনিটি নবজাতক মৃত্যু)' },
      { url: 'https://ee.kobotoolbox.org/x/5Z0xMqTa',
        label: 'CIPRB 4 — MPDSR Form 04 (Facility Maternal)',
        labelBn: 'সিআইপিআরবি ৪ — এমপিডিএসআর ফর্ম-৪ (ফ্যাসিলিটি মাতৃমৃত্যু)' },
      { url: 'https://ee.kobotoolbox.org/x/b8FQVLdU',
        label: 'CIPRB 5 — MPDSR Form 05 (Facility Neonatal)',
        labelBn: 'সিআইপিআরবি ৫ — এমপিডিএসআর ফর্ম-৫ (ফ্যাসিলিটি নবজাতক মৃত্যু)' },
      { url: 'https://ee.kobotoolbox.org/x/iPEeXGJt',
        label: 'CIPRB 6 — Social Autopsy',
        labelBn: 'সিআইপিআরবি ৬ — সামাজিক ময়নাতদন্ত' },
      { url: 'https://ee.kobotoolbox.org/x/0riUz39q',
        label: 'CIPRB 7 — Notification Slip 01',
        labelBn: 'সিআইপিআরবি ৭ — অবহিতকরণ স্লিপ ০১' },
      { url: 'https://ee.kobotoolbox.org/x/z12d0TVs',
        label: 'CIPRB 8 — Notification Slip 02',
        labelBn: 'সিআইপিআরবি ৮ — অবহিতকরণ স্লিপ ০২' },
      { url: 'https://ee.kobotoolbox.org/x/UsS0Cwbi',
        label: 'CIPRB 9 — Maternal Near Miss audit',
        labelBn: 'সিআইপিআরবি ৯ — মাতৃ নিকট-মৃত্যু অডিট' },
      { url: 'https://ee.kobotoolbox.org/x/S07hvhWy',
        label: 'CIPRB 10 — MPDSR Response Plan',
        labelBn: 'সিআইপিআরবি ১০ — এমপিডিএসআর রেসপন্স প্ল্যান' },
      { url: 'https://ee.kobotoolbox.org/x/zsM2QmAv',
        label: 'CIPRB 11 — Safe Surgery Checklist',
        labelBn: 'সিআইপিআরবি ১১ — নিরাপদ অস্ত্রোপচার চেকলিস্ট' },
      // Older CIPRB forms still in use — listed under CIPRB (no separate legacy section).
      { url: 'https://ee.kobotoolbox.org/x/fgFVgdrF', label: 'KF-Fistula Staged',     labelBn: 'ফিস্টুলা স্টেজড ট্র্যাকার' },
      { url: 'https://ee.kobotoolbox.org/x/DwFp6Nhx', label: 'MPDSR Form',             labelBn: 'মাতৃমৃত্যু ফর্ম' },
      { url: 'https://ee.kobotoolbox.org/x/1kkC2bTE', label: 'Fistula Campaign',       labelBn: 'ফিস্টুলা ফর্ম' },
      { url: 'https://ee.kobotoolbox.org/x/tzGBA7nj',
        label: 'CIPRB Baseline — Hijra / Gender-diverse',
        labelBn: 'সিআইপিআরবি বেসলাইন — হিজড়া/প্রান্তিক জনগোষ্ঠী' },
      { url: 'https://ee.kobotoolbox.org/x/83PhCEZ4',
        label: 'CIPRB Baseline — Female Sex Workers',
        labelBn: 'সিআইপিআরবি বেসলাইন — নারী যৌনকর্মী' },
    ],
  },
  {
    heading: 'PHD — FSW SRHR',
    visible: isPhdVisible,
    forms: [
      // Registration — filled once per FSW (creates the permanent ID No).
      // Enketo offline_url — public collect link, works without login.
      { url: 'https://ee.kobotoolbox.org/x/NesXOMsL',
        label: 'PHD 1 — FSW Registration', labelBn: 'যৌনকর্মী নিবন্ধন' },
      // Service Log — daily form with a "What are you recording?" selector
      // that opens the correct section (clinic / HTC / counselling / referral
      // / group education / event / IEC material / GBV corner / stock).
      { url: 'https://ee.kobotoolbox.org/x/o7GhleIk',
        label: 'PHD 2 — Service Log', labelBn: 'সেবা ও কার্যক্রম লগ' },
      // Zero-day return — filed when a centre has nothing to report that day.
      // Shared PHD + Bandhu form; each team picks its own centre.
      { url: 'https://ee.kobotoolbox.org/x/3Ke0ktqc',
        label: 'No Reporting Today', labelBn: 'আজ রিপোর্ট করার কিছু নেই' },
    ],
  },
  {
    heading: 'Bandhu — Key Population SRHR',
    visible: isBandhuVisible,
    forms: [
      // Mother List — beneficiary registration; builds the client master list
      // the Service Log/Activity forms autofill from (Bandhu's PHD-registration
      // equivalent). F-1.1.
      { url: 'https://ee.kobotoolbox.org/x/VO1m2jh1',
        label: 'Bandhu 0 — Mother List', labelBn: 'বন্ধু ০ — মাদার লিস্ট' },
      // Service Log — per-client registers (F-01 logbook, F-05 patient record,
      // F-06 HTC, F-02 GBV, F-03 MH counselling, Counseling, Referral, F-08).
      { url: 'https://ee.kobotoolbox.org/x/DMOqdJFx',
        label: 'Bandhu 1 — Service Log', labelBn: 'বন্ধু ১ — সেবা লগ' },
      // Activity & Operations — F-04 outreach, F-10 mobile camp, F-11
      // attendance, F-12 event report, F-13 stock, F-14 e-billboard.
      { url: 'https://ee.kobotoolbox.org/x/WoHgXucH',
        label: 'Bandhu 2 — Activity & Operations', labelBn: 'বন্ধু ২ — কার্যক্রম ও পরিচালন' },
      // Zero-day return — shared PHD + Bandhu form; each team picks its own centre.
      { url: 'https://ee.kobotoolbox.org/x/3Ke0ktqc',
        label: 'No Reporting Today', labelBn: 'আজ রিপোর্ট করার কিছু নেই' },
    ],
  },
]

// ─── Component ───────────────────────────────────────────────────────────────

// Expand mechanism — hover-only.
//
// Previously the rail had a "pinned" state toggled by clicking the S
// brand. That broke logo convention (top-left logo should go home) and
// the pin/unpin model wasn't worth the complexity for a sidebar that's
// fundamentally browse-by-icon. Now the S routes home and the rail
// expands transiently on hover (350ms in, 250ms out), Linear/Notion-
// style. The transient state is local — no localStorage.
//
// The mobile hamburger still flips the rail open as a drawer; that one
// stays click-driven because hover has no meaning on touch.
export function Spine() {
  const { t } = useTranslation()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [expanded, setExpanded] = useState(false)
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [koboOpen, setKoboOpen] = useState(false)
  const [pendingCount, setPendingCount] = useState<number>(0)
  const panelRef = useRef<HTMLDivElement>(null)
  const spineRef = useRef<HTMLElement>(null)

  const handleSpineMouseEnter = () => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current)
    hoverTimerRef.current = setTimeout(() => setExpanded(true), 350)
  }
  const handleSpineMouseLeave = () => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current)
    hoverTimerRef.current = setTimeout(() => setExpanded(false), 250)
  }

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  // Badge = the per-role pending count the user can actually act on
  // (PendingApprovalsView.total). UNFPA sees its stage-2 queue (Bandhu
  // MANAGER_APPROVED), managers see their own-org PENDING, super sees all.
  // The old /dashboard/kpis/ submissions_pending counted only PENDING for
  // everyone, so UNFPA's stage-2 queue showed 0. Fall back to it if the
  // per-role endpoint is unavailable — the badge can never get worse.
  // count_only: this poll runs every 30s on every page for every signed-in
  // user and reads one number. Without it the server serialises the whole
  // queue (~86 KB an answer) to deliver that number — it was 57% of the
  // deployment's HTTP egress. The response still carries total / counts_by_org.
  useEffect(() => {
    let cancelled = false
    const fetchPending = () => {
      api.get('/programs/pending-approvals/', { params: { count_only: 1 } })
        .then(r => { if (!cancelled) setPendingCount(r.data?.total ?? 0) })
        .catch(() => {
          api.get('/dashboard/kpis/')
            .then(r => { if (!cancelled) setPendingCount(r.data?.submissions_pending ?? 0) })
            .catch(() => {})
        })
    }
    fetchPending()
    const interval = setInterval(fetchPending, 30_000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [])

  // Close kobo panel on outside click
  useEffect(() => {
    if (!koboOpen) return
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setKoboOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [koboOpen])

  // Close expanded spine on outside click (mobile drawer use-case).
  useEffect(() => {
    if (!expanded) return
    const handler = (e: MouseEvent) => {
      if (spineRef.current && !spineRef.current.contains(e.target as Node)) {
        setExpanded(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [expanded])

  // Close on Escape.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (koboOpen) setKoboOpen(false)
        else if (expanded) setExpanded(false)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [koboOpen, expanded])

  const initials = user
    ? (user.full_name || user.email)
        .split(' ')
        .map(p => p[0])
        .join('')
        .slice(0, 2)
        .toUpperCase()
    : '?'

  // Filter nav arrays by role + organisation, then attach the live
  // approval-queue badge to the Approvals item if it survived the filter.
  const visiblePrimary = filterByVisibility(PRIMARY_NAV, user)
    .map(item => item.to === '/approvals' ? { ...item, badge: pendingCount } : item)
  const visibleSecondary = filterByVisibility(SECONDARY_NAV, user)

  // Close drawer when a nav link is clicked (helpful on mobile)
  const handleNavClick = () => setExpanded(false)

  return (
    <>
      {/* Mobile-only hamburger toggle — fixed top-left, hidden on desktop. */}
      <button
        className="mobile-menu-btn"
        title={expanded ? 'Close menu' : 'Open menu'}
        aria-label={expanded ? 'Close menu' : 'Open menu'}
        onClick={() => setExpanded(prev => !prev)}
      >
        {expanded ? <X size={20} /> : <Menu size={20} />}
      </button>

      {/* Mobile backdrop — visible only when drawer open on mobile */}
      {expanded && <div className="spine-backdrop" onClick={() => setExpanded(false)} />}

      <aside
        ref={spineRef}
        className={`spine ${expanded ? 'spine-expanded' : ''}`}
        onMouseEnter={handleSpineMouseEnter}
        onMouseLeave={handleSpineMouseLeave}
      >
      {/* No logo per UNFPA brand kit — using the UNFPA logo for a
          third-party programme would violate the kit (logo cannot be
          altered or combined with other taglines). The "Spondon"
          wordmark lives in the Topbar breadcrumb, which is a Link
          back to home. The spine's top space stays clean — just a
          modest vertical gap so the first nav item doesn't crash
          into the rail edge. */}
      <div className="spine-top-spacer" aria-hidden="true" />

      {/* Primary nav group */}
      <div className="spine-group">
        {visiblePrimary.map(item => (
          <SpineItem key={item.to} {...item} expanded={expanded} onNavigate={handleNavClick} />
        ))}
      </div>

      <div className="spine-sep" />

      {/* Secondary nav group */}
      <div className="spine-group">
        {visibleSecondary.map(item => (
          <SpineItem key={item.to} {...item} expanded={expanded} onNavigate={handleNavClick} />
        ))}
      </div>

      <div className="spine-sep" />

      {/* Utilities */}
      <div className="spine-group">
        {/* KoboToolbox form links */}
        <button
          className={`spine-item ${koboOpen ? 'active' : ''}`}
          title={t('nav.koboForms')}
          onClick={() => setKoboOpen(p => !p)}
        >
          <Smartphone size={18} />
          {expanded ? <span className="spine-label">{t('nav.koboForms')}</span> : <span className="spine-tip">{t('nav.koboForms')}</span>}
        </button>

        {/* Search + Notifications removed — they were dead buttons (no
            handler, no backend). Re-add when there's a real global search
            and a notifications feed wired to the alerts API. */}
      </div>

      {/* Footer */}
      <div className="spine-foot">
        {/* Admin Panel — only for system admins (developer / supervisor). */}
        {user && isAdminRole(user.role) && (
          <NavLink
            to="/admin"
            className={({ isActive }) => `spine-item ${isActive ? 'active' : ''}`}
            title={t('nav.adminPanel')}
          >
            <UserCog size={18} />
            {expanded ? <span className="spine-label">{t('nav.adminPanel')}</span> : <span className="spine-tip">{t('nav.adminPanel')}</span>}
          </NavLink>
        )}
        {/* Profile & password — available to EVERY authenticated user
            (including UNFPA supervisors, who previously only saw Admin Panel
            and had no visible Profile entry). */}
        <NavLink
          to="/profile"
          className={({ isActive }) => `spine-item ${isActive ? 'active' : ''}`}
          title={t('nav.profile', { defaultValue: 'Profile & password' })}
        >
          <Settings size={18} />
          {expanded
            ? <span className="spine-label">{t('nav.profile', { defaultValue: 'Profile' })}</span>
            : <span className="spine-tip">{t('nav.profile', { defaultValue: 'Profile' })}</span>}
        </NavLink>
        <button className="spine-item" onClick={handleLogout} title={t('nav.logout')}>
          <LogOut size={18} />
          {expanded ? <span className="spine-label">{t('nav.logout')}</span> : <span className="spine-tip">{t('nav.logout')}</span>}
        </button>
        <NavLink
          to="/profile"
          className="spine-avatar"
          title={user?.full_name || user?.email || 'Profile'}
          style={{ textDecoration: 'none' }}
        >
          {initials}
        </NavLink>
      </div>

      {/* KoboToolbox slide-out panel */}
      {koboOpen && (
        <div ref={panelRef} className="kobo-panel">
          <div className="kobo-panel-header">
            <div>
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink)' }}>KoboToolbox Forms</div>
              <div className="bn mute" style={{ fontSize: 11 }}>কোবোটুলবক্স ফর্ম</div>
            </div>
            <button onClick={() => setKoboOpen(false)} className="kobo-panel-close" title="Close">
              <X size={16} />
            </button>
          </div>
          <div className="kobo-panel-body scroll-thin">
            {KOBO_GROUPS.filter(group =>
              !group.visible ||
              (user ? group.visible(user.role, user.organisation as string) : false),
            ).map(group => (
              <div key={group.heading} className="kobo-group">
                <div className="kobo-group-heading">{group.heading}</div>
                {group.forms.map(form => (
                  <a
                    key={form.url}
                    href={form.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="kobo-form-link"
                    title={form.labelBn}  /* Bangla on hover — no more stacked dual labels */
                  >
                    <span style={{ flex: 1, color: 'var(--ink)' }}>{form.label}</span>
                    <ExternalLink size={13} style={{ color: 'var(--muted)', flexShrink: 0 }} />
                  </a>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </aside>
    </>
  )
}

function SpineItem({ to, i18nKey, icon, badge, expanded, onNavigate }: SpineItemDef & { expanded?: boolean; onNavigate?: () => void }) {
  const { t } = useTranslation()
  const label = t(i18nKey)
  return (
    <NavLink
      to={to}
      end={to === '/'}
      onClick={onNavigate}
      className={({ isActive }) => `spine-item ${isActive ? 'active' : ''}`}
    >
      {icon}
      {badge != null && badge > 0 && <span className="badge">{badge}</span>}
      {expanded ? (
        <span className="spine-label">{label}</span>
      ) : (
        <span className="spine-tip">{label}</span>
      )}
    </NavLink>
  )
}
