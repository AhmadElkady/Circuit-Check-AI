"""Train: python src/train.py --data datasets/synthetic/data.yaml --epochs 30"""
import argparse
from ultralytics import YOLO

p = argparse.ArgumentParser()
p.add_argument("--data", default="datasets/synthetic/data.yaml")
p.add_argument("--model", default="yolov8n.pt")
p.add_argument("--epochs", type=int, default=30)
p.add_argument("--imgsz", type=int, default=640)
p.add_argument("--device", default="cpu")
a = p.parse_args()
m = YOLO(a.model)
# fliplr=0: flips would change polarity/orientation meaning
m.train(data=a.data, epochs=a.epochs, imgsz=a.imgsz, device=a.device,
        fliplr=0.0, flipud=0.0, mosaic=0.5, project="runs", name="circuitcheck", exist_ok=True)
