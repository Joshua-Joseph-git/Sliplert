import cv2
import numpy as np
import mediapipe as mp
import time
from typing import Tuple, Optional
import math

# Check if running on Raspberry Pi
try:
    from gpiozero import Robot, DistanceSensor
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("GPIO not available - running in simulation mode")

class AutonomousController:
    """Autonomous robot controller that follows a person using MediaPipe pose detection"""

    def __init__(self):
        # MediaPipe Pose initialization
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            smooth_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

        # Robot initialization
        self.robot = None
        self.distance_sensors = {}
        if GPIO_AVAILABLE:
            self.robot = Robot(left=(17, 18), right=(22, 23))
            # Add distance sensors if available
            try:
                self.distance_sensors['front'] = DistanceSensor(echo=24, trigger=25)
                self.distance_sensors['left'] = DistanceSensor(echo=27, trigger=23)
                self.distance_sensors['right'] = DistanceSensor(echo=20, trigger=21)
            except:
                print("Distance sensors not available")

        # Control parameters
        self.target_distance = 100  # cm - desired distance from person
        self.min_distance = 30  # cm - minimum safe distance
        self.max_distance = 200  # cm - maximum distance to track
        self.follow_speed = 0.5  # Speed when following
        self.turn_speed = 0.3  # Speed when turning

        # State tracking
        self.is_running = False
        self.person_position = None  # (x, y, z) in camera coordinates
        self.last_person_position = None
        self.frame_width = 640
        self.frame_height = 480

    def start(self):
        """Start autonomous following"""
        self.is_running = True
        print("Autonomous mode started")

    def stop(self):
        """Stop autonomous following"""
        self.is_running = False
        if self.robot:
            self.robot.stop()
        print("Autonomous mode stopped")

    def process_frame(self, frame: np.ndarray) -> Tuple[bool, dict]:
        """
        Process a camera frame to detect person and calculate robot control commands

        Args:
            frame: Camera frame (numpy array)

        Returns:
            Tuple of (person_detected, control_commands)
        """
        if not self.is_running:
            return False, {"action": "stop"}

        # Convert to RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Process with MediaPipe
        results = self.pose.process(frame_rgb)

        if results.pose_landmarks:
            # Extract person position
            landmarks = results.pose_landmarks.landmark

            # Get torso center (midpoint of shoulders and hips)
            left_shoulder = landmarks[self.mp_pose.PoseLandmark.LEFT_SHOULDER]
            right_shoulder = landmarks[self.mp_pose.PoseLandmark.RIGHT_SHOULDER]
            left_hip = landmarks[self.mp_pose.PoseLandmark.LEFT_HIP]
            right_hip = landmarks[self.mp_pose.PoseLandmark.RIGHT_HIP]

            # Calculate center of mass in image coordinates
            center_x = (left_shoulder.x + right_shoulder.x + left_hip.x + right_hip.x) / 4
            center_y = (left_shoulder.y + right_shoulder.y + left_hip.y + right_hip.y) / 4

            # Estimate distance based on person size (shoulder width)
            shoulder_width = abs(left_shoulder.x - right_shoulder.x)
            estimated_distance = self._estimate_distance(shoulder_width)

            # Store position
            self.person_position = {
                "x": center_x,
                "y": center_y,
                "distance": estimated_distance,
                "confidence": 0.9
            }

            # Calculate control commands
            control_commands = self._calculate_control_commands(center_x, estimated_distance)

            # Execute commands
            self._execute_commands(control_commands)

            return True, control_commands
        else:
            # Person not detected - stop or search
            self.person_position = None
            return False, {"action": "stop"}

    def _estimate_distance(self, shoulder_width: float) -> float:
        """
        Estimate distance to person based on shoulder width in image

        Args:
            shoulder_width: Shoulder width as fraction of image width (0-1)

        Returns:
            Estimated distance in cm
        """
        # Calibrated values (adjust based on your camera and setup)
        known_shoulder_width = 40  # cm (average shoulder width)
        known_distance = 100  # cm (calibration distance)
        known_shoulder_width_in_image = 0.3  # fraction of image width at calibration distance

        # Calculate distance using proportional relationship
        if shoulder_width > 0:
            estimated_distance = (known_shoulder_width_in_image / shoulder_width) * known_distance
            return estimated_distance
        return self.max_distance

    def _calculate_control_commands(self, center_x: float, distance: float) -> dict:
        """
        Calculate robot control commands based on person position

        Args:
            center_x: Person's center x position (0-1, where 0.5 is center)
            distance: Estimated distance to person in cm

        Returns:
            Dictionary with control commands
        """
        commands = {"action": "stop", "speed": 0, "turn": 0}

        # Check for obstacles using distance sensors
        obstacle_detected = self._check_obstacles()
        if obstacle_detected:
            return self._handle_obstacle(obstacle_detected)

        # Calculate horizontal offset from center
        horizontal_offset = center_x - 0.5  # -0.5 to 0.5

        # Distance control
        if distance > self.max_distance:
            # Person too far - move forward
            commands["action"] = "forward"
            commands["speed"] = self.follow_speed
        elif distance < self.min_distance:
            # Person too close - move backward
            commands["action"] = "backward"
            commands["speed"] = self.follow_speed * 0.5
        else:
            # Good distance - just adjust position
            commands["action"] = "adjust"

        # Direction control
        if abs(horizontal_offset) > 0.1:  # More than 10% off center
            if horizontal_offset > 0:
                # Person to the right - turn right
                commands["turn"] = -self.turn_speed
            else:
                # Person to the left - turn left
                commands["turn"] = self.turn_speed
        else:
            commands["turn"] = 0

        return commands

    def _check_obstacles(self) -> Optional[str]:
        """Check distance sensors for obstacles"""
        if not GPIO_AVAILABLE or not self.distance_sensors:
            return None

        for direction, sensor in self.distance_sensors.items():
            try:
                distance = sensor.distance * 100  # Convert to cm
                if distance < 30:  # Obstacle within 30cm
                    return direction
            except:
                pass

        return None

    def _handle_obstacle(self, direction: str) -> dict:
        """Handle obstacle detection"""
        print(f"Obstacle detected at {direction}")

        if direction == "front":
            # Obstacle ahead - stop and wait
            return {"action": "stop", "reason": "obstacle_front"}
        elif direction == "left":
            # Obstacle on left - turn right
            return {"action": "right", "speed": self.turn_speed}
        elif direction == "right":
            # Obstacle on right - turn left
            return {"action": "left", "speed": self.turn_speed}

        return {"action": "stop"}

    def _execute_commands(self, commands: dict):
        """Execute robot control commands"""
        if not self.robot:
            # Simulation mode - just print commands
            print(f"Simulation: {commands}")
            return

        action = commands.get("action")

        if action == "forward":
            self.robot.forward(speed=commands.get("speed", self.follow_speed))
        elif action == "backward":
            self.robot.backward(speed=commands.get("speed", self.follow_speed * 0.5))
        elif action == "left":
            self.robot.left(speed=commands.get("speed", self.turn_speed))
        elif action == "right":
            self.robot.right(speed=commands.get("speed", self.turn_speed))
        elif action == "stop":
            self.robot.stop()
        elif action == "adjust":
            # Adjust direction while maintaining position
            turn = commands.get("turn", 0)
            if turn > 0:
                self.robot.left(speed=turn)
            elif turn < 0:
                self.robot.right(speed=abs(turn))
            else:
                self.robot.stop()

    def get_person_position(self) -> Optional[dict]:
        """Get current person position"""
        return self.person_position

    def is_person_detected(self) -> bool:
        """Check if person is currently detected"""
        return self.person_position is not None


# Standalone test function
def test_autonomous_controller():
    """Test the autonomous controller with a webcam"""
    controller = AutonomousController()
    controller.start()

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # Process frame
            person_detected, commands = controller.process_frame(frame)

            # Display info on frame
            cv2.putText(frame, f"Person Detected: {person_detected}", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0) if person_detected else (0, 0, 255), 2)

            if person_detected:
                pos = controller.get_person_position()
                cv2.putText(frame, f"Distance: {pos['distance']:.1f}cm", (10, 60),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.putText(frame, f"Action: {commands['action']}", (10, 90),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            cv2.imshow('Autonomous Controller', frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    finally:
        controller.stop()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    test_autonomous_controller()
