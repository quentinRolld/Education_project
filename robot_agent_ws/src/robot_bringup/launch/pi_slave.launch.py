import os
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    # Declare configurable launch arguments for hardware/IO
    alsa_device_arg = DeclareLaunchArgument(
        'alsa_device',
        default_value='plughw:0,0',
        description='ALSA device for playback (e.g., plughw:1,0)'
    )

    model_path_arg = DeclareLaunchArgument(
        'model_path',
        default_value='/home/kant/piper_models/fr_FR-siwis-medium.onnx',
        description='Path to the Piper French ONNX voice model'
    )

    piper_path_arg = DeclareLaunchArgument(
        'piper_path',
        default_value='piper',
        description='Path to the Piper executable binary'
    )

    # 1. Piper TTS (Speech Synthesis) Node
    piper_tts_node = Node(
        package='robot_audio',
        executable='piper_tts_node',
        name='piper_tts_node',
        parameters=[{
            'alsa_device': LaunchConfiguration('alsa_device'),
            'model_path': LaunchConfiguration('model_path'),
            'piper_path': LaunchConfiguration('piper_path')
        }],
        output='screen'
    )

    # 2. Motor Control Node
    motor_node = Node(
        package='robot_control',
        executable='motor_node',
        name='motor_node',
        output='screen'
    )

    return LaunchDescription([
        alsa_device_arg,
        model_path_arg,
        piper_path_arg,
        piper_tts_node,
        motor_node
    ])
