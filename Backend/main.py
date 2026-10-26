#Start of the code for the main backend
import os
import sys

_venv_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv")
_venv_py = os.path.join(_venv_dir, "bin", "python")
if os.path.exists(_venv_py) and os.path.abspath(sys.prefix) != os.path.abspath(_venv_dir):
    os.execv(_venv_py, [_venv_py] + sys.argv)

#Imports that are going to be used listed below, rember to credit them for vid
from fastapi import FastAPI, File, UploadFile, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import cv2
import numpy as np
import pose_utils
import json
import asyncio
from typing import List, Optional
from datetime import datetime
import base64
from pathlib import Path
import sys
import os
import threading
import time
import subprocess
from contextlib import asynccontextmanager
#DEVIN HELP FOR WHICH API'S I USED
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import autonomous_controller
from autonomous_controller import AutonomousController, MotorDriver

ON_PI = autonomous_controller.GPIO_AVAILABLE

try:
    from twilio.rest import Client as TwilioClient
except ImportError:
    TwilioClient = None

stop_event = threading.Event()
#This is due tomorrow so review the code again(side note) also make sure 
#Git works bc you js started using it, and didn't know prior to use it
#So majority of code isn't commited, or shown on commits so u can't check on git
#Iniziation of Camera
@asynccontextmanager
async def lifespan(app):
    load_contacts_from_file()
    load_fall_history_from_file()
    if os.getenv("ROBOT_CAMERA", "on" if ON_PI else "off").lower() == "on":
        threading.Thread(target=robot_camera_loop, daemon=True).start()
    else:
        print("Robot camera loop off (set ROBOT_CAMERA=on to enable)")
    yield
    stop_event.set()
    robot.stop()

#The app title of the backend 
app = FastAPI(title="SlipLert Backend", lifespan=lifespan)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MediaPipe Pose initialization~USED FOR THE POSE DETECTION THROUGH THE CAMERA OF THE PI
pose = pose_utils.create_landmarker(video=False, complexity=1)

# Global state~help from devin
emergency_contacts = []
fall_history = []
robot_position = {"x": 0, "y": 0, "angle": 0}
camera = None
is_autonomous = os.getenv("AUTONOMOUS_ON_START", "on").lower() == "on"
autonomous_epoch = 0  # bumped whenever the user takes control, cancels a pending auto-resume
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
CONTACTS_FILE = os.path.join(BACKEND_DIR, "emergency_contacts.json")
FALL_HISTORY_FILE = os.path.join(BACKEND_DIR, "fall_history.json")

