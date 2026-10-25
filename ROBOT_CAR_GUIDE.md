

```python
# robot_controller.py
import cv2
import numpy as np
from flask import Flask, Response
import time
import threading

app = Flask(__name__)

class RobotController:
    def __init__(self):
        self.camera = cv2.VideoCapture(0)
        self.motor_pins = {
#PINS FOR ROBOT CAR
            'left_forward': 17,
            'left_backward': 18,
            'right_forward': 22,
            'right_backward': 23
        }
        self.is_autonomous = False
        self.current_position = {'x': 0, 'y': 0, 'angle': 0}#Axis's
        
    def start_camera(self):
        """Initialize camera for fall detection"""#TURN ON CAMERA
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.camera.set(cv2.CAP_PROP_FPS, 30)
        
    def get_frame(self):
        """Capture and return current frame"""
        ret, frame = self.camera.read()
        if ret:
            ret, jpeg = cv2.imencode('.jpg', frame)
            return jpeg.tobytes()
        return None
#SPEEDS, AND FUNCTION:STOP, BACK, RIGHT, LEFT, FORWARD
    def move_forward(self, speed=50):
        """Move robot forward"""
        # GPIO control code here
        pass
        
    def move_backward(self, speed=50):
        """Move robot backward"""
        # GPIO control code here
        pass
        
    def turn_left(self, angle=90):
        """Turn robot left by specified angle"""
        # GPIO control code here
        pass
        
    def turn_right(self, angle=90):
        """Turn robot right by specified angle"""
        # GPIO control code here
        pass
        
    def stop(self):
        """Stop all motors"""
        # GPIO control code here
        pass

robot = RobotController()

@app.route('/video_feed')
def video_feed():
    """Video streaming route"""
    def gen():
        while True:
            frame = robot.get_frame()
            if frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')
#fI NOT FORWARD, BACKWARD, IF NOT BACKWARD, LEFT, IF NOT LEFT, RIGHT, IF NOT LEFT STOP
@app.route('/control/<action>')
def control_robot(action):
    """REST API for robot control"""
    if action == 'forward':
        robot.move_forward()
    elif action == 'backward':
        robot.move_backward()
    elif action == 'left':
        robot.turn_left()
    elif action == 'right':
        robot.turn_right()
    elif action == 'stop':
        robot.stop()
    return {'status': 'success', 'action': action}

if __name__ == '__main__':
    robot.start_camera()
    app.run(host='0.0.0.0', port=5000)
```

---

```typescript
// frontend/lib/robotConnection.ts
//connect for the front end
class RobotConnection {
  private ws: WebSocket | null = null;
  private videoElement: HTMLVideoElement | null = null;

  connect(robotUrl: string) {
    this.ws = new WebSocket(`ws://${robotUrl}:5000/ws`);
    
    this.ws.onopen = () => {
      console.log('Connected to robot');
    };
    
    this.ws.onmessage = (event) => {
      if (event.data instanceof Blob) {
        // Handle video frame
        const imageUrl = URL.createObjectURL(event.data);
        if (this.videoElement) {
          this.videoElement.src = imageUrl;
        }
      }
    };
    
    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }

  sendCommand(command: string) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ command }));
    }
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
    }
  }
}

export const robotConnection = new RobotConnection();
```

### Step 2: Update Dashboard to Use Robot Feed

Modify your dashboard to connect to the robot's camera:

```typescript
// frontend/app/dashboard/page.tsx
import { useEffect, useRef } from 'react';
import { robotConnection } from '@/lib/robotConnection';

export default function CameraDashboard() {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    // Connect to robot (replace with your robot's IP)
    robotConnection.connect('192.168.1.100');
    robotConnection.videoElement = videoRef.current;

    return () => {
      robotConnection.disconnect();
    };
  }, []);

  return (
    <video ref={videoRef} autoPlay playsInline muted />
  );
}
```

---

## Implementing Autonomous Navigation

### Option 1: Simple Patrol Mode

The robot follows a predefined path:

```python
# autonomous_patrol.py
import time
from robot_controller import RobotController

