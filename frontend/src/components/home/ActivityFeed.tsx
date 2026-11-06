/**
 * ActivityFeed — live heartbeat of submissions arriving across all partners.
 *
 * Animesh's spec: 'PHD field worker submitted from Sylhet, 2 minutes ago' —
 * gives the system a live feel and proves it's wired to real activity.
 *
 * Polls /api/dashboard/activity/?limit=10 every 30s. New items slide in
 * from the top with a brief highlight pulse so the eye catches what just
 * happened.
 *
 * UNFPA-only surface: hidden from focal/manager/field_staff so partner
 * managers don't see the cross-partner picture.
 */
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { motion, AnimatePresence, useReducedMotion } from 'motion/react'
import { Radio, MapPin } from 'lucide-react'
import { api } from '@/api/client'
import { useAuth } from '@/context/AuthContext'

interface FeedItem {
  id: string
  form_type: string
  form_type_display: string
  partner: string
  worker_name: string
  district: string
  submitted_at: string
  time_ago: string
}

// UNFPA branding — all partners share the brand orange. Partner identity
// is communicated by the bold code text next to each row, not by colour.
const PARTNER_COLOR: Record<string, string> = {
  PHD: '#F96000',
  BANDHU: '#F96000',
  CIPRB: '#F96000',
}

export function ActivityFeed() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const [items, setItems] = useState<FeedItem[] | null>(null)
  const reduce = useReducedMotion()
  const seenIds = useRef<Set<string>>(new Set())

  useEffect(() => {
    if (!user || !['supervisor', 'developer'].includes(user.role)) return
    let cancelled = false
    const fetch = () =>
      api
        .get<FeedItem[] | { results: FeedItem[] }>('/dashboard/activity/?limit=10')
        .then(r => {
          if (cancelled) return
          const rows = Array.isArray(r.data) ? r.data : r.data.results ?? []
          setItems(rows)
        })
        .catch(() => { /* leave previous state intact */ })
    fetch()
    const id = setInterval(fetch, 30_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [user])

  if (!user || !['supervisor', 'developer'].includes(user.role)) return null
  if (!items || items.length === 0) return null

  return (
    <section className="section" style={{ marginTop: 36 }}>
      <div className="kicker" style={{ marginBottom: 8 }}>
        <span className="live-dot" />
        {t('feed.kicker', { defaultValue: 'LIVE ACTIVITY · ARRIVING NOW' })}
      </div>
      <h2 className="section-title" style={{ marginBottom: 4 }}>
        {t('feed.title', { defaultValue: 'Field heartbeat' })}
      </h2>
      <p className="section-sub" style={{ marginBottom: 16 }}>
        {t('feed.sub', { defaultValue: 'Most recent submissions across all partners — updates every 30 seconds.' })}
      </p>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
          <AnimatePresence initial={false}>
            {items.map((it) => {
              const isNew = !seenIds.current.has(it.id)
              seenIds.current.add(it.id)
              return (
                <motion.li
                  key={it.id}
                  layout
                  initial={isNew ? { opacity: 0, y: reduce ? 0 : -8, backgroundColor: 'rgba(249,96,0,0.10)' } : false}
                  animate={{ opacity: 1, y: 0, backgroundColor: 'rgba(249,96,0,0)' }}
                  transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1], backgroundColor: { duration: 1.6 } }}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'auto 1fr auto',
                    alignItems: 'center', gap: 14,
                    padding: '12px 16px',
                    borderBottom: '1px solid var(--hair)',
                  }}
                >
                  <span style={{
                    width: 8, height: 8, borderRadius: 999,
                    background: PARTNER_COLOR[it.partner] ?? 'var(--muted)',
                    flexShrink: 0,
                  }} />
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 13, color: 'var(--ink)', fontWeight: 500 }}>
                      <b style={{ color: PARTNER_COLOR[it.partner] ?? 'var(--ink)' }}>
                        {it.partner}
                      </b>
                      {' · '}
                      <span style={{ color: 'var(--ink-2)' }}>{it.form_type_display}</span>
                      {it.worker_name && (
                        <span style={{ color: 'var(--muted)' }}> · {it.worker_name}</span>
                      )}
                    </div>
                    {it.district && (
                      <div style={{
                        fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2,
                        display: 'inline-flex', alignItems: 'center', gap: 4,
                      }}>
                        <MapPin size={11} style={{ color: 'var(--muted)' }} />
                        {it.district}
                      </div>
                    )}
                  </div>
                  <span style={{
                    fontSize: 11, color: 'var(--muted)',
                    fontVariantNumeric: 'tabular-nums', flexShrink: 0,
                  }}>
                    <Radio size={10} style={{ marginRight: 4, verticalAlign: -1 }} />
                    {it.time_ago}
                  </span>
                </motion.li>
              )
            })}
          </AnimatePresence>
        </ul>
      </div>
    </section>
  )
}
