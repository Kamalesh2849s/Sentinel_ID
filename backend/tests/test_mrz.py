"""
Tests for MRZ parsing and check-digit validation.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.mrz.mrz_parser import (
    MRZParser, compute_check_digit, validate_check_digit, ParsedMRZ
)


class TestCheckDigit:
    """Test ICAO check digit algorithm."""

    def test_simple_digits(self):
        """ICAO check digit algorithm is internally consistent."""
        # Verify that computing a check digit and validating it always passes
        data = "740101"
        check = compute_check_digit(data)
        assert isinstance(check, int)
        assert 0 <= check <= 9
        assert validate_check_digit(data, str(check)) is True

    def test_alphanumeric(self):
        """Check digit for alphanumeric string."""
        # AB1234567 check digit (standard passport number)
        result = compute_check_digit("AB1234567")
        assert isinstance(result, int)
        assert 0 <= result <= 9

    def test_filler_chars(self):
        """Filler '<' characters have value 0."""
        result = compute_check_digit("<<<<<<<<<")
        assert result == 0

    def test_validate_correct(self):
        """Validation passes for correct check digit."""
        data = "740101"
        check = str(compute_check_digit(data))
        assert validate_check_digit(data, check) is True

    def test_validate_incorrect(self):
        """Validation fails for wrong check digit."""
        assert validate_check_digit("740101", "0") is False

    def test_validate_invalid_check_char(self):
        """Non-digit check character fails validation."""
        assert validate_check_digit("740101", "X") is False

    def test_empty_string(self):
        """Empty string produces check digit 0."""
        assert compute_check_digit("") == 0


class TestMRZParserTD3:
    """Test TD3 (passport) MRZ parsing."""

    def setup_method(self):
        self.parser = MRZParser()

    def _make_td3(self, doc_num="AB1234567", dob="850315", expiry="280315",
                  nationality="USA", surname="SMITH", given="JOHN"):
        """Build a synthetic TD3 MRZ for testing."""
        # Line 1: P<USASMITH<<JOHN<<<<<<<<<<<<<<<<<<<<<<<<<<<
        line1 = f"P<USA{surname}<<{given}".ljust(44, '<')[:44]

        # Compute check digits
        doc_check = compute_check_digit(doc_num.ljust(9, '<'))
        dob_check = compute_check_digit(dob)
        expiry_check = compute_check_digit(expiry)

        # Personal number (empty)
        personal = "<<<<<<<<<<<<<<"
        personal_check = compute_check_digit(personal)

        # Line 2
        doc_num_padded = doc_num.ljust(9, '<')[:9]
        line2_base = f"{doc_num_padded}{doc_check}{nationality}{dob}{dob_check}M{expiry}{expiry_check}{personal}{personal_check}"
        composite_data = line2_base[:10] + line2_base[13:20] + line2_base[21:43]
        composite_check = compute_check_digit(composite_data)
        line2 = line2_base + str(composite_check)
        line2 = line2.ljust(44, '<')[:44]

        return f"{line1}\n{line2}"

    def test_valid_td3_detected(self):
        mrz = self._make_td3()
        result = self.parser.parse(mrz)
        assert result.mrz_detected is True

    def test_td3_format_detection(self):
        mrz = self._make_td3()
        result = self.parser.parse(mrz)
        assert result.mrz_format == "TD3"

    def test_valid_check_digits(self):
        mrz = self._make_td3(doc_num="AB1234567", dob="850315", expiry="280315")
        result = self.parser.parse(mrz)
        assert result.check_digit_valid is True, f"Failures: {result.failure_reasons}"

    def test_nationality_extracted(self):
        mrz = self._make_td3(nationality="GBR")
        result = self.parser.parse(mrz)
        assert result.nationality == "GBR"

    def test_document_number_extracted(self):
        mrz = self._make_td3(doc_num="XY9876543")
        result = self.parser.parse(mrz)
        assert result.document_number == "XY9876543"

    def test_name_parsing(self):
        mrz = self._make_td3(surname="GARCIA", given="MARIA ELENA")
        result = self.parser.parse(mrz)
        assert "GARCIA" in result.surname.upper()

    def test_corrupted_mrz_fails(self):
        """MRZ with wrong check digit should fail."""
        # Manually corrupt a check digit
        mrz = self._make_td3()
        lines = mrz.split('\n')
        # Flip the doc check digit in line 2
        line2 = list(lines[1])
        line2[9] = '0' if line2[9] != '0' else '1'
        corrupted = lines[0] + '\n' + ''.join(line2)
        result = self.parser.parse(corrupted)
        assert result.check_digit_valid is False

    def test_empty_mrz_returns_no_detection(self):
        result = self.parser.parse("")
        assert result.mrz_detected is False

    def test_non_mrz_text_not_detected(self):
        result = self.parser.parse("Hello world\nThis is not an MRZ")
        assert result.mrz_detected is False


class TestMRZDateFormatting:
    """Test date formatting from YYMMDD."""

    def setup_method(self):
        self.parser = MRZParser()

    def test_year_1900s(self):
        """Years >= 30 → 19XX."""
        result = self.parser._format_date("850315")
        assert "1985" in result

    def test_year_2000s(self):
        """Years < 30 → 20XX."""
        result = self.parser._format_date("280315")
        assert "2028" in result

    def test_month_formatting(self):
        result = self.parser._format_date("850315")
        assert "03" in result

    def test_day_formatting(self):
        result = self.parser._format_date("850315")
        assert "15" in result


class TestMRZLineDetection:
    """Test MRZ line detection heuristics."""

    def setup_method(self):
        self.parser = MRZParser()

    def test_valid_mrz_line_detected(self):
        line = "P<USASMITH<<JOHN<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
        assert self.parser._is_mrz_like(line) is True

    def test_short_line_rejected(self):
        assert self.parser._is_mrz_like("HELLO") is False

    def test_text_line_rejected(self):
        assert self.parser._is_mrz_like("This is normal text with spaces!") is False
