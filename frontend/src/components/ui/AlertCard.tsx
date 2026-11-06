import { AlertTriangle, TrendingDown, X } from 'lucide-react'
import { cn } from '@/utils/cn'
import type { Alert } from '@/types'

interface Props {
  alert: Alert
  onAcknowledge?: (id: string) => void
  className?: string
}

const severityConfig = {
  info: {
    border: 'border-blue-400',
    bg: 'bg-blue-50 dark:bg-blue-900/20',
    icon: 'text-blue-500',
    badge: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  },
  warning: {
    border: 'border-amber-400',
    bg: 'bg-amber-50 dark:bg-amber-900/20',
    icon: 'text-amber-500',
    badge: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  },
  critical: {
    border: 'border-red-500',
    bg: 'bg-red-50 dark:bg-red-900/20',
    icon: 'text-red-500',
    badge: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  },
}

export function AlertCard({ alert, onAcknowledge, className }: Props) {
  const cfg = severityConfig[alert.severity] ?? severityConfig.info

  return (
    <div
      className={cn(
        'flex gap-3 rounded-xl border-l-4 p-4 shadow-sm',
        cfg.border,
        cfg.bg,
        className
      )}
    >
      <AlertTriangle className={cn('mt-0.5 h-5 w-5 flex-shrink-0', cfg.icon)} />
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-semibold text-gray-900 dark:text-white text-sm">{alert.title}</p>
            <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide', cfg.badge)}>
              {alert.severity_display}
            </span>
          </div>
          {onAcknowledge && !alert.acknowledged && (
            <button
              onClick={() => onAcknowledge(alert.id)}
              className="flex-shrink-0 rounded-full p-1 hover:bg-black/5 dark:hover:bg-white/10"
              title="Acknowledge"
            >
              <X className="h-4 w-4 text-gray-500 dark:text-gray-400" />
            </button>
          )}
        </div>
        <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">{alert.message}</p>
        <div className="mt-2 flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
          <span className="flex items-center gap-1">
            <TrendingDown className="h-3 w-3" />
            {alert.alert_type_display}
          </span>
          <span>Partner: <strong>{alert.partner}</strong></span>
        </div>
      </div>
    </div>
  )
}
