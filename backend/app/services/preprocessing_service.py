"""
Image preprocessing service.
Prepares document images for OCR and analysis with robust multi-step pipeline.
"""
import logging
import os
import tempfile
from typing import Tuple, Optional
import cv2
import numpy as np
from PIL import Image, ImageEnhance
import io

logger = logging.getLogger(__name__)


class PreprocessingService:
    """
    Preprocesses document images for optimal OCR and analysis quality.
    Steps: load → validate → resize → orient → denoise → enhance → sharpen → prepare

    Returns both the preprocessed image AND saves a preprocessed version to disk
    so OCR engines that work better with file paths can use it.
    """

    MAX_DIMENSION = 4096
    MIN_DIMENSION = 600   # Raised from 400 — PaddleOCR needs decent resolution
    TARGET_DPI = 300

    def preprocess_for_ocr(self, image_path: str) -> Tuple[np.ndarray, Image.Image]:
        """
        Full preprocessing pipeline for OCR.
        Returns (cv2 BGR array, PIL Image).
        """
        # Load image
        img_cv = cv2.imread(image_path)
        if img_cv is None:
            raise ValueError(f"Cannot load image: {image_path}")

        logger.info(
            "Preprocessing image: %s, original shape: %s",
            os.path.basename(image_path), img_cv.shape
        )

        # Resize to optimal dimensions
        img_cv = self._resize_image(img_cv)

        # Auto-rotate based on content
        img_cv = self._correct_orientation(img_cv)

        # Light denoising (preserve edges for OCR)
        img_cv = self._denoise(img_cv)

        # Enhance contrast
        img_cv = self._enhance_contrast(img_cv)

        # Sharpen for better OCR
        img_cv = self._sharpen(img_cv)

        logger.info("Preprocessed image shape: %s", img_cv.shape)

        # Convert to PIL for flexibility
        img_pil = Image.fromarray(cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB))

        return img_cv, img_pil

    def save_preprocessed(self, img_cv: np.ndarray, original_path: str) -> str:
        """
        Save preprocessed image to a temp file alongside the original.
        Returns path to the saved preprocessed image.
        """
        base, ext = os.path.splitext(original_path)
        preprocessed_path = base + "_preprocessed.png"
        cv2.imwrite(preprocessed_path, img_cv)
        logger.debug("Saved preprocessed image to: %s", preprocessed_path)
        return preprocessed_path

    def preprocess_for_ela(self, image_path: str) -> Image.Image:
        """Load image as PIL for ELA analysis."""
        img = Image.open(image_path).convert("RGB")
        img = self._resize_pil(img)
        return img

    def preprocess_for_face(self, image_path: str) -> np.ndarray:
        """Preprocess image for face detection."""
        img_cv = cv2.imread(image_path)
        if img_cv is None:
            raise ValueError(f"Cannot load image: {image_path}")
        img_cv = self._resize_image(img_cv)
        return img_cv

    def extract_mrz_region(self, img_cv: np.ndarray) -> Optional[np.ndarray]:
        """
        Attempt to isolate the MRZ zone (bottom portion of passport).
        Returns cropped MRZ region or None.
        """
        height, width = img_cv.shape[:2]
        # MRZ is typically in bottom 25-30% of passport image
        mrz_start = int(height * 0.70)
        mrz_region = img_cv[mrz_start:height, 0:width]
        return mrz_region

    def prepare_mrz_region_for_ocr(self, mrz_region: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare MRZ region specifically for OCR.
        Returns (color_enhanced, grayscale_binary) — color version preferred for PaddleOCR 3.x.

        For MRZ specifically:
        - Scale up to help with small text
        - High contrast black-on-white
        - Clean binary threshold
        """
        if mrz_region is None or mrz_region.size == 0:
            raise ValueError("Empty MRZ region")

        h, w = mrz_region.shape[:2]

        # Scale up if too small
        if h < 60:
            scale = 60 / h
            mrz_region = cv2.resize(mrz_region, None, fx=scale, fy=scale,
                                    interpolation=cv2.INTER_CUBIC)

        # Color enhanced version (for PaddleOCR 3.x)
        gray = cv2.cvtColor(mrz_region, cv2.COLOR_BGR2GRAY)

        # Adaptive threshold for variable lighting
        adaptive = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )

        # Otsu threshold
        _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Pick whichever has more white (text-on-white is standard)
        if np.mean(adaptive) > np.mean(otsu):
            binary = adaptive
        else:
            binary = otsu

        # Convert binary back to BGR for PaddleOCR
        binary_bgr = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)

        # Also produce a contrast-enhanced color version
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
        enhanced_gray = clahe.apply(gray)
        color_enhanced = cv2.cvtColor(enhanced_gray, cv2.COLOR_GRAY2BGR)

        return color_enhanced, binary_bgr

    # ─── Private helpers ──────────────────────────────────────────────────────

    def _resize_image(self, img: np.ndarray) -> np.ndarray:
        """Resize image to within MAX_DIMENSION while preserving aspect ratio."""
        h, w = img.shape[:2]
        max_dim = max(h, w)
        if max_dim > self.MAX_DIMENSION:
            scale = self.MAX_DIMENSION / max_dim
            new_w = int(w * scale)
            new_h = int(h * scale)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        elif max_dim < self.MIN_DIMENSION:
            scale = self.MIN_DIMENSION / max_dim
            new_w = int(w * scale)
            new_h = int(h * scale)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
        return img

    def _resize_pil(self, img: Image.Image) -> Image.Image:
        """Resize PIL image."""
        w, h = img.size
        max_dim = max(h, w)
        if max_dim > self.MAX_DIMENSION:
            scale = self.MAX_DIMENSION / max_dim
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        return img

    def _correct_orientation(self, img: np.ndarray) -> np.ndarray:
        """
        Attempt basic orientation correction.
        For production: use EXIF data or ML-based orientation detection.
        """
        # Basic: ensure image is wider than tall (landscape for passport)
        h, w = img.shape[:2]
        if h > w * 1.5:
            # Likely portrait — rotate 90 degrees
            img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        return img

    def _denoise(self, img: np.ndarray) -> np.ndarray:
        """Apply light noise reduction — preserve text edges."""
        # Use lighter denoising to preserve text sharpness
        # h=5 is lighter than the previous h=7 — less blurring of text
        try:
            return cv2.fastNlMeansDenoisingColored(img, None, 5, 5, 7, 21)
        except Exception as e:
            logger.warning("Denoising failed: %s", e)
            return img

    def _enhance_contrast(self, img: np.ndarray) -> np.ndarray:
        """Apply CLAHE for local contrast enhancement."""
        try:
            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l = clahe.apply(l)
            enhanced = cv2.merge((l, a, b))
            return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
        except Exception as e:
            logger.warning("Contrast enhancement failed: %s", e)
            return img

    def _sharpen(self, img: np.ndarray) -> np.ndarray:
        """Apply unsharp mask sharpening for crisper text."""
        try:
            gaussian = cv2.GaussianBlur(img, (0, 0), 2.0)
            sharpened = cv2.addWeighted(img, 1.5, gaussian, -0.5, 0)
            return sharpened
        except Exception as e:
            logger.warning("Sharpening failed: %s", e)
            return img

    def prepare_mrz_for_ocr(self, mrz_region: np.ndarray) -> np.ndarray:
        """
        Legacy method — prepare MRZ region for text extraction.
        Kept for backward compatibility.
        """
        gray = cv2.cvtColor(mrz_region, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        cleaned = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        return cleaned


preprocessing_service = PreprocessingService()
