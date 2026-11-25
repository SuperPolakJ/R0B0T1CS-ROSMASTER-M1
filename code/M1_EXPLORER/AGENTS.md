# R0B0T1CS LAB — M1 EXPLORER

## Project Overview

Educational robotics platform based on the Yahboom
ROSMASTER M1.

The objective is to progressively develop a modular,
maintainable and documented robotic system while
learning robotics engineering fundamentals.

## Hardware

- Raspberry Pi 5 — 8 GB RAM
- STM32F103RCT6 motor control board
- Four DC motors with encoders
- Four Mecanum wheels
- T-MINI PLUS LiDAR
- Nuwa-HP60C RGB-D camera
- 9-axis IMU
- OLED display
- 3S2P Li-ion battery

## Software Environment

- Raspberry Pi OS — Debian 12
- ROS 2 Humble inside Docker
- Python 3
- ROS_DOMAIN_ID=61
- VS Code Remote SSH
- Git and GitHub

Host workspace:
    /home/pi/share/M1_EXPLORER/

Docker workspace:
    /root/share/M1_EXPLORER/

Docker container names are dynamically generated.
Never assume a fixed container name.

## Project Structure

- runtime/motion/: motor command architecture
- runtime/monitoring/: telemetry and monitoring
- controllers/: reusable control libraries
- examples/: demonstration programs
- tests/: validation and regression tests
- config/: configuration files
- data/: generated runtime data
- documentation/: technical documentation
- installers/: historical installation scripts
- backups/: local backups

## Motion Architecture

Python Controller / Joystick
    -> Command Multiplexer
    -> Motion Safety Supervisor
    -> Yahboom Driver
    -> STM32
    -> Motors

## ROS 2 Interfaces

- /cmd_vel_python: Python motion commands
- /cmd_vel_joy: joystick motion commands
- /cmd_vel_input: multiplexer output
- /cmd_vel: supervisor output
- /vel_raw: velocity feedback
- /voltage: battery voltage
- /motion_safety/status: safety state
- /command_mux/source: selected source

## Mandatory Safety Rules

- Never initiate physical movement without explicit
  user authorization.
- Never publish directly to /cmd_vel.
- Never bypass the Command Multiplexer.
- Never bypass the Motion Safety Supervisor.
- Application controllers must use /cmd_vel_python.
- Never automatically reset or rearm after a fault.
- Never execute a motor demonstration autonomously.
- First motor tests must be performed with all wheels
  suspended above the ground.
- Keep the robot disarmed during development.
- Require explicit approval before hardware testing.
- Do not consider the software emergency stop a
  certified physical emergency stop.
- Independent hardware watchdog protection has not
  yet been demonstrated.

## Engineering Rules

- Inspect existing code before modifying it.
- Reuse existing validated components.
- Prefer modular and readable implementations.
- Use SI units and ROS 2 coordinate conventions.
- Document assumptions and limitations.
- Do not invent hardware or software interfaces.
- Prefer official documentation.
- Preserve backward compatibility when possible.
- Avoid unnecessary dependencies.
- Never delete existing files without approval.
- Do not modify systemd services, Docker settings,
  network configuration or startup scripts without
  explicit approval.
- Historical installers must not be executed without
  verifying their paths and compatibility.

## Testing Rules

Static analysis and syntax validation are preferred
during development.

Hardware tests require explicit authorization.

Distinguish between:

- Static validation
- Software validation
- Integration validation
- Physical validation

Never claim that an unexecuted test has passed.

The historical test_motion_safety.py bypasses the
multiplexer and must not be executed directly against
the permanent motion architecture.

## Learning Approach

The user is an electromechanical engineer developing
robotics engineering skills.

- Explain important design decisions.
- Explain equations and algorithms.
- Avoid unnecessary complexity.
- Identify alternative implementations when useful.
- Summarize modified files and remaining limitations.
- Communicate primarily in French.
- Preserve standard English technical terminology.