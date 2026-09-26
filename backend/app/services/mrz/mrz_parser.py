"""
MRZ (Machine Readable Zone) parser for ICAO 9303 standard documents.
Supports TD1 (3-line, 30 chars), TD2 (2-line, 36 chars), TD3 (2-line, 44 chars / passport).
Fully implements exact positional parsing, check digit validation, raw/normalized line preservation,
and unambiguous character resolution per field type.
"""
import re
import logging
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

MRZ_WEIGHTS = [7, 3, 1]
FILLER = "<"

MONTH_NAMES = {
    "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
    "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
    "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
}


def compute_check_digit(data: str) -> int:
    """
    Compute standard ICAO MRZ check digit for a string.
    Character values:
      0-9 -> 0-9
      A-Z -> 10-35
      < -> 0
    Weights repeat: 7, 3, 1
    Returns value modulo 10.
    """
    total = 0
    for i, char in enumerate(data.upper()):
        if char == FILLER:
            value = 0
        elif char.isdigit():
            value = int(char)
        elif char.isalpha():
            value = ord(char) - ord('A') + 10
        else:
            value = 0
        total += value * MRZ_WEIGHTS[i % 3]
    return total % 10


def validate_check_digit(data: str, check_char: str) -> bool:
    """Validate that check_char matches computed check digit for data."""
    if not check_char or not check_char.isdigit():
        return False
    return compute_check_digit(data) == int(check_char)


def normalize_mrz_date(yymmdd: str, is_expiry: bool = False) -> Dict[str, Any]:
    """
    Normalize a YYMMDD MRZ date string.
    Century resolution rule:
      For expiry date: YY <= 80 -> 20YY, YY > 80 -> 19YY
      For DOB: YY >= 30 -> 19YY, YY < 30 -> 20YY
    Returns dict with: raw, normalized, iso, year, month, day, century_rule, valid
    """
    result: Dict[str, Any] = {
        "raw": yymmdd,
        "normalized": None,
        "iso": None,
        "year": None,
        "month": None,
        "day": None,
        "century_rule": None,
        "valid": False,
    }
    if not yymmdd or len(yymmdd) < 6:
        return result
    try:
        yy = int(yymmdd[0:2])
        mm = int(yymmdd[2:4])
        dd = int(yymmdd[4:6])
    except (ValueError, IndexError):
        return result
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        return result

    if is_expiry:
        if yy <= 80:
            year = 2000 + yy
            century_rule = f"Expiry YY={yy:02d} <= 80 assumed 20XX"
        else:
            year = 1900 + yy
            century_rule = f"Expiry YY={yy:02d} > 80 assumed 19XX"
    else:
        if yy >= 30:
            year = 1900 + yy
            century_rule = f"DOB YY={yy:02d} >= 30 assumed 19XX"
        else:
            year = 2000 + yy
            century_rule = f"DOB YY={yy:02d} < 30 assumed 20XX"

    month_name = MONTH_NAMES.get(f"{mm:02d}", f"{mm:02d}")
    result.update({
        "normalized": f"{dd:02d} {month_name} {year}",
        "iso": f"{year}-{mm:02d}-{dd:02d}",
        "year": year,
        "month": mm,
        "day": dd,
        "century_rule": century_rule,
        "valid": True,
    })
    return result


@dataclass
class CheckDigitResult:
    """Result of a single ICAO check digit validation."""
    field_name: str
    data: str
    expected_digit: str
    computed_digit: int
    passed: bool
    applicable: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_name": self.field_name,
            "data": self.data,
            "expected_digit": self.expected_digit,
            "computed_digit": self.computed_digit,
            "passed": self.passed,
            "applicable": self.applicable,
        }


