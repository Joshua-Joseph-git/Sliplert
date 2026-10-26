#Start of the code for the main backend

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
from contextlib import asynccontextmanager
#DEVIN HELP FOR WHICH API'S I USED
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from gpiozero import Robot
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("GPIO not available - running in simulation mode")

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
    if os.getenv("ROBOT_CAMERA", "on" if GPIO_AVAILABLE else "off").lower() == "on":
        threading.Thread(target=robot_camera_loop, daemon=True).start()
    else:
        print("Robot camera loop off (set ROBOT_CAMERA=on to enable)")
    yield
    stop_event.set()
    if robot:
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
is_autonomous = False
CONTACTS_FILE = "emergency_contacts.json"
FALL_HISTORY_FILE = "fall_history.json"

robot = None

if GPIO_AVAILABLE:

    try:
        robot = Robot(
            left=(int(os.getenv("ROBOT_LEFT_FORWARD_PIN", 17)), int(os.getenv("ROBOT_LEFT_BACKWARD_PIN", 18))),
            right=(int(os.getenv("ROBOT_RIGHT_FORWARD_PIN", 22)), int(os.getenv("ROBOT_RIGHT_BACKWARD_PIN", 23)))
        )
        print("Robot GPIO initialized")
    except Exception as e:
        print(f"Robot GPIO initialization failed (not on Raspberry Pi): {e}")
        GPIO_AVAILABLE = False



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

            hips_visible = pose_utils.visibility(left_hip) > 0.45 and pose_utils.visibility(right_hip) > 0.45
            ankles_visible = pose_utils.visibility(left_ankle) > 0.45 and pose_utils.visibility(right_ankle) > 0.45

            # Calculate vertical alignment (shoulder to hip to ankle)
            vertical_alignment = self._calculate_vertical_alignment(shoulder_center, hip_center, ankle_center)

            # Calculate body angle: use torso angle if hips are in frame, plus shoulder/head tilt when close to camera
            torso_angle = self._calculate_body_angle(shoulder_center, hip_center) if hips_visible else 0.0
            shoulder_dx = abs(left_shoulder.x - right_shoulder.x)
            shoulder_dy = abs(left_shoulder.y - right_shoulder.y)
            shoulder_tilt = float(np.degrees(np.arctan2(shoulder_dy, max(shoulder_dx, 1e-4))))
            head_tilt = self._calculate_body_angle({"x": nose.x, "y": nose.y}, shoulder_center)
            drop_penalty = max(0.0, (shoulder_center["y"] - 0.55) * 140.0)
            body_angle = float(min(90.0, max(torso_angle, shoulder_tilt * 1.35, head_tilt * 0.85, drop_penalty)))

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

            # Fall detection logic
            is_fall = False
            fall_type = None

            # Check Number 1: Body or shoulders tilted past threshold (fallen sideways/horizontally)
            if body_angle > 48 or shoulder_tilt > 35:
                is_fall = True
                fall_type = "horizontal"

            # Check Number 2: Fast downward drop or collapse toward bottom of camera frame
            elif downward_velocity > 0.45 or recent_drop > 0.20 or nose.y > 0.78 or shoulder_center["y"] > 0.82:
                is_fall = True
                fall_type = "fast_fall"
                body_angle = max(body_angle, 72.0)

            # Check NUMBER 3: Sudden change in vertical alignment
            elif ankles_visible and len(self.previous_positions) >= 5:
                recent_alignment = [p["vertical_alignment"] for p in self.previous_positions[-5:]]
                if max(recent_alignment) - min(recent_alignment) > 0.5:
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

from autonomous_controller import AutonomousController

follower = AutonomousController(robot=robot, create_hardware=False)
camera_state = {"running": False, "person_detected": False, "fps": 0.0, "body_angle": 0.0, "posture_score": 98, "last_fall": None}
latest_jpeg = None
frame_lock = threading.Lock()
TORSO_LANDMARKS = [
    pose_utils.NOSE,
    pose_utils.LEFT_SHOULDER,
    pose_utils.RIGHT_SHOULDER,
]

