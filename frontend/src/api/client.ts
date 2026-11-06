import axios, { AxiosError } from 'axios'

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp('(^|;\\s*)' + name + '=([^;]+)'))
  return match ? decodeURIComponent(match[2]) : null
}

export const api = axios.create({
  baseURL: '/api',
  withCredentials: true,
  xsrfCookieName: 'csrftoken',
  xsrfHeaderName: 'X-CSRFToken',
})

api.interceptors.request.use((config) => {
  const method = (config.method || 'get').toUpperCase()
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    const token = readCookie('csrftoken')
    if (token) {
      config.headers = config.headers || {}
      ;(config.headers as Record<string, string>)['X-CSRFToken'] = token
    }
  }
  return config
})

/** Pull a human-readable error string out of a DRF error response. */
export function apiErrorMessage(err: unknown, fallback = 'Something went wrong.'): string {
  if (err instanceof AxiosError) {
    const data = err.response?.data
    if (typeof data === 'string') return data
    if (data && typeof data === 'object') {
      if ('detail' in data && typeof data.detail === 'string') return data.detail
      // DRF field errors: { field: ["msg"] }
      const first = Object.values(data)[0]
      if (Array.isArray(first) && typeof first[0] === 'string') return first[0]
      if (typeof first === 'string') return first
    }
    if (err.message) return err.message
  }
  if (err instanceof Error) return err.message
  return fallback
}

/** Call once on app boot to get the CSRF cookie. */
export async function ensureCSRF(): Promise<void> {
  try {
    await api.get('/accounts/csrf/')
  } catch {
    // non-fatal; subsequent unsafe requests will retry
  }
}
