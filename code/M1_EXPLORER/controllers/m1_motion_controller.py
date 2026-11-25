#!/usr/bin/env python3
"""M1 EXPLORER V1.0 — synchronous ROS 2 bench motion API.
Use only with wheels off the floor, physical power switch accessible.
One controller, one thread; no background keepalive, no automatic reset.
"""
import math
import time
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import String, Float32
from std_srvs.srv import Trigger


class M1MotionController(Node):
    def __init__(self, *, connect_timeout=10.0):
        if not math.isfinite(connect_timeout) or connect_timeout <= 0:
            raise ValueError('connect_timeout must be positive and finite')
        super().__init__('m1_motion_controller')
        self.connect_timeout = connect_timeout
        self.pub = self.create_publisher(Twist, '/cmd_vel_python', 1)
        self.samples = {}
        self.subs = []
        for topic, kind in [('/motion_safety/status', String),
                            ('/command_mux/source', String), ('/cmd_vel', Twist),
                            ('/vel_raw', Twist), ('/voltage', Float32)]:
            self.subs.append(self.create_subscription(
                kind, topic, lambda msg, t=topic: self._record(t, msg), 1))
        self.service_clients = {name: self.create_client(Trigger, '/' + name)
            for name in ('motion_safety/arm', 'motion_safety/disarm',
                         'motion_safety/emergency_stop', 'command_mux/select_python',
                         'command_mux/select_none')}
        self.owns_session = False

    def _record(self, topic, msg):
        self.samples[topic] = (time.monotonic(), msg)

    def _latest(self, topic, max_age=2.0):
        stamp, msg = self.samples.get(topic, (0, None))
        if msg is None or time.monotonic() - stamp > max_age:
            raise RuntimeError('Missing/stale data: ' + topic)
        return msg

    @staticmethod
    def _vector(msg):
        return (msg.linear.x, msg.linear.y, msg.linear.z,
                msg.angular.x, msg.angular.y, msg.angular.z)

    def _zero(self):
        return all(abs(v) < 1e-6 for v in self._vector(self._latest('/cmd_vel', .25)))

    def _check_publishers(self):
        for topic in ('/cmd_vel', '/cmd_vel_input', '/cmd_vel_python'):
            if self.count_publishers(topic) != 1:
                raise RuntimeError('Unexpected publisher count: ' + topic)

    def _pump(self, duration, msg=None, armed=False):
        end = time.monotonic() + duration
        next_pub = 0.0
        while rclpy.ok() and time.monotonic() < end:
            if armed:
                self._check_publishers()
                if self.get_safety_state() != 'ARMED' or self._latest('/command_mux/source').data != 'PYTHON':
                    raise RuntimeError('Motion authorization lost')
            now = time.monotonic()
            if msg is not None and now >= next_pub:
                self.pub.publish(msg)
                next_pub = now + .05
            rclpy.spin_once(self, timeout_sec=.01)
        if not rclpy.ok():
            raise RuntimeError('ROS context stopped')

    def _wait(self, predicate, timeout=2.0, msg=None):
        end = time.monotonic() + timeout
        while time.monotonic() < end and rclpy.ok():
            try:
                if predicate():
                    return
            except RuntimeError:
                pass
            self._pump(.05, msg)
        raise RuntimeError('Expected state not observed')

    def _call(self, name, neutral=False):
        client = self.service_clients[name]
        if not client.service_is_ready():
            raise RuntimeError('Service unavailable: ' + name)
        future = client.call_async(Trigger.Request())
        end = time.monotonic() + 1.5
        while rclpy.ok() and not future.done() and time.monotonic() < end:
            self._pump(.05, Twist() if neutral else None)
        if not future.done() or future.result() is None:
            raise RuntimeError('No service response: ' + name)
        response = future.result()
        if not response.success:
            raise RuntimeError(name + ': ' + response.message)

    def get_safety_state(self):
        return self._latest('/motion_safety/status').data

    def get_velocity(self):
        msg = self._latest('/vel_raw', .5)
        return msg.linear.x, msg.linear.y, msg.angular.z

    def get_battery(self):
        return float(self._latest('/voltage').data)

    def _connection_issues(self):
        issues = [f'Service unavailable: /{name}'
                  for name, client in self.service_clients.items()
                  if not client.service_is_ready()]
        checks = (
            ('/motion_safety/status', self.get_safety_state, 'DISARMED'),
            ('/command_mux/source', lambda: self._latest('/command_mux/source').data, 'NONE'),
            ('/cmd_vel', self._zero, True),
        )
        for topic, read, expected in checks:
            try:
                observed = read()
            except RuntimeError as exc:
                issues.append(str(exc))
                continue
            if observed != expected:
                if topic == '/cmd_vel':
                    issues.append('Nonzero motor command on /cmd_vel')
                else:
                    issues.append(f'{topic}: expected {expected}, observed {observed!r}')
        return issues

    def connect(self):
        issues = []

        def ready():
            nonlocal issues
            issues = self._connection_issues()
            return not issues

        try:
            self._wait(ready, timeout=self.connect_timeout)
        except RuntimeError as exc:
            if not rclpy.ok() or not issues:
                raise
            details = '; '.join(issues)
            raise RuntimeError(
                f'Connection failed within {self.connect_timeout:g} s: {details}'
            ) from exc
        self._check_publishers()
        if self.pub.get_subscription_count() != 1:
            raise RuntimeError('Python input subscriber count is not one')

    def arm(self):
        self.connect()
        self.owns_session = True
        try:
            self._call('command_mux/select_python')
            self._pump(1.2, Twist())  # Mux guard 0.75 s
            self._call('motion_safety/arm', neutral=True)
            self._wait(lambda: self.get_safety_state() == 'ARMED'
                       and self._latest('/command_mux/source').data == 'PYTHON', msg=Twist())
        except BaseException:
            self._abort()
            raise

    def move(self, vx, vy, wz, duration):
        # Deliberately conservative bench limits, below supervisor limits.
        if not all(math.isfinite(v) for v in (vx, vy, wz, duration)) or not (
                math.hypot(vx, vy) <= .05 + 1e-9 and abs(wz) <= .2 and 0 < duration <= 2):
            raise ValueError('Bench limits: 0.05 m/s, 0.2 rad/s, 0 < duration <= 2 s')
        if not self.owns_session:
            raise RuntimeError('Call arm() first')
        msg = Twist()
        msg.linear.x, msg.linear.y, msg.angular.z = float(vx), float(vy), float(wz)
        try:
            self._pump(duration, msg, armed=True)
            self.stop()
        except BaseException:
            self._abort()
            raise

    def forward(self, speed, duration):
        self.move(abs(speed), 0, 0, duration)

    def backward(self, speed, duration):
        self.move(-abs(speed), 0, 0, duration)

    def strafe_left(self, speed, duration):
        self.move(0, abs(speed), 0, duration)

    def strafe_right(self, speed, duration):
        self.move(0, -abs(speed), 0, duration)

    def rotate(self, speed, duration):
        self.move(0, 0, speed, duration)

    def stop(self):
        if not self.owns_session:
            raise RuntimeError('No active session')
        self._pump(.2, Twist(), armed=True)
        if not self._zero():
            raise RuntimeError('Zero output not observed')

    def disarm(self):
        if not self.owns_session:
            return
        self.pub.publish(Twist())
        self._call('motion_safety/disarm')
        self._call('command_mux/select_none')
        self._wait(lambda: self.get_safety_state() == 'DISARMED'
                   and self._latest('/command_mux/source').data == 'NONE' and self._zero())
        self.owns_session = False

    def emergency_stop(self):
        self.pub.publish(Twist())
        self._call('motion_safety/emergency_stop')
        self._call('command_mux/select_none')
        self._wait(lambda: self.get_safety_state() == 'EMERGENCY_STOP' and self._zero()
                   and self._latest('/command_mux/source').data == 'NONE')
        self.owns_session = False

    def _abort(self):
        if self.owns_session and rclpy.ok():
            try:
                self.emergency_stop()
            except Exception as exc:
                self.get_logger().error('STOP NOT CONFIRMED: ' + str(exc))
