"""Unit tests for src/reporting.py."""
from __future__ import annotations

from pathlib import Path
import sys

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import json  # noqa: E402
from collections import Counter  # noqa: E402 (keep any other stdlib imports you had)

from PIL import Image  # noqa: E402

from config import STATUS_FAIL  # noqa: E402
from decision import DecisionResult  # noqa: E402
from post_processing import Detection  # noqa: E402
import reporting  # noqa: E402


def test_generate_report_creates_png_and_json(tmp_path, monkeypatch):
    src_img = tmp_path / "sample_pcb.png"
    Image.new("RGB", (120, 90), color=(30, 120, 50)).save(src_img)

    annotated_dir = tmp_path / "annotated"
    reports_dir = tmp_path / "reports"
    monkeypatch.setattr(reporting, "ANNOTATED_DIR", annotated_dir)
    monkeypatch.setattr(reporting, "REPORTS_DIR", reports_dir)

    defect = Detection(
        class_name="open_circuit",
        confidence=0.88,
        xyxy=(10.0, 15.0, 50.0, 45.0),
    )
    decision_res = DecisionResult(
        status=STATUS_FAIL,
        detections=[defect],
        review_candidates=[],
        reasons=["open_circuit detected (severity: critical, confidence: 0.88)"],
        inspection_complete=True,
    )

    paths = reporting.generate_report(
        image_path=src_img,
        result=decision_res,
        board_id="board_test",
    )

    assert paths.annotated_image.is_file()
    assert paths.json_report.is_file()

    with Image.open(paths.annotated_image) as out_img:
        assert out_img.size == (120, 90)

    payload = json.loads(paths.json_report.read_text(encoding="utf-8"))
    assert payload["board_id"] == "board_test"
    assert payload["inspection"]["status"] == STATUS_FAIL
    assert payload["inspection"]["total_defects"] == 1
    assert payload["defects"][0]["class_name"] == "open_circuit"