#camera instilization 
def open_camera():
    try:
        from picamera2 import Picamera2
        picam = Picamera2()
        cfg = picam.create_preview_configuration(
            main={"size": (640, 480), "format": "RGB888"},
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
        probe.join(timeout=3.0)
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
        return (lambda: cv2.cvtColor(picam.capture_array(), cv2.COLOR_RGB2BGR)), _close_picam
    except Exception as e:
        print(f"picamera2 not available ({e}) - trying USB/OpenCV camera")

    cap = cv2.VideoCapture(int(os.getenv("CAMERA_INDEX", 0)))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    if not cap.isOpened():
        return None, None
    print("Using OpenCV camera")
    return (lambda: cap.read()[1]), cap.release

#the camera constantly is running and checking for the condtiions and if it is connected
def robot_camera_loop():
    global latest_jpeg
    read_frame, release = open_camera()
    if not read_frame:
        print("No camera found - robot camera loop not started")
        return

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
                time.sleep(0.05)
                continue

            timestamp_ms = max(timestamp_ms + 1, int(time.monotonic() * 1000))
            landmarks = pose_utils.detect_landmarks(loop_pose, frame, timestamp_ms)
            visible = landmarks is not None and sum(pose_utils.visibility(landmarks[i]) > 0.35 for i in TORSO_LANDMARKS) >= 2
            camera_state["person_detected"] = visible

            if visible:
                analysis = loop_detector.analyze_pose(landmarks)
                angle = float(analysis.get("body_angle", 0.0))
                camera_state["body_angle"] = round(angle, 1)
                camera_state["posture_score"] = max(0, min(100, int(round(100 - angle))))
                fall_streak = fall_streak + 1 if analysis.get("is_fall") else 0
                if fall_streak >= confirm_frames:
                    fall_streak = 0
                    record = {
                        "timestamp": datetime.now().isoformat(),
                        "fall_type": analysis["fall_type"],
                        "body_angle": analysis["body_angle"],
                        "confidence": analysis["confidence"],
                        "source": "robot_camera"
                    }#CHECKS FOR FALL IF SO THERE IS AN ALERT
                    camera_state["last_fall"] = record
                    if send_emergency_alert(record):
                        fall_history.append(record)
                        save_fall_history_to_file()
                elif is_autonomous:
                    follower.is_running = True
                    follower.follow_landmarks(landmarks)
            elif is_autonomous:
                follower.lose_person()

            if not is_autonomous and follower.is_running:
                follower.stop()

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
                fall_history.append(fall_record)
                save_fall_history_to_file()

                # Trigger emergency alert
                await trigger_emergency_alert(fall_record)

            return {
                "fall_detected": analysis["is_fall"],
                "fall_type": analysis["fall_type"],
                "body_angle": analysis["body_angle"],
                "vertical_alignment": analysis["vertical_alignment"],
                "velocity": analysis["velocity"],
                "confidence": analysis["confidence"]
            }
        else:
            return {"fall_detected": False, "message": "No pose detected"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/detect-fall-base64")
async def detect_fall_base64(data: dict):
    """Detect fall from base64 encoded image"""
    try:
        if data.get("coordinates") or data.get("simulate"):
            fall_record = {
                "timestamp": datetime.now().isoformat(),
                "fall_type": "simulated_fall",
                "body_angle": 82.0,
                "confidence": 0.98
            }
            camera_state["last_fall"] = fall_record
            camera_state["body_angle"] = 82.0
            camera_state["posture_score"] = 18
            fall_history.append(fall_record)
            save_fall_history_to_file()
            await trigger_emergency_alert(fall_record)
            return {
                "fall_detected": True,
                "fall_type": "simulated_fall",
                "body_angle": 82.0,
                "vertical_alignment": 0.9,
                "velocity": 2.4,
                "confidence": 0.98
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
                fall_history.append(fall_record)
                save_fall_history_to_file()
                await trigger_emergency_alert(fall_record)

            return {
                "fall_detected": analysis["is_fall"],
                "fall_type": analysis["fall_type"],
                "body_angle": analysis["body_angle"],
                "vertical_alignment": analysis["vertical_alignment"],
                "velocity": analysis["velocity"],
                "confidence": analysis["confidence"]
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


def send_emergency_alert(fall_record: dict) -> bool:
    global last_alert_time, is_autonomous
    with alert_lock:
        now = time.time()
        if now - last_alert_time < ALERT_COOLDOWN_SECONDS:
            return False
        last_alert_time = now

    print(f"🚨 EMERGENCY ALERT: Fall detected at {fall_record['timestamp']}")
    print(f"Fall type: {fall_record['fall_type']}")
    print(f"Body angle: {fall_record['body_angle']:.2f}°")

    is_autonomous = False
    follower.stop()
#prints if a fall occured 
    client = get_twilio_client()
    from_number = os.getenv("TWILIO_PHONE_NUMBER")
    message = "This is SlipLert. A fall has been detected. Please check on your loved one immediately."
    if not emergency_contacts:
        print("No emergency contacts saved, nobody to call")
    for contact in emergency_contacts:
        if not client:
            print(f" Would call (Twilio not configured): {contact['name']} ({contact['phone']})")
            continue
        try:
            client.calls.create(
                to=contact["phone"],
                from_=from_number,
                twiml=f'<Response><Say loop="2">{message}</Say></Response>'
            )
            client.messages.create(to=contact["phone"], from_=from_number, body=f"{message} Time: {fall_record['timestamp']}")
            print(f"Called and texted {contact['name']} ({contact['phone']})")
        except Exception as e:
            print(f"Failed to alert {contact['name']} ({contact['phone']}): {e}")
    return True


async def trigger_emergency_alert(fall_record: dict):
    """Trigger emergency alert - call all contacts"""
    await asyncio.to_thread(send_emergency_alert, fall_record)

# Robot Control...

@app.post("/robot/control")
async def control_robot(command: dict):
    """Control the robot"""
    action = command.get("action")
    speed = command.get("speed", 50)

    if not robot:
        return {"message": "Robot not available (GPIO not initialized)", "status": "simulation"}

    try:#More driving functions
        if action == "forward":
            robot.forward(speed=speed/100)
        elif action == "backward":
            robot.backward(speed=speed/100)
        elif action == "left":
            robot.left(speed=speed/100)
        elif action == "right":
            robot.right(speed=speed/100)
        elif action == "stop":
            robot.stop()
        else:
            raise HTTPException(status_code=400, detail="Invalid action")

        return {"message": f"Robot {action} executed", "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/robot/autonomous")
async def toggle_autonomous(settings: dict):
    """Toggle autonomous mode"""
    global is_autonomous
    is_autonomous = bool(settings.get("enabled", False))
    if is_autonomous and not camera_state["running"]:
        stop_event.clear()
        threading.Thread(target=robot_camera_loop, daemon=True).start()
    if not is_autonomous:
        follower.stop()
    message = f"Autonomous mode {'enabled' if is_autonomous else 'disabled'}"
    return {"message": message, "status": is_autonomous}

@app.post("/robot/camera")
async def toggle_robot_camera(settings: dict):
    global is_autonomous
    enable = bool(settings.get("enabled", True))
    if enable:
        if not camera_state["running"]:
            stop_event.clear()
            threading.Thread(target=robot_camera_loop, daemon=True).start()
            await asyncio.sleep(0.6)
        return {"message": "Robot camera started", "camera_running": camera_state["running"]}
    is_autonomous = False
    follower.stop()
    stop_event.set()
    return {"message": "Robot camera stopped", "camera_running": False}

@app.get("/robot/status")
async def get_robot_status():
    """Get robot status"""
    return {
        "position": robot_position,
        "autonomous": is_autonomous,
        "gpio_available": GPIO_AVAILABLE,
        "camera_running": camera_state["running"],
        "person_detected": camera_state["person_detected"],
        "person_position": follower.get_person_position(),
        "fps": camera_state["fps"],
        "body_angle": camera_state["body_angle"],
        "posture_score": camera_state["posture_score"],
        "last_fall": camera_state["last_fall"],
        "twilio_configured": get_twilio_client() is not None,
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