if sys.platform.startswith("linux"):
    try:
        my_pid = os.getpid()
        if not os.getenv("INVOCATION_ID"):
            subprocess.run(["sudo", "-n", "systemctl", "stop", "sliplert"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        out = subprocess.check_output(["pgrep", "-f", "main.py"], text=True)
        for line in out.splitlines():
            pid = int(line.strip())
            if pid != my_pid:
                os.kill(pid, 9)
        time.sleep(0.5)
    except Exception:
        pass

# Motors: all wiring/polarity settings live in MotorDriver (see autonomous_controller.py and .env)
robot = MotorDriver()
GPIO_AVAILABLE = robot.available



class FallDetector:#DECTION OF FALLS CALCULATIONS OF POSITION, THIS WAS HELPED THROUGH DEVIN
    def __init__(self):
        self.previous_positions = []
        self.position_history_limit = 10
        self.fall_threshold = 0.7  # Threshold for fall detection
        self.velocity_threshold = 2.0  # Velocity threshold for fast falls

    def analyze_pose(self, landmarks):
        """Analyze pose landmarks to detect falls"""
        try:
            # Extract key landmarks
            nose = landmarks[pose_utils.NOSE]
            left_shoulder = landmarks[pose_utils.LEFT_SHOULDER]
            right_shoulder = landmarks[pose_utils.RIGHT_SHOULDER]
            left_hip = landmarks[pose_utils.LEFT_HIP]
            right_hip = landmarks[pose_utils.RIGHT_HIP]
            left_ankle = landmarks[pose_utils.LEFT_ANKLE]
            right_ankle = landmarks[pose_utils.RIGHT_ANKLE]

            # Calculate center points
            shoulder_center = self._get_midpoint(left_shoulder, right_shoulder)
            hip_center = self._get_midpoint(left_hip, right_hip)
            ankle_center = self._get_midpoint(left_ankle, right_ankle)

            shoulders_visible = pose_utils.visibility(left_shoulder) > 0.3 and pose_utils.visibility(right_shoulder) > 0.3
            hips_visible = shoulders_visible and pose_utils.visibility(left_hip) > 0.45 and pose_utils.visibility(right_hip) > 0.45
            ankles_visible = pose_utils.visibility(left_ankle) > 0.45 and pose_utils.visibility(right_ankle) > 0.45
            if not shoulders_visible:
                # Low-confidence shoulder points are guesses; their angles/heights would cause false alarms
                self.previous_positions.clear()
                return {"is_fall": False, "fall_type": None, "body_angle": 0.0,
                        "vertical_alignment": 0.0, "velocity": 0.0, "confidence": 0.0}

            # Calculate vertical alignment (shoulder to hip to ankle)
            vertical_alignment = self._calculate_vertical_alignment(shoulder_center, hip_center, ankle_center)

            # Calculate true body tilt angle (torso tilt when hips visible, or shoulder tilt when close to camera)
            torso_angle = self._calculate_body_angle(shoulder_center, hip_center) if hips_visible else 0.0
            shoulder_dx = abs(left_shoulder.x - right_shoulder.x)
            shoulder_dy = abs(left_shoulder.y - right_shoulder.y)
            shoulder_tilt = float(np.degrees(np.arctan2(shoulder_dy, max(shoulder_dx, 1e-4))))
            body_angle = float(min(90.0, max(torso_angle, shoulder_tilt)))

            head_y = (nose.y + shoulder_center["y"]) / 2.0

            # Store position for velocity calculation
            current_position = {
                "timestamp": datetime.now().isoformat(),
                "y": head_y,
                "vertical_alignment": vertical_alignment,
                "body_angle": body_angle
            }
            self.previous_positions.append(current_position)
            if len(self.previous_positions) > self.position_history_limit:
                self.previous_positions.pop(0)

            # Calculate downward velocity and recent drop
            velocity = 0.0
            downward_velocity = 0.0
            recent_drop = 0.0
            if len(self.previous_positions) >= 2:
                velocity = self._calculate_velocity()
                downward_velocity = self._calculate_downward_velocity()
                recent_drop = head_y - min(p["y"] for p in self.previous_positions)

            # Fall detection logic: only flag real falls (not normal sitting or turning head)
            is_fall = False
            fall_type = None

            # Whole-body cues for a person lying with their head mid-frame (hips/feet seen less confidently)
            loose_hips = [h for h in (left_hip, right_hip) if pose_utils.visibility(h) > 0.25]
            loose_torso = self._calculate_body_angle(shoulder_center, {"x": sum(h.x for h in loose_hips) / len(loose_hips),
                                                                       "y": sum(h.y for h in loose_hips) / len(loose_hips)}) if loose_hips else 0.0
            feet = [p for p in (left_ankle, right_ankle, landmarks[pose_utils.LEFT_KNEE], landmarks[pose_utils.RIGHT_KNEE])
                    if pose_utils.visibility(p) > 0.25]
            body_axis = self._calculate_body_angle(shoulder_center, {"x": sum(p.x for p in feet) / len(feet),
                                                                     "y": sum(p.y for p in feet) / len(feet)}) if feet else 0.0
            lying_cue = nose.y > 0.45 or loose_torso > 55 or body_axis > 60

            # Check Number 1: Torso tilted > 55 deg OR shoulders tipped > 45 deg sideways (with the body lying, not a head tilt)
            if (hips_visible and torso_angle > 55) or (shoulder_tilt > 45 and lying_cue):
                is_fall = True
                fall_type = "horizontal"
                body_angle = max(body_angle, 70.0)

            # Check Number 2: Big/fast downward drop — counts even if the person
            # doesn't end fully flat (collapsed to knees, slumped forward, etc.)
            elif (downward_velocity > 0.45 and recent_drop > 0.22) or \
               (downward_velocity > 0.55 and recent_drop > 0.24 and head_y > 0.62) or \
               (recent_drop > 0.30 and downward_velocity > 0.20):
                is_fall = True
                fall_type = "fast_fall"
                body_angle = max(body_angle, 75.0)

            # Check NUMBER 3: Sudden change in full-body vertical alignment
            elif ankles_visible and hips_visible and len(self.previous_positions) >= 5:
                recent_alignment = [p["vertical_alignment"] for p in self.previous_positions[-5:]]
                if max(recent_alignment) - min(recent_alignment) > 0.55 and torso_angle > 45:
                    is_fall = True
                    fall_type = "sudden_alignment_change"

            return {
                "is_fall": is_fall,
                "fall_type": fall_type,
                "body_angle": body_angle,
                "vertical_alignment": vertical_alignment,
                "velocity": velocity,
                "confidence": 0.95 if is_fall else 0.85
            }
#calculation help from devin
        except Exception as e:
            print(f"Error analyzing pose: {e}")
            return {"is_fall": False, "error": str(e)}

    def _get_midpoint(self, point1, point2):
        return {"x": (point1.x + point2.x) / 2, "y": (point1.y + point2.y) / 2}

    def _calculate_vertical_alignment(self, shoulder, hip, ankle):
        """Calculate how well aligned the body is vertically (0 = perfect, 1 = completely horizontal)"""
        # Simple calculation: horizontal distance between shoulder and ankle relative to vertical distance
        horizontal_dist = abs(shoulder["x"] - ankle["x"])
        vertical_dist = abs(shoulder["y"] - ankle["y"])
        if vertical_dist == 0:
            return 1.0
        return horizontal_dist / vertical_dist

    def _calculate_body_angle(self, shoulder, hip):
        """Calculate the angle of the body from vertical (0 = upright, 90 = horizontal)"""
        dx = shoulder["x"] - hip["x"]
        dy = shoulder["y"] - hip["y"]
        angle = np.degrees(np.arctan2(abs(dx), abs(dy)))
        return angle

    def _calculate_velocity(self):
        """Calculate downward velocity based on recent positions"""
        if len(self.previous_positions) < 2:
            return 0

        recent = self.previous_positions[-2:]
        time_diff = (datetime.fromisoformat(recent[1]["timestamp"]) -
                    datetime.fromisoformat(recent[0]["timestamp"])).total_seconds()
        if time_diff == 0:
            return 0

        y_diff = recent[1]["y"] - recent[0]["y"]
        velocity = abs(y_diff / time_diff)
        return velocity

    def _calculate_downward_velocity(self):
        if len(self.previous_positions) < 2:
            return 0.0
        recent = self.previous_positions[-2:]
        time_diff = (datetime.fromisoformat(recent[1]["timestamp"]) -
                    datetime.fromisoformat(recent[0]["timestamp"])).total_seconds()
        if time_diff <= 0:
            return 0.0
        return (recent[1]["y"] - recent[0]["y"]) / time_diff

fall_detector = FallDetector()

follower = AutonomousController(robot=robot, create_hardware=False)
if is_autonomous:
    follower.start()
camera_state = {"running": False, "person_detected": False, "fps": 0.0, "body_angle": 0.0, "posture_score": 98, "last_fall": None, "error": None}
latest_jpeg = None
frame_lock = threading.Lock()
camera_loop_lock = threading.Lock()
TORSO_LANDMARKS = [
    pose_utils.NOSE,
    pose_utils.LEFT_SHOULDER,
    pose_utils.RIGHT_SHOULDER,
]

SYSTEM_PACKAGE_DIRS = ("/usr/lib/python3/dist-packages", f"/usr/lib/python3.{sys.version_info.minor}/dist-packages")


def _import_picamera2():
    """picamera2 (the only way to use the ribbon camera on a Pi 5) is installed by Raspberry Pi OS as a
    system package, which a plain .venv can't see. If the venv doesn't have it, use the system copy."""
    try:
        from picamera2 import Picamera2
        return Picamera2
    except ImportError:
        if not sys.platform.startswith("linux"):
            raise
    added = [d for d in SYSTEM_PACKAGE_DIRS if os.path.isdir(d) and d not in sys.path]
    sys.path.extend(added)  # appended last, so the venv's own packages still win
    try:
        from picamera2 import Picamera2
        print("Loaded picamera2 from the Raspberry Pi system packages")
        return Picamera2
    except ImportError as e:
        raise ImportError(f"{e} -> run: sudo apt install -y python3-picamera2  (or run setup_pi.sh)") from e


#camera instilization
def open_camera():
    try:
        Picamera2 = _import_picamera2()
        picam = Picamera2()
        cfg = picam.create_preview_configuration(
            main={"size": (640, 480), "format": "RGB888"},
            raw=None,
            buffer_count=2,
        )
        picam.configure(cfg)
        picam.start()

        first_frame = [None]
        def _grab_one():
            try:
                first_frame[0] = picam.capture_array()
            except Exception:
                pass
        probe = threading.Thread(target=_grab_one, daemon=True)
        probe.start()
        probe.join(timeout=6.0)  # the Pi 5 camera can take a few seconds to deliver its first frame
        if first_frame[0] is None:
            try:
                picam.stop()
                picam.close()
            except Exception:
                pass
            raise RuntimeError("Pi camera did not return a frame (check ribbon cable or reboot Pi)")

        def _close_picam():
            try:
                picam.stop()
                picam.close()
            except Exception:
                pass

        print("Using Raspberry Pi camera (picamera2)")
        # picamera2's "RGB888" frames are already stored in B,G,R order - exactly what OpenCV expects
        return picam.capture_array, _close_picam
    except Exception as e:
        print(f"Pi camera (picamera2) not available ({e}) - trying USB/OpenCV camera")

    cap = cv2.VideoCapture(int(os.getenv("CAMERA_INDEX", 0)))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    if not cap.isOpened():
        print("No USB/OpenCV camera found either")
        return None, None
    cv_frame = [None]
    def _grab_cv():
        try:
            ok, fr = cap.read()
            if ok and fr is not None:
                cv_frame[0] = fr
        except Exception:
            pass
    cv_probe = threading.Thread(target=_grab_cv, daemon=True)
    cv_probe.start()
    cv_probe.join(timeout=2.5)
    if cv_frame[0] is None:
        try:
            cap.release()
        except Exception:
            pass
        print("OpenCV camera opened but returned no frames")
        return None, None
    print("Using OpenCV camera")
    return (lambda: cap.read()[1]), cap.release

#the camera constantly is running and checking for the condtiions and if it is connected
def robot_camera_loop():
    global latest_jpeg
    if not camera_loop_lock.acquire(timeout=3.0):  # wait for a stopping loop to release the camera
        return
    try:
        read_frame, release = open_camera()
        while not read_frame and not stop_event.is_set():
            # Never drive without eyes: keep the motors stopped and retry the camera
            camera_state["error"] = "No camera frames - check the ribbon cable / USB camera. Retrying every 5s."
            print(camera_state["error"])
            robot.stop()
            stop_event.wait(5.0)
            if not stop_event.is_set():
                read_frame, release = open_camera()
        if not read_frame:
            return
        camera_state["error"] = None

        loop_pose = pose_utils.create_landmarker(video=True, complexity=int(os.getenv("POSE_MODEL_COMPLEXITY", 0)))
        loop_detector = FallDetector()
        timestamp_ms = 0
        confirm_frames = int(os.getenv("FALL_CONFIRM_FRAMES", 3))
        fall_streak = 0
        last_tick = time.time()
        camera_state["running"] = True
        print("Robot camera loop running")

        try:
            while not stop_event.is_set():
                frame = read_frame()
                if frame is None:
                    follower.lose_person()
                    time.sleep(0.05)
                    continue

                timestamp_ms = max(timestamp_ms + 1, int(time.monotonic() * 1000))
                landmarks = pose_utils.detect_landmarks(loop_pose, frame, timestamp_ms)
                visible = landmarks is not None and any(pose_utils.visibility(landmarks[i]) > 0.18 for i in TORSO_LANDMARKS)
                body_visible = landmarks is not None and follower.has_body(landmarks)
                camera_state["person_detected"] = visible or body_visible
                camera_state["running"] = True

                fall_confirmed = False
                if visible:
                    analysis = loop_detector.analyze_pose(landmarks)
                    angle = float(analysis.get("body_angle", 0.0))
                    camera_state["body_angle"] = round(angle, 1)
                    camera_state["posture_score"] = max(0, min(100, int(round(100 - angle))))
                    fall_streak = fall_streak + 1 if analysis.get("is_fall") else 0
                    if fall_streak >= confirm_frames:
                        fall_streak = 0
                        fall_confirmed = True
                        record = {
                            "timestamp": datetime.now().isoformat(),
                            "fall_type": analysis["fall_type"],
                            "body_angle": analysis["body_angle"],
                            "confidence": analysis["confidence"],
                            "source": "robot_camera"
                        }#CHECKS FOR FALL IF SO THERE IS AN ALERT
                        # Only a fall that actually sent an alert is shown on the dashboard
                        # (during the cooldown the person is still on the floor; don't spam "email sent")
                        if send_emergency_alert(record):
                            camera_state["last_fall"] = record
                            fall_history.append(record)
                            save_fall_history_to_file()
                else:
                    fall_streak = 0

                if is_autonomous and not fall_confirmed:
                    follower.is_running = True
                    if body_visible:
                        follower.follow_landmarks(landmarks)
                    else:
                        follower.search_last_direction()
                camera_state["follow_state"] = follower.state if is_autonomous else "paused"

                if landmarks:
                    pose_utils.draw_landmarks(frame, landmarks)
                ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ok:
                    with frame_lock:
                        latest_jpeg = buf.tobytes()

                now = time.time()
                camera_state["fps"] = round(1 / (now - last_tick), 1) if now > last_tick else 0.0
                last_tick = now
        finally:
            camera_state["running"] = False
            follower.stop()
            release()
    finally:
        camera_loop_lock.release()
#STORAGE OF THE EMERGANCY CONTACTS
def load_contacts_from_file():
    global emergency_contacts
    try:
        if os.path.exists(CONTACTS_FILE):
            with open(CONTACTS_FILE, 'r') as f:
                emergency_contacts = json.load(f)
            print(f"Loaded {len(emergency_contacts)} contacts from file")
    except Exception as e:
        print(f"Error loading contacts: {e}")
        emergency_contacts = []
#SAVING THE CONTACTS YOU INPUT IN THE SETTINGS TAB
def save_contacts_to_file():
    try:
        with open(CONTACTS_FILE, 'w') as f:
            json.dump(emergency_contacts, f, indent=2)
        print(f"Saved {len(emergency_contacts)} contacts to file")
    except Exception as e:
        print(f"Error saving contacts: {e}")
#STORTES WHEN YOUR LOVED ONES FELL PRIOR
def load_fall_history_from_file():
    global fall_history
    try:
        if os.path.exists(FALL_HISTORY_FILE):
            with open(FALL_HISTORY_FILE, 'r') as f:
                fall_history = json.load(f)
            print(f"Loaded {len(fall_history)} fall records from file")
    except Exception as e:
        print(f"Error loading fall history: {e}")
        fall_history = []

def save_fall_history_to_file():
    try:
        with open(FALL_HISTORY_FILE, 'w') as f:
            json.dump(fall_history, f, indent=2)
    except Exception as e:
        print(f"Error saving fall history: {e}")

# API Routes
#HELP FROM DEVIN
@app.get("/")
async def root():
    load_contacts_from_file()
    load_fall_history_from_file()
    return {"message": "SlipLert Backend API", "status": "running", "gpio_available": GPIO_AVAILABLE}

@app.post("/detect-fall")
async def detect_fall(file: UploadFile = File(...)):
    """Detect fall from uploaded image"""
    try:
        # Read image
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image")

        # Convert to RGB for MediaPipe
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # Process with MediaPipe
        landmarks = pose_utils.detect_landmarks(pose, img)

        if landmarks:
            analysis = fall_detector.analyze_pose(landmarks)

            if analysis["is_fall"]:
                # Log the fall
                fall_record = {
                    "timestamp": datetime.now().isoformat(),
                    "fall_type": analysis["fall_type"],
                    "body_angle": analysis["body_angle"],
                    "confidence": analysis["confidence"]
                }
                # Trigger emergency alert (one record per alert, not one per frame during the cooldown)
                if await trigger_emergency_alert(fall_record):
                    fall_history.append(fall_record)
                    save_fall_history_to_file()

            return {
                "fall_detected": analysis["is_fall"],
                "fall_type": analysis["fall_type"],
                "body_angle": analysis["body_angle"],
                "vertical_alignment": analysis["vertical_alignment"],
                "velocity": analysis["velocity"],
                "confidence": analysis["confidence"],
                "called_contacts": fall_record.get("called_contacts", []) if analysis["is_fall"] else [],
                "called_phones": fall_record.get("called_phones", []) if analysis["is_fall"] else [],
            }
        else:
            return {"fall_detected": False, "message": "No pose detected"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/detect-fall-base64")
async def detect_fall_base64(data: dict):
    """Detect fall from base64 encoded image"""
    try:
        incoming_contacts = data.get("contacts")
        if isinstance(incoming_contacts, list) and len(incoming_contacts) > 0:
            load_contacts_from_file()
            existing_phones = {_contact_key(c.get("phone", "")) for c in emergency_contacts}
            added_any = False
            for c in incoming_contacts:
                if isinstance(c, dict) and c.get("name") and c.get("phone"):
                    p = _contact_key(c["phone"])
                    if p not in existing_phones:
                        emergency_contacts.append({
                            "id": max((x["id"] for x in emergency_contacts), default=0) + 1,
                            "name": c["name"],
                            "phone": c["phone"],
                            "relationship": c.get("relationship", "Emergency Contact"),
                            "created_at": datetime.now().isoformat(),
                        })
                        existing_phones.add(p)
                        added_any = True
            if added_any:
                save_contacts_to_file()

        if data.get("coordinates") or data.get("simulate"):
            fall_record = {
                "timestamp": datetime.now().isoformat(),
                "fall_type": "simulated_fall",
                "body_angle": 82.0,
                "confidence": 0.98
            }
            camera_state["body_angle"] = 82.0
            camera_state["posture_score"] = 18
            fall_history.append(fall_record)
            # A test button press always sends, even inside the normal alert cooldown
            await trigger_emergency_alert(fall_record, force=True)
            camera_state["last_fall"] = fall_record
            save_fall_history_to_file()
            return {
                "timestamp": fall_record["timestamp"],
                "fall_detected": True,
                "fall_type": "simulated_fall",
                "body_angle": 82.0,
                "vertical_alignment": 0.9,
                "velocity": 2.4,
                "confidence": 0.98,
                "called_contacts": fall_record.get("called_contacts", []),
                "called_phones": fall_record.get("called_phones", []),
                "delivery": fall_record.get("delivery", []),
            }

        image_data = data.get("image")
        if not image_data:
            raise HTTPException(status_code=400, detail="No image data provided")

        # Decode base64
        if "," in image_data:
            image_data = image_data.split(",")[1]
        img_bytes = base64.b64decode(image_data)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image")

        # Convert to RGB for MediaPipe-this was hard so help from devin
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # Process with MediaPipe
        landmarks = pose_utils.detect_landmarks(pose, img)

        if landmarks:
            analysis = fall_detector.analyze_pose(landmarks)

            if analysis["is_fall"]:
                fall_record = {
                    "timestamp": datetime.now().isoformat(),
                    "fall_type": analysis["fall_type"],
                    "body_angle": analysis["body_angle"],
                    "confidence": analysis["confidence"]
                }
                if await trigger_emergency_alert(fall_record):
                    fall_history.append(fall_record)
                    save_fall_history_to_file()

            return {
                "fall_detected": analysis["is_fall"],
                "fall_type": analysis["fall_type"],
                "body_angle": analysis["body_angle"],
                "vertical_alignment": analysis["vertical_alignment"],
                "velocity": analysis["velocity"],
                "confidence": analysis["confidence"],
                "called_contacts": fall_record.get("called_contacts", []) if analysis["is_fall"] else [],
                "called_phones": fall_record.get("called_phones", []) if analysis["is_fall"] else [],
            }
        else:
            return {"fall_detected": False, "message": "No pose detected"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Emergency Contact Management

@app.post("/emergency-contacts")
async def add_emergency_contact(contact: dict):
    """Add an emergency contact"""
    required_fields = ["name", "phone", "relationship"]
    for field in required_fields:
        if field not in contact:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    load_contacts_from_file()
    contact["phone"] = str(contact["phone"]).strip()
    for existing in emergency_contacts:
        if _contact_key(existing.get("phone", "")) == _contact_key(contact["phone"]):
            return {"message": "Contact already saved", "contact": existing}
    contact["id"] = max((c["id"] for c in emergency_contacts), default=0) + 1
    contact["created_at"] = datetime.now().isoformat()
    emergency_contacts.append(contact)
    save_contacts_to_file()
    return {"message": "Contact added successfully", "contact": contact}

@app.get("/emergency-contacts")#THis takes the input you put in and returns the words contacts: then the varible of what number you put
async def get_emergency_contacts():
    """Get all emergency contacts"""
    load_contacts_from_file()
    return {"contacts": emergency_contacts}
#Delete function of removing contacts to be called
@app.delete("/emergency-contacts/{contact_id}")
async def delete_emergency_contact(contact_id: int):
    """Delete an emergency contact"""
    global emergency_contacts
    load_contacts_from_file()
    emergency_contacts = [c for c in emergency_contacts if c["id"] != contact_id]
    save_contacts_to_file()
    return {"message": "Contact deleted successfully"}

ALERT_COOLDOWN_SECONDS = float(os.getenv("ALERT_COOLDOWN_SECONDS", 60))
last_alert_time = 0.0
alert_lock = threading.Lock()


def get_twilio_client():
    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    if TwilioClient and sid.startswith("AC") and token and os.getenv("TWILIO_PHONE_NUMBER"):
        return TwilioClient(sid, token)
    return None


def _normalize_phone(phone: str) -> str:
    digits = "".join(ch for ch in str(phone) if ch.isdigit() or ch == "+")
    if not digits:
        return str(phone).strip()
    if not digits.startswith("+"):
        if len(digits) == 10:
            return "+1" + digits
        if len(digits) == 11 and digits.startswith("1"):
            return "+" + digits
    return digits


def _contact_key(target: str) -> str:
    """Same person/address no matter how it was typed (emails ignore case, phones ignore formatting)."""
    target = str(target).strip()
    return target.lower() if "@" in target else _normalize_phone(target)


def _lookup_mx_hosts(domain: str) -> list:
    """Look up MX records for a domain; auto-installs dnspython if needed."""
    try:
        import dns.resolver
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "dnspython"], check=False)
        try:
            import dns.resolver
        except ImportError:
            return []
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=6)
        hosts = sorted([(int(r.preference), str(r.exchange).rstrip(".")) for r in answers])
        return [h for _, h in hosts]
    except Exception:
        return []


def _send_direct_mx_email(recipient: str, subject: str, body: str) -> bool:
    """Deliver mail straight to the recipient's mail server — no account or activation needed.
    NOTE: many home internet providers block port 25, and Gmail/Outlook often reject or spam-folder
    mail from a home IP. Set SMTP_EMAIL + SMTP_PASSWORD in .env for reliable delivery."""
    import smtplib
    from email.message import EmailMessage
    domain = recipient.split("@")[-1].strip().lower()
    mx_hosts = _lookup_mx_hosts(domain)
    if not mx_hosts:
        # Common-provider MX guesses when DNS lookup is unavailable
        guesses = {
            "gmail.com": "gmail-smtp-in.l.google.com",
            "googlemail.com": "gmail-smtp-in.l.google.com",
            "yahoo.com": "mta5.am0.yahoodns.net",
            "icloud.com": "mx01.mail.icloud.com",
            "me.com": "mx01.mail.icloud.com",
            "outlook.com": "outlook-com.olc.protection.outlook.com",
            "hotmail.com": "hotmail-com.olc.protection.outlook.com",
        }
        mx_hosts = [guesses[domain]] if domain in guesses else [f"mail.{domain}", domain]
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.getenv("ALERT_FROM_EMAIL", "alerts@sliplert.local")
    msg["To"] = recipient
    msg.set_content(body)
    for host in mx_hosts[:3]:
        try:
            with smtplib.SMTP(host, 25, timeout=8) as s:
                s.ehlo()
                if s.has_extn("starttls"):
                    s.starttls()
                    s.ehlo()
                s.send_message(msg)
            print(f"Emergency email delivered directly to {recipient} via {host}")
            return True
        except Exception as e:
            print(f"Direct MX delivery via {host} failed: {e}")
    return False


def _send_emergency_email(recipient: str, name: str, fall_record: dict):
    """Returns (delivered, method, error)."""
    subject = "URGENT: SlipLert Fall Detected - Check on Your Loved One"
    body = (
        f"Hello {name},\n\n"
        f"Your loved one has fallen — please check on them immediately.\n\n"
        f"- Time: {fall_record.get('timestamp')}\n"
        f"- Fall Type: {fall_record.get('fall_type')}\n"
        f"- Body Angle: {fall_record.get('body_angle', 0):.1f} deg\n"
        f"- Robot: stopped safely next to them\n\n"
        f"- SlipLert Autonomous Safety Monitor"
    )
    errors = []
    smtp_user = os.getenv("SMTP_EMAIL", "").strip()
    smtp_pass = os.getenv("SMTP_PASSWORD", "").strip().replace(" ", "")
    if smtp_user and smtp_pass:
        try:
            import smtplib
            from email.message import EmailMessage
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = smtp_user
            msg["To"] = recipient
            msg.set_content(body)
            host = os.getenv("SMTP_HOST", "smtp.gmail.com")
            port = int(os.getenv("SMTP_PORT", 465))
            if port == 587:
                with smtplib.SMTP(host, port, timeout=10) as s:
                    s.starttls()
                    s.login(smtp_user, smtp_pass)
                    s.send_message(msg)
            else:
                with smtplib.SMTP_SSL(host, port, timeout=10) as s:
                    s.login(smtp_user, smtp_pass)
                    s.send_message(msg)
            print(f"Sent emergency email via SMTP to {name} <{recipient}>")
            return True, "smtp", None
        except Exception as e:
            print(f"SMTP email error: {e}")
            errors.append(f"SMTP: {e}")

    if _send_direct_mx_email(recipient, subject, body):
        return True, "direct_mx", None
    errors.append("direct MX delivery failed (port 25 blocked or rejected)")

    try:
        import urllib.request
        payload = json.dumps({
            "_subject": subject,
            "name": "SlipLert Autonomous Safety Monitor",
            "recipient": name,
            "fall_type": str(fall_record.get("fall_type")),
            "timestamp": str(fall_record.get("timestamp")),
            "message": body,
        }).encode("utf-8")
        import urllib.parse
        # FormSubmit rejects requests that don't come from a web page ("open this page through a web
        # server"), so send the same Origin/Referer the dashboard's browser would send.
        origin = os.getenv("FORMSUBMIT_ORIGIN", "http://localhost:3000")
        req = urllib.request.Request(
            f"https://formsubmit.co/ajax/{urllib.parse.quote(recipient.strip())}",
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "SlipLert/1.0",
                     "Origin": origin, "Referer": f"{origin}/dashboard"},
            method="POST",
        )
        # FormSubmit can take over a minute to answer; this runs in a background thread so waiting is fine
        with urllib.request.urlopen(req, timeout=90) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            if res.get("success") in (True, "true"):
                print(f"Sent emergency email to {name} <{recipient}> via FormSubmit")
                return True, "formsubmit", None
            errors.append(f"FormSubmit: {res.get('message', res)}")
    except Exception as e:
        errors.append(f"FormSubmit: {e}")
    print(f"EMAIL NOT DELIVERED to {name} <{recipient}>: {'; '.join(errors)}")
    return False, "none", "; ".join(errors)


