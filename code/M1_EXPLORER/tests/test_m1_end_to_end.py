#!/usr/bin/env python3
"""M1 EXPLORER — supervised bench test; wheels clear of floor."""
import time
import math
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import String
from std_srvs.srv import Trigger


class BenchTest(Node):
    def __init__(self):
        super().__init__('m1_end_to_end_tester')
        self.pub = self.create_publisher(Twist, '/cmd_vel_python', 1)
        self.samples = {}
        self.count = 0
        self.subs = []
        for topic, kind in [('/motion_safety/status', String),
                            ('/command_mux/source', String),
                            ('/cmd_vel', Twist), ('/cmd_vel_joy', Twist)]:
            self.subs.append(self.create_subscription(
                kind, topic, lambda msg, t=topic: self.record(t, msg), 1))
        self.service_clients = {}
        for name in ['motion_safety/arm', 'motion_safety/disarm',
                     'motion_safety/reset', 'motion_safety/emergency_stop',
                     'command_mux/select_python', 'command_mux/select_joy',
                     'command_mux/select_none']:
            self.service_clients[name] = self.create_client(Trigger, '/' + name)

    def record(self, topic, msg):
        self.samples[topic] = (time.monotonic(), msg)

    def latest(self, topic, age=2.0):
        stamp, msg = self.samples.get(topic, (0, None))
        return msg if time.monotonic() - stamp < age else None

    def state(self, topic, value):
        msg = self.latest(topic)
        return msg is not None and msg.data == value

    @staticmethod
    def vector(msg):
        return (msg.linear.x, msg.linear.y, msg.linear.z,
                msg.angular.x, msg.angular.y, msg.angular.z)

    def output(self, vx=0.0):
        msg = self.latest('/cmd_vel', 0.25)
        return msg is not None and all(abs(a-b) < 0.001 for a, b in
            zip(self.vector(msg), (vx, 0, 0, 0, 0, 0)))

    def pump(self, duration, vx=None):
        end = time.monotonic() + duration
        next_pub = 0.0
        msg = Twist()
        if vx is not None:
            msg.linear.x = vx
        while rclpy.ok() and time.monotonic() < end:
            if vx is not None and time.monotonic() >= next_pub:
                self.pub.publish(msg)
                next_pub = time.monotonic() + 0.05
            rclpy.spin_once(self, timeout_sec=0.02)

    def wait(self, condition, timeout=2.0, vx=None):
        end = time.monotonic() + timeout
        while rclpy.ok() and time.monotonic() < end:
            if condition():
                return True
            self.pump(0.05, vx)
        return False

    def call(self, name):
        client = self.service_clients[name]
        if not client.wait_for_service(timeout_sec=2.0):
            raise RuntimeError('Unavailable: ' + name)
        future = client.call_async(Trigger.Request())
        rclpy.spin_until_future_complete(self, future, timeout_sec=1.0)
        if not future.done() or future.result() is None:
            raise RuntimeError('No response: ' + name)
        return future.result().success

    def check(self, label, result):
        print(('PASS' if result else 'FAIL') + ' | ' + label, flush=True)
        if not result:
            raise RuntimeError(label)
        self.count += 1

    def select_and_arm(self):
        if not self.call('command_mux/select_python'):
            raise RuntimeError('Python selection rejected')
        self.pump(1.2, 0.0)  # Mux switch guard: 0.75 s.
        if not self.call('motion_safety/arm'):
            raise RuntimeError('Arm rejected')
        if not self.wait(lambda: self.state('/motion_safety/status', 'ARMED'), vx=0.0):
            raise RuntimeError('ARMED not observed')

    def run(self):
        self.pump(1.5)
        if not (self.state('/motion_safety/status', 'DISARMED') and
                self.state('/command_mux/source', 'NONE') and self.output()):
            raise RuntimeError('Initial DISARMED/NONE/zero required')
        if self.count_publishers('/cmd_vel') != 1 or self.count_publishers('/cmd_vel_input') != 1 or self.count_publishers('/cmd_vel_python') != 1:
            raise RuntimeError('Unexpected command publisher count')
        self.check('E2E-01 - Python selected', self.call('command_mux/select_python') and
                   self.wait(lambda: self.state('/command_mux/source', 'PYTHON')))
        self.pump(1.2, 0.0)
        self.check('E2E-02 - Safe arm', self.call('motion_safety/arm') and
                   self.wait(lambda: self.state('/motion_safety/status', 'ARMED'), vx=0.0))
        print('Observe wheels: forward, then stop on command loss.', flush=True)
        self.pump(0.5, 0.05)
        self.check('E2E-03 - Forward output', self.output(0.05))
        # Check output while actual neutral joystick traffic is present.
        joy = self.latest('/cmd_vel_joy', 0.5)
        self.check('E2E-04 - Neutral joystick traffic isolated', joy is not None and
                   all(abs(v) < 1e-6 for v in self.vector(joy)) and self.output(0.05))
        # Stop normally before service call; keep arm active with recent zero.
        self.pump(0.2, 0.0)
        self.check('E2E-05 - Source switch while armed rejected',
                   not self.call('command_mux/select_joy'))
        self.pump(0.2, 0.0)
        if not self.state('/motion_safety/status', 'ARMED'):
            raise RuntimeError('Arm lost before watchdog experiment')
        self.pump(0.5, 0.05)
        if not self.output(0.05):
            raise RuntimeError('No forward output before timeout')
        print('Watchdog test: silence; observe physical stop.', flush=True)
        self.check('E2E-06 - Timeout and zero output', self.wait(lambda:
            self.state('/motion_safety/status', 'TIMEOUT') and self.output(), 2.0))
        self.check('E2E-07 - Source cleared', self.wait(lambda:
            self.state('/command_mux/source', 'NONE')))
        if not self.call('motion_safety/reset') or not self.wait(lambda:
            self.state('/motion_safety/status', 'DISARMED')):
            raise RuntimeError('Reset failed')
        self.pump(0.3)
        self.select_and_arm()
        self.pump(0.5, 0.05)
        if not self.output(0.05):
            raise RuntimeError('No forward output before stop')
        print('Software emergency stop: observe physical stop.', flush=True)
        self.check('E2E-08 - Software stop', self.call('motion_safety/emergency_stop') and
                   self.wait(lambda: self.state('/motion_safety/status', 'EMERGENCY_STOP')
                             and self.output()))
        if not self.call('command_mux/select_none') or not self.call('motion_safety/reset'):
            raise RuntimeError('Final reset failed')
        self.check('E2E-09 - DISARMED/NONE/zero', self.wait(lambda:
            self.state('/motion_safety/status', 'DISARMED') and
            self.state('/command_mux/source', 'NONE') and self.output()))


def main():
    rclpy.init()
    node = BenchTest()
    success = False
    try:
        node.run()
        success = True
    except (Exception, KeyboardInterrupt) as exc:
        print('ABORT:', exc, flush=True)
    finally:
        if not success and rclpy.ok():
            try:
                node.pub.publish(Twist())
                node.call('motion_safety/emergency_stop')
                node.call('command_mux/select_none')
            except Exception as exc:
                print('STOP NOT CONFIRMED:', exc, flush=True)
        print(f'Passed: {node.count}/9; verify physical stop.', flush=True)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
