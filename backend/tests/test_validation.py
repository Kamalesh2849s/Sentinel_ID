"""
Tests for document validation engine.
"""
import pytest
import sys
import os
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.validation.document_validator import DocumentValidator


class TestDocumentValidator:
    def setup_method(self):
        self.validator = DocumentValidator()

    def _make_valid_doc(self):
        today = date.today()
        future = today + timedelta(days=365 * 5)
        past = today - timedelta(days=365 * 2)
        return {
            "full_name": "JOHN SMITH",
            "document_number": "AB123456",
            "date_of_birth": "01/01/1985",
            "expiry_date": future.strftime("%d/%m/%Y"),
            "issue_date": past.strftime("%d/%m/%Y"),
            "nationality": "USA",
            "sex": "M",
            "issuing_country": "USA",
        }

    def test_valid_document_passes(self):
        doc = self._make_valid_doc()
        checks = self.validator.validate_document_fields(doc)
        failed = [c for c in checks if c.status == "FAIL"]
        assert len(failed) == 0

    def test_missing_required_field_fails(self):
        doc = self._make_valid_doc()
        doc["document_number"] = None
        checks = self.validator.validate_document_fields(doc)
        failed = [c for c in checks if c.status == "FAIL" and "document_number" in c.check_name.lower()]
        assert len(failed) > 0

    def test_expired_document_fails(self):
        doc = self._make_valid_doc()
        yesterday = date.today() - timedelta(days=1)
        doc["expiry_date"] = yesterday.strftime("%d/%m/%Y")
        checks = self.validator.validate_document_fields(doc)
        expiry_checks = [c for c in checks if "Expiry" in c.check_name and c.status == "FAIL"]
        assert len(expiry_checks) > 0

    def test_expiry_before_issue_fails(self):
        doc = self._make_valid_doc()
        doc["issue_date"] = "01/01/2025"
        doc["expiry_date"] = "01/01/2020"  # Before issue date
        checks = self.validator.validate_document_fields(doc)
        failed = [c for c in checks if "Consistency" in c.check_name and c.status == "FAIL"]
        assert len(failed) > 0

    def test_valid_document_number_format(self):
        doc = self._make_valid_doc()
        doc["document_number"] = "AB123456"
        checks = self.validator.validate_document_fields(doc)
        num_check = [c for c in checks if "Number Format" in c.check_name]
        assert any(c.status == "PASS" for c in num_check)

    def test_invalid_sex_warning(self):
        doc = self._make_valid_doc()
        doc["sex"] = "Z"
        checks = self.validator.validate_document_fields(doc)
        sex_checks = [c for c in checks if "Sex" in c.check_name]
        assert any(c.status == "WARNING" for c in sex_checks)

    def test_valid_sex_m(self):
        doc = self._make_valid_doc()
        doc["sex"] = "M"
        checks = self.validator.validate_document_fields(doc)
        sex_checks = [c for c in checks if "Sex" in c.check_name]
        assert any(c.status == "PASS" for c in sex_checks)

    def test_impossible_age_fails(self):
        doc = self._make_valid_doc()
        doc["date_of_birth"] = "01/01/1800"  # 225 years old — impossible
        checks = self.validator.validate_document_fields(doc)
        # Should have a FAIL for impossible age
        birth_checks = [c for c in checks if "Birth" in c.check_name and c.status == "FAIL"]
        assert len(birth_checks) > 0

    def test_mrz_vs_ocr_consistency_match(self):
        mrz = {
            "mrz_detected": True,
            "document_number": "AB123456",
            "expiry_date": "01/01/2028",
            "check_digit_valid": True,
            "valid_structure": True,
            "mrz_format": "TD3",
            "failure_reasons": [],
        }
        ocr = {"document_number": "AB123456", "expiry_date": "01/01/2028"}
        checks = self.validator.validate_mrz_vs_ocr(mrz, ocr)
        doc_num_checks = [c for c in checks if "Document Number Consistency" in c.check_name]
        assert any(c.status == "PASS" for c in doc_num_checks)

    def test_mrz_vs_ocr_mismatch_fails(self):
        mrz = {
            "mrz_detected": True,
            "document_number": "AB123456",
            "expiry_date": "01/01/2028",
            "check_digit_valid": True,
            "valid_structure": True,
            "mrz_format": "TD3",
            "failure_reasons": [],
        }
        ocr = {"document_number": "XY999999", "expiry_date": "01/01/2028"}
        checks = self.validator.validate_mrz_vs_ocr(mrz, ocr)
        mismatches = [c for c in checks if "Consistency" in c.check_name and c.status == "FAIL"]
        assert len(mismatches) > 0

    def test_no_mrz_detected(self):
        mrz = {"mrz_detected": False}
        ocr = {"document_number": "AB123456"}
        checks = self.validator.validate_mrz_vs_ocr(mrz, ocr)
        mrz_checks = [c for c in checks if "MRZ Presence" in c.check_name and c.status == "FAIL"]
        assert len(mrz_checks) > 0


class TestDateParsing:
    def setup_method(self):
        self.validator = DocumentValidator()

    def test_dd_mm_yyyy_format(self):
        result = self.validator._parse_date("15/03/1985")
        assert result == date(1985, 3, 15)

    def test_yyyy_mm_dd_format(self):
        result = self.validator._parse_date("1985-03-15")
        assert result == date(1985, 3, 15)

    def test_yymmdd_format_1900s(self):
        result = self.validator._parse_date("850315")
        assert result == date(1985, 3, 15)

    def test_yymmdd_format_2000s(self):
        result = self.validator._parse_date("280315")
        assert result == date(2028, 3, 15)

    def test_invalid_date_returns_none(self):
        result = self.validator._parse_date("not-a-date")
        assert result is None