def _send_fallback_sms(phone: str, message: str) -> bool:
    try:
        import urllib.parse
        import urllib.request
        payload = urllib.parse.urlencode({
            "phone": phone,
            "message": message,
            "key": os.getenv("TEXTBELT_API_KEY", "textbelt"),
        }).encode("utf-8")
        req = urllib.request.Request("https://textbelt.com/text", data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=8) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return bool(result.get("success"))
    except Exception as e:
        print(f"SMS gateway fallback error: {e}")
        return False


def _deliver_alerts(fall_record: dict, contacts: list):
    """Runs in a background thread so the camera loop (and the robot) never freeze while emails send.
    Results land in fall_record["delivery"], which the dashboard reads from /robot/status."""
    client = get_twilio_client()
    from_number = os.getenv("TWILIO_PHONE_NUMBER")
    message = "SlipLert Emergency Alert: A fall has been detected. Please check on your loved one immediately."
    for entry, contact in zip(fall_record["delivery"], contacts):
        target = entry["to"]
        try:
            if "@" in target:
                ok, method, err = _send_emergency_email(target, contact["name"], fall_record)
            elif client:
                client.calls.create(
                    to=target,
                    from_=from_number,
                    twiml=f'<Response><Say loop="2">{message}</Say></Response>'
                )
                client.messages.create(to=target, from_=from_number, body=f"{message} Time: {fall_record['timestamp']}")
                print(f"Called and texted {contact['name']} ({target})")
                ok, method, err = True, "twilio", None
            else:
                ok = _send_fallback_sms(target, f"{message} Time: {fall_record['timestamp']}")
                method = "textbelt"
                err = None if ok else "free SMS quota used up - add an email contact or Twilio keys"
                print(f"{'Sent' if ok else 'FAILED to send'} emergency SMS to {contact['name']} ({target})")
        except Exception as e:
            ok, method, err = False, "error", str(e)
            print(f"Failed to alert {contact['name']} ({target}): {e}")
        entry.update({"status": "sent" if ok else "failed", "method": method, "error": err})
    save_fall_history_to_file()


