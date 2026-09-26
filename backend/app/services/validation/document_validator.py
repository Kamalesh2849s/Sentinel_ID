"""
Rule-based document validation engine.
Validates document fields against business rules and consistency checks.
"""
import re
import logging
from datetime import datetime, date
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class ValidationCheck:
    """A single validation check result."""
    def __init__(
        self,
        check_name: str,
        category: str,
        status: str,
        message: str,
        severity: str = "LOW",
    ):
        self.check_name = check_name
        self.category = category
        self.status = status  # PASS, FAIL, WARNING, SKIPPED
        self.message = message
        self.severity = severity  # LOW, MEDIUM, HIGH

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_name": self.check_name,
            "category": self.category,
            "status": self.status,
            "message": self.message,
            "severity": self.severity,
        }


class DocumentValidator:
    """
    Validates extracted document fields against rules.
    Checks: format, dates, consistency, MRZ vs OCR fields.
    """

    # Document number patterns by type
    PASSPORT_NUMBER_PATTERN = re.compile(r'^[A-Z0-9]{6,12}$')

    # Valid sex values
    VALID_SEX = {'M', 'F', 'X', '<'}

    # Valid ICAO country codes (sample — full list has 193+ codes)
    KNOWN_COUNTRY_CODES = {
        'USA', 'GBR', 'CAN', 'AUS', 'DEU', 'FRA', 'ITA', 'ESP', 'JPN',
        'CHN', 'IND', 'BRA', 'MEX', 'RUS', 'ZAF', 'NGA', 'EGY', 'KEN',
        'ARG', 'COL', 'PHL', 'IDN', 'PAK', 'BGD', 'THA', 'VNM', 'MYS',
        'SGP', 'NZL', 'ARE', 'SAU', 'KOR', 'TWN', 'HKG', 'GHA', 'ETH',
        'UGA', 'TZA', 'ZWE', 'ZMB', 'CMR', 'SEN', 'CIV', 'MDG', 'MOZ',
        'UNK',  # Unknown — MRZ filler
    }

    def validate_document_fields(
        self,
        extracted_data: Dict[str, Any],
        document_type: str = "passport",
    ) -> List[ValidationCheck]:
        """Run all document validation checks. Returns list of ValidationCheck."""
        checks = []

        # Required fields check
        checks.extend(self._check_required_fields(extracted_data, document_type))

        # Document number format
        if extracted_data.get("document_number"):
            checks.append(self._check_document_number(extracted_data["document_number"]))

        # Date validations
        if extracted_data.get("expiry_date"):
            checks.append(self._check_expiry_date(extracted_data["expiry_date"]))

        if extracted_data.get("date_of_birth"):
            checks.append(self._check_birth_date(extracted_data["date_of_birth"]))

        if extracted_data.get("issue_date") and extracted_data.get("expiry_date"):
            checks.append(
                self._check_date_consistency(
                    extracted_data["issue_date"],
                    extracted_data["expiry_date"],
                )
            )

        if extracted_data.get("date_of_birth") and extracted_data.get("issue_date"):
            checks.append(
                self._check_age_at_issue(
                    extracted_data["date_of_birth"],
                    extracted_data["issue_date"],
                )
            )

        # Sex field
        if extracted_data.get("sex"):
            checks.append(self._check_sex_field(extracted_data["sex"]))

        # Nationality/country codes
        if extracted_data.get("nationality"):
            checks.append(self._check_country_code(extracted_data["nationality"], "Nationality"))

        if extracted_data.get("issuing_country"):
            checks.append(self._check_country_code(extracted_data["issuing_country"], "Issuing country"))

        return checks

    def validate_mrz_vs_ocr(
        self,
        mrz_data: Dict[str, Any],
        ocr_data: Dict[str, Any],
        document_type: str = "passport",
    ) -> List[ValidationCheck]:
        """Compare MRZ extracted fields against OCR extracted fields."""
        checks = []

        if not mrz_data.get("mrz_detected"):
            is_passport = "passport" in str(document_type).lower()
            checks.append(ValidationCheck(
                check_name="MRZ Presence",
                category="mrz",
                status="FAIL" if is_passport else "SKIPPED",
                message="No MRZ zone detected in passport" if is_passport else "MRZ zone not applicable/required for this document type",
                severity="HIGH" if is_passport else "LOW",
            ))
            return checks

        # Compare document number
        mrz_doc_num = mrz_data.get("document_number", "").upper().strip()
        ocr_doc_num = (ocr_data.get("document_number") or "").upper().strip()
        if mrz_doc_num and ocr_doc_num:
            if mrz_doc_num == ocr_doc_num:
                checks.append(ValidationCheck(
                    check_name="Document Number Consistency",
                    category="identity",
                    status="PASS",
                    message=f"Document number matches between MRZ and visual zone ({mrz_doc_num})",
                    severity="LOW",
                ))
            else:
                checks.append(ValidationCheck(
                    check_name="Document Number Consistency",
                    category="identity",
                    status="FAIL",
                    message=f"Document number mismatch: MRZ={mrz_doc_num}, OCR={ocr_doc_num}",
                    severity="HIGH",
                ))

        # Compare expiry date
        mrz_expiry = mrz_data.get("expiry_date", "")
        ocr_expiry = ocr_data.get("expiry_date", "")
        if mrz_expiry and ocr_expiry:
            # Normalize dates for comparison
            mrz_norm = self._normalize_date_for_comparison(mrz_expiry)
            ocr_norm = self._normalize_date_for_comparison(ocr_expiry)
            if mrz_norm == ocr_norm or mrz_norm in ocr_norm or ocr_norm in mrz_norm:
                checks.append(ValidationCheck(
                    check_name="Expiry Date Consistency",
                    category="identity",
                    status="PASS",
                    message="Expiry date matches between MRZ and visual zone",
                    severity="LOW",
                ))
            else:
                checks.append(ValidationCheck(
                    check_name="Expiry Date Consistency",
                    category="identity",
                    status="WARNING",
                    message=f"Expiry date may differ: MRZ={mrz_expiry}, OCR={ocr_expiry}",
                    severity="MEDIUM",
                ))

        # MRZ check digit validation
        checks.append(ValidationCheck(
            check_name="MRZ Check Digits",
            category="mrz",
            status="PASS" if mrz_data.get("check_digit_valid") else "FAIL",
            message=(
                "All MRZ check digits are valid"
                if mrz_data.get("check_digit_valid")
                else f"MRZ check digit validation failed: {'; '.join(mrz_data.get('failure_reasons', []))}"
            ),
            severity="LOW" if mrz_data.get("check_digit_valid") else "HIGH",
        ))

        # MRZ structure
        checks.append(ValidationCheck(
            check_name="MRZ Structure",
            category="mrz",
            status="PASS" if mrz_data.get("valid_structure") else "FAIL",
            message=(
                f"MRZ structure is valid ({mrz_data.get('mrz_format', 'unknown')} format)"
                if mrz_data.get("valid_structure")
                else "MRZ structure is invalid or malformed"
            ),
            severity="LOW" if mrz_data.get("valid_structure") else "HIGH",
        ))

        return checks

    def _check_required_fields(
        self, data: Dict[str, Any], doc_type: str
    ) -> List[ValidationCheck]:
        """Check that required fields are present."""
        checks = []
        doc_type_lower = str(doc_type).lower()
        if "passport" in doc_type_lower:
            required = ["document_number", "date_of_birth", "expiry_date", "full_name"]
        elif any(k in doc_type_lower for k in ("id", "aadhaar", "national")):
            required = ["document_number", "full_name"]
        elif "visa" in doc_type_lower:
            required = ["document_number", "full_name", "expiry_date"]
        else:
            required = ["document_number", "full_name"]

        for field in required:
            value = data.get(field)
            if not value:
                checks.append(ValidationCheck(
                    check_name=f"Required Field: {field}",
                    category="document",
                    status="FAIL",
                    message=f"Required field '{field}' is missing or empty",
                    severity="MEDIUM",
                ))
            else:
                checks.append(ValidationCheck(
                    check_name=f"Required Field: {field}",
                    category="document",
                    status="PASS",
                    message=f"Field '{field}' is present",
                    severity="LOW",
                ))

        return checks

    def _check_document_number(self, doc_number: str) -> ValidationCheck:
        """Validate document number format."""
        clean = doc_number.strip().upper()
        if self.PASSPORT_NUMBER_PATTERN.match(clean):
            return ValidationCheck(
                check_name="Document Number Format",
                category="document",
                status="PASS",
                message=f"Document number format is valid ({clean})",
                severity="LOW",
            )
        return ValidationCheck(
            check_name="Document Number Format",
            category="document",
            status="WARNING",
            message=f"Document number '{clean}' does not match expected format",
            severity="MEDIUM",
        )

    def _check_expiry_date(self, expiry_date: str) -> ValidationCheck:
        """Check if document is expired."""
        parsed = self._parse_date(expiry_date)
        if not parsed:
            return ValidationCheck(
                check_name="Expiry Date Format",
                category="document",
                status="WARNING",
                message=f"Cannot parse expiry date: {expiry_date}",
                severity="MEDIUM",
            )

        today = date.today()
        if parsed < today:
            days_expired = (today - parsed).days
            return ValidationCheck(
                check_name="Document Expiry",
                category="document",
                status="FAIL",
                message=f"Document expired {days_expired} days ago (expired: {parsed})",
                severity="HIGH",
            )
        elif (parsed - today).days < 90:
            days_remaining = (parsed - today).days
            return ValidationCheck(
                check_name="Document Expiry",
                category="document",
                status="WARNING",
                message=f"Document expires in {days_remaining} days — may be near expiry",
                severity="MEDIUM",
            )

        return ValidationCheck(
            check_name="Document Expiry",
            category="document",
            status="PASS",
            message=f"Document is valid until {parsed}",
            severity="LOW",
        )

    def _check_birth_date(self, dob: str) -> ValidationCheck:
        """Validate birth date is reasonable."""
        parsed = self._parse_date(dob)
        if not parsed:
            return ValidationCheck(
                check_name="Birth Date Format",
                category="document",
                status="WARNING",
                message=f"Cannot parse birth date: {dob}",
                severity="MEDIUM",
            )

        today = date.today()
        age = (today - parsed).days // 365
        if age < 0 or age > 120:
            return ValidationCheck(
                check_name="Birth Date Validity",
                category="document",
                status="FAIL",
                message=f"Birth date implies impossible age: {age} years",
                severity="HIGH",
            )

        return ValidationCheck(
            check_name="Birth Date Validity",
            category="document",
            status="PASS",
            message=f"Birth date is valid (age: ~{age} years)",
            severity="LOW",
        )

    def _check_date_consistency(self, issue_date: str, expiry_date: str) -> ValidationCheck:
        """Check that expiry date is after issue date."""
        issue = self._parse_date(issue_date)
        expiry = self._parse_date(expiry_date)

        if not issue or not expiry:
            return ValidationCheck(
                check_name="Date Consistency",
                category="document",
                status="SKIPPED",
                message="Could not compare issue and expiry dates — parse error",
                severity="LOW",
            )

        if expiry <= issue:
            return ValidationCheck(
                check_name="Date Consistency",
                category="document",
                status="FAIL",
                message=f"Expiry date ({expiry}) is not after issue date ({issue})",
                severity="HIGH",
            )

        validity_years = (expiry - issue).days / 365
        if validity_years > 15:
            return ValidationCheck(
                check_name="Date Consistency",
                category="document",
                status="WARNING",
                message=f"Unusually long validity period: {validity_years:.1f} years",
                severity="MEDIUM",
            )

        return ValidationCheck(
            check_name="Date Consistency",
            category="document",
            status="PASS",
            message=f"Issue and expiry dates are consistent ({validity_years:.1f} year validity)",
            severity="LOW",
        )

    def _check_age_at_issue(self, dob: str, issue_date: str) -> ValidationCheck:
        """Check age at document issuance is reasonable."""
        birth = self._parse_date(dob)
        issue = self._parse_date(issue_date)

        if not birth or not issue:
            return ValidationCheck(
                check_name="Age at Issue",
                category="document",
                status="SKIPPED",
                message="Cannot verify age at issuance",
                severity="LOW",
            )

        age_at_issue = (issue - birth).days // 365
        if age_at_issue < 0:
            return ValidationCheck(
                check_name="Age at Issue",
                category="document",
                status="FAIL",
                message="Issue date is before birth date — impossible",
                severity="HIGH",
            )

        return ValidationCheck(
            check_name="Age at Issue",
            category="document",
            status="PASS",
            message=f"Age at document issuance: {age_at_issue} years — reasonable",
            severity="LOW",
        )

    def _check_sex_field(self, sex: str) -> ValidationCheck:
        """Validate sex field value."""
        if sex.upper() in self.VALID_SEX:
            return ValidationCheck(
                check_name="Sex Field",
                category="document",
                status="PASS",
                message=f"Sex field is valid: {sex}",
                severity="LOW",
            )
        return ValidationCheck(
            check_name="Sex Field",
            category="document",
            status="WARNING",
            message=f"Unexpected sex field value: '{sex}' (expected M, F, or X)",
            severity="LOW",
        )

    def _check_country_code(self, code: str, field_name: str) -> ValidationCheck:
        """Check if country code is known."""
        clean = code.strip().upper()
        if clean in self.KNOWN_COUNTRY_CODES or (len(clean) == 3 and clean.isalpha()):
            return ValidationCheck(
                check_name=f"{field_name} Code",
                category="document",
                status="PASS",
                message=f"{field_name} code is valid: {clean}",
                severity="LOW",
            )
        return ValidationCheck(
            check_name=f"{field_name} Code",
            category="document",
            status="WARNING",
            message=f"{field_name} code '{clean}' is not a known ISO 3166-1 alpha-3 code",
            severity="LOW",
        )

    def _parse_date(self, date_str: str) -> Optional[date]:
        """Try to parse various date formats."""
        if not date_str:
            return None

        formats = [
            "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y",
            "%d %m %Y", "%m/%d/%Y", "%d/%m/%y",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except ValueError:
                continue

        # Try 6-digit YYMMDD (MRZ format)
        if re.match(r'^\d{6}$', date_str.strip()):
            try:
                yy = int(date_str[0:2])
                mm = int(date_str[2:4])
                dd = int(date_str[4:6])
                year = 1900 + yy if yy >= 30 else 2000 + yy
                return date(year, mm, dd)
            except ValueError:
                pass

        return None

    def _normalize_date_for_comparison(self, date_str: str) -> str:
        """Normalize date string for comparison."""
        parsed = self._parse_date(date_str)
        if parsed:
            return parsed.strftime("%Y-%m-%d")
        return date_str.strip()


document_validator = DocumentValidator()
