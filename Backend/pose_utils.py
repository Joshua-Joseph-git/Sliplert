from dataclasses import dataclass
import math
import os
import platform
import subprocess
import sys
import urllib.request

import cv2
import numpy as np

NOSE = 0
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_ELBOW = 13
RIGHT_ELBOW = 14
LEFT_WRIST = 15
RIGHT_WRIST = 16
LEFT_HIP = 23
RIGHT_HIP = 24
LEFT_KNEE = 25
RIGHT_KNEE = 26
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
MOVENET_ONNX_URL = "https://huggingface.co/Xenova/movenet-singlepose-lightning/resolve/main/onnx/model.onnx"
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
    if os.getenv("FORCE_ONNX_POSE", "").lower() in ("1", "true", "yes"):
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


def _ensure_onnxruntime():
    try:
        import onnxruntime as ort
        return ort
    except ImportError:
        print("Installing onnxruntime for Raspberry Pi pose detection...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "onnxruntime"], check=False)
        import onnxruntime as ort
        return ort


MP_AVAILABLE = _check_mediapipe_usable()
if MP_AVAILABLE:
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python import vision
else:
    print("Using MoveNet Pose ONNX engine with multi-scale & flat-fall detection (Raspberry Pi mode)")


def model_path(complexity: int) -> str:
    complexity = 1 if complexity >= 1 else 0
    path = os.path.join(MODEL_DIR, os.path.basename(MODEL_URLS[complexity]))
    if not os.path.exists(path):
        os.makedirs(MODEL_DIR, exist_ok=True)
        print(f"Downloading pose model to {path} ...")
        urllib.request.urlretrieve(MODEL_URLS[complexity], path)
    return path


def _movenet_onnx_path() -> str:
    path = os.path.join(MODEL_DIR, "movenet_lightning.onnx")
    if not os.path.exists(path):
        os.makedirs(MODEL_DIR, exist_ok=True)
        print(f"Downloading MoveNet pose model to {path} ...")
        req = urllib.request.Request(MOVENET_ONNX_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            with open(path, "wb") as out:
                out.write(resp.read())
    return path


def create_landmarker(video: bool, complexity: int = 1):
    if MP_AVAILABLE:
        options = vision.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path(complexity)),
            running_mode=vision.RunningMode.IMAGE,
            num_poses=1,
            min_pose_detection_confidence=0.35,
            min_pose_presence_confidence=0.35,
            min_tracking_confidence=0.35,
        )
        return vision.PoseLandmarker.create_from_options(options)
    ort = _ensure_onnxruntime()
    return ort.InferenceSession(_movenet_onnx_path(), providers=["CPUExecutionProvider"])


def _movenet_kpts_to_33(kpts: np.ndarray):
    lms = [Landmark(0.5, 0.5, 0.0, 0.0) for _ in range(33)]
    mapping = {
        0: 0,   # nose
        2: 1,   # left eye
        5: 2,   # right eye
        7: 3,   # left ear
        8: 4,   # right ear
        11: 5,  # left shoulder
        12: 6,  # right shoulder
        13: 7,  # left elbow
        14: 8,  # right elbow
        15: 9,  # left wrist
        16: 10, # right wrist
        23: 11, # left hip
        24: 12, # right hip
        25: 13, # left knee
        26: 14, # right knee
        27: 15, # left ankle
        28: 16, # right ankle
    }
    for mp_idx, mn_idx in mapping.items():
        y, x, s = float(kpts[mn_idx, 0]), float(kpts[mn_idx, 1]), float(kpts[mn_idx, 2])
        lms[mp_idx] = Landmark(x=x, y=y, z=0.0, visibility=s)
    return lms


def _run_movenet_raw(sess, bgr_frame: np.ndarray) -> np.ndarray:
    in_name = sess.get_inputs()[0].name
    rgb = cv2.cvtColor(cv2.resize(bgr_frame, (192, 192)), cv2.COLOR_BGR2RGB).astype(np.int32)[None, ...]
    return sess.run(None, {in_name: rgb})[0][0, 0]


def _pose_score(lms) -> float:
    if not lms:
        return 0.0
    return max(
        visibility(lms[NOSE]),
        (visibility(lms[LEFT_SHOULDER]) + visibility(lms[RIGHT_SHOULDER])) / 2.0,
    )


