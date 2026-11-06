// All programme timestamps are stored UTC (USE_TZ=True) and the programme runs
// in Bangladesh, so every date renders in Asia/Dhaka regardless of the
// reviewer's own browser timezone. Without this pin a reviewer outside Dhaka
// sees their local clock — and dates flip by a day for the hours around
// midnight UTC. (Fault F2.)
const DHAKA_TZ = 'Asia/Dhaka'

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: DHAKA_TZ })
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: DHAKA_TZ,
  })
}

export function formatNumber(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  return n.toLocaleString('en-US')
}

export function formatPercent(n: number | null | undefined, digits = 1): string {
  if (n === null || n === undefined) return '—'
  return `${n.toFixed(digits)}%`
}

export const MONTH_NAMES = [
  '', 'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

export function monthLabel(year: number, month: number): string {
  return `${MONTH_NAMES[month]} ${year}`
}
