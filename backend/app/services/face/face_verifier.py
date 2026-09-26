"""
Face verification service using DeepFace.
Compares document photograph against a provided person photo.

Architecture:
  Document image → face detection → face embedding
  Person photo   → face detection → face embedding
  → cosine similarity → match decision

PROTOTYPE NOTES:
- Liveness detection is NOT implemented (requires specialized hardware/model)
- This compares two static images only
- Results are similarity scores, not definitive identity verification
"""
import logging
from typing import Dict, Any, Optional, Tuple
import numpy as np
import cv2

logger = logging.getLogger(__name__)


class FaceVerifier:
    """
    DeepFace-based face verification service.
    Falls back to OpenCV Haar cascade if DeepFace is unavailable.
    """

    SIMILARITY_THRESHOLD = 0.6  # Overridden by config

    def __init__(self, similarity_threshold: float = 0.6):
        self.similarity_threshold = similarity_threshold
        self._deepface_available = False
        self._opencv_cascade = None
        self._initialize()

    def _initialize(self):
        """Initialize face detection backends."""
        # Try DeepFace
        try:
            import deepface  # noqa: F401
            self._deepface_available = True
            logger.info("DeepFace initialized for face verification")
        except ImportError:
            logger.info("DeepFace not available, using OpenCV cascade fallback")

        # Always load OpenCV cascade as fallback
        try:
            self._opencv_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
            logger.info("OpenCV Haar cascade loaded")
        except Exception as e:
            logger.warning("OpenCV cascade load failed: %s", e)

    def verify(
        self,
        document_image_path: str,
        person_image_path: str,
    ) -> Dict[str, Any]:
        """
        Compare document photo with person photo.
        Returns verification result with similarity and match decision.
        """
        logger.info("Running face verification")

        if self._deepface_available:
            return self._deepface_verify(document_image_path, person_image_path)
        else:
            return self._opencv_verify(document_image_path, person_image_path)

    def detect_face_in_document(self, document_image_path: str) -> Dict[str, Any]:
        """Detect and return face metadata from document image only."""
        if self._deepface_available:
            return self._deepface_detect(document_image_path)
        else:
            return self._opencv_detect(document_image_path)

    def _deepface_verify(
        self, doc_path: str, person_path: str
    ) -> Dict[str, Any]:
        """Use DeepFace for face verification."""
        try:
            from deepface import DeepFace

            result = DeepFace.verify(
                img1_path=doc_path,
                img2_path=person_path,
                model_name="VGG-Face",
                distance_metric="cosine",
                enforce_detection=False,
            )

            # DeepFace returns distance, not similarity
            distance = result.get("distance", 1.0)
            threshold = result.get("threshold", 0.4)
            similarity = max(0.0, 1.0 - distance)
            match = result.get("verified", False)

            return {
                "face_detected_document": True,
                "face_detected_person": True,
                "similarity": round(similarity, 3),
                "match": match,
                "confidence": round(similarity, 3),
                "distance": round(distance, 3),
                "threshold_used": threshold,
                "model": "VGG-Face (DeepFace)",
                "liveness_status": "prototype — static image comparison only",
                "failure_reason": None,
            }

        except Exception as e:
            error_msg = str(e)
            logger.error("DeepFace verification failed: %s", error_msg)

            # Check for specific errors
            if "face" in error_msg.lower() and "detect" in error_msg.lower():
                return self._no_face_result("Face could not be detected in one or both images")
            elif "cannot" in error_msg.lower() or "error" in error_msg.lower():
                return self._no_face_result(f"Face verification error: {error_msg[:200]}")
            else:
                return self._no_face_result(f"Verification failed: {error_msg[:200]}")

    def _opencv_verify(
        self, doc_path: str, person_path: str
    ) -> Dict[str, Any]:
        """
        OpenCV-based face verification fallback.
        Uses face detection + basic feature comparison.
        Note: This is less accurate than deep learning-based methods.
        """
        doc_face = self._opencv_extract_face(doc_path)
        person_face = self._opencv_extract_face(person_path)

        if doc_face is None:
            return self._no_face_result("No face detected in document image (OpenCV)")

        if person_face is None:
            return self._no_face_result("No face detected in person image (OpenCV)")

        # Resize both to same size
        target_size = (100, 100)
        doc_face_resized = cv2.resize(doc_face, target_size)
        person_face_resized = cv2.resize(person_face, target_size)

        # Compute normalized cross-correlation
        doc_gray = cv2.cvtColor(doc_face_resized, cv2.COLOR_BGR2GRAY).astype(np.float32)
        person_gray = cv2.cvtColor(person_face_resized, cv2.COLOR_BGR2GRAY).astype(np.float32)

        # Histogram comparison
        doc_hist = cv2.calcHist([doc_gray.astype(np.uint8)], [0], None, [256], [0, 256])
        person_hist = cv2.calcHist([person_gray.astype(np.uint8)], [0], None, [256], [0, 256])
        hist_similarity = cv2.compareHist(doc_hist, person_hist, cv2.HISTCMP_CORREL)

        # Template matching similarity
        result = cv2.matchTemplate(doc_gray, person_gray, cv2.TM_CCOEFF_NORMED)
        template_similarity = float(np.max(result))

        # Combined similarity (weighted)
        similarity = (float(hist_similarity) * 0.4 + max(template_similarity, 0) * 0.6)
        similarity = max(0.0, min(1.0, similarity))
        match = similarity >= self.similarity_threshold

        return {
            "face_detected_document": True,
            "face_detected_person": True,
            "similarity": round(similarity, 3),
            "match": match,
            "confidence": round(similarity * 0.7, 3),  # Lower confidence for OpenCV method
            "model": "OpenCV Haar Cascade (basic — less accurate than deep learning)",
            "liveness_status": "prototype — static image comparison only",
            "failure_reason": None,
            "note": "DeepFace not available. Using basic OpenCV comparison. Accuracy is limited.",
        }

    def _deepface_detect(self, image_path: str) -> Dict[str, Any]:
        """Detect face using DeepFace."""
        try:
            from deepface import DeepFace
            faces = DeepFace.extract_faces(
                img_path=image_path,
                enforce_detection=False,
            )
            if faces:
                return {
                    "face_detected": True,
                    "face_count": len(faces),
                    "confidence": faces[0].get("confidence", 0.8),
                }
            return {"face_detected": False, "face_count": 0, "confidence": 0.0}
        except Exception as e:
            return {"face_detected": False, "face_count": 0, "error": str(e)}

    def _opencv_detect(self, image_path: str) -> Dict[str, Any]:
        """Detect face using OpenCV."""
        face = self._opencv_extract_face(image_path)
        return {
            "face_detected": face is not None,
            "face_count": 1 if face is not None else 0,
            "confidence": 0.7 if face is not None else 0.0,
        }

    def _opencv_extract_face(self, image_path: str) -> Optional[np.ndarray]:
        """Detect and crop face from image using OpenCV Haar cascade."""
        if self._opencv_cascade is None:
            return None

        img = cv2.imread(image_path)
        if img is None:
            return None

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = self._opencv_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30),
        )

        if len(faces) == 0:
            return None

        # Return the largest face
        faces_sorted = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
        x, y, w, h = faces_sorted[0]

        # Add padding
        pad = int(0.15 * max(w, h))
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(img.shape[1], x + w + pad)
        y2 = min(img.shape[0], y + h + pad)

        return img[y1:y2, x1:x2]

    def _no_face_result(self, reason: str) -> Dict[str, Any]:
        """Return a result indicating face detection failure."""
        return {
            "face_detected_document": False,
            "face_detected_person": False,
            "similarity": 0.0,
            "match": False,
            "confidence": 0.0,
            "liveness_status": "prototype",
            "failure_reason": reason,
        }


def create_face_verifier() -> FaceVerifier:
    """Factory: create face verifier with config-driven threshold."""
    from app.core.config import settings
    return FaceVerifier(similarity_threshold=settings.FACE_SIMILARITY_THRESHOLD)


face_verifier = create_face_verifier()
