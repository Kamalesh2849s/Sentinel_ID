"""
MRZ extractor: locates and extracts the MRZ zone from a document image.

Strategy order:
1. Bottom-region crop → Tesseract MRZ mode (character whitelist) → MRZ pattern filter
2. Bottom-region crop → standard OCR → MRZ pattern filter
3. Morphological MRZ band detection → crop → OCR
4. Full-page OCR → MRZ pattern filter

Each strategy tries both original and preprocessed (contrast-enhanced, thresholded) versions.

OCR Confusion Corrections (Tesseract on MRZ zone):
  - 'c', 'e', 's' → '<'   (filler char misread as letters)
  - 'o', 'O' → '0'         (zero misread as O in numeric positions)
  - 'l', 'I' → '1'         (one misread as letter)
  - spaces removed          (MRZ has no spaces)
"""
import logging
import os
import re
import tempfile
from typing import Optional, List, Tuple
import cv2
import numpy as np

from app.services.ocr.ocr_engine import ocr_engine

logger = logging.getLogger(__name__)

# Valid MRZ characters
MRZ_CHARS_SET = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<')

# ICAO standard MRZ line lengths
VALID_MRZ_LENGTHS = {44: "TD3", 36: "TD2", 30: "TD1"}

# Common OCR confusions in the MRZ zone context
# These are characters that Tesseract often returns instead of MRZ-valid chars
MRZ_OCR_CORRECTIONS = {
    # Filler '<' is often misread as these letters/symbols
    'c': '<', 'e': '<', 's': '<', 'ç': '<', 'é': '<',
    # Zero '0' misread as these
    'o': '0', 'ö': '0', 'ø': '0',
    # One '1' misread as these (only in numeric contexts — applied after initial clean)
    'l': '1', 'i': '1', '|': '1',
    # Other common misreads
    'z': '2', 'g': '6', 'b': '8',
}


