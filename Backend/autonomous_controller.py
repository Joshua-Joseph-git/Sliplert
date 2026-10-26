#Start of code for the robot car to move without a controller
#Pose detection comes from pose_utils (MoveNet ONNX on the Pi, MediaPipe on a laptop)


import cv2
#This code is helped with Devin, the code was hard to decode and what modules/imports to use were confusing and how to properly font this.
import numpy as np
import pose_utils
import os
import sys
import threading
import time
from typing import Tuple, Optional

# gpiozero needs a pin driver (lgpio / RPi.GPIO). Raspberry Pi OS ships them as system packages,
# which a normal .venv can't see -> "Unable to load any default pin factory" and no motors.
# Fall back to the system copies (appended last, so the venv's own packages still win).
if sys.platform.startswith("linux"):
    import importlib.util
    if importlib.util.find_spec("lgpio") is None and importlib.util.find_spec("RPi") is None:
        for _sys_pkgs in ("/usr/lib/python3/dist-packages", f"/usr/lib/python3.{sys.version_info.minor}/dist-packages"):
            if os.path.isdir(_sys_pkgs) and _sys_pkgs not in sys.path:
                sys.path.append(_sys_pkgs)

# Check if running on Raspberry Pi
try:
    from gpiozero import Motor
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("GPIO not available - running in simulation mode")


def _env_flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _env_pin(name: str):
    value = os.getenv(name, "").strip()
    return int(value) if value else None


# (left wheel, right wheel): 1 = forward, -1 = backward, 0 = stopped
MOTIONS = {
    "forward": (1, 1),
    "backward": (-1, -1),
    "spin_left": (-1, 1),
    "spin_right": (1, -1),
    "arc_left": (0, 1),   # only the right wheel drives -> gentle left curve
    "arc_right": (1, 0),  # only the left wheel drives -> gentle right curve
    "stop": (0, 0),
}


class MotorDriver:
    """Owns the two L298N motors. Everything else in the app asks for LOGICAL moves
    ("forward" = toward what the camera sees); wiring quirks are fixed here, once.

    .env settings (defaults match the current car, where motor polarity is reversed):
      ROBOT_REVERSE_LEFT=1 / ROBOT_REVERSE_RIGHT=1  flip a wheel that spins the wrong way
      ROBOT_SWAP_SIDES=0                            set to 1 if left/right turns are mirrored
      ROBOT_LEFT_ENABLE_PIN / ROBOT_RIGHT_ENABLE_PIN only if ENA/ENB go to the Pi (no jumpers)
      ROBOT_PWM=0                                   1 lets MOTOR_SPEED below 1.0 work
    """

    def __init__(self):
        self.left = None
        self.right = None
        self.error = None
        self.last_action = "stop"
        self._deadline = None
        self._lock = threading.Lock()
        self.pwm = _env_flag("ROBOT_PWM", "0")
        self.speed = float(os.getenv("MOTOR_SPEED", "1.0")) if self.pwm else 1.0

        left = [int(os.getenv("ROBOT_LEFT_FORWARD_PIN", 17)), int(os.getenv("ROBOT_LEFT_BACKWARD_PIN", 18)), _env_pin("ROBOT_LEFT_ENABLE_PIN")]
        right = [int(os.getenv("ROBOT_RIGHT_FORWARD_PIN", 22)), int(os.getenv("ROBOT_RIGHT_BACKWARD_PIN", 23)), _env_pin("ROBOT_RIGHT_ENABLE_PIN")]
        # Swapping a motor's forward/backward pins in software is the same as swapping its wires
        if _env_flag("ROBOT_REVERSE_LEFT", "1"):
            left[0], left[1] = left[1], left[0]
        if _env_flag("ROBOT_REVERSE_RIGHT", "1"):
            right[0], right[1] = right[1], right[0]
        if _env_flag("ROBOT_SWAP_SIDES", "0"):
            left, right = right, left
        self.config = {"left": left, "right": right, "pwm": self.pwm}

        if not GPIO_AVAILABLE:
            self.error = "gpiozero is not installed (simulation mode)"
        else:
            try:
                self.left = Motor(left[0], left[1], enable=left[2], pwm=self.pwm)
                self.right = Motor(right[0], right[1], enable=right[2], pwm=self.pwm)
                print(f"Robot GPIO initialized (left pins {left}, right pins {right}, pwm={self.pwm})")
            except Exception as e:
                for m in (self.left, self.right):
                    if m is not None:
                        try:
                            m.close()
                        except Exception:
                            pass
                self.left = self.right = None
                self.error = f"{type(e).__name__}: {e}"
                hint = ""
                if "PinFactory" in type(e).__name__ or "pin factory" in str(e).lower():
                    hint = " -> no GPIO driver found. Run: sudo apt install python3-lgpio  (then restart SlipLert)"
                elif "in use" in str(e).lower():
                    hint = " -> another program is holding the GPIO pins (an old main.py?). Reboot or: sudo pkill -f main.py"
                print(f"Robot GPIO initialization failed: {self.error}{hint}") #ERROR CODE IF THE CODE WRITTEN DOSEN"T WORK
                self.error += hint

        # Safety watchdog: any timed move stops by itself, so a frozen camera or a lost
        # Wi-Fi connection can never leave the car driving into a wall.
        threading.Thread(target=self._watchdog, daemon=True).start()

    @property
    def available(self) -> bool:
        return self.left is not None and self.right is not None

    def drive(self, action: str, duration: Optional[float] = None):
        """Start a logical move. With a duration, the move stops on its own after that many seconds."""
        if action not in MOTIONS:
            raise ValueError(f"Unknown motion: {action}")
        with self._lock:
            if action != self.last_action and not self.available:
                print(f"Simulation: {action}")
            self._apply(action)
            self._deadline = time.monotonic() + duration if duration and action != "stop" else None

    def stop(self):
        self.drive("stop")

    def _apply(self, action: str):
        self.last_action = action
        if not self.available:
            return
        for motor, direction in zip((self.left, self.right), MOTIONS[action]):
            if direction > 0:
                motor.forward(self.speed)
            elif direction < 0:
                motor.backward(self.speed)
            else:
                motor.stop()

    def _watchdog(self):
        while True:
            time.sleep(0.03)
            with self._lock:
                if self._deadline is not None and time.monotonic() >= self._deadline:
                    self._deadline = None
                    self._apply("stop")