def send_emergency_alert(fall_record: dict, force: bool = False) -> bool:
    global last_alert_time, is_autonomous
    load_contacts_from_file()
    contacts = list(emergency_contacts)
    with alert_lock:
        now = time.time()
        if not force and now - last_alert_time < ALERT_COOLDOWN_SECONDS:
            return False
        last_alert_time = now

    print(f"EMERGENCY ALERT: Fall detected at {fall_record['timestamp']}")
    print(f"Fall type: {fall_record['fall_type']}")
    print(f"Body angle: {fall_record['body_angle']:.2f}°")

    was_autonomous = is_autonomous
    is_autonomous = False
    follower.stop()
#prints if a fall occured
    targets = []
    for contact in contacts:
        raw_target = str(contact["phone"]).strip()
        targets.append(raw_target if "@" in raw_target else _normalize_phone(raw_target))
    fall_record["called_contacts"] = [
        f"{c['name']} <{t}>" if "@" in t else f"{c['name']} ({t})" for c, t in zip(contacts, targets)
    ]
    fall_record["called_phones"] = targets
    fall_record["delivery"] = [{"name": c["name"], "to": t, "status": "sending"} for c, t in zip(contacts, targets)]
    if not contacts:
        print("No emergency contacts saved, nobody to call")
    threading.Thread(target=_deliver_alerts, args=(fall_record, contacts), daemon=True).start()

    if was_autonomous:
        epoch = autonomous_epoch
        def _resume_autonomous():
            global is_autonomous
            time.sleep(7.0)
            if autonomous_epoch == epoch:  # user did not take manual control in the meantime
                is_autonomous = True
                follower.start()
                print("Resumed autonomous following after emergency dispatch")
        threading.Thread(target=_resume_autonomous, daemon=True).start()

    return True


