"""
Error Level Analysis (ELA) for document tamper detection.
ELA detects compression-level inconsistencies that may indicate image manipulation.

IMPORTANT DISCLAIMER:
ELA is an anomaly signal, NOT definitive proof of document forgery.
Results must be interpreted by a trained human investigator.
"""
import io
import logging
from typing import Dict, Any, List
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


class ELAAnalyzer:
    """
    Error Level Analysis implementation.
    Re-compresses the image at a lower quality and computes the pixel-level
    difference to identify regions with inconsistent compression levels.
    Regions with significantly higher ELA values may indicate manipulation.
    """

    def __init__(self, quality: int = 90):
        self.quality = quality

    def analyze(self, image_path: str) -> Dict[str, Any]:
        """
        Run ELA on an image file.
        Returns structured analysis with score, regions, and explanation.
        """
        try:
            original = Image.open(image_path).convert("RGB")
            ela_image, ela_array = self._compute_ela(original)

            ela_score = self._compute_ela_score(ela_array)
            anomaly_regions = self._detect_anomaly_regions(ela_array, original.size)
            reasons = self._generate_reasons(ela_score, anomaly_regions)

            return {
                "ela_score": round(ela_score, 3),
                "anomaly_regions": anomaly_regions,
                "reasons": reasons,
                "analysis_method": "Error Level Analysis (ELA)",
                "disclaimer": (
                    "ELA is an anomaly signal only. Elevated ELA scores may indicate "
                    "image manipulation but can also result from legitimate processing, "
                    "format conversion, or re-saving. Human expert review is required."
                ),
            }

        except Exception as e:
            logger.error("ELA analysis failed: %s", e)
            return {
                "ela_score": 0.5,
                "anomaly_regions": [],
                "reasons": [f"ELA analysis error: {str(e)}"],
                "analysis_method": "ELA (failed)",
                "disclaimer": "ELA could not be completed for this image.",
            }

    def _compute_ela(self, original: Image.Image) -> tuple:
        """Compute ELA image and return (PIL ela_image, numpy array)."""
        # Save at reduced quality
        buffer = io.BytesIO()
        original.save(buffer, format="JPEG", quality=self.quality)
        buffer.seek(0)
        compressed = Image.open(buffer).convert("RGB")

        # Compute pixel difference
        orig_arr = np.array(original, dtype=np.float32)
        comp_arr = np.array(compressed, dtype=np.float32)
        ela_arr = np.abs(orig_arr - comp_arr)

        # Scale for visualization
        max_val = ela_arr.max()
        if max_val > 0:
            scaled = (ela_arr / max_val * 255).astype(np.uint8)
        else:
            scaled = ela_arr.astype(np.uint8)

        ela_image = Image.fromarray(scaled)
        return ela_image, ela_arr

    def _compute_ela_score(self, ela_array: np.ndarray) -> float:
        """
        Compute a normalized ELA score (0-1).
        Higher score suggests more potential anomalies.
        """
        if ela_array.size == 0:
            return 0.0

        # Use mean of top 5% of values as the anomaly signal
        flat = ela_array.flatten()
        threshold = np.percentile(flat, 95)
        high_values = flat[flat >= threshold]

        if len(high_values) == 0:
            return 0.0

        score = float(np.mean(high_values)) / 255.0
        return min(score, 1.0)

    def _detect_anomaly_regions(
        self, ela_array: np.ndarray, image_size: tuple
    ) -> List[Dict[str, Any]]:
        """
        Identify regions with anomalously high ELA values.
        Returns list of bounding boxes with scores.
        """
        from PIL import Image as PILImage

        regions = []
        ela_gray = np.mean(ela_array, axis=2) if ela_array.ndim == 3 else ela_array
        height, width = ela_gray.shape

        # Divide into grid and find high-anomaly cells
        grid_h, grid_w = 4, 4
        cell_h = height // grid_h
        cell_w = width // grid_w

        global_mean = np.mean(ela_gray)
        global_std = np.std(ela_gray)
        threshold = global_mean + 2 * global_std

        for row in range(grid_h):
            for col in range(grid_w):
                y1 = row * cell_h
                y2 = min((row + 1) * cell_h, height)
                x1 = col * cell_w
                x2 = min((col + 1) * cell_w, width)

                cell = ela_gray[y1:y2, x1:x2]
                cell_mean = np.mean(cell)

                if cell_mean > threshold:
                    severity = "HIGH" if cell_mean > threshold * 1.5 else "MEDIUM"
                    # Normalize coordinates to 0-1 range
                    regions.append({
                        "x": round(x1 / width, 3),
                        "y": round(y1 / height, 3),
                        "width": round((x2 - x1) / width, 3),
                        "height": round((y2 - y1) / height, 3),
                        "ela_intensity": round(float(cell_mean), 3),
                        "severity": severity,
                        "label": f"Anomaly region ({row},{col})",
                    })

        return regions

    def _generate_reasons(self, ela_score: float, regions: List) -> List[str]:
        """Generate human-readable ELA findings."""
        reasons = []

        if ela_score > 0.7:
            reasons.append(
                f"High ELA score ({ela_score:.2f}): significant compression inconsistencies detected. "
                "This may indicate image manipulation — human review recommended."
            )
        elif ela_score > 0.4:
            reasons.append(
                f"Moderate ELA score ({ela_score:.2f}): some compression anomalies detected. "
                "Could indicate processing artifacts or potential manipulation."
            )
        else:
            reasons.append(
                f"Low ELA score ({ela_score:.2f}): compression levels appear consistent."
            )

        if regions:
            high_severity = [r for r in regions if r["severity"] == "HIGH"]
            if high_severity:
                reasons.append(
                    f"{len(high_severity)} high-severity anomaly region(s) detected. "
                    "Photo or text regions may have been altered."
                )

        return reasons
