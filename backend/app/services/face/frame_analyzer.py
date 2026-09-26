"""
Frame analysis component for SentinelID.
Validates, decodes, and measures quality metrics across camera frames.
"""
import base64
import logging
import io
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any, Union
import numpy as np
import cv2
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class FrameQuality:
    """Frame quality evaluation result."""
    sharpness: float       # Laplacian variance
    brightness: float      # 0-255 mean
    contrast: float        # Standard deviation of intensity
    is_blurred: bool       # Sharpness below threshold
    is_underexposed: bool  # Mean intensity too low
    is_overexposed: bool   # Mean intensity too high
    overall_score: float   # 0.0 - 1.0 composite quality score


class FrameAnalyzer:
    """
    Decodes, validates, and analyzes camera frames.
    """

    SHARPNESS_MIN = 60.0
    BRIGHTNESS_MIN = 35.0
    BRIGHTNESS_MAX = 230.0

    @staticmethod
    def decode_frame(frame_input: Union[str, bytes, np.ndarray]) -> Optional[np.ndarray]:
        """
        Robustly decode a frame from base64 string, file path, bytes, or ndarray.
        Returns BGR numpy array or None.
        """
        if frame_input is None:
            return None

        if isinstance(frame_input, np.ndarray):
            return frame_input.copy()

        if isinstance(frame_input, bytes):
            nparr = np.frombuffer(frame_input, np.uint8)
            return cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if isinstance(frame_input, str):
            # Check for Base64 Data URL
            if frame_input.startswith("data:image"):
                try:
                    header, encoded = frame_input.split(",", 1)
                    raw_bytes = base64.b64decode(encoded)
                    nparr = np.frombuffer(raw_bytes, np.uint8)
                    return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                except Exception as e:
                    logger.warning("Failed to decode base64 data URL: %s", e)
                    return None

            # Check if pure base64 without prefix
            if len(frame_input) > 200 and not frame_input.endswith((".jpg", ".png", ".webp", ".jpeg")):
                try:
                    raw_bytes = base64.b64decode(frame_input)
                    nparr = np.frombuffer(raw_bytes, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if img is not None:
                        return img
                except Exception:
                    pass

            # Otherwise treat as file path
            try:
                img = cv2.imread(frame_input)
                return img
            except Exception as e:
                logger.warning("Failed to read image from path %s: %s", frame_input, e)
                return None

        return None

    @classmethod
    def evaluate_quality(cls, img: np.ndarray) -> FrameQuality:
        """
        Evaluate image sharpness, exposure, and composite quality.
        """
        if img is None or img.size == 0:
            return FrameQuality(
                sharpness=0.0,
                brightness=0.0,
                contrast=0.0,
                is_blurred=True,
                is_underexposed=True,
                is_overexposed=False,
                overall_score=0.0,
            )

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img

        # Sharpness: Laplacian variance
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        is_blurred = sharpness < cls.SHARPNESS_MIN

        # Brightness & contrast
        brightness = float(np.mean(gray))
        contrast = float(np.std(gray))

        is_underexposed = brightness < cls.BRIGHTNESS_MIN
        is_overexposed = brightness > cls.BRIGHTNESS_MAX

        # Normalize metrics to 0-1
        sharpness_norm = min(1.0, sharpness / 400.0)
        contrast_norm = min(1.0, contrast / 50.0)
        
        # Exposure score: best around 128
        exp_diff = abs(brightness - 128.0)
        exposure_norm = max(0.0, 1.0 - (exp_diff / 128.0))

        overall_score = float(round(
            0.5 * sharpness_norm + 0.3 * contrast_norm + 0.2 * exposure_norm,
            3
        ))

        return FrameQuality(
            sharpness=round(sharpness, 2),
            brightness=round(brightness, 2),
            contrast=round(contrast, 2),
            is_blurred=is_blurred,
            is_underexposed=is_underexposed,
            is_overexposed=is_overexposed,
            overall_score=max(0.0, min(1.0, overall_score)),
        )

    @classmethod
    def select_best_frame(
        cls,
        frames: List[np.ndarray],
        detected_faces: List[Optional[Any]],
    ) -> Tuple[int, np.ndarray]:
        """
        Select the best quality frame from a sequence.
        Prioritizes frames with detected faces and high sharpness.
        Returns (best_index, best_frame).
        """
        if not frames:
            raise ValueError("No frames provided for selection")

        best_idx = 0
        best_score = -1.0

        for i, frame in enumerate(frames):
            quality = cls.evaluate_quality(frame)
            score = quality.overall_score

            face = detected_faces[i] if i < len(detected_faces) else None
            if face is not None:
                # Big bonus for face presence and face quality
                score += 1.0 + getattr(face, "quality_score", 0.5)

            if score > best_score:
                best_score = score
                best_idx = i

        return best_idx, frames[best_idx]


frame_analyzer = FrameAnalyzer()
