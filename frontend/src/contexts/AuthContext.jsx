import { createContext, useContext, useState, useEffect } from 'react'
import { authApi } from '../services/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const storedUser = localStorage.getItem('sentinel_user')
    const token = localStorage.getItem('sentinel_token')
    if (storedUser && token) {
      setUser(JSON.parse(storedUser))
    }
    setLoading(false)
  }, [])

  const login = async (username, password) => {
    const { data } = await authApi.login(username, password)
    localStorage.setItem('sentinel_token', data.access_token)
    localStorage.setItem('sentinel_user', JSON.stringify(data))
    setUser(data)
    return data
  }

  const logout = () => {
    localStorage.removeItem('sentinel_token')
    localStorage.removeItem('sentinel_user')
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, login, logout, loading }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
