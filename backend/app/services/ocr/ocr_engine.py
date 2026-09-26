"""
OCR engine wrapper.
Supports PaddleOCR 3.x (primary) and Tesseract (fallback).

PaddleOCR 3.x API (version >= 3.0):
  - Init:   PaddleOCR(lang='en')          — no use_angle_cls, no show_log
  - Call:   ocr.predict(image_path)        — returns generator of result objects
  - Result: each item has .rec_texts (list[str]) and .rec_scores (list[float])
  - NOTE:   Requires PaddlePaddle >= 3.0 (2.x causes ConvertPirAttribute errors)

Tesseract fallback:
  - pytesseract with hardcoded Windows path if not in PATH
  - MRZ-optimized extraction uses character whitelist + PSM 6
"""
import logging
import os
import tempfile
from typing import Optional, List, Any
import numpy as np
import cv2

from app.core.config import settings

logger = logging.getLogger(__name__)

# Windows default Tesseract install location
TESSERACT_WIN_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# MRZ character whitelist for Tesseract (ICAO 9303 characters + common OCR confusions)
TESSERACT_MRZ_CONFIG = (
    "--psm 6 --oem 3 "
    "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"
)

TESSERACT_GENERAL_CONFIG = "--psm 3 --oem 3"


class OCRResult:
    """Structured OCR output."""
    def __init__(
        self,
        raw_text: str,
        confidence: float,
        lines: List[str],
        boxes: Optional[List] = None,
        raw_output: Optional[Any] = None,
        engine_used: str = "",
    ):
        self.raw_text = raw_text
        self.confidence = confidence
        self.lines = lines
        self.boxes = boxes or []
        self.raw_output = raw_output  # preserve for debugging
        self.engine_used = engine_used


