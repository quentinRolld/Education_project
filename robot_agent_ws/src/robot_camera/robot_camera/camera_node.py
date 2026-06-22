
# -------------------------------
# file: robot_camera/camera_node.py
# -------------------------------
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2


class CameraNode(Node):
    def __init__(self):
        super().__init__('camera_node')
        # Declare parameter for camera index (default: 0)
        self.declare_parameter('device_index', 0)
        self.device_index = self.get_parameter('device_index').value

        self.publisher_ = self.create_publisher(Image, '/camera/image_raw', 10)
        self.timer = self.create_timer(0.2, self.timer_callback)
        self.bridge = CvBridge()
        
        self.get_logger().info(f'Opening camera device index {self.device_index} (V4L2)...')
        self.cap = cv2.VideoCapture(self.device_index, cv2.CAP_V4L2)
        if not self.cap.isOpened():
            self.get_logger().error(f'Could not open camera device {self.device_index}')
        else:
            # Configure resolution and compression to avoid USB bandwidth issues on Jetson
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            
            # warmup
            import time
            time.sleep(1.0)
            self.get_logger().info(f'Camera device {self.device_index} opened and configured (640x480 MJPG)')


    def timer_callback(self):
        if not self.cap.isOpened():
            return
        ret, frame = self.cap.read()
        if not ret:
            self.get_logger().warning('Camera read failed')
            return
        # Optionally resize to 512x512 for VLM
        frame = cv2.resize(frame, (512, 512))
        msg = self.bridge.cv2_to_imgmsg(frame, encoding='bgr8')
        self.publisher_.publish(msg)


    def destroy_node(self):
        try:
            self.get_logger().info('Releasing camera capture...')
            self.cap.release()
        except Exception:
            pass
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = CameraNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
