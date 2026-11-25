"""High-level inference entry point for CircuitCheck AI."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from config import DEVICE, IMGSZ, USE_TILING, WEIGHTS
from detection import RawDetection, detect_pcb


@dataclass(frozen=True)
class InferenceOutput:
    """Raw detections and image dimensions produced during inference."""

    raw_detections: list[RawDetection]
    image_shape: tuple[int, int]  # (height, width)
    weights_path: Path


def run_inference(
    image: str | Path | np.ndarray,
    *,
    weights_path: str | Path = WEIGHTS,
    device: str | int = DEVICE,
    imgsz: int = IMGSZ,
    use_tiling: bool = USE_TILING,
) -> InferenceOutput:
    """Run model inference on a PCB image path or numpy array."""
    resolved_weights = Path(weights_path)
    raw_dets, shape = detect_pcb(
        image,
        weights_path=resolved_weights,
        device=device,
        imgsz=imgsz,
        use_tiling=use_tiling,
    )
    return InferenceOutput(
        raw_detections=raw_dets,
        image_shape=shape,
        weights_path=resolved_weights,
    )