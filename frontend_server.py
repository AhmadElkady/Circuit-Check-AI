"""Serve the frontend and save each completed PCB inspection as one record."""

from io import BytesIO
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from threading import Lock
from uuid import uuid4

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps
# Keep Pillow's decoder before Ultralytics adds optional format handling.
from PIL.Image import open as open_pcb_image

ROOT = Path(__file__).resolve().parent
# The existing scripts use flat imports from src.
sys.path.insert(0, str(ROOT / "src"))

from config import ANNOTATED_DIR, MAX_UPLOAD_MB, REPORTS_DIR, WEIGHTS
from decision import decide
from infer import run_inference
from post_processing import postprocess_detections
from reporting import generate_report

INSPECTIONS_DIR = ROOT / "outputs" / "inspections"
INSPECTION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")
app = FastAPI()
inference_lock = Lock()


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _local_file(directory: Path, name: str) -> Path | None:
    path = directory / name
    if path.is_symlink() or not path.is_file():
        return None
    return path


def _read_record(inspection_id: str):
    if not INSPECTION_ID.fullmatch(inspection_id):
        return None

    run_dir = INSPECTIONS_DIR / inspection_id
    original = None
    if run_dir.is_dir() and not run_dir.is_symlink():
        report_path = _local_file(run_dir, "report.json")
        annotated = _local_file(run_dir, "annotated.png")
        original = _local_file(run_dir, "original.png")
        url_base = f"/outputs/inspections/{inspection_id}"
        report_url = f"{url_base}/report.json"
        annotated_url = f"{url_base}/annotated.png"
        original_url = f"{url_base}/original.png" if original else None
    else:
        report_name = f"{inspection_id}.json"
        image_name = f"{inspection_id}.png"
        report_path = _local_file(REPORTS_DIR, report_name)
        annotated = _local_file(ANNOTATED_DIR, image_name)
        report_url = f"/outputs/reports/{report_name}"
        annotated_url = f"/outputs/annotated/{image_name}"
        original_url = None

    if report_path is None or annotated is None:
        return None
    report = _read_json(report_path)
    if report is None or not isinstance(report.get("inspection"), dict):
        return None

    record = {
        "id": inspection_id,
        "report": report,
        "originalUrl": original_url,
        "annotatedUrl": annotated_url,
        "reportUrl": report_url,
        "pdfUrl": f"/api/reports/{inspection_id}.pdf",
    }
    return record, original, annotated


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/frontend/index.html")


@app.get("/api/inspections")
def list_inspections():
    inspection_ids = {path.stem for path in REPORTS_DIR.glob("*.json")}
    inspection_ids.update(path.parent.name for path in INSPECTIONS_DIR.glob("*/report.json"))
    records = []
    for inspection_id in inspection_ids:
        entry = _read_record(inspection_id)
        if entry is not None:
            records.append(entry[0])
    records.sort(key=lambda record: (str(record["report"].get("timestamp", "")), record["id"]), reverse=True)

    featured = _read_json(INSPECTIONS_DIR / "featured.json") or {}
    featured_id = featured.get("id")
    if not any(record["id"] == featured_id and record["originalUrl"] for record in records):
        featured_id = None

    return {"records": records, "featuredId": featured_id}


@app.get("/api/reports/{inspection_id}.pdf")
def download_report_pdf(inspection_id: str):
    entry = _read_record(inspection_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Inspection report not found.")

    from pdf_report import build_inspection_pdf

    record, original, annotated = entry
    pdf = build_inspection_pdf(inspection_id, record["report"], original_path=original, annotated_path=annotated)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{inspection_id}.pdf"'},
    )


@app.post("/api/inspect")
def inspect_image(image: UploadFile):
    if not WEIGHTS.is_file():
        raise HTTPException(status_code=503, detail=f"Trained model weights are missing. Put best.pt at {WEIGHTS}.")

    byte_limit = MAX_UPLOAD_MB * 1024 * 1024
    upload = image.file.read(byte_limit + 1)
    if len(upload) > byte_limit:
        raise HTTPException(status_code=413, detail=f"Choose a JPG or PNG under {MAX_UPLOAD_MB} MB.")

    try:
        with open_pcb_image(BytesIO(upload)) as source:
            if source.format not in {"JPEG", "PNG"}:
                raise HTTPException(status_code=415, detail="Choose a JPG or PNG image.")
            original = ImageOps.exif_transpose(source).convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise HTTPException(status_code=422, detail="Could not read this image. Choose a valid JPG or PNG.") from error

    inspection_id = uuid4().hex
    INSPECTIONS_DIR.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".pending-", dir=INSPECTIONS_DIR) as temporary:
        work_dir = Path(temporary)
        record_dir = work_dir / "record"
        record_dir.mkdir()
        input_path = record_dir / "original.png"
        # Apply the same EXIF orientation that the browser shows in the upload.
        original.save(input_path)
        with inference_lock:
            inference = run_inference(input_path, weights_path=WEIGHTS)
        processed = postprocess_detections(inference.raw_detections, image_shape=inference.image_shape)
        result = decide(processed)
        paths = generate_report(input_path, result, board_id="inspection", output_dir=work_dir)
        report = json.loads(paths.json_report.read_text(encoding="utf-8"))
        filename = (image.filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
        report["source_image"] = filename or "upload.png"
        url_base = f"/outputs/inspections/{inspection_id}"
        report["artifacts"]["original_image"] = f"{url_base}/original.png"
        report["artifacts"]["annotated_image"] = f"{url_base}/annotated.png"
        paths.annotated_image.rename(record_dir / "annotated.png")
        (record_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        record_dir.rename(INSPECTIONS_DIR / inspection_id)

    return _read_record(inspection_id)[0]


app.mount("/frontend", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
app.mount("/outputs", StaticFiles(directory=ROOT / "outputs"), name="outputs")
