

































import { useState, useRef, useEffect, useCallback } from 'react'
import {
  Camera, RefreshCw, Upload, CheckCircle2, XCircle, AlertTriangle,
  ShieldCheck, AlertCircle, Video, VideoOff,
  Crosshair, Sliders, Info
} from 'lucide-react'
import { Spinner } from './UIComponents'
import { identityApi } from '../services/api'
import { faceDetectorService } from '../services/faceDetectorService'

/**
 * PersonVerificationSection
 * Handles browser camera stream, real-time MediaPipe face detection,
 * mirrored overlay canvas with bounding boxes, oval guide alignment checks,
 * multi-frame burst capture for liveness, prototype upload fallback,
 * and document face verification.
 */
export default function PersonVerificationSection({
  screeningId,
  onVerificationComplete,
  onFramesCaptured,
  required = true,
  initialData = null,
}) {
  // Single Unified Camera State Machine
  const [cameraState, setCameraState] = useState(
    initialData?.status === 'PASS' ? 'VERIFICATION_PASS' : 'CAMERA_REQUIRED'
  )
  const [cameraActive, setCameraActive] = useState(false)
  const [capturing, setCapturing] = useState(false)
  const [captureProgress, setCaptureProgress] = useState(0)
  const [capturedFrames, setCapturedFrames] = useState([])
  const [capturedPreview, setCapturedPreview] = useState(null)
  const [isUploadFallback, setIsUploadFallback] = useState(false)
  const [uploadedFile, setUploadedFile] = useState(null)
  const [cameraError, setCameraError] = useState('')
  const [verifying, setVerifying] = useState(false)

  // Face Detection & Quality States
  const [detectorStatus, setDetectorStatus] = useState('idle') // 'idle' | 'loading' | 'ready' | 'error'
  const [faceDetected, setFaceDetected] = useState(false)
  const [faceCount, setFaceCount] = useState(0)
  const [faceConfidence, setFaceConfidence] = useState(0)
  const [facePositionQuality, setFacePositionQuality] = useState('NONE') // 'NONE' | 'GOOD' | 'OFF_CENTER' | 'TOO_FAR' | 'TOO_CLOSE' | 'OUT_OF_FRAME' | 'MULTIPLE'
  const [faceQuality, setFaceQuality] = useState('NONE') // 'NONE' | 'GOOD' | 'POOR'
  const [faceFeedback, setFaceFeedback] = useState('Position face inside the oval and blink naturally')
  const [faceUiState, setFaceUiState] = useState('NO_FACE') // 'NO_FACE' | 'FACE_DETECTED' | 'POSITION_INSIDE_GUIDE' | 'FACE_POSITION_OK' | 'MULTIPLE_FACES' | ...
  const [videoDims, setVideoDims] = useState({ width: 640, height: 480 })
  const [debugHudVisible, setDebugHudVisible] = useState(false)

  // Verification Results
  const [verificationResult, setVerificationResult] = useState(initialData)

  // Progress states: 'idle' | 'ready' | 'capturing' | 'checking_liveness' | 'detecting_face' | 'comparing' | 'complete' | 'failed'
  const [pipelineState, setPipelineState] = useState(initialData ? 'complete' : 'idle')

  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const containerRef = useRef(null)
  const streamRef = useRef(null)
  const fileInputRef = useRef(null)
  const animFrameRef = useRef(null)
  const detectionLoopRef = useRef(null)
  const isDetectingRef = useRef(false)
  const lastDetectTimeRef = useRef(0)
  const evaluatedFaceRef = useRef(null)

  // Initialize face detector on component mount or camera start
  const ensureDetectorReady = useCallback(async () => {
    if (detectorStatus === 'ready') return true
    try {
      setDetectorStatus('loading')
      await faceDetectorService.init()
      setDetectorStatus('ready')
      return true
    } catch (err) {
      console.error('[SentinelID Face] Failed to initialize detector:', err)
      setDetectorStatus('error')
      return false
    }
  }, [detectorStatus])

  // Clear overlay canvas
  const clearCanvas = useCallback(() => {
    if (canvasRef.current) {
      const ctx = canvasRef.current.getContext('2d')
      if (ctx) {
        ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height)
      }
    }
  }, [])

  // Draw bounding box, corner brackets, and tags on canvas
  const drawBoundingBox = useCallback((ctx, face, color, label, isGood) => {
    const { mirroredX: x, dispY: y, boxW: w, boxH: h, keypoints } = face
    const cornerLength = Math.min(22, w * 0.22, h * 0.22)
    const lineWidth = 3

    ctx.save()

    // 1. Subtle translucent fill
    ctx.fillStyle = isGood ? 'rgba(16, 185, 129, 0.08)' : 'rgba(245, 158, 11, 0.08)'
    ctx.fillRect(x, y, w, h)

    // 2. Faint dashed border
    ctx.strokeStyle = color
    ctx.globalAlpha = 0.35
    ctx.lineWidth = 1
    ctx.setLineDash([4, 4])
    ctx.strokeRect(x, y, w, h)
    ctx.setLineDash([])
    ctx.globalAlpha = 1.0

    // 3. 4 Corner brackets: ┌ ┐ └ ┘
    ctx.lineWidth = lineWidth
    ctx.strokeStyle = color
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'

    // Top-Left ┌
    ctx.beginPath()
    ctx.moveTo(x, y + cornerLength)
    ctx.lineTo(x, y)
    ctx.lineTo(x + cornerLength, y)
    ctx.stroke()

    // Top-Right ┐
    ctx.beginPath()
    ctx.moveTo(x + w - cornerLength, y)
    ctx.lineTo(x + w, y)
    ctx.lineTo(x + w, y + cornerLength)
    ctx.stroke()

    // Bottom-Left └
    ctx.beginPath()
    ctx.moveTo(x, y + h - cornerLength)
    ctx.lineTo(x, y + h)
    ctx.lineTo(x + cornerLength, y + h)
    ctx.stroke()

    // Bottom-Right ┘
    ctx.beginPath()
    ctx.moveTo(x + w - cornerLength, y + h)
    ctx.lineTo(x + w, y + h)
    ctx.lineTo(x + w, y + h - cornerLength)
    ctx.stroke()

    // 4. Draw keypoints (eyes, nose, mouth) if available
    if (keypoints && keypoints.length > 0) {
      ctx.fillStyle = color
      keypoints.forEach((kp) => {
        ctx.beginPath()
        ctx.arc(kp.x, kp.y, 2.5, 0, Math.PI * 2)
        ctx.fill()
      })
    }

    // 5. Draw status tag pill above bounding box
    ctx.font = 'bold 10px "JetBrains Mono", monospace'
    const textWidth = ctx.measureText(label).width
    const pillPadding = 8
    const pillHeight = 20
    const pillWidth = textWidth + pillPadding * 2
    const pillX = Math.max(4, Math.min(x + (w - pillWidth) / 2, ctx.canvas.width - pillWidth - 4))
    const pillY = Math.max(4, y - pillHeight - 6)

    // Pill background
    ctx.fillStyle = 'rgba(8, 12, 20, 0.90)'
    ctx.strokeStyle = color
    ctx.lineWidth = 1.2
    ctx.beginPath()
    if (ctx.roundRect) {
      ctx.roundRect(pillX, pillY, pillWidth, pillHeight, 5)
    } else {
      ctx.rect(pillX, pillY, pillWidth, pillHeight)
    }
    ctx.fill()
    ctx.stroke()

    // Pill text
    ctx.fillStyle = color
    ctx.fillText(label, pillX + pillPadding, pillY + 14)

    ctx.restore()
  }, [])

  // Process live video frame through face detector
  const processFrame = useCallback(
    (timestamp) => {
      const video = videoRef.current
      const canvas = canvasRef.current
      const container = containerRef.current
      if (!video || !canvas || !container) return

      // Ensure playback is not stalled in paused state
      if (video.paused && !video.ended) {
        video.play().catch(() => {})
      }

      if (video.readyState < 2) return

      // Synchronize canvas dimensions with rendered container
      const displayWidth = container.clientWidth
      const displayHeight = container.clientHeight
      if (canvas.width !== displayWidth || canvas.height !== displayHeight) {
        canvas.width = displayWidth
        canvas.height = displayHeight
      }

      const ctx = canvas.getContext('2d')
      if (!ctx) return

      const detections = faceDetectorService.detectVideo(video, timestamp)
      const count = detections.length

      if (count === 0) {
        clearCanvas()
        setFaceDetected(false)
        setFaceCount(0)
        setFaceConfidence(0)
        setFacePositionQuality('NONE')
        setFaceQuality('NONE')
        setFaceFeedback('No face detected — please look directly at the camera')
        setFaceUiState('NO_FACE')
        setCameraState((prev) => (prev === 'CAMERA_ACTIVE' || prev === 'FACE_DETECTED' ? 'NO_FACE' : prev))
        evaluatedFaceRef.current = null
        faceDetectorService.logState(0, 'NONE', { width: video.videoWidth, height: video.videoHeight })
        return
      }

      if (count > 1) {
        ctx.clearRect(0, 0, displayWidth, displayHeight)
        detections.forEach((det, idx) => {
          const evalSingle = faceDetectorService.evaluateFace(
            det,
            video.videoWidth,
            video.videoHeight,
            displayWidth,
            displayHeight
          )
          drawBoundingBox(ctx, evalSingle, '#ef4444', `MULTIPLE FACES DETECTED (${idx + 1})`, false)
        })

        setFaceDetected(true)
        setFaceCount(count)
        setFaceConfidence(detections[0]?.categories?.[0]?.score || 0)
        setFacePositionQuality('MULTIPLE')
        setFaceQuality('POOR')
        setFaceFeedback('Multiple faces detected — only one person permitted')
        setFaceUiState('MULTIPLE_FACES')
        evaluatedFaceRef.current = null
        faceDetectorService.logState(count, 'MULTIPLE', { width: video.videoWidth, height: video.videoHeight })
        return
      }

      // Exactly 1 face detected
      const evaluated = faceDetectorService.evaluateFace(
        detections[0],
        video.videoWidth,
        video.videoHeight,
        displayWidth,
        displayHeight,
        { width: 192, height: 256 } // matches oval guide w-48 (192px), h-64 (256px)
      )

      evaluatedFaceRef.current = evaluated

      // Draw bounding box
      ctx.clearRect(0, 0, displayWidth, displayHeight)
      const isGood = evaluated.isPositionOk
      const color = isGood ? '#10b981' : '#f59e0b'
      const label = isGood
        ? `FACE POSITION OK • ${Math.round(evaluated.confidence * 100)}%`
        : `FACE DETECTED • ${Math.round(evaluated.confidence * 100)}%`

      drawBoundingBox(ctx, evaluated, color, label, isGood)

      setFaceDetected(true)
      setFaceCount(1)
      setFaceConfidence(evaluated.confidence)
      setFacePositionQuality(evaluated.facePosition)
      setFaceQuality(evaluated.faceQuality)
      setFaceFeedback(evaluated.feedback)
      setFaceUiState(evaluated.uiState)
      setCameraState((prev) => (prev === 'CAMERA_ACTIVE' || prev === 'NO_FACE' ? 'FACE_DETECTED' : prev))

      faceDetectorService.logState(1, evaluated.facePosition, { width: video.videoWidth, height: video.videoHeight })
    },
    [clearCanvas, drawBoundingBox]
  )

  // Stop single detection loop
  const stopDetectionLoop = useCallback(() => {
    if (detectionLoopRef.current) {
      cancelAnimationFrame(detectionLoopRef.current)
      detectionLoopRef.current = null
    }
  }, [])

  // Start continuous detection frame loop with single-instance guard
  const startDetectionLoop = useCallback(() => {
    if (detectionLoopRef.current) {
      return
    }
    console.log('[CAMERA] Detector started')

    const loop = (time) => {
      if (!streamRef.current) {
        detectionLoopRef.current = null
        return
      }
      if (time - lastDetectTimeRef.current >= 120 && !isDetectingRef.current) {
        isDetectingRef.current = true
        lastDetectTimeRef.current = time
        try {
          processFrame(time)
        } catch (e) {
          console.warn('[SentinelID Face] Frame processing error:', e)
        } finally {
          isDetectingRef.current = false
        }
      }
      detectionLoopRef.current = requestAnimationFrame(loop)
    }

    detectionLoopRef.current = requestAnimationFrame(loop)
  }, [processFrame])

  // Attach active MediaStream to video element and initiate playback
  const attachStreamToVideo = useCallback((videoEl) => {
    if (!videoEl || !streamRef.current) return
    if (videoEl.srcObject !== streamRef.current) {
      videoEl.srcObject = streamRef.current
    }
    videoEl.play().catch((err) => {
      console.warn('[SentinelID Face] video.play() error:', err)
    })
  }, [])

  // Callback ref ensuring video element is immediately wired up on DOM mount
  const setVideoRef = useCallback(
    (node) => {
      videoRef.current = node
      if (node && streamRef.current) {
        attachStreamToVideo(node)
      }
    },
    [attachStreamToVideo]
  )

  // Stop camera stream & frame loop
  const stopCamera = useCallback(() => {
    stopDetectionLoop()
    clearCanvas()

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
      console.log('[CAMERA] Stream stopped')
    }

    if (videoRef.current) {
      videoRef.current.srcObject = null
    }

    setCameraActive(false)
    setFaceDetected(false)
    setFaceCount(0)
    setFacePositionQuality('NONE')
    setFaceQuality('NONE')
    setFaceFeedback('Position face inside the oval and blink naturally')
    setFaceUiState('NO_FACE')
    evaluatedFaceRef.current = null
  }, [clearCanvas, stopDetectionLoop])

  // Start browser camera with idempotent guard
  const startCamera = async () => {
    if (streamRef.current) {
      return
    }
    setCameraError('')
    setIsUploadFallback(false)
    setUploadedFile(null)
    setCameraState('CAMERA_STARTING')
    try {
      await ensureDetectorReady()

      console.log('[CAMERA] getUserMedia called')
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 640 },
          height: { ideal: 480 },
          facingMode: 'user',
        },
        audio: false,
      })

      console.log('[CAMERA] Stream created')
      streamRef.current = stream
      setCameraActive(true)
      setCameraState('CAMERA_ACTIVE')
      setPipelineState('ready')

      if (videoRef.current) {
        attachStreamToVideo(videoRef.current)
      }
    } catch (err) {
      console.error('Camera access error:', err)
      setCameraError(
        'Unable to access camera. Please allow camera permissions in your browser or use the prototype upload fallback.'
      )
      setCameraActive(false)
      setCameraState('CAMERA_ERROR')
    }
  }

  // Handle video metadata or loaded data
  const handleVideoMetadata = () => {
    if (videoRef.current) {
      const w = videoRef.current.videoWidth || 640
      const h = videoRef.current.videoHeight || 480
      setVideoDims({ width: w, height: h })
      console.log('[CAMERA] Video ready')
      startDetectionLoop()
    }
  }

  // Ensure stream attachment and detection loop run whenever cameraActive is true
  useEffect(() => {
    if (cameraActive && streamRef.current && videoRef.current) {
      attachStreamToVideo(videoRef.current)
      startDetectionLoop()
    }
  }, [cameraActive, attachStreamToVideo, startDetectionLoop])

  // Camera Component Mount & Unmount lifecycle
  useEffect(() => {
    console.log('[CAMERA] Component mounted')
    return () => {
      console.log('[CAMERA] Component unmounted')
      stopCamera()
    }
  }, [stopCamera])

  // Burst capture multiple frames for temporal liveness analysis
  const captureBurstFrames = async () => {
    if (!videoRef.current || !cameraActive) return
    if (!faceDetected || faceCount !== 1 || !evaluatedFaceRef.current?.isPositionOk) {
      console.warn('[SentinelID Face] Capture blocked: Face position not OK')
      return
    }

    console.log('[CAMERA] Liveness started')
    setCameraState('LIVENESS_PROCESSING')
    setCapturing(true)
    setCaptureProgress(0)
    setPipelineState('capturing')
    const frames = []
    const frameDetections = []
    const totalFrames = 6
    const intervalMs = 250 // capture every 250ms (~1.5s total)

    const canvas = document.createElement('canvas')
    canvas.width = 640
    canvas.height = 480
    const ctx = canvas.getContext('2d')

    for (let i = 0; i < totalFrames; i++) {
      ctx.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height)
      const dataUrl = canvas.toDataURL('image/jpeg', 0.88)
      frames.push(dataUrl)

      // Record detection snapshot for client temporal verification
      const rawDetections = faceDetectorService.detectVideo(videoRef.current, performance.now())
      if (rawDetections.length === 1 && containerRef.current) {
        const evalFace = faceDetectorService.evaluateFace(
          rawDetections[0],
          videoRef.current.videoWidth,
          videoRef.current.videoHeight,
          containerRef.current.clientWidth,
          containerRef.current.clientHeight
        )
        frameDetections.push({ faceCount: 1, face: evalFace })
      } else {
        frameDetections.push({ faceCount: rawDetections.length, face: null })
      }

      setCaptureProgress(Math.round(((i + 1) / totalFrames) * 100))
      if (i === 0) {
        setCapturedPreview(dataUrl)
      }
      await new Promise((r) => setTimeout(r, intervalMs))
    }

    // Client temporal liveness analysis
    const clientLiveness = faceDetectorService.analyzeTemporalLiveness(frameDetections)
    console.log('[SentinelID Face] Client temporal liveness analysis result:', clientLiveness)

    setCapturedFrames(frames)
    setCapturing(false)
    stopCamera()

    if (onFramesCaptured) {
      onFramesCaptured({ frames, isUpload: false, clientLiveness })
    }

    // If screeningId is already known, trigger live verification immediately
    if (screeningId) {
      runVerification(frames, false, clientLiveness)
    } else {
      setPipelineState('complete')
    }
  }

  // Handle Prototype Upload Fallback
  const handleFileUpload = (e) => {
    const file = e.target.files[0]
    if (!file) return

    stopCamera()
    setIsUploadFallback(true)
    setUploadedFile(file)
    setCameraError('')

    const reader = new FileReader()
    reader.onload = (event) => {
      const dataUrl = event.target.result
      setCapturedPreview(dataUrl)
      setCapturedFrames([dataUrl])

      if (onFramesCaptured) {
        onFramesCaptured({ frames: [dataUrl], isUpload: true, file })
      }

      if (screeningId) {
        runVerification([dataUrl], true)
      } else {
        setPipelineState('complete')
      }
    }
    reader.readAsDataURL(file)
  }

  // Retake
  const handleRetake = () => {
    setCapturedFrames([])
    setCapturedPreview(null)
    setIsUploadFallback(false)
    setUploadedFile(null)
    setVerificationResult(null)
    setPipelineState('idle')
    startCamera()
  }

  // Run live verification through API
  const runVerification = async (frames, isUpload = false, clientLiveness = null) => {
    if (!screeningId || frames.length === 0) return

    setVerifying(true)
    setPipelineState('checking_liveness')

    try {
      // Step 1: Liveness Check stage
      await new Promise((r) => setTimeout(r, 400))
      setPipelineState('detecting_face')

      // Step 2: Full Verification API call
      await new Promise((r) => setTimeout(r, 400))
      setPipelineState('comparing')

      setCameraState('FACE_MATCHING')
      const { data } = await identityApi.verify(screeningId, {
        frames,
        is_upload: isUpload,
        client_liveness: clientLiveness,
      })

      setVerificationResult(data.identity_verification)
      const passed = data.identity_verification?.status === 'PASS'
      setPipelineState(passed ? 'complete' : 'failed')
      setCameraState(passed ? 'VERIFICATION_PASS' : 'VERIFICATION_FAIL')

      if (onVerificationComplete) {
        onVerificationComplete(data)
      }
    } catch (err) {
      console.error('Verification failed:', err)
      setPipelineState('failed')
      setCameraError(err.response?.data?.detail || 'Identity verification request failed')
    } finally {
      setVerifying(false)
    }
  }

  const identityStatus = verificationResult?.status || verificationResult?.identity_status || 'INCOMPLETE'
  const liveness = verificationResult?.liveness
  const faceMatch = verificationResult?.face_match
  const docFace = verificationResult?.document_face
  const personFace = verificationResult?.person_face

  // Determine if frame capture is allowed
  const facePositionOk = faceDetected && faceCount === 1 && facePositionQuality === 'GOOD'
  const canCapture = cameraActive && facePositionOk && !capturing

  // Dynamic Live Status Indicator (Section 9)
  let statusBadgeText = 'NO FACE DETECTED'
  let statusBadgeColor = 'text-red-400'
  let statusDotColor = 'bg-red-500'
  let statusDotPulse = false

  if (capturing || pipelineState === 'checking_liveness') {
    statusBadgeText = 'LIVENESS CHECKING'
    statusBadgeColor = 'text-sentinel-primary'
    statusDotColor = 'bg-sentinel-primary'
    statusDotPulse = true
  } else if (pipelineState === 'complete' && identityStatus === 'PASS') {
    statusBadgeText = 'LIVENESS PASSED'
    statusBadgeColor = 'text-emerald-400'
    statusDotColor = 'bg-emerald-400'
  } else if (faceCount > 1) {
    statusBadgeText = 'MULTIPLE FACES DETECTED'
    statusBadgeColor = 'text-red-400'
    statusDotColor = 'bg-red-500'
  } else if (facePositionOk) {
    statusBadgeText = 'FACE POSITION OK'
    statusBadgeColor = 'text-emerald-400'
    statusDotColor = 'bg-emerald-400'
  } else if (faceDetected) {
    statusBadgeText = 'FACE DETECTED'
    statusBadgeColor = 'text-amber-400'
    statusDotColor = 'bg-amber-400'
  }

  return (
    <div className="glass-card p-6 space-y-5 animate-fade-in" id="person-verification-card">
      <div className="flex items-center justify-between border-b border-sentinel-border/40 pb-4">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-sentinel-primary/10 border border-sentinel-primary/20 text-sentinel-primary">
            <Camera className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-gray-100 flex items-center gap-2">
              Person Verification
              {required && (
                <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-sentinel-primary/15 text-sentinel-primary border border-sentinel-primary/30">
                  Required
                </span>
              )}
            </h2>
            <p className="text-xs text-gray-500">
              Live camera capture for real-time face detection, temporal liveness, and document matching
            </p>
          </div>
        </div>

        {capturedPreview && (
          <button
            type="button"
            onClick={handleRetake}
            className="btn-secondary text-xs flex items-center gap-1.5 py-1.5 px-3"
            id="retake-camera-btn"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Retake
          </button>
        )}
      </div>

      {/* Progress State Tracker */}
      <div className="bg-sentinel-surface/40 rounded-xl p-3 border border-sentinel-border/40">
        <div className="flex items-center justify-between text-xs text-gray-400 font-mono mb-2">
          <span>PIPELINE PROGRESS</span>
          <span className="uppercase text-sentinel-primary font-bold">
            {pipelineState === 'idle' && 'Waiting'}
            {pipelineState === 'ready' && (facePositionOk ? 'Ready for Liveness' : faceDetected ? 'Face Detected' : 'Camera Active')}
            {pipelineState === 'capturing' && `Capturing Frames (${captureProgress}%)`}
            {pipelineState === 'checking_liveness' && 'Checking Liveness...'}
            {pipelineState === 'detecting_face' && 'Detecting Face...'}
            {pipelineState === 'comparing' && 'Comparing With Document...'}
            {pipelineState === 'complete' && (identityStatus === 'PASS' ? 'Verified ✓' : 'Evaluated')}
            {pipelineState === 'failed' && 'Failed ✗'}
          </span>
        </div>
        <div className="w-full bg-sentinel-bg rounded-full h-1.5 overflow-hidden">
          <div
            className={`h-full transition-all duration-300 ${
              pipelineState === 'failed'
                ? 'bg-red-500'
                : identityStatus === 'PASS'
                ? 'bg-emerald-400'
                : 'bg-sentinel-primary'
            }`}
            style={{
              width:
                pipelineState === 'idle'
                  ? '5%'
                  : pipelineState === 'ready'
                  ? facePositionOk ? '35%' : '20%'
                  : pipelineState === 'capturing'
                  ? '50%'
                  : pipelineState === 'checking_liveness'
                  ? '70%'
                  : pipelineState === 'detecting_face'
                  ? '85%'
                  : pipelineState === 'comparing'
                  ? '95%'
                  : '100%',
            }}
          />
        </div>
      </div>

      {/* Camera Preview / Video Area */}
      <div className="relative rounded-xl overflow-hidden bg-sentinel-bg border border-sentinel-border min-h-[260px] flex items-center justify-center">
        {cameraActive ? (
          <div
            ref={containerRef}
            className="relative w-full aspect-video max-h-[320px] bg-black flex items-center justify-center overflow-hidden"
          >
            {/* Live Video (Mirrored for natural webcam preview) */}
            <video
              ref={setVideoRef}
              autoPlay
              playsInline
              muted
              onLoadedMetadata={handleVideoMetadata}
              onLoadedData={handleVideoMetadata}
              onCanPlay={() => {
                if (videoRef.current && videoRef.current.paused) {
                  videoRef.current.play().catch(() => {})
                }
              }}
              className="w-full h-full object-cover mirror relative z-[1]"
              style={{
                border: '3px solid #00d4ff',
                boxShadow: '0 0 15px rgba(0, 212, 255, 0.4)',
              }}
            />

            {/* Real-time Bounding Box Canvas Overlay (Overlaid over live video) */}
            <canvas
              ref={canvasRef}
              className="absolute inset-0 w-full h-full pointer-events-none z-10"
            />

            {/* Facial alignment oval guide overlay */}
            <div className="absolute inset-0 pointer-events-none flex items-center justify-center z-10">
              <div
                className={`w-48 h-64 border-2 rounded-full transition-all duration-300 ${
                  !faceDetected
                    ? 'border-dashed border-sentinel-primary/40 animate-pulse-slow'
                    : faceCount > 1
                    ? 'border-dashed border-red-500 shadow-[0_0_15px_rgba(239,68,68,0.4)]'
                    : facePositionOk
                    ? 'border-solid border-emerald-400 shadow-[0_0_20px_rgba(52,211,153,0.45)]'
                    : 'border-dashed border-amber-400/80 shadow-[0_0_15px_rgba(245,158,11,0.3)]'
                }`}
              />
            </div>

            {/* Live Camera & Dynamic Face Status Badge (Section 9) */}
            <div className="absolute top-3 left-3 flex items-center gap-2 bg-black/80 backdrop-blur-md px-3 py-1.5 rounded-full text-[11px] font-mono border border-sentinel-border/80 shadow-lg z-20">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-gray-300 font-semibold tracking-wide">CAMERA ACTIVE</span>
              <span className="text-gray-600">|</span>
              <span className={`font-bold flex items-center gap-1.5 ${statusBadgeColor}`}>
                <span className={`w-2 h-2 rounded-full ${statusDotColor} ${statusDotPulse ? 'animate-ping' : ''}`} />
                {statusBadgeText}
              </span>
            </div>

            {/* Debug HUD Toggle & Panel (Section 12) */}
            <div className="absolute top-3 right-3 z-20 flex flex-col items-end gap-1">
              <button
                type="button"
                onClick={() => setDebugHudVisible(!debugHudVisible)}
                className="bg-black/75 hover:bg-black/90 backdrop-blur px-2.5 py-1 rounded text-[10px] font-mono text-gray-400 hover:text-gray-200 border border-sentinel-border/60 transition-colors flex items-center gap-1 shadow-md"
              >
                <Sliders className="w-3 h-3 text-sentinel-primary" />
                <span>{debugHudVisible ? 'Hide Debug' : 'Debug HUD'}</span>
              </button>

              {debugHudVisible && (
                <div className="bg-black/90 backdrop-blur-md border border-sentinel-primary/30 p-2.5 rounded-lg text-[10px] font-mono text-gray-300 space-y-1 shadow-2xl text-left min-w-[200px] animate-fade-in">
                  <div className="text-sentinel-primary font-bold border-b border-sentinel-border pb-1 flex justify-between items-center">
                    <span>SentinelID Face HUD</span>
                    <span className="text-[9px] px-1 py-0.2 bg-sentinel-primary/20 text-sentinel-primary rounded">DEV</span>
                  </div>
                  <div>Camera: <span className="text-emerald-400 font-bold">ACTIVE</span></div>
                  <div>Video dimensions: <span className="text-gray-100">{videoDims.width} × {videoDims.height}</span></div>
                  <div>Face detector: <span className={detectorStatus === 'ready' ? 'text-emerald-400 font-bold' : 'text-amber-400'}>{detectorStatus.toUpperCase()} (MediaPipe)</span></div>
                  <div>Faces detected: <span className={faceCount === 1 ? 'text-emerald-400 font-bold' : faceCount > 1 ? 'text-red-400 font-bold' : 'text-gray-400'}>{faceCount}</span></div>
                  <div>Face confidence: <span className="text-gray-100">{faceCount > 0 ? `${(faceConfidence * 100).toFixed(0)}%` : '—'}</span></div>
                  <div>Face position: <span className={facePositionOk ? 'text-emerald-400 font-bold' : 'text-amber-400'}>{facePositionQuality}</span></div>
                  <div>Face quality: <span className={faceQuality === 'GOOD' ? 'text-emerald-400 font-bold' : 'text-amber-400'}>{faceQuality}</span></div>
                </div>
              )}
            </div>

            {/* Instruction / Feedback Banner (Section 5 & 6) */}
            <div className="absolute bottom-3 inset-x-3 text-center pointer-events-none z-20">
              <span
                className={`px-3.5 py-1.5 rounded-lg text-xs backdrop-blur-md font-medium inline-flex items-center gap-1.5 shadow-lg border transition-colors ${
                  facePositionOk
                    ? 'bg-emerald-950/85 text-emerald-200 border-emerald-500/40'
                    : faceDetected && faceCount === 1
                    ? 'bg-amber-950/85 text-amber-200 border-amber-500/40'
                    : faceCount > 1
                    ? 'bg-red-950/85 text-red-200 border-red-500/40'
                    : 'bg-black/80 text-gray-300 border-sentinel-border/50'
                }`}
              >
                {facePositionOk ? (
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                ) : faceDetected && faceCount === 1 ? (
                  <Crosshair className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />
                ) : faceCount > 1 ? (
                  <AlertTriangle className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />
                ) : (
                  <Info className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
                )}
                <span>{faceFeedback}</span>
              </span>
            </div>
          </div>
        ) : capturedPreview ? (
          <div className="relative w-full aspect-video max-h-[300px] bg-black flex items-center justify-center">
            <img
              src={capturedPreview}
              alt="Person verification capture"
              className="w-full h-full object-contain"
            />
            {isUploadFallback && (
              <div className="absolute top-3 right-3 bg-amber-500/20 border border-amber-500/40 text-amber-300 text-xs px-2.5 py-1 rounded-md font-medium">
                Prototype Image Upload
              </div>
            )}
          </div>
        ) : (
          <div className="text-center p-8 space-y-4 max-w-sm">
            <div className="w-16 h-16 rounded-2xl bg-sentinel-surface border border-sentinel-border flex items-center justify-center mx-auto text-gray-500">
              <Video className="w-8 h-8" />
            </div>
            <div>
              <p className="text-sm font-semibold text-gray-200">
                Camera Verification Required
              </p>
              <p className="text-xs text-gray-500 mt-1">
                Real-time AI face detection and multi-frame temporal liveness analysis are required for identity verification.
              </p>
            </div>
            <button
              type="button"
              onClick={startCamera}
              className="btn-primary text-xs py-2 px-5 inline-flex items-center gap-2"
              id="start-camera-btn"
            >
              <Camera className="w-4 h-4" /> Start Camera
            </button>
          </div>
        )}

        {/* Capturing overlay */}
        {capturing && (
          <div className="absolute inset-0 bg-black/80 backdrop-blur-sm flex flex-col items-center justify-center text-center p-6 space-y-3 z-30">
            <Spinner size="lg" />
            <p className="text-sm font-semibold text-white">Analyzing Temporal Liveness...</p>
            <p className="text-xs text-gray-400 font-mono">Capturing frame sequence: {captureProgress}%</p>
            <p className="text-xs text-sentinel-primary animate-pulse">Please stay still and blink naturally</p>
          </div>
        )}
      </div>



      {/* Action Buttons & Guidance (Section 10) */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
        <div className="flex flex-wrap items-center gap-3">
          {cameraActive && (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={captureBurstFrames}
                disabled={!canCapture}
                className={`btn-primary flex items-center gap-2 text-xs py-2 px-4 transition-all duration-200 ${
                  !canCapture ? 'opacity-50 cursor-not-allowed hover:bg-sentinel-primary' : ''
                }`}
                id="capture-image-btn"
                title={
                  !faceDetected
                    ? 'No face detected in video stream'
                    : faceCount > 1
                    ? 'Only one person should be visible'
                    : !facePositionOk
                    ? faceFeedback
                    : 'Click to capture verification frames'
                }
              >
                <Camera className="w-4 h-4" />
                Capture Verification Frames
              </button>

              {!canCapture && !capturing && (
                <span className="text-[11px] text-amber-400/90 font-mono bg-amber-500/10 border border-amber-500/25 px-2.5 py-1 rounded-md">
                  {!faceDetected
                    ? 'Waiting for face...'
                    : faceCount > 1
                    ? 'Only 1 person allowed'
                    : faceFeedback}
                </span>
              )}
            </div>
          )}

          {cameraActive && (
            <button
              type="button"
              onClick={stopCamera}
              className="btn-secondary text-xs py-2 px-3 flex items-center gap-1.5"
            >
              <VideoOff className="w-3.5 h-3.5" /> Stop Preview
            </button>
          )}
        </div>

        {/* Development Fallback Upload */}
        <div className="flex items-center gap-2">
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileUpload}
            accept="image/jpeg,image/png,image/webp"
            className="hidden"
            id="person-file-input"
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="text-xs text-gray-400 hover:text-gray-200 transition-colors flex items-center gap-1.5 py-1 px-2.5 rounded-lg border border-sentinel-border/50 hover:bg-sentinel-surface"
            id="upload-fallback-btn"
          >
            <Upload className="w-3 h-3 text-gray-500" />
            <span>Upload verification image (Dev Fallback)</span>
          </button>
        </div>
      </div>

      {/* Security Rule Warning for Upload Fallback */}
      {isUploadFallback && (
        <div className="flex items-start gap-2.5 bg-amber-500/10 border border-amber-500/30 rounded-xl p-3.5">
          <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
          <div className="text-xs text-amber-300/90 leading-relaxed">
            <span className="font-semibold text-amber-200">Security Rule Enforced: </span>
            A single uploaded photograph cannot establish temporal liveness. Liveness is marked as{' '}
            <strong className="font-mono text-amber-200">INCONCLUSIVE</strong>, and identity verification will not PASS until live camera frames are verified.
          </div>
        </div>
      )}

      {cameraError && (
        <div className="flex items-center gap-2 bg-red-500/10 border border-red-500/30 rounded-xl p-3 text-xs text-red-400">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{cameraError}</span>
        </div>
      )}

      {/* Live Verification Status Cards */}
      {verificationResult && (
        <div className="mt-4 pt-4 border-t border-sentinel-border/40 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-gray-300 uppercase tracking-wider flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-sentinel-primary" />
              Identity Verification Status
            </span>
            <span
              className={`text-xs px-2.5 py-0.5 rounded-full font-mono font-bold ${
                identityStatus === 'PASS'
                  ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                  : identityStatus === 'INCOMPLETE'
                  ? 'bg-gray-500/20 text-gray-400 border border-gray-500/40'
                  : 'bg-red-500/20 text-red-400 border border-red-500/40'
              }`}
            >
              {identityStatus || 'INCOMPLETE'}
            </span>
          </div>

          {/* Metric Breakdown Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {/* 1. Liveness Status */}
            <div className="bg-sentinel-surface/50 rounded-xl p-3 border border-sentinel-border/30">
              <p className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">Liveness Status</p>
              <div className="flex items-center gap-1.5">
                {liveness?.status === 'PASS' ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                ) : liveness?.status === 'INCONCLUSIVE' ? (
                  <AlertTriangle className="w-4 h-4 text-amber-400" />
                ) : (
                  <XCircle className="w-4 h-4 text-red-400" />
                )}
                <span
                  className={`text-sm font-bold font-mono ${
                    liveness?.status === 'PASS'
                      ? 'text-emerald-400'
                      : liveness?.status === 'INCONCLUSIVE'
                      ? 'text-amber-400'
                      : 'text-red-400'
                  }`}
                >
                  {liveness?.status || 'NOT RUN'}
                </span>
              </div>
              <p className="text-[10px] text-gray-600 mt-1">
                {liveness?.confidence ? `Confidence: ${(liveness.confidence * 100).toFixed(0)}%` : 'Temporal frame check'}
              </p>
            </div>

            {/* 2. Face Similarity */}
            <div className="bg-sentinel-surface/50 rounded-xl p-3 border border-sentinel-border/30">
              <p className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">Face Similarity</p>
              <div className="flex items-center gap-1.5">
                <span
                  className={`text-sm font-bold font-mono ${
                    faceMatch?.status === 'PASS' ? 'text-emerald-400' : 'text-red-400'
                  }`}
                >
                  {faceMatch?.similarity !== undefined
                    ? `${(faceMatch.similarity * 100).toFixed(1)}%`
                    : '—'}
                </span>
                <span className="text-[10px] text-gray-500">
                  (Min: {((faceMatch?.threshold || 0.6) * 100).toFixed(0)}%)
                </span>
              </div>
              <p className="text-[10px] text-gray-600 mt-1">
                Cosine embedding distance
              </p>
            </div>

            {/* 3. Face Match Status */}
            <div className="bg-sentinel-surface/50 rounded-xl p-3 border border-sentinel-border/30">
              <p className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">Face Match</p>
              <div className="flex items-center gap-1.5">
                {faceMatch?.status === 'PASS' ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                ) : (
                  <XCircle className="w-4 h-4 text-red-400" />
                )}
                <span
                  className={`text-sm font-bold font-mono ${
                    faceMatch?.status === 'PASS' ? 'text-emerald-400' : 'text-red-400'
                  }`}
                >
                  {faceMatch?.status || 'PENDING'}
                </span>
              </div>
              <p className="text-[10px] text-gray-600 mt-1">
                {docFace?.detected ? 'Doc face ✓' : 'Doc face ✗'} · {personFace?.detected ? 'Person face ✓' : 'Person face ✗'}
              </p>
            </div>
          </div>

          {/* Failure or Warning reason */}
          {verificationResult.failure_reason && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-2.5 text-xs text-red-400 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>{verificationResult.failure_reason}</span>
            </div>
          )}
        </div>
      )}

      {/* Prototype limitation notice */}
      <p className="text-[11px] text-gray-600 italic text-center pt-1 border-t border-sentinel-border/30">
        AI-assisted identity verification prototype · MediaPipe real-time face detection & temporal liveness · Human review required for uncertain results
      </p>
    </div>
  )
}
