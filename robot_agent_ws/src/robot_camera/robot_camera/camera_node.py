
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
        self.publisher_ = self.create_publisher(Image, '/camera/image_raw', 10)
        self.timer = self.create_timer(0.2, self.timer_callback)
        self.bridge = CvBridge()
        # OpenCV VideoCapture 0
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self.get_logger().error('Could not open camera device 0')
        else:
        # warmup
            import time
            time.sleep(1.0)
            self.get_logger().info('Camera opened')


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


    def destroy(self):
        try:
            self.cap.release()
        except Exception:
            pass


def main(args=None):
    rclpy.init(args=args)
    node = CameraNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
