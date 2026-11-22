import sys; sys.path.insert(0, "src")
from synth_board import render, CLASSES
def test_render_labels_valid():
    img, labels = render(defect_prob=1.0, seed=1)
    assert img.shape == (480, 640, 3) and labels
    for c, x, y, w, h in labels:
        assert 0 <= c < len(CLASSES) and 0 < x < 1 and 0 < y < 1 and w > 0 and h > 0
def test_good_board_has_no_labels():
    assert render(defect_prob=0.0, seed=2)[1] == []
