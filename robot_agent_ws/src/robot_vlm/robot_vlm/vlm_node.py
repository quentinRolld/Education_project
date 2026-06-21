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

        # Warmup model at startup (non-blocking thread could be used, but a blocking warmup is fine here)
        self.get_logger().info('Warming up Gemma model (this may take time)...')
        try:
            requests.post(f'{OLLAMA_URL}/api/generate', json={'model': MODEL_NAME, 'prompt': 'warmup', 'stream': False}, timeout=120)
        except Exception as e:
            self.get_logger().warning(f'Warmup request failed: {e}')
        self.get_logger().info('VLM ready')


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
        # build prompt
        system_prompt = f"""
        You are the onboard vision-language model of a two-wheeled mobile robot.
        You receive visual input from the robot's front-facing USB camera and text instructions from a human user.
        User instruction: {user_instruction}

        Your task is to interpret the scene and the user's instruction to determine a simple motion plan.
        Output strictly two values:
        1. The straight distance (in centimeters) the robot should move forward (+) or backward (−).
        2. The rotation angle (in degrees) the robot should turn clockwise (+) or counterclockwise (−).

        Guidelines:
        - Respond only with a JSON object in the form:
        {{"distance_cm": float, "angle_deg": float}}
        - Do not include explanations or any text outside this JSON.
        - If the task cannot be interpreted, respond with {{"distance_cm": 0.0, "angle_deg": 0.0}}.
        """
        payload = {
            'model': MODEL_NAME,
            'prompt': system_prompt,
            'images': [self.last_image_b64],
            'stream': False
        }
        self.get_logger().info('Sending request to Gemma...')
        try:
            resp = requests.post(f'{OLLAMA_URL}/api/generate', json=payload, timeout=600)
            resp.raise_for_status()
            data = resp.json()
            # Ollama returns 'response' key
            response_text = data.get('response', '')
            # Publish raw response and parsed JSON
            self.output_pub.publish(String(data=response_text))
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