class AutonomousController:
    """Autonomous robot controller that follows a person using pose detection"""

    def __init__(self, robot: Optional[MotorDriver] = None, create_hardware=True):
        self.pose = None

        # Robot initialization
        self.robot = robot
        if create_hardware and robot is None:
            self.robot = MotorDriver()

        # Control parameters (distances come from the shoulder-width estimate below)
        self.target_distance = float(os.getenv("FOLLOW_TARGET_CM", 70))  # cm - stop driving forward once this close
        self.min_distance = float(os.getenv("FOLLOW_MIN_CM", 40))  # cm - back up if closer than this
        self.max_distance = 1000  # cm - maximum distance to track
        self.dead_zone = 0.12  # person within 12% of center -> drive straight
        self.spin_zone = 0.30  # person more than 30% off center -> turn in place
        self.drive_hold = 0.5  # s - forward moves auto-stop unless the next frame renews them
        self.turn_pulse = float(os.getenv("TURN_PULSE_S", 0.12))  # s - short turn bursts so it doesn't overshoot
        self.turn_settle = 0.15  # s - pause after a turn so the camera gets a sharp frame
        self.lost_grace = 0.6  # s - wait this long before searching (pose models drop single frames)
        self.search_pulse = 0.15
        self.search_pause = 0.45
        self.search_timeout = float(os.getenv("SEARCH_TIMEOUT_S", 25))
        self.is_running = False
        self.state = "idle"
        self.person_position = None  # (x, y, distance) in camera coordinates
        self.last_person_position = None
        self._lost_since = None
        self._next_turn_at = 0.0
        self.frame_width = 640
        self.frame_height = 480

    def start(self):#to start the robot
        """Start autonomous following"""
        self.is_running = True
        self._lost_since = None
        self.state = "searching"
        print("Autonomous mode started")

    def stop(self):#stoping movment
        """Stop autonomous following"""
        self.is_running = False
        self.state = "idle"
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

        if self.pose is None:
            self.pose = pose_utils.create_landmarker(video=False, complexity=1)
        landmarks = pose_utils.detect_landmarks(self.pose, frame)

        if landmarks and self.has_body(landmarks):
            commands = self.follow_landmarks(landmarks)
            return True, commands
        self.search_last_direction()
        return False, {"action": self.robot.last_action if self.robot else "stop"}

    @staticmethod
    def has_body(landmarks) -> bool:
        """True if enough of a person is visible to follow (the low car camera often sees only hips/legs up close)"""
        return any(pose_utils.visibility(landmarks[i]) > 0.25 for i in FOLLOW_LANDMARKS)

    def lose_person(self):#If the person is not found for use to see
        self.person_position = None
        if self.robot:
            self.robot.stop()

    def search_last_direction(self):
        """Person not in view: wait briefly, then turn toward where they were last seen in short
        bursts with pauses (spinning nonstop blurs every frame). Never drives forward blind."""
        self.person_position = None
        if not self.is_running or not self.robot:
            return
        now = time.monotonic()
        if self._lost_since is None:
            self._lost_since = now
        lost_for = now - self._lost_since
        if lost_for < self.lost_grace:
            self.state = "waiting"
            self.robot.stop()
            return
        if lost_for > self.search_timeout:
            self.state = "idle"
            self.robot.stop()
            return
        self.state = "searching"
        if now >= self._next_turn_at:
            last_x = self.last_person_position["x"] if self.last_person_position else 0.6
            self.robot.drive("spin_left" if last_x < 0.5 else "spin_right", self.search_pulse)
            self._next_turn_at = now + self.search_pulse + self.search_pause

    def follow_landmarks(self, landmarks) -> dict:
        if not self.is_running:
            return {"action": "stop"}
        self._lost_since = None

        # Center of whatever body points are visible (works when the head or legs are out of frame)
        vis_pts = [landmarks[i] for i in FOLLOW_LANDMARKS if pose_utils.visibility(landmarks[i]) > 0.25]
        if not vis_pts:
            vis_pts = [landmarks[pose_utils.LEFT_SHOULDER], landmarks[pose_utils.RIGHT_SHOULDER]]
        center_x = sum(pt.x for pt in vis_pts) / len(vis_pts)
        center_y = sum(pt.y for pt in vis_pts) / len(vis_pts)

        estimated_distance = self._estimate_distance(landmarks)

        # Store position
        self.person_position = {
            "x": center_x,
            "y": center_y,
            "distance": estimated_distance,
            "confidence": 0.9
        }
        self.last_person_position = self.person_position

        # Calculate control commands
        control_commands = self._calculate_control_commands(center_x, estimated_distance)

        # Execute commands
        self._execute_commands(control_commands)

        return control_commands

    def _estimate_distance(self, landmarks) -> float:
        """
        Estimate distance to person from how wide their shoulders (or hips) look in the image

        Returns:
            Estimated distance in cm
        """
        # Calibrated values (adjust based on your camera and setup)
        known_distance = 100  # cm (calibration distance)
        known_shoulder_width_in_image = 0.3  # fraction of image width at calibration distance

        vis = pose_utils.visibility
        ls, rs = landmarks[pose_utils.LEFT_SHOULDER], landmarks[pose_utils.RIGHT_SHOULDER]
        lh, rh = landmarks[pose_utils.LEFT_HIP], landmarks[pose_utils.RIGHT_HIP]
        if vis(ls) > 0.3 and vis(rs) > 0.3:
            width = abs(ls.x - rs.x)
        elif vis(lh) > 0.3 and vis(rh) > 0.3:
            width = abs(lh.x - rh.x) / 0.7  # hip keypoints sit ~70% as wide as shoulders
        else:
            # Only legs/feet in view: the person is towering over the low camera, so treat as arrived
            return self.target_distance
        if width > 0.02:
            return (known_shoulder_width_in_image / width) * known_distance
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
        horizontal_offset = center_x - 0.5  # -0.5 (far left) to 0.5 (far right)
        side = "left" if horizontal_offset < 0 else "right"
        commands = {"action": "stop", "distance": round(distance, 1), "offset": round(horizontal_offset, 3)}

        if abs(horizontal_offset) > self.spin_zone:
            # Way off to one side - turn in place toward them
            commands["action"] = f"spin_{side}"
        elif abs(horizontal_offset) > self.dead_zone:
            # A bit off center - curve toward them while driving, or turn in place if already close
            commands["action"] = f"arc_{side}" if distance > self.target_distance else f"spin_{side}"
        elif distance > self.target_distance:
            commands["action"] = "forward"
        elif distance < self.min_distance:
            commands["action"] = "backward"
        else:
            commands["action"] = "stop"  # close enough and centered - stay next to them
        return commands

    def _execute_commands(self, commands: dict):
        """Execute robot control commands"""
        action = commands.get("action", "stop")
        self.state = {"stop": "arrived", "forward": "approaching", "backward": "backing_up"}.get(action, "turning")
        if not self.robot:
            print(f"Simulation: {commands}")
            return

        if action.startswith("spin_"):
            now = time.monotonic()
            if now < self._next_turn_at:
                # Still settling from the last turn burst - hold still for a sharp frame
                self.robot.stop()
                return
            self.robot.drive(action, self.turn_pulse)
            self._next_turn_at = now + self.turn_pulse + self.turn_settle
        elif action == "stop":
            self.robot.stop()
        else:
            # forward / backward / arc: keeps going only while new frames keep renewing it
            self.robot.drive(action, self.drive_hold)

    def get_person_position(self) -> Optional[dict]:
        """Get current person position"""
        return self.person_position

    def is_person_detected(self) -> bool:
        """Check if person is currently detected"""
        return self.person_position is not None


FOLLOW_LANDMARKS = [
    pose_utils.NOSE,
    pose_utils.LEFT_SHOULDER, pose_utils.RIGHT_SHOULDER,
    pose_utils.LEFT_HIP, pose_utils.RIGHT_HIP,
    pose_utils.LEFT_KNEE, pose_utils.RIGHT_KNEE,
]


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

    #THE END dum dum dum!!!!!
