

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
                '--model', '/models/fr/model.onnx',
                '--output', tmp_wav.name
            ], check=False)

            # Play with aplay (force hw:0,0 or detect externally)
            subprocess.run(['aplay', '-D', 'hw:0,0', tmp_wav.name], check=False)
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
