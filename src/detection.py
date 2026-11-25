"""YOLO model wrapper and raw/tiled object detection for CircuitCheck AI."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from ultralytics import YOLO

from config import (
    CLASSES,
    CONF_DEFAULT,
    CONF_THRESHOLDS,
    DEVICE,
    IMGSZ,
    REVIEW_MARGIN,
    TILE_OVERLAP,
    TILE_SIZE,
    USE_TILING,
    WEIGHTS,
    conf_threshold,
)

BBox = tuple[float, float, float, float]  # (x1, y1, x2, y2) in full-image pixels

_MODEL_CACHE: dict[tuple[str, str], YOLO] = {}


@dataclass(frozen=True)
class RawDetection:
    """Raw box emitted by the detector prior to post-processing."""

    class_name: str
    confidence: float
    xyxy: BBox
    class_id: int | None = None


def load_image(image: str | Path | np.ndarray) -> np.ndarray:
    """Load an image path into a BGR numpy array, or validate an existing array."""
    if isinstance(image, np.ndarray):
        if image.ndim < 2 or image.size == 0:
            raise ValueError("Input image array is empty or invalid.")
        return image

    path = Path(image)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {path}")

    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Failed to decode image from path: {path}")
    return img


def get_model(weights_path: str | Path = WEIGHTS, device: str | int = DEVICE) -> YOLO:
    """Load and cache a YOLO model instance by weights path and device."""
    weights_str = str(Path(weights_path).resolve())
    device_str = str(device)
    cache_key = (weights_str, device_str)

    if cache_key not in _MODEL_CACHE:
        weights_file = Path(weights_path)
        if not weights_file.exists():
            raise FileNotFoundError(
                f"Model weights not found at {weights_file}. Run training first."
            )
        model = YOLO(str(weights_file))
        model.to(device)
        _MODEL_CACHE[cache_key] = model

    return _MODEL_CACHE[cache_key]


def clear_model_cache() -> None:
    """Clear cached YOLO models (useful in tests or when reloading weights)."""
    _MODEL_CACHE.clear()


def _lowest_candidate_conf() -> float:
    """Lowest confidence worth keeping before postprocessing review-margin filtering."""
    configured = [conf_threshold(cls) for cls in CLASSES] + [CONF_DEFAULT] + list(CONF_THRESHOLDS.values())
    min_thresh = min(configured) if configured else CONF_DEFAULT
    return max(0.05, min_thresh - max(0.0, REVIEW_MARGIN))


def _resolve_class_name(cls_idx: int, model_names: Any) -> str:
    """Map numeric class index to class name using CLASSES with model.names fallback."""
    if 0 <= cls_idx < len(CLASSES):
        return CLASSES[cls_idx]
    if isinstance(model_names, dict) and cls_idx in model_names:
        return str(model_names[cls_idx])
    if isinstance(model_names, (list, tuple)) and 0 <= cls_idx < len(model_names):
        return str(model_names[cls_idx])
    raise IndexError(f"Predicted class index {cls_idx} out of range for CLASSES ({len(CLASSES)}).")


def _predict_single_frame(
    model: YOLO,
    frame: np.ndarray,
    *,
    conf: float,
    imgsz: int,
    device: str | int,
    offset_xy: tuple[float, float] = (0.0, 0.0),
) -> list[RawDetection]:
    """Run YOLO on a single image/tile and offset coordinates into full-image space."""
    dx, dy = offset_xy
    results = model.predict(
        source=frame,
        conf=conf,
        imgsz=imgsz,
        device=device,
        verbose=False,
    )

    detections: list[RawDetection] = []
    if not results:
        return detections

    result = results[0]
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return detections

    xyxy_arr = boxes.xyxy.cpu().numpy()
    conf_arr = boxes.conf.cpu().numpy()
    cls_arr = boxes.cls.cpu().numpy().astype(int)
    model_names = getattr(result, "names", getattr(model, "names", None))

    for box, score, cls_idx in zip(xyxy_arr, conf_arr, cls_arr):
        cls_name = _resolve_class_name(int(cls_idx), model_names)
        x1, y1, x2, y2 = (
            float(box[0]) + dx,
            float(box[1]) + dy,
            float(box[2]) + dx,
            float(box[3]) + dy,
        )
        detections.append(
            RawDetection(
                class_name=cls_name,
                confidence=float(score),
                xyxy=(x1, y1, x2, y2),
                class_id=int(cls_idx),
            )
        )

    return detections


def _generate_tiles(
    height: int,
    width: int,
    tile_size: int = TILE_SIZE,
    overlap: float = TILE_OVERLAP,
) -> list[tuple[int, int, int, int]]:
    """Generate (x1, y1, x2, y2) tile windows covering a (height, width) image."""
    if tile_size <= 0:
        raise ValueError("TILE_SIZE must be positive.")
    if not 0.0 <= overlap < 1.0:
        raise ValueError("TILE_OVERLAP must be in [0.0, 1.0).")

    stride = max(1, int(round(tile_size * (1.0 - overlap))))

    def _axis_starts(dim: int) -> list[int]:
        if dim <= tile_size:
            return [0]
        starts = list(range(0, max(1, dim - tile_size + 1), stride))
        last_start = max(0, dim - tile_size)
        if starts[-1] != last_start:
            starts.append(last_start)
        return starts

    xs = _axis_starts(width)
    ys = _axis_starts(height)

    tiles: list[tuple[int, int, int, int]] = []
    for y1 in ys:
        for x1 in xs:
            x2 = min(width, x1 + tile_size)
            y2 = min(height, y1 + tile_size)
            tiles.append((x1, y1, x2, y2))
    return tiles


def detect_pcb(
    image: str | Path | np.ndarray,
    *,
    weights_path: str | Path = WEIGHTS,
    device: str | int = DEVICE,
    imgsz: int = IMGSZ,
    use_tiling: bool = USE_TILING,
    tile_size: int = TILE_SIZE,
    tile_overlap: float = TILE_OVERLAP,
    raw_conf_floor: float | None = None,
) -> tuple[list[RawDetection], tuple[int, int]]:
    """Run raw YOLO detection on a PCB image (full-frame or tiled).

    Returns:
        (raw_detections, (height, width))
    """
    img = load_image(image)
    height, width = img.shape[:2]
    model = get_model(weights_path=weights_path, device=device)
    conf_floor = _lowest_candidate_conf() if raw_conf_floor is None else raw_conf_floor

    if not use_tiling or (width <= tile_size and height <= tile_size):
        raw = _predict_single_frame(
            model,
            img,
            conf=conf_floor,
            imgsz=imgsz,
            device=device,
            offset_xy=(0.0, 0.0),
        )
        return raw, (height, width)

    raw_all: list[RawDetection] = []
    for x1, y1, x2, y2 in _generate_tiles(height, width, tile_size=tile_size, overlap=tile_overlap):
        tile = img[y1:y2, x1:x2]
        if tile.size == 0:
            continue
        tile_dets = _predict_single_frame(
            model,
            tile,
            conf=conf_floor,
            imgsz=imgsz,
            device=device,
            offset_xy=(float(x1), float(y1)),
        )
        raw_all.extend(tile_dets)

    return raw_all, (height, width)