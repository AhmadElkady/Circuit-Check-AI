
from pathlib import Path
from ultralytics import YOLO

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATASET_CONFIG = PROJECT_ROOT / "datasets" / "pcb" / "data.yaml"

OUTPUT_DIR = PROJECT_ROOT / "models" / "yolo" / "weights"

TRAINING_RESULTS = PROJECT_ROOT / "outputs" / "training_results"


def train_model():

    # 1. Check dataset configuration
    if not DATASET_CONFIG.exists():
        raise FileNotFoundError(
            f"Dataset configuration not found: {DATASET_CONFIG}"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TRAINING_RESULTS.mkdir(parents=True, exist_ok=True)

    # 2. Load pretrained YOLO model
    model = YOLO("yolo11n.pt")

    # 3. Train model
    results = model.train(
        data=str(DATASET_CONFIG),
        epochs=100,
        imgsz=640,
        batch=16,
        patience=20,
        optimizer="auto",
        device="0",  # NVIDIA GPU; change to "cpu" if unavailable
        project=str(TRAINING_RESULTS),
        name="pcb_defect_detection",
        exist_ok=True,
        plots=True,
        save=True,
        workers=4
    )

    # 4. Save best model
    best_weights = (
        Path(results.save_dir) / "weights" / "best.pt"
    )

    if not best_weights.exists():
        raise FileNotFoundError("Training completed but best.pt was not found.")

    import shutil

    destination = OUTPUT_DIR / "best.pt"
    shutil.copy2(best_weights, destination)

    print("\nTraining completed successfully!")
    print(f"Best model saved at: {destination}")


if __name__ == "__main__":
    train_model()
