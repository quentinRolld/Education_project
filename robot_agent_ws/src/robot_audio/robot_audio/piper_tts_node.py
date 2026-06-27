

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
import re


class PiperTTSNode(Node):
    def __init__(self):
        super().__init__('piper_tts')
        self.get_logger().info('Starting Piper TTS node')
        
        self.declare_parameter('model_path', '/models/fr/model.onnx')
        self.declare_parameter('alsa_device', 'auto')
        self.declare_parameter('piper_path', 'piper')
        
        self.model_path = self.get_parameter('model_path').value
        self.alsa_device = self.get_parameter('alsa_device').value
        self.piper_path = self.get_parameter('piper_path').value

        if self.alsa_device == 'auto':
            self.alsa_device = self.auto_discover_speaker()

        self.sub = self.create_subscription(String, '/say_text', self.say_callback, 10)

        # Say hello on startup
        self.say('Hello, I am ready.')

    def auto_discover_speaker(self) -> str:
        self.get_logger().info('Auto-discovering USB speaker (aplay -l)...')
        try:
            result = subprocess.run(['aplay', '-l'], capture_output=True, text=True)
            for line in result.stdout.split('\n'):
                # Look for "card X:" and "USB" or "UACDemo"
                if 'card' in line and ('USB' in line or 'UACDemo' in line):
                    match = re.search(r'card (\d+):', line)
                    if match:
                        card_num = match.group(1)
                        # Assuming device 0 for the card
                        dev_string = f"plughw:{card_num},0"
                        self.get_logger().info(f'Found USB Speaker on {dev_string}')
                        return dev_string
        except Exception as e:
            self.get_logger().error(f'Failed to run aplay -l: {e}')
            
        self.get_logger().warning('Auto-discovery failed to find a USB speaker. Falling back to plughw:0,0')
        return 'plughw:0,0'

    def say_callback(self, msg):
        self.say(msg.data)

    def say(self, text: str):
        # Generate TTS WAV using piper CLI
        try:
            tmp_wav = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
            tmp_wav.close()
            
            proc = subprocess.run([
                self.piper_path,
                '--model', self.model_path,
                '-f', tmp_wav.name
            ], input=text.encode('utf-8'), capture_output=True)
            
            if proc.returncode != 0:
                self.get_logger().error(f'Piper failed: {proc.stderr.decode("utf-8")}')
                return

            # Play with aplay
            play_proc = subprocess.run(['aplay', '-D', self.alsa_device, tmp_wav.name], capture_output=True)
            if play_proc.returncode != 0:
                self.get_logger().error(f'aplay failed: {play_proc.stderr.decode("utf-8")}')
                
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