def _mp_detect_single(landmarker, bgr_frame: np.ndarray):
    rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = landmarker.detect(image)
    return result.pose_landmarks[0] if result.pose_landmarks else None


def detect_landmarks(landmarker, bgr_frame, timestamp_ms=None):
    h, w = bgr_frame.shape[:2]

    if MP_AVAILABLE:
        best = _mp_detect_single(landmarker, bgr_frame)
        best_score = _pose_score(best)

        # Far-away 2x center zoom check if full frame didn't catch the person
        if best_score < 0.40:
            y0, y1, x0, x1 = h // 6, (5 * h) // 6, w // 6, (5 * w) // 6
            crop_lms = _mp_detect_single(landmarker, bgr_frame[y0:y1, x0:x1])
            cs = _pose_score(crop_lms)
            if crop_lms and cs > best_score:
                best = [
                    Landmark(
                        x=lm.x * ((x1 - x0) / w) + (x0 / w),
                        y=lm.y * ((y1 - y0) / h) + (y0 / h),
                        z=lm.z,
                        visibility=visibility(lm),
                    )
                    for lm in crop_lms
                ]
                best_score = cs

        # Flat-on-the-floor 90-degree rotation check when person lies completely horizontal
        if best_score < 0.40:
            for rot_code, unmap in [
                (cv2.ROTATE_90_COUNTERCLOCKWISE, lambda y, x: (1.0 - x, y)),
                (cv2.ROTATE_90_CLOCKWISE, lambda y, x: (x, 1.0 - y)),
            ]:
                rot_lms = _mp_detect_single(landmarker, cv2.rotate(bgr_frame, rot_code))
                rs = _pose_score(rot_lms)
                if rot_lms and rs > best_score:
                    best = []
                    for lm in rot_lms:
                        ny, nx = unmap(lm.y, lm.x)
                        best.append(Landmark(x=nx, y=ny, z=lm.z, visibility=visibility(lm)))
                    best_score = rs

        return best if best_score >= 0.22 else None

    # Raspberry Pi ONNX MoveNet multi-scale + flat-fall detector
    kpts = _run_movenet_raw(landmarker, bgr_frame)
    best = kpts
    best_score = float(max(kpts[0, 2], (kpts[5, 2] + kpts[6, 2]) / 2.0))

    # 1) Far-away zoom crops so the Pi detects a person across the room
    if best_score < 0.38:
        for y0, y1, x0, x1 in [(h // 6, (5 * h) // 6, w // 6, (5 * w) // 6), (h // 4, (3 * h) // 4, w // 4, (3 * w) // 4)]:
            ck = _run_movenet_raw(landmarker, bgr_frame[y0:y1, x0:x1])
            cs = float(max(ck[0, 2], (ck[5, 2] + ck[6, 2]) / 2.0))
            if cs > best_score:
                mapped = ck.copy()
                mapped[:, 0] = ck[:, 0] * ((y1 - y0) / h) + (y0 / h)
                mapped[:, 1] = ck[:, 1] * ((x1 - x0) / w) + (x0 / w)
                best, best_score = mapped, cs

    # 2) 90-degree rotated pass so the Pi detects a person lying completely flat on the floor
    if best_score < 0.38:
        for rot_code, unmap in [
            (cv2.ROTATE_90_COUNTERCLOCKWISE, lambda y, x: (1.0 - x, y)),
            (cv2.ROTATE_90_CLOCKWISE, lambda y, x: (x, 1.0 - y)),
        ]:
            rk = _run_movenet_raw(landmarker, cv2.rotate(bgr_frame, rot_code))
            rs = float(max(rk[0, 2], (rk[5, 2] + rk[6, 2]) / 2.0))
            if rs > best_score:
                mapped = rk.copy()
                for i in range(17):
                    ny, nx = unmap(rk[i, 0], rk[i, 1])
                    mapped[i, 0], mapped[i, 1] = ny, nx
                best, best_score = mapped, rs

    if best_score < 0.18:
        return None
    return _movenet_kpts_to_33(best)


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
        if visibility(landmarks[a]) > 0.18 and visibility(landmarks[b]) > 0.18:
            cv2.line(bgr_frame, points[a], points[b], (255, 255, 255), 2)
    for i in {i for pair in CONNECTIONS for i in pair} | {NOSE}:
        if visibility(landmarks[i]) > 0.18:
            cv2.circle(bgr_frame, points[i], 4, (0, 0, 255), -1)
