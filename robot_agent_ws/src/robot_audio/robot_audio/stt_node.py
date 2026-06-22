#!/usr/bin/env python3
# -------------------------------
# file: robot_audio/stt_node.py
# -------------------------------
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import threading

try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False


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
        
        self.declare_parameter('language', 'fr-FR')
        self.declare_parameter('energy_threshold', 300)  # Silence detection sensitivity
        self.declare_parameter('device_index', -1)      # -1 for default mic, or specific audio index

        self.language = self.get_parameter('language').value
        self.energy_threshold = self.get_parameter('energy_threshold').value
        
        try:
            self.device_index = int(self.get_parameter('device_index').value)
        except (ValueError, TypeError):
            self.device_index = -1

        self.pub = self.create_publisher(String, '/user/instruction', 10)
        self.running = True

        # Start the microphone listener thread
        if SR_AVAILABLE:
            self.listener_thread = threading.Thread(target=self.listen_loop, daemon=True)
            self.listener_thread.start()
            self.get_logger().info('Mic listener thread started')

    def listen_loop(self):
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = self.energy_threshold
        recognizer.dynamic_energy_threshold = True

        # Use specified mic index if configured
        mic_index = None if self.device_index == -1 else self.device_index
        
        try:
            mic = sr.Microphone(device_index=mic_index)
            
            # Calibrate threshold to ambient noise
            self.get_logger().info('Calibrating microphone to ambient noise...')
            with mic as source:
                recognizer.adjust_for_ambient_noise(source, duration=2.0)
            self.get_logger().info(f'Calibration done. New threshold: {recognizer.energy_threshold:.1f}')
            
            self.get_logger().info("STT is listening. You can speak now...")
            
            while self.running:
                with mic as source:
                    try:
                        # Listen for a phrase (timeout = no speech, phrase_time_limit = max duration of speech)
                        audio = recognizer.listen(source, timeout=1.0, phrase_time_limit=10.0)
                    except sr.WaitTimeoutError:
                        continue  # Keep listening
                    
                if not self.running:
                    break

                self.get_logger().info('Speech detected. Transcribing...')
                try:
                    # Recognize speech using Google Speech Recognition
                    text = recognizer.recognize_google(audio, language=self.language)
                    self.get_logger().info(f'Transcribed speech: "{text}"')
                    
                    # Publish the text instruction
                    msg = String()
                    msg.data = text
                    self.pub.publish(msg)
                except sr.UnknownValueError:
                    self.get_logger().warning("Could not understand audio")
                except sr.RequestError as e:
                    self.get_logger().error(f"Could not request transcription service: {e}")
                except Exception as e:
                    self.get_logger().error(f"Error during recognition: {e}")
                    
        except Exception as e:
            self.get_logger().error(f"Failed to initialize microphone: {e}. Is your USB microphone connected?")

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
