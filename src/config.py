"""Shared settings for CircuitCheck AI. Every other module imports from here.

Rule: no logic and no heavy imports in this file, only constants and tiny helpers.
Run all scripts from the project root so the paths below resolve correctly.
"""
from pathlib import Path

# ---------------------------------------------------------------- paths
ROOT = Path(__file__).resolve().parent.parent        # circuitcheck/

DATASET_DIR = ROOT / "datasets" / "pcb"
DATA_YAML = DATASET_DIR / "data.yaml"

MODEL_DIR = ROOT / "models" / "yolo"
WEIGHTS = MODEL_DIR / "weights" / "best.pt"          # deployed model
MODEL_CONFIG_DIR = MODEL_DIR / "config"

GOLDEN_DIR = ROOT / "golden"
BOARDS = {                                           # board_id -> golden image
    "board_A": GOLDEN_DIR / "board_A" / "golden.png",
    "board_B": GOLDEN_DIR / "board_B" / "golden.png",
}

OUTPUT_DIR = ROOT / "outputs"
ANNOTATED_DIR = OUTPUT_DIR / "annotated"
REPORTS_DIR = OUTPUT_DIR / "reports"
TRAINING_DIR = OUTPUT_DIR / "training_results"

# ---------------------------------------------------------------- classes
# ORDER MATTERS: index i here must be class id i in datasets/pcb/data.yaml.
# Only list defects you actually have labeled examples of.
CLASSES = [
    "missing_hole",
    "mouse_bite",
    "open_circuit",
    "short",
    "spur",
    "spurious_copper",
]

# severity per class: "critical" | "major" | "minor"
SEVERITY = {
    "missing_hole": "major",
    "mouse_bite": "minor",
    "open_circuit": "critical",
    "short": "critical",
    "spur": "minor",
    "spurious_copper": "major",
}
CRITICAL = {c for c, s in SEVERITY.items() if s == "critical"}

# ---------------------------------------------------------------- training
BASE_MODEL = "yolov8n.pt"      # pretrained starting weights
EPOCHS = 50
IMGSZ = 640
BATCH = 16
DEVICE = "cpu"                 # use 0 for the first NVIDIA GPU
SEED = 42
# Flips would change what "orientation" means, so keep them off while a
# wrong_orientation class exists.
AUGMENT = {"fliplr": 0.0, "flipud": 0.0, "mosaic": 0.5}

# ---------------------------------------------------------------- detection
CONF_DEFAULT = 0.40
CONF_THRESHOLDS = {
    "missing_hole": 0.35,
    "mouse_bite": 0.40,
    "open_circuit": 0.30,
    "short": 0.30,
    "spur": 0.40,
    "spurious_copper": 0.35,
}
USE_TILING = False             # True for tiny defects on large images
TILE_SIZE = 640
TILE_OVERLAP = 0.20            # fraction of overlap between neighbouring tiles

# ---------------------------------------------------------------- post-processing
NMS_IOU = 0.50                 # merge boxes of the same class overlapping this much
MIN_BOX_AREA = 16              # px^2, smaller boxes are dropped as noise

# ---------------------------------------------------------------- decision
REVIEW_MARGIN = 0.10           # conf in [threshold - margin, threshold) -> REVIEW
STATUS_PASS, STATUS_FAIL, STATUS_REVIEW = "PASS", "FAIL", "REVIEW"

# ---------------------------------------------------------------- alignment
USE_ALIGNMENT = False          # turn on when images are not in a fixed position
ALIGN_MIN_INLIERS = 15         # fewer matched keypoints -> alignment failed

# ---------------------------------------------------------------- API
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
MAX_UPLOAD_MB = 20


# ---------------------------------------------------------------- helpers
def conf_threshold(cls_name: str) -> float:
    """Confidence needed for this class to count as a detection."""
    return CONF_THRESHOLDS.get(cls_name, CONF_DEFAULT)


def ensure_dirs() -> None:
    """Create output folders (call at startup so a fresh clone does not crash)."""
    for d in (ANNOTATED_DIR, REPORTS_DIR, TRAINING_DIR, MODEL_DIR / "weights", MODEL_CONFIG_DIR):
        d.mkdir(parents=True, exist_ok=True)


def validate() -> None:
    """Catch typos in this file early. Raises ValueError on a problem."""
    if len(set(CLASSES)) != len(CLASSES):
        raise ValueError("CLASSES contains duplicates")
    for name, table in (("SEVERITY", SEVERITY), ("CONF_THRESHOLDS", CONF_THRESHOLDS)):
        unknown = set(table) - set(CLASSES)
        if unknown:
            raise ValueError(f"{name} has classes not in CLASSES: {sorted(unknown)}")
    missing = set(CLASSES) - set(SEVERITY)
    if missing:
        raise ValueError(f"SEVERITY is missing classes: {sorted(missing)}")
    if not 0 < CONF_DEFAULT < 1:
        raise ValueError("CONF_DEFAULT must be between 0 and 1")


def validate_against_data_yaml(path=DATA_YAML) -> None:
    """Check that CLASSES matches data.yaml (same names, same order)."""
    import yaml  # installed together with ultralytics
    with open(path, encoding="utf-8") as f:
        names = yaml.safe_load(f)["names"]
    names = [names[k] for k in sorted(names)] if isinstance(names, dict) else list(names)
    if names != CLASSES:
        raise ValueError(f"data.yaml classes {names} != config.CLASSES {CLASSES}")


validate()