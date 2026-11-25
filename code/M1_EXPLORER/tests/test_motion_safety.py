#!/usr/bin/env python3

# R0B0T1CS LAB
# M1 EXPLORER
# Motion Safety Supervisor - Integration Tests
# Version: 1.0

import math
import time

import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Twist
from std_msgs.msg import String
from std_srvs.srv import Trigger


class SafetyTester(Node):

    def __init__(self):

        super().__init__('motion_safety_tester')

        self.status = None
        self.output = None
        self.output_time = None
        self.results = []

        self.publisher = self.create_publisher(
            Twist, '/cmd_vel_input', 1
        )

        self.status_sub = self.create_subscription(
            String,
            '/motion_safety/status',
            self.status_callback,
            10
        )

        self.output_sub = self.create_subscription(
            Twist,
            '/cmd_vel',
            self.output_callback,
            10
        )

        self.service_clients = {}

        for service in (
            'arm',
            'disarm',
            'reset',
            'emergency_stop'
        ):

            self.service_clients[service] = self.create_client(
                Trigger,
                f'/motion_safety/{service}'
            )

    def status_callback(self, msg):

        self.status = msg.data

    def output_callback(self, msg):

        self.output = msg
        self.output_time = time.monotonic()

    def spin_for(self, duration):

        end = time.monotonic() + duration

        while rclpy.ok() and time.monotonic() < end:

            rclpy.spin_once(self, timeout_sec=0.02)

    def send_command(
        self,
        vx=0.0,
        vy=0.0,
        wz=0.0,
        duration=0.5
    ):

        msg = Twist()

        msg.linear.x = float(vx)
        msg.linear.y = float(vy)
        msg.angular.z = float(wz)

        end = time.monotonic() + duration

        while rclpy.ok() and time.monotonic() < end:

            self.publisher.publish(msg)
            self.spin_for(0.05)

    def call_service(self, name):

        client = self.service_clients[name]

        if not client.wait_for_service(timeout_sec=3.0):
            raise RuntimeError(f'Service unavailable: {name}')

        future = client.call_async(Trigger.Request())

        rclpy.spin_until_future_complete(
            self,
            future,
            timeout_sec=2.0
        )

        if not future.done() or future.result() is None:
            raise RuntimeError(f'Service call failed: {name}')

        return future.result()

    def output_is_zero(self):

        if self.output is None or self.output_time is None:
            return False

        if time.monotonic() - self.output_time > 0.25:
            return False

        values = (
            self.output.linear.x,
            self.output.linear.y,
            self.output.linear.z,
            self.output.angular.x,
            self.output.angular.y,
            self.output.angular.z
        )

        return all(abs(value) < 1e-6 for value in values)

    def check(self, name, condition):

        passed = bool(condition)

        self.results.append((name, passed))

        print(
            f'{"PASS" if passed else "FAIL"} | {name}',
            flush=True
        )

        # Abort testing immediately after any failure.
        if not passed:
            raise RuntimeError(f'Test failed: {name}')

    def run_tests(self):

        print('\n=== M1 EXPLORER SAFETY TESTS ===\n')

        self.call_service('reset')
        self.spin_for(1.5)

        # SAF-01: Motion forbidden when disarmed

        self.send_command(vx=0.05)

        self.check(
            'SAF-01 - Disarmed motion rejected',
            self.output_is_zero()
        )

        # SAF-02: Arm without a fresh zero command

        response = self.call_service('arm')

        self.check(
            'SAF-02 - Unsafe arming rejected',
            not response.success
        )

        # SAF-03: Safe arming

        self.send_command()

        response = self.call_service('arm')

        self.check(
            'SAF-03 - Safe arming accepted',
            response.success and self.status == 'ARMED'
        )

        # SAF-04: Normal motion

        self.send_command(
            vx=0.05,
            duration=0.5
        )

        self.check(
            'SAF-04 - Motion command forwarded',
            self.output is not None
            and abs(self.output.linear.x - 0.05) < 0.001
        )

        # SAF-05: Velocity limitation

        self.send_command(
            vx=0.30,
            vy=0.30,
            duration=0.5
        )

        speed = math.hypot(
            self.output.linear.x,
            self.output.linear.y
        )

        self.check(
            'SAF-05 - Linear speed limited',
            abs(speed - 0.15) < 0.001
        )

        # SAF-06: Stop publishing input commands

        print('Testing command loss...')

        self.spin_for(1.0)

        self.check(
            'SAF-06 - Watchdog timeout',
            self.status == 'TIMEOUT'
            and self.output_is_zero()
        )

        # SAF-07: Communication returns

        self.send_command(vx=0.05)

        self.check(
            'SAF-07 - Automatic restart prevented',
            self.status == 'TIMEOUT'
            and self.output_is_zero()
        )

        # SAF-08: Reset

        response = self.call_service('reset')
        self.spin_for(0.2)

        self.check(
            'SAF-08 - Reset to DISARMED',
            response.success
            and self.status == 'DISARMED'
            and self.output_is_zero()
        )

        # SAF-09: Emergency stop

        self.send_command()

        response = self.call_service('arm')

        if not response.success:
            raise RuntimeError('Could not arm for stop test')

        self.send_command(
            vx=0.05,
            duration=0.5
        )

        response = self.call_service('emergency_stop')

        self.spin_for(0.2)

        self.check(
            'SAF-09 - Software emergency stop',
            response.success
            and self.status == 'EMERGENCY_STOP'
            and self.output_is_zero()
        )

        # SAF-10: Restart forbidden

        self.send_command()

        response = self.call_service('arm')

        self.check(
            'SAF-10 - Emergency stop remains latched',
            not response.success
            and self.output_is_zero()
        )

    def finish(self):

        # Request a software stop before exiting.

        try:
            self.send_command(duration=0.2)
            self.call_service('emergency_stop')

        except Exception as error:

            print(f'WARNING: Stop request failed: {error}')

        passed = sum(result for _, result in self.results)

        print('\n=== TEST SUMMARY ===')
        print(f'Passed: {passed}/10')
        print('Supervisor requested state: EMERGENCY_STOP')


def main(args=None):

    rclpy.init(args=args)

    node = SafetyTester()

    try:

        node.run_tests()

    except KeyboardInterrupt:

        print('\nTest interrupted.')

    except Exception as error:

        print(f'\nERROR: {error}')

    finally:

        if rclpy.ok():

            node.finish()

        node.destroy_node()

        if rclpy.ok():

            rclpy.shutdown()


if __name__ == '__main__':

    main()