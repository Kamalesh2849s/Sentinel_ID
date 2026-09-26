import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { Shield, Eye, EyeOff, AlertCircle, Lock } from 'lucide-react'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(username, password)
      navigate('/')
    } catch (err) {
      setError(err.response?.data?.detail || 'Invalid credentials')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-sentinel-bg relative overflow-hidden">
      {/* Animated background grid */}
      <div className="absolute inset-0 opacity-5"
        style={{
          backgroundImage: 'linear-gradient(rgba(0,212,255,0.3) 1px, transparent 1px), linear-gradient(90deg, rgba(0,212,255,0.3) 1px, transparent 1px)',
          backgroundSize: '40px 40px'
        }}
      />

      {/* Glow orbs */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-sentinel-primary/5 rounded-full blur-3xl" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-sentinel-accent/5 rounded-full blur-3xl" />

      <div className="relative z-10 w-full max-w-md px-4">
        {/* Logo & Title */}
        <div className="text-center mb-8 animate-fade-in">
          <div className="flex justify-center mb-4">
            <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-sentinel-primary/20 to-sentinel-accent/20 border border-sentinel-primary/30 flex items-center justify-center"
              style={{ boxShadow: '0 0 30px rgba(0, 212, 255, 0.2)' }}>
              <Shield className="w-10 h-10 text-sentinel-primary" />
            </div>
          </div>
          <h1 className="text-3xl font-bold text-sentinel-gradient">SentinelID</h1>
          <p className="text-sm text-gray-400 mt-1 font-mono tracking-wider uppercase">
            Border Document Screening System
          </p>
          <div className="mt-2 inline-flex items-center gap-1.5 bg-amber-500/10 border border-amber-500/30 rounded px-3 py-1">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
            <span className="text-xs text-amber-400 font-mono">PROTOTYPE — Not for production use</span>
          </div>
        </div>

        {/* Login Card */}
        <div className="glass-card p-8 animate-slide-up">
          <div className="flex items-center gap-2 mb-6">
            <Lock className="w-4 h-4 text-sentinel-primary" />
            <span className="text-sm font-medium text-gray-300">Officer Authentication</span>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-2 uppercase tracking-wider">
                Badge / Username
              </label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="input-field"
                placeholder="officer1"
                required
                autoComplete="username"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-400 mb-2 uppercase tracking-wider">
                Password
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="input-field pr-11"
                  placeholder="••••••••"
                  required
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3">
                <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
                <span className="text-sm text-red-400">{error}</span>
              </div>
            )}

            <button
              id="login-btn"
              type="submit"
              disabled={loading}
              className="btn-primary w-full flex items-center justify-center gap-2 py-3"
            >
              {loading ? (
                <>
                  <div className="w-4 h-4 border-2 border-sentinel-bg/50 border-t-sentinel-bg rounded-full animate-spin" />
                  Authenticating...
                </>
              ) : (
                <>
                  <Shield className="w-4 h-4" />
                  Sign In
                </>
              )}
            </button>
          </form>

          {/* Demo credentials */}
          <div className="mt-6 p-4 bg-sentinel-surface/50 rounded-lg border border-sentinel-border/50">
            <p className="text-xs text-gray-500 font-mono mb-2 uppercase tracking-wider">Demo Credentials</p>
            <div className="space-y-1 text-xs font-mono text-gray-400">
              <div className="flex justify-between">
                <span>officer1</span><span className="text-gray-600">password123</span>
              </div>
              <div className="flex justify-between">
                <span>admin</span><span className="text-gray-600">admin123</span>
              </div>
            </div>
          </div>
        </div>

        <p className="text-center text-xs text-gray-600 mt-4 font-mono">
          SentinelID v1.0.0 — Prototype System
        </p>
      </div>
    </div>
  )
}
