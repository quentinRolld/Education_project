# -------------------------------
# file: robot_vlm/scripts/vlm_node.py
# -------------------------------
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from sensor_msgs.msg import Image
import base64
import requests
import json
from cv_bridge import CvBridge


OLLAMA_URL = 'http://localhost:11434'
MODEL_NAME = 'gemma3:4b-it-qat'


class VLMNode(Node):
    def __init__(self):
        super().__init__('vlm_node')
        self.get_logger().info('Starting VLM node')
        self.bridge = CvBridge()
        self.last_image_b64 = None
        self.create_subscription(Image, '/camera/image_raw', self.image_cb, 10)
        self.create_subscription(String, '/user/instruction', self.instruction_cb, 10)
        self.output_pub = self.create_publisher(String, '/vlm/output', 10)
        self.speech_pub = self.create_publisher(String, '/say_text', 10)
        self.motion_pub = self.create_publisher(String, '/vlm/motion_command', 10)

        # Start background thread to warm up the model
        import threading
        self.warmup_thread = threading.Thread(target=self.warmup_ollama, daemon=True)
        self.warmup_thread.start()
        
        self.get_logger().info('VLM Node ready (Warmup thread started in background)')

    def warmup_ollama(self):
        import time
        # Sleep to allow ROS2 network discovery to find the TTS node subscriber
        time.sleep(2.0)
        self.speech_pub.publish(String(data="Initialisation et préchauffage du modèle."))

        self.get_logger().info(f'Pre-loading and warming up model {MODEL_NAME} in Ollama...')
        # 1x1 black PNG in base64
        dummy_image = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='
        payload = {
            'model': MODEL_NAME,
            'prompt': 'initialization',
            'images': [dummy_image],
            'stream': False,
            'options': {
                'num_predict': 1
            },
            'keep_alive': -1
        }
        try:
            resp = requests.post(f'{OLLAMA_URL}/api/generate', json=payload, timeout=300)
            if resp.status_code == 200:
                self.get_logger().info('Ollama model pre-loaded and warmed up successfully!')
                self.speech_pub.publish(String(data="Le modèle est préchargé et prêt."))
            else:
                self.get_logger().warning(f'Warmup failed with status code {resp.status_code}')
        except Exception as e:
            self.get_logger().warning(f'Failed to warm up Ollama at startup: {e}')

    def image_cb(self, msg: Image):
        # convert to jpg base64
        try:
            cv_img = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            import cv2
            _, buf = cv2.imencode('.jpg', cv_img)
            self.last_image_b64 = base64.b64encode(buf.tobytes()).decode('utf-8')
        except Exception as e:
            self.get_logger().error(f'Image conversion failed: {e}')


    def instruction_cb(self, msg: String):
        user_instruction = msg.data
        if self.last_image_b64 is None:
            self.get_logger().warning('No image available yet, ignoring instruction')
            return
        
        system_prompt = f"""
        You are the onboard vision-language model of a two-wheeled mobile robot.
        You receive visual input from the robot's front-facing USB camera and text instructions from a human user.
        User instruction: {user_instruction}

        Your task is to interpret the scene and the user's instruction to answer the user's question or explain your action, and plan any necessary movement.
        Output a JSON object with exactly these three keys:
        1. "text_response": A string containing your answer to the user in French. If the user asks a question, answer it. If the user gives a movement command, explain what you are going to do.
        2. "distance_cm": The straight distance (in centimeters) the robot should move forward (+) or backward (-). Default to 0.0 if no movement is needed.
        3. "angle_deg": The rotation angle (in degrees) the robot should turn clockwise (+) or counterclockwise (-). Default to 0.0 if no rotation is needed.

        Guidelines:
        - Respond ONLY with a valid JSON object.
        - Do not include any explanations or text outside the JSON.
        - JSON format example:
        {{
          "text_response": "Je vais avancer de 50 cm pour éviter la boîte.",
          "distance_cm": 50.0,
          "angle_deg": 0.0
        }}
        """
        payload = {
            'model': MODEL_NAME,
            'prompt': system_prompt,
            'images': [self.last_image_b64],
            'stream': False,
            'keep_alive': -1
        }
        self.get_logger().info('Sending request to Gemma...')
        try:
            resp = requests.post(f'{OLLAMA_URL}/api/generate', json=payload, timeout=600)
            resp.raise_for_status()
            data = resp.json()
            # Ollama returns 'response' key
            response_text = data.get('response', '')
            # Publish raw response
            self.output_pub.publish(String(data=response_text))
            
            # Robust parsing of JSON response
            import re
            parsed_json = None
            try:
                parsed_json = json.loads(response_text.strip())
            except Exception:
                # Try finding JSON block in case model outputs markdown formatting
                match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if match:
                    try:
                        parsed_json = json.loads(match.group(0))
                    except Exception:
                        pass
            
            if parsed_json is not None:
                text_response = parsed_json.get('text_response', '')
                distance = parsed_json.get('distance_cm', 0.0)
                angle = parsed_json.get('angle_deg', 0.0)
                
                self.get_logger().info(f'Parsed VLM Response -> Speech: "{text_response}", Distance: {distance} cm, Angle: {angle} deg')
                
                # Publish speech text to TTS node
                if text_response:
                    self.speech_pub.publish(String(data=text_response))
                
                # Publish motion commands
                motion_data = json.dumps({"distance_cm": distance, "angle_deg": angle})
                self.motion_pub.publish(String(data=motion_data))
            else:
                self.get_logger().warning('Could not parse VLM response as JSON, falling back to reading raw output')
                # Fallback: treat whole response as text response
                self.speech_pub.publish(String(data=response_text))
                motion_data = json.dumps({"distance_cm": 0.0, "angle_deg": 0.0})
                self.motion_pub.publish(String(data=motion_data))
                
        except Exception as e:
            self.get_logger().error(f'VLM request failed: {e}')


def main(args=None):
    rclpy.init(args=args)
    node = VLMNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
