import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  History, Search, Filter, ArrowRight,
  ChevronLeft, ChevronRight, RefreshCw, Shield
} from 'lucide-react'
import { screeningsApi } from '../services/api'
import { StatusBadge, RiskGauge, Spinner, EmptyState } from '../components/UIComponents'

const STATUSES = ['ALL', 'VERIFIED', 'SUSPICIOUS', 'HIGH_RISK', 'PENDING', 'FAILED']
const DOC_TYPES = ['ALL', 'passport', 'visa', 'national_id', 'permit', 'travel_authorization']
const RISK_LEVELS = ['ALL', 'low', 'medium', 'high']

export default function HistoryPage() {
  const navigate = useNavigate()
  const [screenings, setScreenings] = useState([])
  const [loading, setLoading] = useState(true)
  const [filters, setFilters] = useState({
    status: 'ALL',
    document_type: 'ALL',
    risk_level: 'ALL',
  })
  const [page, setPage] = useState(0)
  const limit = 20

  const fetchScreenings = async () => {
    setLoading(true)
    try {
      const params = {
        limit,
        offset: page * limit,
      }
      if (filters.status !== 'ALL') params.status = filters.status
      if (filters.document_type !== 'ALL') params.document_type = filters.document_type
      if (filters.risk_level !== 'ALL') params.risk_level = filters.risk_level

      const { data } = await screeningsApi.list(params)
      setScreenings(data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchScreenings()
  }, [filters, page])

  const handleFilterChange = (key, value) => {
    setFilters(prev => ({ ...prev, [key]: value }))
    setPage(0)
  }

  return (
    <div className="p-6 space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-100">Screening History</h1>
          <p className="text-sm text-gray-500 mt-0.5">All document screenings and audit records</p>
        </div>
        <button
          onClick={fetchScreenings}
          className="btn-secondary flex items-center gap-2"
          disabled={loading}
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="glass-card p-4">
        <div className="flex items-center gap-2 mb-3">
          <Filter className="w-4 h-4 text-sentinel-primary" />
          <span className="text-sm font-medium text-gray-300">Filters</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Status filter */}
          <div>
            <label className="text-xs text-gray-500 uppercase tracking-wider mb-1.5 block">Status</label>
            <div className="flex flex-wrap gap-1">
              {STATUSES.map((s) => (
                <button
                  key={s}
                  onClick={() => handleFilterChange('status', s)}
                  className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                    filters.status === s
                      ? 'bg-sentinel-primary/20 border border-sentinel-primary/30 text-sentinel-primary'
                      : 'bg-sentinel-surface border border-sentinel-border text-gray-500 hover:text-gray-300'
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {/* Document type filter */}
          <div>
            <label className="text-xs text-gray-500 uppercase tracking-wider mb-1.5 block">Document Type</label>
            <div className="flex flex-wrap gap-1">
              {DOC_TYPES.map((t) => (
                <button
                  key={t}
                  onClick={() => handleFilterChange('document_type', t)}
                  className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                    filters.document_type === t
                      ? 'bg-sentinel-primary/20 border border-sentinel-primary/30 text-sentinel-primary'
                      : 'bg-sentinel-surface border border-sentinel-border text-gray-500 hover:text-gray-300'
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          {/* Risk level filter */}
          <div>
            <label className="text-xs text-gray-500 uppercase tracking-wider mb-1.5 block">Risk Level</label>
            <div className="flex flex-wrap gap-1">
              {RISK_LEVELS.map((r) => (
                <button
                  key={r}
                  onClick={() => handleFilterChange('risk_level', r)}
                  className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                    filters.risk_level === r
                      ? 'bg-sentinel-primary/20 border border-sentinel-primary/30 text-sentinel-primary'
                      : 'bg-sentinel-surface border border-sentinel-border text-gray-500 hover:text-gray-300'
                  }`}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="glass-card overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Spinner size="lg" />
          </div>
        ) : screenings.length === 0 ? (
          <EmptyState
            icon={History}
            title="No screenings found"
            message="No screenings match your current filters, or no screenings have been created yet."
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-sentinel-border bg-sentinel-surface/50">
                    <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-4 py-3">#</th>
                    <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-4 py-3">Document Type</th>
                    <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-4 py-3">Status</th>
                    <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-4 py-3">Risk Score</th>
                    <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-4 py-3">Processing Time</th>
                    <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-4 py-3">Date</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-sentinel-border/30">
                  {screenings.map((s) => (
                    <tr
                      key={s.id}
                      onClick={() => navigate(`/screening/${s.id}`)}
                      className="hover:bg-sentinel-surface/50 cursor-pointer transition-colors group"
                    >
                      <td className="px-4 py-3">
                        <span className="text-sm font-mono text-gray-500">#{s.id}</span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <Shield className="w-3.5 h-3.5 text-gray-600" />
                          <span className="text-sm text-gray-300 capitalize">{s.document_type?.replace('_', ' ')}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={s.status} />
                      </td>
                      <td className="px-4 py-3">
                        <RiskGauge score={s.risk_score} />
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-sm font-mono text-gray-500">
                          {s.processing_time_ms
                            ? `${(s.processing_time_ms / 1000).toFixed(1)}s`
                            : '—'}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-sm text-gray-500">
                          {new Date(s.created_at).toLocaleDateString()}
                        </span>
                        <br />
                        <span className="text-xs text-gray-600">
                          {new Date(s.created_at).toLocaleTimeString()}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <ArrowRight className="w-4 h-4 text-gray-600 group-hover:text-sentinel-primary transition-colors" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between px-4 py-3 border-t border-sentinel-border/30">
              <span className="text-xs text-gray-500 font-mono">
                Showing {page * limit + 1}–{page * limit + screenings.length}
              </span>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage(p => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="btn-secondary px-2 py-1 text-xs disabled:opacity-50"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setPage(p => p + 1)}
                  disabled={screenings.length < limit}
                  className="btn-secondary px-2 py-1 text-xs disabled:opacity-50"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
