#!/usr/bin/env python3

# ============================================================
# R0B0T1CS LAB
# M1 EXPLORER
#
# Motion Safety Supervisor
# Version: 1.0
# Project: P02 - First Robot Motion
# ROS Distribution: Humble
# ============================================================

import math
import time

from enum import Enum

import rclpy
from rclpy.node import Node
from rclpy.clock import Clock, ClockType

from geometry_msgs.msg import Twist
from std_msgs.msg import String
from std_srvs.srv import Trigger


# ============================================================
# STATE MACHINE
# ============================================================

class RobotState(Enum):

    DISARMED = 'DISARMED'
    ARMED = 'ARMED'
    TIMEOUT = 'TIMEOUT'
    EMERGENCY_STOP = 'EMERGENCY_STOP'
    INVALID_COMMAND = 'INVALID_COMMAND'


# ============================================================
# MOTION SAFETY SUPERVISOR
# ============================================================

class MotionSafetySupervisor(Node):

    def __init__(self):

        super().__init__('motion_safety_supervisor')

        # ----------------------------------------------------
        # ROS 2 PARAMETERS
        # ----------------------------------------------------

        self.declare_parameter('max_linear_x', 0.15)
        self.declare_parameter('max_linear_y', 0.15)
        self.declare_parameter('max_linear_speed', 0.15)
        self.declare_parameter('max_angular_z', 0.5)

        self.declare_parameter('command_timeout', 0.5)
        self.declare_parameter('publish_rate', 20.0)

        self.max_linear_x = float(
            self.get_parameter('max_linear_x').value
        )

        self.max_linear_y = float(
            self.get_parameter('max_linear_y').value
        )

        self.max_linear_speed = float(
            self.get_parameter('max_linear_speed').value
        )

        self.max_angular_z = float(
            self.get_parameter('max_angular_z').value
        )

        self.command_timeout = float(
            self.get_parameter('command_timeout').value
        )

        self.publish_rate = float(
            self.get_parameter('publish_rate').value
        )

        # Validate configuration before starting

        parameters = (
            self.max_linear_x,
            self.max_linear_y,
            self.max_linear_speed,
            self.max_angular_z,
            self.command_timeout,
            self.publish_rate
        )

        if not all(
            math.isfinite(value) and value > 0.0
            for value in parameters
        ):
            raise ValueError('Invalid supervisor parameters')

        # ----------------------------------------------------
        # INTERNAL STATE
        # ----------------------------------------------------

        self.state = RobotState.DISARMED

        self.last_command = Twist()
        self.last_command_time = None

        # A fresh zero command is required before arming
        self.last_input_was_zero = False

        # ----------------------------------------------------
        # ROS 2 PUBLISHERS
        # ----------------------------------------------------

        self.cmd_publisher = self.create_publisher(
            Twist,
            '/cmd_vel',
            1
        )

        self.status_publisher = self.create_publisher(
            String,
            '/motion_safety/status',
            10
        )

        # ----------------------------------------------------
        # ROS 2 SUBSCRIBER
        # ----------------------------------------------------

        self.cmd_subscription = self.create_subscription(
            Twist,
            '/cmd_vel_input',
            self.command_callback,
            1
        )

        # ----------------------------------------------------
        # ROS 2 SERVICES
        # ----------------------------------------------------

        self.arm_service = self.create_service(
            Trigger,
            '/motion_safety/arm',
            self.arm_callback
        )

        self.disarm_service = self.create_service(
            Trigger,
            '/motion_safety/disarm',
            self.disarm_callback
        )

        self.estop_service = self.create_service(
            Trigger,
            '/motion_safety/emergency_stop',
            self.emergency_stop_callback
        )

        self.reset_service = self.create_service(
            Trigger,
            '/motion_safety/reset',
            self.reset_callback
        )

        # ----------------------------------------------------
        # TIMERS
        # ----------------------------------------------------

        # Steady clock: independent of ROS simulation time
        # and system clock corrections.

        self.steady_clock = Clock(
            clock_type=ClockType.STEADY_TIME
        )

        self.control_timer = self.create_timer(
            1.0 / self.publish_rate,
            self.control_callback,
            clock=self.steady_clock
        )

        self.status_timer = self.create_timer(
            1.0,
            self.publish_status,
            clock=self.steady_clock
        )

        # ----------------------------------------------------
        # STARTUP
        # ----------------------------------------------------

        self.publish_stop()
        self.publish_status()

        self.get_logger().info(
            'Motion Safety Supervisor V1.0 started'
        )

        self.get_logger().info(
            f'Initial state: {self.state.value}'
        )

        self.get_logger().info(
            f'Watchdog timeout: {self.command_timeout:.2f} s'
        )

        self.get_logger().info(
            f'Output frequency: {self.publish_rate:.1f} Hz'
        )

    # ========================================================
    # COMMAND VALIDATION
    # ========================================================

    def validate_command(self, msg):

        values = (
            msg.linear.x,
            msg.linear.y,
            msg.linear.z,
            msg.angular.x,
            msg.angular.y,
            msg.angular.z
        )

        # Reject NaN and infinite values

        if not all(math.isfinite(value) for value in values):
            return False

        # Only planar motion is supported

        if (
            abs(msg.linear.z) > 1e-6
            or abs(msg.angular.x) > 1e-6
            or abs(msg.angular.y) > 1e-6
        ):
            return False

        return True

    # ========================================================
    # ZERO COMMAND DETECTION
    # ========================================================

    def is_zero_command(self, msg):

        return (
            abs(msg.linear.x) < 1e-6
            and abs(msg.linear.y) < 1e-6
            and abs(msg.angular.z) < 1e-6
        )

    # ========================================================
    # VELOCITY LIMITER
    # ========================================================

    @staticmethod
    def clamp(value, minimum, maximum):

        return max(minimum, min(value, maximum))

    def limit_command(self, msg):

        safe_cmd = Twist()

        safe_cmd.linear.x = self.clamp(
            msg.linear.x,
            -self.max_linear_x,
            self.max_linear_x
        )

        safe_cmd.linear.y = self.clamp(
            msg.linear.y,
            -self.max_linear_y,
            self.max_linear_y
        )

        safe_cmd.angular.z = self.clamp(
            msg.angular.z,
            -self.max_angular_z,
            self.max_angular_z
        )

        # Limit resultant planar velocity

        linear_speed = math.hypot(
            safe_cmd.linear.x,
            safe_cmd.linear.y
        )

        if linear_speed > self.max_linear_speed:

            scale = (
                self.max_linear_speed / linear_speed
            )

            safe_cmd.linear.x *= scale
            safe_cmd.linear.y *= scale

        return safe_cmd

    # ========================================================
    # SUBSCRIBER CALLBACK
    # ========================================================

    def command_callback(self, msg):

        # Validate received command

        if not self.validate_command(msg):

            if self.state != RobotState.EMERGENCY_STOP:
                self.change_state(
                    RobotState.INVALID_COMMAND
                )

            self.last_command_time = None
            self.last_input_was_zero = False

            self.publish_stop()

            return

        # Record reception time

        self.last_command_time = time.monotonic()

        self.last_input_was_zero = (
            self.is_zero_command(msg)
        )

        # Ignore movement commands when not armed

        if self.state != RobotState.ARMED:

            self.last_command = Twist()

            return

        # Apply velocity limits

        self.last_command = self.limit_command(msg)

    # ========================================================
    # MAIN CONTROL LOOP
    # ========================================================

    def control_callback(self):

        # Movement is forbidden in every state except ARMED

        if self.state != RobotState.ARMED:

            self.publish_stop()

            return

        # Check if a command has been received

        if self.last_command_time is None:

            self.change_state(RobotState.TIMEOUT)
            self.publish_stop()

            return

        # Calculate command age

        command_age = (
            time.monotonic()
            - self.last_command_time
        )

        # Watchdog timeout

        if command_age >= self.command_timeout:

            self.change_state(RobotState.TIMEOUT)

            self.last_command = Twist()
            self.last_command_time = None
            self.last_input_was_zero = False

            self.publish_stop()

            return

        # Forward validated command

        self.cmd_publisher.publish(
            self.last_command
        )

    # ========================================================
    # ARM SERVICE
    # ========================================================

    def arm_callback(self, request, response):

        # Fault states require an explicit reset

        if self.state != RobotState.DISARMED:

            response.success = False
            response.message = (
                f'Cannot arm from state: {self.state.value}'
            )

            return response

        # Require a recent zero command before arming

        fresh_command = (
            self.last_command_time is not None
            and time.monotonic() - self.last_command_time
            < self.command_timeout
        )

        if not fresh_command or not self.last_input_was_zero:

            response.success = False
            response.message = (
                'Arming requires a fresh zero Twist input'
            )

            return response

        self.last_command = Twist()

        self.change_state(RobotState.ARMED)

        response.success = True
        response.message = 'Robot armed'

        return response

    # ========================================================
    # DISARM SERVICE
    # ========================================================

    def disarm_callback(self, request, response):

        # Disarm must not clear a latched fault

        if self.state == RobotState.ARMED:

            self.change_state(RobotState.DISARMED)

        self.clear_command()
        self.publish_stop()

        response.success = True
        response.message = (
            f'Motion stopped. State: {self.state.value}'
        )

        return response

    # ========================================================
    # EMERGENCY STOP SERVICE
    # ========================================================

    def emergency_stop_callback(self, request, response):

        self.change_state(
            RobotState.EMERGENCY_STOP
        )

        self.clear_command()
        self.publish_stop()

        response.success = True
        response.message = 'Software stop activated'

        return response

    # ========================================================
    # RESET SERVICE
    # ========================================================

    def reset_callback(self, request, response):

        self.clear_command()
        self.publish_stop()

        self.change_state(
            RobotState.DISARMED
        )

        response.success = True
        response.message = (
            'Supervisor reset. Robot remains disarmed.'
        )

        return response

    # ========================================================
    # UTILITY FUNCTIONS
    # ========================================================

    def clear_command(self):

        self.last_command = Twist()
        self.last_command_time = None
        self.last_input_was_zero = False

    def publish_stop(self):

        self.cmd_publisher.publish(Twist())

    def change_state(self, new_state):

        if self.state == new_state:
            return

        previous_state = self.state

        self.state = new_state

        self.get_logger().warning(
            f'State transition: '
            f'{previous_state.value} -> {new_state.value}'
        )

        self.publish_status()

    def publish_status(self):

        msg = String()

        msg.data = self.state.value

        self.status_publisher.publish(msg)

    # ========================================================
    # SHUTDOWN PROCEDURE
    # ========================================================

    def shutdown_robot(self):

        self.clear_command()

        self.state = RobotState.DISARMED

        # Attempt to transmit repeated zero commands
        # before destroying the ROS 2 node.

        if rclpy.ok():

            self.publish_status()

            for _ in range(10):

                if not rclpy.ok():
                    break

                self.publish_stop()

                time.sleep(0.05)


# ============================================================
# MAIN
# ============================================================

def main(args=None):

    rclpy.init(args=args)

    node = None

    try:

        node = MotionSafetySupervisor()

        rclpy.spin(node)

    except KeyboardInterrupt:

        pass

    finally:

        if node is not None:

            try:

                node.shutdown_robot()

            finally:

                node.destroy_node()

        if rclpy.ok():

            rclpy.shutdown()


if __name__ == '__main__':

    main()