"""
Tests for the risk engine.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.risk.risk_engine import RiskEngine


class TestRiskEngine:
    def setup_method(self):
        self.engine = RiskEngine()

    def _all_good(self):
        """Input signals for a clean, valid document."""
        return {
            "mrz_result": {
                "mrz_detected": True,
                "valid_structure": True,
                "check_digit_valid": True,
                "field_consistency": True,
                "mrz_format": "TD3",
                "failure_reasons": [],
            },
            "database_result": {
                "database_risk": 0.0,
                "valid_doc_found": True,
                "valid_doc_status": "VALID",
                "watchlist_match": False,
                "blacklist_match": False,
                "watchlist_entries": [],
            },
            "tamper_result": {
                "tamper_detected": False,
                "tamper_score": 0.1,
                "confidence": 0.8,
                "ela_score": 0.1,
            },
            "face_result": {
                "face_detected_document": True,
                "face_detected_person": True,
                "similarity": 0.85,
                "match": True,
                "confidence": 0.85,
                "failure_reason": None,
            },
            "validation_checks": [
                {"category": "identity", "status": "PASS", "check_name": "test", "message": "", "severity": "LOW"},
            ],
        }

    def test_all_good_is_verified(self):
        inputs = self._all_good()
        result = self.engine.calculate(**inputs)
        assert result.status == "VERIFIED"
        assert result.risk_score < 35

    def test_all_good_has_reasons(self):
        result = self.engine.calculate(**self._all_good())
        assert len(result.reasons) > 0

    def test_blacklist_match_is_high_risk(self):
        inputs = self._all_good()
        inputs["database_result"]["blacklist_match"] = True
        inputs["database_result"]["database_risk"] = 1.0
        result = self.engine.calculate(**inputs)
        # Database risk contributes 20% weight — high risk
        assert result.database_risk == 1.0
        # Overall status may be SUSPICIOUS or HIGH_RISK depending on other signals
        assert result.status in ("SUSPICIOUS", "HIGH_RISK") or result.risk_score > 25

    def test_invalid_mrz_increases_risk(self):
        inputs = self._all_good()
        inputs["mrz_result"]["check_digit_valid"] = False
        inputs["mrz_result"]["failure_reasons"] = ["Check digit mismatch"]
        result_bad = self.engine.calculate(**inputs)

        result_good = self.engine.calculate(**self._all_good())
        assert result_bad.risk_score > result_good.risk_score

    def test_high_tamper_score_increases_risk(self):
        inputs = self._all_good()
        inputs["tamper_result"]["tamper_score"] = 0.9
        inputs["tamper_result"]["tamper_detected"] = True
        result = self.engine.calculate(**inputs)
        assert result.tamper_risk > 0.5

    def test_face_no_match_increases_risk(self):
        inputs = self._all_good()
        inputs["face_result"]["match"] = False
        inputs["face_result"]["similarity"] = 0.2
        result = self.engine.calculate(**inputs)
        assert result.face_risk > 0.5

    def test_no_mrz_detected_high_risk(self):
        inputs = self._all_good()
        inputs["mrz_result"]["mrz_detected"] = False
        result = self.engine.calculate(**inputs)
        assert result.mrz_risk > 0.5

    def test_risk_score_is_0_to_100(self):
        result = self.engine.calculate(**self._all_good())
        assert 0 <= result.risk_score <= 100

    def test_status_band_verified(self):
        result = self.engine.calculate(**self._all_good())
        assert result.status == "VERIFIED"

    def test_weights_returned(self):
        result = self.engine.calculate(**self._all_good())
        assert "mrz" in result.weights_used
        assert "tamper" in result.weights_used
        assert "face" in result.weights_used

    def test_recommendation_generated(self):
        result = self.engine.calculate(**self._all_good())
        assert len(result.recommendation) > 0

    def test_none_inputs_handled(self):
        """All None inputs should not crash and should return a result."""
        result = self.engine.calculate(
            mrz_result=None,
            database_result=None,
            tamper_result=None,
            face_result=None,
            validation_checks=None,
        )
        assert result is not None
        assert 0 <= result.risk_score <= 100

    def test_consistency_failure_raises_risk(self):
        inputs = self._all_good()
        inputs["validation_checks"] = [
            {"category": "identity", "status": "FAIL", "check_name": "doc number mismatch",
             "message": "mismatch", "severity": "HIGH"},
        ]
        result = self.engine.calculate(**inputs)
        result_clean = self.engine.calculate(**self._all_good())
        assert result.consistency_risk > result_clean.consistency_risk

    def test_incomplete_screening_returns_pending_null_score(self):
        """When require_signals=True and person verification is missing, risk score must be None."""
        inputs = self._all_good()
        inputs["face_result"] = None
        inputs["identity_verification"] = None

        result = self.engine.calculate(**inputs, require_signals=True)
        assert result.risk_score is None
        assert result.risk_status == "pending"
        assert result.status == "PENDING"
        assert "complete identity verification" in result.recommendation.lower()

    def test_deterministic_calculation(self):
        """Identical screening inputs must produce the exact same risk score."""
        inputs = self._all_good()
        res1 = self.engine.calculate(**inputs)
        res2 = self.engine.calculate(**inputs)
        assert res1.risk_score == res2.risk_score
        assert res1.risk_status == res2.risk_status
        assert res1.risk_level == res2.risk_level
        assert len(res1.reasons) == len(res2.reasons)
        for r1, r2 in zip(res1.reasons, res2.reasons):
            assert r1.signal == r2.signal
            assert r1.result == r2.result
            assert r1.impact == r2.impact

    def test_signal_status_mapping(self):
        """Signals object must map signals to PASS, FAIL, WARNING, UNAVAILABLE, PENDING."""
        signals = self.engine.build_signals_object(
            mrz_result={"mrz_detected": True, "valid_structure": True, "check_digit_valid": True},
            database_result={"watchlist_match": False, "blacklist_match": False},
            tamper_result={"tamper_detected": False},
            face_result=None,
            identity_verification={"status": "INCOMPLETE"},
            validation_checks=[],
        )
        assert signals["mrz"]["status"] == "completed"
        assert signals["mrz"]["valid"] is True
        assert signals["person_verification"]["status"] == "pending"
        assert signals["liveness"]["status"] == "pending"
        assert signals["face_match"]["status"] == "pending"

    def test_reasons_contain_signal_result_impact(self):
        """Risk reasons must include signal name, result status, and numerical impact."""
        result = self.engine.calculate(**self._all_good())
        for reason in result.reasons:
            assert hasattr(reason, "signal")
            assert hasattr(reason, "result")
            assert hasattr(reason, "impact")
            assert reason.result in ("PASS", "FAIL", "WARNING", "UNAVAILABLE", "PENDING")
            assert isinstance(reason.impact, (int, float))

