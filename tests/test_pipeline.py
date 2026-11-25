"""Integration test for pipeline wiring using a fake YOLO model."""
from __future__ import annotations

from pathlib import Path
import sys

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from types import SimpleNamespace

import cv2
import numpy as np

from decision import decide
from post_processing import postprocess_detections
import reporting


def test_pipeline_end_to_end_with_fake_yolo(tmp_path, monkeypatch):
    img_path = tmp_path / "pcb_sample.png"
    img = np.full((200, 200, 3), 50, dtype=np.uint8)
    cv2.imwrite(str(img_path), img)

    monkeypatch.setattr(reporting, "ANNOTATED_DIR", tmp_path / "annotated")
    monkeypatch.setattr(reporting, "REPORTS_DIR", tmp_path / "reports")

    # Fake Ultralytics YOLO output mimicking a single confirmed defect
    fake_box = SimpleNamespace(
        cls=np.array([5.0]),      # spurious_copper in default PCB classes
        conf=np.array([0.85]),
        xyxy=np.array([[20.0, 20.0, 60.0, 60.0]]),
    )
    fake_result = SimpleNamespace(
        boxes=[fake_box],
        names={5: "spurious_copper"},
    )

    raw_items = [
        SimpleNamespace(
            class_name=fake_result.names[int(b.cls[0])],
            confidence=float(b.conf[0]),
            xyxy=tuple(float(x) for x in b.xyxy[0]),
        )
        for b in fake_result.boxes
    ]

    processed = postprocess_detections(raw_items, image_shape=img.shape[:2])
    decision_res = decide(processed)
    report_paths = reporting.generate_report(
        image_path=img_path,
        result=decision_res,
        board_id="board_A",
    )

    assert decision_res.total_defects == 1
    assert report_paths.annotated_image.is_file()
    assert report_paths.json_report.is_file()