import os
from launch import LaunchDescription
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    # Declare configurable launch arguments for hardware/IO
    device_index_arg = DeclareLaunchArgument(
        'device_index',
        default_value='-1',
        description='Index of the USB camera device (V4L2) or -1 for auto-discovery'
    )

    alsa_device_arg = DeclareLaunchArgument(
        'alsa_device',
        default_value='auto',
        description='ALSA device for playback (e.g., plughw:1,0) or auto for discovery'
    )

    model_path_arg = DeclareLaunchArgument(
        'model_path',
        default_value='/home/kant/piper_models/en_US-lessac-medium.onnx',
        description='Path to the Piper English ONNX voice model'
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

    volume_gain_arg = DeclareLaunchArgument(
        'volume_gain',
        default_value='1.0',
        description='Software gain applied to TTS audio (1.0 = unchanged)'
    )

    wheel_diameter_arg = DeclareLaunchArgument(
        'wheel_diameter_cm',
        default_value='6.5',
        description='Wheel diameter used to convert encoder ticks to distance'
    )

    track_width_arg = DeclareLaunchArgument(
        'track_width_cm',
        default_value='20.0',
        description='Distance between the two wheel contact points, used for encoder-based turns and odometry'
    )

    encoder_slots_arg = DeclareLaunchArgument(
        'encoder_slots',
        default_value='20',
        description='Number of slots on the encoder disk'
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
            'piper_path': LaunchConfiguration('piper_path'),
            'volume_gain': LaunchConfiguration('volume_gain')
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
        parameters=[{
            'wheel_diameter_cm': ParameterValue(LaunchConfiguration('wheel_diameter_cm'), value_type=float),
            'track_width_cm': ParameterValue(LaunchConfiguration('track_width_cm'), value_type=float),
            'encoder_slots': ParameterValue(LaunchConfiguration('encoder_slots'), value_type=int)
        }],
        output='screen'
    )

    return LaunchDescription([
        device_index_arg,
        alsa_device_arg,
        model_path_arg,
        mic_device_index_arg,
        piper_path_arg,
        volume_gain_arg,
        wheel_diameter_arg,
        track_width_arg,
        encoder_slots_arg,
        camera_node,
        piper_tts_node,
        stt_node,
        motor_node
    ])
