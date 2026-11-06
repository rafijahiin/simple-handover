import { cn } from '@/utils/cn'

interface Props {
  value: number      // actual value
  target: number     // target value
  size?: number      // diameter px
  strokeWidth?: number
  label?: string
  sublabel?: string
  className?: string
}

export function ProgressRing({
  value,
  target,
  size = 120,
  strokeWidth = 10,
  label,
  sublabel,
  className,
}: Props) {
  const pct = target > 0 ? Math.min(value / target, 1) : 0
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference * (1 - pct)

  const color =
    pct >= 0.9 ? '#16a34a' : pct >= 0.6 ? '#d97706' : '#dc2626'

  return (
    <div
      className={cn('relative inline-flex flex-col items-center justify-center', className)}
      style={{ width: size, height: size }}
    >
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="-rotate-90"
      >
        {/* Track */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={strokeWidth}
          className="text-gray-200 dark:text-gray-700"
        />
        {/* Progress */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 0.6s ease' }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-xl font-bold text-gray-900 dark:text-white leading-none">
          {Math.round(pct * 100)}%
        </span>
        {label && (
          <span className="mt-0.5 text-xs font-medium text-gray-600 dark:text-gray-400 text-center px-2 leading-tight">
            {label}
          </span>
        )}
        {sublabel && (
          <span className="text-[10px] text-gray-400 dark:text-gray-500 text-center px-2 leading-tight">
            {sublabel}
          </span>
        )}
      </div>
    </div>
  )
}
