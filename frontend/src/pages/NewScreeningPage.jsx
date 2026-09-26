import { useState, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Upload, FileImage, Scan, AlertCircle,
  X, CheckCircle, ChevronDown, ShieldCheck
} from 'lucide-react'
import { screeningsApi, identityApi } from '../services/api'
import { Spinner } from '../components/UIComponents'
import PersonVerificationSection from '../components/PersonVerificationSection'

const DOCUMENT_TYPES = [
  { value: 'passport', label: 'Passport' },
  { value: 'visa', label: 'Visa' },
  { value: 'national_id', label: 'National ID' },
  { value: 'permit', label: 'Permit' },
  { value: 'travel_authorization', label: 'Travel Authorization' },
]

function FileDropZone({ label, description, accept, file, onFile, id }) {
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef()

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setDragOver(false)
    const f = e.dataTransfer.files[0]
    if (f) onFile(f)
  }, [onFile])

  return (
    <div
      id={id}
      className={`relative border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-200
        ${dragOver
          ? 'border-sentinel-primary bg-sentinel-primary/10'
          : file
          ? 'border-emerald-500/50 bg-emerald-500/5'
          : 'border-sentinel-border hover:border-sentinel-primary/50 hover:bg-sentinel-primary/5'
        }`}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => e.target.files[0] && onFile(e.target.files[0])}
      />

      {file ? (
        <div className="space-y-2">
          <CheckCircle className="w-10 h-10 text-emerald-400 mx-auto" />
          <p className="text-sm font-medium text-emerald-400">{file.name}</p>
          <p className="text-xs text-gray-500">{(file.size / 1024).toFixed(1)} KB</p>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="w-14 h-14 rounded-xl border border-sentinel-border bg-sentinel-surface flex items-center justify-center mx-auto">
            <Upload className="w-6 h-6 text-gray-500" />
          </div>
          <div>
            <p className="text-sm font-medium text-gray-300">{label}</p>
            <p className="text-xs text-gray-500 mt-1">{description}</p>
            <p className="text-xs text-gray-600 mt-1">JPG · PNG · WEBP · Max 10MB</p>
          </div>
        </div>
      )}
    </div>
  )
}

export default function NewScreeningPage() {
  const [documentFile, setDocumentFile] = useState(null)
  const [personData, setPersonData] = useState(null) // { frames: [], isUpload: bool, file: File }
  const [documentType, setDocumentType] = useState('passport')
  const [loading, setLoading] = useState(false)
  const [statusMessage, setStatusMessage] = useState('')
  const [error, setError] = useState('')
  const navigate = useNavigate()

  const handleFramesCaptured = (data) => {
    setPersonData(data)
    setError('')
  }

  const handleSubmit = async (e) => {
    e.preventDefault()

    // Enforce dual-input requirement:
    // 1. Document image
    // 2. Person verification
    if (!documentFile) {
      setError('Document image is required.')
      return
    }

    if (!personData || !personData.frames || personData.frames.length === 0) {
      setError('Person verification is mandatory. Please capture camera frames or use the prototype upload fallback.')
      return
    }

    setLoading(true)
    setError('')
    setStatusMessage('Uploading document and initiating pipeline...')

    try {
      const formData = new FormData()
      formData.append('document_image', documentFile)
      if (personData.file) {
        formData.append('person_image', personData.file)
      }
      if (personData.frames && personData.frames.length > 0) {
        formData.append('person_frames_json', JSON.stringify(personData.frames))
      }
      formData.append('document_type', documentType)

      const { data } = await screeningsApi.create(formData)
      const screeningId = data.screening_id

      navigate(`/screening/${screeningId}`)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create screening')
      setLoading(false)
      setStatusMessage('')
    }
  }

  const bothInputsReady = documentFile && personData && personData.frames && personData.frames.length > 0

  return (
    <div className="p-6 max-w-3xl mx-auto animate-fade-in">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-100 flex items-center gap-2">
          New Document Screening
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Requires Document Image and Person Verification for AI-assisted identity authentication
        </p>
      </div>

      {/* Mandatory Dual-Input Banner */}
      <div className="bg-sentinel-surface/60 border border-sentinel-border rounded-xl p-4 mb-6">
        <div className="flex items-center gap-2 text-xs font-semibold text-gray-300 uppercase tracking-wider mb-2">
          <ShieldCheck className="w-4 h-4 text-sentinel-primary" />
          Mandatory Dual-Input Identity Pipeline
        </div>
        <div className="grid grid-cols-2 gap-3 text-xs">
          <div className={`p-2.5 rounded-lg border flex items-center gap-2 ${
            documentFile
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
              : 'bg-sentinel-bg border-sentinel-border/50 text-gray-400'
          }`}>
            <span className={`w-2 h-2 rounded-full ${documentFile ? 'bg-emerald-400' : 'bg-gray-600'}`} />
            <span>1. Document Image: {documentFile ? 'Provided ✓' : 'Required'}</span>
          </div>
          <div className={`p-2.5 rounded-lg border flex items-center gap-2 ${
            personData?.frames?.length > 0
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
              : 'bg-sentinel-bg border-sentinel-border/50 text-gray-400'
          }`}>
            <span className={`w-2 h-2 rounded-full ${personData?.frames?.length > 0 ? 'bg-emerald-400' : 'bg-gray-600'}`} />
            <span>2. Person Verification: {personData?.frames?.length > 0 ? 'Captured ✓' : 'Required'}</span>
          </div>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Document Type */}
        <div className="glass-card p-6">
          <label className="block text-xs font-medium text-gray-400 mb-3 uppercase tracking-wider">
            Document Type
          </label>
          <div className="relative">
            <select
              id="document-type-select"
              value={documentType}
              onChange={(e) => setDocumentType(e.target.value)}
              className="input-field appearance-none pr-10"
            >
              {DOCUMENT_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
            <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 pointer-events-none" />
          </div>
        </div>

        {/* 1. Document File Upload */}
        <div className="glass-card p-6 space-y-4">
          <h2 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
            <FileImage className="w-4 h-4 text-sentinel-primary" />
            1. Document Image
            <span className="text-red-400 text-xs font-medium">*Required</span>
          </h2>
          <FileDropZone
            id="document-upload-zone"
            label="Drop document image here or click to browse"
            description="Passport, ID card, visa, or other travel document"
            accept="image/jpeg,image/jpg,image/png,image/webp"
            file={documentFile}
            onFile={setDocumentFile}
          />
          {documentFile && (
            <button
              type="button"
              onClick={() => setDocumentFile(null)}
              className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-red-400 transition-colors"
            >
              <X className="w-3 h-3" /> Remove document image
            </button>
          )}
        </div>

        {/* 2. Person Verification Section */}
        <PersonVerificationSection
          onFramesCaptured={handleFramesCaptured}
          required={true}
        />

        {error && (
          <div className="flex items-center gap-2 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3">
            <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
            <span className="text-sm text-red-400">{error}</span>
          </div>
        )}

        <div className="flex gap-3 pt-2">
          <button
            type="button"
            onClick={() => navigate('/')}
            className="btn-secondary flex-1"
          >
            Cancel
          </button>
          <button
            id="start-screening-btn"
            type="submit"
            disabled={loading || !bothInputsReady}
            className="btn-primary flex-1 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed py-3 font-semibold"
          >
            {loading ? (
              <>
                <Spinner size="sm" />
                <span>{statusMessage || 'Processing...'}</span>
              </>
            ) : (
              <>
                <Scan className="w-4 h-4" />
                Start Full Screening
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  )
}
