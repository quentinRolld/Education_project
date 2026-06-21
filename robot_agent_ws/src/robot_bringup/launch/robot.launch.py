import os
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    # Declare configurable launch arguments
    device_index_arg = DeclareLaunchArgument(
        'device_index',
        default_value='0',
        description='Index of the USB camera device (V4L2)'
    )

    # 1. Camera Node
    camera_node = Node(
        package='robot_camera',
        executable='camera_node',
        name='camera_node',
        parameters=[{'device_index': LaunchConfiguration('device_index')}],
        output='screen'
    )

    # 2. VLM Brain Node
    vlm_node = Node(
        package='robot_vlm',
        executable='vlm_node',
        name='vlm_node',
        output='screen'
    )

    # 3. Piper TTS (Speech Synthesis) Node
    piper_tts_node = Node(
        package='robot_audio',
        executable='piper_tts_node',
        name='piper_tts_node',
        output='screen'
    )

    # 4. Speech-To-Text (Microphone Capture) Node
    stt_node = Node(
        package='robot_audio',
        executable='stt_node',
        name='stt_node',
        output='screen'
    )

    # 5. Motor Control Node
    motor_node = Node(
        package='robot_control',
        executable='motor_node',
        name='motor_node',
        output='screen'
    )

    return LaunchDescription([
        device_index_arg,
        camera_node,
        vlm_node,
        piper_tts_node,
        stt_node,
        motor_node
    ])
