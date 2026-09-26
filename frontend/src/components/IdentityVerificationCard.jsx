import {
  ShieldCheck, AlertTriangle, CheckCircle2, XCircle,
  HelpCircle, User, FileText, Activity, Scale
} from 'lucide-react'

/**
 * IdentityVerificationCard
 * Displays the explainable identity verification decision to the screening officer.
 * Shows Document Face, Person Face, Liveness, Face Similarity, Threshold, and Identity Match.
 */
export default function IdentityVerificationCard({ identity, onTriggerVerification }) {
  if (!identity) {
    return (
      <div className="glass-card p-6 border-l-4 border-l-amber-500">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-gray-200">IDENTITY VERIFICATION</h3>
              <p className="text-xs text-amber-400/90 font-medium mt-0.5">
                Person Verification is Required — Status: INCOMPLETE
              </p>
            </div>
          </div>
          {onTriggerVerification && (
            <button
              onClick={onTriggerVerification}
              className="btn-primary text-xs py-1.5 px-3"
            >
              Verify Person Identity
            </button>
          )}
        </div>
      </div>
    )
  }

  const status = identity.status || identity.identity_status || 'INCOMPLETE'
  const isPass = status === 'PASS'
  const isFail = status === 'FAIL'
  const isIncomplete = status === 'INCOMPLETE'

  const docFace = identity.document_face || {}
  const personFace = identity.person_face || {}
  const liveness = identity.liveness || {}
  const faceMatch = identity.face_match || {}

  const similarityPercent =
    faceMatch.similarity !== undefined && faceMatch.status !== 'NOT_EVALUATED'
      ? `${(faceMatch.similarity * 100).toFixed(0)}%`
      : 'Not evaluated'

  const thresholdPercent =
    faceMatch.threshold !== undefined
      ? `${(faceMatch.threshold * 100).toFixed(0)}%`
      : '60%'

  return (
    <div
      className={`glass-card p-6 border-l-4 transition-all duration-300 ${
        isPass
          ? 'border-l-emerald-500'
          : isIncomplete
          ? 'border-l-amber-500'
          : 'border-l-red-500'
      }`}
      id="identity-verification-report-card"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-sentinel-border/30 pb-4 mb-4">
        <div className="flex items-center gap-3">
          <div
            className={`p-2.5 rounded-xl border ${
              isPass
                ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                : isIncomplete
                ? 'bg-amber-500/10 border-amber-500/30 text-amber-400'
                : 'bg-red-500/10 border-red-500/30 text-red-400'
            }`}
          >
            {isPass ? (
              <ShieldCheck className="w-5 h-5" />
            ) : (
              <AlertTriangle className="w-5 h-5" />
            )}
          </div>
          <div>
            <h3 className="text-base font-bold text-gray-100 tracking-wide font-mono">
              IDENTITY VERIFICATION
            </h3>
            <p className="text-xs text-gray-500">
              Mandatory dual-input biometric & temporal liveness screening
            </p>
          </div>
        </div>

        {/* Status Badge */}
        <div
          className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-bold border ${
            isPass
              ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
              : isIncomplete
              ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
              : 'bg-red-500/20 text-red-300 border-red-500/40'
          }`}
        >
          {isPass ? (
            <CheckCircle2 className="w-3.5 h-3.5" />
          ) : isIncomplete ? (
            <HelpCircle className="w-3.5 h-3.5" />
          ) : (
            <XCircle className="w-3.5 h-3.5" />
          )}
          <span>{status}</span>
        </div>
      </div>

      {/* Structured Comparison Table */}
      <div className="divide-y divide-sentinel-border/20 text-sm">
        {/* Document Face */}
        <div className="py-2.5 flex items-center justify-between">
          <span className="text-gray-400 flex items-center gap-2">
            <FileText className="w-4 h-4 text-sentinel-primary" />
            Document Face
          </span>
          <span
            className={`font-mono font-semibold flex items-center gap-1.5 ${
              docFace.detected ? 'text-emerald-400' : 'text-red-400'
            }`}
          >
            {docFace.detected ? '✓ Detected' : '✗ Not detected'}
          </span>
        </div>

        {/* Person Face */}
        <div className="py-2.5 flex items-center justify-between">
          <span className="text-gray-400 flex items-center gap-2">
            <User className="w-4 h-4 text-sentinel-primary" />
            Person Face
          </span>
          <span
            className={`font-mono font-semibold flex items-center gap-1.5 ${
              personFace.detected
                ? 'text-emerald-400'
                : isIncomplete
                ? 'text-amber-400'
                : 'text-red-400'
            }`}
          >
            {personFace.detected
              ? '✓ Detected'
              : isIncomplete
              ? '— Missing'
              : '✗ Not detected'}
          </span>
        </div>

        {/* Liveness */}
        <div className="py-2.5 flex items-center justify-between">
          <span className="text-gray-400 flex items-center gap-2">
            <Activity className="w-4 h-4 text-sentinel-primary" />
            Liveness
          </span>
          <span
            className={`font-mono font-bold flex items-center gap-1.5 ${
              liveness.status === 'PASS'
                ? 'text-emerald-400'
                : liveness.status === 'INCONCLUSIVE'
                ? 'text-amber-400'
                : 'text-red-400'
            }`}
          >
            {liveness.status === 'PASS'
              ? '✓ PASS'
              : liveness.status === 'INCONCLUSIVE'
              ? '⚠ INCONCLUSIVE'
              : '✗ FAIL'}
          </span>
        </div>

        {/* Face Similarity */}
        <div className="py-2.5 flex items-center justify-between">
          <span className="text-gray-400 flex items-center gap-2">
            <Scale className="w-4 h-4 text-sentinel-primary" />
            Face Similarity
          </span>
          <span className="font-mono text-gray-200 font-semibold">
            {similarityPercent}
          </span>
        </div>

        {/* Match Threshold */}
        <div className="py-2.5 flex items-center justify-between">
          <span className="text-gray-400">Match Threshold</span>
          <span className="font-mono text-gray-400">{thresholdPercent}</span>
        </div>

        {/* Identity Match */}
        <div className="py-2.5 flex items-center justify-between">
          <span className="text-gray-300 font-medium">Identity Match</span>
          <span
            className={`font-mono font-bold flex items-center gap-1.5 ${
              faceMatch.status === 'PASS'
                ? 'text-emerald-400'
                : isIncomplete
                ? 'text-amber-400'
                : 'text-red-400'
            }`}
          >
            {faceMatch.status === 'PASS' ? '✓ PASS' : '✗ FAIL'}
          </span>
        </div>
      </div>

      {/* Failure Reason Box */}
      {identity.failure_reason && (
        <div className="mt-4 p-3 rounded-xl bg-red-500/10 border border-red-500/30 text-xs text-red-300 flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
          <div>
            <span className="font-bold text-red-200">Reason: </span>
            <span>"{identity.failure_reason}. Human review required."</span>
          </div>
        </div>
      )}

      {/* Retake / Re-verify button if not passing */}
      {!isPass && onTriggerVerification && (
        <div className="mt-4 pt-3 border-t border-sentinel-border/30 flex justify-end">
          <button
            onClick={onTriggerVerification}
            className="btn-primary text-xs py-1.5 px-4"
          >
            {isIncomplete ? 'Complete Person Verification' : 'Retake Verification'}
          </button>
        </div>
      )}
    </div>
  )
}
