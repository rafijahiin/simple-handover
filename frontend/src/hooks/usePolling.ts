import { useCallback, useEffect, useRef, useState } from 'react'

interface UsePollingOptions<T> {
  fetcher: () => Promise<T>
  interval?: number
  enabled?: boolean
  /**
   * Optional dependency list. Whenever any value here changes, the polling
   * loop restarts and an immediate refetch fires. Use this when the fetcher
   * closes over reactive params (e.g. filters, date ranges) so the data
   * follows the UI selection — without this, the fetcher ref updates but
   * the effect would not re-run.
   */
  deps?: ReadonlyArray<unknown>
}

interface UsePollingResult<T> {
  data: T | null
  loading: boolean
  error: string | null
  refetch: () => void
}

export function usePolling<T>({
  fetcher,
  interval = 30_000,
  enabled = true,
  deps = [],
}: UsePollingOptions<T>): UsePollingResult<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  // Only push new data when it actually differs from the last poll. An
  // unconditional setData re-renders the whole page every interval even when
  // nothing changed, which re-animates charts / count-ups / the activity feed
  // and nudges the scroll position ("the screen auto-scrolls a bit").
  const prevJsonRef = useRef<string>('')
  const fetch = useCallback(async () => {
    try {
      const result = await fetcherRef.current()
      const json = JSON.stringify(result)
      if (json !== prevJsonRef.current) {
        prevJsonRef.current = json
        setData(result)
      }
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!enabled) return
    fetch()
    timerRef.current = setInterval(fetch, interval)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, fetch, interval, ...deps])

  return { data, loading, error, refetch: fetch }
}
