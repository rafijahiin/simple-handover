import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Shell } from '@/components/layout/Shell'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { useAuth } from '@/context/AuthContext'
import { isAdminRole } from '@/types'

const Login = lazy(() => import('@/pages/Login'))
const Home = lazy(() => import('@/pages/Home'))
const PHDDashboard = lazy(() => import('@/pages/PHDDashboard'))
const BondhuDashboard = lazy(() => import('@/pages/BondhuDashboard'))
const ManagerApprovals = lazy(() => import('@/pages/ManagerApprovals'))
const FistulaTracker = lazy(() => import('@/pages/FistulaTracker'))
const MPDSRTracker = lazy(() => import('@/pages/MPDSRTracker'))
const ReportingHub = lazy(() => import('@/pages/ReportingHub'))
const BaselineEndline = lazy(() => import('@/pages/BaselineEndline'))
const TrainingLog = lazy(() => import('@/pages/TrainingLog'))
const ProgressTracker = lazy(() => import('@/pages/ProgressTracker'))
const AdminPanel = lazy(() => import('@/pages/AdminPanel'))
const TargetConfig = lazy(() => import('@/pages/TargetConfig'))
const RecordList = lazy(() => import('@/pages/RecordList'))
const Infographics = lazy(() => import('@/pages/Infographics'))
const Profile = lazy(() => import('@/pages/Profile'))
const CIPRBDashboard = lazy(() => import('@/pages/CIPRBDashboard'))
const MpdsrAtlas = lazy(() => import('@/pages/MpdsrAtlas'))
const OpenQuestions = lazy(() => import('@/pages/OpenQuestions'))

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <PageLoader />
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

function RequireSupervisorOrDeveloper({ children }: { children: React.ReactNode }) {
  // Admin Panel = user management. Gated to system-level roles only.
  const { user } = useAuth()
  if (!user || !isAdminRole(user.role)) {
    return <Navigate to="/" replace />
  }
  return <>{children}</>
}

/** Guard for the Target Config screen.
 *  - Developer + Supervisor: read + edit any partner
 *  - Org Lead: read-only, own partner only
 *  - Everyone else: bounce to home
 *  Server enforces edit restrictions on the API (CanConfigureTargets);
 *  this guard only controls view access. */
