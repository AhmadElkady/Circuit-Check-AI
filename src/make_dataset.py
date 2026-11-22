"""Generate a YOLO-format synthetic dataset: python src/make_dataset.py --n 600"""
import argparse, os, cv2
from pathlib import Path
from synth_board import render, CLASSES

p = argparse.ArgumentParser()
p.add_argument("--n", type=int, default=600)
p.add_argument("--out", default="datasets/synthetic")
a = p.parse_args()
out = Path(a.out)
for split in ("train", "val", "test"):
    (out / "images" / split).mkdir(parents=True, exist_ok=True)
    (out / "labels" / split).mkdir(parents=True, exist_ok=True)

for i in range(a.n):
    split = "train" if i < 0.7 * a.n else "val" if i < 0.85 * a.n else "test"
    img, labels = render(defect_prob=0.6, seed=i)
    cv2.imwrite(str(out / "images" / split / f"{i:05d}.jpg"), img)
    with open(out / "labels" / split / f"{i:05d}.txt", "w") as f:
        for c, x, y, w, h in labels:
            f.write(f"{c} {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n")

(out / "data.yaml").write_text(
    f"path: {out.resolve()}\ntrain: images/train\nval: images/val\ntest: images/test\n"
    f"names:\n" + "".join(f"  {k}: {n}\n" for k, n in enumerate(CLASSES)))
print("dataset ready:", out.resolve())
