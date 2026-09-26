import sys

path = '../frontend/src/pages/ScreeningDetailPage.jsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_mrz_start = 'function MRZAnalysisSection({ mrz }) {'
old_mrz_end = '// ─── Tamper Section'

idx_start = content.index(old_mrz_start)
idx_end = content.index(old_mrz_end)

new_mrz_and_doc = """function MRZAnalysisSection({ mrz }) {
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

"""

content = content[:idx_start] + new_mrz_and_doc + content[idx_end:]
print('MRZ & ExtractedDocument sections replaced')

# 2. Camera single instance rendering in main page
old_camera_part = """          {/* ── 8. Live Person Camera / Liveness Verification ────────────────── */}
          {(showVerifyWidget || idStatus !== 'PASS') && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  Live Person Camera Verification
                </span>
                <button
                  onClick={() => setShowVerifyWidget(false)}
                  className="text-xs text-gray-500 hover:text-gray-300"
                >
                  Hide Camera Widget
                </button>
              </div>
              <PersonVerificationSection
                screeningId={s.id}
                initialData={identity}
                onVerificationComplete={() => {
                  fetchScreening()
                  setShowVerifyWidget(false)
                }}
              />
            </div>
          )}"""

new_camera_part = """          {/* ── 8. Live Person Camera / Liveness Verification (Exactly ONE camera component) ────────────────── */}
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
          )}"""

if old_camera_part in content:
    content = content.replace(old_camera_part, new_camera_part, 1)
    print('Camera single rendering updated')
else:
    print('old_camera_part not found')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('ScreeningDetailPage.jsx successfully updated!')
