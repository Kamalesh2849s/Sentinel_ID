"""
Image consistency analyzer for document tamper detection.
Checks for noise inconsistencies, color histogram anomalies,
and edge artifacts that may indicate document manipulation.
"""
import logging
from typing import Dict, Any, List
import cv2
import numpy as np

logger = logging.getLogger(__name__)


class ConsistencyAnalyzer:
    """
    Analyzes document images for internal consistency.
    Looks for signs of cut-and-paste, photo replacement, or text alteration.
    """

    def analyze(self, image_path: str) -> Dict[str, Any]:
        """
        Run consistency analysis on a document image.
        Returns structured results with score and reasons.
        """
        try:
            img = cv2.imread(image_path)
            if img is None:
                return self._error_result("Cannot load image")

            results = {}
            reasons = []
            scores = []

            # 1. Noise consistency across regions
            noise_result = self._analyze_noise_consistency(img)
            results["noise"] = noise_result
            scores.append(noise_result["anomaly_score"])
            reasons.extend(noise_result["reasons"])

            # 2. Color histogram consistency
            color_result = self._analyze_color_histogram(img)
            results["color"] = color_result
            scores.append(color_result["anomaly_score"])
            reasons.extend(color_result["reasons"])

            # 3. Edge density analysis
            edge_result = self._analyze_edge_density(img)
            results["edges"] = edge_result
            scores.append(edge_result["anomaly_score"])
            reasons.extend(edge_result["reasons"])

            # 4. JPEG blocking artifacts
            blocking_result = self._analyze_blocking_artifacts(img)
            results["blocking"] = blocking_result
            scores.append(blocking_result["anomaly_score"])
            reasons.extend(blocking_result["reasons"])

            consistency_score = float(np.mean(scores))

            return {
                "consistency_score": round(consistency_score, 3),
                "sub_results": results,
                "reasons": reasons,
                "analysis_method": "Image Consistency Analysis",
            }

        except Exception as e:
            logger.error("Consistency analysis failed: %s", e)
            return {
                "consistency_score": 0.5,
                "sub_results": {},
                "reasons": [f"Consistency analysis error: {str(e)}"],
                "analysis_method": "Consistency Analysis (failed)",
            }

    def _analyze_noise_consistency(self, img: np.ndarray) -> Dict[str, Any]:
        """
        Measure noise level consistency across image regions.
        Inconsistent noise may indicate spliced regions.
        """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        height, width = gray.shape

        # Divide into quadrants
        regions = [
            gray[0:height//2, 0:width//2],
            gray[0:height//2, width//2:width],
            gray[height//2:height, 0:width//2],
            gray[height//2:height, width//2:width],
        ]

        noise_levels = []
        for region in regions:
            # Estimate noise as std of Laplacian
            laplacian = cv2.Laplacian(region, cv2.CV_64F)
            noise_levels.append(float(np.std(laplacian)))

        if not noise_levels:
            return {"anomaly_score": 0.3, "reasons": [], "noise_levels": []}

        mean_noise = np.mean(noise_levels)
        max_deviation = max(abs(n - mean_noise) for n in noise_levels)
        coefficient_of_variation = np.std(noise_levels) / mean_noise if mean_noise > 0 else 0

        # High variation = inconsistent noise = anomaly signal
        anomaly_score = min(coefficient_of_variation / 2.0, 1.0)

        reasons = []
        if anomaly_score > 0.5:
            reasons.append(
                f"Noise inconsistency detected across document regions (CV={coefficient_of_variation:.2f}). "
                "This may indicate spliced content."
            )
        elif anomaly_score > 0.3:
            reasons.append("Moderate noise variation across regions.")
        else:
            reasons.append("Noise levels appear consistent across regions.")

        return {
            "anomaly_score": round(anomaly_score, 3),
            "reasons": reasons,
            "noise_levels": [round(n, 2) for n in noise_levels],
            "coefficient_of_variation": round(coefficient_of_variation, 3),
        }

    def _analyze_color_histogram(self, img: np.ndarray) -> Dict[str, Any]:
        """
        Compare color histograms across image regions.
        Abrupt histogram changes may indicate spliced photo regions.
        """
        height, width = img.shape[:2]
        h_mid = height // 2
        w_mid = width // 2

        # Only compare regions likely to share color characteristics
        regions = {
            "top_left": img[0:h_mid, 0:w_mid],
            "top_right": img[0:h_mid, w_mid:width],
            "bottom_left": img[h_mid:height, 0:w_mid],
            "bottom_right": img[h_mid:height, w_mid:width],
        }

        histograms = {}
        for name, region in regions.items():
            hist = cv2.calcHist([region], [0, 1, 2], None,
                                [8, 8, 8], [0, 256, 0, 256, 0, 256])
            hist = cv2.normalize(hist, hist).flatten()
            histograms[name] = hist

        # Compare adjacent regions
        region_names = list(histograms.keys())
        distances = []
        for i in range(len(region_names)):
            for j in range(i + 1, len(region_names)):
                dist = cv2.compareHist(
                    histograms[region_names[i]],
                    histograms[region_names[j]],
                    cv2.HISTCMP_BHATTACHARYYA
                )
                distances.append(dist)

        max_distance = max(distances) if distances else 0
        mean_distance = np.mean(distances) if distances else 0

        # High histogram distance = color inconsistency
        anomaly_score = min(max_distance, 1.0)

        reasons = []
        if anomaly_score > 0.7:
            reasons.append(
                "Significant color inconsistency between document regions. "
                "Photo area may have been replaced."
            )
        elif anomaly_score > 0.4:
            reasons.append("Moderate color variation between regions. Could be normal.")
        else:
            reasons.append("Color distribution appears consistent.")

        return {
            "anomaly_score": round(anomaly_score, 3),
            "max_histogram_distance": round(max_distance, 3),
            "mean_histogram_distance": round(mean_distance, 3),
            "reasons": reasons,
        }

    def _analyze_edge_density(self, img: np.ndarray) -> Dict[str, Any]:
        """
        Analyze edge density across regions.
        Artificially inserted text/photos often show unnatural edge patterns.
        """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)

        height, width = edges.shape
        grid_size = 4
        cell_h = height // grid_size
        cell_w = width // grid_size

        densities = []
        for row in range(grid_size):
            for col in range(grid_size):
                y1, y2 = row * cell_h, (row + 1) * cell_h
                x1, x2 = col * cell_w, (col + 1) * cell_w
                cell = edges[y1:y2, x1:x2]
                density = np.mean(cell) / 255.0
                densities.append(density)

        if not densities:
            return {"anomaly_score": 0.3, "reasons": []}

        mean_density = np.mean(densities)
        std_density = np.std(densities)
        cv = std_density / mean_density if mean_density > 0 else 0

        anomaly_score = min(cv / 3.0, 1.0)
        reasons = []
        if anomaly_score > 0.5:
            reasons.append("Uneven edge density distribution may indicate inserted content.")
        else:
            reasons.append("Edge density distribution appears normal.")

        return {
            "anomaly_score": round(anomaly_score, 3),
            "mean_edge_density": round(mean_density, 3),
            "edge_density_std": round(std_density, 3),
            "reasons": reasons,
        }

    def _analyze_blocking_artifacts(self, img: np.ndarray) -> Dict[str, Any]:
        """
        Analyze JPEG blocking artifacts.
        Inconsistent blocking patterns may indicate multiple compression history.
        """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
        height, width = gray.shape

        # Sample block boundaries (JPEG uses 8x8 blocks)
        h_diffs = []
        v_diffs = []

        for y in range(8, height - 8, 8):
            row_diff = np.mean(np.abs(gray[y, :] - gray[y-1, :]))
            h_diffs.append(row_diff)

        for x in range(8, width - 8, 8):
            col_diff = np.mean(np.abs(gray[:, x] - gray[:, x-1]))
            v_diffs.append(col_diff)

        all_diffs = h_diffs + v_diffs
        if not all_diffs:
            return {"anomaly_score": 0.3, "reasons": []}

        std_diff = np.std(all_diffs)
        mean_diff = np.mean(all_diffs)
        anomaly_score = min(std_diff / (mean_diff + 1e-6) / 5.0, 1.0)

        reasons = []
        if anomaly_score > 0.5:
            reasons.append(
                "Inconsistent JPEG block boundaries detected — may indicate "
                "different compression history in different regions."
            )
        else:
            reasons.append("JPEG compression artifacts appear consistent.")

        return {
            "anomaly_score": round(anomaly_score, 3),
            "blocking_variability": round(float(std_diff), 3),
            "reasons": reasons,
        }

    def _error_result(self, message: str) -> Dict[str, Any]:
        return {
            "consistency_score": 0.5,
            "sub_results": {},
            "reasons": [message],
            "analysis_method": "Consistency Analysis (error)",
        }
