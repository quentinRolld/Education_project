import os
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    # Declare configurable launch arguments for hardware/IO
    device_index_arg = DeclareLaunchArgument(
        'device_index',
        default_value='0',
        description='Index of the USB camera device (V4L2)'
    )

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

    mic_device_index_arg = DeclareLaunchArgument(
        'mic_device_index',
        default_value='-1',
        description='PyAudio index of the USB microphone device'
    )

    piper_path_arg = DeclareLaunchArgument(
        'piper_path',
        default_value='piper',
        description='Path to the Piper executable binary'
    )

    # 1. Camera Node
    camera_node = Node(
        package='robot_camera',
        executable='camera_node',
        name='camera_node',
        parameters=[{'device_index': LaunchConfiguration('device_index')}],
        output='screen'
    )

    # 2. Piper TTS (Speech Synthesis) Node
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

    # 3. Speech-To-Text (Microphone Capture) Node
    stt_node = Node(
        package='robot_audio',
        executable='stt_node',
        name='stt_node',
        parameters=[{'device_index': LaunchConfiguration('mic_device_index')}],
        output='screen'
    )

    # 4. Motor Control Node
    motor_node = Node(
        package='robot_control',
        executable='motor_node',
        name='motor_node',
        output='screen'
    )

    return LaunchDescription([
        device_index_arg,
        alsa_device_arg,
        model_path_arg,
        mic_device_index_arg,
        piper_path_arg,
        camera_node,
        piper_tts_node,
        stt_node,
        motor_node
    ])