class OCREngine:
    """
    Strategy-pattern OCR engine.
    Uses PaddleOCR 3.x if available and functional, falls back to Tesseract.
    """

    def __init__(self):
        self._paddle = None
        self._tesseract_available = False
        self._engine_name = "none"
        self._paddle_version = 0
        # Set Tesseract path early so all calls use it
        self._set_tesseract_path()
        self._initialize()

    def _set_tesseract_path(self):
        """Set Tesseract binary path on Windows before any pytesseract calls."""
        if os.name == "nt" and os.path.isfile(TESSERACT_WIN_PATH):
            try:
                import pytesseract
                pytesseract.pytesseract.tesseract_cmd = TESSERACT_WIN_PATH
                logger.info("Pre-set Tesseract path: %s", TESSERACT_WIN_PATH)
            except ImportError:
                pass

    def _initialize(self):
        """Initialize the configured OCR engine."""
        if settings.OCR_ENGINE == "paddleocr":
            self._paddle = self._try_init_paddle()
            if self._paddle:
                self._engine_name = "paddleocr"
                return

        # Try Tesseract
        if self._try_init_tesseract():
            self._tesseract_available = True
            self._engine_name = "tesseract"
            return

        logger.warning(
            "No OCR engine available. OCR will return empty results. "
            "Install paddleocr (with paddlepaddle>=3.0) or pytesseract + Tesseract binary."
        )

    def _try_init_paddle(self):
        """Attempt to initialize PaddleOCR 3.x."""
        try:
            import paddleocr
            version_str = getattr(paddleocr, "__version__", "2.0.0")
            major_version = int(version_str.split(".")[0])
            self._paddle_version = major_version
            logger.info("PaddleOCR version: %s (major=%d)", version_str, major_version)

            from paddleocr import PaddleOCR

            if major_version >= 3:
                ocr = PaddleOCR(lang="en")
            else:
                ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)

            # Validate it actually works by running on a tiny test image
            if not self._validate_paddle(ocr, major_version):
                logger.warning("PaddleOCR initialized but failed validation test — falling back to Tesseract")
                return None

            logger.info("PaddleOCR %s initialized and validated successfully", version_str)
            return ocr
        except ImportError:
            logger.info("PaddleOCR not installed, trying Tesseract")
            return None
        except Exception as e:
            logger.warning("PaddleOCR init failed: %s", e)
            return None

    def _validate_paddle(self, ocr, major_version: int) -> bool:
        """Quick sanity-check: run OCR on a tiny image to catch runtime errors."""
        import tempfile
        try:
            from PIL import Image, ImageDraw
            img = Image.new("RGB", (200, 50), color="white")
            draw = ImageDraw.Draw(img)
            draw.text((5, 10), "TEST 123", fill="black")
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                tmp = f.name
            img.save(tmp)
            try:
                if major_version >= 3:
                    # predict() returns a generator
                    results = list(ocr.predict(tmp))
                else:
                    results = ocr.ocr(tmp, cls=True)
                logger.debug("PaddleOCR validation succeeded, got %d results", len(results))
                return True
            except Exception as e:
                err_str = str(e)
                # Catch all known PaddlePaddle/PIR incompatibility errors
                known_errors = [
                    "ConvertPirAttribute",
                    "Unimplemented",
                    "InvalidArgument",
                    "strides is not right",
                    "pir::Int32Attribute",
                    "pir::ArrayAttribute",
                ]
                if any(kw in err_str for kw in known_errors):
                    logger.warning(
                        "PaddleOCR runtime error (PaddlePaddle/PaddleOCR version incompatible): %s", e
                    )
                else:
                    logger.warning("PaddleOCR validation failed: %s", e)
                return False
            finally:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
        except Exception as e:
            logger.warning("PaddleOCR validation setup failed: %s", e)
            return False

    def _try_init_tesseract(self) -> bool:
        """Check if Tesseract binary + pytesseract are available."""
        try:
            import pytesseract

            # On Windows, set the path if not in PATH
            if os.name == "nt" and os.path.isfile(TESSERACT_WIN_PATH):
                pytesseract.pytesseract.tesseract_cmd = TESSERACT_WIN_PATH
                logger.info("Set Tesseract path: %s", TESSERACT_WIN_PATH)

            ver = pytesseract.get_tesseract_version()
            logger.info("Tesseract initialized successfully (version %s)", ver)
            return True
        except Exception as e:
            logger.info("Tesseract not available: %s", e)
            return False

    # ─── Public interface ─────────────────────────────────────────────────────

    def extract_text(self, image_path: str) -> OCRResult:
        """
        Extract text from an image file path.
        Returns OCRResult with raw text, confidence, and line list.
        """
        if self._paddle:
            return self._paddle_extract(image_path)
        elif self._tesseract_available:
            return self._tesseract_extract(image_path)
        else:
            logger.error("No OCR engine available")
            return OCRResult(raw_text="", confidence=0.0, lines=[], engine_used="none")

    def extract_text_from_array(self, img_array: np.ndarray) -> OCRResult:
        """
        Extract text from a numpy image array.
        Saves to a temp PNG for PaddleOCR (file-path mode is more reliable).
        """
        if self._paddle:
            return self._paddle_extract_array(img_array)
        elif self._tesseract_available:
            return self._tesseract_extract_array(img_array)
        else:
            return OCRResult(raw_text="", confidence=0.0, lines=[], engine_used="none")

    def extract_mrz_text(self, img_array: np.ndarray) -> OCRResult:
        """
        Extract text from an image array using MRZ-optimized settings.
        Uses character whitelist and PSM 6 (uniform block) for MRZ lines.
        Returns OCRResult with raw text from MRZ region.
        """
        if self._tesseract_available:
            return self._tesseract_extract_mrz(img_array)
        elif self._paddle:
            return self._paddle_extract_array(img_array)
        else:
            return OCRResult(raw_text="", confidence=0.0, lines=[], engine_used="none")

    # ─── PaddleOCR extraction ─────────────────────────────────────────────────

    def _paddle_extract(self, image_path: str) -> OCRResult:
        """Run PaddleOCR on a file path."""
        try:
            if self._paddle_version >= 3:
                results = list(self._paddle.predict(image_path))
            else:
                results = self._paddle.ocr(image_path, cls=True)

            parsed = self._parse_paddle_result(results)
            logger.info(
                "PaddleOCR extracted %d lines from %s (conf=%.2f)",
                len(parsed.lines), os.path.basename(image_path), parsed.confidence
            )
            if parsed.lines:
                logger.debug("OCR lines (first 5): %s", parsed.lines[:5])
            return parsed
        except Exception as e:
            logger.error("PaddleOCR file extraction failed: %s", e, exc_info=True)
            return OCRResult(raw_text="", confidence=0.0, lines=[], engine_used="paddleocr_error")

    def _paddle_extract_array(self, img_array: np.ndarray) -> OCRResult:
        """Run PaddleOCR on a numpy array by saving to a temp file first."""
        tmp_path = None
        try:
            # Ensure 3-channel BGR
            if len(img_array.shape) == 2:
                img_bgr = cv2.cvtColor(img_array, cv2.COLOR_GRAY2BGR)
            elif img_array.shape[2] == 4:
                img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGBA2BGR)
            else:
                img_bgr = img_array.copy()

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name
            cv2.imwrite(tmp_path, img_bgr)

            return self._paddle_extract(tmp_path)
        except Exception as e:
            logger.error("PaddleOCR array extraction failed: %s", e, exc_info=True)
            return OCRResult(raw_text="", confidence=0.0, lines=[], engine_used="paddleocr_error")
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    def _parse_paddle_result(self, result) -> OCRResult:
        """
        Parse PaddleOCR output into OCRResult.

        PaddleOCR 3.x format (predict() generator):
            Each item has .rec_texts (list[str]) and .rec_scores (list[float])
            and .dt_polys (list[ndarray]) for bounding boxes

        PaddleOCR 2.x format (ocr() return):
            result[0] = list of [bbox_points, [text, confidence]]
            (result[0] may be None if no text found)
        """
        lines = []
        confidences = []
        boxes = []

        if result is None:
            logger.debug("PaddleOCR returned None")
            return OCRResult(raw_text="", confidence=0.0, lines=[], engine_used="paddleocr")

        logger.debug("PaddleOCR result type=%s, length=%s",
                     type(result).__name__, len(result) if hasattr(result, '__len__') else "?")

        try:
            if not result:
                return OCRResult(raw_text="", confidence=0.0, lines=[], engine_used="paddleocr")

            first = result[0] if isinstance(result, (list, tuple)) else result

            # ── PaddleOCR 3.x: result objects with rec_texts attribute ────────
            if hasattr(first, 'rec_texts'):
                for res_obj in result:
                    texts = getattr(res_obj, 'rec_texts', None) or []
                    scores = getattr(res_obj, 'rec_scores', None) or []
                    polys = getattr(res_obj, 'dt_polys', None) or []
                    for i, text in enumerate(texts):
                        if text and str(text).strip():
                            score = float(scores[i]) if i < len(scores) else 0.8
                            lines.append(str(text).strip())
                            confidences.append(score)
                            if i < len(polys):
                                boxes.append(polys[i])
                logger.debug("Parsed 3.x object format: %d lines", len(lines))

            # ── PaddleOCR 3.x: dict-style result ─────────────────────────────
            elif isinstance(first, dict) and 'rec_texts' in first:
                for res_dict in result:
                    texts = res_dict.get('rec_texts', []) or []
                    scores = res_dict.get('rec_scores', []) or []
                    polys = res_dict.get('dt_polys', []) or []
                    for i, text in enumerate(texts):
                        if text and str(text).strip():
                            score = float(scores[i]) if i < len(scores) else 0.8
                            lines.append(str(text).strip())
                            confidences.append(score)
                            if i < len(polys):
                                boxes.append(polys[i])
                logger.debug("Parsed 3.x dict format: %d lines", len(lines))

            # ── PaddleOCR 2.x: nested list [[bbox, [text, conf]], ...] ────────
            elif isinstance(first, list):
                content = first  # result[0]
                if content is None:
                    logger.debug("PaddleOCR 2.x returned None content (no text)")
                elif isinstance(content, list):
                    for item in content:
                        if not item or len(item) < 2:
                            continue
                        bbox = item[0]
                        text_part = item[1]
                        if isinstance(text_part, (list, tuple)) and len(text_part) >= 2:
                            text = str(text_part[0])
                            conf = float(text_part[1])
                        else:
                            text = str(text_part)
                            conf = 0.8
                        if text.strip():
                            lines.append(text.strip())
                            confidences.append(conf)
                            boxes.append(bbox)
                logger.debug("Parsed 2.x nested format: %d lines", len(lines))

            else:
                logger.warning("Unknown PaddleOCR result format: %s", type(first).__name__)
                # Last resort — try recursive extraction
                self._extract_text_fallback(result, lines, confidences)

        except Exception as e:
            logger.error("Error parsing PaddleOCR result: %s", e, exc_info=True)

        raw_text = "\n".join(lines)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        logger.info("OCR parsed: %d lines, avg_conf=%.2f", len(lines), avg_confidence)
        return OCRResult(
            raw_text=raw_text,
            confidence=avg_confidence,
            lines=lines,
            boxes=boxes,
            raw_output=result,
            engine_used="paddleocr",
        )

    def _extract_text_fallback(self, result, lines: list, confidences: list):
        """Recursively search result for text strings."""
        if isinstance(result, str) and result.strip():
            lines.append(result.strip())
            confidences.append(0.5)
        elif isinstance(result, (list, tuple)):
            for item in result:
                self._extract_text_fallback(item, lines, confidences)
        elif isinstance(result, dict):
            for key in ('text', 'rec_texts', 'transcription', 'words'):
                val = result.get(key)
                if val:
                    self._extract_text_fallback(val, lines, confidences)

    # ─── Tesseract extraction ─────────────────────────────────────────────────

    def _tesseract_extract(self, image_path: str) -> OCRResult:
        """Run Tesseract on a file with general document config."""
        try:
            import pytesseract
            from PIL import Image

            if os.name == "nt" and os.path.isfile(TESSERACT_WIN_PATH):
                pytesseract.pytesseract.tesseract_cmd = TESSERACT_WIN_PATH

            img = Image.open(image_path)
            data = pytesseract.image_to_data(
                img,
                output_type=pytesseract.Output.DICT,
                config=TESSERACT_GENERAL_CONFIG,
            )
            result = self._parse_tesseract_data(data, engine_used="tesseract")
            logger.info(
                "Tesseract extracted %d lines from %s (conf=%.2f)",
                len(result.lines), os.path.basename(image_path), result.confidence
            )
            if result.lines:
                logger.info("Tesseract raw lines (first 10): %s", result.lines[:10])
            return result
        except Exception as e:
            logger.error("Tesseract extraction failed: %s", e)
            return OCRResult(raw_text="", confidence=0.0, lines=[], engine_used="tesseract_error")

    def _tesseract_extract_array(self, img_array: np.ndarray) -> OCRResult:
        """Run Tesseract on a numpy array with general document config."""
        try:
            import pytesseract
            from PIL import Image

            if os.name == "nt" and os.path.isfile(TESSERACT_WIN_PATH):
                pytesseract.pytesseract.tesseract_cmd = TESSERACT_WIN_PATH

            if len(img_array.shape) == 2:
                img_pil = Image.fromarray(img_array)
            else:
                img_rgb = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
                img_pil = Image.fromarray(img_rgb)

            data = pytesseract.image_to_data(
                img_pil,
                output_type=pytesseract.Output.DICT,
                config=TESSERACT_GENERAL_CONFIG,
            )
            return self._parse_tesseract_data(data, engine_used="tesseract")
        except Exception as e:
            logger.error("Tesseract array extraction failed: %s", e)
            return OCRResult(raw_text="", confidence=0.0, lines=[], engine_used="tesseract_error")

    def _tesseract_extract_mrz(self, img_array: np.ndarray) -> OCRResult:
        """
        Run Tesseract on a numpy array with MRZ-optimized settings.
        Uses PSM 6 (uniform text block) and restricts to MRZ characters.
        This is critical for reliable MRZ line extraction.
        """
        try:
            import pytesseract
            from PIL import Image

            if os.name == "nt" and os.path.isfile(TESSERACT_WIN_PATH):
                pytesseract.pytesseract.tesseract_cmd = TESSERACT_WIN_PATH

            if len(img_array.shape) == 2:
                img_pil = Image.fromarray(img_array)
            else:
                img_rgb = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
                img_pil = Image.fromarray(img_rgb)

            # Use MRZ-specific config: PSM 6, whitelist, high DPI hint
            raw_text = pytesseract.image_to_string(
                img_pil,
                config=TESSERACT_MRZ_CONFIG,
            )
            lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
            logger.info("Tesseract MRZ mode: %d lines extracted", len(lines))
            if lines:
                logger.debug("Tesseract MRZ lines: %s", lines)

            return OCRResult(
                raw_text=raw_text,
                confidence=0.8 if lines else 0.0,
                lines=lines,
                engine_used="tesseract_mrz",
            )
        except Exception as e:
            logger.error("Tesseract MRZ extraction failed: %s", e)
            return OCRResult(raw_text="", confidence=0.0, lines=[], engine_used="tesseract_mrz_error")

    def _parse_tesseract_data(self, data: dict, engine_used: str = "tesseract") -> OCRResult:
        """Parse Tesseract image_to_data dict into OCRResult."""
        texts = []
        confidences = []
        current_line = []
        current_line_num = -1

        for i, text in enumerate(data["text"]):
            conf = int(data["conf"][i])
            line_num = data["line_num"][i]
            if conf > 20 and text.strip():  # Lowered threshold from 30 to 20
                if line_num != current_line_num:
                    if current_line:
                        texts.append(" ".join(current_line))
                    current_line = [text.strip()]
                    current_line_num = line_num
                else:
                    current_line.append(text.strip())
                confidences.append(float(conf) / 100.0)

        if current_line:
            texts.append(" ".join(current_line))

        raw_text = "\n".join(texts)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        return OCRResult(
            raw_text=raw_text,
            confidence=avg_confidence,
            lines=texts,
            engine_used=engine_used,
        )

    @property
    def engine_name(self) -> str:
        return self._engine_name


ocr_engine = OCREngine()
