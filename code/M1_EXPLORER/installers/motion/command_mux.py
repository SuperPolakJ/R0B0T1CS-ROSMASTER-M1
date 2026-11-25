#!/usr/bin/env python3
"""M1 EXPLORER — laboratory command source selector (ROS 2 Humble)."""
import math
import time
from functools import partial

import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from rclpy.clock import Clock, ClockType
from geometry_msgs.msg import Twist
from std_msgs.msg import String
from std_srvs.srv import Trigger


class CommandMux(Node):
    STATUS_MAX_AGE = 2.0  # Supervisor status is normally published at 1 Hz.
    SWITCH_GUARD = 0.75   # Longer than the configured 0.5 s watchdog.

    def __init__(self):
        super().__init__('command_mux')
        self.selected = 'NONE'
        self.supervisor_state = None
        self.status_time = None
        self.guard_until = 0.0
        self.neutral_seen = False
        self.output_pub = self.create_publisher(Twist, '/cmd_vel_input', 1)
        self.selection_pub = self.create_publisher(String, '/command_mux/source', 10)
        self.state_sub = self.create_subscription(
            String, '/motion_safety/status', self.on_status, 10)
        self.joy_sub = self.create_subscription(
            Twist, '/cmd_vel_joy', partial(self.on_command, 'JOY'), 1)
        self.python_sub = self.create_subscription(
            Twist, '/cmd_vel_python', partial(self.on_command, 'PYTHON'), 1)
        self.select_joy_srv = self.create_service(
            Trigger, '/command_mux/select_joy', partial(self.select, 'JOY'))
        self.select_python_srv = self.create_service(
            Trigger, '/command_mux/select_python', partial(self.select, 'PYTHON'))
        self.select_none_srv = self.create_service(
            Trigger, '/command_mux/select_none', partial(self.select, 'NONE'))
        self.steady_clock = Clock(clock_type=ClockType.STEADY_TIME)
        self.timer = self.create_timer(0.2, self.tick, clock=self.steady_clock)
        self.get_logger().info('Command Mux V1.0 started; source NONE')

    def status_fresh(self):
        return (self.status_time is not None and
                time.monotonic() - self.status_time < self.STATUS_MAX_AGE)

    def publish_selection(self):
        msg = String()
        msg.data = self.selected
        self.selection_pub.publish(msg)

    def clear_selection(self):
        if self.selected != 'NONE':
            self.get_logger().warning('Source cleared: motion input inhibited')
        self.selected = 'NONE'
        self.neutral_seen = False
        self.publish_selection()

    def on_status(self, msg):
        self.supervisor_state = msg.data
        self.status_time = time.monotonic()
        if msg.data not in ('DISARMED', 'ARMED'):
            self.clear_selection()

    def tick(self):
        if not self.status_fresh():
            self.clear_selection()
        self.publish_selection()

    def select(self, source, request, response):
        # NONE is always allowed: stop forwarding so the supervisor times out.
        if source == 'NONE':
            self.clear_selection()
            response.success = True
            response.message = 'Source NONE; use supervisor disarm for immediate stop'
            return response
        if not self.status_fresh() or self.supervisor_state != 'DISARMED':
            response.success = False
            response.message = 'Source selection requires fresh DISARMED status'
            return response
        self.selected = source
        self.neutral_seen = False
        self.guard_until = time.monotonic() + self.SWITCH_GUARD
        self.publish_selection()
        response.success = True
        response.message = f'{source} selected; wait for a fresh neutral input before arming'
        return response

    @staticmethod
    def neutral(msg):
        values = (msg.linear.x, msg.linear.y, msg.linear.z,
                  msg.angular.x, msg.angular.y, msg.angular.z)
        return all(math.isfinite(v) and abs(v) < 1e-6 for v in values)

    def on_command(self, source, msg):
        if source != self.selected or not self.status_fresh():
            return
        if self.supervisor_state not in ('DISARMED', 'ARMED'):
            return
        if time.monotonic() < self.guard_until:
            return
        if not self.neutral_seen:
            if not self.neutral(msg):
                return
            self.neutral_seen = True
        # No repeating or synthetic zero messages: upstream silence must remain
        # visible to the watchdog. Supervisor validates all forwarded commands.
        self.output_pub.publish(msg)


def main():
    rclpy.init()
    node = None
    try:
        node = CommandMux()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
