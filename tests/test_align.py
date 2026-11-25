"""Unit tests for src/align.py."""
from __future__ import annotations

from pathlib import Path
import sys

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import cv2
import numpy as np
import pytest

import align as align_mod


def test_align_disabled_returns_original(monkeypatch):
    monkeypatch.setattr(align_mod, "USE_ALIGNMENT", False)
    img = np.zeros((80, 100, 3), dtype=np.uint8)

    res = align_mod.align_to_golden(img, board_id="board_A")
    assert res.aligned is False
    assert res.inliers == 0
    assert res.image.shape == img.shape


def test_align_missing_golden_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(align_mod, "USE_ALIGNMENT", True)
    monkeypatch.setattr(align_mod, "GOLDEN_DIR", tmp_path)
    monkeypatch.setattr(align_mod, "BOARDS", {"board_A": {"golden": "missing.png"}})

    img = np.full((80, 100, 3), 120, dtype=np.uint8)
    res = align_mod.align_to_golden(img, board_id="board_A")

    assert res.aligned is False
    assert res.inliers == 0


def test_align_low_inliers_falls_back(tmp_path, monkeypatch):
    golden_path = tmp_path / "golden_a.png"
    golden = np.zeros((120, 120, 3), dtype=np.uint8)
    cv2.rectangle(golden, (20, 20), (40, 40), (255, 255, 255), -1)
    cv2.imwrite(str(golden_path), golden)

    monkeypatch.setattr(align_mod, "USE_ALIGNMENT", True)
    monkeypatch.setattr(align_mod, "GOLDEN_DIR", tmp_path)
    monkeypatch.setattr(align_mod, "BOARDS", {"board_A": {"golden": "golden_a.png"}})
    monkeypatch.setattr(align_mod, "ALIGN_MIN_INLIERS", 15)

    # Mostly uniform noise has far fewer than 15 reliable feature inliers
    incoming = np.full((120, 120, 3), 10, dtype=np.uint8)
    res = align_mod.align_to_golden(incoming, board_id="board_A")

    assert res.aligned is False
    assert res.inliers < 15


def test_align_rejects_empty_image():
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    with pytest.raises(ValueError):
        align_mod.align_to_golden(empty, board_id="board_A")