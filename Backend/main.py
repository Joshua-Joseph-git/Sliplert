from fastapi import FastAPI, File, UploadFile, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import cv2
import numpy as np
import mediapipe as mp
import json
import asyncio
from typing import List, Optional
from datetime import datetime
import base64
from pathlib import Path
import sys
import os

try:
    from gpiozero import Robot, DistanceSensor
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("GPIO not available - running in simulation mode")

SENSOR_TYPE = os.getenv("SENSOR_TYPE", "HC-SR04")
vl53l0x_sensor = None

app = FastAPI(title="SlipLert Backend")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MediaPipe Pose initialization
mp_pose = mp.solutions.pose
pose = mp_pose.Pose(
    static_image_mode=False,
    model_complexity=1,
    smooth_landmarks=True,
    enable_segmentation=False,
    smooth_segmentation=False,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

# Global state
emergency_contacts = []
fall_history = []
robot_position = {"x": 0, "y": 0, "angle": 0}
camera = None
is_autonomous = False
CONTACTS_FILE = "emergency_contacts.json"
FALL_HISTORY_FILE = "fall_history.json"

robot = None
distance_sensors = {}

if GPIO_AVAILABLE:
    robot = Robot(left=(17, 18), right=(22, 23))

    if SENSOR_TYPE == "HC-SR04":
        try:
            distance_sensors['front'] = DistanceSensor(
                echo=int(os.getenv("SENSOR_FRONT_ECHO", 24)),
                trigger=int(os.getenv("SENSOR_FRONT_TRIGGER", 25))
            )
            distance_sensors['left'] = DistanceSensor(
                echo=int(os.getenv("SENSOR_LEFT_ECHO", 27)),
                trigger=int(os.getenv("SENSOR_LEFT_TRIGGER", 23))
            )
            distance_sensors['right'] = DistanceSensor(
                echo=int(os.getenv("SENSOR_RIGHT_ECHO", 20)),
                trigger=int(os.getenv("SENSOR_RIGHT_TRIGGER", 21))
            )
            print("HC-SR04 sensors initialized")
        except Exception as e:
            print(f"HC-SR04 sensor initialization failed: {e}")

    elif SENSOR_TYPE == "VL53L0X":
        try:
            import board
            import busio
            import adafruit_vl53l0x
            i2c = busio.I2C(board.SCL, board.SDA)
            vl53l0x_sensor = adafruit_vl53l0x.VL53L0X(i2c)
            print("VL53L0X sensor initialized")
        except ImportError:
            print("VL53L0X library not installed. Install with: pip install adafruit-circuitpython-vl53l0x")
        except Exception as e:
            print(f"VL53L0X sensor initialization failed: {e}")

    elif SENSOR_TYPE == "NONE":
        print("No distance sensors configured - using camera-only mode")

class FallDetector:
    def __init__(self):
        self.previous_positions = []
        self.position_history_limit = 10
        self.fall_threshold = 0.7  # Threshold for fall detection
        self.velocity_threshold = 2.0  # Velocity threshold for fast falls

    def analyze_pose(self, landmarks):
        """Analyze pose landmarks to detect falls"""
        try:
            # Extract key landmarks
            nose = landmarks[mp_pose.PoseLandmark.NOSE]
            left_shoulder = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER]
            right_shoulder = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER]
            left_hip = landmarks[mp_pose.PoseLandmark.LEFT_HIP]
            right_hip = landmarks[mp_pose.PoseLandmark.RIGHT_HIP]
            left_ankle = landmarks[mp_pose.PoseLandmark.LEFT_ANKLE]
            right_ankle = landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE]

            # Calculate center points
            shoulder_center = self._get_midpoint(left_shoulder, right_shoulder)
            hip_center = self._get_midpoint(left_hip, right_hip)
            ankle_center = self._get_midpoint(left_ankle, right_ankle)

            # Calculate vertical alignment (shoulder to hip to ankle)
            vertical_alignment = self._calculate_vertical_alignment(shoulder_center, hip_center, ankle_center)

            # Calculate body angle (how tilted the person is)
            body_angle = self._calculate_body_angle(shoulder_center, hip_center)

            # Store position for velocity calculation
            current_position = {
                "timestamp": datetime.now().isoformat(),
                "y": nose.y,
                "vertical_alignment": vertical_alignment,
                "body_angle": body_angle
            }
            self.previous_positions.append(current_position)
            if len(self.previous_positions) > self.position_history_limit:
                self.previous_positions.pop(0)

            # Calculate velocity if we have enough history
            velocity = 0
            if len(self.previous_positions) >= 2:
                velocity = self._calculate_velocity()

            # Fall detection logic
            is_fall = False
            fall_type = None

            # Check 1: Body is horizontal (fallen)
            if body_angle > 60:  # More than 60 degrees from vertical
                is_fall = True
                fall_type = "horizontal"

            # Check 2: Fast downward movement
            elif velocity > self.velocity_threshold and vertical_alignment < self.fall_threshold:
                is_fall = True
                fall_type = "fast_fall"

            # Check 3: Sudden change in vertical alignment
            elif len(self.previous_positions) >= 5:
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
        angle = abs(np.degrees(np.arctan2(dx, dy)))
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

