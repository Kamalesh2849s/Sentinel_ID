import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Shield, RefreshCw, ArrowLeft, Info, AlertTriangle,
  Eye, Fingerprint, Database, FileSearch, Cpu,
  CheckCircle, XCircle, Clock, ChevronDown, ChevronUp,
  Camera, UserCheck, Activity, BookOpen, GitCompare
} from 'lucide-react'
import { screeningsApi } from '../services/api'
import {
  StatusBadge, RiskGauge, StageIndicator,
  ValidationRow, RiskReasonCard, Spinner
} from '../components/UIComponents'
import IdentityVerificationCard from '../components/IdentityVerificationCard'
import PersonVerificationSection from '../components/PersonVerificationSection'

const PIPELINE_STAGES = [
  { key: 'preprocessing', label: 'Image Preprocessing', icon: FileSearch },
  { key: 'ocr', label: 'OCR Text Extraction', icon: Cpu },
  { key: 'mrz', label: 'MRZ Extraction & Validation', icon: Fingerprint },
  { key: 'validation', label: 'Document Validation', icon: Shield },
  { key: 'tamper', label: 'Tamper Detection', icon: Eye },
  { key: 'doc_face', label: 'Document Face Extraction', icon: UserCheck },
  { key: 'person', label: 'Person Verification', icon: Camera },
  { key: 'liveness', label: 'Liveness Detection', icon: Activity },
  { key: 'face_match', label: 'Face Matching', icon: Database },
  { key: 'risk', label: 'Risk Analysis', icon: AlertTriangle },
]

