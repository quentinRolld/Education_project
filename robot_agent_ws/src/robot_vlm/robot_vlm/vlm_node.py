# -------------------------------
# file: robot_vlm/scripts/vlm_node.py
# -------------------------------
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import Empty, String
from sensor_msgs.msg import Image
import base64
import requests
import json
import re
import threading
import time
import cv2
import numpy as np
from cv_bridge import CvBridge


OLLAMA_URL = 'http://localhost:11434'
MODEL_NAME = 'gemma3:4b-it-qat'

# Matches a completed "text_response" string value (escaped quotes allowed) in a
# partially streamed JSON answer.
TEXT_RESPONSE_RE = re.compile(r'"text_response"\s*:\s*"((?:[^"\\]|\\.)*)"')

# Warm-up health check: on a healthy load a camera-sized image request takes
# ~7-9s; when part of the model fell back to CPU it takes minutes or fails.
HEALTHY_IMAGE_REQUEST_S = 20.0
WARMUP_MAX_ATTEMPTS = 3

# A pre-encoded frame older than this is considered stale and not used.
PREENCODED_FRAME_MAX_AGE_S = 20.0

# Shared by warmup and real requests: any difference (e.g. num_ctx) makes Ollama
# reload the model. The smaller context/batch leaves enough memory on the 8GB
# Orin for every layer and the vision encoder to stay on the GPU; with the
# defaults (4096/512) part of the model fell back to CPU and image requests
# took ~100s instead of ~10s.
OLLAMA_OPTIONS = {
    'num_ctx': 2048,
    'num_batch': 256,
    'temperature': 0.1,
}

# Everything that does not depend on the user's words comes first, so that the
# image + this prefix can be encoded while the user is still speaking and then
# reused from Ollama's cache when the transcribed instruction arrives (appended
# last). Must stay byte-identical between the pre-encode and the real request.
PROMPT_PREFIX = """You are the onboard vision-language model of a two-wheeled mobile robot.
You receive visual input from the robot's front-facing USB camera and text instructions from a human user.

Your task is to interpret the scene and the user's instruction to answer the user's question or explain your action, and plan any necessary movement.
Output a JSON object with exactly these three keys:
1. "text_response": A string containing your answer to the user in English. If the user asks a question, answer it. If the user gives a movement command, explain what you are going to do.
2. "distance_cm": The straight distance (in centimeters) the robot should move forward (+) or backward (-). Default to 0.0 if no movement is needed.
3. "angle_deg": The rotation angle (in degrees) the robot should turn clockwise (+) or counterclockwise (-). Default to 0.0 if no rotation is needed.

Guidelines:
- Respond ONLY with a valid JSON object.
- Keep "text_response" to one short sentence.
- Do not include any explanations or text outside the JSON.
- JSON format example:
{
  "text_response": "I will move forward by 50 cm to avoid the box.",
  "distance_cm": 50.0,
  "angle_deg": 0.0
}

"""


