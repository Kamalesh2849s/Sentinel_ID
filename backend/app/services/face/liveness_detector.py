"""
Modular Liveness Detection Service for SentinelID.

Architecture:
LivenessDetector
├── FaceDetection
├── FrameAnalysis
├── MotionAnalysis
├── Blink/Challenge Detection
└── LivenessDecision

PROTOTYPE DISCLAIMER:
This is a prototype liveness verification module for demonstration and testing.
It performs temporal frame analysis and movement verification.
It does NOT claim production-grade spoof/deepfake protection.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any, Union
import numpy as np

from app.services.face.face_detector import face_detector, DetectedFace
from app.services.face.frame_analyzer import frame_analyzer, FrameQuality
from app.services.face.motion_analyzer import motion_analyzer, MotionMetrics
from app.services.face.blink_detector import blink_detector, BlinkMetrics

logger = logging.getLogger(__name__)


@dataclass
class LivenessDecision:
    """Final liveness verification decision and explanation."""
    status: str                 # "PASS", "FAIL", "INCONCLUSIVE"
    confidence: float          # 0.0 - 1.0
    is_static_image: bool
    face_continuity: float     # Percentage of frames with face detected
    motion_score: float        # Natural movement metric
    blink_detected: bool       # Whether eye state transition observed
    frames_analyzed: int
    failure_reason: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "confidence": round(self.confidence, 3),
            "is_static_image": self.is_static_image,
            "face_continuity": round(self.face_continuity, 3),
            "motion_score": round(self.motion_score, 3),
            "blink_detected": self.blink_detected,
            "frames_analyzed": self.frames_analyzed,
            "failure_reason": self.failure_reason,
            "details": self.details,
            "disclaimer": "Prototype liveness verification — human review required for uncertain results",
        }


class LivenessDetector:
    """
    Modular Liveness Detection Engine.
    Executes sequential temporal checks on camera frame sequences.
    """

    MIN_FRAMES_REQUIRED = 3     # Minimum frames for temporal analysis
    FACE_CONTINUITY_MIN = 0.60  # Minimum face detection frequency across frames

    def __init__(self):
        self.face_detection = face_detector
        self.frame_analysis = frame_analyzer
        self.motion_analysis = motion_analyzer
        self.blink_detection = blink_detector

    def verify_liveness(
        self,
        frame_inputs: List[Union[str, bytes, np.ndarray]],
        is_single_image_upload: bool = False,
    ) -> LivenessDecision:
        """
        Execute full modular liveness verification on a list of camera frames.
        
        Security Rule:
        If is_single_image_upload is True or len(frame_inputs) < 2,
        Liveness is immediately set to INCONCLUSIVE.
        """
        # ── 1. Security Check: Single Image Fallback ──────────────────────────
        if is_single_image_upload or len(frame_inputs) < self.MIN_FRAMES_REQUIRED:
            return LivenessDecision(
                status="INCONCLUSIVE",
                confidence=0.0,
                is_static_image=True,
                face_continuity=1.0 if len(frame_inputs) == 1 else 0.0,
                motion_score=0.0,
                blink_detected=False,
                frames_analyzed=len(frame_inputs),
                failure_reason=(
                    "Single uploaded photo cannot establish liveness. "
                    "Liveness requires multi-frame temporal camera analysis per security policy."
                ),
                details={
                    "note": "Uploaded photo fallback used. Identity verification cannot PASS without camera liveness.",
                    "frames_provided": len(frame_inputs),
                    "min_required": self.MIN_FRAMES_REQUIRED,
                },
            )

        # ── 2. Frame Analysis: Decode and evaluate all frames ─────────────────
        decoded_frames: List[np.ndarray] = []
        frame_qualities: List[FrameQuality] = []

        for f_input in frame_inputs:
            img = self.frame_analysis.decode_frame(f_input)
            if img is not None:
                decoded_frames.append(img)
                frame_qualities.append(self.frame_analysis.evaluate_quality(img))

        if len(decoded_frames) < self.MIN_FRAMES_REQUIRED:
            return LivenessDecision(
                status="FAIL",
                confidence=0.0,
                is_static_image=False,
                face_continuity=0.0,
                motion_score=0.0,
                blink_detected=False,
                frames_analyzed=len(decoded_frames),
                failure_reason="Unable to decode sufficient valid camera frames",
                details={"valid_frames": len(decoded_frames)},
            )

        # ── 3. Face Detection across all frames ───────────────────────────────
        detected_faces: List[Optional[DetectedFace]] = []
        face_crops: List[Optional[np.ndarray]] = []
        face_centers: List[Optional[Tuple[int, int]]] = []

        for frame in decoded_frames:
            face = self.face_detection.detect_primary_face(frame)
            detected_faces.append(face)
            if face is not None:
                face_crops.append(face.cropped_face)
                face_centers.append(face.center)
            else:
                face_crops.append(None)
                face_centers.append(None)

        faces_found = sum(1 for f in detected_faces if f is not None)
        face_continuity = faces_found / float(len(decoded_frames))

        # Check face continuity
        if face_continuity < self.FACE_CONTINUITY_MIN:
            return LivenessDecision(
                status="FAIL",
                confidence=0.2,
                is_static_image=False,
                face_continuity=face_continuity,
                motion_score=0.0,
                blink_detected=False,
                frames_analyzed=len(decoded_frames),
                failure_reason=(
                    f"Face not consistently detected across frames "
                    f"({faces_found}/{len(decoded_frames)} frames detected, "
                    f"minimum {int(self.FACE_CONTINUITY_MIN * 100)}% required)"
                ),
                details={
                    "face_continuity": face_continuity,
                    "faces_found": faces_found,
                    "total_frames": len(decoded_frames),
                },
            )

        # ── 4. Motion Analysis ────────────────────────────────────────────────
        motion_metrics: MotionMetrics = self.motion_analysis.analyze_motion(
            decoded_frames, face_centers
        )

        # Check for static photo attack
        if motion_metrics.is_static_image:
            return LivenessDecision(
                status="FAIL",
                confidence=0.1,
                is_static_image=True,
                face_continuity=face_continuity,
                motion_score=0.05,
                blink_detected=False,
                frames_analyzed=len(decoded_frames),
                failure_reason=(
                    "Static image behavior detected. Consecutive frames show zero or negligible "
                    "temporal motion (possible printed photo or still screen display)."
                ),
                details={
                    "mean_pixel_difference": motion_metrics.mean_frame_difference,
                    "face_displacement_variance": motion_metrics.face_displacement_variance,
                    "is_static": True,
                },
            )

        if motion_metrics.is_excessive_movement:
            return LivenessDecision(
                status="FAIL",
                confidence=0.25,
                is_static_image=False,
                face_continuity=face_continuity,
                motion_score=motion_metrics.natural_movement_score,
                blink_detected=False,
                frames_analyzed=len(decoded_frames),
                failure_reason="Excessive camera or subject movement detected during capture",
                details={
                    "mean_pixel_difference": motion_metrics.mean_frame_difference,
                },
            )

        # ── 5. Blink & Eye State Analysis ─────────────────────────────────────
        blink_metrics: BlinkMetrics = self.blink_detection.analyze_sequence(face_crops)

        # ── 6. Liveness Decision Synthesis ────────────────────────────────────
        # Calculate composite confidence
        # Motion naturalness (50%) + Face continuity (30%) + Blink/Eye micro-movements (20%)
        conf = (
            0.50 * motion_metrics.natural_movement_score
            + 0.30 * face_continuity
            + 0.20 * (0.95 if blink_metrics.blink_detected else (0.75 if blink_metrics.eye_detection_rate > 0.4 else 0.55))
        )
        conf = float(round(max(0.40, min(0.99, conf)), 3))

        decision_status = "PASS" if conf >= 0.55 else "FAIL"
        failure_reason = None
        if decision_status == "FAIL":
            failure_reason = "Liveness verification confidence did not reach passing threshold"

        details = {
            "frames_analyzed": len(decoded_frames),
            "face_continuity": round(face_continuity, 3),
            "motion_score": round(motion_metrics.natural_movement_score, 3),
            "mean_frame_diff": motion_metrics.mean_frame_difference,
            "face_displacement_var": motion_metrics.face_displacement_variance,
            "blink_detected": blink_metrics.blink_detected,
            "eye_detection_rate": blink_metrics.eye_detection_rate,
            "eye_state_transitions": blink_metrics.eye_state_transitions,
            "best_frame_sharpness": max((q.sharpness for q in frame_qualities), default=0.0),
        }

        return LivenessDecision(
            status=decision_status,
            confidence=conf,
            is_static_image=False,
            face_continuity=face_continuity,
            motion_score=motion_metrics.natural_movement_score,
            blink_detected=blink_metrics.blink_detected,
            frames_analyzed=len(decoded_frames),
            failure_reason=failure_reason,
            details=details,
        )


liveness_detector = LivenessDetector()
