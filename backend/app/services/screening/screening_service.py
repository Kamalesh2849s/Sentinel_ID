"""
SentinelID Screening Service — Main pipeline orchestrator.

Pipeline:
  upload → preprocess → OCR (original + preprocessed) → MRZ → validate → tamper → face → risk → explain → save

Each stage is independently testable and error-isolated.
A single stage failure does not abort the complete pipeline.
"""
import logging
import re
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
import concurrent.futures
from sqlalchemy.orm import Session

from app.models.models import (
    Screening, ExtractedDocument, MRZResult, TamperResult,
    FaceResult, IdentityVerification, ValidationResult, RiskResult as RiskResultModel,
    AuditLog, ScreeningStatus, DocumentType
)
from app.services.preprocessing_service import preprocessing_service
from app.services.ocr.ocr_engine import ocr_engine
from app.services.ocr.field_extractor import field_extractor
from app.services.mrz.mrz_extractor import mrz_extractor
from app.services.mrz.mrz_parser import mrz_parser
from app.services.tamper.tamper_detector import tamper_detector
from app.services.face.face_verifier import face_verifier
from app.services.face.identity_service import identity_service
from app.services.validation.document_validator import document_validator
from app.services.validation.database_validator import database_validator
from app.services.risk.risk_engine import risk_engine, RiskResult

logger = logging.getLogger(__name__)


class StageStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ScreeningService:
    """
    Main screening pipeline orchestrator.
    Runs all analysis stages and saves results to the database.
    """

    def run_full_pipeline(
        self,
        screening: Screening,
        db: Session,
        person_image_path: Optional[str] = None,
        person_frames: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute the complete screening pipeline.
        Returns final result dict with all stage outputs.
        """
        start_time = time.time()
        stages = {}
        doc_image_path = screening.image_path
        processing_logs = []  # Collect detailed debug logs

        logger.info("Starting screening pipeline for document_id=%s", screening.document_id)
        processing_logs.append(f"Pipeline start: {doc_image_path}")

        # Update status to PROCESSING
        screening.status = ScreeningStatus.PROCESSING
        db.commit()

        # ── Stage 1: Preprocess ──────────────────────────────────────────────
        stages["preprocessing"] = StageStatus.PROCESSING
        img_cv = None
        preprocessed_path = None
        t0 = time.time()
        try:
            img_cv, img_pil = preprocessing_service.preprocess_for_ocr(doc_image_path)
            # Save preprocessed image for file-based OCR
            preprocessed_path = preprocessing_service.save_preprocessed(img_cv, doc_image_path)
            stages["preprocessing"] = StageStatus.COMPLETED
            processing_logs.append(
                f"Preprocessing: OK, shape={img_cv.shape}, preprocessed={preprocessed_path}"
            )
            self._log_audit(db, screening.id, "PREPROCESSING", "SUCCESS",
                            metadata={"shape": list(img_cv.shape)})
            logger.info(f"[PERF] Image preprocessing: {int((time.time() - t0)*1000)} ms")
            print(f"[PERF] Image preprocessing: {int((time.time() - t0)*1000)} ms")
        except Exception as e:
            stages["preprocessing"] = StageStatus.FAILED
            self._log_audit(db, screening.id, "PREPROCESSING", "FAILED", error=str(e))
            logger.error("Preprocessing failed: %s", e)
            processing_logs.append(f"Preprocessing FAILED: {e}")
            print(f"[PERF] Image preprocessing: {int((time.time() - t0)*1000)} ms")

        def do_ocr():
            t1 = time.time()
            ocr_data = {}
            ocr_debug = {}
            status = StageStatus.PROCESSING
            try:
                # Run OCR on preprocessed image if available, otherwise original
                img_to_ocr = preprocessed_path if preprocessed_path else doc_image_path
                ocr_result_best = ocr_engine.extract_text(img_to_ocr)
                
                ocr_data = field_extractor.extract(ocr_result_best.raw_text)
                ocr_data["extraction_confidence"] = ocr_result_best.confidence
                ocr_data["raw_ocr_text"] = ocr_result_best.raw_text
                ocr_data["engine_used"] = ocr_engine.engine_name
                
                ocr_debug = {
                    "selected": "preprocessed" if preprocessed_path else "original",
                    "engine": ocr_engine.engine_name,
                }
                status = StageStatus.COMPLETED
                logger.info(f"[PERF] OCR: {int((time.time() - t1)*1000)} ms")
                print(f"[PERF] OCR: {int((time.time() - t1)*1000)} ms")
                return ocr_data, ocr_debug, status, ocr_result_best, None
            except Exception as e:
                logger.error("OCR failed: %s", e, exc_info=True)
                print(f"[PERF] OCR: {int((time.time() - t1)*1000)} ms")
                return {}, {}, StageStatus.FAILED, None, str(e)

        def do_mrz():
            t2 = time.time()
            mrz_data = {"mrz_detected": False, "mrz_status": "NOT_DETECTED"}
            mrz_debug = {}
            status = StageStatus.PROCESSING
            try:
                mrz_text = mrz_extractor.extract_mrz_text(doc_image_path, img_cv)
                if mrz_text:
                    parsed = mrz_parser.parse(mrz_text)
                    mrz_data = parsed.to_dict()
                    mrz_debug = {
                        "raw_mrz_text": mrz_text,
                        "parsed_format": parsed.mrz_format,
                        "check_digits_valid": parsed.check_digit_valid,
                        "failure_reasons": parsed.failure_reasons,
                    }
                else:
                    mrz_data = {
                        "mrz_detected": False,
                        "mrz_status": "NOT_DETECTED",
                        "failure_reasons": ["MRZ not detected in uploaded document"],
                    }
                status = StageStatus.COMPLETED
                logger.info(f"[PERF] MRZ: {int((time.time() - t2)*1000)} ms")
                print(f"[PERF] MRZ: {int((time.time() - t2)*1000)} ms")
                return mrz_data, mrz_debug, status, mrz_text, None
            except Exception as e:
                logger.error("MRZ extraction failed: %s", e, exc_info=True)
                print(f"[PERF] MRZ: {int((time.time() - t2)*1000)} ms")
                return mrz_data, {}, StageStatus.FAILED, None, str(e)

        def do_tamper():
            t4 = time.time()
            try:
                tamper_data = tamper_detector.analyze(doc_image_path)
                logger.info(f"[PERF] Tamper detection: {int((time.time() - t4)*1000)} ms")
                print(f"[PERF] Tamper detection: {int((time.time() - t4)*1000)} ms")
                return tamper_data, StageStatus.COMPLETED, None
            except Exception as e:
                logger.error("Tamper detection failed: %s", e)
                print(f"[PERF] Tamper detection: {int((time.time() - t4)*1000)} ms")
                return {"tamper_score": 0.0, "tamper_detected": False}, StageStatus.FAILED, str(e)

        def do_doc_face():
            t_df = time.time()
            try:
                doc_face_res = identity_service.extract_document_face(doc_image_path)
                logger.info(f"[PERF] Document face extraction: {int((time.time() - t_df)*1000)} ms")
                print(f"[PERF] Document face extraction: {int((time.time() - t_df)*1000)} ms")
                return doc_face_res, None
            except Exception as e:
                logger.error("Doc face extraction failed: %s", e)
                return {}, str(e)

        # Execute independent tasks concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            fut_ocr = executor.submit(do_ocr)
            fut_mrz = executor.submit(do_mrz)
            fut_tamper = executor.submit(do_tamper)
            fut_doc_face = executor.submit(do_doc_face)

            ocr_data, ocr_debug, stages["ocr"], ocr_result_best, ocr_err = fut_ocr.result()
            mrz_data, mrz_debug, stages["mrz"], mrz_text, mrz_err = fut_mrz.result()
            tamper_data, stages["tamper"], tamper_err = fut_tamper.result()
            doc_face_res, doc_face_err = fut_doc_face.result()

        # ── MRZ Enrichment: fill missing OCR fields from MRZ ─────────────────
        # MRZ is more structured/reliable than pattern-matched OCR fields.
        # This fills document_number, DOB, expiry, name, nationality, sex
        # when OCR pattern extraction couldn't find them.
        if mrz_data.get("mrz_detected"):
            ocr_data = field_extractor.enrich_from_mrz(ocr_data, mrz_data)
            processing_logs.append(
                f"MRZ enrichment applied: doc_num={ocr_data.get('document_number')}, "
                f"name={ocr_data.get('full_name')}, dob={ocr_data.get('date_of_birth')}"
            )
            # ── MRZ / OCR consistency comparison ─────────────────────────────
            consistency = self._compute_mrz_ocr_consistency(mrz_data, ocr_data)
            mrz_data["consistency"] = consistency
            processing_logs.append(
                f"MRZ/OCR consistency: {consistency}"
            )

        # Handle OCR Persistence & Logging
        if stages["ocr"] == StageStatus.COMPLETED:
            self._save_extracted_document(db, screening.id, ocr_data)
            self._log_audit(db, screening.id, "OCR_EXTRACTION", "SUCCESS")
        elif ocr_err:
            self._log_audit(db, screening.id, "OCR_EXTRACTION", "FAILED", error=ocr_err)

        # Handle MRZ Persistence & Logging
        if stages["mrz"] == StageStatus.COMPLETED:
            self._save_mrz_result(db, screening.id, mrz_data)
            self._log_audit(db, screening.id, "MRZ_EXTRACTION", "SUCCESS")
        elif mrz_err:
            self._log_audit(db, screening.id, "MRZ_EXTRACTION", "FAILED", error=mrz_err)

        # Handle Tamper Persistence & Logging
        if stages["tamper"] == StageStatus.COMPLETED:
            self._save_tamper_result(db, screening.id, tamper_data)
            self._log_audit(db, screening.id, "TAMPER_DETECTION", "SUCCESS")
        elif tamper_err:
            self._log_audit(db, screening.id, "TAMPER_DETECTION", "FAILED", error=tamper_err)

        # ── Stage 4: Validation ───────────────────────────────────────────────
        stages["validation"] = StageStatus.PROCESSING

        validation_checks = []
        database_result = {}
        t3 = time.time()
        try:
            # Run document field validation (format, dates, consistency)
            doc_checks = document_validator.validate_document_fields(ocr_data)
            validation_checks.extend([c.to_dict() for c in doc_checks])

            # MRZ vs OCR consistency checks (if MRZ was detected)
            if mrz_data.get("mrz_detected"):
                mrz_checks = document_validator.validate_mrz_vs_ocr(mrz_data, ocr_data)
                validation_checks.extend([c.to_dict() for c in mrz_checks])

            # Database checks (watchlist, blacklist, valid document registry)
            doc_number = ocr_data.get("document_number")
            database_result = database_validator.validate(doc_number, db)
            validation_checks.extend(database_result.get("checks", []))

            stages["validation"] = StageStatus.COMPLETED
            self._save_validation_results(db, screening.id, validation_checks)
            self._log_audit(db, screening.id, "VALIDATION", "SUCCESS",
                            metadata={"checks_count": len(validation_checks)})
            logger.info(f"[PERF] Validation: {int((time.time() - t3)*1000)} ms")
            print(f"[PERF] Validation: {int((time.time() - t3)*1000)} ms")
        except Exception as e:
            stages["validation"] = StageStatus.FAILED
            self._log_audit(db, screening.id, "VALIDATION", "FAILED", error=str(e))
            logger.error("Validation failed: %s", e)
            processing_logs.append(f"Validation FAILED: {e}")
            print(f"[PERF] Validation: {int((time.time() - t3)*1000)} ms")

        # ── Stage 6: Identity & Face Verification ────────────────────────────
        stages["face"] = StageStatus.PROCESSING
        face_data = {}
        identity_data = {}
        t5 = time.time()
        try:
            frames_to_test = []
            is_single_upload = False
            if person_frames:
                frames_to_test = person_frames
            elif person_image_path:
                frames_to_test = [person_image_path]
                is_single_upload = True

            # If identity verification was already completed by verify endpoint, preserve it
            if not frames_to_test and screening.identity_verification and screening.identity_verification.identity_status != "INCOMPLETE":
                id_verif = screening.identity_verification
                identity_data = {
                    "status": id_verif.identity_status,
                    "document_face": {"detected": id_verif.document_face_detected},
                    "person_face": {"detected": id_verif.person_face_detected},
                    "liveness": {"status": id_verif.liveness_status, "confidence": id_verif.liveness_confidence},
                    "face_match": {
                        "similarity": id_verif.face_similarity,
                        "status": "PASS" if id_verif.face_similarity >= id_verif.face_threshold else "FAIL",
                        "threshold": id_verif.face_threshold,
                    },
                    "failure_reason": id_verif.failure_reason,
                }
                stages["face"] = StageStatus.COMPLETED
            elif not frames_to_test:
                # No person verification input provided yet — incomplete screening!
                doc_face_detected = doc_face_res.get("document_face_detected", False)
                identity_data = {
                    "status": "INCOMPLETE",
                    "failure_reason": "Person verification capture required",
                    "reason": "Person verification capture required",
                    "liveness": {
                        "status": "PENDING",
                        "confidence": 0.0,
                        "details": {},
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
                        "threshold": 0.6,
                        "status": "PENDING",
                    },
                }
                identity_service.save_identity_result(db, screening.id, identity_data)
                stages["face"] = StageStatus.PENDING
            else:
                t_face_only = time.time()
                # Run the rest of identity verification, passing the precomputed doc_face_res
                doc_embedding = doc_face_res.get("embedding")
                person_face_res = identity_service.verify_person_face(frames_to_test if frames_to_test else None, doc_embedding)
                liveness_decision = identity_service.verify_liveness(frames_to_test if frames_to_test else None, is_single_upload)
                
                # Manual synthesis to avoid re-extracting document face
                liveness_passed = (liveness_decision.status == "PASS")
                doc_face_detected = doc_face_res.get("document_face_detected", False)
                person_face_detected = person_face_res.get("person_face_detected", False)
                similarity = person_face_res.get("similarity", 0.0)
                face_match = person_face_res.get("match", False)
                
                failure_reason = None
                identity_status = "FAIL"
                if not doc_face_detected:
                    failure_reason = "No face detected in document photograph"
                elif not person_face_detected:
                    failure_reason = "No face detected in person verification capture"
                elif liveness_decision.status == "INCONCLUSIVE":
                    failure_reason = "Liveness verification is inconclusive."
                elif not liveness_passed:
                    failure_reason = liveness_decision.failure_reason or "Liveness verification failed"
                elif not face_match:
                    failure_reason = "Person does not sufficiently match the document photograph"
                else:
                    identity_status = "PASS"

                identity_data = {
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
                        "threshold": person_face_res.get("threshold", 0.6),
                        "status": "PASS" if face_match else "FAIL",
                    },
                }

                # Persist to database
                identity_service.save_identity_result(db, screening.id, identity_data)
                stages["face"] = StageStatus.COMPLETED
                print(f"[PERF] Person verification & Liveness: {int((time.time() - t_face_only)*1000)} ms")

            face_data = {
                "face_detected_document": identity_data["document_face"]["detected"],
                "face_detected_person": identity_data["person_face"]["detected"],
                "similarity": identity_data["face_match"]["similarity"],
                "match": (identity_data["face_match"]["status"] == "PASS"),
                "confidence": identity_data["face_match"]["similarity"],
                "liveness_status": identity_data["liveness"]["status"],
                "failure_reason": identity_data.get("failure_reason"),
            }

            if person_image_path:
                screening.person_image_path = person_image_path

            self._log_audit(db, screening.id, "IDENTITY_VERIFICATION",
                            "SUCCESS" if identity_data.get("status") in ("PASS", "INCOMPLETE") else "FAILED",
                            metadata={
                                "identity_status": identity_data.get("status"),
                                "liveness_status": identity_data.get("liveness", {}).get("status"),
                                "match": identity_data.get("face_match", {}).get("status") == "PASS",
                                "similarity": identity_data.get("face_match", {}).get("similarity"),
                            })
            processing_logs.append(
                f"Identity: status={identity_data.get('status')}, "
                f"liveness={identity_data.get('liveness', {}).get('status')}, "
                f"similarity={identity_data.get('face_match', {}).get('similarity')}"
            )
            logger.info(f"[PERF] Identity & Face: {int((time.time() - t5)*1000)} ms")
            print(f"[PERF] Identity & Face: {int((time.time() - t5)*1000)} ms")
        except Exception as e:
            stages["face"] = StageStatus.FAILED
            self._log_audit(db, screening.id, "IDENTITY_VERIFICATION", "FAILED", error=str(e))
            logger.error("Identity verification failed: %s", e)
            face_data = {"failure_reason": str(e)}
            identity_data = {"status": "FAIL", "failure_reason": str(e)}
            processing_logs.append(f"Identity verification FAILED: {e}")
            print(f"[PERF] Identity & Face: {int((time.time() - t5)*1000)} ms")

        # ── Stage 7: Risk Calculation ─────────────────────────────────────────
        stages["risk"] = StageStatus.PROCESSING
        try:
            # Build signals object and check if all required signals are ready
            # ── Stage 7: Centralized Risk Engine ──────────────────────────────────
            risk_result = risk_engine.calculate(
                mrz_result=mrz_data,
                database_result=database_result,
                tamper_result=tamper_data,
                face_result=face_data,
                validation_checks=validation_checks,
                identity_result=identity_data,
                ocr_data=ocr_data,
                require_signals=True,
            )

            self._save_risk_result(db, screening.id, risk_result)

            processing_time = int((time.time() - start_time) * 1000)
            screening.processing_time_ms = processing_time

            if risk_result.risk_status == "completed":
                screening.status = ScreeningStatus[risk_result.status]
                screening.risk_score = risk_result.risk_score
                screening.completed_at = datetime.utcnow()
                stages["risk"] = StageStatus.COMPLETED
                self._log_audit(db, screening.id, "RISK_CALCULATION", "SUCCESS",
                                metadata={
                                    "risk_score": risk_result.risk_score,
                                    "status": risk_result.status,
                                })
                logger.info(
                    "Screening complete: document_id=%s, status=%s, risk=%.1f, time=%dms",
                    screening.document_id, risk_result.status,
                    risk_result.risk_score, processing_time
                )
            elif risk_result.risk_status == "pending":
                screening.status = ScreeningStatus.PENDING
                screening.risk_score = None
                screening.completed_at = None
                stages["risk"] = StageStatus.PENDING
                logger.info(
                    "Screening pending verification: document_id=%s, risk_status=%s",
                    screening.document_id, risk_result.risk_status
                )
            else:
                screening.status = ScreeningStatus.FAILED
                screening.risk_score = None
                screening.completed_at = datetime.utcnow()
                stages["risk"] = StageStatus.FAILED
                logger.warning(
                    "Screening unavailable/failed: document_id=%s, risk_status=%s, reason=%s",
                    screening.document_id, risk_result.risk_status, risk_result.failure_reason
                )

            db.commit()

            return {
                "screening_id": screening.id,
                "document_id": screening.document_id,
                "status": risk_result.status,
                "risk_score": risk_result.risk_score,
                "risk": risk_result.to_dict(),
                "stages": stages,
                "ocr_data": ocr_data,
                "ocr_debug": ocr_debug,
                "mrz_data": mrz_data,
                "mrz_debug": mrz_debug,
                "tamper_data": tamper_data,
                "face_data": face_data,
                "identity_data": identity_data,
                "validation_checks": validation_checks,
                "risk_result": risk_result.to_dict(),
                "processing_time_ms": processing_time,
                "processing_logs": processing_logs,
            }

        except Exception as e:
            stages["risk"] = StageStatus.FAILED
            self._log_audit(db, screening.id, "RISK_CALCULATION", "FAILED", error=str(e))
            logger.error("Risk calculation failed: %s", e)

            screening.status = ScreeningStatus.FAILED
            screening.completed_at = datetime.utcnow()
            db.commit()

            return {
                "screening_id": screening.id,
                "document_id": screening.document_id,
                "status": "FAILED",
                "error": str(e),
                "stages": stages,
                "processing_logs": processing_logs,
            }

    # ─── Database save helpers ────────────────────────────────────────────────

    def _compute_mrz_ocr_consistency(self, mrz_data: Dict, ocr_data: Dict) -> Dict[str, str]:
        """
        Compare MRZ-derived fields with OCR-derived fields.
        Returns dict with status MATCH / PARTIAL_MATCH / MISMATCH / UNAVAILABLE.
        """
        def _normalize(val: str) -> str:
            if not val:
                return ""
            return str(val).upper().replace(" ", "").replace("/", "").replace("-", "")

        def _compare(mrz_val, ocr_val) -> str:
            if not mrz_val or not ocr_val:
                return "UNAVAILABLE"
            nm = _normalize(mrz_val)
            no = _normalize(ocr_val)
            return "MATCH" if nm == no else "MISMATCH"

        def _norm_tokens(s: Optional[str]) -> List[str]:
            if not s:
                return []
            c = re.sub(r'[^A-Z\s]', ' ', str(s).upper().replace('<', ' '))
            return [w for w in c.split() if w]

        ocr_name = ocr_data.get("name_ocr") or ocr_data.get("full_name")
        mrz_name = mrz_data.get("full_name_mrz") or mrz_data.get("full_name") or (
            f"{mrz_data.get('surname', '')} {mrz_data.get('given_names', '')}".strip()
        )

        ocr_tokens = _norm_tokens(ocr_name)
        mrz_tokens = _norm_tokens(mrz_name)

        if ocr_tokens and mrz_tokens:
            set_ocr = set(ocr_tokens)
            set_mrz = set(mrz_tokens)
            if ocr_tokens == mrz_tokens or set_ocr == set_mrz:
                name_consistency = "MATCH"
            elif set_ocr.issubset(set_mrz) or set_mrz.issubset(set_ocr) or len(set_ocr.intersection(set_mrz)) > 0:
                name_consistency = "PARTIAL_MATCH"
            else:
                name_consistency = "MISMATCH"
        else:
            name_consistency = "UNAVAILABLE"

        # Required debugging logs per Bug 1 (#22)
        print(f"[NAME] OCR: {ocr_name}")
        print(f"[NAME] MRZ: {mrz_name}")
        print(f"[NAME] Normalized OCR: {' '.join(ocr_tokens)}")
        print(f"[NAME] Normalized MRZ: {' '.join(mrz_tokens)}")
        print(f"[NAME] Consistency: {name_consistency}")

        return {
            "name": name_consistency,
            "document_number": _compare(
                mrz_data.get("document_number"), ocr_data.get("document_number")
            ),
            "date_of_birth": _compare(
                mrz_data.get("date_of_birth"), ocr_data.get("date_of_birth")
            ),
            "date_of_expiry": _compare(
                mrz_data.get("expiry_date"), ocr_data.get("expiry_date")
            ),
            "nationality": _compare(
                mrz_data.get("nationality_code") or mrz_data.get("nationality"),
                ocr_data.get("nationality_code") or ocr_data.get("nationality"),
            ),
        }

    def _save_extracted_document(
        self, db: Session, screening_id: int, data: Dict
    ):
        """Save OCR extracted fields to database (update if exists, insert if new)."""
        existing = db.query(ExtractedDocument).filter(
            ExtractedDocument.screening_id == screening_id
        ).first()
        if existing:
            existing.full_name = data.get("full_name")
            existing.document_number = data.get("document_number")
            existing.date_of_birth = data.get("date_of_birth")
            existing.nationality = data.get("nationality")
            existing.issue_date = data.get("issue_date")
            existing.expiry_date = data.get("expiry_date")
            existing.sex = data.get("sex")
            existing.issuing_country = data.get("issuing_country")
            existing.visa_number = data.get("visa_number")
            existing.raw_ocr_text = data.get("raw_ocr_text", "")
            existing.extraction_confidence = data.get("extraction_confidence", 0.0)
            existing.nationality_code = data.get("nationality_code")
            existing.issuing_country_code = data.get("issuing_country_code")
            existing.date_of_issue = data.get("date_of_issue") or data.get("issue_date")
            existing.date_of_issue_source = data.get("date_of_issue_source", "OCR/VIZ")
            existing.name_ocr = data.get("name_ocr")
            existing.name_mrz = data.get("name_mrz")
            existing.name_source = data.get("name_source")
            existing.name_consistency = data.get("name_consistency")
            existing.name_confidence = data.get("name_confidence")
        else:
            extracted = ExtractedDocument(
                screening_id=screening_id,
                full_name=data.get("full_name"),
                document_number=data.get("document_number"),
                date_of_birth=data.get("date_of_birth"),
                nationality=data.get("nationality"),
                issue_date=data.get("issue_date"),
                expiry_date=data.get("expiry_date"),
                sex=data.get("sex"),
                issuing_country=data.get("issuing_country"),
                visa_number=data.get("visa_number"),
                raw_ocr_text=data.get("raw_ocr_text", ""),
                extraction_confidence=data.get("extraction_confidence", 0.0),
                nationality_code=data.get("nationality_code"),
                issuing_country_code=data.get("issuing_country_code"),
                date_of_issue=data.get("date_of_issue") or data.get("issue_date"),
                date_of_issue_source=data.get("date_of_issue_source", "OCR/VIZ"),
                name_ocr=data.get("name_ocr"),
                name_mrz=data.get("name_mrz"),
                name_source=data.get("name_source"),
                name_consistency=data.get("name_consistency"),
                name_confidence=data.get("name_confidence"),
            )
            db.add(extracted)
        db.commit()

    def _save_mrz_result(
        self, db: Session, screening_id: int, data: Dict
    ):
        """Save MRZ parsing result to database (update if exists, insert if new)."""
        existing = db.query(MRZResult).filter(
            MRZResult.screening_id == screening_id
        ).first()
        raw_mrz_val = data.get("raw_mrz") or "\n".join(data.get("raw_mrz_lines", []))
        norm_mrz_val = data.get("normalized_mrz") or "\n".join(data.get("normalized_mrz_lines", []))
        mrz_status_val = data.get("mrz_status") or ("VALID" if data.get("check_digit_valid") else "INVALID")
        if not data.get("mrz_detected"):
            mrz_status_val = "NOT_DETECTED"

        if existing:
            existing.mrz_detected = data.get("mrz_detected", False)
            existing.mrz_status = mrz_status_val
            existing.raw_mrz = raw_mrz_val
            existing.raw_mrz_lines = data.get("raw_mrz_lines", [])
            existing.normalized_mrz = norm_mrz_val
            existing.normalized_mrz_lines = data.get("normalized_mrz_lines", [])
            existing.mrz_format = data.get("mrz_format")
            existing.valid_structure = data.get("valid_structure", False)
            existing.check_digit_valid = data.get("check_digit_valid", False)
            existing.document_number = data.get("document_number")
            existing.date_of_birth = data.get("date_of_birth")
            existing.expiry_date = data.get("expiry_date")
            existing.nationality = data.get("nationality")
            existing.nationality_code = data.get("nationality_code")
            existing.surname = data.get("surname")
            existing.given_names = data.get("given_names")
            existing.issuing_country = data.get("issuing_country")
            existing.issuing_country_code = data.get("issuing_country_code")
            existing.sex = data.get("sex")
            existing.field_consistency = data.get("field_consistency", False)
            existing.failure_reasons = data.get("failure_reasons", [])
            existing.check_digits = data.get("check_digits") or data.get("check_digits_dict")
            existing.mrz_parsed_fields = data.get("mrz_parsed_fields")
        else:
            mrz = MRZResult(
                screening_id=screening_id,
                mrz_detected=data.get("mrz_detected", False),
                mrz_status=mrz_status_val,
                raw_mrz=raw_mrz_val,
                raw_mrz_lines=data.get("raw_mrz_lines", []),
                normalized_mrz=norm_mrz_val,
                normalized_mrz_lines=data.get("normalized_mrz_lines", []),
                mrz_format=data.get("mrz_format"),
                valid_structure=data.get("valid_structure", False),
                check_digit_valid=data.get("check_digit_valid", False),
                document_number=data.get("document_number"),
                date_of_birth=data.get("date_of_birth"),
                expiry_date=data.get("expiry_date"),
                nationality=data.get("nationality"),
                nationality_code=data.get("nationality_code"),
                surname=data.get("surname"),
                given_names=data.get("given_names"),
                issuing_country=data.get("issuing_country"),
                issuing_country_code=data.get("issuing_country_code"),
                sex=data.get("sex"),
                field_consistency=data.get("field_consistency", False),
                failure_reasons=data.get("failure_reasons", []),
                check_digits=data.get("check_digits") or data.get("check_digits_dict"),
                mrz_parsed_fields=data.get("mrz_parsed_fields"),
            )
            db.add(mrz)
        db.commit()

    def _save_tamper_result(
        self, db: Session, screening_id: int, data: Dict
    ):
        """Save tamper detection result to database (update if exists, insert if new)."""
        existing = db.query(TamperResult).filter(
            TamperResult.screening_id == screening_id
        ).first()
        if existing:
            existing.tamper_detected = data.get("tamper_detected", False)
            existing.tamper_score = data.get("tamper_score", 0.0)
            existing.confidence = data.get("confidence", 0.0)
            existing.ela_score = data.get("ela_score", 0.0)
            existing.consistency_score = data.get("consistency_score", 0.0)
            existing.regions = data.get("regions", [])
            existing.reasons = data.get("reasons", [])
        else:
            tamper = TamperResult(
                screening_id=screening_id,
                tamper_detected=data.get("tamper_detected", False),
                tamper_score=data.get("tamper_score", 0.0),
                confidence=data.get("confidence", 0.0),
                ela_score=data.get("ela_score", 0.0),
                consistency_score=data.get("consistency_score", 0.0),
                regions=data.get("regions", []),
                reasons=data.get("reasons", []),
            )
            db.add(tamper)
        db.commit()

    def _save_face_result(
        self, db: Session, screening_id: int, data: Dict
    ):
        """Save face verification result to database (update if exists, insert if new)."""
        existing = db.query(FaceResult).filter(
            FaceResult.screening_id == screening_id
        ).first()
        if existing:
            existing.face_detected_document = data.get("face_detected_document", False)
            existing.face_detected_person = data.get("face_detected_person", False)
            existing.similarity = data.get("similarity", 0.0)
            existing.match = data.get("match", False)
            existing.confidence = data.get("confidence", 0.0)
            existing.liveness_status = data.get("liveness_status", "prototype")
            existing.failure_reason = data.get("failure_reason")
        else:
            face = FaceResult(
                screening_id=screening_id,
                face_detected_document=data.get("face_detected_document", False),
                face_detected_person=data.get("face_detected_person", False),
                similarity=data.get("similarity", 0.0),
                match=data.get("match", False),
                confidence=data.get("confidence", 0.0),
                liveness_status=data.get("liveness_status", "prototype"),
                failure_reason=data.get("failure_reason"),
            )
            db.add(face)
        db.commit()

    def _save_validation_results(
        self, db: Session, screening_id: int, checks: List[Dict]
    ):
        """Save all validation check results."""
        db.query(ValidationResult).filter(
            ValidationResult.screening_id == screening_id
        ).delete()
        db.flush()

        for check in checks:
            val = ValidationResult(
                screening_id=screening_id,
                check_name=check.get("check_name", ""),
                category=check.get("category", ""),
                status=check.get("status", ""),
                message=check.get("message", ""),
                severity=check.get("severity", "LOW"),
            )
            db.add(val)
        db.commit()

    def _save_risk_result(
        self, db: Session, screening_id: int, risk
    ):
        """Save risk engine result to database (update if exists, insert if new)."""
        from app.models.models import ScreeningStatus as SS
        status_enum = SS[risk.status] if (risk.status and risk.status in SS.__members__) else SS.PENDING
        existing = db.query(RiskResultModel).filter(
            RiskResultModel.screening_id == screening_id
        ).first()
        if existing:
            existing.risk_score = risk.risk_score
            existing.risk_status = getattr(risk, "risk_status", "pending")
            existing.risk_level = getattr(risk, "risk_level", None)
            existing.failure_reason = getattr(risk, "failure_reason", None)
            existing.calculated_at = getattr(risk, "calculated_at", None)
            existing.status = status_enum
            existing.mrz_risk = risk.mrz_risk
            existing.database_risk = risk.database_risk
            existing.tamper_risk = risk.tamper_risk
            existing.face_risk = risk.face_risk
            existing.consistency_risk = risk.consistency_risk
            existing.reasons = [r.to_dict() if hasattr(r, "to_dict") else r for r in risk.reasons]
            existing.recommendation = risk.recommendation
            existing.weights_used = risk.weights_used
        else:
            risk_model = RiskResultModel(
                screening_id=screening_id,
                risk_score=risk.risk_score,
                risk_status=getattr(risk, "risk_status", "pending"),
                risk_level=getattr(risk, "risk_level", None),
                failure_reason=getattr(risk, "failure_reason", None),
                calculated_at=getattr(risk, "calculated_at", None),
                status=status_enum,
                mrz_risk=risk.mrz_risk,
                database_risk=risk.database_risk,
                tamper_risk=risk.tamper_risk,
                face_risk=risk.face_risk,
                consistency_risk=risk.consistency_risk,
                reasons=[r.to_dict() if hasattr(r, "to_dict") else r for r in risk.reasons],
                recommendation=risk.recommendation,
                weights_used=risk.weights_used,
            )
            db.add(risk_model)
        db.commit()

    def _log_audit(
        self,
        db: Session,
        screening_id: int,
        action: str,
        status: str,
        metadata: Optional[Dict] = None,
        error: Optional[str] = None,
    ):
        """Add an audit log entry."""
        log = AuditLog(
            screening_id=screening_id,
            action=action,
            status=status,
            timestamp=datetime.utcnow(),
            action_metadata=metadata or {},
            error_message=error,
        )
        db.add(log)
        try:
            db.commit()
        except Exception as e:
            logger.warning("Audit log save failed: %s", e)
            db.rollback()


screening_service = ScreeningService()

