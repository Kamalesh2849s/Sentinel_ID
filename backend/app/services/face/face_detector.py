"""
Face detection component for SentinelID.
Detects faces in document images and camera frames with quality assessment.
"""
import logging
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict, Any
import numpy as np
import cv2

logger = logging.getLogger(__name__)


@dataclass
class DetectedFace:
    """Detected face metadata."""
    bbox: Tuple[int, int, int, int]  # (x, y, w, h)
    center: Tuple[int, int]          # (cx, cy)
    area: int
    confidence: float
    cropped_face: np.ndarray
    quality_score: float             # 0.0 - 1.0


class FaceDetector:
    """
    OpenCV-based robust face detector with multi-scale cascades
    and facial boundary normalization.
    """

    def __init__(self):
        self._cascade_frontal = None
        self._cascade_alt = None
        self._initialize()

    def _initialize(self):
        """Load Haar cascades."""
        try:
            self._cascade_frontal = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
            self._cascade_alt = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_alt2.xml"
            )
            logger.info("FaceDetector: cascades initialized successfully")
        except Exception as e:
            logger.error("FaceDetector initialization failed: %s", e)

    def detect_faces(
        self,
        img: np.ndarray,
        min_size: Tuple[int, int] = (40, 40),
        scale_factor: float = 1.1,
        min_neighbors: int = 4,
    ) -> List[DetectedFace]:
        """
        Detect all faces in an image (BGR or grayscale).
        Returns list of DetectedFace sorted by area (largest first).
        """
        if img is None or img.size == 0:
            return []

        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img

        # Histogram equalization for better contrast
        equalized = cv2.equalizeHist(gray)

        # Primary detector
        faces = []
        if self._cascade_alt is not None:
            raw_faces = self._cascade_alt.detectMultiScale(
                equalized,
                scaleFactor=scale_factor,
                minNeighbors=min_neighbors,
                minSize=min_size,
            )
            if len(raw_faces) > 0:
                faces = list(raw_faces)

        # Fallback to default cascade if none found
        if not faces and self._cascade_frontal is not None:
            raw_faces = self._cascade_frontal.detectMultiScale(
                equalized,
                scaleFactor=scale_factor,
                minNeighbors=max(3, min_neighbors - 1),
                minSize=min_size,
            )
            if len(raw_faces) > 0:
                faces = list(raw_faces)

        if not faces:
            return []

        results = []
        h_img, w_img = img.shape[:2]

        for (x, y, w, h) in faces:
            # Add padding
            pad_x = int(0.15 * w)
            pad_y = int(0.20 * h)
            x1 = max(0, x - pad_x)
            y1 = max(0, y - pad_y)
            x2 = min(w_img, x + w + pad_x)
            y2 = min(h_img, y + h + pad_y)

            crop = img[y1:y2, x1:x2]
            if crop.size == 0:
                continue

            # Quality calculation: sharpness (Laplacian var) + contrast + resolution
            crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
            laplacian_var = cv2.Laplacian(crop_gray, cv2.CV_64F).var()
            sharpness_score = min(1.0, laplacian_var / 500.0)
            
            # Contrast score (std deviation of pixel intensities)
            std_dev = float(np.std(crop_gray))
            contrast_score = min(1.0, std_dev / 50.0)

            # Size score (relative to reasonable face size 120x120)
            size_score = min(1.0, (w * h) / (120 * 120))

            quality = float(round(0.5 * sharpness_score + 0.3 * contrast_score + 0.2 * size_score, 3))
            quality = max(0.1, min(1.0, quality))

            # Confidence estimated from detection size & quality
            confidence = min(0.99, max(0.65, 0.6 + 0.35 * quality))

            results.append(DetectedFace(
                bbox=(int(x), int(y), int(w), int(h)),
                center=(int(x + w / 2), int(y + h / 2)),
                area=int(w * h),
                confidence=float(round(confidence, 3)),
                cropped_face=crop,
                quality_score=quality,
            ))

        # Sort by area descending
        results.sort(key=lambda f: f.area, reverse=True)
        return results

    def detect_primary_face(self, img: np.ndarray) -> Optional[DetectedFace]:
        """Detect and return the single primary (largest/best) face in image."""
        faces = self.detect_faces(img)
        return faces[0] if faces else None

    def detect_document_face(self, doc_img_or_path) -> Dict[str, Any]:
        """
        Detect face in an identity document.
        Returns document face detection metadata.
        """
        if isinstance(doc_img_or_path, str):
            img = cv2.imread(doc_img_or_path)
        else:
            img = doc_img_or_path

        if img is None:
            return {
                "document_face_detected": False,
                "document_face_quality": 0.0,
                "document_face_embedding_available": False,
                "error": "Failed to read document image",
            }

        face = self.detect_primary_face(img)
        if face is None:
            return {
                "document_face_detected": False,
                "document_face_quality": 0.0,
                "document_face_embedding_available": False,
                "error": "No face detected in document photo",
            }

        return {
            "document_face_detected": True,
            "document_face_quality": face.quality_score,
            "document_face_embedding_available": True,
            "bbox": face.bbox,
            "confidence": face.confidence,
            "face_crop": face.cropped_face,
        }


face_detector = FaceDetector()
