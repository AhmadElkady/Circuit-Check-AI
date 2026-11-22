"""Operator UI: streamlit run app.py"""
import numpy as np, cv2, streamlit as st
from ultralytics import YOLO
import sys; sys.path.insert(0, "src")
from infer import inspect

st.set_page_config(page_title="CircuitCheck AI", layout="wide")
st.title("CircuitCheck AI")
weights = st.sidebar.text_input("Weights path", "runs/circuitcheck/weights/best.pt")
conf = st.sidebar.slider("Sensitivity (confidence threshold)", 0.1, 0.9, 0.4, 0.05)

@st.cache_resource
def load(w): return YOLO(w)

up = st.file_uploader("Upload a board image", type=["jpg", "jpeg", "png"])
if up:
    img = cv2.imdecode(np.frombuffer(up.read(), np.uint8), cv2.IMREAD_COLOR)
    status, defects, vis = inspect(load(weights), img, conf)
    c1, c2 = st.columns(2)
    c1.image(img[:, :, ::-1], caption="Input")
    c2.image(vis[:, :, ::-1], caption="Detections")
    (st.error if status == "FAIL" else st.success)(f"Result: {status}")
    if defects: st.table(defects)
