"""Post-processing for raw detector bounding boxes in CircuitCheck AI."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence

from config import (
    MIN_BOX_AREA,
    NMS_IOU,
    REVIEW_MARGIN,
    conf_threshold,
)

BBox = tuple[float, float, float, float]  # (x1, y1, x2, y2) in pixels


@dataclass(frozen=True)
class Detection:
    """Normalized defect detection in pixel coordinates."""

    class_name: str
    confidence: float
    xyxy: BBox

    @property
    def width(self) -> float:
        return max(0.0, self.xyxy[2] - self.xyxy[0])

    @property
    def height(self) -> float:
        return max(0.0, self.xyxy[3] - self.xyxy[1])

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass(frozen=True)
class PostprocessResult:
    """Confirmed detections plus borderline candidates in the review band."""

    detections: list[Detection]
    review_candidates: list[Detection]


def clamp_box(xyxy: BBox, image_shape: tuple[int, int] | None = None) -> BBox | None:
    """Validate finite coordinates, normalize ordering, and clamp to (height, width)."""
    if len(xyxy) != 4:
        return None
    x1, y1, x2, y2 = xyxy
    if not all(math.isfinite(float(v)) for v in (x1, y1, x2, y2)):
        return None

    fx1, fy1, fx2, fy2 = float(x1), float(y1), float(x2), float(y2)
    if fx1 > fx2:
        fx1, fx2 = fx2, fx1
    if fy1 > fy2:
        fy1, fy2 = fy2, fy1

    if image_shape is not None:
        height, width = image_shape
        if width <= 0 or height <= 0:
            return None
        w_bound = float(width)
        h_bound = float(height)
        fx1 = max(0.0, min(w_bound, fx1))
        fy1 = max(0.0, min(h_bound, fy1))
        fx2 = max(0.0, min(w_bound, fx2))
        fy2 = max(0.0, min(h_bound, fy2))

    if fx2 <= fx1 or fy2 <= fy1:
        return None
    return (fx1, fy1, fx2, fy2)


def compute_iou(box_a: BBox, box_b: BBox) -> float:
    """Compute Intersection-over-Union between two (x1, y1, x2, y2) boxes."""
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b

    inter_w = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    inter_h = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter_area = inter_w * inter_h
    if inter_area <= 0.0:
        return 0.0

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter_area
    if union <= 0.0:
        return 0.0
    return inter_area / union


def nms_per_class(
    detections: Sequence[Detection],
    iou_threshold: float = NMS_IOU,
) -> list[Detection]:
    """Run greedy Non-Maximum Suppression independently per defect class."""
    if not detections:
        return []

    by_class: dict[str, list[Detection]] = {}
    for det in detections:
        by_class.setdefault(det.class_name, []).append(det)

    kept: list[Detection] = []
    for class_dets in by_class.values():
        ordered = sorted(class_dets, key=lambda d: d.confidence, reverse=True)
        selected: list[Detection] = []
        for candidate in ordered:
            if any(compute_iou(candidate.xyxy, chosen.xyxy) >= iou_threshold for chosen in selected):
                continue
            selected.append(candidate)
        kept.extend(selected)

    kept.sort(key=lambda d: d.confidence, reverse=True)
    return kept


def postprocess_detections(
    raw_detections: Iterable[object],
    *,
    image_shape: tuple[int, int] | None = None,
    min_box_area: float = MIN_BOX_AREA,
    nms_iou: float = NMS_IOU,
    review_margin: float = REVIEW_MARGIN,
) -> PostprocessResult:
    """Filter, threshold, and NMS raw detections into confirmed and review lists."""
    confirmed: list[Detection] = []
    review_candidates: list[Detection] = []

    for raw in raw_detections:
        class_name = getattr(raw, "class_name", None)
        conf_val = getattr(raw, "confidence", None)
        xyxy_val = getattr(raw, "xyxy", None)

        if not isinstance(class_name, str) or not class_name or conf_val is None or xyxy_val is None:
            continue

        conf = float(conf_val)
        if not math.isfinite(conf):
            continue

        clamped = clamp_box(xyxy_val, image_shape=image_shape)  # type: ignore[arg-type]
        if clamped is None:
            continue

        area = (clamped[2] - clamped[0]) * (clamped[3] - clamped[1])
        if area < min_box_area:
            continue

        det = Detection(class_name=class_name, confidence=conf, xyxy=clamped)
        threshold = conf_threshold(det.class_name)
        review_floor = max(0.0, threshold - max(0.0, review_margin))

        if det.confidence >= threshold:
            confirmed.append(det)
        elif det.confidence >= review_floor:
            review_candidates.append(det)

    return PostprocessResult(
        detections=nms_per_class(confirmed, iou_threshold=nms_iou),
        review_candidates=nms_per_class(review_candidates, iou_threshold=nms_iou),
    )