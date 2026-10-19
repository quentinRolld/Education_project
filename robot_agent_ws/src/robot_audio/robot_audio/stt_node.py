#!/usr/bin/env python3
# -------------------------------
# file: robot_audio/stt_node.py
# -------------------------------
import rclpy
from rclpy.node import Node
from std_msgs.msg import Empty, String
import threading
import time

import numpy as np

try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False


class OnsetDetectingStream:
    """Wraps the microphone stream to signal the start of speech as soon as it is
    heard, i.e. before the phrase ends and gets transcribed. The VLM uses this
    signal to encode the camera frame while the user is still talking."""

    def __init__(self, stream, get_threshold, on_onset, min_loud_chunks=3):
        self._stream = stream
        self._get_threshold = get_threshold
        self._on_onset = on_onset
        # 3 chunks of 1024 samples at 16 kHz is ~0.2s: ignores short clicks
        self._min_loud_chunks = min_loud_chunks
        self._loud_chunks = 0
        self._armed = True

    def read(self, size):
        buffer = self._stream.read(size)
        if self._armed:
            samples = np.frombuffer(buffer, dtype=np.int16).astype(np.float32)
            rms = float(np.sqrt(np.mean(samples ** 2))) if samples.size else 0.0
            self._loud_chunks = self._loud_chunks + 1 if rms > self._get_threshold() else 0
            if self._loud_chunks >= self._min_loud_chunks:
                self._armed = False
                self._on_onset()
        return buffer

    def rearm(self):
        self._armed = True
        self._loud_chunks = 0

    def __getattr__(self, name):
        return getattr(self._stream, name)


class SpeechToTextNode(Node):
    def __init__(self):
        super().__init__('stt_node')
        self.get_logger().info('Starting Speech-To-Text (STT) Node')

        if not SR_AVAILABLE:
            self.get_logger().error(
                'speech_recognition library not installed. '
                'Please run: pip3 install SpeechRecognition pyaudio'
            )
            # We don't crash, but we will print errors during callbacks
        
        self.declare_parameter('language', 'en-US')
        self.declare_parameter('energy_threshold', 300)  # Silence detection sensitivity
        self.declare_parameter('device_index', -1)      # -1 for default mic, or specific audio index

        self.language = self.get_parameter('language').value
        self.energy_threshold = self.get_parameter('energy_threshold').value
        
        try:
            self.device_index = int(self.get_parameter('device_index').value)
        except (ValueError, TypeError):
            self.device_index = -1

        if self.device_index == -1 and SR_AVAILABLE:
            self.device_index = self.auto_discover_microphone()

        self.pub = self.create_publisher(String, '/user/instruction', 10)
        self.speech_started_pub = self.create_publisher(Empty, '/user/speech_started', 10)
        self.running = True

        # Start the microphone listener thread
        if SR_AVAILABLE:
            self.listener_thread = threading.Thread(target=self.listen_loop, daemon=True)
            self.listener_thread.start()
            self.get_logger().info('Mic listener thread started')

    def auto_discover_microphone(self) -> int:
        self.get_logger().info('Auto-discovering USB microphone...')
        try:
            import pyaudio
            p = pyaudio.PyAudio()
            try:
                for i in range(p.get_device_count()):
                    info = p.get_device_info_by_index(i)
                    name = info['name']
                    # Must actually expose input channels, not just match by name
                    # (USB speakers/sound cards often share naming keywords with USB mics)
                    if info['maxInputChannels'] > 0 and (
                        'USB' in name or 'Camera' in name or 'Mic' in name or 'UACDemo' in name
                    ):
                        self.get_logger().info(f'Found Microphone: "{name}" at index {i}')
                        return i
            finally:
                p.terminate()
        except Exception as e:
            self.get_logger().error(f'Failed to list microphones: {e}')

        self.get_logger().warning('Auto-discovery failed. Using system default microphone (index -1).')
        return -1

    def listen_loop(self):
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = self.energy_threshold
        # Fixed threshold after calibration instead of continuously adapting during
        # listening: dynamic mode was making recognition inconsistent across
        # sessions (drifting threshold triggering on background noise, or cutting
        # phrases at the wrong point).
        recognizer.dynamic_energy_threshold = False
        recognizer.operation_timeout = 10  # cap the Google API request so a network hiccup can't hang the loop forever
        recognizer.pause_threshold = 1.0  # seconds of silence ending a phrase (default 0.8 cut sentences mid-way)

        # Use specified mic index if configured
        mic_index = None if self.device_index == -1 else self.device_index
        
        try:
            mic = sr.Microphone(device_index=mic_index)
            
            # Open the mic stream once and keep it open for the whole listening
            # session (re-opening it every loop iteration was re-triggering
            # ALSA's device probing on every timeout, flooding the logs).
            with mic as source:
                # Calibrate threshold to ambient noise
                self.get_logger().info('Calibrating microphone to ambient noise...')
                recognizer.adjust_for_ambient_noise(source, duration=3.0)
                self.get_logger().info(f'Calibration done. New threshold: {recognizer.energy_threshold:.1f}')

                onset_stream = OnsetDetectingStream(
                    source.stream, lambda: recognizer.energy_threshold, self.publish_speech_started
                )
                source.stream = onset_stream

                self.get_logger().info("STT is listening. You can speak now...")
                last_heartbeat = time.monotonic()

                while self.running:
                    try:
                        # Listen for a phrase (timeout = no speech, phrase_time_limit = max duration of speech)
                        audio = recognizer.listen(source, timeout=1.0, phrase_time_limit=10.0)
                    except sr.WaitTimeoutError:
                        onset_stream.rearm()
                        # Periodic proof-of-life so idle silence isn't mistaken for a hang
                        if time.monotonic() - last_heartbeat > 30.0:
                            self.get_logger().info('Still listening, no speech detected recently...')
                            last_heartbeat = time.monotonic()
                        continue  # Keep listening

                    last_heartbeat = time.monotonic()
                    onset_stream.rearm()

                    if not self.running:
                        break

                    duration = len(audio.frame_data) / (audio.sample_rate * audio.sample_width)
                    rms = float(np.sqrt(np.mean(np.frombuffer(audio.frame_data, dtype=np.int16).astype(np.float32) ** 2)))
                    self.get_logger().info(
                        f'Speech detected ({duration:.1f}s, rms {rms:.0f}, threshold {recognizer.energy_threshold:.0f}). Transcribing...'
                    )
                    try:
                        # Recognize speech using Google Speech Recognition
                        text = recognizer.recognize_google(audio, language=self.language)
                        self.get_logger().info(f'Transcribed speech: "{text}"')

                        # Publish the text instruction
                        msg = String()
                        msg.data = text
                        self.pub.publish(msg)
                    except sr.UnknownValueError:
                        self.get_logger().warning("Could not understand audio (clip saved to /tmp/stt_last_failed.wav)")
                        with open('/tmp/stt_last_failed.wav', 'wb') as f:
                            f.write(audio.get_wav_data())
                    except sr.RequestError as e:
                        self.get_logger().error(f"Could not request transcription service: {e}")
                    except Exception as e:
                        self.get_logger().error(f"Error during recognition: {e}")

        except Exception as e:
            self.get_logger().error(f"Failed to initialize microphone: {e}. Is your USB microphone connected?")

    def publish_speech_started(self):
        self.get_logger().info('Speech onset heard, asking the VLM to pre-encode the camera frame')
        self.speech_started_pub.publish(Empty())

    def destroy_node(self):
        self.running = False
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = SpeechToTextNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
