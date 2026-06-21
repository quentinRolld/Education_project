

# -------------------------------
# file: robot_audio/scripts/piper_tts_node.py
# -------------------------------
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import subprocess
import tempfile
import os


class PiperTTSNode(Node):
    def __init__(self):
        super().__init__('piper_tts')
        self.get_logger().info('Starting Piper TTS node')
        
        # Declare parameters for easy audio routing and model path configuration
        self.declare_parameter('model_path', '/models/fr/model.onnx')
        self.declare_parameter('alsa_device', 'plughw:0,0')
        
        self.model_path = self.get_parameter('model_path').value
        self.alsa_device = self.get_parameter('alsa_device').value

        # Subscriber to /say_text topic
        self.sub = self.create_subscription(String, '/say_text', self.say_callback, 10)

        # Say hello on startup
        self.say('Bonjour, je suis prêt.')

    def say_callback(self, msg):
        self.say(msg.data)

    def say(self, text: str):
        # Generate TTS WAV using piper CLI (assumes piper installed and a French model path set)
        try:
            tmp_wav = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
            tmp_wav.close()
            # Adjust model path if needed
            # Example piper invocation; change according to your piper installation
            proc = subprocess.run([
                'piper',
                '--text', text,
                '--model', self.model_path,
                '-f', tmp_wav.name
            ], check=False)

            # Play with aplay
            subprocess.run(['aplay', '-D', self.alsa_device, tmp_wav.name], check=False)
        except Exception as e:
            self.get_logger().error(f'Failed to say text: {e}')
        finally:
            try:
                os.remove(tmp_wav.name)
            except Exception:
                pass




def main(args=None):
    rclpy.init(args=args)
    node = PiperTTSNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
