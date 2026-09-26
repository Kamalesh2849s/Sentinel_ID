"""
Tamper detection orchestrator.
Combines ELA and consistency analysis into a single tamper detection result.

Architecture:
TamperDetector
├── ELAAnalyzer
├── ConsistencyAnalyzer
└── CNNForgeryDetector (interface for future model integration)

IMPORTANT:
- Results are anomaly signals only, not definitive forgery detection
- A trained CNN model can be integrated via the CNNForgeryDetector interface
- Never claim an untrained model is detecting fraud
"""
import logging
from typing import Dict, Any, List, Optional

from app.services.tamper.ela_analyzer import ELAAnalyzer
from app.services.tamper.consistency_analyzer import ConsistencyAnalyzer

logger = logging.getLogger(__name__)


class CNNForgeryDetector:
    """
    Interface for a trained CNN-based forgery detection model.
    Currently a placeholder — integrate a trained model here when available.

    To integrate a model:
    1. Load model weights in __init__
    2. Implement analyze() to return a score (0-1)
    3. Set self.model_available = True
    """

    def __init__(self):
        self.model_available = False
        logger.info(
            "CNNForgeryDetector: No trained model loaded. "
            "CNN-based forgery detection is disabled. "
            "To enable, load a trained model in CNNForgeryDetector.__init__()."
        )

    def analyze(self, image_path: str) -> Dict[str, Any]:
        """Returns a placeholder result when no model is available."""
        return {
            "cnn_score": None,
            "model_available": False,
            "message": (
                "CNN-based forgery detection is not available in this prototype. "
                "A trained model can be integrated via the CNNForgeryDetector interface."
            ),
        }


class TamperDetector:
    """
    Main tamper detection service.
    Combines multiple analysis methods into a unified tamper score.
    """

    # Weights for combining analysis signals
    ELA_WEIGHT = 0.45
    CONSISTENCY_WEIGHT = 0.45
    CNN_WEIGHT = 0.10  # Reserved for when CNN model is available

    # Thresholds
    TAMPER_DETECTION_THRESHOLD = 0.55
    HIGH_CONFIDENCE_THRESHOLD = 0.75

    def __init__(self):
        self.ela_analyzer = ELAAnalyzer()
        self.consistency_analyzer = ConsistencyAnalyzer()
        self.cnn_detector = CNNForgeryDetector()

    def analyze(self, image_path: str) -> Dict[str, Any]:
        """
        Run full tamper detection pipeline.
        Returns structured tamper result with score, confidence, and reasons.
        """
        logger.info("Running tamper detection on: %s", image_path)

        # Run all analyzers
        ela_result = self.ela_analyzer.analyze(image_path)
        consistency_result = self.consistency_analyzer.analyze(image_path)
        cnn_result = self.cnn_detector.analyze(image_path)

        # Compute weighted score
        ela_score = ela_result.get("ela_score", 0.5)
        consistency_score = consistency_result.get("consistency_score", 0.5)

        if self.cnn_detector.model_available:
            cnn_score = cnn_result.get("cnn_score", 0.0)
            tamper_score = (
                ela_score * self.ELA_WEIGHT
                + consistency_score * self.CONSISTENCY_WEIGHT
                + cnn_score * self.CNN_WEIGHT
            )
        else:
            # Redistribute CNN weight to ELA and consistency when no model
            ela_w = self.ELA_WEIGHT / (self.ELA_WEIGHT + self.CONSISTENCY_WEIGHT)
            con_w = self.CONSISTENCY_WEIGHT / (self.ELA_WEIGHT + self.CONSISTENCY_WEIGHT)
            tamper_score = ela_score * ela_w + consistency_score * con_w

        tamper_score = round(min(tamper_score, 1.0), 3)
        tamper_detected = tamper_score > self.TAMPER_DETECTION_THRESHOLD
        confidence = self._compute_confidence(ela_score, consistency_score, tamper_score)

        # Collect all reasons
        all_reasons = (
            ela_result.get("reasons", [])
            + consistency_result.get("reasons", [])
        )

        # Add CNN disclaimer to reasons
        all_reasons.append(cnn_result.get("message", ""))

        # Collect anomaly regions from ELA
        regions = ela_result.get("anomaly_regions", [])

        result = {
            "tamper_detected": tamper_detected,
            "tamper_score": tamper_score,
            "confidence": round(confidence, 3),
            "ela_score": ela_score,
            "consistency_score": consistency_score,
            "cnn_available": self.cnn_detector.model_available,
            "regions": regions,
            "reasons": [r for r in all_reasons if r],
            "disclaimer": (
                "PROTOTYPE: Tamper detection uses image anomaly analysis (ELA + consistency). "
                "Results are indicative signals only. All suspicious documents require "
                "trained human forensic review. This system does not claim to definitively "
                "identify forged documents."
            ),
        }

        logger.info(
            "Tamper analysis complete: score=%.3f, detected=%s, confidence=%.3f",
            tamper_score, tamper_detected, confidence
        )

        return result

    def _compute_confidence(
        self,
        ela_score: float,
        consistency_score: float,
        combined_score: float,
    ) -> float:
        """
        Compute confidence based on agreement between analyzers.
        Higher confidence when analyzers agree strongly.
        """
        # Agreement: both scores point strongly in same direction
        agreement = 1.0 - abs(ela_score - consistency_score)
        # Distance from threshold (higher distance = more confident)
        distance = abs(combined_score - self.TAMPER_DETECTION_THRESHOLD)
        confidence = (agreement * 0.5 + distance * 0.5)
        return min(confidence, 1.0)


tamper_detector = TamperDetector()
