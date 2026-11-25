#!/usr/bin/env bash
set -euo pipefail
# M1 EXPLORER — OLED monitoring V1.0
[[ $EUID -eq 0 ]] || { echo 'Run with sudo'; exit 1; }
share=/home/pi/share
original=/home/pi/software/oled_yahboom/yahboom_oled.py
custom=/home/pi/software/oled_yahboom/m1_explorer_oled.py
[[ -f "$original" && -d "$share" ]] || { echo 'Expected Yahboom paths missing'; exit 1; }
# Build and check the OLED variant before changing services.
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
python3 - "$original" "$work/oled.py" <<'PY'
import sys
from pathlib import Path
s=Path(sys.argv[1]).read_text()
anchor='import subprocess'
assert s.count(anchor)==1, 'Unexpected original imports'
s=s.replace(anchor, anchor+'\nimport json\nimport math')
anchor='    def main_program(self):'
assert s.count(anchor)==1, 'Unexpected original main_program'
s=s.replace(anchor, '''    def battery_lines(self):
        try:
            with open('/home/pi/share/battery_status.json') as f:
                data = json.load(f)
            with open('/proc/sys/kernel/random/boot_id') as f:
                boot_id = f.read().strip()
            age = time.monotonic() - data['timestamp_monotonic']
            if (data['data_valid'] is not True or data['boot_id'] != boot_id
                    or not 0 <= age <= 3.0):
                raise ValueError('stale data')
            voltage = float(data['voltage_filtered'])
            percentage = int(data['percentage'])
            status = data['status']
            if (not math.isfinite(voltage) or not 0 <= percentage <= 100
                    or status not in ('NORMAL', 'LOW', 'WARNING', 'CRITICAL')):
                raise ValueError('invalid data')
            return (f'Battery: ~{percentage}%', f'Voltage: {voltage:.2f}V',
                    f'Status: {status}', 'Mode: UNKNOWN')
        except (OSError, ValueError, TypeError, KeyError):
            return ('Battery: N/A', 'Voltage: N/A', 'Status: UNKNOWN', 'Mode: UNKNOWN')

'''+anchor)
old='''                self.add_text(0, 0, str_CPU)
                self.add_text(50, 0, str_Time)
                self.add_line(str_FreeRAM, 2)
                self.add_line(str_Disk, 3)
                self.add_line(str_IP, 4)'''
new='''                if int((time.monotonic() - page_start) / 5) % 2 == 0:
                    self.add_text(0, 0, str_CPU)
                    self.add_text(50, 0, str_Time)
                    self.add_line(str_FreeRAM, 2)
                    self.add_line(str_Disk, 3)
                    self.add_line(str_IP, 4)
                else:
                    for line, text in enumerate(self.battery_lines(), 1):
                        self.add_line(text, line)'''
assert s.count(old)==1, 'Unexpected original layout'
s=s.replace(old,new)
old='            cpu_index = 0\n            state = self.begin()'
assert s.count(old)==1
s=s.replace(old,'            cpu_index = 0\n            page_start = time.monotonic()\n            state = self.begin()')
Path(sys.argv[2]).write_text(s)
PY
cat > "$work/battery_monitor.py" <<'PY'
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
OUTPUT = '/root/share/battery_status.json'
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
PY
python3 -m py_compile "$work/oled.py" "$work/battery_monitor.py"
# Preserve existing user script once; original Yahboom script is never changed.
if [[ -f "$share/battery_monitor.py" && ! -e "$share/battery_monitor.pre_v1.py" ]]; then
    cp -p "$share/battery_monitor.py" "$share/battery_monitor.pre_v1.py"
fi
install -o pi -g pi -m 0644 "$work/battery_monitor.py" "$share/battery_monitor.py"
install -o pi -g pi -m 0644 "$work/oled.py" "$custom"
install -d /usr/local/lib/m1-explorer /etc/systemd/system/yahboom_oled.service.d
cat > /usr/local/lib/m1-explorer/battery-service.sh <<'SH'
#!/bin/bash
set -euo pipefail
state=/run/m1-battery-monitor/container
if [[ ${1:-start} == stop ]]; then
    if [[ -s $state ]]; then
        id=$(cat "$state")
        /usr/bin/docker exec "$id" python3 -c 'import os,signal
for p in os.listdir("/proc"):
    if p.isdigit():
        try:
            with open("/proc/"+p+"/cmdline","rb") as f:
                args=f.read().split(b"\0")
            if args[:2]==[b"python3",b"/root/share/battery_monitor.py"]:
                os.kill(int(p),signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass' || true
    fi
    exit 0
fi
mapfile -t ids < <(/usr/bin/docker ps --filter ancestor=192.168.2.51:5000/ros-humble-m1:1.1.1 --format '{{.ID}}')
if [[ ${#ids[@]} != 1 ]]; then
    echo 'Expected exactly one running Yahboom M1 container; retrying.' >&2
    exit 1
fi
printf '%s\n' "${ids[0]}" > "$state"
exec /usr/bin/docker exec -e ROS_DOMAIN_ID=61 -e M1_BOOT_ID="$(cat /proc/sys/kernel/random/boot_id)" "${ids[0]}" bash -c 'source /opt/ros/humble/setup.bash && exec python3 /root/share/battery_monitor.py'
SH
chmod 0755 /usr/local/lib/m1-explorer/battery-service.sh
cat > /etc/systemd/system/m1-battery-monitor.service <<'UNIT'
[Unit]
Description=M1 Explorer battery telemetry subscriber
After=docker.service
Requires=docker.service
StartLimitIntervalSec=0
[Service]
Type=simple
User=pi
RuntimeDirectory=m1-battery-monitor
ExecStart=/usr/local/lib/m1-explorer/battery-service.sh start
ExecStop=/usr/local/lib/m1-explorer/battery-service.sh stop
Restart=always
RestartSec=5
TimeoutStopSec=10
[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/systemd/system/yahboom_oled.service.d/90-m1-explorer.conf <<'UNIT'
[Service]
ExecStart=
ExecStart=/usr/bin/python3 /home/pi/software/oled_yahboom/m1_explorer_oled.py
UNIT
systemctl daemon-reload
systemctl enable --now m1-battery-monitor.service
systemctl restart yahboom_oled.service
printf '\nInstalled. Check both OLED pages and run:\n  systemctl is-active m1-battery-monitor.service yahboom_oled.service\n  cat /home/pi/share/battery_status.json\n'
