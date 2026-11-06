/**
 * ExportButton — capture the current page as PDF or PNG.
 *
 * Uses html2canvas to rasterise the <main> element, then either
 * downloads it directly as PNG or pipes it into jsPDF for a sized
 * A4-portrait PDF. The capture target is the same <main> region the
 * WCAG focus hook in Shell.tsx already targets, so what the user sees
 * is what they export.
 *
 * Tradeoffs (declared up front):
 *   - html2canvas rasterises with the browser's current rendering, so
 *     fonts + colours match exactly. Cost: large images for tall pages.
 *   - PDF flow: single-page A4 portrait, content scaled to fit width.
 *     Tall pages get scaled down (everything fits, but small text may
 *     become unreadable). Multi-page slicing is a future enhancement.
 *   - Hidden during capture: the Topbar's controls (refresh / dark /
 *     language / AI / export buttons themselves), via a .no-export class.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation } from 'react-router-dom'
import { Download, ChevronDown, FileText, Image as ImageIcon, AlertCircle, X } from 'lucide-react'
import { motion, AnimatePresence } from 'motion/react'

// Slug-friendly page name from route.
function pageNameFromPath(p: string): string {
  if (p === '/') return 'home'
  return p.replace(/^\//, '').replace(/\//g, '-')
}

// Today's date as YYYY-MM-DD for the filename.
function todayStamp(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function ExportButton() {
  const { t } = useTranslation()
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState<null | 'pdf' | 'png'>(null)
  const [errMsg, setErrMsg] = useState<string | null>(null)
  // Non-fatal notice when the export succeeded but had to skip the
  // map area due to stale cached tiles. Shown in the same slot as
  // errMsg, styled as info rather than error.
  const [noticeMsg, setNoticeMsg] = useState<string | null>(null)

  useEffect(() => {
    if (!noticeMsg) return
    const id = setTimeout(() => setNoticeMsg(null), 6000)
    return () => clearTimeout(id)
  }, [noticeMsg])

  // Auto-dismiss error toast after 6s so it doesn't linger.
  useEffect(() => {
    if (!errMsg) return
    const id = setTimeout(() => setErrMsg(null), 6000)
    return () => clearTimeout(id)
  }, [errMsg])

  const filenameBase = `simple-${pageNameFromPath(pathname)}-${todayStamp()}`

  /**
   * Dynamic imports keep jspdf + html2canvas out of the main bundle.
   * They land in their own chunk only when the user actually triggers
   * an export. Saves ~250 KB on initial load.
   */
  /**
   * Capture <main> as a canvas. Primary engine is modern-screenshot,
   * which handles CSS variables in SVG `<stopColor>` and `<pattern>`
   * elements correctly — html2canvas crashed on those with
   * "createPattern ... canvas with width or height of 0" when recharts
   * gradients in the OrgDashboard area chart were on screen.
   *
   * Two-tier capture:
   *   1. First attempt: full <main>, map included.
   *   2. Fallback: if anything throws a tainted-canvas / CORS error
   *      (stale cached Leaflet tiles from before the crossOrigin prop
   *      was added), retry skipping the leaflet container. The map
   *      area shows as a blank rectangle; mapSkipped flips so the
   *      caller can notify the user.
   */
  const captureMain = async (): Promise<{ canvas: HTMLCanvasElement; mapSkipped: boolean }> => {
    const { domToCanvas } = await import('modern-screenshot')
    const target = document.querySelector('main') as HTMLElement
    if (!target) throw new Error('main element not found')

    const bg = getComputedStyle(document.documentElement)
      .getPropertyValue('--paper').trim() || '#EFF1F7'

    const baseOpts = {
      backgroundColor: bg,
      scale: 1.5,
      // Skip our chrome controls + iframes during the capture.
      filter: (node: Node) => {
        if (!(node instanceof Element)) return true
        if (node.classList.contains('no-export')) return false
        if (node.tagName === 'IFRAME') return false
        return true
      },
    }

    // Attempt 1 — include the map.
    try {
      const canvas = await domToCanvas(target, baseOpts)
      // Force-touch to surface any taint NOW rather than at toBlob time.
      canvas.toDataURL()
      return { canvas, mapSkipped: false }
    } catch (e) {
      const msg = (e as Error)?.message?.toLowerCase() ?? ''
      const tainted = msg.includes('tainted') || msg.includes('cors') || msg.includes('security')
      if (!tainted) throw e
      // Attempt 2 — skip Leaflet entirely.
      const canvas = await domToCanvas(target, {
        ...baseOpts,
        filter: (node: Node) => {
          if (!(node instanceof Element)) return true
          if (node.classList.contains('no-export')) return false
          if (node.classList.contains('leaflet-container')) return false
          if (node.classList.contains('leaflet-pane')) return false
          if (node.tagName === 'IFRAME') return false
          return true
        },
      })
      return { canvas, mapSkipped: true }
    }
  }

  /** Convert any thrown export error into a short, user-readable line. */
  const friendlyError = (e: unknown): string => {
    if (e instanceof Error) {
      const msg = e.message.toLowerCase()
      if (msg.includes('tainted') || msg.includes('cors') || msg.includes('security')) {
        return t('export.errCors', {
          defaultValue: 'Some images on this page block export. The map area will be skipped — please try again.',
        })
      }
      if (msg.includes('oklch') || msg.includes('color') || msg.includes('parse')) {
        return t('export.errColor', {
          defaultValue: 'Browser color parsing failed during export. Try toggling dark mode off and retry.',
        })
      }
      return e.message || t('export.errGeneric', { defaultValue: 'Export failed.' })
    }
    return t('export.errGeneric', { defaultValue: 'Export failed.' })
  }

  const mapSkippedNotice = () => t('export.mapSkipped', {
    defaultValue: 'Saved without the map — your cached tiles loaded before CORS was enabled. Hard refresh the page (Ctrl+Shift+R) and the map will appear in the next export.',
  })

  const exportPNG = async () => {
    setBusy('png')
    setErrMsg(null)
    setNoticeMsg(null)
    try {
      const { canvas, mapSkipped } = await captureMain()
      const blob = await new Promise<Blob | null>((res) =>
        canvas.toBlob(res, 'image/png'),
      )
      if (!blob) throw new Error('canvas.toBlob returned null')
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${filenameBase}.png`
      a.click()
      URL.revokeObjectURL(url)
      setOpen(false)
      if (mapSkipped) setNoticeMsg(mapSkippedNotice())
    } catch (e) {
      console.error('PNG export failed', e)
      setErrMsg(friendlyError(e))
    } finally {
      setBusy(null)
    }
  }

  const exportPDF = async () => {
    setBusy('pdf')
    setErrMsg(null)
    setNoticeMsg(null)
    try {
      const { jsPDF } = await import('jspdf')
      const { canvas, mapSkipped } = await captureMain()
      const imgData = canvas.toDataURL('image/png')
      const pdf = new jsPDF({ unit: 'mm', format: 'a4', orientation: 'portrait' })
      const pageW = pdf.internal.pageSize.getWidth()
      const pageH = pdf.internal.pageSize.getHeight()
      const margin = 8
      const imgW = pageW - margin * 2
      const imgH = (canvas.height * imgW) / canvas.width
      if (imgH <= pageH - margin * 2) {
        pdf.addImage(imgData, 'PNG', margin, margin, imgW, imgH)
      } else {
        const scaled = pageH - margin * 2
        const scaledW = (canvas.width * scaled) / canvas.height
        const offsetX = (pageW - scaledW) / 2
        pdf.addImage(imgData, 'PNG', offsetX, margin, scaledW, scaled)
      }
      pdf.save(`${filenameBase}.pdf`)
      setOpen(false)
      if (mapSkipped) setNoticeMsg(mapSkippedNotice())
    } catch (e) {
      console.error('PDF export failed', e)
      setErrMsg(friendlyError(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="no-export" style={{ position: 'relative' }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={busy !== null}
        className="lang-toggle-btn"
        title={t('export.title', { defaultValue: 'Export current view' })}
        aria-label={t('export.title', { defaultValue: 'Export current view' })}
        aria-expanded={open}
        aria-haspopup="menu"
        style={{
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          gap: 4, padding: '0 6px 0 10px',
          minHeight: 32, height: 32,
          borderRadius: 999,
          background: 'var(--surface-2)',
          border: '1px solid var(--hair)',
          color: 'var(--ink-3)',
          cursor: busy ? 'wait' : 'pointer',
        }}
      >
        <Download size={13} />
        <ChevronDown size={11} style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 150ms ease' }} />
      </button>

      <AnimatePresence mode="wait">
        {open && (
          <>
            <div
              onClick={() => setOpen(false)}
              style={{ position: 'fixed', inset: 0, zIndex: 90 }}
            />
            <motion.div
              role="menu"
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0, transition: { duration: 0.16, ease: [0.22, 1, 0.36, 1] } }}
              exit={{ opacity: 0, y: -4, transition: { duration: 0.12 } }}
              style={{
                position: 'absolute', top: 'calc(100% + 6px)', right: 0,
                minWidth: 200, padding: 4, borderRadius: 10,
                background: 'var(--surface)',
                border: '1px solid var(--hair)',
                boxShadow: 'var(--sh-2)',
                zIndex: 100,
              }}
            >
              <MenuItem
                icon={<FileText size={14} />}
                label={t('export.pdf', { defaultValue: 'Save as PDF (A4)' })}
                onClick={exportPDF}
                disabled={busy !== null}
                busy={busy === 'pdf'}
              />
              <MenuItem
                icon={<ImageIcon size={14} />}
                label={t('export.png', { defaultValue: 'Save as PNG image' })}
                onClick={exportPNG}
                disabled={busy !== null}
                busy={busy === 'png'}
              />
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* Non-fatal map-skipped notice. Same slot as the error toast
          but blue-tinted (info, not error). */}
      <AnimatePresence mode="wait">
        {noticeMsg && !errMsg && (
          <motion.div
            key="export-notice"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0, transition: { duration: 0.16 } }}
            exit={{ opacity: 0, y: -4, transition: { duration: 0.12 } }}
            role="status"
            aria-live="polite"
            style={{
              position: 'absolute', top: 'calc(100% + 6px)', right: 0,
              width: 320, padding: '12px 14px', borderRadius: 10,
              background: 'rgba(33, 113, 236, 0.06)',
              border: '1px solid rgba(33, 113, 236, 0.20)',
              boxShadow: 'var(--sh-2)',
              zIndex: 110,
              display: 'flex', alignItems: 'flex-start', gap: 10,
              fontSize: 12.5, color: 'var(--ink)',
              lineHeight: 1.45,
            }}
          >
            <AlertCircle size={15} style={{ color: '#1E3A8A', flexShrink: 0, marginTop: 1 }} />
            <div style={{ flex: 1, minWidth: 0, color: 'var(--ink-2)' }}>{noticeMsg}</div>
            <button
              onClick={() => setNoticeMsg(null)}
              aria-label={t('export.dismissError', { defaultValue: 'Dismiss' })}
              style={{
                background: 'transparent', border: 'none',
                color: 'var(--ink-3)', cursor: 'pointer',
                padding: 0, lineHeight: 0,
              }}
            >
              <X size={14} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Inline error toast — replaces the prior generic alert() with
          an on-brand, dismissible card carrying the actual reason. */}
      <AnimatePresence mode="wait">
        {errMsg && (
          <motion.div
            key="export-err"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0, transition: { duration: 0.16 } }}
            exit={{ opacity: 0, y: -4, transition: { duration: 0.12 } }}
            role="alert"
            aria-live="polite"
            style={{
              position: 'absolute', top: 'calc(100% + 6px)', right: 0,
              width: 320, padding: '12px 14px', borderRadius: 10,
              background: 'rgba(241, 15, 69, 0.06)',
              border: '1px solid rgba(241, 15, 69, 0.20)',
              boxShadow: 'var(--sh-2)',
              zIndex: 110,
              display: 'flex', alignItems: 'flex-start', gap: 10,
              fontSize: 12.5, color: 'var(--ink)',
              lineHeight: 1.45,
            }}
          >
            <AlertCircle size={15} style={{ color: '#9A1131', flexShrink: 0, marginTop: 1 }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 600, marginBottom: 2 }}>
                {t('export.errTitle', { defaultValue: 'Export failed' })}
              </div>
              <div style={{ color: 'var(--ink-3)' }}>{errMsg}</div>
            </div>
            <button
              onClick={() => setErrMsg(null)}
              aria-label={t('export.dismissError', { defaultValue: 'Dismiss' })}
              style={{
                background: 'transparent', border: 'none',
                color: 'var(--ink-3)', cursor: 'pointer',
                padding: 0, lineHeight: 0,
              }}
            >
              <X size={14} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function MenuItem({
  icon, label, onClick, disabled, busy,
}: { icon: React.ReactNode; label: string; onClick: () => void; disabled: boolean; busy: boolean }) {
  return (
    <button
      role="menuitem"
      onClick={onClick}
      disabled={disabled}
      style={{
        display: 'flex', alignItems: 'center', gap: 10,
        width: '100%', padding: '8px 10px',
        background: 'transparent', border: 'none', borderRadius: 6,
        color: 'var(--ink)', fontSize: 13, fontWeight: 500,
        cursor: disabled ? 'wait' : 'pointer', textAlign: 'left',
      }}
      onMouseEnter={(e) => { (e.target as HTMLElement).style.background = 'var(--surface-2)' }}
      onMouseLeave={(e) => { (e.target as HTMLElement).style.background = 'transparent' }}
    >
      <span style={{ color: 'var(--ink-3)' }}>{icon}</span>
      <span style={{ flex: 1 }}>{label}</span>
      {busy && <span style={{ fontSize: 11, color: 'var(--muted)' }}>…</span>}
    </button>
  )
}
