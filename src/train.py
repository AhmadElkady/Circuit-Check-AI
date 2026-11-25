
from pathlib import Path
import shutil

from ultralytics import YOLO

from config import (
    DATA_YAML,
    BASE_MODEL,
    EPOCHS,
    IMGSZ,
    BATCH,
    DEVICE,
    SEED,
    AUGMENT,
    TRAINING_DIR,
    WEIGHTS,
    ensure_dirs,
    validate,
    validate_against_data_yaml,
)


def train_model():

    # 1. Validate configuration
    validate()
    validate_against_data_yaml()

    if not DATA_YAML.exists():
        raise FileNotFoundError(
            f"Dataset configuration not found: {DATA_YAML}"
        )

    ensure_dirs()

    # 2. Load pretrained model
    model = YOLO(BASE_MODEL)

    # 3. Train
    results = model.train(
        data=str(DATA_YAML),
        epochs=EPOCHS,
        imgsz=IMGSZ,
        batch=BATCH,
        device=DEVICE,
        seed=SEED,
        fliplr=AUGMENT["fliplr"],
        flipud=AUGMENT["flipud"],
        mosaic=AUGMENT["mosaic"],
        project=str(TRAINING_DIR),
        name="pcb_defect_detection",
        exist_ok=True,
        patience=20,
        plots=True,
        save=True,
    )

    # 4. Retrieve best weights
    best_weights = Path(results.save_dir) / "weights" / "best.pt"

    if not best_weights.exists():
        raise FileNotFoundError("Best model weights were not generated.")

    # 5. Copy trained weights to deployment location
    shutil.copy2(best_weights, WEIGHTS)

    print("\nTraining completed!")
    print(f"Best model: {WEIGHTS}")


if __name__ == "__main__":
    train_model()
