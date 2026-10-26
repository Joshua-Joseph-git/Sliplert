#Automatic checks for the robot logic - no real motors, camera, or email needed.
#Run from the Backend folder:   python -m unittest test_robot_logic -v
#(uses gpiozero's fake "mock" pins, so it is safe on the Pi with the car on the floor)
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

os.environ.setdefault("GPIOZERO_PIN_FACTORY", "mock")
os.environ["ROBOT_CAMERA"] = "off"
os.environ["AUTONOMOUS_ON_START"] = "off"
os.environ.pop("SMTP_EMAIL", None)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pose_utils
import autonomous_controller as ac
from pose_utils import Landmark

try:
    from gpiozero import Device
    from gpiozero.pins.mock import MockFactory
    HAVE_GPIOZERO = True
except ImportError:
    HAVE_GPIOZERO = False


def make_person(cx=0.5, shoulder_width=0.15, lying=False, top=0.2, vis=0.9):
    """33 landmarks for a person centered at cx. Hidden points get visibility 0."""
    lms = [Landmark(0.5, 0.5, 0.0, 0.0) for _ in range(33)]
    half = shoulder_width / 2
    if lying:
        # body horizontal across the frame at height 0.8
        pts = {pose_utils.NOSE: (cx - 0.3, 0.78), pose_utils.LEFT_SHOULDER: (cx - 0.2, 0.75), pose_utils.RIGHT_SHOULDER: (cx - 0.2, 0.85),
               pose_utils.LEFT_HIP: (cx + 0.05, 0.76), pose_utils.RIGHT_HIP: (cx + 0.05, 0.84),
               pose_utils.LEFT_KNEE: (cx + 0.2, 0.77), pose_utils.RIGHT_KNEE: (cx + 0.2, 0.83),
               pose_utils.LEFT_ANKLE: (cx + 0.35, 0.78), pose_utils.RIGHT_ANKLE: (cx + 0.35, 0.82)}
    else:
        pts = {pose_utils.NOSE: (cx, top), pose_utils.LEFT_SHOULDER: (cx + half, top + 0.1), pose_utils.RIGHT_SHOULDER: (cx - half, top + 0.1),
               pose_utils.LEFT_HIP: (cx + half * 0.7, top + 0.35), pose_utils.RIGHT_HIP: (cx - half * 0.7, top + 0.35),
               pose_utils.LEFT_KNEE: (cx + half * 0.7, top + 0.55), pose_utils.RIGHT_KNEE: (cx - half * 0.7, top + 0.55),
               pose_utils.LEFT_ANKLE: (cx + half * 0.7, top + 0.75), pose_utils.RIGHT_ANKLE: (cx - half * 0.7, top + 0.75)}
    for i, (x, y) in pts.items():
        lms[i] = Landmark(x, y, 0.0, vis)
    return lms


class FakeDriver:
    """Records what the controller asks the motors to do."""
    available = True
    error = None

    def __init__(self):
        self.calls = []
        self.last_action = "stop"

    def drive(self, action, duration=None):
        self.calls.append((action, duration))
        self.last_action = action

    def stop(self):
        self.drive("stop")