class VLMNode(Node):
    def __init__(self):
        super().__init__('vlm_node')
        self.get_logger().info('Starting VLM node')
        self.bridge = CvBridge()
        self.last_image_b64 = None
        self.create_subscription(Image, '/camera/image_raw', self.image_cb, 10)
        self.create_subscription(String, '/user/instruction', self.instruction_cb, 10)
        self.create_subscription(Empty, '/user/speech_started', self.speech_started_cb, 10)
        # Frame captured when the user started speaking, being/already encoded by Ollama
        self.speech_image_b64 = None
        self.speech_image_time = 0.0
        self.preencode_thread = None
        self.output_pub = self.create_publisher(String, '/vlm/output', 10)
        self.speech_pub = self.create_publisher(String, '/say_text', 10)
        self.motion_pub = self.create_publisher(String, '/vlm/motion_command', 10)

        # Start background thread to warm up the model
        self.warmup_thread = threading.Thread(target=self.warmup_ollama, daemon=True)
        self.warmup_thread.start()
        
        self.get_logger().info('VLM Node ready (Warmup thread started in background)')

    def warmup_ollama(self):
        # Sleep to allow ROS2 network discovery to find the TTS node subscriber
        time.sleep(2.0)
        self.speech_pub.publish(String(data="Initializing and warming up the model."))

        for attempt in range(1, WARMUP_MAX_ATTEMPTS + 1):
            self.get_logger().info(f'Loading {MODEL_NAME} in Ollama (attempt {attempt}/{WARMUP_MAX_ATTEMPTS})...')
            if not self.load_model():
                continue
            elapsed = self.time_image_request()
            if elapsed is not None and elapsed <= HEALTHY_IMAGE_REQUEST_S:
                self.get_logger().info(f'Model ready: image request took {elapsed:.1f}s')
                self.speech_pub.publish(String(data="The model is preloaded and ready."))
                return
            # On the 8GB Orin a large GPU allocation can fail at load time; Ollama then
            # silently keeps part of the model on the CPU and image requests take
            # minutes or fail. Reloading from a clean state usually fixes it.
            self.get_logger().warning(
                f'Image request took {"too long" if elapsed is None else f"{elapsed:.1f}s"}: '
                'model probably partly on CPU, reloading it'
            )
            self.unload_model()

        self.get_logger().error('Model still slow after reloads; check `journalctl -u ollama` for NvMap errors')
        self.speech_pub.publish(String(data="Warning, the model is running slowly."))

    def load_model(self) -> bool:
        payload = {
            'model': MODEL_NAME,
            'prompt': 'initialization',
            'stream': False,
            'options': {**OLLAMA_OPTIONS, 'num_predict': 1},
            'keep_alive': -1
        }
        try:
            requests.post(f'{OLLAMA_URL}/api/generate', json=payload, timeout=300).raise_for_status()
            return True
        except Exception as e:
            self.get_logger().warning(f'Failed to load the model in Ollama: {e}')
            return False

    def time_image_request(self):
        """Time one request with a camera-sized image (fresh, so not cached).
        Returns the duration in seconds, or None if it failed or timed out."""
        noise = np.random.default_rng().integers(0, 255, (480, 640, 3), dtype=np.uint8)
        image_b64 = base64.b64encode(cv2.imencode('.jpg', noise)[1].tobytes()).decode('utf-8')
        payload = {
            'model': MODEL_NAME,
            'prompt': 'Describe the image in one word.',
            'images': [image_b64],
            'stream': False,
            'options': {**OLLAMA_OPTIONS, 'num_predict': 1},
            'keep_alive': -1
        }
        start = time.monotonic()
        try:
            requests.post(f'{OLLAMA_URL}/api/generate', json=payload, timeout=90).raise_for_status()
            return time.monotonic() - start
        except Exception as e:
            self.get_logger().warning(f'Warm-up image request failed: {e}')
            return None

    def unload_model(self):
        try:
            requests.post(f'{OLLAMA_URL}/api/generate', json={'model': MODEL_NAME, 'keep_alive': 0}, timeout=150)
            for _ in range(60):
                loaded = requests.get(f'{OLLAMA_URL}/api/ps', timeout=10).json().get('models', [])
                if not any(m.get('name') == MODEL_NAME for m in loaded):
                    return
                time.sleep(2.0)
        except Exception as e:
            self.get_logger().warning(f'Failed to unload the model: {e}')

    def image_cb(self, msg: Image):
        # convert to jpg base64
        try:
            cv_img = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            
            # Resize image to speed up VLM inference by reducing visual tokens
            height, width = cv_img.shape[:2]
            if width > 640 or height > 480:
                cv_img = cv2.resize(cv_img, (640, 480))
                
            # Compress slightly more to reduce base64 size
            _, buf = cv2.imencode('.jpg', cv_img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            self.last_image_b64 = base64.b64encode(buf.tobytes()).decode('utf-8')
        except Exception as e:
            self.get_logger().error(f'Image conversion failed: {e}')


    def speech_started_cb(self, msg: Empty):
        if self.last_image_b64 is None:
            return
        if self.preencode_thread is not None and self.preencode_thread.is_alive():
            return  # Ollama handles one request at a time; don't queue a second encode
        self.speech_image_b64 = self.last_image_b64
        self.speech_image_time = time.monotonic()
        self.preencode_thread = threading.Thread(
            target=self.preencode_frame, args=(self.speech_image_b64,), daemon=True
        )
        self.preencode_thread.start()

    def preencode_frame(self, image_b64: str):
        # Same image and prompt prefix as the upcoming real request, so Ollama keeps
        # the encoded image in its cache and the real request skips the ~6s encode.
        payload = {
            'model': MODEL_NAME,
            'prompt': PROMPT_PREFIX,
            'images': [image_b64],
            'stream': False,
            'options': {**OLLAMA_OPTIONS, 'num_predict': 1},
            'keep_alive': -1
        }
        start = time.monotonic()
        try:
            requests.post(f'{OLLAMA_URL}/api/generate', json=payload, timeout=120).raise_for_status()
            self.get_logger().info(f'Frame pre-encoded while user speaks ({time.monotonic() - start:.1f}s)')
        except Exception as e:
            self.get_logger().warning(f'Frame pre-encoding failed: {e}')

    def instruction_cb(self, msg: String):
        user_instruction = msg.data
        if self.last_image_b64 is None:
            self.get_logger().warning('No image available yet, ignoring instruction')
            return

        # Prefer the frame captured at speech onset: it is the one Ollama has (or is
        # finishing) encoded, and it shows the scene the user was talking about.
        image_b64 = self.last_image_b64
        if self.speech_image_b64 is not None and time.monotonic() - self.speech_image_time < PREENCODED_FRAME_MAX_AGE_S:
            image_b64 = self.speech_image_b64
        self.speech_image_b64 = None


        system_prompt = PROMPT_PREFIX + f'User instruction: {user_instruction}\n'
        payload = {
            'model': MODEL_NAME,
            'prompt': system_prompt,
            'images': [image_b64],
            # Streamed so the spoken answer can go to TTS as soon as "text_response"
            # is complete, without waiting for the motion fields that follow it.
            'stream': True,
            # No 'format': 'json': Ollama's constrained decoding added ~1s per request on
            # the Orin; the regex fallback below already strips the ```json fences.
            'options': {**OLLAMA_OPTIONS, 'num_predict': 100},
            'keep_alive': -1
        }
        self.get_logger().info('Sending request to Gemma...')
        start = time.monotonic()
        try:
            response_text = ''
            spoken_text = None
            with requests.post(f'{OLLAMA_URL}/api/generate', json=payload, timeout=600, stream=True) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    response_text += chunk.get('response', '')
                    if spoken_text is None:
                        match = TEXT_RESPONSE_RE.search(response_text)
                        if match:
                            spoken_text = json.loads(f'"{match.group(1)}"')
                            self.get_logger().info(f'Speech ready ({time.monotonic() - start:.1f}s): "{spoken_text}"')
                            if spoken_text:
                                self.speech_pub.publish(String(data=spoken_text))
                    if chunk.get('done'):
                        break

            # Publish raw response
            self.output_pub.publish(String(data=response_text))

            # Robust parsing of JSON response
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

                self.get_logger().info(f'Parsed VLM Response ({time.monotonic() - start:.1f}s) -> Speech: "{text_response}", Distance: {distance} cm, Angle: {angle} deg')

                # Publish speech text to TTS node, unless it was already spoken while streaming
                if text_response and spoken_text is None:
                    self.speech_pub.publish(String(data=text_response))

                # Publish motion commands
                motion_data = json.dumps({"distance_cm": distance, "angle_deg": angle})
                self.motion_pub.publish(String(data=motion_data))
            else:
                self.get_logger().warning('Could not parse VLM response as JSON, falling back to reading raw output')
                # Fallback: treat whole response as text response
                if spoken_text is None:
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
