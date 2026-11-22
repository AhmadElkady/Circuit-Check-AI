"""Inspect boards: python src/infer.py --weights runs/circuitcheck/weights/best.pt --source path/to/img_or_folder"""
import argparse, json, cv2
from pathlib import Path
from ultralytics import YOLO

CRITICAL = {"missing_component", "wrong_orientation", "misplaced_shifted"}

def inspect(model, img, conf=0.4):
    r = model.predict(img, conf=conf, verbose=False)[0]
    defects = []
    for b in r.boxes:
        defects.append({"defect": model.names[int(b.cls)], "confidence": round(float(b.conf), 3),
                        "box_xyxy": [round(v, 1) for v in b.xyxy[0].tolist()]})
    status = "FAIL" if any(d["defect"] in CRITICAL for d in defects) else "PASS"
    return status, defects, r.plot()

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--weights", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--conf", type=float, default=0.4)
    p.add_argument("--out", default="outputs")
    a = p.parse_args()
    model = YOLO(a.weights)
    Path(a.out).mkdir(exist_ok=True)
    src = Path(a.source)
    files = sorted(src.glob("*.jp*g")) + sorted(src.glob("*.png")) if src.is_dir() else [src]
    report = {}
    for f in files:
        status, defects, vis = inspect(model, str(f), a.conf)
        cv2.imwrite(str(Path(a.out) / f.name), vis)
        report[f.name] = {"status": status, "defects": defects}
        print(f"{f.name}: {status} ({len(defects)} defects)")
    Path(a.out, "report.json").write_text(json.dumps(report, indent=2))
