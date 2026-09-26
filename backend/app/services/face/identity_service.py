"""
Identity Verification Orchestration Service for SentinelID.

Orchestrates:
1. Document Face Extraction & Embedding
2. Person Camera Frames Temporal Liveness Detection
3. Best-Frame Person Face Detection & Embedding
4. Cosine Similarity Embedding Comparison
5. Final Identity Decision:
   identity_verified = (
       liveness_passed
       AND document_face_detected
       AND person_face_detected
       AND face_match
   )

Security Rules:
- Missing person verification CANNOT produce PASS (status = INCOMPLETE).
- Liveness failure CANNOT produce PASS (status = FAIL).
- Face mismatch CANNOT produce PASS (status = FAIL).
- Single uploaded photo results in Liveness = INCONCLUSIVE and CANNOT produce PASS.
"""
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from sqlalchemy.orm import Session
import cv2
import numpy as np

from app.core.config import settings
from app.models.models import Screening, IdentityVerification, FaceResult, ScreeningStatus
from app.services.face.face_detector import face_detector
from app.services.face.frame_analyzer import frame_analyzer
from app.services.face.motion_analyzer import motion_analyzer
from app.services.face.blink_detector import blink_detector
from app.services.face.liveness_detector import liveness_detector, LivenessDecision
from app.services.face.face_embedder import face_embedder
from app.services.preprocessing_service import preprocessing_service

logger = logging.getLogger(__name__)


