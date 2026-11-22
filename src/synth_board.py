"""Synthetic PCB generator with labeled assembly defects.

One fixed board layout (like a real single-board-type product). Every image is
the same board with random lighting/noise, and optional injected defects.
Labels are produced in YOLO format automatically.

Classes: 0 missing_component, 1 misplaced_shifted, 2 wrong_orientation
"""
import random
import cv2
import numpy as np

W, H = 640, 480
CLASSES = ["missing_component", "misplaced_shifted", "wrong_orientation"]

# Fixed layout: (kind, cx, cy, w, h)  kind: R=resistor, C=capacitor(polarized), U=IC
_rng = random.Random(7)
LAYOUT = []
for i in range(8):
    LAYOUT.append(("R", 70 + (i % 4) * 70, 80 + (i // 4) * 50, 34, 16))
for i in range(6):
    LAYOUT.append(("C", 400 + (i % 3) * 65, 80 + (i // 3) * 55, 22, 22))
LAYOUT += [("U", 150, 280, 90, 60), ("U", 330, 290, 70, 50), ("U", 500, 300, 80, 56),
           ("U", 150, 400, 60, 40), ("U", 330, 405, 90, 44)]


def _pads(img, kind, cx, cy, w, h):
    pad = (150, 185, 205)  # tin/gold color (BGR)
    if kind == "R":
        for s in (-1, 1):
            cv2.rectangle(img, (cx + s * (w // 2) - 6, cy - h // 2 - 2),
                          (cx + s * (w // 2) + 6, cy + h // 2 + 2), pad, -1)
    elif kind == "C":
        cv2.circle(img, (cx, cy), w // 2 + 4, pad, 2)
    else:
        n = max(3, w // 14)
        for k in range(n):
            x = cx - w // 2 + 8 + k * (w - 16) // (n - 1)
            for s in (-1, 1):
                cv2.rectangle(img, (x - 3, cy + s * (h // 2 + 3) - 3),
                              (x + 3, cy + s * (h // 2 + 3) + 3), pad, -1)


def _body(img, kind, cx, cy, w, h, flip=False):
    if kind == "R":
        cv2.rectangle(img, (cx - w // 2, cy - h // 2), (cx + w // 2, cy + h // 2), (60, 60, 70), -1)
        cv2.rectangle(img, (cx - w // 2, cy - h // 2), (cx - w // 2 + 6, cy + h // 2), (190, 190, 190), -1)
        cv2.rectangle(img, (cx + w // 2 - 6, cy - h // 2), (cx + w // 2, cy + h // 2), (190, 190, 190), -1)
    elif kind == "C":
        cv2.circle(img, (cx, cy), w // 2, (40, 40, 45), -1)
        # polarity stripe: left side normally, right side when reversed
        x0 = cx + (1 if flip else -1) * (w // 4)
        cv2.rectangle(img, (x0 - 4, cy - w // 2 + 3), (x0 + 4, cy + w // 2 - 3), (230, 230, 230), -1)
    else:
        cv2.rectangle(img, (cx - w // 2, cy - h // 2), (cx + w // 2, cy + h // 2), (25, 25, 25), -1)
        dx = (w // 2 - 8) * (1 if flip else -1)
        dy = (h // 2 - 8) * (1 if flip else -1)
        cv2.circle(img, (cx + dx, cy + dy), 4, (220, 220, 220), -1)  # pin-1 dot


def render(defect_prob=0.5, seed=None):
    """Return (image, labels) where labels=[(cls, xc, yc, w, h)] normalized."""
    rng = random.Random(seed)
    img = np.full((H, W, 3), (70, 110, 30), np.uint8)  # green solder mask
    for x in range(0, W, 40):  # fake traces
        cv2.line(img, (x, 0), (x + rng.randint(-20, 20), H), (60, 140, 50), 1)
    for (kind, cx, cy, w, h) in LAYOUT:
        _pads(img, kind, cx, cy, w, h)

    labels = []
    for (kind, cx, cy, w, h) in LAYOUT:
        pad_ext = 12
        bw, bh = w + pad_ext, h + pad_ext
        if rng.random() < defect_prob / 3:  # per-component defect chance
            d = rng.choice([0, 1, 2]) if kind != "R" else rng.choice([0, 1])
            if d == 0:
                pass  # pads only
            elif d == 1:
                dx, dy = rng.choice([-1, 1]) * rng.randint(10, 20), rng.randint(-10, 10)
                _body(img, kind, cx + dx, cy + dy, w, h)
            else:
                _body(img, kind, cx, cy, w, h, flip=True)
            labels.append((d, cx / W, cy / H, (bw + (25 if d == 1 else 0)) / W,
                           (bh + (15 if d == 1 else 0)) / H))
        else:
            _body(img, kind, cx + rng.randint(-1, 1), cy + rng.randint(-1, 1), w, h)

    # lighting gradient + noise + slight blur (simulates camera/lighting drift)
    gain = rng.uniform(0.75, 1.15)
    grad = np.linspace(rng.uniform(0.85, 1.0), rng.uniform(1.0, 1.15), W)[None, :, None]
    img = np.clip(img.astype(np.float32) * gain * grad, 0, 255)
    img += np.random.default_rng(seed).normal(0, rng.uniform(2, 7), img.shape)
    img = cv2.GaussianBlur(np.clip(img, 0, 255).astype(np.uint8), (3, 3), 0)
    return img, labels
