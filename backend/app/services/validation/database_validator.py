"""
Database validation service.
Queries local prototype databases to check document status against
valid document registry, watchlist, and blacklist.

IMPORTANT: These are local prototype databases only.
NOT connected to any real government or law enforcement databases.
All data is clearly marked as prototype/simulation data.
"""
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.models.models import ValidDocument, Watchlist, Blacklist
from app.services.validation.document_validator import ValidationCheck

logger = logging.getLogger(__name__)


class DatabaseValidator:
    """
    PROTOTYPE: Local database validation service.
    Checks document against local mock registries.
    
    Architecture is designed to replace local DB queries
    with real government API calls when available.
    """

    PROTOTYPE_DISCLAIMER = (
        "PROTOTYPE DATA: This check uses a local simulated database, "
        "NOT a real government document registry or law enforcement database."
    )

    def validate(
        self,
        document_number: str,
        db: Session,
    ) -> Dict[str, Any]:
        """
        Perform all database validation checks.
        Returns structured result with status, risk level, and checks.
        """
        if not document_number:
            return self._empty_result("No document number provided for database check")

        doc_num_upper = document_number.strip().upper()

        checks = []
        database_risk = 0.0
        overall_status = "NOT_FOUND"

        # Check valid documents registry
        valid_result = self._check_valid_documents(doc_num_upper, db)
        checks.extend(valid_result["checks"])
        if valid_result["found"]:
            overall_status = valid_result["doc_status"]

        # Check watchlist
        watchlist_result = self._check_watchlist(doc_num_upper, db)
        checks.extend(watchlist_result["checks"])
        if watchlist_result["found"]:
            database_risk = max(database_risk, watchlist_result["risk"])

        # Check blacklist
        blacklist_result = self._check_blacklist(doc_num_upper, db)
        checks.extend(blacklist_result["checks"])
        if blacklist_result["found"]:
            database_risk = max(database_risk, blacklist_result["risk"])

        # If document not found anywhere, moderate risk
        if overall_status == "NOT_FOUND":
            database_risk = max(database_risk, 0.5)

        return {
            "document_number": doc_num_upper,
            "overall_status": overall_status,
            "database_risk": round(database_risk, 3),
            "valid_doc_found": valid_result["found"],
            "watchlist_match": watchlist_result["found"],
            "blacklist_match": blacklist_result["found"],
            "valid_doc_status": valid_result.get("doc_status"),
            "watchlist_entries": watchlist_result.get("entries", []),
            "checks": [c.to_dict() for c in checks],
            "disclaimer": self.PROTOTYPE_DISCLAIMER,
        }

    def _check_valid_documents(
        self, doc_number: str, db: Session
    ) -> Dict[str, Any]:
        """Query valid document registry."""
        try:
            doc = db.query(ValidDocument).filter(
                ValidDocument.document_number == doc_number
            ).first()

            if not doc:
                return {
                    "found": False,
                    "doc_status": "NOT_FOUND",
                    "checks": [ValidationCheck(
                        check_name="Valid Document Registry",
                        category="database",
                        status="WARNING",
                        message=f"Document {doc_number} not found in prototype valid document registry",
                        severity="MEDIUM",
                    )],
                }

            # Document found
            status = doc.status
            if status == "VALID":
                check_status = "PASS"
                severity = "LOW"
                message = f"Document found in registry with status: VALID"
            elif status == "EXPIRED":
                check_status = "FAIL"
                severity = "HIGH"
                message = f"Document found in registry with status: EXPIRED"
            elif status == "CANCELLED":
                check_status = "FAIL"
                severity = "HIGH"
                message = f"Document found in registry with status: CANCELLED"
            else:
                check_status = "WARNING"
                severity = "MEDIUM"
                message = f"Document found in registry with status: {status}"

            return {
                "found": True,
                "doc_status": status,
                "doc_name": doc.full_name,
                "doc_nationality": doc.nationality,
                "checks": [ValidationCheck(
                    check_name="Valid Document Registry",
                    category="database",
                    status=check_status,
                    message=f"[PROTOTYPE DATA] {message}",
                    severity=severity,
                )],
            }

        except Exception as e:
            logger.error("Valid document DB check failed: %s", e)
            return {
                "found": False,
                "doc_status": "ERROR",
                "checks": [ValidationCheck(
                    check_name="Valid Document Registry",
                    category="database",
                    status="SKIPPED",
                    message=f"Database check error: {str(e)}",
                    severity="LOW",
                )],
            }

    def _check_watchlist(
        self, doc_number: str, db: Session
    ) -> Dict[str, Any]:
        """Query watchlist registry."""
        try:
            entries = db.query(Watchlist).filter(
                Watchlist.document_number == doc_number,
                Watchlist.status == "ACTIVE",
            ).all()

            if not entries:
                return {
                    "found": False,
                    "risk": 0.0,
                    "entries": [],
                    "checks": [ValidationCheck(
                        check_name="Watchlist Check",
                        category="database",
                        status="PASS",
                        message="Document not found on watchlist [PROTOTYPE DATA]",
                        severity="LOW",
                    )],
                }

            # Found on watchlist
            max_severity = max((e.severity for e in entries), key=lambda s: {"LOW": 1, "MEDIUM": 2, "HIGH": 3}.get(s, 0))
            risk_map = {"LOW": 0.5, "MEDIUM": 0.7, "HIGH": 0.9}
            risk = risk_map.get(max_severity, 0.5)

            return {
                "found": True,
                "risk": risk,
                "entries": [{"reason": e.reason, "severity": e.severity} for e in entries],
                "checks": [ValidationCheck(
                    check_name="Watchlist Check",
                    category="database",
                    status="FAIL",
                    message=f"[PROTOTYPE DATA] Document FOUND on watchlist. Reason: {entries[0].reason}. Severity: {max_severity}",
                    severity=max_severity,
                )],
            }

        except Exception as e:
            logger.error("Watchlist DB check failed: %s", e)
            return {
                "found": False,
                "risk": 0.0,
                "entries": [],
                "checks": [ValidationCheck(
                    check_name="Watchlist Check",
                    category="database",
                    status="SKIPPED",
                    message=f"Watchlist check error: {str(e)}",
                    severity="LOW",
                )],
            }

    def _check_blacklist(
        self, doc_number: str, db: Session
    ) -> Dict[str, Any]:
        """Query blacklist registry."""
        try:
            entries = db.query(Blacklist).filter(
                Blacklist.document_number == doc_number,
                Blacklist.status == "ACTIVE",
            ).all()

            if not entries:
                return {
                    "found": False,
                    "risk": 0.0,
                    "checks": [ValidationCheck(
                        check_name="Blacklist Check",
                        category="database",
                        status="PASS",
                        message="Document not found on blacklist [PROTOTYPE DATA]",
                        severity="LOW",
                    )],
                }

            return {
                "found": True,
                "risk": 1.0,  # Maximum risk for blacklisted documents
                "checks": [ValidationCheck(
                    check_name="Blacklist Check",
                    category="database",
                    status="FAIL",
                    message=f"[PROTOTYPE DATA] Document FOUND on blacklist. Reason: {entries[0].reason}. IMMEDIATE REVIEW REQUIRED.",
                    severity="HIGH",
                )],
            }

        except Exception as e:
            logger.error("Blacklist DB check failed: %s", e)
            return {
                "found": False,
                "risk": 0.0,
                "checks": [ValidationCheck(
                    check_name="Blacklist Check",
                    category="database",
                    status="SKIPPED",
                    message=f"Blacklist check error: {str(e)}",
                    severity="LOW",
                )],
            }

    def _empty_result(self, reason: str) -> Dict[str, Any]:
        return {
            "document_number": None,
            "overall_status": "SKIPPED",
            "database_risk": 0.5,
            "valid_doc_found": False,
            "watchlist_match": False,
            "blacklist_match": False,
            "checks": [ValidationCheck(
                check_name="Database Check",
                category="database",
                status="SKIPPED",
                message=reason,
                severity="LOW",
            ).to_dict()],
            "disclaimer": self.PROTOTYPE_DISCLAIMER,
        }


database_validator = DatabaseValidator()
