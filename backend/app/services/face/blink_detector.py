"""
Blink and eye-state analysis component for SentinelID liveness verification.
Detects eye presence, state transitions (open/closed), and facial micro-changes.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
import numpy as np
import cv2

logger = logging.getLogger(__name__)


@dataclass
class BlinkMetrics:
    """Blink and eye movement analysis summary."""
    blink_detected: bool
    eye_state_transitions: int
    frames_with_eyes_detected: int
    eye_detection_rate: float
    eye_variation_score: float
    confidence: float


class BlinkDetector:
    """
    OpenCV-based eye detection and blink analysis.
    """

    def __init__(self):
        self._cascade_eye = None
        self._cascade_eyeglasses = None
        self._initialize()

    def _initialize(self):
        """Load eye cascades."""
        try:
            self._cascade_eye = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_eye.xml"
            )
            self._cascade_eyeglasses = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_eye_tree_eyeglasses.xml"
            )
            logger.info("BlinkDetector: eye cascades initialized")
        except Exception as e:
            logger.warning("BlinkDetector initialization warning: %s", e)

    def detect_eyes_in_face(self, face_crop: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """
        Detect eyes in the upper half of a cropped face.
        Returns list of (x, y, w, h) bounding boxes.
        """
        if face_crop is None or face_crop.size == 0:
            return []

        h, w = face_crop.shape[:2]
        # Search primarily in upper 65% of the face
        eye_region = face_crop[:int(h * 0.65), :]
        if eye_region.size == 0:
            return []

        if len(eye_region.shape) == 3:
            gray = cv2.cvtColor(eye_region, cv2.COLOR_BGR2GRAY)
        else:
            gray = eye_region

        equalized = cv2.equalizeHist(gray)

        eyes = []
        if self._cascade_eye is not None:
            detected = self._cascade_eye.detectMultiScale(
                equalized,
                scaleFactor=1.1,
                minNeighbors=3,
                minSize=(int(w * 0.12), int(h * 0.12)),
                maxSize=(int(w * 0.45), int(h * 0.45)),
            )
            if len(detected) > 0:
                eyes = list(detected)

        # Fallback to eyeglasses cascade if none found
        if not eyes and self._cascade_eyeglasses is not None:
            detected = self._cascade_eyeglasses.detectMultiScale(
                equalized,
                scaleFactor=1.1,
                minNeighbors=2,
                minSize=(int(w * 0.12), int(h * 0.12)),
            )
            if len(detected) > 0:
                eyes = list(detected)

        return eyes

    def analyze_sequence(
        self,
        face_crops: List[Optional[np.ndarray]],
    ) -> BlinkMetrics:
        """
        Analyze eye states across consecutive face crops to detect blinks or eye micro-changes.
        """
        valid_crops = [c for c in face_crops if c is not None and c.size > 0]
        if len(valid_crops) < 2:
            return BlinkMetrics(
                blink_detected=False,
                eye_state_transitions=0,
                frames_with_eyes_detected=0,
                eye_detection_rate=0.0,
                eye_variation_score=0.0,
                confidence=0.0,
            )

        eye_counts = []
        eye_region_intensities = []

        for crop in valid_crops:
            eyes = self.detect_eyes_in_face(crop)
            eye_counts.append(len(eyes))

            # Sample eye band intensity variance
            h, w = crop.shape[:2]
            eye_band = crop[int(h * 0.2):int(h * 0.55), int(w * 0.15):int(w * 0.85)]
            if eye_band.size > 0:
                g = cv2.cvtColor(eye_band, cv2.COLOR_BGR2GRAY) if len(eye_band.shape) == 3 else eye_band
                eye_region_intensities.append(float(np.mean(g)))
            else:
                eye_region_intensities.append(0.0)

        # Detect blink transitions: eye count dropping (e.g. from 2/1 to 0) and then restoring
        transitions = 0
        for i in range(len(eye_counts) - 1):
            if (eye_counts[i] >= 1 and eye_counts[i + 1] == 0) or (eye_counts[i] == 0 and eye_counts[i + 1] >= 1):
                transitions += 1

        # Also measure eye band intensity variation across frames
        if len(eye_region_intensities) >= 2:
            intensity_var = float(np.var(eye_region_intensities))
            intensity_variation_score = min(1.0, intensity_var / 15.0)
        else:
            intensity_variation_score = 0.0

        frames_with_eyes = sum(1 for c in eye_counts if c > 0)
        detection_rate = frames_with_eyes / max(1, len(valid_crops))

        # A blink is detected if we saw state transitions OR significant eyelid movement / intensity change
        blink_detected = (transitions >= 2) or (transitions >= 1 and intensity_variation_score > 0.35)

        confidence = 0.85 if blink_detected else (0.65 if detection_rate > 0.5 else 0.40)

        return BlinkMetrics(
            blink_detected=blink_detected,
            eye_state_transitions=transitions,
            frames_with_eyes_detected=frames_with_eyes,
            eye_detection_rate=round(detection_rate, 2),
            eye_variation_score=round(intensity_variation_score, 2),
            confidence=round(confidence, 2),
        )


blink_detector = BlinkDetector()
