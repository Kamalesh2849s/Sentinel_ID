import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Shield, FileCheck, AlertTriangle, XCircle,
  Clock, TrendingUp, Activity, ArrowRight,
  Scan, Database, BarChart3
} from 'lucide-react'
import { dashboardApi } from '../services/api'
import { StatusBadge, RiskGauge, Spinner, EmptyState } from '../components/UIComponents'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'

function StatCard({ title, value, icon: Icon, color, subtitle, trend }) {
  const colorMap = {
    cyan: 'text-sentinel-primary border-sentinel-primary/20 bg-sentinel-primary/5',
    green: 'text-emerald-400 border-emerald-500/20 bg-emerald-500/5',
    amber: 'text-amber-400 border-amber-500/20 bg-amber-500/5',
    red: 'text-red-400 border-red-500/20 bg-red-500/5',
    purple: 'text-purple-400 border-purple-500/20 bg-purple-500/5',
  }

  return (
    <div className={`glass-card p-6 border ${colorMap[color]}`}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-gray-400 uppercase tracking-wider font-mono">{title}</p>
          <p className={`text-3xl font-bold mt-1 ${colorMap[color].split(' ')[0]}`}>{value ?? '—'}</p>
          {subtitle && <p className="text-xs text-gray-500 mt-1">{subtitle}</p>}
        </div>
        <div className={`p-3 rounded-xl ${colorMap[color].split(' ')[2]} border ${colorMap[color].split(' ')[1]}`}>
          <Icon className={`w-6 h-6 ${colorMap[color].split(' ')[0]}`} />
        </div>
      </div>
    </div>
  )
}

const STATUS_COLORS = {
  VERIFIED: '#10b981',
  SUSPICIOUS: '#f59e0b',
  HIGH_RISK: '#ef4444',
  FAILED: '#6b7280',
  PENDING: '#3b82f6',
}

export default function DashboardPage() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  const fetchStats = async () => {
    try {
      const { data } = await dashboardApi.getStats()
      setStats(data)
    } catch (err) {
      setError('Failed to load dashboard data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStats()
    const interval = setInterval(fetchStats, 30000) // Refresh every 30s
    return () => clearInterval(interval)
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <Spinner size="lg" className="mx-auto mb-4" />
          <p className="text-gray-400 font-mono">Loading dashboard...</p>
        </div>
      </div>
    )
  }

  const pieData = stats?.status_distribution
    ? Object.entries(stats.status_distribution)
        .filter(([, v]) => v > 0)
        .map(([k, v]) => ({ name: k, value: v }))
    : []

  const avgTime = stats?.average_processing_time_ms
    ? `${(stats.average_processing_time_ms / 1000).toFixed(1)}s`
    : '—'

  return (
    <div className="p-6 space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-100">Command Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5 font-mono">Real-time border screening overview</p>
        </div>
        <button
          onClick={() => navigate('/new-screening')}
          className="btn-primary flex items-center gap-2"
        >
          <Scan className="w-4 h-4" />
          New Screening
        </button>
      </div>

      {/* Prototype disclaimer */}
      <div className="flex items-center gap-3 bg-amber-500/5 border border-amber-500/20 rounded-xl px-4 py-3">
        <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
        <p className="text-xs text-amber-400/80">
          <strong>PROTOTYPE SYSTEM:</strong> All data shown is simulated. Local prototype database only.
          Not connected to any real government or law enforcement database.
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Total Screenings"
          value={stats?.total_screenings ?? 0}
          icon={Database}
          color="cyan"
          subtitle="All time"
        />
        <StatCard
          title="Verified"
          value={stats?.verified ?? 0}
          icon={FileCheck}
          color="green"
          subtitle="Low risk cleared"
        />
        <StatCard
          title="Suspicious"
          value={stats?.suspicious ?? 0}
          icon={AlertTriangle}
          color="amber"
          subtitle="Require review"
        />
        <StatCard
          title="High Risk"
          value={stats?.high_risk ?? 0}
          icon={XCircle}
          color="red"
          subtitle="Immediate review"
        />
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Pending / Processing"
          value={stats?.pending ?? 0}
          icon={Clock}
          color="purple"
        />
        <StatCard
          title="Avg Processing Time"
          value={avgTime}
          icon={TrendingUp}
          color="cyan"
        />
        <StatCard
          title="Failed"
          value={stats?.failed ?? 0}
          icon={XCircle}
          color="amber"
        />
        <StatCard
          title="System Status"
          value="ONLINE"
          icon={Activity}
          color="green"
          subtitle="All systems operational"
        />
      </div>

      {/* Charts + Recent */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Status distribution pie */}
        <div className="glass-card p-6">
          <h2 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-sentinel-primary" />
            Status Distribution
          </h2>
          {pieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={80}
                  paddingAngle={3}
                  dataKey="value"
                >
                  {pieData.map((entry) => (
                    <Cell
                      key={entry.name}
                      fill={STATUS_COLORS[entry.name] || '#6b7280'}
                    />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    background: '#111827',
                    border: '1px solid #1e2d45',
                    borderRadius: '8px',
                    color: '#e5e7eb',
                    fontSize: '12px',
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-48 flex items-center justify-center text-gray-600 text-sm">
              No data yet
            </div>
          )}
          {/* Legend */}
          <div className="grid grid-cols-2 gap-1 mt-2">
            {Object.entries(STATUS_COLORS).map(([k, c]) => (
              <div key={k} className="flex items-center gap-1.5">
                <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: c }} />
                <span className="text-xs text-gray-500">{k.replace('_', ' ')}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Recent Screenings */}
        <div className="lg:col-span-2 glass-card p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
              <Activity className="w-4 h-4 text-sentinel-primary" />
              Recent Screenings
            </h2>
            <button
              onClick={() => navigate('/history')}
              className="text-xs text-sentinel-primary hover:text-sentinel-primary-dark flex items-center gap-1"
            >
              View all <ArrowRight className="w-3 h-3" />
            </button>
          </div>

          {stats?.recent_screenings?.length > 0 ? (
            <div className="space-y-2">
              {stats.recent_screenings.slice(0, 8).map((s) => (
                <div
                  key={s.id}
                  onClick={() => navigate(`/screening/${s.id}`)}
                  className="flex items-center gap-3 p-3 rounded-lg bg-sentinel-surface/50 hover:bg-sentinel-surface cursor-pointer transition-colors border border-transparent hover:border-sentinel-border group"
                >
                  <div className="w-8 h-8 rounded-lg bg-sentinel-bg flex items-center justify-center border border-sentinel-border flex-shrink-0">
                    <Shield className="w-4 h-4 text-gray-500" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-gray-300 font-mono truncate">
                        #{s.id} — {s.document_type}
                      </span>
                    </div>
                    <p className="text-xs text-gray-500">
                      {new Date(s.created_at).toLocaleString()}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <RiskGauge score={s.risk_score} />
                    <StatusBadge status={s.status} />
                    <ArrowRight className="w-4 h-4 text-gray-600 group-hover:text-gray-400 transition-colors" />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              icon={Shield}
              title="No screenings yet"
              message="Start your first document screening to see results here."
            />
          )}
        </div>
      </div>
    </div>
  )
}