async def trigger_emergency_alert(fall_record: dict, force: bool = False) -> bool:
    """Trigger emergency alert - call all contacts"""
    return await asyncio.to_thread(send_emergency_alert, fall_record, force)

# Robot Control...

# Dashboard buttons -> logical moves. The dashboard's "▲ Backward" button sends "forward" and "▼ Forward"
# sends "backward" (named after the old raw motor calls on this reversed-wiring car), so they swap here.
MANUAL_ACTIONS = {"forward": "backward", "backward": "forward", "left": "spin_left", "right": "spin_right", "stop": "stop"}


def _start_camera_loop():
    if not camera_state["running"]:
        stop_event.clear()
        threading.Thread(target=robot_camera_loop, daemon=True).start()


@app.post("/robot/control")
async def control_robot(command: dict):
    """Manual drive. Without a `duration` the car keeps moving until a "stop" command (what the
    dashboard buttons expect); with one, it stops by itself after that many seconds."""
    global is_autonomous, autonomous_epoch
    action = command.get("action")
    if action not in MANUAL_ACTIONS:
        raise HTTPException(status_code=400, detail="Invalid action")

    is_autonomous = False
    autonomous_epoch += 1
    follower.is_running = False

    duration = None
    if command.get("duration") is not None:
        try:
            duration = min(5.0, max(0.1, float(command["duration"])))
        except (TypeError, ValueError):
            duration = None
    robot.drive(MANUAL_ACTIONS[action], duration)
    if not robot.available:
        return {"message": f"Robot not available: {robot.error}", "status": "simulation"}
    print(f"[MOTOR] Manual command: {action} -> {MANUAL_ACTIONS[action]}" + (f" for {duration:.1f}s" if duration else " until stop"))
    return {"message": f"Robot {action} executed", "status": "success"}