fall_detector = FallDetector()

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

def save_contacts_to_file():
    try:
        with open(CONTACTS_FILE, 'w') as f:
            json.dump(emergency_contacts, f, indent=2)
        print(f"Saved {len(emergency_contacts)} contacts to file")
    except Exception as e:
        print(f"Error saving contacts: {e}")

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

def read_distance_sensor(sensor_name: str) -> Optional[float]:
    try:
        if SENSOR_TYPE == "HC-SR04" and sensor_name in distance_sensors:
            return distance_sensors[sensor_name].distance * 100
        elif SENSOR_TYPE == "VL53L0X" and vl53l0x_sensor:
            return vl53l0x_sensor.range / 10
        else:
            return None
    except Exception as e:
        print(f"Error reading sensor {sensor_name}: {e}")
        return None

# API Routes

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
        results = pose.process(img_rgb)

        if results.pose_landmarks:
            analysis = fall_detector.analyze_pose(results.pose_landmarks.landmark)

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

        # Convert to RGB for MediaPipe
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # Process with MediaPipe
        results = pose.process(img_rgb)

        if results.pose_landmarks:
            analysis = fall_detector.analyze_pose(results.pose_landmarks.landmark)

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

    contact["id"] = len(emergency_contacts) + 1
    contact["created_at"] = datetime.now().isoformat()
    emergency_contacts.append(contact)
    save_contacts_to_file()
    return {"message": "Contact added successfully", "contact": contact}

@app.get("/emergency-contacts")
async def get_emergency_contacts():
    """Get all emergency contacts"""
    load_contacts_from_file()
    return {"contacts": emergency_contacts}

@app.delete("/emergency-contacts/{contact_id}")
async def delete_emergency_contact(contact_id: int):
    """Delete an emergency contact"""
    global emergency_contacts
    emergency_contacts = [c for c in emergency_contacts if c["id"] != contact_id]
    save_contacts_to_file()
    return {"message": "Contact deleted successfully"}

async def trigger_emergency_alert(fall_record: dict):
    """Trigger emergency alert - call all contacts"""
    print(f"🚨 EMERGENCY ALERT: Fall detected at {fall_record['timestamp']}")
    print(f"Fall type: {fall_record['fall_type']}")
    print(f"Body angle: {fall_record['body_angle']:.2f}°")

    # In production, integrate with Twilio or other calling service here
    # For now, we'll log the contacts that would be called
    for contact in emergency_contacts:
        print(f"📞 Would call: {contact['name']} ({contact['phone']}) - {contact['relationship']}")

    # Stop robot if it's moving
    if robot:
        robot.stop()

# Robot Control

@app.post("/robot/control")
async def control_robot(command: dict):
    """Control the robot"""
    action = command.get("action")
    speed = command.get("speed", 50)

    if not robot:
        return {"message": "Robot not available (GPIO not initialized)", "status": "simulation"}

    try:
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
    is_autonomous = settings.get("enabled", False)
    return {"message": f"Autonomous mode {'enabled' if is_autonomous else 'disabled'}", "status": is_autonomous}

@app.get("/robot/status")
async def get_robot_status():
    """Get robot status"""
    return {
        "position": robot_position,
        "autonomous": is_autonomous,
        "gpio_available": GPIO_AVAILABLE
    }

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
