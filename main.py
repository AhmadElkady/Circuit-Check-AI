"""Streamlit main.py compatible with an unmodified src/pipeline.py."""
from __future__ import annotations

import importlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import streamlit as st  # noqa: E402

from config import ALLOWED_EXTENSIONS, ANNOTATED_DIR, BOARDS, REPORTS_DIR, WEIGHTS  # noqa: E402

TARGET_SAMPLE_PATH = ROOT / "datasets" / "pcb" / "images" / "test" / "example.jpg"
BACKUP_SAMPLE_PATH = ROOT / "outputs" / "_example_backup.jpg"


def _run_untouched_pipeline(uploaded_bytes: bytes) -> None:
    """Write uploaded image to pipeline's hardcoded path, run pipeline, and restore."""
    TARGET_SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BACKUP_SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)

    had_existing = TARGET_SAMPLE_PATH.exists()
    if had_existing:
        shutil.copy2(TARGET_SAMPLE_PATH, BACKUP_SAMPLE_PATH)

    try:
        TARGET_SAMPLE_PATH.write_bytes(uploaded_bytes)

        if "pipeline" in sys.modules:
            importlib.reload(sys.modules["pipeline"])
        else:
            importlib.import_module("pipeline")
    finally:
        if had_existing and BACKUP_SAMPLE_PATH.exists():
            shutil.move(str(BACKUP_SAMPLE_PATH), str(TARGET_SAMPLE_PATH))
        elif TARGET_SAMPLE_PATH.exists():
            TARGET_SAMPLE_PATH.unlink()


def main() -> None:
    st.set_page_config(page_title="CircuitCheck AI", page_icon="🔌", layout="wide")
    st.title("CircuitCheck AI — PCB Defect Inspection")

    board_options = list(BOARDS.keys()) if BOARDS else ["board_A", "board_B"]
    allowed_types = [ext.lstrip(".") for ext in ALLOWED_EXTENSIONS]

    with st.sidebar:
        st.header("Inspection Settings")
        st.selectbox("Board ID", options=board_options, index=0)
        st.caption(f"Weights: `{WEIGHTS}`")
        st.caption("Pipeline target path: `datasets/pcb/images/test/example.jpg`")

    uploaded = st.file_uploader("Upload a PCB image", type=allowed_types)
    if uploaded is None:
        st.info("Upload a PCB image above to run `pipeline.py` without modifying it.")
        return

    st.image(uploaded.getvalue(), caption=f"Uploaded: {uploaded.name}", width="stretch")

    if st.button("Run Pipeline", type="primary"):
        with st.spinner("Running unmodified pipeline.py..."):
            _run_untouched_pipeline(uploaded.getvalue())

        st.success("`pipeline.py` finished running.")

        latest_annotated = sorted(
            Path(ANNOTATED_DIR).glob("*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        latest_reports = sorted(
            Path(REPORTS_DIR).glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        if latest_annotated:
            st.subheader("Latest Annotated Output")
            st.image(str(latest_annotated[0]), width="stretch")

        if latest_reports:
            st.subheader("Latest JSON Report")
            report_data = json.loads(latest_reports[0].read_text(encoding="utf-8"))
            st.json(report_data)


if __name__ == "__main__":
    main()