@dataclass
class ParsedMRZ:
    """Structured output of MRZ parsing."""
    mrz_detected: bool = False
    mrz_status: str = "NOT_DETECTED"
    raw_mrz: str = ""
    raw_mrz_lines: List[str] = field(default_factory=list)
    normalized_mrz: str = ""
    normalized_mrz_lines: List[str] = field(default_factory=list)
    line1: str = ""
    line2: str = ""
    line3: str = ""
    mrz_format: str = ""
    valid_structure: bool = False
    document_type: str = ""
    issuing_country_code: str = ""
    nationality_code: str = ""
    document_number: str = ""
    document_number_raw: str = ""
    date_of_birth: str = ""
    date_of_birth_raw: str = ""
    date_of_birth_normalized: Optional[Dict] = None
    expiry_date: str = ""
    expiry_date_raw: str = ""
    expiry_date_normalized: Optional[Dict] = None
    sex: str = ""
    surname: str = ""
    given_names: str = ""
    full_name: str = ""
    optional_data: str = ""
    personal_number: str = ""
    document_number_check: str = ""
    document_number_check_result: Optional[CheckDigitResult] = None
    dob_check: str = ""
    dob_check_result: Optional[CheckDigitResult] = None
    expiry_check: str = ""
    expiry_check_result: Optional[CheckDigitResult] = None
    optional_data_check: str = ""
    optional_data_check_result: Optional[CheckDigitResult] = None
    composite_check: str = ""
    composite_check_result: Optional[CheckDigitResult] = None
    check_digit_valid: bool = False
    all_check_digits_valid: bool = False
    field_consistency: bool = False
    failure_reasons: List[str] = field(default_factory=list)

    @property
    def issuing_country(self) -> str:
        return self.issuing_country_code

    @property
    def nationality(self) -> str:
        return self.nationality_code

    def get_full_name(self) -> str:
        if self.full_name:
            return self.full_name
        parts = []
        if self.surname:
            parts.append(self.surname)
        if self.given_names:
            parts.append(self.given_names)
        return " ".join(parts).strip()

    def get_mrz_overall_status(self) -> str:
        if not self.mrz_detected:
            return "NOT_DETECTED"
        if not self.valid_structure:
            return "INVALID"

        # Check mandatory check digits
        checks = []
        if self.document_number_check_result and self.document_number_check_result.applicable:
            checks.append(self.document_number_check_result.passed)
        if self.dob_check_result and self.dob_check_result.applicable:
            checks.append(self.dob_check_result.passed)
        if self.expiry_check_result and self.expiry_check_result.applicable:
            checks.append(self.expiry_check_result.passed)
        if self.composite_check_result and self.composite_check_result.applicable:
            checks.append(self.composite_check_result.passed)

        if not checks:
            return "VALID" if self.valid_structure else "INVALID"

        if all(checks):
            return "VALID"
        elif any(checks):
            return "PARTIALLY VALID"
        else:
            return "INVALID"

    @property
    def check_digits_dict(self) -> Dict[str, Any]:
        return {
            "document_number": self.document_number_check_result.passed if self.document_number_check_result else None,
            "date_of_birth": self.dob_check_result.passed if self.dob_check_result else None,
            "date_of_expiry": self.expiry_check_result.passed if self.expiry_check_result else None,
            "composite": self.composite_check_result.passed if self.composite_check_result else None,
        }

    def to_dict(self) -> Dict[str, Any]:
        is_detected = bool(self.mrz_detected and self.valid_structure)
        dob_norm = self.date_of_birth_normalized or {}
        exp_norm = self.expiry_date_normalized or {}

        def _cd(r: Optional[CheckDigitResult]) -> Optional[Dict]:
            return r.to_dict() if r else None

        overall_status = self.get_mrz_overall_status()

        structured_fields = {
            "document_type": self.document_type,
            "issuing_country_code": self.issuing_country_code,
            "full_name": self.get_full_name(),
            "document_number": self.document_number,
            "nationality_code": self.nationality_code,
            "date_of_birth": self.date_of_birth,
            "sex": self.sex,
            "date_of_expiry": self.expiry_date,
            "optional_data": self.optional_data,
            "check_digits": self.check_digits_dict,
        }

        return {
            "mrz_detected": self.mrz_detected,
            "mrz_status": overall_status,
            "raw_mrz": self.raw_mrz,
            "raw_mrz_lines": self.raw_mrz_lines,
            "normalized_mrz": self.normalized_mrz,
            "normalized_mrz_lines": self.normalized_mrz_lines,
            "line1": self.line1 if is_detected else "",
            "line2": self.line2 if is_detected else "",
            "line3": self.line3 if (is_detected and self.mrz_format == "TD1") else "",
            "mrz_format": self.mrz_format,
            "valid_structure": self.valid_structure,
            "document_type": self.document_type,
            "issuing_country_code": self.issuing_country_code,
            "nationality_code": self.nationality_code,
            # Legacy aliases
            "issuing_country": self.issuing_country_code,
            "nationality": self.nationality_code,
            "document_number": self.document_number,
            "surname": self.surname,
            "given_names": self.given_names,
            "full_name": self.get_full_name(),
            "full_name_mrz": self.get_full_name(),
            "sex": self.sex,
            "optional_data": self.optional_data,
            "date_of_birth": self.date_of_birth,
            "expiry_date": self.expiry_date,
            "date_of_birth_raw": self.date_of_birth_raw,
            "expiry_date_raw": self.expiry_date_raw,
            "date_of_birth_normalized": dob_norm,
            "expiry_date_normalized": exp_norm,
            "date_of_issue": None,
            "date_of_issue_source": "OCR",
            "passport_number_check": self.document_number_check_result.passed if self.document_number_check_result else None,
            "passport_number_check_detail": _cd(self.document_number_check_result),
            "dob_check": self.dob_check_result.passed if self.dob_check_result else None,
            "dob_check_detail": _cd(self.dob_check_result),
            "expiry_check": self.expiry_check_result.passed if self.expiry_check_result else None,
            "expiry_check_detail": _cd(self.expiry_check_result),
            "optional_data_check": self.optional_data_check_result.passed if self.optional_data_check_result else None,
            "optional_data_check_detail": _cd(self.optional_data_check_result),
            "composite_check": self.composite_check_result.passed if self.composite_check_result else None,
            "composite_check_detail": _cd(self.composite_check_result),
            "check_digits": self.check_digits_dict,
            "check_digit_valid": self.check_digit_valid,
            "all_check_digits_valid": self.all_check_digits_valid,
            "field_consistency": self.field_consistency,
            "failure_reasons": self.failure_reasons,
            "mrz_parsed_fields": structured_fields,
        }


