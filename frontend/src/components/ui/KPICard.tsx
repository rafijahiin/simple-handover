import { TrendingDown, TrendingUp } from 'lucide-react'
import { cn } from '@/utils/cn'
import { Sparkline } from './Sparkline'

interface Props {
  label: string
  labelBn?: string
  value: number | string
  unit?: string
  trend?: number          // % change; positive = up, negative = down
  sparkData?: number[]
  icon?: React.ReactNode
  highlight?: boolean
  className?: string
}

export function KPICard({
  label,
  labelBn,
  value,
  unit,
  trend,
  sparkData,
  icon,
  highlight,
  className,
}: Props) {
  const trendUp = trend !== undefined && trend >= 0
  const trendColor = trendUp ? 'text-status-on_track' : 'text-status-critical'

  return (
    <div
      className={cn(
        'relative flex flex-col gap-3 rounded-xl p-5 shadow-sm border',
        highlight
          ? 'bg-unfpa-blue text-white border-unfpa-dark'
          : 'bg-white dark:bg-gray-800 border-gray-100 dark:border-gray-700',
        className
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          {labelBn && (
            <p className={cn('font-bangla text-xs mb-0.5', highlight ? 'text-blue-100' : 'text-gray-400 dark:text-gray-500')}>
              {labelBn}
            </p>
          )}
          <p className={cn('text-sm font-medium', highlight ? 'text-blue-100' : 'text-gray-500 dark:text-gray-400')}>
            {label}
          </p>
        </div>
        {icon && (
          <span className={cn('text-xl', highlight ? 'text-blue-200' : 'text-unfpa-blue')}>
            {icon}
          </span>
        )}
      </div>

      <div className="flex items-end justify-between gap-2">
        <div>
          <span className={cn('text-3xl font-bold leading-none', highlight ? 'text-white' : 'text-gray-900 dark:text-white')}>
            {typeof value === 'number' ? value.toLocaleString() : value}
          </span>
          {unit && (
            <span className={cn('ml-1 text-sm', highlight ? 'text-blue-200' : 'text-gray-400 dark:text-gray-500')}>
              {unit}
            </span>
          )}
        </div>
        {sparkData && sparkData.length >= 2 && (
          <Sparkline
            data={sparkData}
            color={highlight ? '#93c5fd' : '#2171EC'}
            width={72}
            height={28}
          />
        )}
      </div>

      {trend !== undefined && (
        <div className={cn('flex items-center gap-1 text-xs font-medium', highlight ? 'text-blue-200' : trendColor)}>
          {trendUp ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
          <span>{Math.abs(trend).toFixed(1)}% vs last month</span>
        </div>
      )}
    </div>
  )
}