@unittest.skipUnless(HAVE_GPIOZERO, "gpiozero not installed")
class MotorDriverTests(unittest.TestCase):
    def setUp(self):
        Device.pin_factory = MockFactory()

    def tearDown(self):
        Device.pin_factory.reset()

    def pins(self, *nums):
        return tuple(int(Device.pin_factory.pin(n).state) for n in nums)

    def make(self, **env):
        base = {"ROBOT_LEFT_FORWARD_PIN": "5", "ROBOT_LEFT_BACKWARD_PIN": "6",
                "ROBOT_RIGHT_FORWARD_PIN": "13", "ROBOT_RIGHT_BACKWARD_PIN": "19"}
        base.update(env)
        with mock.patch.dict(os.environ, base):
            d = ac.MotorDriver()
        self.assertTrue(d.available, d.error)
        return d

    def test_default_reversed_polarity(self):
        # Car is wired reversed: logical forward must energize the *backward* pins (6 and 19)
        d = self.make()
        d.drive("forward")
        self.assertEqual(self.pins(5, 6, 13, 19), (0, 1, 0, 1))
        d.drive("backward")
        self.assertEqual(self.pins(5, 6, 13, 19), (1, 0, 1, 0))
        d.stop()
        self.assertEqual(self.pins(5, 6, 13, 19), (0, 0, 0, 0))

    def test_normal_polarity_and_turns(self):
        d = self.make(ROBOT_REVERSE_LEFT="0", ROBOT_REVERSE_RIGHT="0")
        d.drive("forward")
        self.assertEqual(self.pins(5, 6, 13, 19), (1, 0, 1, 0))
        d.drive("spin_left")   # left wheel back, right wheel forward
        self.assertEqual(self.pins(5, 6, 13, 19), (0, 1, 1, 0))
        d.drive("spin_right")
        self.assertEqual(self.pins(5, 6, 13, 19), (1, 0, 0, 1))
        d.drive("arc_left")    # only right wheel
        self.assertEqual(self.pins(5, 6, 13, 19), (0, 0, 1, 0))
        d.drive("arc_right")   # only left wheel
        self.assertEqual(self.pins(5, 6, 13, 19), (1, 0, 0, 0))

    def test_swap_sides(self):
        d = self.make(ROBOT_REVERSE_LEFT="0", ROBOT_REVERSE_RIGHT="0", ROBOT_SWAP_SIDES="1")
        d.drive("arc_right")   # "left" wheel is now on the right-side pins
        self.assertEqual(self.pins(5, 6, 13, 19), (0, 0, 1, 0))

    def test_watchdog_stops_timed_moves(self):
        d = self.make()
        d.drive("forward", 0.15)
        self.assertNotEqual(self.pins(6, 19), (0, 0))
        time.sleep(0.35)
        self.assertEqual(self.pins(5, 6, 13, 19), (0, 0, 0, 0))
        self.assertEqual(d.last_action, "stop")

    def test_renewed_move_keeps_going(self):
        d = self.make()
        for _ in range(6):
            d.drive("forward", 0.15)
            time.sleep(0.08)
        self.assertEqual(self.pins(6, 19), (1, 1))
        d.stop()

    def test_untimed_move_does_not_auto_stop(self):
        d = self.make()
        d.drive("forward")
        time.sleep(0.2)
        self.assertEqual(self.pins(6, 19), (1, 1))
        d.stop()

    def test_bad_action_rejected(self):
        d = self.make()
        with self.assertRaises(ValueError):
            d.drive("fly")


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.drv = FakeDriver()
        self.c = ac.AutonomousController(robot=self.drv, create_hardware=False)
        self.c.start()

    def act(self, lms):
        return self.c.follow_landmarks(lms)["action"]

    def test_far_and_centered_drives_forward(self):
        self.assertEqual(self.act(make_person(0.5, 0.12)), "forward")
        self.assertEqual(self.drv.calls[-1], ("forward", self.c.drive_hold))

    def test_close_and_centered_stops(self):
        # shoulder width 0.43 of frame ~ 70cm away
        self.assertEqual(self.act(make_person(0.5, 0.45)), "stop")

    def test_too_close_backs_up(self):
        self.assertEqual(self.act(make_person(0.5, 0.9)), "backward")

    def test_only_legs_visible_counts_as_arrived(self):
        lms = make_person(0.5, 0.12)
        for i in (pose_utils.NOSE, pose_utils.LEFT_SHOULDER, pose_utils.RIGHT_SHOULDER, pose_utils.LEFT_HIP, pose_utils.RIGHT_HIP):
            lms[i] = Landmark(lms[i].x, lms[i].y, 0, 0.05)
        self.assertTrue(self.c.has_body(lms))
        self.assertEqual(self.act(lms), "stop")

    def test_steering_direction(self):
        self.assertEqual(self.act(make_person(0.70, 0.12)), "arc_right")
        self.assertEqual(self.act(make_person(0.30, 0.12)), "arc_left")
        self.c._next_turn_at = 0
        self.assertEqual(self.act(make_person(0.92, 0.12)), "spin_right")
        self.c._next_turn_at = 0
        self.assertEqual(self.act(make_person(0.08, 0.12)), "spin_left")

    def test_spins_are_short_pulses_with_settle(self):
        self.act(make_person(0.92, 0.12))
        self.assertEqual(self.drv.calls[-1], ("spin_right", self.c.turn_pulse))
        self.act(make_person(0.92, 0.12))  # next frame, still settling
        self.assertEqual(self.drv.calls[-1][0], "stop")

    def test_lost_person_never_drives_forward(self):
        self.act(make_person(0.75, 0.12))
        self.drv.calls.clear()
        t0 = time.monotonic()
        with mock.patch.object(ac.time, "monotonic") as mono:
            for k in range(200):  # 20 simulated seconds at 10 fps
                mono.return_value = t0 + k * 0.1
                self.c.search_last_direction()
        actions = {a for a, _ in self.drv.calls}
        self.assertNotIn("forward", actions)
        self.assertIn("spin_right", actions)          # turns toward where they were last seen
        self.assertNotIn("spin_left", actions)
        self.assertEqual(self.drv.calls[0][0], "stop")  # waits first instead of reacting to one dropped frame
        for a, d in self.drv.calls:
            if a != "stop":
                self.assertIsNotNone(d, "search moves must be timed")

    def test_search_gives_up(self):
        t0 = time.monotonic()
        with mock.patch.object(ac.time, "monotonic") as mono:
            mono.return_value = t0
            self.c.search_last_direction()
            mono.return_value = t0 + self.c.search_timeout + 1
            self.c.search_last_direction()
        self.assertEqual(self.drv.calls[-1][0], "stop")
        self.assertEqual(self.c.state, "idle")

    def test_not_running_does_nothing(self):
        self.c.stop()
        self.drv.calls.clear()
        self.c.follow_landmarks(make_person())
        self.c.search_last_direction()
        self.assertEqual(self.drv.calls, [])