class AutonomousPatrol:
    def __init__(self, robot: RobotController):
        self.robot = robot
        self.waypoints = [
            {'x': 0, 'y': 0},
            {'x': 2, 'y': 0},
            {'x': 2, 'y': 2},
            {'x': 0, 'y': 2},
        ]
        self.current_waypoint = 0
        
    def navigate_to_waypoint(self, target):
        """Navigate to specified waypoint"""
        current = self.robot.current_position
        
        # Calculate angle to target
        dx = target['x'] - current['x']
        dy = target['y'] - current['y']
        target_angle = math.atan2(dy, dx)
        
        # Turn to face target
        angle_diff = target_angle - current['angle']
        if angle_diff > 0:
            self.robot.turn_left(angle_diff)
        else:
            self.robot.turn_right(abs(angle_diff))
            
        # Move forward
        distance = math.sqrt(dx**2 + dy**2)
        self.robot.move_forward()
        time.sleep(distance * 2)  # Adjust based on robot speed
        self.robot.stop()
        
    def start_patrol(self):
        """Start autonomous patrol loop"""
        while True:
            target = self.waypoints[self.current_waypoint]
            self.navigate_to_waypoint(target)
            
            self.current_waypoint = (self.current_waypoint + 1) % len(self.waypoints)
            time.sleep(5)  # Wait at each waypoint
```

### Option 2: Obstacle Avoidance Mode

The robot uses sensors to navigate around obstacles:

```python
# obstacle_avoidance.py
import time
from robot_controller import RobotController

class ObstacleAvoidance:
    def __init__(self, robot: RobotController):
        self.robot = robot
        self.sensor_threshold = 30  # cm
        
    def check_obstacles(self):
        """Check distance sensors for obstacles"""
        # Read ultrasonic sensors
        front_distance = self.read_sensor('front')
        left_distance = self.read_sensor('left')
        right_distance = self.read_sensor('right')
        
        return {
            'front': front_distance,
            'left': left_distance,
            'right': right_distance
        }
        
    def autonomous_navigate(self):
        """Navigate while avoiding obstacles"""
        while True:
            obstacles = self.check_obstacles()
            
            if obstacles['front'] < self.sensor_threshold:
                # Obstacle ahead - decide which way to turn
                if obstacles['left'] > obstacles['right']:
                    self.robot.turn_left(90)
                else:
                    self.robot.turn_right(90)
            else:
                # Path clear - move forward
                self.robot.move_forward()
                
            time.sleep(0.1)
            
    def read_sensor(self, position):
        """Read distance from ultrasonic sensor"""
        # GPIO code to read HC-SR04 sensor
        # Return distance in cm
        pass
```

### Option 3: AI-Powered Navigation (Advanced)

Use computer vision for smart navigation:

```python
# ai_navigation.py
import cv2
import numpy as np
from robot_controller import RobotController

class AINavigation:
    def __init__(self, robot: RobotController):
        self.robot = robot
        
    def detect_path(self, frame):
        """Use computer vision to detect navigable path"""
        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Apply edge detection
        edges = cv2.Canny(gray, 50, 150)
        
        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Analyze contours to find path
        # This is simplified - you'd use more sophisticated algorithms
        return self.calculate_safe_direction(contours)
        
    def calculate_safe_direction(self, contours):
        """Calculate safe direction based on detected obstacles"""
        # Analyze frame to determine best direction
        # Return: 'left', 'right', 'forward', or 'stop'
        pass
        
    def navigate_with_vision(self):
        """Navigate using computer vision"""
        while True:
            frame = self.robot.camera.read()
            direction = self.detect_path(frame)
            
            if direction == 'forward':
                self.robot.move_forward()
            elif direction == 'left':
                self.robot.turn_left(30)
            elif direction == 'right':
                self.robot.turn_right(30)
            elif direction == 'stop':
                self.robot.stop()
```

---

## Integration with Fall Detection

### Sending Video to AI for Analysis

```python
# fall_detection_integration.py
import requests
from robot_controller import RobotController

class FallDetectionIntegration:
    def __init__(self, robot: RobotController, ai_endpoint: str):
        self.robot = robot
        self.ai_endpoint = ai_endpoint
        
    def capture_and_analyze(self):
        """Capture frame and send to AI for fall detection"""
        ret, frame = self.robot.camera.read()
        if ret:
            # Preprocess frame if needed
            processed_frame = self.preprocess_frame(frame)
            
            # Send to AI endpoint
            response = requests.post(
                self.ai_endpoint,
                json={'image': processed_frame.tolist()}
            )
            
            result = response.json()
            
            if result.get('fall_detected'):
                self.handle_fall_alert()
                
    def handle_fall_alert(self):
        """Handle fall detection alert"""
        self.robot.stop()
        # Send alert to frontend
        # Take additional actions (sound alarm, etc.)
```

---

\