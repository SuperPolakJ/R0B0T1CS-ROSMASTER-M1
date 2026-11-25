#!/usr/bin/env python3
"""First bench test — no motion without explicit --bench flag."""
import argparse
import rclpy
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "controllers"))

from m1_motion_controller import M1MotionController


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bench', action='store_true', required=True,
                        help='Confirm wheels off floor and physical stop accessible')
    parser.parse_args()
    rclpy.init()
    robot = M1MotionController()
    success = False
    try:
        robot.connect()
        print(f'Connected | battery: {robot.get_battery():.2f} V | velocity: {robot.get_velocity()}', flush=True)
        robot.arm()
        print('ARMED | forward 0.05 m/s for 1 s', flush=True)
        robot.forward(.05, 1.0)
        robot.disarm()
        print('PASS | DISARMED / NONE / zero command; verify wheels stopped', flush=True)
        success = True
    except (Exception, KeyboardInterrupt) as exc:
        print('ABORT:', exc, flush=True)
    finally:
        if robot.owns_session:
            robot._abort()
        robot.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
