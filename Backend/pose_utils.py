import math
import os
import urllib.request

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python import vision

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


def model_path(complexity: int) -> str:
    complexity = 1 if complexity >= 1 else 0
    path = os.path.join(MODEL_DIR, os.path.basename(MODEL_URLS[complexity]))
    if not os.path.exists(path):
        os.makedirs(MODEL_DIR, exist_ok=True)
        print(f"Downloading pose model to {path} ...")
        urllib.request.urlretrieve(MODEL_URLS[complexity], path)
    return path


def create_landmarker(video: bool, complexity: int = 1):
    options = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=model_path(complexity)),
        running_mode=vision.RunningMode.VIDEO if video else vision.RunningMode.IMAGE,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    return vision.PoseLandmarker.create_from_options(options)


def detect_landmarks(landmarker, bgr_frame, timestamp_ms=None):
    rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    if timestamp_ms is None:
        result = landmarker.detect(image)
    else:
        result = landmarker.detect_for_video(image, timestamp_ms)
    return result.pose_landmarks[0] if result.pose_landmarks else None


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
