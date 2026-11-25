"""Unit tests for src/postprocessing.py."""
from __future__ import annotations

import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from detection import RawDetection  # noqa: E402
from post_processing import (  # noqa: E402
    Detection,
    clamp_box,
    compute_iou,
    nms_per_class,
    postprocess_detections,
)


def test_clamp_box_bounds_and_invalid_inputs():
    assert clamp_box((-10.0, -5.0, 50.0, 40.0), image_shape=(100, 200)) == (0.0, 0.0, 50.0, 40.0)
    assert clamp_box((180.0, 90.0, 250.0, 120.0), image_shape=(100, 200)) == (180.0, 90.0, 200.0, 100.0)
    assert clamp_box((50.0, 50.0, 50.0, 80.0), image_shape=(100, 200)) is None
    assert clamp_box((math.nan, 0.0, 20.0, 20.0), image_shape=(100, 200)) is None


def test_compute_iou_overlap_and_disjoint():
    assert math.isclose(compute_iou((0.0, 0.0, 10.0, 10.0), (0.0, 0.0, 10.0, 10.0)), 1.0)
    assert math.isclose(compute_iou((0.0, 0.0, 10.0, 10.0), (20.0, 20.0, 30.0, 30.0)), 0.0)
    # Overlap is 5x5=25; union is 100 + 100 - 25 = 175
    assert math.isclose(compute_iou((0.0, 0.0, 10.0, 10.0), (5.0, 5.0, 15.0, 15.0)), 25.0 / 175.0)


def test_nms_suppresses_same_class_but_keeps_different_class():
    d1 = Detection(class_name="short", confidence=0.90, xyxy=(10.0, 10.0, 50.0, 50.0))
    d2 = Detection(class_name="short", confidence=0.70, xyxy=(12.0, 12.0, 52.0, 52.0))
    d3 = Detection(class_name="spur", confidence=0.85, xyxy=(10.0, 10.0, 50.0, 50.0))

    kept = nms_per_class([d2, d1, d3], iou_threshold=0.5)
    assert len(kept) == 2
    assert kept[0] == d1
    assert kept[1] == d3


def test_postprocess_thresholds_review_band_and_min_area():
    # In config:
    # - short threshold = 0.30, review band = [0.20, 0.30)
    # - mouse_bite threshold = 0.40, review band = [0.30, 0.40)
    raw_items = [
        RawDetection(class_name="short", confidence=0.75, xyxy=(10.0, 10.0, 40.0, 40.0)),      # confirmed
        RawDetection(class_name="short", confidence=0.25, xyxy=(100.0, 100.0, 130.0, 130.0)), # review
        RawDetection(class_name="mouse_bite", confidence=0.35, xyxy=(150.0, 150.0, 180.0, 180.0)), # review
        RawDetection(class_name="short", confidence=0.10, xyxy=(200.0, 200.0, 230.0, 230.0)), # dropped (<0.20)
        RawDetection(class_name="short", confidence=0.95, xyxy=(250.0, 250.0, 252.0, 252.0)), # dropped (area=4 < 16)
    ]

    res = postprocess_detections(raw_items, image_shape=(640, 640))
    assert len(res.detections) == 1
    assert res.detections[0].class_name == "short"
    assert res.detections[0].confidence == 0.75

    assert len(res.review_candidates) == 2
    review_classes = {d.class_name for d in res.review_candidates}
    assert review_classes == {"short", "mouse_bite"}