"""
Motion analysis component for SentinelID liveness verification.
Measures temporal changes, inter-frame variation, face translation,
and detects static image spoofing attempts.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
import numpy as np
import cv2

logger = logging.getLogger(__name__)


@dataclass
class MotionMetrics:
    """Motion analysis summary."""
    mean_frame_difference: float      # Mean pixel absolute difference across frames
    face_displacement_variance: float # Variance of face center movement across frames
    is_static_image: bool              # True if frames show no natural movement
    is_excessive_movement: bool        # True if movement is unnaturally turbulent
    natural_movement_score: float      # 0.0 - 1.0 (1.0 = ideal natural human movement)
    inter_frame_variances: List[float] = field(default_factory=list)


class MotionAnalyzer:
    """
    Temporal motion analyzer across consecutive camera frames.
    """

    # Thresholds for static image detection
    STATIC_PIXEL_DIFF_THRESHOLD = 0.85     # Mean pixel diff below this indicates static photo
    STATIC_FACE_VAR_THRESHOLD = 0.15       # Face center variance below this indicates frozen image
    EXCESSIVE_PIXEL_DIFF_THRESHOLD = 85.0  # Camera violently shaken or dropped

    def analyze_motion(
        self,
        frames: List[np.ndarray],
        face_centers: List[Optional[Tuple[int, int]]],
    ) -> MotionMetrics:
        """
        Analyze temporal motion across a sequence of frames.
        """
        if len(frames) < 2:
            return MotionMetrics(
                mean_frame_difference=0.0,
                face_displacement_variance=0.0,
                is_static_image=True,
                is_excessive_movement=False,
                natural_movement_score=0.0,
                inter_frame_variances=[],
            )

        # 1. Compute inter-frame pixel differences
        frame_diffs = []
        for i in range(len(frames) - 1):
            f1 = frames[i]
            f2 = frames[i + 1]

            g1 = cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY) if len(f1.shape) == 3 else f1
            g2 = cv2.cvtColor(f2, cv2.COLOR_BGR2GRAY) if len(f2.shape) == 3 else f2

            # Resize to standard size for consistent metric calculation
            if g1.shape != (240, 320):
                g1 = cv2.resize(g1, (320, 240))
                g2 = cv2.resize(g2, (320, 240))

            diff = cv2.absdiff(g1, g2)
            mean_diff = float(np.mean(diff))
            frame_diffs.append(mean_diff)

        mean_frame_diff = float(np.mean(frame_diffs)) if frame_diffs else 0.0

        # 2. Track face center displacements
        valid_centers = [c for c in face_centers if c is not None]
        if len(valid_centers) >= 2:
            xs = [c[0] for c in valid_centers]
            ys = [c[1] for c in valid_centers]
            var_x = float(np.var(xs))
            var_y = float(np.var(ys))
            face_var = (var_x + var_y) / 2.0
        else:
            face_var = 0.0

        # 3. Check for static behavior
        # A static photo held in front of a camera will have almost identical consecutive frames
        is_static = (
            mean_frame_diff < self.STATIC_PIXEL_DIFF_THRESHOLD
            and face_var < self.STATIC_FACE_VAR_THRESHOLD
        )

        is_excessive = mean_frame_diff > self.EXCESSIVE_PIXEL_DIFF_THRESHOLD

        # 4. Compute natural movement score (0-1)
        # Optimal human micro-movement: mean_diff between 2.0 and 25.0, face_var between 0.5 and 50.0
        if is_static:
            natural_score = 0.05
        elif is_excessive:
            natural_score = 0.20
        else:
            # Score peaks around mean_diff in [3.0, 15.0]
            if mean_frame_diff < 1.5:
                diff_score = mean_frame_diff / 1.5
            elif mean_frame_diff <= 20.0:
                diff_score = 1.0
            else:
                diff_score = max(0.2, 1.0 - (mean_frame_diff - 20.0) / 40.0)

            # Face displacement score: natural slight head sway / micro-repositioning
            if face_var < 0.3:
                var_score = max(0.2, face_var / 0.3)
            elif face_var <= 40.0:
                var_score = 1.0
            else:
                var_score = max(0.3, 1.0 - (face_var - 40.0) / 100.0)

            natural_score = float(round(0.55 * diff_score + 0.45 * var_score, 3))
            natural_score = max(0.1, min(1.0, natural_score))

        return MotionMetrics(
            mean_frame_difference=round(mean_frame_diff, 2),
            face_displacement_variance=round(face_var, 2),
            is_static_image=is_static,
            is_excessive_movement=is_excessive,
            natural_movement_score=natural_score,
            inter_frame_variances=[round(v, 2) for v in frame_diffs],
        )


motion_analyzer = MotionAnalyzer()