// ─── Source badge ─────────────────────────────────────────────────────────────
function SourceBadge({ source }) {
  if (!source) return null
  const colors = {
    MRZ: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
    OCR: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
    'MRZ + OCR': 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
    BOTH: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  }
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded border font-mono ${colors[source] || 'bg-gray-500/20 text-gray-400 border-gray-500/30'}`}>
      {source}
    </span>
  )
}

// ─── Info field with source ───────────────────────────────────────────────────
function InfoField({ label, value, source, subValue }) {
  return (
    <div className="py-2.5 border-b border-sentinel-border/30 last:border-0">
      <div className="flex items-center gap-2 mb-0.5">
        <p className="text-xs text-gray-500 uppercase tracking-wider">{label}</p>
        {source && <SourceBadge source={source} />}
      </div>
      <p className="text-sm text-gray-200 font-medium">
        {value || <span className="text-gray-600 font-normal italic">Not detected</span>}
      </p>
      {subValue && (
        <p className="text-[11px] text-gray-600 font-mono mt-0.5">{subValue}</p>
      )}
    </div>
  )
}

// ─── Collapsible section ──────────────────────────────────────────────────────
function CollapsibleSection({ title, icon: Icon, children, defaultOpen = false, badge }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="glass-card overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 p-5 hover:bg-sentinel-surface/50 transition-colors"
      >
        <Icon className="w-4 h-4 text-sentinel-primary" />
        <span className="text-sm font-semibold text-gray-300 flex-1 text-left">{title}</span>
        {badge}
        {open ? <ChevronUp className="w-4 h-4 text-gray-500" /> : <ChevronDown className="w-4 h-4 text-gray-500" />}
      </button>
      {open && (
        <div className="px-5 pb-5 border-t border-sentinel-border/30">
          {children}
        </div>
      )}
    </div>
  )
}

// ─── Check digit row ──────────────────────────────────────────────────────────
function CheckRow({ label, passed, notUsed }) {
  if (passed === null || passed === undefined) {
    return (
      <div className="flex items-center justify-between py-1.5 border-b border-sentinel-border/20 last:border-0">
        <span className="text-xs text-gray-400">{label}</span>
        <span className="text-xs text-gray-500 font-mono">N/A</span>
      </div>
    )
  }
  if (notUsed) {
    return (
      <div className="flex items-center justify-between py-1.5 border-b border-sentinel-border/20 last:border-0">
        <span className="text-xs text-gray-400">{label}</span>
        <span className="text-xs text-gray-500 font-mono">NOT USED</span>
      </div>
    )
  }
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-sentinel-border/20 last:border-0">
      <span className="text-xs text-gray-400">{label}</span>
      <div className="flex items-center gap-1.5">
        {passed
          ? <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
          : <XCircle className="w-3.5 h-3.5 text-red-400" />}
        <span className={`text-xs font-mono font-bold ${passed ? 'text-emerald-400' : 'text-red-400'}`}>
          {passed ? 'PASS' : 'FAIL'}
        </span>
      </div>
    </div>
  )
}

// ─── Consistency row ──────────────────────────────────────────────────────────
function ConsistencyRow({ label, status }) {
  const icon = status === 'MATCH'
    ? <CheckCircle className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
    : status === 'MISMATCH'
    ? <AlertTriangle className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />
    : <span className="w-3.5 h-3.5 text-gray-500 flex-shrink-0">—</span>
  const color = status === 'MATCH' ? 'text-emerald-400' : status === 'MISMATCH' ? 'text-amber-400' : 'text-gray-500'
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-sentinel-border/20 last:border-0">
      <span className="text-xs text-gray-400">{label}</span>
      <div className="flex items-center gap-1.5">
        {icon}
        <span className={`text-xs font-mono font-bold ${color}`}>{status || 'NOT AVAILABLE'}</span>
      </div>
    </div>
  )
}

// ─── MRZ Analysis Section ─────────────────────────────────────────────────────
function MRZAnalysisSection({ mrz }) {
  if (!mrz) {
    return (
      <div className="pt-4">
        <div className="flex items-center gap-2 p-3 bg-gray-500/10 border border-gray-500/20 rounded-lg">
          <XCircle className="w-4 h-4 text-gray-400" />
          <p className="text-sm text-gray-400">MRZ data not available for this screening</p>
        </div>
      </div>
    )
  }

  const isDetected = !!mrz.mrz_detected
  const line1 = mrz.line1 || (mrz.raw_mrz_lines && mrz.raw_mrz_lines[0]) || ''
  const line2 = mrz.line2 || (mrz.raw_mrz_lines && mrz.raw_mrz_lines[1]) || ''
  const line3 = mrz.line3 || (mrz.raw_mrz_lines && mrz.raw_mrz_lines[2]) || ''

  const docNumCheck = mrz.passport_number_check !== undefined ? mrz.passport_number_check : mrz.check_digits?.document_number
  const dobCheck = mrz.dob_check !== undefined ? mrz.dob_check : mrz.check_digits?.date_of_birth
  const expCheck = mrz.expiry_check !== undefined ? mrz.expiry_check : mrz.check_digits?.date_of_expiry
  const compCheck = mrz.composite_check !== undefined ? mrz.composite_check : mrz.check_digits?.composite

  let overallStatus = 'UNAVAILABLE'
  if (!isDetected) {
    overallStatus = 'UNAVAILABLE'
  } else if (mrz.mrz_status === 'VALID' || (docNumCheck && dobCheck && expCheck && compCheck)) {
    overallStatus = 'VALID'
  } else if ([docNumCheck, dobCheck, expCheck, compCheck].some(Boolean)) {
    overallStatus = 'PARTIALLY VALID'
  } else {
    overallStatus = 'INVALID'
  }

  const statusColors = {
    VALID: 'bg-emerald-500/15 border-emerald-500/30 text-emerald-400',
    'PARTIALLY VALID': 'bg-amber-500/15 border-amber-500/30 text-amber-400',
    INVALID: 'bg-red-500/15 border-red-500/30 text-red-400',
    UNAVAILABLE: 'bg-gray-500/15 border-gray-500/30 text-gray-400',
  }
  const statusColor = statusColors[overallStatus] || 'bg-gray-500/15 border-gray-500/30 text-gray-400'

  return (
    <div className="pt-4 space-y-4" id="mrz-analysis-container">
      {/* 1. Header Cards: MRZ Status, Format, Overall MRZ Status */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="bg-sentinel-surface/50 rounded-lg p-3">
          <p className="text-xs text-gray-500 mb-1">MRZ STATUS</p>
          <div className="flex items-center gap-1.5">
            {isDetected ? (
              <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
            ) : (
              <XCircle className="w-3.5 h-3.5 text-gray-500" />
            )}
            <span className={`text-sm font-mono font-bold ${isDetected ? 'text-emerald-400' : 'text-gray-400'}`}>
              {isDetected ? 'Detected' : 'Not Detected'}
            </span>
          </div>
        </div>

        <div className="bg-sentinel-surface/50 rounded-lg p-3">
          <p className="text-xs text-gray-500 mb-1">FORMAT</p>
          <p className="text-sm font-mono font-bold text-blue-300">
            {mrz.mrz_format || '—'}
            {mrz.mrz_format === 'TD3' && <span className="text-gray-500 font-normal text-xs ml-1">/ 2×44 Passport</span>}
            {mrz.mrz_format === 'TD1' && <span className="text-gray-500 font-normal text-xs ml-1">/ 3×30 ID</span>}
            {mrz.mrz_format === 'TD2' && <span className="text-gray-500 font-normal text-xs ml-1">/ 2×36 TD2</span>}
          </p>
        </div>

        <div className={`p-3 rounded-lg border ${statusColor}`}>
          <p className="text-xs text-gray-400 mb-1">OVERALL MRZ STATUS</p>
          <div className="flex items-center gap-1.5">
            {overallStatus === 'VALID' ? (
              <CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0" />
            ) : overallStatus === 'PARTIALLY VALID' ? (
              <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
            ) : (
              <XCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
            )}
            <span className="text-sm font-mono font-bold">
              {overallStatus}
            </span>
          </div>
        </div>
      </div>

      {isDetected && (
        <>
          {/* 2. RAW MRZ */}
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wider mb-2 font-semibold">RAW MRZ</p>
            <div className="bg-sentinel-bg rounded-lg p-3 border border-sentinel-border/30 space-y-2">
              {line1 && (
                <div>
                  <div className="flex justify-between items-center mb-1">
                    <p className="text-[10px] text-gray-500 font-mono uppercase">Line 1</p>
                    <p className="text-[10px] text-gray-600 font-mono">{line1.length} chars</p>
                  </div>
                  <pre className="text-xs text-emerald-300 font-mono tracking-wider break-all">{line1}</pre>
                </div>
              )}
              {line2 && (
                <div>
                  <div className="flex justify-between items-center mb-1">
                    <p className="text-[10px] text-gray-500 font-mono uppercase">Line 2</p>
                    <p className="text-[10px] text-gray-600 font-mono">{line2.length} chars</p>
                  </div>
                  <pre className="text-xs text-emerald-300 font-mono tracking-wider break-all">{line2}</pre>
                </div>
              )}
              {line3 && (
                <div>
                  <div className="flex justify-between items-center mb-1">
                    <p className="text-[10px] text-gray-500 font-mono uppercase">Line 3</p>
                    <p className="text-[10px] text-gray-600 font-mono">{line3.length} chars</p>
                  </div>
                  <pre className="text-xs text-emerald-300 font-mono tracking-wider break-all">{line3}</pre>
                </div>
              )}
            </div>
          </div>

          {/* 3. PARSED DATA */}
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wider mb-2 font-semibold">PARSED DATA</p>
            <div className="bg-sentinel-surface/40 rounded-lg p-3 grid grid-cols-2 md:grid-cols-3 gap-3 border border-sentinel-border/30">
              <div>
                <span className="text-[11px] text-gray-400 block">Document Number</span>
                <span className="text-xs font-mono font-bold text-gray-200">
                  {mrz.document_number || mrz.mrz_parsed_fields?.document_number || '—'}
                </span>
              </div>
              <div>
                <span className="text-[11px] text-gray-400 block">Nationality</span>
                <span className="text-xs font-mono font-bold text-cyan-300">
                  {mrz.nationality_code || mrz.nationality || mrz.mrz_parsed_fields?.nationality_code || '—'}
                </span>
              </div>
              <div>
                <span className="text-[11px] text-gray-400 block">Date of Birth</span>
                <span className="text-xs font-mono font-bold text-gray-200">
                  {mrz.date_of_birth || mrz.mrz_parsed_fields?.date_of_birth || '—'}
                </span>
              </div>
              <div>
                <span className="text-[11px] text-gray-400 block">Sex</span>
                <span className="text-xs font-mono font-bold text-gray-200">
                  {mrz.sex || mrz.mrz_parsed_fields?.sex || '—'}
                </span>
              </div>
              <div>
                <span className="text-[11px] text-gray-400 block">Expiry Date</span>
                <span className="text-xs font-mono font-bold text-gray-200">
                  {mrz.expiry_date || mrz.mrz_parsed_fields?.date_of_expiry || '—'}
                </span>
              </div>
              <div>
                <span className="text-[11px] text-gray-400 block">Issuing Country</span>
                <span className="text-xs font-mono font-bold text-blue-300">
                  {mrz.issuing_country_code || mrz.issuing_country || mrz.mrz_parsed_fields?.issuing_country_code || '—'}
                </span>
              </div>
            </div>
          </div>

          {/* 4. CHECK DIGITS */}
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wider mb-2 font-semibold">CHECK DIGITS</p>
            <div className="bg-sentinel-surface/40 rounded-lg p-3 space-y-0 border border-sentinel-border/30">
              <CheckRow label="Document Number" passed={docNumCheck} />
              <CheckRow label="Date of Birth" passed={dobCheck} />
              <CheckRow label="Expiry Date" passed={expCheck} />
              <CheckRow label="Composite" passed={compCheck} />
            </div>
          </div>

          {/* Failure details */}
          {mrz.failure_reasons?.length > 0 && (
            <div className="space-y-1">
              {mrz.failure_reasons.map((r, i) => (
                <p key={i} className="text-xs text-red-400">⚠ {r}</p>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ─── Consistency Section ──────────────────────────────────────────────────────
function ConsistencySection({ consistency }) {
  if (!consistency) {
    return <p className="text-sm text-gray-500 pt-4">Consistency data not available — MRZ not detected or OCR failed</p>
  }
  return (
    <div className="pt-4">
      <p className="text-xs text-gray-500 mb-3 leading-relaxed">
        Comparison of MRZ machine-readable fields against OCR-extracted visual zone data.
        Mismatches may indicate tampering or OCR errors.
      </p>
      <div className="bg-sentinel-surface/40 rounded-lg p-3 space-y-0">
        <ConsistencyRow label="Full Name" status={consistency.name} />
        <ConsistencyRow label="Document Number" status={consistency.document_number} />
        <ConsistencyRow label="Date of Birth" status={consistency.date_of_birth} />
        <ConsistencyRow label="Date of Expiry" status={consistency.date_of_expiry} />
        <ConsistencyRow label="Nationality" status={consistency.nationality} />
      </div>
    </div>
  )
}

// ─── Document Data Section ───────────────────────────────────────────────────
function ExtractedDocumentSection({ doc, mrz }) {
  // Determine values and their sources per Bug 1 requirements 7, 8, 9, 10
  const fullName = doc?.full_name || mrz?.full_name_mrz || mrz?.full_name || null
  const nameSource = doc?.name_source || (
    doc?.full_name && mrz?.full_name ? 'MRZ + OCR'
    : mrz?.full_name ? 'MRZ'
    : doc?.full_name ? 'OCR' : null
  )

  const docNumber = mrz?.document_number || doc?.document_number || null
  const docNumSource = mrz?.document_number && doc?.document_number ? 'MRZ + OCR'
    : mrz?.document_number ? 'MRZ'
    : doc?.document_number ? 'OCR' : null

  const dob = mrz?.date_of_birth || doc?.date_of_birth || null
  const dobSource = mrz?.date_of_birth && doc?.date_of_birth ? 'MRZ + OCR'
    : mrz?.date_of_birth ? 'MRZ'
    : doc?.date_of_birth ? 'OCR' : null

  // Date of Issue: Never fabricate from TD3 MRZ!
  const issueDate = doc?.date_of_issue || doc?.issue_date || null
  const issueSource = issueDate ? (doc?.date_of_issue_source || 'OCR/VIZ') : 'Not detected'

  const expiry = mrz?.expiry_date || doc?.expiry_date || null
  const expirySource = mrz?.expiry_date && doc?.expiry_date ? 'MRZ + OCR'
    : mrz?.expiry_date ? 'MRZ'
    : doc?.expiry_date ? 'OCR' : null

  // Nationality vs Issuing Country vs Country Code (Requirement 10)
  const nationality = doc?.nationality || mrz?.nationality_code || mrz?.nationality || null
  const issuingCountry = doc?.issuing_country || mrz?.issuing_country_code || mrz?.issuing_country || null
  const countryCode = mrz?.issuing_country_code || doc?.issuing_country_code || (issuingCountry && issuingCountry.length === 3 ? issuingCountry : null)

  const sex = mrz?.sex || doc?.sex || null
  const sexSource = mrz?.sex && doc?.sex ? 'MRZ + OCR' : mrz?.sex ? 'MRZ' : doc?.sex ? 'OCR' : null
  const docType = mrz?.document_type || doc?.document_type || 'Passport'

  return (
    <div className="space-y-0">
      <InfoField
        label="Full Name"
        value={fullName}
        source={nameSource}
      />
      <InfoField
        label="Nationality"
        value={nationality}
        source={mrz?.nationality_code ? 'MRZ' : doc?.nationality ? 'OCR' : null}
      />
      <InfoField
        label="Issuing Country"
        value={issuingCountry}
        source={mrz?.issuing_country_code ? 'MRZ' : doc?.issuing_country ? 'OCR' : null}
      />
      <InfoField
        label="Country Code"
        value={countryCode}
        source={countryCode ? 'MRZ' : null}
      />
      <InfoField
        label="Date of Birth"
        value={dob}
        source={dobSource}
        subValue={mrz?.date_of_birth_raw ? `MRZ raw: ${mrz.date_of_birth_raw}` : null}
      />
      <InfoField
        label="Date of Issue"
        value={issueDate || 'Not detected'}
        source={issueSource}
        subValue={!issueDate ? 'Not in MRZ (TD3) — visual OCR only' : null}
      />
      <InfoField
        label="Date of Expiry"
        value={expiry}
        source={expirySource}
        subValue={mrz?.expiry_date_raw ? `MRZ raw: ${mrz.expiry_date_raw}` : null}
      />
      <InfoField
        label="Document Number"
        value={docNumber}
        source={docNumSource}
      />
      <InfoField
        label="Sex"
        value={sex}
        source={sexSource}
      />
      <InfoField
        label="Document Type"
        value={docType}
        source={mrz?.document_type ? 'MRZ' : null}
      />
    </div>
  )
}

// ─── Tamper Section ───────────────────────────────────────────────────────────
function TamperSection({ tamper }) {
  if (!tamper) return <p className="text-sm text-gray-500 py-2">No tamper analysis data</p>
  return (
    <div className="pt-4 space-y-3">
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-sentinel-surface/50 rounded-lg p-3">
          <p className="text-xs text-gray-500 mb-1">Tamper Score</p>
          <p className={`text-2xl font-bold font-mono ${tamper.tamper_score > 0.55 ? 'text-red-400' : 'text-emerald-400'}`}>
            {(tamper.tamper_score * 100).toFixed(0)}%
          </p>
        </div>
        <div className="bg-sentinel-surface/50 rounded-lg p-3">
          <p className="text-xs text-gray-500 mb-1">ELA Score</p>
          <p className={`text-2xl font-bold font-mono ${tamper.ela_score > 0.5 ? 'text-amber-400' : 'text-emerald-400'}`}>
            {(tamper.ela_score * 100).toFixed(0)}%
          </p>
        </div>
      </div>
      <div className={`flex items-center gap-2 p-3 rounded-lg ${tamper.tamper_detected ? 'bg-red-500/10 border border-red-500/20' : 'bg-emerald-500/10 border border-emerald-500/20'}`}>
        {tamper.tamper_detected
          ? <XCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
          : <CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0" />}
        <span className={`text-sm ${tamper.tamper_detected ? 'text-red-400' : 'text-emerald-400'}`}>
          {tamper.tamper_detected ? 'Anomalies detected — human review recommended' : 'No significant anomalies detected'}
        </span>
      </div>
      {tamper.reasons?.map((r, i) => (
        <p key={i} className="text-xs text-gray-400 leading-relaxed">• {r}</p>
      ))}
    </div>
  )
}

// ─── Face Section ─────────────────────────────────────────────────────────────
function FaceSection({ face }) {
  if (!face) return <p className="text-sm text-gray-500 py-2">No face verification data</p>
  return (
    <div className="pt-4 space-y-3">
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-sentinel-surface/50 rounded-lg p-3">
          <p className="text-xs text-gray-500 mb-1">Similarity Score</p>
          <p className={`text-2xl font-bold font-mono ${face.match ? 'text-emerald-400' : 'text-red-400'}`}>
            {(face.similarity * 100).toFixed(1)}%
          </p>
        </div>
        <div className="bg-sentinel-surface/50 rounded-lg p-3">
          <p className="text-xs text-gray-500 mb-1">Match Decision</p>
          <div className="flex items-center gap-2 mt-1">
            {face.match
              ? <CheckCircle className="w-5 h-5 text-emerald-400" />
              : <XCircle className="w-5 h-5 text-red-400" />}
            <span className={`font-bold ${face.match ? 'text-emerald-400' : 'text-red-400'}`}>
              {face.match ? 'MATCH' : 'NO MATCH'}
            </span>
          </div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div className="flex items-center gap-2">
          <span className={face.face_detected_document ? 'text-emerald-400' : 'text-red-400'}>
            {face.face_detected_document ? '✓' : '✗'}
          </span>
          <span className="text-gray-400">Face in document</span>
        </div>
        <div className="flex items-center gap-2">
          <span className={face.face_detected_person ? 'text-emerald-400' : 'text-amber-400'}>
            {face.face_detected_person ? '✓' : '—'}
          </span>
          <span className="text-gray-400">Person photo provided</span>
        </div>
      </div>
      {face.failure_reason && (
        <p className="text-sm text-amber-400">Note: {face.failure_reason}</p>
      )}
      <p className="text-xs text-gray-600 italic">
        Liveness status: {face.liveness_status}
      </p>
    </div>
  )
}

// ─── Risk Score Section with 4 States ───────────────────────────────────────
function RiskScoreSection({ screening, onTriggerVerification }) {
  const s = screening
  const risk = s.risk || {}
  const riskResult = s.risk_result || {}
  const idStatus = s.identity_verification?.status || s.identity_verification?.identity_status || 'INCOMPLETE'

  // 4 States: 1. Processing, 2. Waiting for Verification, 3. Failed/Unavailable, 4. Completed
  const isCalculating = s.status === 'PROCESSING' || risk.status === 'calculating'
  const isWaitingVerification =
    !isCalculating &&
    (risk.status === 'pending' ||
      s.status === 'PENDING' ||
      risk.score === null ||
      s.risk_score === null ||
      idStatus !== 'PASS')
  const isUnavailableOrFailed =
    !isCalculating &&
    !isWaitingVerification &&
    (risk.status === 'unavailable' || risk.status === 'failed' || s.status === 'FAILED')
  const isCompleted =
    !isCalculating &&
    !isWaitingVerification &&
    !isUnavailableOrFailed &&
    (risk.status === 'completed' || (s.risk_score !== null && s.risk_score !== undefined))

  const failureReason =
    risk.failure_reason ||
    riskResult.failure_reason ||
    (s.status === 'FAILED' ? 'Document or screening processing failed' : null)

  const numericScore = s.risk_score !== null && s.risk_score !== undefined ? s.risk_score : risk.score
  const level =
    risk.level ||
    riskResult.risk_level ||
    (numericScore !== null
      ? numericScore <= 35
        ? 'LOW'
        : numericScore <= 65
        ? 'MEDIUM'
        : 'HIGH'
      : null)

  return (
    <div className="glass-card p-6 flex flex-col items-center gap-4">
      <div className="w-full flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-sentinel-primary" />
          Risk Score
        </h2>
        {isCompleted && level && (
          <span
            className={`text-xs font-mono font-bold px-2.5 py-0.5 rounded border uppercase ${
              level.toLowerCase() === 'low'
                ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                : level.toLowerCase() === 'medium'
                ? 'bg-amber-500/10 border-amber-500/30 text-amber-400'
                : 'bg-red-500/10 border-red-500/30 text-red-400'
            }`}
          >
            {level} RISK
          </span>
        )}
      </div>

      {/* STATE 1: PROCESSING */}
      {isCalculating && (
        <div className="flex flex-col items-center gap-3 py-6 text-center">
          <Spinner size="lg" />
          <div>
            <p className="text-base font-bold text-gray-200">Calculating...</p>
            <p className="text-xs text-gray-400 mt-1">Evaluating document signals and verification inputs...</p>
          </div>
        </div>
      )}

      {/* STATE 2: WAITING FOR VERIFICATION */}
      {isWaitingVerification && (
        <div className="flex flex-col items-center gap-3 py-4 text-center max-w-md">
          <div className="w-14 h-14 rounded-full bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400">
            <Camera className="w-6 h-6 animate-pulse" />
          </div>
          <div>
            <h3 className="text-base font-bold text-gray-100">
              Awaiting Identity Verification
            </h3>
            <p className="text-xs text-amber-400/90 mt-1.5 leading-relaxed">
              Risk calculation pending — complete identity verification below.
            </p>
          </div>
          <div className="flex items-center gap-2 bg-sentinel-surface px-3 py-1.5 rounded-lg border border-sentinel-border text-xs text-gray-400 font-mono mt-1">
            <span>Risk Score:</span>
            <span className="text-amber-400 font-bold uppercase">Pending</span>
          </div>
          {onTriggerVerification && (
            <button
              type="button"
              onClick={onTriggerVerification}
              className="btn-primary text-xs flex items-center gap-1.5 py-2 px-4 mt-2 font-semibold"
            >
              <Camera className="w-3.5 h-3.5" /> Open Camera Verification
            </button>
          )}
        </div>
      )}

      {/* STATE 3: FAILED / UNAVAILABLE */}
      {isUnavailableOrFailed && (
        <div className="flex flex-col items-center gap-3 py-4 text-center max-w-md">
          <div className="w-14 h-14 rounded-full bg-red-500/10 border border-red-500/30 flex items-center justify-center text-red-400">
            <AlertTriangle className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-base font-bold text-gray-100">
              Risk Score: Unavailable
            </h3>
            {failureReason && (
              <p className="text-xs text-red-400/90 mt-1.5 leading-relaxed font-mono">
                Reason: {failureReason}
              </p>
            )}
          </div>
          <StatusBadge status="FAILED" className="mt-1" />
        </div>
      )}

      {/* STATE 4: COMPLETED */}
      {isCompleted && (
        <>
          <RiskGauge score={numericScore} size="lg" />
          <div className="text-center">
            <StatusBadge status={s.status} className="mb-2" />
            {s.processing_time_ms && (
              <p className="text-xs text-gray-600 mt-2 font-mono">
                Processed in {(s.processing_time_ms / 1000).toFixed(1)}s
              </p>
            )}
          </div>
        </>
      )}
    </div>
  )
}

// ─── Final Decision Section ───────────────────────────────────────────────────
function FinalDecisionSection({ screening, riskResult }) {
  const statusConfig = {
    VERIFIED: {
      color: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
      label: 'DOCUMENT VERIFIED',
      icon: CheckCircle,
    },
    SUSPICIOUS: {
      color: 'bg-amber-500/10 border-amber-500/30 text-amber-400',
      label: 'SUSPICIOUS — REVIEW REQUIRED',
      icon: AlertTriangle,
    },
    HIGH_RISK: {
      color: 'bg-red-500/10 border-red-500/30 text-red-400',
      label: 'HIGH RISK — MANDATORY REVIEW',
      icon: XCircle,
    },
    PENDING: {
      color: 'bg-sentinel-primary/10 border-sentinel-primary/30 text-sentinel-primary',
      label: 'ACTION REQUIRED — IDENTITY VERIFICATION PENDING',
      icon: Clock,
    },
    FAILED: {
      color: 'bg-gray-500/10 border-gray-500/30 text-gray-400',
      label: 'PROCESSING FAILED',
      icon: XCircle,
    },
  }
  const cfg = statusConfig[screening?.status] || statusConfig.PENDING
  const Icon = cfg.icon
  return (
    <div className={`p-4 rounded-xl border ${cfg.color}`}>
      <div className="flex items-center gap-3 mb-3">
        <Icon className="w-5 h-5 flex-shrink-0" />
        <p className="font-bold text-sm font-mono">{cfg.label}</p>
      </div>
      {riskResult?.recommendation && (
        <p className="text-xs leading-relaxed opacity-80">{riskResult.recommendation}</p>
      )}
      <p className="text-[10px] text-gray-600 italic mt-3">
        ⚠ This automated result does NOT constitute a final determination. Final decision rests with the screening officer.
      </p>
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function ScreeningDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [screening, setScreening] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showVerifyWidget, setShowVerifyWidget] = useState(false)
  const pollRef = useRef(null)
  const abortControllerRef = useRef(null)

  const fetchScreening = useCallback(async () => {
    if (!abortControllerRef.current) {
      abortControllerRef.current = new AbortController()
    }
    const currentSignal = abortControllerRef.current.signal
    try {
      const { data } = await screeningsApi.get(id, { signal: currentSignal })
      if (!currentSignal.aborted) {
        setScreening(data)
        if (['VERIFIED', 'SUSPICIOUS', 'HIGH_RISK', 'FAILED'].includes(data.status)) {
          if (pollRef.current) clearInterval(pollRef.current)
        }
      }
    } catch (err) {
      if (!currentSignal.aborted && err.name !== 'CanceledError' && err.code !== 'ERR_CANCELED') {
        setError('Failed to load screening data')
      }
    } finally {
      if (!currentSignal.aborted) {
        setLoading(false)
      }
    }
  }, [id])

  useEffect(() => {
    setLoading(true)
    setScreening(null)
    setError('')
    
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    abortControllerRef.current = new AbortController()

    fetchScreening()
    pollRef.current = setInterval(fetchScreening, 3000)

    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [id, fetchScreening])

  const handleReprocess = async () => {
    try {
      await screeningsApi.reprocess(id)
      setLoading(true)
      fetchScreening()
    } catch (err) {
      console.error(err)
    }
  }

  if (loading && !screening) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <Spinner size="lg" className="mx-auto mb-4" />
          <p className="text-gray-400 font-mono">Loading screening...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6 text-center">
        <XCircle className="w-12 h-12 text-red-400 mx-auto mb-3" />
        <p className="text-gray-400">{error}</p>
        <button className="btn-secondary mt-4" onClick={() => navigate('/history')}>
          Back to History
        </button>
      </div>
    )
  }

  const s = screening
  const isProcessing = s.status === 'PROCESSING' || (s.status === 'PENDING' && !s.extracted_document && !s.mrz_result)
  const riskResult = s.risk_result
  const doc = s.extracted_document
  const mrz = s.mrz_result
  const tamper = s.tamper_result
  const face = s.face_result
  const identity = s.identity_verification
  const idStatus = identity?.status || identity?.identity_status || 'INCOMPLETE'
  const validations = s.validation_results || []

  // Consistency data — can come from mrz_result.consistency
  const consistency = mrz?.consistency || null

  return (
    <div className="p-6 space-y-6 animate-fade-in">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between">
        <div>
          <button
            onClick={() => navigate('/history')}
            className="flex items-center gap-2 text-gray-500 hover:text-gray-300 text-sm mb-3 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" /> Back to History
          </button>
          <h1 className="text-2xl font-bold text-gray-100">
            Screening #{s.id}
          </h1>
          <p className="text-sm text-gray-500 font-mono mt-0.5">
            {s.document_type} · {new Date(s.created_at).toLocaleString()}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <StatusBadge status={s.status} />
          <button
            onClick={handleReprocess}
            disabled={isProcessing}
            className="btn-secondary flex items-center gap-1.5 text-xs disabled:opacity-50"
          >
            <RefreshCw className={`w-3 h-3 ${isProcessing ? 'animate-spin' : ''}`} />
            Reprocess
          </button>
        </div>
      </div>

      {/* ── Risk Banners ────────────────────────────────────────────────────── */}
      {s.status === 'PENDING' && (
        <div className="flex items-center gap-3 bg-sentinel-primary/10 border border-sentinel-primary/40 rounded-xl px-5 py-4">
          <Clock className="w-5 h-5 text-sentinel-primary flex-shrink-0 animate-pulse" />
          <div className="flex-1">
            <p className="text-sm font-bold text-sentinel-primary">IDENTITY VERIFICATION PENDING</p>
            <p className="text-xs text-gray-300 mt-0.5">
              Document processing is complete. Awaiting live person camera verification to calculate final risk score.
            </p>
          </div>
          <button
            onClick={() => setShowVerifyWidget(true)}
            className="btn-primary text-xs flex items-center gap-1.5 py-2 px-3.5 flex-shrink-0 font-semibold"
          >
            <Camera className="w-3.5 h-3.5" /> Complete Identity Verification
          </button>
        </div>
      )}

      {s.status === 'HIGH_RISK' && (
        <div className="flex items-center gap-3 bg-red-500/10 border border-red-500/40 rounded-xl px-5 py-4 animate-pulse-slow">
          <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0" />
          <div>
            <p className="text-sm font-bold text-red-400">HUMAN REVIEW REQUIRED</p>
            <p className="text-xs text-red-400/70 mt-0.5">
              This document has been flagged as high risk. Officer review is mandatory before any decision.
              This automated result does NOT constitute a final determination.
            </p>
          </div>
        </div>
      )}

      {s.status === 'SUSPICIOUS' && (
        <div className="flex items-center gap-3 bg-amber-500/10 border border-amber-500/30 rounded-xl px-5 py-3">
          <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0" />
          <div>
            <p className="text-sm font-bold text-amber-400">HUMAN REVIEW RECOMMENDED</p>
            <p className="text-xs text-amber-400/70 mt-0.5">
              Document has suspicious indicators or incomplete identity verification.
            </p>
          </div>
        </div>
      )}

      {/* ── Processing indicator ─────────────────────────────────────────────── */}
      {isProcessing && (
        <div className="glass-card p-6">
          <h2 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
            <Clock className="w-4 h-4 text-sentinel-primary animate-pulse" />
            Processing Pipeline
          </h2>
          <div className="space-y-2">
            {PIPELINE_STAGES.map((stage) => (
              <StageIndicator
                key={stage.key}
                stage={stage.label}
                status={isProcessing ? (stage.key === 'preprocessing' ? 'processing' : 'pending') : 'completed'}
              />
            ))}
          </div>
        </div>
      )}

      {!isProcessing && (
        <>
          {/* ── 1. Risk Score ────────────────────────────────────────────────── */}
          <RiskScoreSection screening={s} onTriggerVerification={() => setShowVerifyWidget(true)} />

          {/* ── 2. Extracted Document Data ───────────────────────────────────── */}
          <div className="glass-card p-6">
            <h2 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
              <BookOpen className="w-4 h-4 text-sentinel-primary" />
              Extracted Document Data
            </h2>
            <p className="text-xs text-gray-500 mb-3">
              Fields extracted from MRZ (machine-readable zone) and OCR (visual zone).
              Source labels indicate the extraction origin.
            </p>
            <ExtractedDocumentSection doc={doc} mrz={mrz} />
          </div>

          {/* ── 3. MRZ Analysis ──────────────────────────────────────────────── */}
          <CollapsibleSection
            title="MRZ Analysis"
            icon={Fingerprint}
            defaultOpen={true}
            badge={
              mrz?.mrz_detected ? (
                <span className={`text-xs font-mono ${mrz.all_check_digits_valid ? 'text-emerald-400' : 'text-red-400'}`}>
                  {mrz.mrz_format} · {mrz.all_check_digits_valid ? 'VALID' : 'CHECK DIGIT FAILURE'}
                </span>
              ) : (
                <span className="text-xs text-gray-500 font-mono">NOT DETECTED</span>
              )
            }
          >
            <MRZAnalysisSection mrz={mrz} />
          </CollapsibleSection>

          {/* ── 4. OCR / MRZ Consistency ─────────────────────────────────────── */}
          <CollapsibleSection
            title="OCR / MRZ Consistency"
            icon={GitCompare}
            defaultOpen={true}
            badge={
              consistency ? (
                <span className={`text-xs font-mono ${
                  Object.values(consistency).some(v => v === 'MISMATCH') ? 'text-amber-400' : 'text-emerald-400'
                }`}>
                  {Object.values(consistency).filter(v => v === 'MISMATCH').length} mismatch(es)
                </span>
              ) : null
            }
          >
            <ConsistencySection consistency={consistency} />
          </CollapsibleSection>

          {/* ── 5. Validation Checks ─────────────────────────────────────────── */}
          {validations.length > 0 && (
            <CollapsibleSection title="Validation Checks" icon={Shield} defaultOpen={false}
              badge={
                <span className="text-xs text-gray-500 font-mono">
                  {validations.filter(v => v.status === 'PASS').length}/{validations.length} passed
                </span>
              }
            >
              <div className="pt-4">
                {validations.map((v, i) => (
                  <ValidationRow key={i} check={v} />
                ))}
              </div>
            </CollapsibleSection>
          )}

          {/* ── 6. Tamper Detection ──────────────────────────────────────────── */}
          <CollapsibleSection title="Tamper Detection" icon={Eye}
            badge={tamper?.tamper_detected && <span className="text-xs text-red-400 font-mono">ANOMALY DETECTED</span>}
          >
            <TamperSection tamper={tamper} />
          </CollapsibleSection>

          {/* ── 7. Identity Verification Card ────────────────────────────────── */}
          <IdentityVerificationCard
            identity={identity}
            onTriggerVerification={() => setShowVerifyWidget(!showVerifyWidget)}
          />

          {/* ── 8. Live Person Camera / Liveness Verification (Exactly ONE camera component) ────────────────── */}
          {idStatus !== 'PASS' && (
            <div className="space-y-3" id="person-verification-section">
              <PersonVerificationSection
                screeningId={s.id}
                initialData={identity}
                onVerificationComplete={() => {
                  fetchScreening()
                }}
              />
            </div>
          )}

          {/* ── 9. Face Verification ─────────────────────────────────────────── */}
          <CollapsibleSection title="Face Verification" icon={Database}
            badge={face?.match !== undefined && (
              <span className={`text-xs font-mono ${face.match ? 'text-emerald-400' : face.face_detected_person ? 'text-red-400' : 'text-gray-500'}`}>
                {face.face_detected_person ? (face.match ? 'MATCH' : 'NO MATCH') : 'NO PERSON PHOTO'}
              </span>
            )}
          >
            <FaceSection face={face} />
          </CollapsibleSection>

          {/* ── 10. Risk Analysis Explained ──────────────────────────────────── */}
          {riskResult?.reasons?.length > 0 && (
            <CollapsibleSection title="Risk Analysis — Explained" icon={AlertTriangle} defaultOpen={true}>
              <div className="pt-4 space-y-2">
                {riskResult.reasons.map((r, i) => (
                  <RiskReasonCard key={i} reason={r} />
                ))}
              </div>
              {riskResult.weights_used && (
                <div className="mt-4 pt-3 border-t border-sentinel-border/30">
                  <p className="text-xs text-gray-500 mb-2 font-mono">Risk Weights Used:</p>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(riskResult.weights_used).map(([k, v]) => (
                      <span key={k} className="text-xs bg-sentinel-surface px-2 py-1 rounded border border-sentinel-border font-mono">
                        {k.toUpperCase()}: {v}%
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </CollapsibleSection>
          )}

          {/* ── 11 (bonus). Final Screening Decision ─────────────────────────── */}
          <div className="glass-card p-6">
            <h2 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
              <Shield className="w-4 h-4 text-sentinel-primary" />
              Final Screening Decision
            </h2>
            <FinalDecisionSection screening={s} riskResult={riskResult} />
          </div>

          {/* ── Audit Trail ───────────────────────────────────────────────────── */}
          {s.audit_logs?.length > 0 && (
            <CollapsibleSection title="Audit Trail" icon={Info}>
              <div className="pt-4 space-y-2">
                {s.audit_logs.map((log, i) => (
                  <div key={i} className="flex items-start gap-3 text-xs">
                    <span className="text-gray-600 font-mono flex-shrink-0 w-20">
                      {new Date(log.timestamp).toLocaleTimeString()}
                    </span>
                    <span className={`flex-shrink-0 w-16 font-mono ${log.status === 'SUCCESS' ? 'text-emerald-400' : 'text-red-400'}`}>
                      {log.status}
                    </span>
                    <span className="text-gray-400 font-mono">{log.action}</span>
                    {log.error_message && (
                      <span className="text-red-400 truncate">{log.error_message}</span>
                    )}
                  </div>
                ))}
              </div>
            </CollapsibleSection>
          )}
        </>
      )}
    </div>
  )
}
