from dataclasses import dataclass
import math
import os
import platform
import subprocess
import sys
import urllib.request
import zipfile

import cv2
import numpy as np

NOSE = 0
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_HIP = 23
RIGHT_HIP = 24
LEFT_ANKLE = 27
RIGHT_ANKLE = 28

CONNECTIONS = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27), (24, 26), (26, 28),
]

MODEL_URLS = {
    0: "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task",
    1: "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task",
}
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")


@dataclass
class Landmark:
    x: float
    y: float
    z: float
    visibility: float


def _cpu_lacks_aes_on_arm() -> bool:
    if platform.system() != "Linux" or platform.machine().lower() not in ("aarch64", "arm64", "armv7l"):
        return False
    try:
        with open("/proc/cpuinfo", "r") as f:
            info = f.read().lower()
        return "aes" not in info.split()
    except Exception:
        return False


def _check_mediapipe_usable() -> bool:
    if os.getenv("FORCE_TFLITE_DNN", "").lower() in ("1", "true", "yes"):
        return False
    if sys.version_info >= (3, 13) and _cpu_lacks_aes_on_arm():
        return False
    code = (
        "import mediapipe as mp; from mediapipe.tasks.python import vision; "
        "from mediapipe.tasks.python.core import mediapipe_c_bindings as b; b.load_raw_library()"
        if sys.version_info >= (3, 13)
        else "import mediapipe as mp; from mediapipe.tasks.python import vision"
    )
    try:
        res = subprocess.run(
            [sys.executable, "-c", code],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
        return res.returncode == 0
    except Exception:
        return False


MP_AVAILABLE = _check_mediapipe_usable()
if MP_AVAILABLE:
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python import vision
else:
    print("Using MediaPipe BlazePose TFLite model via OpenCV DNN (Raspberry Pi CPU mode)")


def model_path(complexity: int) -> str:
    complexity = 1 if complexity >= 1 else 0
    path = os.path.join(MODEL_DIR, os.path.basename(MODEL_URLS[complexity]))
    if not os.path.exists(path):
        os.makedirs(MODEL_DIR, exist_ok=True)
        print(f"Downloading pose model to {path} ...")
        urllib.request.urlretrieve(MODEL_URLS[complexity], path)
    return path


def _tflite_model_path(complexity: int) -> str:
    task_file = model_path(complexity)
    tflite_file = os.path.join(MODEL_DIR, f"pose_landmarks_detector_{1 if complexity >= 1 else 0}.tflite")
    if not os.path.exists(tflite_file):
        with zipfile.ZipFile(task_file, "r") as zf:
            with open(tflite_file, "wb") as out:
                out.write(zf.read("pose_landmarks_detector.tflite"))
    return tflite_file


def create_landmarker(video: bool, complexity: int = 1):
    if MP_AVAILABLE:
        options = vision.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path(complexity)),
            running_mode=vision.RunningMode.VIDEO if video else vision.RunningMode.IMAGE,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        return vision.PoseLandmarker.create_from_options(options)
    return cv2.dnn.readNetFromTFLite(_tflite_model_path(complexity))


def detect_landmarks(landmarker, bgr_frame, timestamp_ms=None):
    if MP_AVAILABLE:
        rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        if timestamp_ms is None:
            result = landmarker.detect(image)
        else:
            result = landmarker.detect_for_video(image, timestamp_ms)
        return result.pose_landmarks[0] if result.pose_landmarks else None

    blob = cv2.dnn.blobFromImage(bgr_frame, scalefactor=1.0 / 255.0, size=(256, 256), swapRB=True)
    landmarker.setInput(blob)
    score = float(landmarker.forward("Identity_1").flat[0])
    if score < 0.35:
        return None
    raw = landmarker.forward("Identity")
    if raw.size >= 165:
        pts = raw.reshape(-1, 5)[:33]
        return [
            Landmark(
                x=float(pts[i, 0]) / 256.0,
                y=float(pts[i, 1]) / 256.0,
                z=float(pts[i, 2]) / 256.0,
                visibility=float(1.0 / (1.0 + math.exp(-max(-20.0, min(20.0, float(pts[i, 3])))))),
            )
            for i in range(33)
        ]
    pts3d = landmarker.forward("Identity_4").reshape(-1, 3)[:33]
    return [
        Landmark(
            x=float(np.clip(pts3d[i, 0] + 0.5, 0.0, 1.0)),
            y=float(np.clip(pts3d[i, 1] + 0.5, 0.0, 1.0)),
            z=float(pts3d[i, 2]),
            visibility=score,
        )
        for i in range(33)
    ]


def visibility(landmark) -> float:
    v = landmark.visibility
    if v is None:
        return 1.0
    if 0.0 <= v <= 1.0:
        return v
    return 1 / (1 + math.exp(-v))


def draw_landmarks(bgr_frame, landmarks):
    h, w = bgr_frame.shape[:2]
    points = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]
    for a, b in CONNECTIONS:
        cv2.line(bgr_frame, points[a], points[b], (255, 255, 255), 2)
    for i in {i for pair in CONNECTIONS for i in pair} | {NOSE}:
        cv2.circle(bgr_frame, points[i], 4, (0, 0, 255), -1)