@app.post("/robot/autonomous")
async def toggle_autonomous(settings: dict):
    """Toggle autonomous mode"""
    global is_autonomous, autonomous_epoch
    is_autonomous = bool(settings.get("enabled", False))
    autonomous_epoch += 1
    if is_autonomous:
        # Don't move yet - the camera loop starts driving once it actually sees the person
        follower.start()
        _start_camera_loop()
    else:
        follower.stop()
    message = f"Autonomous mode {'enabled' if is_autonomous else 'disabled'}"
    return {"message": message, "status": is_autonomous}

@app.post("/robot/camera")
async def toggle_robot_camera(settings: dict):
    global is_autonomous, latest_jpeg, autonomous_epoch
    enable = bool(settings.get("enabled", True))
    autonomous_epoch += 1
    if enable:
        if settings.get("autonomous", True):
            is_autonomous = True
            follower.start()
        if not camera_state["running"]:
            _start_camera_loop()
            await asyncio.sleep(0.6)
        return {"message": "Robot camera started", "camera_running": camera_state["running"], "autonomous": is_autonomous}
    is_autonomous = False
    follower.stop()
    stop_event.set()
    for _ in range(15):
        if not camera_state["running"]:
            break
        await asyncio.sleep(0.1)
    with frame_lock:
        latest_jpeg = None
    camera_state["person_detected"] = False
    camera_state["fps"] = 0.0
    return {"message": "Robot camera stopped", "camera_running": False}

