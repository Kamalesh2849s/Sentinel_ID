"""
Transparent weighted risk engine for SentinelID.
Combines multiple screening signals into a 0-100 risk score with full explainability.

Design principles:
- All weights are configurable (not hardcoded)
- Every score contribution is traced to a specific signal
- Human-readable reasons are generated for each signal
- Status bands (VERIFIED/SUSPICIOUS/HIGH_RISK) are threshold-configurable
"""
import logging
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.config import settings

logger = logging.getLogger(__name__)


class RiskLevel:
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class RiskReason:
    """A single risk factor explanation."""
    category: str
    severity: str
    message: str
    contribution: float = 0.0  # Risk contribution (0-100)
    signal: Optional[str] = None
    result: Optional[str] = None
    impact: float = 0.0

    def __post_init__(self):
        if not self.signal:
            self.signal = {
                "mrz": "MRZ validation",
                "database": "Watchlist & database check",
                "tamper": "Tamper detection",
                "face": "Face matching & identity",
                "identity": "Face matching & identity",
                "consistency": "Field consistency check",
            }.get(self.category.lower(), self.category.replace("_", " ").title())

        if not self.result:
            sev_upper = str(self.severity).upper()
            if "HIGH" in sev_upper:
                self.result = "FAIL"
            elif "MEDIUM" in sev_upper or "WARN" in sev_upper:
                self.result = "WARNING"
            else:
                self.result = "PASS"

        if self.impact == 0.0 and self.contribution != 0.0:
            self.impact = round(self.contribution, 1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "severity": self.severity,
            "message": self.message,
            "signal": self.signal,
            "result": self.result,
            "impact": self.impact,
        }


@dataclass
class RiskResult:
    """Complete risk assessment result."""
    risk_score: Optional[float] = None
    risk_status: str = "pending"  # pending, calculating, completed, unavailable, failed
    risk_level: Optional[str] = None  # low, medium, high
    status: str = "PENDING"  # VERIFIED, SUSPICIOUS, HIGH_RISK, PENDING, FAILED
    mrz_risk: float = 0.0
    database_risk: float = 0.0
    tamper_risk: float = 0.0
    face_risk: float = 0.0
    consistency_risk: float = 0.0
    reasons: List[RiskReason] = field(default_factory=list)
    recommendation: str = ""
    weights_used: Dict[str, int] = field(default_factory=dict)
    failure_reason: Optional[str] = None
    calculated_at: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_score": round(self.risk_score, 1) if self.risk_score is not None else None,
            "risk_status": self.risk_status,
            "risk_level": self.risk_level,
            "status": self.status,
            "failure_reason": self.failure_reason,
            "mrz_risk": round(self.mrz_risk, 3),
            "database_risk": round(self.database_risk, 3),
            "tamper_risk": round(self.tamper_risk, 3),
            "face_risk": round(self.face_risk, 3),
            "consistency_risk": round(self.consistency_risk, 3),
            "reasons": [r.to_dict() for r in self.reasons],
            "recommendation": self.recommendation,
            "weights_used": self.weights_used,
            "calculated_at": self.calculated_at.isoformat() if hasattr(self.calculated_at, "isoformat") else self.calculated_at,
        }