function RequireTargetConfigAccess({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  if (!['developer', 'supervisor', 'org_lead'].includes(user.role)) {
    return <Navigate to="/" replace />
  }
  return <>{children}</>
}

/** Guard for the per-indicator record drill-down (audit FIX 6.5).
 *  Field staff and focal are denied — they don't browse approved aggregates. */
function RequireRecordListAccess({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  if (['field_staff', 'focal', 'ciprb_baseline'].includes(user.role)) {
    return <Navigate to="/" replace />
  }
  return <>{children}</>
}

/** Guard for CIPRB-owned surfaces (fistula registers, baseline survey).
 *  Cross-org admins (developer / supervisor) plus any CIPRB-org user may
 *  open them; PHD/Bandhu users typing the URL are bounced home. Finer
 *  intra-CIPRB role limits (e.g. fistula PII = org-lead+, baseline entry =
 *  ciprb_baseline) are enforced server-side. Mirrors the nav visibility. */
function RequireCIPRBOrg({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  const ok = isAdminRole(user.role) || user.organisation === 'CIPRB'
  if (!ok) return <Navigate to="/" replace />
  return <>{children}</>
}

/** Managers' only authorised surface is /approvals. Block them from any
 *  other route by redirecting back to /approvals. */
function RequireNotManager({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  if (user.role === 'manager') return <Navigate to="/approvals" replace />
  return <>{children}</>
}

/** Restrict a route to users whose `user.organisation` is in `allow` —
 *  bypassed entirely for cross-org admin roles (dev / supervisor). Used to
 *  block a Bandhu manager from typing the /phd URL and reaching the page. */
function RequireOrg({
  allow,
  children,
}: {
  allow: ('PHD' | 'Bandhu' | 'CIPRB')[]
  children: React.ReactNode
}) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  if (isAdminRole(user.role) || user.role === 'org_lead') return <>{children}</>
  if (!allow.includes(user.organisation as 'PHD' | 'Bandhu' | 'CIPRB')) {
    return <Navigate to="/" replace />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            element={
              <RequireAuth>
                <Shell />
              </RequireAuth>
            }
          >
            <Route index element={<RequireNotManager><Home /></RequireNotManager>} />
            {/* PHD + Bandhu managers see their own org dashboard — read-only,
                same KPIs/tables their org_lead sees. They still cannot reach
                other orgs (RequireOrg enforces) or cross-org tools (reports,
                tracker, training — those keep RequireNotManager). */}
            <Route
              path="phd"
              element={
                <RequireOrg allow={['PHD']}>
                  <PHDDashboard />
                </RequireOrg>
              }
            />
            <Route
              path="bondhu"
              element={
                <RequireOrg allow={['Bandhu']}>
                  <BondhuDashboard />
                </RequireOrg>
              }
            />
            {/* Modern-spelling alias — /bandhu resolves to the Bandhu org
                dashboard at /bondhu (the legacy slug). */}
            <Route path="bandhu" element={<Navigate to="/bondhu" replace />} />
            <Route path="approvals" element={<ManagerApprovals />} />
            {/* Unified CIPRB Dashboard — Fistula KPIs + registers + MPDSR in
                one place, mirroring /phd and /bondhu structure. */}
            <Route path="ciprb"    element={<RequireCIPRBOrg><CIPRBDashboard /></RequireCIPRBOrg>} />
            <Route path="atlas"    element={<RequireCIPRBOrg><MpdsrAtlas /></RequireCIPRBOrg>} />
            {/* Legacy redirects so old bookmarks still work. */}
            <Route path="fistula"  element={<Navigate to="/ciprb" replace />} />
            <Route path="mpdsr"    element={<Navigate to="/ciprb" replace />} />
            <Route path="reports"  element={<RequireNotManager><ReportingHub /></RequireNotManager>} />
            <Route path="baseline" element={<RequireCIPRBOrg><BaselineEndline /></RequireCIPRBOrg>} />
            <Route path="training" element={<RequireNotManager><TrainingLog /></RequireNotManager>} />
            <Route path="tracker"  element={<RequireNotManager><ProgressTracker /></RequireNotManager>} />
            <Route
              path="admin"
              element={
                <RequireSupervisorOrDeveloper>
                  <AdminPanel />
                </RequireSupervisorOrDeveloper>
              }
            />
            {/* Standalone Target Config route (audit FIX 4.1 restored — the
                merged tracker tab also routes here; both paths render the
                same screen). */}
            {/* /admin/targets is a stale legacy alias — the live Target
                Config UI lives at /tracker (Programme Targets tab). The
                /admin/* path is also proxied to Django in vite.config so
                this route never actually rendered in dev. Redirect for
                bookmark safety. */}
            <Route
              path="admin/targets"
              element={<Navigate to="/tracker" replace />}
            />
            {/* Record drill-down per indicator (audit FIX 6.5). */}
            <Route
              path="records"
              element={
                <RequireRecordListAccess>
                  <RecordList />
                </RequireRecordListAccess>
              }
            />
            {/* Shareable indicator infographic cards (one PNG-export
                per row). Same access as RecordList — managers and up. */}
            <Route
              path="infographics"
              element={
                <RequireRecordListAccess>
                  <Infographics />
                </RequireRecordListAccess>
              }
            />
            {/* Profile + password change — available to every authenticated user. */}
            <Route path="profile" element={<Profile />} />
            {/* Wednesday-meeting prep page — open questions for Animesh /
                Sayeed. UNFPA-only via the same gate as Target Config. */}
            <Route
              path="open-questions"
              element={
                <RequireTargetConfigAccess>
                  <OpenQuestions />
                </RequireTargetConfigAccess>
              }
            />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}
