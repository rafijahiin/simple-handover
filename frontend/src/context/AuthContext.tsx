import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, apiErrorMessage, ensureCSRF } from '@/api/client'
import type { User } from '@/types'

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  login: async () => {},
  logout: async () => {},
  refresh: async () => {},
})

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const res = await api.get<User>('/accounts/me/')
      setUser(res.data)
    } catch {
      setUser(null)
    }
  }, [])

  useEffect(() => {
    ensureCSRF().then(() => refresh().finally(() => setLoading(false)))
  }, [refresh])

  const login = async (username: string, password: string) => {
    await ensureCSRF()
    const res = await api.post<{ user?: User }>(
      '/accounts/login/',
      { email: username, password }
    )
    if (res.data.user) setUser(res.data.user)
    else await refresh()
  }

  const logout = async () => {
    try {
      await api.post('/accounts/logout/')
    } finally {
      setUser(null)
    }
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}

export { apiErrorMessage }
