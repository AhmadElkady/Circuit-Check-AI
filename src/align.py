"""Golden-board alignment for CircuitCheck AI."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from config import (
    ALIGN_MIN_INLIERS,
    BOARDS,
    GOLDEN_DIR,
    USE_ALIGNMENT,
)


@dataclass(frozen=True)
class AlignmentResult:
    """Result of aligning a board image to its golden reference."""

    image: np.ndarray
    aligned: bool
    inliers: int
    reason: str


def _resolve_golden_path(board_id: str | None) -> Path | None:
    """Resolve the golden image path for a given board_id from BOARDS / GOLDEN_DIR."""
    if not board_id or board_id not in BOARDS:
        return None

    board_cfg = BOARDS[board_id]
    golden_file: Any = None

    if isinstance(board_cfg, dict):
        golden_file = board_cfg.get("golden") or board_cfg.get("golden_image")
    else:
        golden_file = getattr(board_cfg, "golden", None) or getattr(board_cfg, "golden_image", None)

    if not golden_file:
        return None

    candidate = Path(golden_file)
    if candidate.is_absolute():
        return candidate
    if candidate.exists():
        return candidate
    return Path(GOLDEN_DIR) / candidate


def align_to_golden(
    image: np.ndarray,
    board_id: str | None = None,
    *,
    enabled: bool = USE_ALIGNMENT,
    min_inliers: int = ALIGN_MIN_INLIERS,
    max_features: int = 1500,
    ransac_reproj_threshold: float = 5.0,
) -> AlignmentResult:
    """Align an incoming PCB image to its golden reference using ORB + RANSAC homography.

    Falls back cleanly to the unaligned image if alignment is disabled,
    the golden reference is unavailable, or RANSAC inliers are below min_inliers.
    """
    if image is None or not isinstance(image, np.ndarray) or image.size == 0:
        raise ValueError("Input image must be a non-empty NumPy array.")

    if not enabled:
        return AlignmentResult(
            image=image,
            aligned=False,
            inliers=0,
            reason="Alignment disabled (USE_ALIGNMENT=False).",
        )

    golden_path = _resolve_golden_path(board_id)
    if golden_path is None or not golden_path.is_file():
        return AlignmentResult(
            image=image,
            aligned=False,
            inliers=0,
            reason=f"Golden image not found for board_id={board_id!r}.",
        )

    golden_img = cv2.imread(str(golden_path), cv2.IMREAD_COLOR)
    if golden_img is None or golden_img.size == 0:
        return AlignmentResult(
            image=image,
            aligned=False,
            inliers=0,
            reason=f"Failed to read golden image at {golden_path}.",
        )

    src_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    dst_gray = cv2.cvtColor(golden_img, cv2.COLOR_BGR2GRAY)

    orb = cv2.ORB_create(nfeatures=max_features)
    kp_src, desc_src = orb.detectAndCompute(src_gray, None)
    kp_dst, desc_dst = orb.detectAndCompute(dst_gray, None)

    if desc_src is None or desc_dst is None or len(kp_src) < 4 or len(kp_dst) < 4:
        return AlignmentResult(
            image=image,
            aligned=False,
            inliers=0,
            reason="Insufficient ORB keypoints/descriptors for homography.",
        )

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = matcher.match(desc_src, desc_dst)
    if len(matches) < 4:
        return AlignmentResult(
            image=image,
            aligned=False,
            inliers=0,
            reason=f"Too few feature matches ({len(matches)} < 4).",
        )

    matches = sorted(matches, key=lambda m: m.distance)
    src_pts = np.float32([kp_src[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp_dst[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)

    homography, mask = cv2.findHomography(
        src_pts,
        dst_pts,
        cv2.RANSAC,
        ransac_reproj_threshold,
    )
    if homography is None or mask is None:
        return AlignmentResult(
            image=image,
            aligned=False,
            inliers=0,
            reason="Homography estimation failed.",
        )

    inliers = int(np.count_nonzero(mask.ravel()))
    if inliers < min_inliers:
        return AlignmentResult(
            image=image,
            aligned=False,
            inliers=inliers,
            reason=f"Inliers ({inliers}) below ALIGN_MIN_INLIERS ({min_inliers}).",
        )

    out_h, out_w = golden_img.shape[:2]
    warped = cv2.warpPerspective(image, homography, (out_w, out_h))

    return AlignmentResult(
        image=warped,
        aligned=True,
        inliers=inliers,
        reason=f"Aligned to {golden_path.name} with {inliers} RANSAC inliers.",
    )