class MRZParser:
    """ICAO 9303 MRZ parser — TD1, TD2, TD3 with full check-digit validation."""

    def parse(self, mrz_input: Any) -> ParsedMRZ:
        """
        Parse MRZ text or lines into ParsedMRZ with exact positional parsing.
        """
        result = ParsedMRZ()
        if not mrz_input:
            result.failure_reasons.append("Empty MRZ input")
            return result

        # Accept string or list of lines
        if isinstance(mrz_input, list):
            raw_lines = [str(l) for l in mrz_input if str(l).strip()]
            raw_text = "\n".join(raw_lines)
        else:
            raw_text = str(mrz_input)
            raw_lines = [l for l in raw_text.split('\n') if l.strip()]

        if not raw_lines:
            result.failure_reasons.append("No MRZ lines found")
            return result

        # Preserve exact raw text and lines
        result.raw_mrz = raw_text
        result.raw_mrz_lines = list(raw_lines)

        # ── Smart Line Filtering & Format Detection ──────────────────────────
        candidate_lines = [self._clean_line_boundary(l) for l in raw_lines]
        candidate_lines = [l for l in candidate_lines if len(l) >= 20 and self._is_mrz_like(l)]

        if not candidate_lines:
            result.failure_reasons.append("No valid MRZ-like lines detected")
            return result

        # 1. Check for TD3 (Passport: 2 lines of ~44 chars, line 1 starts with P)
        td3_match = self._find_td3_lines(candidate_lines)
        if td3_match:
            return self._parse_td3(td3_match, result)

        # 2. Check for TD1 (ID Card: 3 lines of ~30 chars)
        td1_match = self._find_td1_lines(candidate_lines)
        if td1_match:
            return self._parse_td1(td1_match, result)

        # 3. Check for TD2 (2 lines of ~36 chars)
        td2_match = self._find_td2_lines(candidate_lines)
        if td2_match:
            return self._parse_td2(td2_match, result)

        # Fallback heuristic based on length closeness
        if len(candidate_lines) >= 2:
            avg_len = sum(len(l) for l in candidate_lines[:2]) / 2.0
            if avg_len >= 40:
                padded = [candidate_lines[0].ljust(44, '<')[:44], candidate_lines[1].ljust(44, '<')[:44]]
                result.failure_reasons.append("Using TD3 fallback for detected candidate lines")
                return self._parse_td3(padded, result)
            elif avg_len >= 33:
                padded = [candidate_lines[0].ljust(36, '<')[:36], candidate_lines[1].ljust(36, '<')[:36]]
                result.failure_reasons.append("Using TD2 fallback for detected candidate lines")
                return self._parse_td2(padded, result)
            elif len(candidate_lines) >= 3 and avg_len <= 33:
                padded = [candidate_lines[0].ljust(30, '<')[:30], candidate_lines[1].ljust(30, '<')[:30], candidate_lines[2].ljust(30, '<')[:30]]
                result.failure_reasons.append("Using TD1 fallback for detected candidate lines")
                return self._parse_td1(padded, result)

        result.mrz_detected = True
        result.mrz_status = "INVALID"
        result.failure_reasons.append(f"Unable to match lines to standard MRZ format (found {len(candidate_lines)} lines)")
        return result

    # ─── Format Finding Helpers ────────────────────────────────────────────────

    def _clean_line_boundary(self, line: str) -> str:
        """Strip leading/trailing noise (like '|', spaces) while preserving '<'."""
        s = line.strip().strip('|').strip(':').strip(';').strip('~').strip('!').strip()
        # Remove internal spaces since MRZ has no spaces
        s = s.replace(' ', '').replace('\t', '')
        return s.upper()

    def _find_td3_lines(self, lines: List[str]) -> Optional[List[str]]:
        """Look for a 2-line TD3 pair (approx 44 chars each, line 1 starting with P< or P)."""
        # Look for explicit P< or P prefix
        for i in range(len(lines)):
            l1 = lines[i]
            if (l1.startswith('P<') or (len(l1) >= 2 and l1[0] == 'P' and l1[1].isalpha())) and 38 <= len(l1) <= 50:
                for j in range(i + 1, min(i + 3, len(lines))):
                    l2 = lines[j]
                    if 38 <= len(l2) <= 50:
                        return [l1.ljust(44, '<')[:44], l2.ljust(44, '<')[:44]]

        # Length 44 exact matches
        exact_44 = [l for l in lines if len(l) == 44]
        if len(exact_44) >= 2:
            return exact_44[:2]

        # Close to 44
        close_44 = [l for l in lines if abs(len(l) - 44) <= 4]
        if len(close_44) >= 2:
            return [close_44[0].ljust(44, '<')[:44], close_44[1].ljust(44, '<')[:44]]

        return None

    def _find_td1_lines(self, lines: List[str]) -> Optional[List[str]]:
        """Look for 3 lines of TD1 (approx 30 chars each)."""
        exact_30 = [l for l in lines if len(l) == 30]
        if len(exact_30) >= 3:
            return exact_30[:3]

        close_30 = [l for l in lines if abs(len(l) - 30) <= 3]
        if len(close_30) >= 3:
            return [close_30[0].ljust(30, '<')[:30], close_30[1].ljust(30, '<')[:30], close_30[2].ljust(30, '<')[:30]]

        return None

    def _find_td2_lines(self, lines: List[str]) -> Optional[List[str]]:
        """Look for 2 lines of TD2 (approx 36 chars each)."""
        exact_36 = [l for l in lines if len(l) == 36]
        if len(exact_36) >= 2:
            return exact_36[:2]

        close_36 = [l for l in lines if abs(len(l) - 36) <= 4]
        if len(close_36) >= 2:
            return [close_36[0].ljust(36, '<')[:36], close_36[1].ljust(36, '<')[:36]]

        return None

    # ─── TD3 Parsing ──────────────────────────────────────────────────────────

    def _parse_td3(self, lines: List[str], result: ParsedMRZ) -> ParsedMRZ:
        """
        Parse TD3 passport MRZ with exact positional parsing:
        Line 1 (44 chars):
          [0:2]   Document type
          [2:5]   Issuing country code
          [5:44]  Name: SURNAME<<GIVEN<NAMES
        Line 2 (44 chars):
          [0:9]   Document number
          [9]     Document number check digit
          [10:13] Nationality code
          [13:19] Date of birth (YYMMDD)
          [19]    DOB check digit
          [20]    Sex (M/F/X/<)
          [21:27] Expiry date (YYMMDD)
          [27]    Expiry check digit
          [28:42] Optional data
          [42]    Optional data check digit
          [43]    Composite check digit
        """
        result.mrz_detected = True
        result.mrz_format = "TD3"
        line1 = lines[0].ljust(44, '<')[:44]
        line2 = lines[1].ljust(44, '<')[:44]

        result.line1 = line1
        result.line2 = line2
        result.normalized_mrz_lines = [line1, line2]
        result.normalized_mrz = f"{line1}\n{line2}"

        # ── Line 1 ──
        result.document_type = line1[0:2].replace('<', '').strip()
        result.issuing_country_code = self._clean_alpha_field(line1[2:5])
        result.surname, result.given_names, result.full_name = self._parse_name_field(line1[5:44])

        # ── Line 2 ──
        doc_num_raw = line2[0:9]
        result.document_number_raw = doc_num_raw
        result.document_number = doc_num_raw.replace('<', '').strip()
        result.document_number_check = self._clean_digit(line2[9])

        result.nationality_code = self._clean_alpha_field(line2[10:13])

        # Date of Birth (strictly numeric YYMMDD)
        dob_raw = self._clean_numeric_field(line2[13:19])
        result.date_of_birth_raw = dob_raw
        dob_norm = normalize_mrz_date(dob_raw, is_expiry=False)
        result.date_of_birth_normalized = dob_norm
        result.date_of_birth = dob_norm.get("normalized") or self._fmt_date(dob_raw, is_expiry=False)
        result.dob_check = self._clean_digit(line2[19])

        # Sex
        sex_char = line2[20].upper()
        result.sex = sex_char if sex_char in ('M', 'F', 'X') else ('<' if sex_char == '<' else '')

        # Expiry Date (strictly numeric YYMMDD)
        exp_raw = self._clean_numeric_field(line2[21:27])
        result.expiry_date_raw = exp_raw
        exp_norm = normalize_mrz_date(exp_raw, is_expiry=True)
        result.expiry_date_normalized = exp_norm
        result.expiry_date = exp_norm.get("normalized") or self._fmt_date(exp_raw, is_expiry=True)
        result.expiry_check = self._clean_digit(line2[27])

        # Optional data
        optional_raw = line2[28:42]
        result.optional_data = optional_raw.replace('<', '').strip()
        result.personal_number = result.optional_data
        result.optional_data_check = line2[42]

        # Composite check digit
        composite_char = self._clean_digit(line2[43])
        result.composite_check = composite_char

        result.valid_structure = True

        # ── Check Digits Calculation ──
        failures = []

        # 1. Document number check digit
        # If check fails with raw string, test single ambiguity correction (O<->0, I<->1, B<->8)
        dn_computed = compute_check_digit(doc_num_raw)
        dn_passed = (str(dn_computed) == str(result.document_number_check))

        if not dn_passed:
            # Check if an OCR ambiguity substitution satisfies the check digit
            for i, c in enumerate(doc_num_raw):
                subs = []
                if c == 'O': subs.append('0')
                elif c == '0': subs.append('O')
                elif c in ('I', 'l'): subs.append('1')
                elif c == '1': subs.append('I')
                elif c == 'B': subs.append('8')
                elif c == '8': subs.append('B')
                elif c == 'S': subs.append('5')
                elif c == '5': subs.append('S')
                elif c == 'Z': subs.append('2')
                elif c == '2': subs.append('Z')

                for sub in subs:
                    candidate = doc_num_raw[:i] + sub + doc_num_raw[i+1:]
                    if compute_check_digit(candidate) == int(result.document_number_check):
                        doc_num_raw = candidate
                        result.document_number_raw = candidate
                        result.document_number = candidate.replace('<', '').strip()
                        dn_computed = int(result.document_number_check)
                        dn_passed = True
                        break
                if dn_passed:
                    break

        dn_r = CheckDigitResult(
            field_name="Document Number",
            data=doc_num_raw,
            expected_digit=result.document_number_check,
            computed_digit=dn_computed,
            passed=dn_passed,
        )
        result.document_number_check_result = dn_r
        if not dn_passed:
            failures.append(f"Doc number check failed: computed {dn_computed}, got '{result.document_number_check}'")

        # 2. Date of birth check digit
        dob_computed = compute_check_digit(dob_raw)
        dob_passed = (str(dob_computed) == str(result.dob_check))
        dob_r = CheckDigitResult(
            field_name="Date of Birth",
            data=dob_raw,
            expected_digit=result.dob_check,
            computed_digit=dob_computed,
            passed=dob_passed,
        )
        result.dob_check_result = dob_r
        if not dob_passed:
            failures.append(f"DOB check failed: computed {dob_computed}, got '{result.dob_check}'")

        # 3. Expiry date check digit
        exp_computed = compute_check_digit(exp_raw)
        exp_passed = (str(exp_computed) == str(result.expiry_check))
        exp_r = CheckDigitResult(
            field_name="Expiry Date",
            data=exp_raw,
            expected_digit=result.expiry_check,
            computed_digit=exp_computed,
            passed=exp_passed,
        )
        result.expiry_check_result = exp_r
        if not exp_passed:
            failures.append(f"Expiry check failed: computed {exp_computed}, got '{result.expiry_check}'")

        # 4. Optional data check digit
        opt_filler = all(c == '<' for c in optional_raw)
        opt_computed = compute_check_digit(optional_raw)
        opt_passed = validate_check_digit(optional_raw, result.optional_data_check) or opt_filler
        opt_r = CheckDigitResult(
            field_name="Optional Data",
            data=optional_raw,
            expected_digit=result.optional_data_check,
            computed_digit=opt_computed,
            passed=opt_passed,
            applicable=not opt_filler,
        )
        result.optional_data_check_result = opt_r

        # 5. Composite check digit
        composite_data = line2[0:10] + line2[13:20] + line2[21:43]
        comp_computed = compute_check_digit(composite_data)
        comp_passed = (str(comp_computed) == str(composite_char))
        comp_r = CheckDigitResult(
            field_name="Composite",
            data=composite_data,
            expected_digit=composite_char,
            computed_digit=comp_computed,
            passed=comp_passed,
        )
        result.composite_check_result = comp_r
        if not comp_passed:
            failures.append(f"Composite check failed: computed {comp_computed}, got '{composite_char}'")

        result.failure_reasons = failures
        mandatory_ok = dn_passed and dob_passed and exp_passed and comp_passed
        result.check_digit_valid = mandatory_ok
        result.all_check_digits_valid = mandatory_ok
        result.field_consistency = mandatory_ok and result.valid_structure
        result.mrz_status = result.get_mrz_overall_status()

        # Temporary debugging logs as required by Bug 1 (#22)
        print(f"[MRZ] Raw lines: {result.raw_mrz_lines}")
        print(f"[MRZ] Detected format: {result.mrz_format}")
        print(f"[MRZ] Normalized lines: {result.normalized_mrz_lines}")
        print(f"[MRZ] Parsed name: {result.full_name}")
        print(f"[MRZ] Parsed nationality: {result.nationality_code}")
        print(f"[MRZ] Parsed DOB: {result.date_of_birth}")
        print(f"[MRZ] Parsed expiry: {result.expiry_date}")
        print(f"[MRZ] Document number: {result.document_number}")
        print(f"[MRZ] Check digit results: {result.check_digits_dict}")
        print(f"[MRZ] Overall status: {result.mrz_status}")

        logger.info(f"[MRZ] Parsed {result.mrz_format}: status={result.mrz_status}, doc={result.document_number}, name={result.full_name}")
        return result

    # ─── TD2 Parsing ──────────────────────────────────────────────────────────

    def _parse_td2(self, lines: List[str], result: ParsedMRZ) -> ParsedMRZ:
        """Parse TD2: 2 lines x 36 chars."""
        result.mrz_detected = True
        result.mrz_format = "TD2"
        line1 = lines[0].ljust(36, '<')[:36]
        line2 = lines[1].ljust(36, '<')[:36] if len(lines) > 1 else '<' * 36

        result.line1 = line1
        result.line2 = line2
        result.normalized_mrz_lines = [line1, line2]
        result.normalized_mrz = f"{line1}\n{line2}"

        result.document_type = line1[0:2].replace('<', '').strip()
        result.issuing_country_code = self._clean_alpha_field(line1[2:5])
        result.surname, result.given_names, result.full_name = self._parse_name_field(line1[5:36])

        doc_num_raw = line2[0:9]
        result.document_number_raw = doc_num_raw
        result.document_number = doc_num_raw.replace('<', '').strip()
        result.document_number_check = self._clean_digit(line2[9])

        result.nationality_code = self._clean_alpha_field(line2[10:13])

        dob_raw = self._clean_numeric_field(line2[13:19])
        result.date_of_birth_raw = dob_raw
        dob_norm = normalize_mrz_date(dob_raw, is_expiry=False)
        result.date_of_birth_normalized = dob_norm
        result.date_of_birth = dob_norm.get("normalized") or self._fmt_date(dob_raw, is_expiry=False)
        result.dob_check = self._clean_digit(line2[19])

        result.sex = line2[20].upper()

        exp_raw = self._clean_numeric_field(line2[21:27])
        result.expiry_date_raw = exp_raw
        exp_norm = normalize_mrz_date(exp_raw, is_expiry=True)
        result.expiry_date_normalized = exp_norm
        result.expiry_date = exp_norm.get("normalized") or self._fmt_date(exp_raw, is_expiry=True)
        result.expiry_check = self._clean_digit(line2[27])

        composite_char = self._clean_digit(line2[35])
        result.composite_check = composite_char

        result.valid_structure = True
        failures = []

        dn_computed = compute_check_digit(doc_num_raw)
        dn_passed = (str(dn_computed) == str(result.document_number_check))
        dn_r = CheckDigitResult(
            field_name="Document Number", data=doc_num_raw,
            expected_digit=result.document_number_check,
            computed_digit=dn_computed, passed=dn_passed,
        )
        result.document_number_check_result = dn_r
        if not dn_passed:
            failures.append("Document number check digit failed")

        dob_computed = compute_check_digit(dob_raw)
        dob_passed = (str(dob_computed) == str(result.dob_check))
        dob_r = CheckDigitResult(
            field_name="Date of Birth", data=dob_raw,
            expected_digit=result.dob_check,
            computed_digit=dob_computed, passed=dob_passed,
        )
        result.dob_check_result = dob_r
        if not dob_passed:
            failures.append("DOB check digit failed")

        exp_computed = compute_check_digit(exp_raw)
        exp_passed = (str(exp_computed) == str(result.expiry_check))
        exp_r = CheckDigitResult(
            field_name="Expiry Date", data=exp_raw,
            expected_digit=result.expiry_check,
            computed_digit=exp_computed, passed=exp_passed,
        )
        result.expiry_check_result = exp_r
        if not exp_passed:
            failures.append("Expiry check digit failed")

        comp_data = line2[0:10] + line2[13:20] + line2[21:35]
        comp_computed = compute_check_digit(comp_data)
        comp_passed = (str(comp_computed) == str(composite_char))
        comp_r = CheckDigitResult(
            field_name="Composite", data=comp_data,
            expected_digit=composite_char,
            computed_digit=comp_computed, passed=comp_passed,
        )
        result.composite_check_result = comp_r
        if not comp_passed:
            failures.append("Composite check digit failed")

        result.failure_reasons = failures
        mandatory_ok = dn_passed and dob_passed and exp_passed and comp_passed
        result.check_digit_valid = mandatory_ok
        result.all_check_digits_valid = mandatory_ok
        result.field_consistency = mandatory_ok and result.valid_structure
        result.mrz_status = result.get_mrz_overall_status()

        print(f"[MRZ] Raw lines: {result.raw_mrz_lines}")
        print(f"[MRZ] Detected format: {result.mrz_format}")
        print(f"[MRZ] Check digit results: {result.check_digits_dict}")
        print(f"[MRZ] Overall status: {result.mrz_status}")

        return result

    # ─── TD1 Parsing ──────────────────────────────────────────────────────────

    def _parse_td1(self, lines: List[str], result: ParsedMRZ) -> ParsedMRZ:
        """Parse TD1: 3 lines x 30 chars."""
        result.mrz_detected = True
        result.mrz_format = "TD1"
        line1 = lines[0].ljust(30, '<')[:30]
        line2 = lines[1].ljust(30, '<')[:30] if len(lines) > 1 else '<' * 30
        line3 = lines[2].ljust(30, '<')[:30] if len(lines) > 2 else '<' * 30

        result.line1 = line1
        result.line2 = line2
        result.line3 = line3
        result.normalized_mrz_lines = [line1, line2, line3]
        result.normalized_mrz = f"{line1}\n{line2}\n{line3}"

        result.document_type = line1[0:2].replace('<', '').strip()
        result.issuing_country_code = self._clean_alpha_field(line1[2:5])

        doc_num_raw = line1[5:14]
        result.document_number_raw = doc_num_raw
        result.document_number = doc_num_raw.replace('<', '').strip()
        result.document_number_check = self._clean_digit(line1[14])

        dob_raw = self._clean_numeric_field(line2[0:6])
        result.date_of_birth_raw = dob_raw
        dob_norm = normalize_mrz_date(dob_raw, is_expiry=False)
        result.date_of_birth_normalized = dob_norm
        result.date_of_birth = dob_norm.get("normalized") or self._fmt_date(dob_raw, is_expiry=False)
        result.dob_check = self._clean_digit(line2[6])

        result.sex = line2[7].upper()

        exp_raw = self._clean_numeric_field(line2[8:14])
        result.expiry_date_raw = exp_raw
        exp_norm = normalize_mrz_date(exp_raw, is_expiry=True)
        result.expiry_date_normalized = exp_norm
        result.expiry_date = exp_norm.get("normalized") or self._fmt_date(exp_raw, is_expiry=True)
        result.expiry_check = self._clean_digit(line2[14])

        result.nationality_code = self._clean_alpha_field(line2[15:18])

        composite_char = self._clean_digit(line2[29])
        result.composite_check = composite_char

        result.surname, result.given_names, result.full_name = self._parse_name_field(line3[0:30])

        result.valid_structure = True
        failures = []

        dn_computed = compute_check_digit(doc_num_raw)
        dn_passed = (str(dn_computed) == str(result.document_number_check))
        dn_r = CheckDigitResult(
            field_name="Document Number", data=doc_num_raw,
            expected_digit=result.document_number_check,
            computed_digit=dn_computed, passed=dn_passed,
        )
        result.document_number_check_result = dn_r
        if not dn_passed:
            failures.append("Document number check digit failed")

        dob_computed = compute_check_digit(dob_raw)
        dob_passed = (str(dob_computed) == str(result.dob_check))
        dob_r = CheckDigitResult(
            field_name="Date of Birth", data=dob_raw,
            expected_digit=result.dob_check,
            computed_digit=dob_computed, passed=dob_passed,
        )
        result.dob_check_result = dob_r
        if not dob_passed:
            failures.append("DOB check digit failed")

        exp_computed = compute_check_digit(exp_raw)
        exp_passed = (str(exp_computed) == str(result.expiry_check))
        exp_r = CheckDigitResult(
            field_name="Expiry Date", data=exp_raw,
            expected_digit=result.expiry_check,
            computed_digit=exp_computed, passed=exp_passed,
        )
        result.expiry_check_result = exp_r
        if not exp_passed:
            failures.append("Expiry check digit failed")

        comp_data = line1[5:30] + line2[0:7] + line2[8:15] + line2[18:29]
        comp_computed = compute_check_digit(comp_data)
        comp_passed = (str(comp_computed) == str(composite_char))
        comp_r = CheckDigitResult(
            field_name="Composite", data=comp_data,
            expected_digit=composite_char,
            computed_digit=comp_computed, passed=comp_passed,
        )
        result.composite_check_result = comp_r
        if not comp_passed:
            failures.append("Composite check digit failed")

        result.failure_reasons = failures
        mandatory_ok = dn_passed and dob_passed and exp_passed and comp_passed
        result.check_digit_valid = mandatory_ok
        result.all_check_digits_valid = mandatory_ok
        result.field_consistency = mandatory_ok and result.valid_structure
        result.mrz_status = result.get_mrz_overall_status()

        print(f"[MRZ] Raw lines: {result.raw_mrz_lines}")
        print(f"[MRZ] Detected format: {result.mrz_format}")
        print(f"[MRZ] Check digit results: {result.check_digits_dict}")
        print(f"[MRZ] Overall status: {result.mrz_status}")

        return result

    # ─── Disambiguation & Field Cleaning ──────────────────────────────────────

    def _clean_alpha_field(self, text: str) -> str:
        """Resolve OCR digits to alpha characters in strictly alphabetic fields."""
        NUM_TO_ALPHA = {'0': 'O', '1': 'I', '8': 'B', '5': 'S', '2': 'Z', '6': 'G'}
        clean = ''.join(NUM_TO_ALPHA.get(c, c) for c in text.upper())
        return clean.replace('<', '').strip()

    def _clean_numeric_field(self, text: str) -> str:
        """Resolve OCR letter artifacts to digits in strictly numeric fields (e.g. YYMMDD)."""
        ALPHA_TO_NUM = {
            'O': '0', 'o': '0',
            'I': '1', 'i': '1', 'l': '1', '|': '1',
            'Z': '2', 'z': '2',
            'E': '3',
            'A': '4',
            'S': '5', 's': '5',
            'G': '6', 'b': '6',
            'T': '7',
            'B': '8',
            'g': '9', 'q': '9',
            '<': '0',
        }
        res = []
        for c in text:
            if c.isdigit():
                res.append(c)
            elif c in ALPHA_TO_NUM:
                res.append(ALPHA_TO_NUM[c])
            else:
                res.append('0')
        return ''.join(res)

    def _clean_digit(self, char: str) -> str:
        """Single check digit normalization."""
        if not char:
            return '0'
        if char.isdigit():
            return char
        MAP = {'O': '0', 'I': '1', 'l': '1', 'Z': '2', 'S': '5', 'B': '8', '<': '0'}
        return MAP.get(char.upper(), '0')

    def _parse_name_field(self, raw_name: str) -> Tuple[str, str, str]:
        """
        Parse ICAO name field:
        SURNAME<<GIVEN<NAMES<<<<...
        Returns (surname, given_names, full_name).
        Example: DOE<<JOHN<ROBERT -> (DOE, JOHN ROBERT, DOE JOHN ROBERT)
        """
        # Strip trailing filler '<'
        clean = raw_name.rstrip('<')
        if not clean:
            return "", "", ""

        parts = clean.split('<<')
        surname = parts[0].replace('<', ' ').strip()
        # Clean alpha only in names
        surname = re.sub(r'[^A-Z\s]', '', surname.upper()).strip()

        given_names = ""
        if len(parts) > 1:
            given_raw = '<<'.join(parts[1:])
            given_names = given_raw.replace('<', ' ').strip()
            given_names = re.sub(r'[^A-Z\s]', '', given_names.upper()).strip()
            # Collapse multiple spaces
            given_names = re.sub(r'\s+', ' ', given_names)

        full_parts = []
        if surname:
            full_parts.append(surname)
        if given_names:
            full_parts.append(given_names)
        full_name = " ".join(full_parts).strip()

        return surname, given_names, full_name

    def _fmt_date(self, yymmdd: str, is_expiry: bool = False) -> str:
        """Fallback date formatter: YYMMDD -> DD/MM/YYYY."""
        if not yymmdd or len(yymmdd) < 6:
            return yymmdd or ""
        try:
            yy = int(yymmdd[0:2])
            mm = yymmdd[2:4]
            dd = yymmdd[4:6]
            if is_expiry:
                year = 2000 + yy if yy <= 80 else 1900 + yy
            else:
                year = 1900 + yy if yy >= 30 else 2000 + yy
            return f"{dd}/{mm}/{year}"
        except (ValueError, IndexError):
            return yymmdd

    _format_date = _fmt_date

    def _is_mrz_like(self, line: str) -> bool:
        """Heuristic: determine if a line looks like MRZ data."""
        clean = line.replace(' ', '')
        if len(clean) < 20:
            return False
        mrz_chars = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<')
        ratio = sum(1 for c in clean.upper() if c in mrz_chars) / len(clean)
        if ratio < 0.85:
            return False
        # Must contain at least one letter and (filler or digit)
        has_letter = any(c.isalpha() for c in clean)
        has_digit_or_filler = any(c.isdigit() or c == '<' for c in clean)
        return has_letter and has_digit_or_filler


mrz_parser = MRZParser()
