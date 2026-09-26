"""
Document field extractor.
Uses regex patterns to extract structured fields from raw OCR text.
Also merges/fills fields from parsed MRZ data (which is more reliable than OCR).
"""
import re
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


class FieldExtractor:
    """
    Extracts structured document fields from raw OCR text.
    Uses pattern matching tuned for passport and ID document layouts.
    Can also enrich OCR-extracted fields with reliable MRZ-parsed data.
    """

    # Common date patterns (DD MM YYYY, DD/MM/YYYY, YYYY-MM-DD, etc.)
    DATE_PATTERNS = [
        r'\b(\d{2})[./\-](\d{2})[./\-](\d{4})\b',  # DD/MM/YYYY
        r'\b(\d{4})[./\-](\d{2})[./\-](\d{2})\b',  # YYYY-MM-DD
        r'\b(\d{2})\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+(\d{4})\b',
        r'\b(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{4})\b',
    ]

    MONTH_MAP = {
        'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
        'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
        'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12'
    }

    # Document number patterns — order matters (most specific first)
    DOC_NUMBER_PATTERNS = [
        r'Passport\s+No[.:\s]*([A-Z0-9]{6,12})',       # "Passport No: AB123456"
        r'Document\s+No[.:\s]*([A-Z0-9]{6,12})',        # "Document No: AB123456"
        r'Aadhaar(?:\s*No|\s*Number)?[:\s]*(\d{4}\s*\d{4}\s*\d{4})',  # Aadhaar card
        r'\b(\d{4}\s\d{4}\s\d{4})\b',                   # 12-digit grouped ID
        r'No[.:\s]*([A-Z0-9]{6,12})',                  # "No: AB123456"
        r'\b([A-Z]{1,2}\d{6,8})\b',                     # Standard passport: AB123456
        r'Decument\s+Na[.:\s]*([A-Z0-9]{6,12})',         # OCR artifact: "Decument Na:"
        r'Document\s+Na[.:\s]*([A-Z0-9]{6,12})',
        r'\b([A-Z0-9]{8,12})\b',                         # General alphanumeric (filtered below)
    ]

    NON_DOC_WORDS = {
        'GOVERNMENT', 'REPUBLIC', 'AUTHORITY', 'IDENTIFICATION', 'ENROLMENT',
        'PASSPORT', 'DOCUMENT', 'NATIONALITY', 'SIGNATURE', 'VALIDATION',
        'VERIFIED', 'INDIVIDUAL', 'RESIDENT', 'CONFIDENTIAL', 'OFFICIAL',
        'DEPARTMENT', 'CERTIFICATE', 'CARD',
    }

    # Sex/Gender patterns
    SEX_PATTERNS = [
        r'Sex[:/\s]+([MF])\b',
        r'Gender[:/\s]+([MF])\b',
        r'\bSex[:\s]+(MALE|FEMALE|M|F)\b',
        r'\b(MALE|FEMALE)\b',
    ]

    # Nationality / country patterns (ISO 3166-1 alpha-3)
    COUNTRY_CODE_PATTERN = r'\b([A-Z]{3})\b'

    # Known country codes for nationality validation
    KNOWN_COUNTRY_CODES = {
        'GBR', 'USA', 'FRA', 'DEU', 'IND', 'CHN', 'JPN', 'AUS', 'CAN',
        'RUS', 'BRA', 'MEX', 'ITA', 'ESP', 'NLD', 'BEL', 'CHE', 'SWE',
        'NOR', 'DNK', 'FIN', 'POL', 'CZE', 'AUT', 'PRT', 'GRC', 'TUR',
        'IRN', 'IRQ', 'SAU', 'ARE', 'EGY', 'ZAF', 'NGA', 'KEN', 'ETH',
        'PAK', 'BGD', 'IDN', 'THA', 'VNM', 'MYS', 'SGP', 'PHL', 'KOR',
        'ARG', 'CHL', 'COL', 'PER', 'VEN', 'UKR', 'ROU', 'HUN', 'HRV',
        'SRB', 'BGR', 'SVK', 'LTU', 'LVA', 'EST', 'BLR', 'KAZ', 'UZB',
        'AFG', 'LKA', 'MMR', 'NPL', 'MDV', 'BTN', 'ISL', 'IRL', 'NZL',
        'UNK', 'XXX',  # Unknown/stateless in some MRZ docs
    }

    # Name field indicators
    NAME_INDICATORS = [
        'SURNAME', 'LAST NAME', 'FAMILY NAME', 'GIVEN NAMES', 'FIRST NAME',
        'NAME', 'HOLDER'
    ]

    # Known words that appear in passports but are NOT names
    NON_NAME_WORDS = {
        'PASSPORT', 'VISA', 'REPUBLIC', 'UNITED', 'KINGDOM', 'STATES',
        'NATIONALITY', 'NATIONAL', 'DATE', 'BIRTH', 'ISSUE', 'EXPIRY',
        'DOCUMENT', 'NUMBER', 'GIVEN', 'NAMES', 'SURNAME', 'SEX', 'MALE',
        'FEMALE', 'VALID', 'UNTIL', 'COUNTRY', 'AUTHORITY', 'HOLDER',
        'ORDINARY', 'SERVICE', 'OFFICIAL', 'DIPLOMATIC', 'GOVERNMENT',
        'INDIAN', 'AMERICAN', 'BRITISH', 'CANADIAN', 'AUSTRALIAN',
        'GERMAN', 'FRENCH', 'CHINESE', 'JAPANESE', 'RUSSIAN', 'SIGNATURE',
        'CODE', 'STATE', 'PLACE', 'PHOTO', 'INDIA', 'CITIZEN', 'TYPE',
        'EMBLEM', 'MINISTRY', 'EXTERNAL', 'AFFAIRS', 'OF', 'THE', 'AND'
    }

    def extract(self, raw_text: str) -> Dict[str, Any]:
        """
        Extract structured fields from raw OCR text.
        Returns dict with extracted fields and raw text preserved.
        """
        if not raw_text or not raw_text.strip():
            logger.warning("OCR returned empty text — cannot extract fields")
            return self._empty_result()

        text_upper = raw_text.upper()
        lines = [l.strip() for l in raw_text.split('\n') if l.strip()]

        logger.debug("Field extraction from %d OCR lines", len(lines))

        result = {
            "full_name": self._extract_name(lines, text_upper),
            "document_number": self._extract_document_number(text_upper, lines),
            "date_of_birth": self._extract_labeled_date(text_upper, [
                "DATE OF BIRTH", "DOB", "BIRTH DATE", "BORN", "DATE OF BIRTH:"
            ]),
            "expiry_date": self._extract_labeled_date(text_upper, [
                "EXPIRY DATE", "DATE OF EXPIRY", "VALID UNTIL", "EXPIRY", "EXPIRES",
                "DATE OF EXPIRY:", "EXPIRY DATE:", "EXPIRY.",
            ]),
            "issue_date": self._extract_labeled_date(text_upper, [
                "DATE OF ISSUE", "ISSUE DATE", "ISSUED", "DATE ISSUED",
                "DATE OF ISSUE:", "DATE OF SSUE",  # common OCR artifact
            ]),
            "nationality": self._extract_nationality(text_upper, lines),
            "sex": self._extract_sex(text_upper),
            "issuing_country": self._extract_issuing_country(text_upper),
            "visa_number": self._extract_visa_number(text_upper),
            "raw_ocr_text": raw_text,
        }

        # Fallback date extraction if labeled search missed them
        self._fill_fallback_dates(raw_text, result)

        # Log what was found
        found_fields = [k for k, v in result.items() if v and k not in ('raw_ocr_text',)]
        logger.info("Field extraction found: %s", found_fields)

        return result

    def _fill_fallback_dates(self, raw_text: str, result: Dict[str, Any]):
        """Find unlabeled dates in OCR text and assign them based on chronology."""
        if result.get("date_of_birth") and result.get("expiry_date"):
            return
        pattern = r'\b(\d{2})[./\-](\d{2})[./\-](\d{4})\b'
        candidates = []
        for m in re.finditer(pattern, raw_text):
            dd, mm, yyyy = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= dd <= 31 and 1 <= mm <= 12 and 1920 <= yyyy <= 2060:
                candidates.append((yyyy, f"{m.group(1)}/{m.group(2)}/{m.group(3)}"))

        candidates.sort(key=lambda x: x[0])
        unique_dates = []
        seen_dates = set()
        for y, d in candidates:
            if d not in seen_dates:
                seen_dates.add(d)
                unique_dates.append((y, d))

        for y, d in unique_dates:
            if y < 2012 and not result.get("date_of_birth"):
                result["date_of_birth"] = d
            elif y > 2025 and not result.get("expiry_date"):
                result["expiry_date"] = d
            elif 2012 <= y <= 2025 and not result.get("issue_date"):
                result["issue_date"] = d

    def enrich_from_mrz(self, ocr_data: Dict, mrz_data: Dict) -> Dict:
        """
        Enrich OCR-extracted fields with MRZ-parsed data.
        MRZ data is structured and check-digit validated, so it provides high reliability.
        Also performs OCR vs MRZ name consistency comparison per specification.
        """
        if not mrz_data or not mrz_data.get("mrz_detected"):
            return ocr_data

        enriched = dict(ocr_data)

        # ── MRZ Document Number ──
        if mrz_data.get("document_number") and not enriched.get("document_number"):
            enriched["document_number"] = mrz_data["document_number"]
            logger.debug("Enriched document_number from MRZ: %s", mrz_data["document_number"])

        # ── MRZ Date of Birth ──
        if mrz_data.get("date_of_birth") and not enriched.get("date_of_birth"):
            enriched["date_of_birth"] = mrz_data["date_of_birth"]
            logger.debug("Enriched date_of_birth from MRZ: %s", mrz_data["date_of_birth"])

        # ── MRZ Expiry Date ──
        if mrz_data.get("expiry_date") and not enriched.get("expiry_date"):
            enriched["expiry_date"] = mrz_data["expiry_date"]
            logger.debug("Enriched expiry_date from MRZ: %s", mrz_data["expiry_date"])

        # ── Nationality vs Issuing Country (Separate fields) ──
        nat_code = mrz_data.get("nationality_code") or (
            mrz_data.get("nationality") if len(mrz_data.get("nationality", "")) == 3 else None
        )
        iss_code = mrz_data.get("issuing_country_code") or (
            mrz_data.get("issuing_country") if len(mrz_data.get("issuing_country", "")) == 3 else None
        )
        enriched["nationality_code"] = nat_code
        enriched["issuing_country_code"] = iss_code
        enriched["country_code"] = iss_code
        if nat_code:
            enriched["nationality"] = nat_code
        if iss_code:
            enriched["issuing_country"] = iss_code

        # ── MRZ Sex ──
        if mrz_data.get("sex") and not enriched.get("sex"):
            sex = mrz_data["sex"]
            if sex in ('M', 'F'):
                enriched["sex"] = sex
                logger.debug("Enriched sex from MRZ: %s", sex)

        # ── Date of Issue: Never fabricate from TD3 MRZ! ──
        issue_date = ocr_data.get("issue_date") or ocr_data.get("date_of_issue")
        enriched["issue_date"] = issue_date
        enriched["date_of_issue"] = issue_date
        enriched["date_of_issue_source"] = "OCR/VIZ" if issue_date else "Not detected"

        # ── Structured Full Name Extraction & OCR vs MRZ Consistency ──
        surname = mrz_data.get("surname", "").strip()
        given_names = mrz_data.get("given_names", "").strip()
        mrz_full_name = mrz_data.get("full_name_mrz") or mrz_data.get("full_name")
        if not mrz_full_name:
            full_parts = [p for p in (surname, given_names) if p]
            mrz_full_name = " ".join(full_parts).strip()

        ocr_name = ocr_data.get("full_name")
        # Filter out bogus OCR names that are non-name keywords
        if ocr_name:
            words = [w for w in re.sub(r'[^A-Z\s]', ' ', ocr_name.upper()).split()]
            if not words or all(w in self.NON_NAME_WORDS for w in words):
                ocr_name = None

        def _norm_name(s: Optional[str]) -> str:
            if not s:
                return ""
            cleaned = re.sub(r'[^A-Z\s]', ' ', s.upper().replace('<', ' '))
            return re.sub(r'\s+', ' ', cleaned).strip()

        norm_ocr = _norm_name(ocr_name)
        norm_mrz = _norm_name(mrz_full_name)

        if norm_ocr and norm_mrz:
            tok_ocr = set(norm_ocr.split())
            tok_mrz = set(norm_mrz.split())
            if norm_ocr == norm_mrz or tok_ocr == tok_mrz:
                consistency = "MATCH"
                confidence = 1.0
                source = "MRZ + OCR"
                final_name = mrz_full_name
            elif tok_ocr.issubset(tok_mrz) or tok_mrz.issubset(tok_ocr) or len(tok_ocr.intersection(tok_mrz)) > 0:
                consistency = "PARTIAL_MATCH"
                overlap = len(tok_ocr.intersection(tok_mrz)) / max(len(tok_ocr), len(tok_mrz))
                confidence = round(0.5 + 0.5 * overlap, 2)
                source = "MRZ + OCR"
                final_name = mrz_full_name
            else:
                consistency = "MISMATCH"
                confidence = 0.0
                source = "MRZ"
                final_name = mrz_full_name
        elif norm_mrz:
            consistency = "UNAVAILABLE"
            confidence = 0.95
            source = "MRZ"
            final_name = mrz_full_name
        elif norm_ocr:
            consistency = "UNAVAILABLE"
            confidence = 0.70
            source = "OCR"
            final_name = ocr_name
        else:
            consistency = "UNAVAILABLE"
            confidence = 0.0
            source = None
            final_name = None

        # Required debugging logs per Bug 1 (#22)
        print(f"[NAME] OCR: {ocr_name}")
        print(f"[NAME] MRZ: {mrz_full_name}")
        print(f"[NAME] Normalized OCR: {norm_ocr}")
        print(f"[NAME] Normalized MRZ: {norm_mrz}")
        print(f"[NAME] Consistency: {consistency}")

        enriched["name_ocr"] = ocr_name
        enriched["name_mrz"] = mrz_full_name
        enriched["name_consistency"] = consistency
        enriched["name_confidence"] = confidence
        enriched["name_source"] = source
        enriched["full_name"] = final_name

        # Always prefer MRZ values for key fields if MRZ check digits are valid
        if mrz_data.get("check_digit_valid"):
            if mrz_data.get("document_number"):
                enriched["document_number"] = mrz_data["document_number"]
            if mrz_data.get("date_of_birth"):
                enriched["date_of_birth"] = mrz_data["date_of_birth"]
            if mrz_data.get("expiry_date"):
                enriched["expiry_date"] = mrz_data["expiry_date"]

        logger.info(
            "After MRZ enrichment — fields found: %s",
            [k for k, v in enriched.items() if v and k not in ('raw_ocr_text',)]
        )
        return enriched

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "full_name": None, "document_number": None,
            "date_of_birth": None, "expiry_date": None,
            "issue_date": None, "nationality": None,
            "sex": None, "issuing_country": None,
            "visa_number": None, "raw_ocr_text": "",
            "nationality_code": None, "issuing_country_code": None,
            "date_of_issue": None, "date_of_issue_source": "Not detected",
            "name_source": None, "name_consistency": "UNAVAILABLE",
        }

    def _extract_name(self, lines: list, text_upper: str) -> Optional[str]:
        """Extract full name from document text."""
        # 1. Look specifically for labeled Surname and Given Names in passport OCR
        ocr_surname = None
        ocr_given = None
        for i, line in enumerate(lines):
            line_u = line.upper().strip()
            if 'SURNAME' in line_u:
                rem = re.sub(r'^.*SURNAME[^A-Za-z]*', '', line_u).strip()
                rem = re.sub(r'[^A-Z\s]', '', rem).strip()
                if rem and len(rem) >= 2 and all(w not in self.NON_NAME_WORDS for w in rem.split()):
                    ocr_surname = rem
                elif i + 1 < len(lines):
                    next_l = re.sub(r'[^A-Z\s]', '', lines[i + 1].upper()).strip()
                    if next_l and len(next_l) >= 2 and all(w not in self.NON_NAME_WORDS for w in next_l.split()):
                        ocr_surname = next_l

            if 'GIVEN NAME' in line_u or 'GIVEN NAMES' in line_u:
                rem = re.sub(r'^.*GIVEN\s*NAME[S]?[^A-Za-z]*', '', line_u).strip()
                rem = re.sub(r'[^A-Z\s]', '', rem).strip()
                if rem and len(rem) >= 2 and all(w not in self.NON_NAME_WORDS for w in rem.split()):
                    ocr_given = rem
                elif i + 1 < len(lines):
                    next_l = re.sub(r'[^A-Z\s]', '', lines[i + 1].upper()).strip()
                    if next_l and len(next_l) >= 2 and all(w not in self.NON_NAME_WORDS for w in next_l.split()):
                        ocr_given = next_l

        if ocr_surname and ocr_given:
            return f"{ocr_surname} {ocr_given}".title()
        elif ocr_surname:
            return ocr_surname.title()
        elif ocr_given:
            return ocr_given.title()

        # 2. Check standard Indian ID / address format: "To <Name> S/O ..." or "To <Name> ,"
        for line in lines:
            m_to = re.search(r'^\s*To\s+([A-Za-z\s.]+?)(?:\s+[SDW]/O|\s*,\s*|\n|$)', line, re.IGNORECASE)
            if m_to:
                name_candidate = m_to.group(1).strip()
                cand_words = name_candidate.upper().split()
                if len(name_candidate) >= 3 and not any(w in self.NON_NAME_WORDS for w in cand_words):
                    return name_candidate.title()

        # 3. Look for lines after name indicators
        for i, line in enumerate(lines):
            line_upper = line.upper()
            for indicator in self.NAME_INDICATORS:
                if indicator in line_upper:
                    remaining = re.sub(re.escape(indicator), '', line_upper, flags=re.IGNORECASE).strip(':').strip()
                    rem_words = remaining.split()
                    if remaining and len(remaining) > 3 and remaining.replace(' ', '').isalpha():
                        if not any(w in self.NON_NAME_WORDS for w in rem_words):
                            return remaining.title()
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        next_words = next_line.upper().split()
                        if (next_line and len(next_line) > 3
                                and next_line.replace(' ', '').isalpha()
                                and not any(w in self.NON_NAME_WORDS for w in next_words)):
                            return next_line.title()

        # 4. Fallback: look for all-caps multi-word name lines (common in passports)
        for line in lines:
            stripped = line.strip()
            words = stripped.split()
            if (len(stripped) > 5
                    and len(words) >= 2
                    and stripped.isupper()
                    and stripped.replace(' ', '').isalpha()
                    and not any(w in self.NON_NAME_WORDS for w in words)):
                return stripped.title()

        return None

    def _extract_document_number(self, text_upper: str, lines: List[str] = None) -> Optional[str]:
        """Extract document/passport number."""
        for pattern in self.DOC_NUMBER_PATTERNS:
            match = re.search(pattern, text_upper, re.IGNORECASE)
            if match:
                doc_num = match.group(1).strip()
                # Check for Aadhaar format: 12 digits (with or without spaces)
                clean_digits = doc_num.replace(' ', '')
                if len(clean_digits) == 12 and clean_digits.isdigit():
                    return doc_num

                # Standard alphanumeric document numbers (6-12 chars)
                if 6 <= len(doc_num) <= 12:
                    if doc_num.upper() in self.NON_DOC_WORDS:
                        continue
                    # Pure alphabetic matches without digits are words, unless explicit label in pattern
                    if doc_num.isalpha() and not any(kw in pattern.lower() for kw in ('passport', 'document', 'aadhaar', 'no')):
                        continue
                    return doc_num
        return None

    def _extract_labeled_date(self, text_upper: str, labels: list) -> Optional[str]:
        """Extract a date that appears near a specific label."""
        for label in labels:
            idx = text_upper.find(label)
            if idx >= 0:
                # Search for date in a window after the label
                window = text_upper[idx:idx + 80]  # Increased window from 60 to 80
                date = self._find_date_in_text(window)
                if date:
                    return date
        return None

    def _find_date_in_text(self, text: str) -> Optional[str]:
        """Find and normalize the first date-like pattern in text."""
        # DD/MM/YYYY
        m = re.search(r'(\d{2})[./\- ](\d{2})[./\- ](\d{4})', text)
        if m:
            return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"

        # YYYY-MM-DD
        m = re.search(r'(\d{4})[./\-](\d{2})[./\-](\d{2})', text)
        if m:
            return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"

        # DD MON YYYY
        m = re.search(
            r'(\d{2})\s*(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s*(\d{4})',
            text, re.IGNORECASE
        )
        if m:
            month = self.MONTH_MAP.get(m.group(2).upper(), m.group(2))
            return f"{m.group(1)}/{month}/{m.group(3)}"

        return None

    def _extract_nationality(self, text_upper: str, lines: list) -> Optional[str]:
        """Extract nationality field."""
        # Look for labeled nationality
        for label in ['NATIONALITY', 'NATIONAL', 'CITIZEN']:
            idx = text_upper.find(label)
            if idx >= 0:
                window = text_upper[idx:idx + 60]
                m = re.search(r'[:\s]+([A-Z]{3,})', window)
                if m:
                    val = m.group(1)
                    # Ensure it's not another keyword
                    if val not in {'NATIONALITY', 'NATIONAL', 'CITIZEN', 'NATIONAL'}:
                        # Prefer 3-letter codes
                        if val in self.KNOWN_COUNTRY_CODES:
                            return val
                        # Or return first match if not too long
                        if len(val) <= 10:
                            return val[:3] if len(val) > 3 else val
        return None

    def _extract_sex(self, text_upper: str) -> Optional[str]:
        """Extract sex/gender field."""
        for pattern in self.SEX_PATTERNS:
            m = re.search(pattern, text_upper, re.IGNORECASE)
            if m:
                val = m.group(1).upper()
                if val in ('M', 'MALE'):
                    return 'M'
                elif val in ('F', 'FEMALE'):
                    return 'F'
        return None

    def _extract_issuing_country(self, text_upper: str) -> Optional[str]:
        """Extract issuing country."""
        for label in ['ISSUING COUNTRY', 'ISSUING STATE', 'ISSUED BY', 'COUNTRY OF ISSUE']:
            idx = text_upper.find(label)
            if idx >= 0:
                window = text_upper[idx:idx + 50]
                m = re.search(r'[:\s]+([A-Z]{3})', window)
                if m:
                    return m.group(1)
        return None

    def _extract_visa_number(self, text_upper: str) -> Optional[str]:
        """Extract visa number if present."""
        m = re.search(r'VISA\s+(?:NO|NUMBER|#)[.:\s]*([A-Z0-9]{6,12})', text_upper)
        if m:
            return m.group(1)
        return None


field_extractor = FieldExtractor()
