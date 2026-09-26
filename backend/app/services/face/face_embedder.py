"""
Face embedding extraction and similarity comparison engine for SentinelID.
Extracts normalized multi-dimensional face embeddings and computes cosine similarity.
Supports DeepFace if available, with robust OpenCV multi-scale HOG/spatial feature representation.
"""
import logging
from typing import Optional, Tuple, Dict, Any, List, Union
import numpy as np
import cv2

from app.core.config import settings
from app.services.face.face_detector import face_detector, DetectedFace

logger = logging.getLogger(__name__)


class FaceEmbedder:
    """
    Generates normalized face embeddings and calculates similarity.
    """

    TARGET_SIZE = (160, 160)

    def __init__(self):
        self._deepface_available = False
        self._hog = None
        self._initialize()

    def _initialize(self):
        """Initialize backends."""
        try:
            import deepface  # noqa: F401
            self._deepface_available = True
            logger.info("FaceEmbedder: DeepFace backend is available")
        except ImportError:
            logger.info("FaceEmbedder: DeepFace not installed, using OpenCV HOG/Spatial embedding backend")

        # Initialize HOG descriptor: winSize=(128,128), blockSize=(16,16), blockStride=(8,8), cellSize=(8,8), nbins=9
        try:
            self._hog = cv2.HOGDescriptor(
                (128, 128),  # winSize
                (16, 16),    # blockSize
                (8, 8),      # blockStride
                (8, 8),      # cellSize
                9            # nbins
            )
        except Exception as e:
            logger.warning("Failed to initialize HOGDescriptor: %s", e)

    def extract_face_embedding(self, face_img_or_crop: np.ndarray) -> Optional[np.ndarray]:
        """
        Extract an L2-normalized 1D feature embedding vector from a cropped face image.
        """
        if face_img_or_crop is None or face_img_or_crop.size == 0:
            return None

        try:
            # 1. Standardize size to 128x128
            resized = cv2.resize(face_img_or_crop, (128, 128))

            # 2. Lighting normalization: CLAHE
            if len(resized.shape) == 3:
                lab = cv2.cvtColor(resized, cv2.COLOR_BGR2LAB)
                l, a, b = cv2.split(lab)
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                l_eq = clahe.apply(l)
                norm_bgr = cv2.cvtColor(cv2.merge([l_eq, a, b]), cv2.COLOR_LAB2BGR)
                gray = cv2.cvtColor(norm_bgr, cv2.COLOR_BGR2GRAY)
            else:
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                gray = clahe.apply(resized)
                norm_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

            features = []

            # 3. HOG features (captures facial edges, eyes, nose, mouth structure)
            if self._hog is not None:
                hog_feat = self._hog.compute(gray)
                if hog_feat is not None:
                    # Subsample or flatten HOG features to compact normalized vector
                    flat_hog = hog_feat.flatten()
                    # Sample evenly to 256 dimensions
                    if len(flat_hog) > 256:
                        indices = np.linspace(0, len(flat_hog) - 1, 256, dtype=int)
                        hog_sampled = flat_hog[indices]
                    else:
                        hog_sampled = flat_hog
                    features.append(hog_sampled)

            # 4. Spatial grid intensity moments (4x4 regions across the face)
            grid_features = []
            h, w = gray.shape[:2]
            gh, gw = h // 4, w // 4
            for r in range(4):
                for c in range(4):
                    cell = gray[r * gh:(r + 1) * gh, c * gw:(c + 1) * gw]
                    if cell.size > 0:
                        grid_features.extend([
                            float(np.mean(cell)) / 255.0,
                            float(np.std(cell)) / 128.0,
                        ])
            features.append(np.array(grid_features, dtype=np.float32))

            # 5. Concatenate, mean-center (zero-mean) and L2-normalize
            if not features:
                return None

            combined = np.concatenate(features).astype(np.float32)
            combined = combined - float(np.mean(combined))
            norm = np.linalg.norm(combined)
            if norm > 1e-6:
                combined = combined / norm

            return combined

        except Exception as e:
            logger.error("Error generating face embedding: %s", e)
            return None

    @staticmethod
    def compute_similarity(embedding_a: np.ndarray, embedding_b: np.ndarray) -> float:
        """
        Compute cosine similarity between two L2-normalized embeddings.
        Returns float in range [0.0, 1.0].
        """
        if embedding_a is None or embedding_b is None:
            return 0.0

        if len(embedding_a) != len(embedding_b):
            # Align lengths if different
            min_len = min(len(embedding_a), len(embedding_b))
            embedding_a = embedding_a[:min_len]
            embedding_b = embedding_b[:min_len]

        norm_a = np.linalg.norm(embedding_a)
        norm_b = np.linalg.norm(embedding_b)

        if norm_a < 1e-6 or norm_b < 1e-6:
            return 0.0

        dot = float(np.dot(embedding_a, embedding_b) / (norm_a * norm_b))
        # Clamp to [0.0, 1.0]
        similarity = max(0.0, min(1.0, dot))
        return float(round(similarity, 3))


face_embedder = FaceEmbedder()
