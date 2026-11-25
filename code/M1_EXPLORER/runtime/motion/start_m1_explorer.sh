#!/bin/bash
set -e
source /opt/ros/humble/setup.bash
source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
export INIT_SERVO_S1=90
export INIT_SERVO_S2=35
export ROS_DOMAIN_ID=61
export ROBOT_TYPE=M1
exec ros2 launch /root/share/M1_EXPLORER/runtime/motion/m1_explorer.launch.py
