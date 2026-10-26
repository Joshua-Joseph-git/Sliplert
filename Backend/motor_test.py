#Motor check for the robot car - run this ON THE PI with the car lifted off the ground:
#   sudo systemctl stop sliplert      (so main.py lets go of the GPIO pins)
#   .venv/bin/python motor_test.py
#Watch each step and fix the .env settings it tells you about.
import os
import sys
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from autonomous_controller import MotorDriver

STEPS = [
    ("forward", "BOTH wheels roll FORWARD (toward where the camera points)"),
    ("arc_right", "ONLY the LEFT wheel rolls forward"),
    ("arc_left", "ONLY the RIGHT wheel rolls forward"),
    ("spin_left", "car spins LEFT (counter-clockwise seen from above)"),
    ("spin_right", "car spins RIGHT (clockwise seen from above)"),
    ("backward", "BOTH wheels roll BACKWARD"),
]


def main():
    driver = MotorDriver()
    if not driver.available:
        print(f"\nMotors are NOT working: {driver.error}")
        sys.exit(1)
    print(f"\nPins in use: {driver.config}\n")
    seconds = float(os.getenv("MOTOR_TEST_SECONDS", 1.5))
    try:
        for action, expected in STEPS:
            print(f"-> {action:<11} expected: {expected}")
            driver.drive(action)
            time.sleep(seconds)
            driver.stop()
            time.sleep(1.0)
    finally:
        driver.stop()

    print("""
What to change in Backend/.env if a step looked wrong:
  * Nothing moved at all       -> check the L298N ENA/ENB jumpers are on, the motor battery is
                                  charged, and a GND wire joins the Pi and the L298N.
  * Only one wheel ever moves  -> check that motor's wires/IN pins on the L298N.
  * LEFT wheel went backward   -> flip ROBOT_REVERSE_LEFT  (1 <-> 0)
  * RIGHT wheel went backward  -> flip ROBOT_REVERSE_RIGHT (1 <-> 0)
  * "only LEFT" moved the right wheel (spins are mirrored) -> set ROBOT_SWAP_SIDES=1
Then run this test again until every step matches, and restart: sudo systemctl start sliplert""")


if __name__ == "__main__":
    main()
