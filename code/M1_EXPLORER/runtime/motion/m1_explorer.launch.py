"""M1 EXPLORER — replacement launch; original Yahboom packages remain intact."""
from launch import LaunchDescription
from launch.actions import ExecuteProcess
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(package='joy', executable='joy_node', output='screen'),
        Node(package='yahboomcar_ctrl', executable='yahboom_joy_M1',
             remappings=[('/cmd_vel', '/cmd_vel_joy')], output='screen'),
        Node(package='yahboomcar_bringup', executable='Mcnamu_driver_M1',
             output='screen'),
        ExecuteProcess(cmd=['python3', '/root/share/M1_EXPLORER/runtime/motion/motion_safety_supervisor.py'],
                       name='motion_safety_supervisor_process', output='screen',
                       respawn=True, respawn_delay=0.2),
        ExecuteProcess(cmd=['python3', '/root/share/M1_EXPLORER/runtime/motion/command_mux.py'],
                       name='command_mux_process', output='screen',
                       respawn=True, respawn_delay=0.2),
    ])
