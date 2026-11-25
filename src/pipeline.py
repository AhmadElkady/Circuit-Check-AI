from pathlib import Path
import cv2

from config import WEIGHTS
from ultralytics import YOLO

from infer import convert_yolo_results
from post_processing import postprocess_detections
from decision import decide
from reporting import generate_report

# Load image
image_path = Path("datasets/pcb/images/test/example.jpg")

image = cv2.imread(str(image_path))

if image is None:
    raise FileNotFoundError(f"Could not load image: {image_path}")

# Load trained YOLO model
model = YOLO(str(WEIGHTS))

# Run inference
results = model.predict(source=image, verbose=False)

# Convert YOLO output
raw_detections = convert_yolo_results(results)

# Post-processing
processed = postprocess_detections(
    raw_detections,
    image_shape=image.shape[:2]
)

# Inspection decision
decision_result = decide(processed)

# Generate report
reports = generate_report(
    image_path=image_path,
    result=decision_result,
    board_id="board_A"
)

print("Status:", decision_result.status)
print("Defects:", decision_result.total_defects)
print("Report:", reports.json_report)
print("Annotated:", reports.annotated_image)