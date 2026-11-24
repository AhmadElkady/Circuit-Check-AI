"""
Prepare the Kaggle Akhatova PCB Defects dataset for YOLO object detection.

Expected source (usual Kaggle extraction):
    <source>/PCB_DATASET/images/<class>/*.jpg
    <source>/PCB_DATASET/Annotations/<class>/*.xml

Run:
    python scripts/prepare_dataset.py --source "F:/path/to/PCB_DATASET"

The script:
- keeps only the six official PCB defect classes;
- matches each image to its Pascal VOC XML annotation by filename stem;
- converts VOC boxes to YOLO normalized xywh labels;
- splits by board ID (filename prefix, e.g. 01 in 01_missing_hole_01.jpg)
  to reduce leakage between related board images;
- writes images/{train,val,test}, labels/{train,val,test}, data.yaml,
  and a preparation_report.json.

If your extracted folder differs, pass --images-dir and --annotations-dir.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

CLASSES = [
    "missing_hole",
    "mouse_bite",
    "open_circuit",
    "short",
    "spur",
    "spurious_copper",
]
CLASS_TO_ID = {name: i for i, name in enumerate(CLASSES)}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}

def normalize_class(value: str) -> str:
    value = value.strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "missinghole": "missing_hole",
        "mousebite": "mouse_bite",
        "opencircuit": "open_circuit",
        "spuriouscopper": "spurious_copper",
    }
    return aliases.get(value.replace("_", ""), value)

def find_dirs(source: Path, images_arg: str | None, annotations_arg: str | None):
    if images_arg:
        images_dir = Path(images_arg)
    else:
        candidates = [source / "images", source / "PCB_DATASET" / "images"]
        images_dir = next((p for p in candidates if p.is_dir()), None)

    if annotations_arg:
        annotations_dir = Path(annotations_arg)
    else:
        candidates = [
            source / "Annotations",
            source / "annotations",
            source / "PCB_DATASET" / "Annotations",
            source / "PCB_DATASET" / "annotations",
        ]
        annotations_dir = next((p for p in candidates if p.is_dir()), None)

    if images_dir is None or not images_dir.is_dir():
        raise FileNotFoundError("Could not find images directory. Use --images-dir.")
    if annotations_dir is None or not annotations_dir.is_dir():
        raise FileNotFoundError("Could not find VOC annotations directory. Use --annotations-dir.")
    return images_dir, annotations_dir

def annotation_index(annotations_dir: Path):
    index = {}
    for xml_path in annotations_dir.rglob("*.xml"):
        # Stem is normally unique in this dataset; preserve first deterministic match.
        index.setdefault(xml_path.stem.lower(), xml_path)
    return index

def parse_voc(xml_path: Path):
    root = ET.parse(xml_path).getroot()
    size = root.find("size")
    if size is None:
        raise ValueError(f"Missing <size> in {xml_path}")
    width = float(size.findtext("width", "0"))
    height = float(size.findtext("height", "0"))
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid image dimensions in {xml_path}")

    labels = []
    for obj in root.findall("object"):
        raw_name = obj.findtext("name", "")
        class_name = normalize_class(raw_name)
        if class_name not in CLASS_TO_ID:
            continue
        box = obj.find("bndbox")
        if box is None:
            continue
        xmin = float(box.findtext("xmin", "0"))
        ymin = float(box.findtext("ymin", "0"))
        xmax = float(box.findtext("xmax", "0"))
        ymax = float(box.findtext("ymax", "0"))

        # Clip boxes to image boundaries and reject invalid/zero-area boxes.
        xmin = min(max(xmin, 0.0), width)
        xmax = min(max(xmax, 0.0), width)
        ymin = min(max(ymin, 0.0), height)
        ymax = min(max(ymax, 0.0), height)
        if xmax <= xmin or ymax <= ymin:
            continue

        x_center = ((xmin + xmax) / 2.0) / width
        y_center = ((ymin + ymax) / 2.0) / height
        box_width = (xmax - xmin) / width
        box_height = (ymax - ymin) / height
        labels.append(
            f"{CLASS_TO_ID[class_name]} {x_center:.6f} {y_center:.6f} "
            f"{box_width:.6f} {box_height:.6f}"
        )
    return labels

def board_group(image_path: Path):
    # Typical names: 01_missing_hole_11.jpg. Group by leading board identifier.
    prefix = image_path.stem.split("_", 1)[0]
    return prefix if prefix.isdigit() else image_path.stem

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="Extracted dataset root or PCB_DATASET folder")
    parser.add_argument("--output", default="datasets/pcb", help="Output YOLO dataset directory")
    parser.add_argument("--images-dir", default=None)
    parser.add_argument("--annotations-dir", default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--val-ratio", type=float, default=0.15)
    args = parser.parse_args()

    if not (0 < args.train_ratio < 1 and 0 < args.val_ratio < 1 and
            args.train_ratio + args.val_ratio < 1):
        raise ValueError("Train and val ratios must be positive and sum to less than 1.")

    source = Path(args.source)
    images_dir, annotations_dir = find_dirs(
        source, args.images_dir, args.annotations_dir
    )
    xml_by_stem = annotation_index(annotations_dir)

    records = []
    skipped_no_xml = []
    skipped_bad = []
    for image_path in sorted(images_dir.rglob("*")):
        if not image_path.is_file() or image_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        # Only accept images stored under one of the six known class folders.
        relative_parts = [p.lower().replace(" ", "_") for p in image_path.relative_to(images_dir).parts]
        if not any(normalize_class(part) in CLASSES for part in relative_parts[:-1]):
            continue

        xml_path = xml_by_stem.get(image_path.stem.lower())
        if xml_path is None:
            skipped_no_xml.append(str(image_path))
            continue
        try:
            yolo_labels = parse_voc(xml_path)
            if not yolo_labels:
                skipped_bad.append({"image": str(image_path), "reason": "no valid target boxes"})
                continue
        except Exception as exc:
            skipped_bad.append({"image": str(image_path), "reason": str(exc)})
            continue

        records.append({
            "image": image_path,
            "labels": yolo_labels,
            "group": board_group(image_path),
            "xml": xml_path,
        })

    if not records:
        raise RuntimeError(
            "No annotated images found. Check the source folders and XML annotations."
        )

    # Split by board group so images from the same board ID cannot cross splits.
    groups = defaultdict(list)
    for record in records:
        groups[record["group"]].append(record)

    group_names = sorted(groups)
    random.Random(args.seed).shuffle(group_names)
    n = len(group_names)
    n_train = max(1, round(n * args.train_ratio))
    n_val = max(1, round(n * args.val_ratio))
    if n_train + n_val >= n:
        n_train = max(1, n - 2)
        n_val = 1
    split_groups = {
        "train": set(group_names[:n_train]),
        "val": set(group_names[n_train:n_train + n_val]),
        "test": set(group_names[n_train + n_val:]),
    }
    if not split_groups["test"]:
        raise RuntimeError("Not enough distinct board groups for a train/val/test split.")

    output = Path(args.output)
    for split in ("train", "val", "test"):
        (output / "images" / split).mkdir(parents=True, exist_ok=True)
        (output / "labels" / split).mkdir(parents=True, exist_ok=True)

    split_counts = Counter()
    class_counts = Counter()
    for record in records:
        split = next(name for name, members in split_groups.items()
                     if record["group"] in members)
        # Prefix with source class folder to avoid same-stem filename collisions.
        class_folder = next(
            (part for part in record["image"].relative_to(images_dir).parts[:-1]
             if normalize_class(part) in CLASSES),
            "pcb"
        )
        safe_stem = f"{normalize_class(class_folder)}__{record['image'].stem}"
        destination_image = output / "images" / split / f"{safe_stem}{record['image'].suffix.lower()}"
        destination_label = output / "labels" / split / f"{safe_stem}.txt"
        shutil.copy2(record["image"], destination_image)
        destination_label.write_text("\n".join(record["labels"]) + "\n", encoding="utf-8")
        split_counts[split] += 1
        for line in record["labels"]:
            class_counts[int(line.split()[0])] += 1

    yaml_text = (
        f"path: {output.resolve().as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n\n"
        f"nc: {len(CLASSES)}\n"
        "names:\n" + "".join(f"  {i}: {name}\n" for i, name in enumerate(CLASSES))
    )
    (output / "data.yaml").write_text(yaml_text, encoding="utf-8")

    report = {
        "source_images_dir": str(images_dir.resolve()),
        "source_annotations_dir": str(annotations_dir.resolve()),
        "total_usable_images": len(records),
        "split_images": dict(split_counts),
        "board_groups_per_split": {k: sorted(v) for k, v in split_groups.items()},
        "class_instance_counts": {CLASSES[i]: class_counts[i] for i in range(len(CLASSES))},
        "skipped_without_xml": skipped_no_xml,
        "skipped_invalid_or_empty_annotations": skipped_bad,
        "split_strategy": "grouped by leading numeric filename prefix",
        "seed": args.seed,
    }
    (output / "preparation_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "status": "complete",
        "output": str(output.resolve()),
        "usable_images": len(records),
        "split_images": dict(split_counts),
        "classes": CLASSES,
        "report": str((output / "preparation_report.json").resolve()),
    }, indent=2))

if __name__ == "__main__":
    main()
