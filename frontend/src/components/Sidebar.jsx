import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import {
  Shield, LayoutDashboard, Plus, History,
  LogOut, Activity, ChevronRight, Menu, X
} from 'lucide-react'
import { useState } from 'react'

const navItems = [
  { label: 'Dashboard', icon: LayoutDashboard, path: '/' },
  { label: 'New Screening', icon: Plus, path: '/new-screening' },
  { label: 'Screening History', icon: History, path: '/history' },
]

export default function Sidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuth()
  const [collapsed, setCollapsed] = useState(false)

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <aside className={`flex flex-col h-screen bg-sentinel-surface border-r border-sentinel-border transition-all duration-300 ${collapsed ? 'w-16' : 'w-64'}`}>
      {/* Logo */}
      <div className="flex items-center justify-between p-4 border-b border-sentinel-border">
        {!collapsed && (
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-sentinel-primary/30 to-sentinel-accent/30 border border-sentinel-primary/30 flex items-center justify-center">
              <Shield className="w-4 h-4 text-sentinel-primary" />
            </div>
            <div>
              <span className="font-bold text-sentinel-primary text-sm">SentinelID</span>
              <p className="text-xs text-gray-500 leading-none">v1.0 Prototype</p>
            </div>
          </div>
        )}
        {collapsed && (
          <Shield className="w-6 h-6 text-sentinel-primary mx-auto" />
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="text-gray-400 hover:text-gray-200 p-1 rounded ml-auto"
        >
          {collapsed ? <Menu className="w-4 h-4" /> : <X className="w-4 h-4" />}
        </button>
      </div>

      {/* System status */}
      {!collapsed && (
        <div className="px-4 py-2 border-b border-sentinel-border">
          <div className="flex items-center gap-2">
            <Activity className="w-3 h-3 text-emerald-400" />
            <span className="text-xs text-emerald-400 font-mono">SYSTEM ACTIVE</span>
          </div>
        </div>
      )}

      {/* Nav */}
      <nav className="flex-1 py-4 px-2 space-y-1">
        {navItems.map((item) => {
          const Icon = item.icon
          const isActive = location.pathname === item.path ||
            (item.path !== '/' && location.pathname.startsWith(item.path))
          return (
            <button
              key={item.path}
              onClick={() => navigate(item.path)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 group
                ${isActive
                  ? 'bg-sentinel-primary/10 border border-sentinel-primary/20 text-sentinel-primary'
                  : 'text-gray-400 hover:bg-sentinel-card hover:text-gray-200'
                }`}
            >
              <Icon className={`w-5 h-5 flex-shrink-0 ${isActive ? 'text-sentinel-primary' : ''}`} />
              {!collapsed && (
                <>
                  <span className="text-sm font-medium">{item.label}</span>
                  {isActive && <ChevronRight className="w-3 h-3 ml-auto" />}
                </>
              )}
            </button>
          )
        })}
      </nav>

      {/* User info */}
      <div className="border-t border-sentinel-border p-4">
        {!collapsed && user && (
          <div className="mb-3">
            <p className="text-xs text-gray-400 truncate">{user.full_name || user.username}</p>
            <p className="text-xs text-sentinel-primary font-mono uppercase">{user.role}</p>
          </div>
        )}
        <button
          onClick={handleLogout}
          className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-gray-400 hover:text-red-400 hover:bg-red-500/10 transition-all duration-200 ${collapsed ? 'justify-center' : ''}`}
        >
          <LogOut className="w-4 h-4 flex-shrink-0" />
          {!collapsed && <span className="text-sm">Sign Out</span>}
        </button>
      </div>
    </aside>
  )
}
