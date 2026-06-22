import os
from launch import LaunchDescription
from launch_ros.actions import Node


from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    # Declare camera device index argument
    device_index_arg = DeclareLaunchArgument(
        'device_index',
        default_value='0',
        description='Index of the USB camera device (V4L2)'
    )

    # Declare microphone device index argument
    mic_device_index_arg = DeclareLaunchArgument(
        'mic_device_index',
        default_value='-1',
        description='PyAudio index of the USB microphone device'
    )

    # 1. Camera Node
    camera_node = Node(
        package='robot_camera',
        executable='camera_node',
        name='camera_node',
        parameters=[{'device_index': LaunchConfiguration('device_index')}],
        output='screen'
    )

    # 2. Speech-To-Text (Microphone Capture) Node
    stt_node = Node(
        package='robot_audio',
        executable='stt_node',
        name='stt_node',
        parameters=[{'device_index': LaunchConfiguration('mic_device_index')}],
        output='screen'
    )

    # 3. VLM Brain Node
    vlm_node = Node(
        package='robot_vlm',
        executable='vlm_node',
        name='vlm_node',
        output='screen'
    )

    return LaunchDescription([
        device_index_arg,
        mic_device_index_arg,
        camera_node,
        stt_node,
        vlm_node
    ])