class IdentityService:
    """
    Mandatory identity verification service combining liveness and face matching.
    """

    def __init__(self):
        self.similarity_threshold = settings.FACE_SIMILARITY_THRESHOLD

    def extract_document_face(self, doc_image_path: str) -> Dict[str, Any]:
        """
        Extract document photo, detect face, evaluate quality, and generate embedding.
        Section 3 Acceptance Criteria:
        Return:
        {
          "document_face_detected": true,
          "document_face_quality": 0.85,
          "document_face_embedding_available": true
        }
        """
        if not doc_image_path:
            return {
                "document_face_detected": False,
                "document_face_quality": 0.0,
                "document_face_embedding_available": False,
                "error": "Document image path not provided",
            }

        try:
            img = preprocessing_service.preprocess_for_face(doc_image_path)
        except Exception as e:
            return {
                "document_face_detected": False,
                "document_face_quality": 0.0,
                "document_face_embedding_available": False,
                "error": f"Unable to load/preprocess document image: {e}",
            }

        face = face_detector.detect_primary_face(img)
        if face is None:
            return {
                "document_face_detected": False,
                "document_face_quality": 0.0,
                "document_face_embedding_available": False,
                "error": "No face detected in document image",
            }

        embedding = face_embedder.extract_face_embedding(face.cropped_face)

        return {
            "document_face_detected": True,
            "document_face_quality": face.quality_score,
            "document_face_embedding_available": embedding is not None,
            "face_crop": face.cropped_face,
            "embedding": embedding,
            "bbox": face.bbox,
        }

    def verify_liveness(
        self,
        frames: List[Union[str, bytes, np.ndarray]],
        is_single_image_upload: bool = False,
    ) -> LivenessDecision:
        """
        Run temporal frame analysis using modular LivenessDetector.
        """
        return liveness_detector.verify_liveness(
            frame_inputs=frames,
            is_single_image_upload=is_single_image_upload,
        )

    def verify_person_face(
        self,
        frames: List[Union[str, bytes, np.ndarray]],
        document_embedding: Optional[np.ndarray],
    ) -> Dict[str, Any]:
        """
        Detect person face across frames, select best quality frame,
        generate embedding, and compare with document embedding.
        Section 4 Acceptance Criteria:
        Return:
        {
          "person_face_detected": true,
          "similarity": 0.0,
          "match": false,
          "threshold": 0.60
        }
        """
        threshold = settings.FACE_SIMILARITY_THRESHOLD

        if not frames:
            return {
                "person_face_detected": False,
                "similarity": 0.0,
                "match": False,
                "threshold": threshold,
                "error": "No person frames provided",
            }

        decoded_frames = []
        detected_faces = []

        for f in frames:
            img = frame_analyzer.decode_frame(f)
            if img is not None:
                decoded_frames.append(img)
                face = face_detector.detect_primary_face(img)
                detected_faces.append(face)

        if not decoded_frames:
            return {
                "person_face_detected": False,
                "similarity": 0.0,
                "match": False,
                "threshold": threshold,
                "error": "Failed to decode camera frames",
            }

        # Select best frame with a detected face
        best_idx, best_frame = frame_analyzer.select_best_frame(decoded_frames, detected_faces)
        best_face = detected_faces[best_idx]

        if best_face is None:
            return {
                "person_face_detected": False,
                "similarity": 0.0,
                "match": False,
                "threshold": threshold,
                "error": "No face detected in person camera frames",
            }

        person_embedding = face_embedder.extract_face_embedding(best_face.cropped_face)
        if person_embedding is None or document_embedding is None:
            return {
                "person_face_detected": True,
                "similarity": 0.0,
                "match": False,
                "threshold": threshold,
                "best_frame_quality": best_face.quality_score,
                "error": "Failed to generate embedding for face comparison",
            }

        similarity = face_embedder.compute_similarity(document_embedding, person_embedding)
        match = similarity >= threshold

        return {
            "person_face_detected": True,
            "similarity": similarity,
            "match": match,
            "threshold": threshold,
            "best_frame_quality": best_face.quality_score,
            "person_embedding": person_embedding,
            "best_frame": best_frame,
            "best_face_crop": best_face.cropped_face,
        }

    def verify_identity(
        self,
        doc_image_path: str,
        person_frames: Optional[List[Union[str, bytes, np.ndarray]]] = None,
        is_single_image_upload: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute full Identity Verification Pipeline:
        1. Document Face Extraction
        2. Liveness Verification
        3. Person Face Verification & Matching
        4. Final Decision Synthesis
        """
        threshold = settings.FACE_SIMILARITY_THRESHOLD

        # ── 1. Document Face ──────────────────────────────────────────────────
        doc_face_res = self.extract_document_face(doc_image_path)
        doc_face_detected = doc_face_res.get("document_face_detected", False)
        doc_embedding = doc_face_res.get("embedding")

        # ── Check if person input is missing entirely ─────────────────────────
        if not person_frames:
            return {
                "status": "INCOMPLETE",
                "reason": "Person verification is required",
                "failure_reason": "Person verification is required",
                "liveness": {
                    "status": "INCOMPLETE",
                    "confidence": 0.0,
                    "details": {"note": "No person verification frames provided"},
                },
                "document_face": {
                    "detected": doc_face_detected,
                    "quality": doc_face_res.get("document_face_quality", 0.0),
                    "embedding_available": doc_face_res.get("document_face_embedding_available", False),
                },
                "person_face": {
                    "detected": False,
                    "quality": 0.0,
                    "embedding_available": False,
                },
                "face_match": {
                    "similarity": 0.0,
                    "threshold": threshold,
                    "status": "NOT_EVALUATED",
                },
            }

        # ── 2. Liveness Detection ─────────────────────────────────────────────
        liveness_decision = self.verify_liveness(
            frames=person_frames,
            is_single_image_upload=is_single_image_upload,
        )

        # ── 3. Person Face & Similarity ───────────────────────────────────────
        person_face_res = self.verify_person_face(person_frames, doc_embedding)
        person_face_detected = person_face_res.get("person_face_detected", False)
        similarity = person_face_res.get("similarity", 0.0)
        face_match = person_face_res.get("match", False)

        # ── 4. Final Identity Decision Synthesis ──────────────────────────────
        # identity_verified =
        #     liveness_passed
        #     AND document_face_detected
        #     AND person_face_detected
        #     AND face_match
        liveness_passed = (liveness_decision.status == "PASS")

        # Determine failure reason according to specifications:
        failure_reason = None
        identity_status = "FAIL"

        if not doc_face_detected:
            failure_reason = "No face detected in document photograph"
        elif not person_face_detected:
            failure_reason = "No face detected in person verification capture"
        elif liveness_decision.status == "INCONCLUSIVE":
            failure_reason = (
                "Liveness verification is inconclusive. Camera frame analysis is required; "
                "single uploaded photo is insufficient."
            )
        elif not liveness_passed:
            failure_reason = liveness_decision.failure_reason or "Liveness verification failed"
        elif not face_match:
            failure_reason = "Person does not sufficiently match the document photograph"
        else:
            identity_status = "PASS"

        return {
            "status": identity_status,
            "failure_reason": failure_reason,
            "reason": failure_reason,
            "liveness": {
                "status": liveness_decision.status,
                "confidence": liveness_decision.confidence,
                "details": liveness_decision.details,
            },
            "document_face": {
                "detected": doc_face_detected,
                "quality": doc_face_res.get("document_face_quality", 0.0),
                "embedding_available": doc_face_res.get("document_face_embedding_available", False),
            },
            "person_face": {
                "detected": person_face_detected,
                "quality": person_face_res.get("best_frame_quality", 0.0),
                "embedding_available": person_face_res.get("person_embedding") is not None,
            },
            "face_match": {
                "similarity": round(similarity, 3),
                "threshold": threshold,
                "status": "PASS" if face_match else "FAIL",
            },
        }

    def save_identity_result(
        self,
        db: Session,
        screening_id: int,
        identity_res: Dict[str, Any],
    ) -> IdentityVerification:
        """
        Persist identity verification result and synchronize FaceResult in database.
        """
        doc_face = identity_res.get("document_face", {})
        person_face = identity_res.get("person_face", {})
        liveness = identity_res.get("liveness", {})
        face_match = identity_res.get("face_match", {})

        id_verif = db.query(IdentityVerification).filter(
            IdentityVerification.screening_id == screening_id
        ).first()

        if not id_verif:
            id_verif = IdentityVerification(screening_id=screening_id)
            db.add(id_verif)

        id_verif.document_face_detected = doc_face.get("detected", False)
        id_verif.person_face_detected = person_face.get("detected", False)
        id_verif.liveness_status = liveness.get("status", "INCOMPLETE")
        id_verif.liveness_confidence = liveness.get("confidence", 0.0)
        id_verif.face_similarity = face_match.get("similarity", 0.0)
        id_verif.face_threshold = face_match.get("threshold", settings.FACE_SIMILARITY_THRESHOLD)
        id_verif.identity_status = identity_res.get("status", "INCOMPLETE")
        id_verif.failure_reason = identity_res.get("failure_reason")
        id_verif.details = {
            "liveness": liveness,
            "document_face": doc_face,
            "person_face": person_face,
            "face_match": face_match,
        }
        id_verif.completed_at = datetime.utcnow()

        # Also sync FaceResult for backward compatibility
        face_result = db.query(FaceResult).filter(
            FaceResult.screening_id == screening_id
        ).first()
        if not face_result:
            face_result = FaceResult(screening_id=screening_id)
            db.add(face_result)

        face_result.face_detected_document = id_verif.document_face_detected
        face_result.face_detected_person = id_verif.person_face_detected
        face_result.similarity = id_verif.face_similarity
        face_result.match = (face_match.get("status") == "PASS")
        face_result.confidence = id_verif.face_similarity
        face_result.liveness_status = id_verif.liveness_status
        face_result.failure_reason = id_verif.failure_reason

        db.commit()
        db.refresh(id_verif)
        return id_verif


identity_service = IdentityService()
