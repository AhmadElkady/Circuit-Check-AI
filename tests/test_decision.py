"""Unit tests for src/decision.py."""
from __future__ import annotations

import pytest
from pathlib import Path
import sys

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from config import STATUS_FAIL, STATUS_PASS, STATUS_REVIEW
from decision import decide
from post_processing import Detection, PostprocessResult


def test_decide_pass_when_no_detections_or_review():
    pp = PostprocessResult(detections=[], review_candidates=[])
    res = decide(pp, inspection_complete=True)

    assert res.status == STATUS_PASS
    assert res.total_defects == 0
    assert res.total_review_candidates == 0
    assert res.inspection_complete is True


def test_decide_review_when_review_candidates_present():
    cand = Detection(
        class_name="mouse_bite",
        confidence=0.35,
        xyxy=(10.0, 10.0, 30.0, 30.0),
    )
    pp = PostprocessResult(detections=[], review_candidates=[cand])
    res = decide(pp, inspection_complete=True)

    assert res.status == STATUS_REVIEW
    assert res.total_defects == 0
    assert res.total_review_candidates == 1


def test_decide_review_when_incomplete_without_confirmed_defects():
    pp = PostprocessResult(detections=[], review_candidates=[])
    res = decide(pp, inspection_complete=False)

    assert res.status == STATUS_REVIEW
    assert res.inspection_complete is False


def test_decide_fail_on_confirmed_defect():
    defect = Detection(
        class_name="short",
        confidence=0.92,
        xyxy=(20.0, 20.0, 60.0, 60.0),
    )
    pp = PostprocessResult(detections=[defect], review_candidates=[])
    res = decide(pp, inspection_complete=True)

    assert res.status == STATUS_FAIL
    assert res.total_defects == 1
    assert any("short" in reason for reason in res.reasons)


def test_decide_raises_on_unknown_class():
    bad = Detection(
        class_name="not_a_real_defect",
        confidence=0.80,
        xyxy=(1.0, 1.0, 10.0, 10.0),
    )
    pp = PostprocessResult(detections=[bad], review_candidates=[])

    with pytest.raises(ValueError, match="Unknown defect class"):
        decide(pp)