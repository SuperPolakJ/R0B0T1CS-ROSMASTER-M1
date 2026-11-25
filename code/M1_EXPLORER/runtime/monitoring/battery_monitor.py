#!/usr/bin/env python3
"""M1 EXPLORER — read-only battery telemetry, V1.0."""
import fcntl
import json
import math
import os
import tempfile
import time
from collections import deque

import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import Float32

# Illustrative, uncalibrated 3S Li-ion voltage-to-charge model.
CURVE = [(9.6, 0), (10.5, 5), (11.1, 20), (11.4, 35),
         (11.7, 60), (12.0, 80), (12.3, 90), (12.6, 100)]
OUTPUT = '/root/share/M1_EXPLORER/data/battery_status.json'
TIMEOUT = 3.0

def estimate(voltage):
    if voltage <= CURVE[0][0]:
        return 0
    for (v0, p0), (v1, p1) in zip(CURVE, CURVE[1:]):
        if voltage <= v1:
            return round(p0 + (voltage-v0)*(p1-p0)/(v1-v0))
    return 100

def status_for(p):
    return ('CRITICAL' if p < 10 else 'WARNING' if p < 20 else
            'LOW' if p < 50 else 'NORMAL')

class BatteryMonitor(Node):
    def __init__(self):
        super().__init__('battery_monitor')
        self.buffer = deque(maxlen=50)
        self.last = None
        self.raw = None
        self.boot_id = os.environ.get('M1_BOOT_ID')
        if not self.boot_id:
            with open('/proc/sys/kernel/random/boot_id') as f:
                self.boot_id = f.read().strip()
        self.subscription = self.create_subscription(
            Float32, '/voltage', self.receive, qos_profile_sensor_data)
        self.timer = self.create_timer(1.0, self.export)
        self.get_logger().info('Battery Monitor V1.0 started')

    def receive(self, msg):
        v = float(msg.data)
        if not math.isfinite(v) or not 0 < v <= 13.0:
            self.buffer.clear()
            self.last = None
            self.raw = None
            return
        now = time.monotonic()
        if self.last is None or now - self.last > TIMEOUT:
            self.buffer.clear()
        self.buffer.append(v)
        self.raw = v
        self.last = now

    def export(self, force_invalid=False):
        valid = (not force_invalid and self.last is not None
                 and 0 <= time.monotonic()-self.last <= TIMEOUT
                 and bool(self.buffer))
        voltage = sum(self.buffer)/len(self.buffer) if valid else None
        percentage = estimate(voltage) if valid else None
        data = dict(voltage_raw=round(self.raw, 2) if valid else None,
                    voltage_filtered=round(voltage, 2) if valid else None,
                    percentage=percentage,
                    status=status_for(percentage) if valid else 'UNKNOWN',
                    data_valid=valid, samples=len(self.buffer),
                    timestamp=time.time(), timestamp_monotonic=self.last,
                    boot_id=self.boot_id, soc_model='uncalibrated_3s_v1')
        temp = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', dir=os.path.dirname(OUTPUT),
                                             prefix='.battery-', delete=False) as f:
                temp = f.name
                json.dump(data, f, indent=2, allow_nan=False)
                f.write('\n')
            os.chmod(temp, 0o644)
            os.replace(temp, OUTPUT)
            temp = None
        except OSError as e:
            self.get_logger().error(f'JSON export failed: {e}')
        finally:
            if temp is not None:
                try:
                    os.unlink(temp)
                except OSError:
                    pass

def main():
    # One writer inside this container.
    with open('/tmp/m1_battery_monitor.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Battery monitor already running')
        rclpy.init()
        node = BatteryMonitor()
        try:
            rclpy.spin(node)
        except (KeyboardInterrupt, ExternalShutdownException):
            pass
        finally:
            node.export(force_invalid=True)
            node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()

if __name__ == '__main__':
    main()
