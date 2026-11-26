"""Serve the frontend and adapt the Python inspection pipeline to an upload."""

import base64
from io import BytesIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Lock

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps
from PIL.Image import open as open_pcb_image  # Keep Pillow's decoder before Ultralytics adds optional format handling.

ROOT = Path(__file__).resolve().parent
# The existing scripts use flat imports from src.
sys.path.insert(0, str(ROOT / "src"))

from config import MAX_UPLOAD_MB, WEIGHTS
from decision import decide
from infer import run_inference
from post_processing import postprocess_detections
from reporting import generate_report

app = FastAPI()
inference_lock = Lock()


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/frontend/index.html")


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

    with TemporaryDirectory(prefix="circuitcheck-") as temporary:
        work_dir = Path(temporary)
        input_path = work_dir / "input.png"
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
        report["artifacts"]["annotated_image"] = paths.annotated_image.name
        annotated = base64.b64encode(paths.annotated_image.read_bytes()).decode("ascii")

    return {"report": report, "annotatedImage": f"data:image/png;base64,{annotated}"}


app.mount("/frontend", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
app.mount("/outputs", StaticFiles(directory=ROOT / "outputs"), name="outputs")
