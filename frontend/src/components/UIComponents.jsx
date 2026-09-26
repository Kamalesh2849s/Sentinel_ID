/**
 * Status badge component for screening status display.
 */
export function StatusBadge({ status, className = '' }) {
  const map = {
    VERIFIED: { cls: 'badge-verified', label: 'Verified' },
    SUSPICIOUS: { cls: 'badge-suspicious', label: 'Suspicious' },
    HIGH_RISK: { cls: 'badge-high-risk', label: 'High Risk' },
    PENDING: { cls: 'badge-pending', label: 'Pending' },
    PROCESSING: { cls: 'badge-pending', label: 'Processing' },
    FAILED: { cls: 'badge-failed', label: 'Failed' },
  }
  const cfg = map[status] || map.FAILED
  return <span className={`${cfg.cls} ${className}`}>{cfg.label}</span>
}

/**
 * Severity badge for risk reasons.
 */
export function SeverityBadge({ severity }) {
  const map = {
    HIGH: 'severity-high',
    MEDIUM: 'severity-medium',
    LOW: 'severity-low',
  }
  return <span className={map[severity] || 'severity-low'}>{severity}</span>
}

/**
 * Risk score gauge / meter.
 */
export function RiskGauge({ score, size = 'md' }) {
  if (score === null || score === undefined || isNaN(score)) {
    const radius = size === 'lg' ? 54 : 40
    const strokeWidth = size === 'lg' ? 8 : 6
    const svgSize = (radius + strokeWidth) * 2 + 4
    const center = svgSize / 2
    return (
      <div className="flex flex-col items-center gap-1">
        <div className="relative">
          <svg width={svgSize} height={svgSize} className="-rotate-90">
            <circle
              cx={center}
              cy={center}
              r={radius}
              fill="none"
              stroke="rgba(255,255,255,0.1)"
              strokeWidth={strokeWidth}
              strokeDasharray="4 4"
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <span
              className={`font-bold font-mono text-gray-500 ${size === 'lg' ? 'text-2xl' : 'text-lg'}`}
            >
              --
            </span>
          </div>
        </div>
        <span className="text-xs text-gray-500 font-mono">RISK SCORE</span>
      </div>
    )
  }

  const normalized = Math.min(Math.max(score, 0), 100)
  const color =
    normalized <= 35
      ? '#10b981'
      : normalized <= 65
      ? '#f59e0b'
      : '#ef4444'

  const radius = size === 'lg' ? 54 : 40
  const strokeWidth = size === 'lg' ? 8 : 6
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (normalized / 100) * circumference

  const svgSize = (radius + strokeWidth) * 2 + 4
  const center = svgSize / 2

  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative">
        <svg width={svgSize} height={svgSize} className="-rotate-90">
          {/* Track */}
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke="rgba(255,255,255,0.05)"
            strokeWidth={strokeWidth}
          />
          {/* Progress */}
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            style={{
              filter: `drop-shadow(0 0 6px ${color}80)`,
              transition: 'stroke-dashoffset 1s ease-out',
            }}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span
            className={`font-bold font-mono ${size === 'lg' ? 'text-2xl' : 'text-lg'}`}
            style={{ color }}
          >
            {Math.round(normalized)}
          </span>
        </div>
      </div>
      <span className="text-xs text-gray-500 font-mono">RISK SCORE</span>
    </div>
  )
}

/**
 * Stage progress indicator for the screening pipeline.
 */
export function StageIndicator({ stage, status, description }) {
  const statusConfig = {
    pending: {
      cls: 'stage-pending',
      dot: 'bg-gray-600',
      text: 'text-gray-500',
      icon: '○',
    },
    processing: {
      cls: 'stage-processing',
      dot: 'bg-blue-400 animate-pulse',
      text: 'text-blue-400',
      icon: '◉',
    },
    completed: {
      cls: 'stage-completed',
      dot: 'bg-emerald-400',
      text: 'text-emerald-400',
      icon: '✓',
    },
    failed: {
      cls: 'stage-failed',
      dot: 'bg-red-400',
      text: 'text-red-400',
      icon: '✗',
    },
    skipped: {
      cls: 'stage-pending',
      dot: 'bg-gray-600',
      text: 'text-gray-500',
      icon: '—',
    },
  }

  const cfg = statusConfig[status] || statusConfig.pending

  return (
    <div className={cfg.cls}>
      <div className={`w-7 h-7 rounded-full ${cfg.dot} flex items-center justify-center flex-shrink-0`}>
        <span className={`text-xs font-bold ${cfg.text}`}>{cfg.icon}</span>
      </div>
      <div className="flex-1 min-w-0">
        <p className={`text-sm font-medium ${status === 'pending' ? 'text-gray-500' : 'text-gray-200'}`}>
          {stage}
        </p>
        {description && (
          <p className={`text-xs mt-0.5 ${cfg.text}`}>{description}</p>
        )}
      </div>
    </div>
  )
}