@app.get("/robot/status")
async def get_robot_status():
    """Get robot status"""
    return {
        "position": robot_position,
        "autonomous": is_autonomous,
        "gpio_available": robot.available,
        "motor_error": robot.error,
        "motor_action": robot.last_action,
        "follow_state": follower.state if is_autonomous else "paused",
        "camera_running": camera_state["running"],
        "camera_error": camera_state["error"],
        "person_detected": camera_state["person_detected"],
        "person_position": follower.get_person_position(),
        "fps": camera_state["fps"],
        "body_angle": camera_state["body_angle"],
        "posture_score": camera_state["posture_score"],
        "last_fall": camera_state["last_fall"],
        "twilio_configured": get_twilio_client() is not None,
        "smtp_configured": bool(os.getenv("SMTP_EMAIL", "").strip() and os.getenv("SMTP_PASSWORD", "").strip()),
        "contacts_count": len(emergency_contacts)
    }

@app.get("/video_feed")
async def video_feed():
    async def frames():
        while True:
            with frame_lock:
                jpg = latest_jpeg
            if jpg:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
            await asyncio.sleep(0.1)
    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")

# WebSocket for real-time video streaming and fall detection

@app.websocket("/ws/video")
async def websocket_video_stream(websocket: WebSocket):
    """WebSocket endpoint for real-time video streaming and fall detection"""
    await websocket.accept()
    try:
        while True:
            # Receive frame from client
            data = await websocket.receive_text()
            frame_data = json.loads(data)

            if frame_data.get("type") == "frame":
                # Process frame for fall detection
                image_data = frame_data.get("image")
                if image_data:
                    analysis = await detect_fall_base64({"image": image_data})

                    # Send analysis back
                    await websocket.send_json({
                        "type": "analysis",
                        "analysis": analysis
                    })

    except WebSocketDisconnect:
        print("WebSocket disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