class FakeSession:
    """Stands in for MoveNet: 'detects' the single bright dot in the 192x192 input, but only
    gives a confident score for the image orientation/zoom chosen by the test."""

    class _In:
        name = "input"

    def __init__(self, confident_call):
        self.confident_call = confident_call
        self.n = 0

    def get_inputs(self):
        return [self._In()]

    def run(self, _, feeds):
        img = feeds["input"][0].sum(axis=2)
        y, x = np.unravel_index(np.argmax(img), img.shape)
        score = 0.9 if self.n == self.confident_call else 0.1
        self.n += 1
        out = np.zeros((1, 1, 17, 3), dtype=np.float32)
        out[0, 0, :, 0] = (y + 0.5) / 192
        out[0, 0, :, 1] = (x + 0.5) / 192
        out[0, 0, :, 2] = score
        return [out]


class PoseGeometryTests(unittest.TestCase):
    """A bright dot stands in for the person: wherever the engine 'sees' it (full frame, zoomed
    crop, or rotated 90 degrees), the returned landmark must land back on the dot's real spot."""

    def frame_with_dot(self, dot_xy):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        px, py = int(dot_xy[0] * 640), int(dot_xy[1] * 480)
        frame[py - 6:py + 6, px - 6:px + 6] = 255
        return frame

    def assert_on_dot(self, lms, dot_xy):
        self.assertIsNotNone(lms)
        nose = lms[pose_utils.NOSE]
        self.assertAlmostEqual(nose.x, dot_xy[0], delta=0.03)
        self.assertAlmostEqual(nose.y, dot_xy[1], delta=0.03)

    def check_movenet(self, confident_call, dot_xy=(0.70, 0.30)):
        with mock.patch.object(pose_utils, "MP_AVAILABLE", False):
            lms = pose_utils.detect_landmarks(FakeSession(confident_call), self.frame_with_dot(dot_xy))
        self.assert_on_dot(lms, dot_xy)

    def check_mediapipe(self, confident_call, dot_xy=(0.70, 0.30)):
        calls = {"n": 0}

        def fake_single(_landmarker, img):
            g = img.sum(axis=2)
            y, x = np.unravel_index(np.argmax(g), g.shape)
            score = 0.9 if calls["n"] == confident_call else 0.1
            calls["n"] += 1
            return [Landmark((x + 0.5) / g.shape[1], (y + 0.5) / g.shape[0], 0.0, score) for _ in range(33)]

        with mock.patch.object(pose_utils, "MP_AVAILABLE", True), \
             mock.patch.object(pose_utils, "_mp_detect_single", side_effect=fake_single):
            lms = pose_utils.detect_landmarks(None, self.frame_with_dot(dot_xy))
        self.assert_on_dot(lms, dot_xy)

    def test_movenet_full_frame_letterboxed(self):
        self.check_movenet(0)

    def test_movenet_zoom_crops(self):
        self.check_movenet(1, (0.6, 0.4))
        self.check_movenet(2, (0.55, 0.45))

    def test_movenet_rotated_passes_map_back_correctly(self):
        self.check_movenet(3)  # 90 deg counter-clockwise pass
        self.check_movenet(4)  # 90 deg clockwise pass

    def test_mediapipe_rotated_passes_map_back_correctly(self):
        self.check_mediapipe(0)
        self.check_mediapipe(1, (0.6, 0.4))
        self.check_mediapipe(2)
        self.check_mediapipe(3)


class FallDetectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import main
        cls.main = main

    def test_standing_is_not_a_fall(self):
        det = self.main.FallDetector()
        for _ in range(8):
            self.assertFalse(det.analyze_pose(make_person())["is_fall"])

    def test_lying_is_a_fall(self):
        det = self.main.FallDetector()
        self.assertTrue(det.analyze_pose(make_person(0.5, lying=True))["is_fall"])

    def test_lying_with_head_mid_frame_is_a_fall(self):
        # Seen on real photos: head in the upper half of the frame and one hip barely visible
        det = self.main.FallDetector()
        lms = make_person(0.5, lying=True)
        for i in list(range(33)):
            lms[i] = Landmark(lms[i].x, lms[i].y - 0.4, 0, lms[i].visibility)
        lms[pose_utils.RIGHT_HIP] = Landmark(lms[pose_utils.RIGHT_HIP].x, lms[pose_utils.RIGHT_HIP].y, 0, 0.28)
        self.assertLess(lms[pose_utils.NOSE].y, 0.45)
        self.assertTrue(det.analyze_pose(lms)["is_fall"])

    def test_hidden_shoulders_never_alarm(self):
        det = self.main.FallDetector()
        lms = make_person(0.5, lying=True)
        lms[pose_utils.LEFT_SHOULDER] = Landmark(0.1, 0.1, 0, 0.1)
        lms[pose_utils.RIGHT_SHOULDER] = Landmark(0.9, 0.9, 0, 0.1)
        self.assertFalse(det.analyze_pose(lms)["is_fall"])


class ApiAndLoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import main
        from fastapi.testclient import TestClient
        cls.main = main
        cls.tmp = tempfile.mkdtemp()
        main.CONTACTS_FILE = os.path.join(cls.tmp, "contacts.json")
        main.FALL_HISTORY_FILE = os.path.join(cls.tmp, "falls.json")
        cls.sent = []
        cls._email_patch = mock.patch.object(main, "_send_emergency_email",
                                             side_effect=lambda to, name, rec: (cls.sent.append(to) or (True, "test", None)))
        cls._email_patch.start()
        cls.client = TestClient(main.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        cls._email_patch.stop()

    def setUp(self):
        self.main.emergency_contacts.clear()
        self.main.save_contacts_to_file()
        self.sent.clear()

    def test_manual_drive_auto_stops(self):
        # Dashboard's "▼ Forward" button sends "backward" (reversed-wiring naming)
        r = self.client.post("/robot/control", json={"action": "backward", "duration": 0.2}).json()
        self.assertIn(r["status"], ("success", "simulation"))
        self.assertEqual(self.main.robot.last_action, "forward")
        time.sleep(0.4)
        self.assertEqual(self.main.robot.last_action, "stop")
        self.assertFalse(self.main.is_autonomous)

    def test_dashboard_tap_drives_until_stop(self):
        # The dashboard sends one command per click (no duration) and expects motion until Stop
        self.client.post("/robot/control", json={"action": "forward", "speed": 100})
        time.sleep(0.8)
        self.assertEqual(self.main.robot.last_action, "backward")  # "▲ Backward" button
        self.client.post("/robot/control", json={"action": "stop"})
        self.assertEqual(self.main.robot.last_action, "stop")

    def test_manual_turn_maps_to_spin(self):
        self.client.post("/robot/control", json={"action": "left"})
        self.assertEqual(self.main.robot.last_action, "spin_left")
        self.client.post("/robot/control", json={"action": "stop"})
        self.assertEqual(self.main.robot.last_action, "stop")

    def test_invalid_manual_action(self):
        self.assertEqual(self.client.post("/robot/control", json={"action": "jump"}).status_code, 400)

    def test_enabling_autonomous_does_not_lurch(self):
        with mock.patch.object(self.main, "_start_camera_loop"):
            self.main.robot.stop()
            r = self.client.post("/robot/autonomous", json={"enabled": True}).json()
        self.assertTrue(r["status"])
        self.assertEqual(self.main.robot.last_action, "stop")
        self.client.post("/robot/autonomous", json={"enabled": False})

    def test_status_reports_motor_health(self):
        s = self.client.get("/robot/status").json()
        for key in ("gpio_available", "motor_error", "motor_action", "follow_state", "camera_error", "smtp_configured"):
            self.assertIn(key, s)

    def test_contacts_dedupe_and_delete(self):
        add = lambda p: self.client.post("/emergency-contacts", json={"name": "Mom", "phone": p, "relationship": "Mother"}).json()
        first = add("Mom@Example.com")["contact"]
        add(" mom@example.com ")
        self.assertEqual(len(self.client.get("/emergency-contacts").json()["contacts"]), 1)
        add("(555) 123-4567")
        add("+15551234567")
        self.assertEqual(len(self.client.get("/emergency-contacts").json()["contacts"]), 2)
        self.client.delete(f"/emergency-contacts/{first['id']}")
        left = self.client.get("/emergency-contacts").json()["contacts"]
        self.assertEqual([c["phone"] for c in left], ["(555) 123-4567"])

    def test_simulated_fall_reports_real_delivery(self):
        self.client.post("/emergency-contacts", json={"name": "Dad", "phone": "dad@example.com", "relationship": "Father"})
        r = self.client.post("/detect-fall-base64", json={"simulate": True}).json()
        self.assertTrue(r["fall_detected"])
        self.assertIn("timestamp", r)
        for _ in range(50):
            last = self.client.get("/robot/status").json()["last_fall"]
            if last and last["delivery"] and last["delivery"][0]["status"] != "sending":
                break
            time.sleep(0.05)
        self.assertEqual(last["timestamp"], r["timestamp"])
        self.assertEqual(last["delivery"][0]["status"], "sent")
        self.assertEqual(self.sent, ["dad@example.com"])
        # the test button works again right away (bypasses cooldown)
        self.client.post("/detect-fall-base64", json={"simulate": True})
        time.sleep(0.3)
        self.assertEqual(len(self.sent), 2)

    def test_failed_email_is_reported_as_failed(self):
        self.client.post("/emergency-contacts", json={"name": "Sis", "phone": "sis@example.com", "relationship": "Sister"})
        with mock.patch.object(self.main, "_send_emergency_email", return_value=(False, "none", "port 25 blocked")):
            self.client.post("/detect-fall-base64", json={"simulate": True})
            time.sleep(0.3)
        d = self.client.get("/robot/status").json()["last_fall"]["delivery"][0]
        self.assertEqual((d["status"], d["error"]), ("failed", "port 25 blocked"))

    def test_camera_loop_follows_then_alerts_once(self):
        """Feeds the real camera loop scripted 'frames': person far right -> centered far -> lying on the floor."""
        m = self.main
        self.client.post("/emergency-contacts", json={"name": "Dad", "phone": "dad@example.com", "relationship": "Father"})
        script = ([make_person(0.85, 0.12)] * 3 + [make_person(0.5, 0.12)] * 5 + [None] * 3
                  + [make_person(0.5, lying=True)] * 12)
        frames = iter(range(len(script)))
        idx = {"i": -1}
        actions = []
        done = threading.Event()

        def read_frame():
            try:
                idx["i"] = next(frames)
            except StopIteration:
                done.set()
                m.stop_event.set()
                return None
            time.sleep(0.11)
            return np.zeros((480, 640, 3), dtype=np.uint8)

        def fake_detect(_pose, _frame, _ts=None):
            return script[idx["i"]]

        real_drive = m.robot.drive

        def spy_drive(action, duration=None):
            actions.append(action)  # record every command (a 0.12s turn burst is easy to miss by sampling)
            real_drive(action, duration)

        m.last_alert_time = 0.0
        m.camera_state["last_fall"] = None
        m.is_autonomous = True
        m.follower.start()
        m.stop_event.clear()
        with mock.patch.object(m, "open_camera", return_value=(read_frame, lambda: None)), \
             mock.patch.object(m.pose_utils, "create_landmarker", return_value=None), \
             mock.patch.object(m.pose_utils, "detect_landmarks", side_effect=fake_detect), \
             mock.patch.object(m.pose_utils, "draw_landmarks"),              mock.patch.object(m.robot, "drive", side_effect=spy_drive):
            t = threading.Thread(target=m.robot_camera_loop)
            t.start()
            t.join(15)
        self.assertFalse(t.is_alive())
        first_forward = actions.index("forward")
        self.assertIn("spin_right", actions[:first_forward])  # turned toward the person on the right first
        self.assertNotIn("spin_left", actions)
        self.assertIsNotNone(m.camera_state["last_fall"])
        time.sleep(0.3)
        self.assertEqual(self.sent, ["dad@example.com"])   # one email, not one every 3 frames
        self.assertEqual(m.robot.last_action, "stop")
        m.stop_event.clear()


if __name__ == "__main__":
    unittest.main(verbosity=2)