/**
 * Validation check row.
 */
export function ValidationRow({ check }) {
  const statusColors = {
    PASS: 'text-emerald-400',
    FAIL: 'text-red-400',
    WARNING: 'text-amber-400',
    SKIPPED: 'text-gray-500',
  }
  const statusIcons = { PASS: '✓', FAIL: '✗', WARNING: '⚠', SKIPPED: '—' }

  return (
    <div className="flex items-start gap-3 py-2 border-b border-sentinel-border/30 last:border-0">
      <span className={`text-sm font-mono flex-shrink-0 ${statusColors[check.status]}`}>
        {statusIcons[check.status]}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm text-gray-300">{check.check_name}</span>
          <SeverityBadge severity={check.severity} />
        </div>
        <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">{check.message}</p>
      </div>
    </div>
  )
}

/**
 * Risk reason card.
 */
export function RiskReasonCard({ reason }) {
  const signalName = reason.signal || (reason.category ? `[${reason.category}]` : 'Signal')
  const resultStatus = reason.result || (reason.severity === 'HIGH' ? 'FAIL' : reason.severity === 'MEDIUM' ? 'WARNING' : 'PASS')
  const impactScore = reason.impact !== undefined ? reason.impact : reason.contribution

  return (
    <div className={`p-3.5 rounded-lg border ${
      resultStatus === 'FAIL' || reason.severity === 'HIGH'
        ? 'bg-red-500/5 border-red-500/20'
        : resultStatus === 'WARNING' || reason.severity === 'MEDIUM'
        ? 'bg-amber-500/5 border-amber-500/20'
        : 'bg-emerald-500/5 border-emerald-500/20'
    }`}>
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <span className={`text-xs font-mono font-bold ${
            resultStatus === 'FAIL' || reason.severity === 'HIGH' ? 'text-red-400'
            : resultStatus === 'WARNING' || reason.severity === 'MEDIUM' ? 'text-amber-400'
            : 'text-emerald-400'
          }`}>
            {signalName}
          </span>
          <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border uppercase font-bold ${
            resultStatus === 'PASS'
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
              : resultStatus === 'WARNING'
              ? 'bg-amber-500/10 border-amber-500/30 text-amber-400'
              : 'bg-red-500/10 border-red-500/30 text-red-400'
          }`}>
            {resultStatus}
          </span>
        </div>
        {impactScore > 0 ? (
          <span className="text-[11px] font-mono text-red-400 font-semibold">
            +{impactScore} pts risk
          </span>
        ) : (
          <span className="text-[11px] font-mono text-emerald-400/80">
            0 pts impact
          </span>
        )}
      </div>
      <p className="text-xs text-gray-300 leading-relaxed">{reason.message}</p>
    </div>
  )
}

/**
 * Loading spinner
 */
export function Spinner({ size = 'md', className = '' }) {
  const sizeMap = { sm: 'w-4 h-4', md: 'w-6 h-6', lg: 'w-8 h-8' }
  return (
    <div className={`${sizeMap[size]} border-2 border-sentinel-border border-t-sentinel-primary rounded-full animate-spin ${className}`} />
  )
}

/**
 * Empty state component
 */
export function EmptyState({ icon: Icon, title, message }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      {Icon && <Icon className="w-12 h-12 text-gray-700 mb-4" />}
      <h3 className="text-lg font-medium text-gray-400 mb-2">{title}</h3>
      <p className="text-sm text-gray-600 max-w-sm">{message}</p>
    </div>
  )
}
