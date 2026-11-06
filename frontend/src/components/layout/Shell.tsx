/**
 * Shell — editorial light console layout.
 *
 * app-shell grid: Spine (64px) | Main column (topbar + page canvas).
 * Atmosphere layer behind everything.
 *
 * §9 focus-on-route-change (WCAG): after the user navigates via a Link
 * the focus should move to the main content region so screen-reader
 * users hear the new page announced. We do this with a tabindex=-1 on
 * <main> and an effect that focuses it on every pathname change.
 */
import { useEffect, useRef } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Atmosphere } from './Atmosphere'
import { Spine } from './Spine'
import { Topbar } from './Topbar'

export function Shell() {
  const { pathname } = useLocation()
  const mainRef = useRef<HTMLElement>(null)

  useEffect(() => {
    // Skip the first render — focusing on initial mount would steal
    // focus from the URL bar / page load context. Only respond to
    // subsequent route changes.
    const initialMount = mainRef.current?.dataset.bootstrapped !== '1'
    if (initialMount && mainRef.current) {
      mainRef.current.dataset.bootstrapped = '1'
      return
    }
    if (mainRef.current) {
      mainRef.current.focus({ preventScroll: false })
    }
  }, [pathname])

  return (
    <div className="app-shell">
      {/* Ambient visual layer */}
      <Atmosphere />

      {/* Left rail navigation */}
      <Spine />

      {/* Main content area — tabindex=-1 so focus() works without
          making it part of the natural tab order. */}
      <main
        ref={mainRef}
        tabIndex={-1}
        className="main-col"
        style={{ outline: 'none' }}
      >
        <Topbar />
        <div className="page">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
