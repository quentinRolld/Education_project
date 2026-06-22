import os
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    # 1. VLM Brain Node
    vlm_node = Node(
        package='robot_vlm',
        executable='vlm_node',
        name='vlm_node',
        output='screen'
    )

    return LaunchDescription([
        vlm_node
    ])