class MRZExtractor:
    """
    Locates and extracts MRZ text from a document image.
    Uses multiple strategies and both original + preprocessed images.
    """

    def extract_mrz_text(
        self,
        image_path: str,
        img_cv: Optional[np.ndarray] = None,
    ) -> Optional[str]:
        """
        Extract MRZ text from document image.
        Returns raw MRZ string (normalized, '\n' separated lines) or None.
        """
        if img_cv is None:
            img_cv = cv2.imread(image_path)
            if img_cv is None:
                logger.error("Cannot load image for MRZ extraction: %s", image_path)
                return None

        logger.info("Starting MRZ extraction from %s (shape=%s)",
                    os.path.basename(image_path), img_cv.shape)

        # Strategy 1: Multiple bottom-region crops with MRZ-specific OCR
        for fraction in [0.30, 0.25, 0.35, 0.40, 0.50]:
            mrz_text = self._try_bottom_region_mrz_mode(img_cv, fraction)
            if mrz_text:
                logger.info("MRZ found via MRZ-mode bottom-region strategy (fraction=%.2f)", fraction)
                return mrz_text

        # Strategy 2: Bottom-region with standard OCR
        for fraction in [0.30, 0.25, 0.35, 0.40, 0.50]:
            mrz_text = self._try_bottom_region(img_cv, fraction)
            if mrz_text:
                logger.info("MRZ found via standard bottom-region strategy (fraction=%.2f)", fraction)
                return mrz_text

        # Strategy 3: Morphological band detection
        mrz_text = self._extract_via_morphology(img_cv)
        if mrz_text:
            logger.info("MRZ found via morphological detection")
            return mrz_text

        # Strategy 4: Full-page OCR
        mrz_text = self._extract_from_full_page_ocr(image_path)
        if mrz_text:
            logger.info("MRZ found via full-page OCR")
            return mrz_text

        logger.warning("MRZ not detected in document after all strategies")
        return None

    # ─── Strategy 1: MRZ-optimized OCR on bottom region ──────────────────────

    def _try_bottom_region_mrz_mode(self, img_cv: np.ndarray, fraction: float) -> Optional[str]:
        """
        Crop the bottom region and run Tesseract with MRZ character whitelist.
        This is the most reliable approach for MRZ extraction.
        """
        height, width = img_cv.shape[:2]
        top = int(height * (1.0 - fraction))
        region = img_cv[top:height, 0:width]

        if region.size == 0:
            return None

        # Generate preprocessed variants optimized for MRZ OCR
        for preprocessed in self._prepare_mrz_variants(region):
            result = ocr_engine.extract_mrz_text(preprocessed)
            if result.raw_text.strip():
                mrz = self._filter_mrz_candidates(result.raw_text)
                if mrz:
                    logger.debug("MRZ-mode found candidate: %s", repr(mrz[:80]))
                    return mrz

        return None

    def _prepare_mrz_variants(self, region: np.ndarray) -> List[np.ndarray]:
        """
        Generate preprocessed variants optimized for MRZ OCR.
        MRZ text is monospace, dense, uppercase — needs clean binary image.
        """
        variants = []
        try:
            # Convert to grayscale
            if len(region.shape) == 3:
                gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
            else:
                gray = region.copy()

            h, w = gray.shape

            # Scale up if too small (MRZ characters need at least 20px height)
            min_height = 80
            if h < min_height:
                scale = min_height / h
                gray = cv2.resize(gray, None, fx=scale, fy=scale,
                                  interpolation=cv2.INTER_CUBIC)

            # Variant 1: Otsu threshold (best for clean MRZ)
            _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            variants.append(otsu)

            # Variant 2: CLAHE enhanced + Otsu
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
            enhanced = clahe.apply(gray)
            _, otsu_enhanced = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            variants.append(otsu_enhanced)

            # Variant 3: Adaptive threshold (handles uneven lighting)
            if gray.shape[0] > 10 and gray.shape[1] > 10:
                adaptive = cv2.adaptiveThreshold(
                    gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY, 11, 2
                )
                variants.append(adaptive)

            # Variant 4: Inverted Otsu (black on white)
            _, otsu_inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            otsu_inv_normal = cv2.bitwise_not(otsu_inv)
            variants.append(otsu_inv_normal)

        except Exception as e:
            logger.warning("MRZ variant preparation failed: %s", e)

        return variants

    # ─── Strategy 2: Bottom-region crops (standard OCR) ──────────────────────

    def _try_bottom_region(self, img_cv: np.ndarray, fraction: float) -> Optional[str]:
        """Crop the bottom `fraction` of the image and run standard OCR."""
        height, width = img_cv.shape[:2]
        top = int(height * (1.0 - fraction))
        region = img_cv[top:height, 0:width]

        if region.size == 0:
            return None

        # Try original color region
        result = self._ocr_region(region)
        if result:
            mrz = self._filter_mrz_candidates(result)
            if mrz:
                return mrz

        # Try preprocessed (enhanced) versions
        for processed in self._prepare_region_variants(region):
            result = self._ocr_region_array(processed)
            if result:
                mrz = self._filter_mrz_candidates(result)
                if mrz:
                    return mrz

        return None

    def _prepare_region_variants(self, region: np.ndarray) -> List[np.ndarray]:
        """Generate preprocessed variants of an image region for OCR."""
        variants = []
        try:
            gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)

            # Variant 1: Scale up + Otsu threshold (binary)
            scale = max(1.0, 60 / region.shape[0])  # ensure at least 60px height
            if scale > 1.0:
                gray_scaled = cv2.resize(gray, None, fx=scale, fy=scale,
                                         interpolation=cv2.INTER_CUBIC)
            else:
                gray_scaled = gray.copy()

            _, otsu = cv2.threshold(gray_scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            variants.append(cv2.cvtColor(otsu, cv2.COLOR_GRAY2BGR))

            # Variant 2: Adaptive threshold
            if gray_scaled.shape[0] > 10 and gray_scaled.shape[1] > 10:
                adaptive = cv2.adaptiveThreshold(
                    gray_scaled, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY, 11, 2
                )
                variants.append(cv2.cvtColor(adaptive, cv2.COLOR_GRAY2BGR))

            # Variant 3: CLAHE enhanced (color)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
            enhanced_gray = clahe.apply(gray)
            if scale > 1.0:
                enhanced_gray = cv2.resize(enhanced_gray, None, fx=scale, fy=scale,
                                           interpolation=cv2.INTER_CUBIC)
            variants.append(cv2.cvtColor(enhanced_gray, cv2.COLOR_GRAY2BGR))

        except Exception as e:
            logger.warning("Region preprocessing failed: %s", e)

        return variants

    def _ocr_region(self, region: np.ndarray) -> str:
        """OCR a color image region."""
        try:
            result = ocr_engine.extract_text_from_array(region)
            return result.raw_text
        except Exception as e:
            logger.debug("OCR region failed: %s", e)
            return ""

    def _ocr_region_array(self, region: np.ndarray) -> str:
        """OCR a preprocessed region array."""
        return self._ocr_region(region)

    # ─── Strategy 3: Morphological band detection ─────────────────────────────

    def _extract_via_morphology(self, img_cv: np.ndarray) -> Optional[str]:
        """
        Use morphological operations to detect MRZ region.
        MRZ bands appear as dense horizontal text zones.
        """
        try:
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

            # Wide horizontal kernel connects characters in each MRZ line
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
            morphed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

            contours, _ = cv2.findContours(
                morphed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            height, width = img_cv.shape[:2]
            candidate_regions = []

            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                aspect_ratio = w / max(h, 1)
                # MRZ: wide band, bottom half of image, not too tall
                if (aspect_ratio > 4
                        and w > width * 0.4
                        and y > height * 0.3
                        and h < height * 0.15):
                    candidate_regions.append((y, y + h, x, x + w))

            if not candidate_regions:
                return None

            # Take the bottom candidates (MRZ is at the bottom)
            candidate_regions.sort(key=lambda r: r[0], reverse=True)
            # Take up to 3 nearest bottom bands
            bottom = candidate_regions[:3]

            min_y = max(0, min(r[0] for r in bottom) - 10)
            max_y = min(height, max(r[1] for r in bottom) + 10)
            min_x = max(0, min(r[2] for r in bottom) - 5)
            max_x = min(width, max(r[3] for r in bottom) + 5)

            mrz_crop = img_cv[min_y:max_y, min_x:max_x]
            if mrz_crop.size == 0:
                return None

            # Try MRZ mode first, then standard
            for variant in self._prepare_mrz_variants(mrz_crop):
                text = ocr_engine.extract_mrz_text(variant).raw_text
                if text:
                    mrz = self._filter_mrz_candidates(text)
                    if mrz:
                        return mrz

            for variant in [mrz_crop] + self._prepare_region_variants(mrz_crop):
                text = self._ocr_region(variant)
                if text:
                    mrz = self._filter_mrz_candidates(text)
                    if mrz:
                        return mrz

        except Exception as e:
            logger.warning("Morphological MRZ detection failed: %s", e)

        return None

    # ─── Strategy 4: Full-page OCR ────────────────────────────────────────────

    def _extract_from_full_page_ocr(self, image_path: str) -> Optional[str]:
        """Run OCR on full page and extract MRZ-like lines."""
        try:
            result = ocr_engine.extract_text(image_path)
            if not result.raw_text:
                logger.warning("Full-page OCR returned empty text")
                return None
            logger.info("Full-page OCR got %d lines", len(result.lines))
            return self._filter_mrz_candidates(result.raw_text)
        except Exception as e:
            logger.error("Full-page OCR failed: %s", e)
            return None

    # ─── MRZ line filtering / pattern matching ────────────────────────────────

    def _filter_mrz_candidates(self, text: str) -> Optional[str]:
        """
        From OCR output, extract lines that look like valid MRZ lines.
        Preserves raw lines before normalization and avoids blind character substitution.
        """
        if not text:
            return None

        # Split into raw lines
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if not lines:
            return None

        # Clean outer frame noise (e.g. '|', leading colons) while preserving characters and '<'
        cleaned_candidates = []
        for line in lines:
            cleaned = self._clean_line(line)
            if cleaned and len(cleaned) >= 20 and self._looks_like_mrz_line(cleaned):
                cleaned_candidates.append(cleaned)

        if not cleaned_candidates:
            logger.debug("No MRZ candidates found in OCR text")
            return None

        logger.debug("MRZ candidates: %s", cleaned_candidates)

        # 1. Search for TD3 passport pair:
        # Line 1 starts with P< or P[A-Z] (len ~44) and line 2 follows with doc num / check digits
        for i in range(len(cleaned_candidates)):
            l1 = cleaned_candidates[i]
            if (l1.startswith('P<') or (len(l1) >= 2 and l1[0] == 'P' and l1[1].isalpha())) and 36 <= len(l1) <= 52:
                for j in range(i + 1, min(i + 3, len(cleaned_candidates))):
                    l2 = cleaned_candidates[j]
                    if 36 <= len(l2) <= 52 and ('<' in l2 or re.search(r'\d', l2)):
                        logger.info("Found TD3 candidate pair at lines %d & %d", i, j)
                        return f"{l1}\n{l2}"

        # 2. Check for TD1 (3 lines of ~30 chars)
        td1_candidates = [l for l in cleaned_candidates if 26 <= len(l) <= 34]
        if len(td1_candidates) >= 3:
            return '\n'.join(td1_candidates[:3])

        # 3. Check for TD2 (2 lines of ~36 chars)
        td2_candidates = [l for l in cleaned_candidates if 32 <= len(l) <= 40]
        if len(td2_candidates) >= 2:
            return '\n'.join(td2_candidates[:2])

        # 4. Check for general TD3 length (~44 chars)
        td3_candidates = [l for l in cleaned_candidates if 40 <= len(l) <= 48]
        if len(td3_candidates) >= 2:
            return '\n'.join(td3_candidates[:2])

        # If we have at least 2 candidate lines, return first two
        if len(cleaned_candidates) >= 2:
            return '\n'.join(cleaned_candidates[:2])

        return cleaned_candidates[0]

    def _clean_line(self, line: str) -> str:
        """
        Clean OCR noise from candidate MRZ line without blindly replacing characters.
        - Strip margins (leading/trailing '|', spaces, punctuation)
        - Remove internal whitespace
        - Uppercase
        - Preserve '<' exactly
        """
        # Strip margin artifacts like '| ', ': ', etc.
        s = line.strip().strip('|').strip(':').strip(';').strip('~').strip('!').strip()
        # Remove internal spaces
        s = s.replace(' ', '').replace('\t', '')
        return s.upper()

    def _looks_like_mrz_line(self, line: str) -> bool:
        """Check if line is predominantly MRZ characters."""
        if len(line) < 20:
            return False
        mrz_count = sum(1 for c in line if c in MRZ_CHARS_SET)
        ratio = mrz_count / len(line)
        return ratio >= 0.70 and ('<' in line or any(c.isdigit() for c in line))


mrz_extractor = MRZExtractor()
