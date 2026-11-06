interface Props {
  data: number[]
  width?: number
  height?: number
  color?: string
  className?: string
}

export function Sparkline({ data, width = 80, height = 28, color = '#2171EC', className }: Props) {
  if (!data || data.length < 2) {
    return <span className={className} style={{ width, height, display: 'inline-block' }} />
  }

  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1

  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * width
    const y = height - ((v - min) / range) * (height - 4) - 2
    return `${x},${y}`
  })

  const pathD = `M${points.join(' L')}`

  const lastY = parseFloat(points[points.length - 1].split(',')[1])
  const trend = data[data.length - 1] >= data[data.length - 2]
  const dotColor = trend ? '#16a34a' : '#dc2626'

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      aria-hidden
    >
      <path d={pathD} fill="none" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" opacity={0.7} />
      <circle
        cx={parseFloat(points[points.length - 1].split(',')[0])}
        cy={lastY}
        r={2.5}
        fill={dotColor}
      />
    </svg>
  )
}
