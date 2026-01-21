import streamlit as st
import cv2
import face_recognition
import numpy as np
import pandas as pd
import os
import time
from datetime import datetime

# ==============================
# IP CAMERA CONFIG (SUB-STREAM)
# ==============================
RTSP_URL = "rtsp://admin:Admin%40123@192.168.0.245:554/cam/realmonitor?channel=1&subtype=1"

# ==============================
# SYSTEM CONFIG
# ==============================
st.set_page_config(page_title="FactoryGuard AI – Attendance", layout="wide")

FACES_DIR = "known_faces"
ATTENDANCE_FILE = "factory_logs.csv"

MIN_SHIFT_MINUTES = 60
RESCAN_COOLDOWN = 2
FRAME_SKIP = 3            # run face AI every 3 frames
FACE_TOLERANCE = 0.42

os.makedirs(FACES_DIR, exist_ok=True)
if not os.path.exists(ATTENDANCE_FILE):
    pd.DataFrame(columns=["Name", "Time", "Date", "Type"]).to_csv(
        ATTENDANCE_FILE, index=False
    )

# ==============================
# LOAD FACE DATABASE
# ==============================
@st.cache_resource
def load_database():
    encs, names = [], []
    for root, _, files in os.walk(FACES_DIR):
        for f in files:
            if f.endswith(".jpg"):
                path = os.path.join(root, f)
                img = face_recognition.load_image_file(path)
                e = face_recognition.face_encodings(img)
                if e:
                    encs.append(e[0])
                    names.append(os.path.basename(os.path.dirname(path)))
    return encs, names

# ==============================
# ATTENDANCE LOGIC
# ==============================
def smart_log_logic(name):
    now = datetime.now()
    d = now.strftime("%Y-%m-%d")
    t = now.strftime("%H:%M:%S")

    df = pd.read_csv(ATTENDANCE_FILE)
    logs = df[(df["Name"] == name) & (df["Date"] == d)]

    if logs.empty:
        pd.DataFrame([[name, t, d, "CHECK-IN"]], columns=df.columns)\
            .to_csv(ATTENDANCE_FILE, mode="a", header=False, index=False)
        return "CHECK-IN", (0, 255, 0)

    last = logs.iloc[-1]
    last_dt = datetime.strptime(
        f"{last['Date']} {last['Time']}", "%Y-%m-%d %H:%M:%S"
    )
    mins = (now - last_dt).total_seconds() / 60

    if mins < RESCAN_COOLDOWN:
        return None, None

    if last["Type"] == "CHECK-IN" and mins < MIN_SHIFT_MINUTES:
        return "ON SHIFT", (0, 255, 0)

    new_type = "CHECK-OUT" if last["Type"] == "CHECK-IN" else "CHECK-IN"
    pd.DataFrame([[name, t, d, new_type]], columns=df.columns)\
        .to_csv(ATTENDANCE_FILE, mode="a", header=False, index=False)

    return new_type, (0, 0, 255)

# ==============================
# ATTENDANCE ENGINE
# ==============================
class AttendanceEngine:
    def __init__(self):
        self.encodings, self.names = load_database()
        self.frame_count = 0
        self.last_results = []

    def process(self, frame):
        self.frame_count += 1

        if self.frame_count % FRAME_SKIP == 0:
            small = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

            locs = face_recognition.face_locations(
                rgb, model="hog", number_of_times_to_upsample=1
            )
            encs = face_recognition.face_encodings(rgb, locs)

            results = []
            for enc, loc in zip(encs, locs):
                matches = face_recognition.compare_faces(
                    self.encodings, enc, tolerance=FACE_TOLERANCE
                )
                name = "Unknown"
                color = (200, 200, 200)
                status = ""

                if True in matches:
                    idx = matches.index(True)
                    name = self.names[idx]
                    res = smart_log_logic(name)
                    if res and res[0]:
                        status, color = res

                results.append((name, status, color, loc))

            self.last_results = results

        # Draw results
        for name, status, color, loc in self.last_results:
            top, right, bottom, left = [v * 2 for v in loc]
            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
            label = f"{name} {status}"
            cv2.putText(
                frame, label, (left, top - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2
            )

        return frame

# ==============================
# STREAMLIT UI
# ==============================
st.title("🏭 Factory Attendance – IP Camera")

engine = AttendanceEngine()
frame_box = st.empty()

while True:
    cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        st.error("❌ Camera not reachable. Retrying in 5 seconds...")
        time.sleep(5)
        continue

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = engine.process(frame)
        frame_box.image(
            cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
            use_container_width=True
        )