class RiskEngine:
    """
    Configurable, transparent risk scoring engine.
    
    Risk score = weighted sum of normalized risk signals (0-100 scale).
    
    Signal weights (configurable via .env):
        MRZ validity:       20 pts
        Database status:    20 pts
        Tamper detection:   25 pts
        Face verification:  25 pts
        Field consistency:  10 pts
    """

    def __init__(self):
        self._load_config()

    def _load_config(self):
        """Load weights and thresholds from config."""
        self.weights = settings.risk_weights
        self.threshold_verified = settings.RISK_THRESHOLD_VERIFIED
        self.threshold_suspicious = settings.RISK_THRESHOLD_SUSPICIOUS
        self.face_similarity_threshold = settings.FACE_SIMILARITY_THRESHOLD

    def _determine_risk_level(self, risk_score: Optional[float]) -> Optional[str]:
        """Classify numeric risk score into low/medium/high band."""
        if risk_score is None:
            return None
        if risk_score <= self.threshold_verified:
            return "low"
        elif risk_score <= self.threshold_suspicious:
            return "medium"
        else:
            return "high"

    def build_signals_object(
        self,
        mrz_result: Optional[Dict[str, Any]] = None,
        database_result: Optional[Dict[str, Any]] = None,
        tamper_result: Optional[Dict[str, Any]] = None,
        face_result: Optional[Dict[str, Any]] = None,
        validation_checks: Optional[List[Dict[str, Any]]] = None,
        identity_result: Optional[Union[Dict[str, Any], Any]] = None,
        identity_verification: Optional[Union[Dict[str, Any], Any]] = None,
        ocr_data: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Build structured signals status object according to SentinelID specification.
        Signals: ocr, mrz, document_validation, expiry, blacklist, tamper, document_face, liveness, face_match.
        """
        # Accept either identity_result or identity_verification
        id_input = identity_result if identity_result is not None else identity_verification
        if id_input and not isinstance(id_input, dict) and hasattr(id_input, "identity_status"):
            id_input = {
                "status": id_input.identity_status,
                "liveness": id_input.liveness or {},
                "face_match": id_input.face_match or {},
                "document_face": id_input.document_face or {},
                "failure_reason": id_input.failure_reason,
            }
        identity_result = id_input
        # 1. OCR
        ocr_has_data = bool(ocr_data and (ocr_data.get("full_name") or ocr_data.get("document_number")))
        ocr_valid = bool(ocr_data and not ocr_data.get("fatal_error"))
        ocr_status = "completed" if (ocr_data is not None and (ocr_has_data or ocr_valid)) else ("failed" if ocr_data and ocr_data.get("fatal_error") else "pending")

        # 2. MRZ
        mrz_status = "pending"
        mrz_valid = False
        mrz_check_digits_valid = False
        if mrz_result is not None:
            mrz_status = "completed"
            if mrz_result.get("mrz_detected"):
                mrz_valid = bool(mrz_result.get("valid_structure", True))
                mrz_check_digits_valid = bool(mrz_result.get("check_digit_valid", False) or mrz_result.get("all_check_digits_valid", False))
            else:
                mrz_valid = False
                mrz_check_digits_valid = False

        # 3. Document Validation & Expiry
        val_status = "completed" if validation_checks is not None else "pending"
        val_valid = True
        expiry_valid = True
        if validation_checks:
            for c in validation_checks:
                if c.get("status") == "FAIL":
                    val_valid = False
                if "expiry" in c.get("check_name", "").lower() and c.get("status") == "FAIL":
                    expiry_valid = False

        # 4. Blacklist / Watchlist
        bl_status = "completed" if database_result is not None else "pending"
        bl_matched = bool(database_result.get("blacklist_match", False)) if database_result else False

        # 5. Tamper
        tamper_status = "completed" if tamper_result is not None else "pending"
        tamper_anomaly = bool(tamper_result.get("tamper_detected", False)) if tamper_result else False

        # 6. Document Face
        doc_face_status = "pending"
        doc_face_detected = False
        if identity_result and "document_face" in identity_result:
            doc_face_status = "completed"
            doc_face_detected = bool(identity_result["document_face"].get("detected", False))
        elif face_result and "face_detected_document" in face_result:
            doc_face_status = "completed"
            doc_face_detected = bool(face_result.get("face_detected_document", False))

        # 7. Liveness & 8. Face Match (Person Verification)
        liveness_status = "pending"
        liveness_passed = False
        face_match_status = "pending"
        face_match_matched = False
        face_match_similarity = 0.0

        if identity_result and identity_result.get("status") not in ("INCOMPLETE", "PENDING", None):
            liv = identity_result.get("liveness", {})
            liveness_status = "completed" if liv.get("status") in ("PASS", "FAIL", "INCONCLUSIVE") else "pending"
            liveness_passed = (liv.get("status") == "PASS")

            fm = identity_result.get("face_match", {})
            face_match_status = "completed" if fm.get("status") in ("PASS", "FAIL") else "pending"
            face_match_matched = (fm.get("status") == "PASS")
            face_match_similarity = fm.get("similarity", 0.0)
        elif face_result and (face_result.get("face_detected_person") or face_result.get("match") is not None and face_result.get("similarity", 0) > 0):
            liveness_status = "completed"
            liveness_passed = (face_result.get("liveness_status") == "PASS" or face_result.get("liveness_status") == "prototype")
            face_match_status = "completed"
            face_match_matched = bool(face_result.get("match", False))
            face_match_similarity = face_result.get("similarity", 0.0)

        return {
            "ocr": {"status": ocr_status, "valid": ocr_valid},
            "mrz": {"status": mrz_status, "valid": mrz_valid, "check_digits_valid": mrz_check_digits_valid},
            "document_validation": {"status": val_status, "valid": val_valid},
            "expiry": {"status": val_status, "valid": expiry_valid},
            "blacklist": {"status": bl_status, "matched": bl_matched},
            "tamper": {"status": tamper_status, "anomaly_detected": tamper_anomaly},
            "document_face": {"status": doc_face_status, "detected": doc_face_detected},
            "person_verification": {"status": liveness_status},
            "liveness": {"status": liveness_status, "passed": liveness_passed},
            "face_match": {"status": face_match_status, "matched": face_match_matched, "similarity": face_match_similarity},
        }

    def evaluate_readiness(self, signals: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
        """
        Check if required signals are ready before calculating final risk score.
        Returns: (is_ready, risk_status, failure_reason)
        """
        # If person verification (liveness or face_match) is pending
        if signals.get("liveness", {}).get("status") == "pending" or signals.get("face_match", {}).get("status") == "pending":
            return False, "pending", "Risk calculation pending — complete identity verification"

        # If a required document processing stage actually failed/errored out completely
        if signals.get("ocr", {}).get("status") == "failed":
            return False, "unavailable", "OCR text extraction failed"

        return True, "completed", None

    def calculate(
        self,
        mrz_result: Optional[Dict[str, Any]] = None,
        database_result: Optional[Dict[str, Any]] = None,
        tamper_result: Optional[Dict[str, Any]] = None,
        face_result: Optional[Dict[str, Any]] = None,
        validation_checks: Optional[List[Dict[str, Any]]] = None,
        identity_result: Optional[Union[Dict[str, Any], Any]] = None,
        identity_verification: Optional[Union[Dict[str, Any], Any]] = None,
        ocr_data: Optional[Dict[str, Any]] = None,
        require_signals: bool = False,
        **kwargs,
    ) -> RiskResult:
        """
        Calculate risk score from all screening signals.
        Returns fully explainable RiskResult.
        """
        self._load_config()  # Reload in case config changed

        signals = self.build_signals_object(
            mrz_result=mrz_result,
            database_result=database_result,
            tamper_result=tamper_result,
            face_result=face_result,
            validation_checks=validation_checks,
            identity_result=identity_result,
            identity_verification=identity_verification,
            ocr_data=ocr_data,
            **kwargs,
        )

        is_ready, r_status, failure_reason = self.evaluate_readiness(signals)

        # Temporary debugging logs as specified in SentinelID guidelines
        logger.info("[RISK] Starting risk calculation")
        logger.info("[RISK] OCR status: %s", signals.get("ocr", {}).get("status"))
        logger.info("[RISK] MRZ status: %s", signals.get("mrz", {}).get("status"))
        logger.info("[RISK] Validation status: %s", signals.get("document_validation", {}).get("status"))
        logger.info("[RISK] Tamper status: %s", signals.get("tamper", {}).get("status"))
        logger.info("[RISK] Liveness status: %s", signals.get("liveness", {}).get("status"))
        logger.info("[RISK] Face match status: %s", signals.get("face_match", {}).get("status"))
        logger.info("[RISK] Required signals ready: %s", is_ready)

        if require_signals and not is_ready:
            logger.info("[RISK] Risk calculation pending/unavailable: %s", failure_reason)
            return RiskResult(
                risk_score=None,
                risk_status=r_status,
                risk_level=None,
                status="PENDING" if r_status == "pending" else "FAILED",
                failure_reason=failure_reason,
                recommendation=(
                    "Risk calculation pending — complete identity verification"
                    if r_status == "pending"
                    else f"Risk calculation unavailable: {failure_reason}"
                ),
                weights_used=self.weights,
            )

        reasons = []
        component_scores = {}

        # ── 1. MRZ Risk (0-1 normalized) ──────────────────────────────────────
        mrz_risk, mrz_reasons = self._score_mrz(mrz_result)
        component_scores["mrz"] = mrz_risk
        reasons.extend(mrz_reasons)

        # ── 2. Database Risk ───────────────────────────────────────────────────
        db_risk, db_reasons = self._score_database(database_result)
        component_scores["database"] = db_risk
        reasons.extend(db_reasons)

        # ── 3. Tamper Risk ─────────────────────────────────────────────────────
        tamper_risk, tamper_reasons = self._score_tamper(tamper_result)
        component_scores["tamper"] = tamper_risk
        reasons.extend(tamper_reasons)

        # ── 4. Face & Identity Risk ───────────────────────────────────────────
        face_risk, face_reasons, identity_passed = self._score_face(face_result, identity_result)
        component_scores["face"] = face_risk
        reasons.extend(face_reasons)

        # ── 5. Field Consistency Risk ──────────────────────────────────────────
        consistency_risk, cons_reasons = self._score_consistency(validation_checks)
        component_scores["consistency"] = consistency_risk
        reasons.extend(cons_reasons)

        # ── Weighted combination ───────────────────────────────────────────────
        total_weight = sum(self.weights.values())
        risk_score = 0.0
        for signal, normalized_risk in component_scores.items():
            weight = self.weights.get(signal, 0)
            risk_score += (normalized_risk * weight)

        # Normalize to 0-100
        if total_weight > 0:
            risk_score = (risk_score / total_weight) * 100

        risk_score = round(min(max(risk_score, 0.0), 100.0), 1)
        risk_level = self._determine_risk_level(risk_score)

        # Determine status (identity must pass for status to be VERIFIED)
        status = self._determine_status(risk_score, identity_passed=identity_passed)

        # Generate recommendation
        recommendation = self._generate_recommendation(status, reasons)

        weights_used = self.weights.copy()
        weights_used["identity"] = weights_used.get("face", 25)

        logger.info("[RISK] Calculated score: %s", risk_score)
        logger.info("[RISK] Risk level: %s", risk_level)

        return RiskResult(
            risk_score=risk_score,
            risk_status="completed",
            risk_level=risk_level,
            status=status,
            mrz_risk=mrz_risk,
            database_risk=db_risk,
            tamper_risk=tamper_risk,
            face_risk=face_risk,
            consistency_risk=consistency_risk,
            reasons=reasons,
            recommendation=recommendation,
            weights_used=weights_used,
            calculated_at=datetime.now(timezone.utc),
        )

    def _score_mrz(
        self, mrz_result: Optional[Dict]
    ) -> Tuple[float, List[RiskReason]]:
        """Score MRZ validation result."""
        reasons = []

        if not mrz_result or not mrz_result.get("mrz_detected"):
            reasons.append(RiskReason(
                category="MRZ",
                severity=RiskLevel.HIGH,
                message="MRZ zone not detected in document — cannot validate machine-readable fields",
            ))
            return 1.0, reasons

        risk = 0.0

        if not mrz_result.get("valid_structure"):
            risk = max(risk, 0.8)
            reasons.append(RiskReason(
                category="MRZ",
                severity=RiskLevel.HIGH,
                message=f"MRZ structure is invalid — format does not conform to ICAO standards",
            ))
        else:
            reasons.append(RiskReason(
                category="MRZ",
                severity=RiskLevel.LOW,
                message=f"MRZ structure is valid ({mrz_result.get('mrz_format', 'unknown')} format)",
            ))

        if not mrz_result.get("check_digit_valid"):
            risk = max(risk, 0.9)
            failures = mrz_result.get("failure_reasons", [])
            reasons.append(RiskReason(
                category="MRZ",
                severity=RiskLevel.HIGH,
                message=f"MRZ check digit validation failed: {'; '.join(failures) if failures else 'unknown reason'}",
            ))
        else:
            reasons.append(RiskReason(
                category="MRZ",
                severity=RiskLevel.LOW,
                message="All MRZ check digits are valid — document number, DOB, expiry, and composite checks passed",
            ))

        if not mrz_result.get("field_consistency"):
            risk = max(risk, 0.6)
            reasons.append(RiskReason(
                category="MRZ",
                severity=RiskLevel.MEDIUM,
                message="MRZ fields are inconsistent with visual zone data",
            ))

        return min(risk, 1.0), reasons

    def _score_database(
        self, database_result: Optional[Dict]
    ) -> Tuple[float, List[RiskReason]]:
        """Score database validation result."""
        reasons = []

        if not database_result:
            reasons.append(RiskReason(
                category="DATABASE",
                severity=RiskLevel.LOW,
                message="Database check was skipped",
            ))
            return 0.5, reasons

        risk = database_result.get("database_risk", 0.5)

        if database_result.get("blacklist_match"):
            reasons.append(RiskReason(
                category="DATABASE",
                severity=RiskLevel.HIGH,
                message="[PROTOTYPE] Document number found on blacklist — immediate officer review required",
            ))
        elif database_result.get("watchlist_match"):
            entries = database_result.get("watchlist_entries", [])
            reason_text = entries[0]["reason"] if entries else "Unknown"
            reasons.append(RiskReason(
                category="DATABASE",
                severity=RiskLevel.MEDIUM,
                message=f"[PROTOTYPE] Document found on watchlist — {reason_text}",
            ))
        elif database_result.get("valid_doc_found"):
            doc_status = database_result.get("valid_doc_status", "")
            if doc_status == "VALID":
                reasons.append(RiskReason(
                    category="DATABASE",
                    severity=RiskLevel.LOW,
                    message="[PROTOTYPE] Document found in registry with status: VALID",
                ))
            elif doc_status in ("EXPIRED", "CANCELLED"):
                reasons.append(RiskReason(
                    category="DATABASE",
                    severity=RiskLevel.HIGH,
                    message=f"[PROTOTYPE] Document found in registry with status: {doc_status}",
                ))
            else:
                reasons.append(RiskReason(
                    category="DATABASE",
                    severity=RiskLevel.MEDIUM,
                    message=f"[PROTOTYPE] Document status in registry: {doc_status}",
                ))
        else:
            reasons.append(RiskReason(
                category="DATABASE",
                severity=RiskLevel.MEDIUM,
                message="[PROTOTYPE] Document not found in local registry — cannot verify authenticity via database",
            ))

        return min(risk, 1.0), reasons

    def _score_tamper(
        self, tamper_result: Optional[Dict]
    ) -> Tuple[float, List[RiskReason]]:
        """Score tamper detection result."""
        reasons = []

        if not tamper_result:
            reasons.append(RiskReason(
                category="TAMPER",
                severity=RiskLevel.LOW,
                message="Tamper analysis was not performed",
            ))
            return 0.3, reasons

        tamper_score = tamper_result.get("tamper_score", 0.0)
        tamper_detected = tamper_result.get("tamper_detected", False)
        ela_score = tamper_result.get("ela_score", 0.0)

        if tamper_detected and tamper_score > 0.7:
            reasons.append(RiskReason(
                category="TAMPER",
                severity=RiskLevel.HIGH,
                message=(
                    f"Image anomaly analysis detected potential manipulation "
                    f"(tamper score: {tamper_score:.2f}, ELA score: {ela_score:.2f}). "
                    "Human forensic review required."
                ),
            ))
        elif tamper_detected:
            reasons.append(RiskReason(
                category="TAMPER",
                severity=RiskLevel.MEDIUM,
                message=(
                    f"Moderate image anomalies detected (tamper score: {tamper_score:.2f}). "
                    "May indicate processing artifacts or potential manipulation."
                ),
            ))
        else:
            reasons.append(RiskReason(
                category="TAMPER",
                severity=RiskLevel.LOW,
                message=f"No significant image anomalies detected (tamper score: {tamper_score:.2f})",
            ))

        return tamper_score, reasons

    def _score_face(
        self,
        face_result: Optional[Dict],
        identity_result: Optional[Dict] = None,
    ) -> Tuple[float, List[RiskReason], bool]:
        """
        Score face verification and liveness verification result.
        Returns (risk_score, reasons, identity_passed).
        """
        reasons = []

        # Merge data from identity_result or face_result
        data = {}
        if face_result:
            data.update(face_result)
        if identity_result:
            data.update(identity_result)

        if not data:
            reasons.append(RiskReason(
                category="IDENTITY",
                severity=RiskLevel.HIGH,
                message="Person verification is missing — mandatory identity verification requirement not satisfied",
            ))
            return 0.85, reasons, False

        doc_face_detected = data.get("document_face_detected")
        if doc_face_detected is None:
            doc_face_detected = data.get("face_detected_document", False)
        if isinstance(data.get("document_face"), dict):
            doc_face_detected = data["document_face"].get("detected", doc_face_detected)

        person_face_detected = data.get("person_face_detected")
        if person_face_detected is None:
            person_face_detected = data.get("face_detected_person", False)
        if isinstance(data.get("person_face"), dict):
            person_face_detected = data["person_face"].get("detected", person_face_detected)

        # Liveness status
        liveness_status = data.get("liveness_status")
        if isinstance(data.get("liveness"), dict):
            liveness_status = data["liveness"].get("status", liveness_status)
        if not liveness_status:
            liveness_status = "prototype"

        # Similarity and match
        similarity = data.get("similarity", 0.0)
        match = data.get("match", False)
        if isinstance(data.get("face_match"), dict):
            similarity = data["face_match"].get("similarity", similarity)
            match = (data["face_match"].get("status") == "PASS") or data["face_match"].get("match", match)

        threshold = self.face_similarity_threshold

        identity_passed = True
        risk_components = []

        # 1. Document face check
        if not doc_face_detected:
            identity_passed = False
            reasons.append(RiskReason(
                category="IDENTITY",
                severity=RiskLevel.HIGH,
                message="No face detected in document image — cannot verify document photograph",
            ))
            risk_components.append(0.9)
        else:
            reasons.append(RiskReason(
                category="IDENTITY",
                severity=RiskLevel.LOW,
                message="Document face detected and verified in document photograph",
            ))

        # 2. Person face check
        if not person_face_detected:
            identity_passed = False
            reasons.append(RiskReason(
                category="IDENTITY",
                severity=RiskLevel.HIGH,
                message="No face detected in person verification capture — cannot match traveler identity",
            ))
            risk_components.append(0.85)

        # 3. Liveness check
        if liveness_status == "FAIL":
            identity_passed = False
            reasons.append(RiskReason(
                category="LIVENESS",
                severity=RiskLevel.HIGH,
                message="Liveness verification FAILED — temporal analysis did not observe authentic physical presence",
            ))
            risk_components.append(0.95)
        elif liveness_status == "INCONCLUSIVE":
            identity_passed = False
            reasons.append(RiskReason(
                category="LIVENESS",
                severity=RiskLevel.HIGH,
                message="Liveness verification INCONCLUSIVE — single uploaded image provided. Multi-frame camera verification required",
            ))
            risk_components.append(0.75)
        elif liveness_status == "PASS":
            reasons.append(RiskReason(
                category="LIVENESS",
                severity=RiskLevel.LOW,
                message="Liveness verification PASS — multi-frame temporal analysis confirmed authentic physical presence",
            ))
        elif liveness_status in ("prototype", "INCOMPLETE") and not person_face_detected:
            identity_passed = False
            reasons.append(RiskReason(
                category="LIVENESS",
                severity=RiskLevel.HIGH,
                message="Liveness verification incomplete — live camera verification required",
            ))
            risk_components.append(0.80)

        # 4. Face match check
        if not match:
            identity_passed = False
            reasons.append(RiskReason(
                category="FACE",
                severity=RiskLevel.HIGH,
                message=(
                    f"Face verification NO MATCH — similarity score: {similarity:.2f} "
                    f"(threshold: {threshold:.2f}). Person does not sufficiently match document photo."
                ),
            ))
            risk_components.append(max(0.85, 1.0 - similarity))
        else:
            reasons.append(RiskReason(
                category="FACE",
                severity=RiskLevel.LOW,
                message=f"Face verification MATCH — similarity score: {similarity:.2f} (threshold: {threshold:.2f})",
            ))
            risk_components.append(max(0.0, 1.0 - similarity))

        if not identity_passed:
            face_risk = max(risk_components) if risk_components else 0.8
        else:
            face_risk = 1.0 - similarity

        return min(max(face_risk, 0.0), 1.0), reasons, identity_passed

    def _score_consistency(
        self, validation_checks: Optional[List[Dict]]
    ) -> Tuple[float, List[RiskReason]]:
        """Score field consistency from validation results."""
        reasons = []

        if not validation_checks:
            reasons.append(RiskReason(
                category="CONSISTENCY",
                severity=RiskLevel.LOW,
                message="Field consistency checks were not performed",
            ))
            return 0.3, reasons

        identity_checks = [
            c for c in validation_checks
            if c.get("category") == "identity"
        ]

        if not identity_checks:
            return 0.2, reasons

        failed = [c for c in identity_checks if c.get("status") == "FAIL"]
        warnings = [c for c in identity_checks if c.get("status") == "WARNING"]
        total = len(identity_checks)

        if failed:
            risk = 0.5 + (len(failed) / total) * 0.5
            reasons.append(RiskReason(
                category="CONSISTENCY",
                severity=RiskLevel.HIGH,
                message=(
                    f"{len(failed)} field consistency check(s) failed — "
                    f"data mismatch between MRZ and visual zone"
                ),
            ))
        elif warnings:
            risk = 0.3
            reasons.append(RiskReason(
                category="CONSISTENCY",
                severity=RiskLevel.MEDIUM,
                message=f"{len(warnings)} field consistency warning(s) — minor discrepancies detected",
            ))
        else:
            risk = 0.0
            reasons.append(RiskReason(
                category="CONSISTENCY",
                severity=RiskLevel.LOW,
                message="All field consistency checks passed — MRZ and visual zone data are consistent",
            ))

        return min(risk, 1.0), reasons

    def _determine_status(self, risk_score: float, identity_passed: bool = True) -> str:
        """Determine status band from risk score and mandatory identity pass."""
        if risk_score <= self.threshold_verified:
            if not identity_passed:
                return "SUSPICIOUS"
            return "VERIFIED"
        elif risk_score <= self.threshold_suspicious:
            return "SUSPICIOUS"
        else:
            return "HIGH_RISK"

    def _generate_recommendation(
        self, status: str, reasons: List[RiskReason]
    ) -> str:
        """Generate officer recommendation based on status."""
        high_severity_count = sum(1 for r in reasons if r.severity == RiskLevel.HIGH)

        if status == "VERIFIED":
            return (
                "Document screening indicates low risk. Standard processing may proceed. "
                "Final decision rests with the screening officer."
            )
        elif status == "SUSPICIOUS":
            return (
                "HUMAN REVIEW RECOMMENDED: Document has been flagged with moderate risk indicators. "
                f"{high_severity_count} high-severity issue(s) detected. "
                "Screening officer should examine the document, verify identity with the traveler, "
                "and consider additional verification steps before making a final decision."
            )
        else:  # HIGH_RISK
            return (
                "HUMAN REVIEW REQUIRED: Document has been flagged with high risk indicators. "
                f"{high_severity_count} high-severity issue(s) detected. "
                "Screening officer must conduct a thorough manual review. "
                "Do not process this document without supervisor approval. "
                "This automated screening result does NOT constitute a final determination."
            )


risk_engine = RiskEngine()
