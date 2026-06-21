#!/usr/bin/env python3
# -------------------------------
# file: robot_control/motor_node.py
# -------------------------------
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import json
import time
import math

try:
    import Jetson.GPIO as GPIO
    GPIO_AVAILABLE = True
except Exception:
    GPIO_AVAILABLE = False


class MotorNode(Node):
    def __init__(self):
        super().__init__('motor_node')
        self.get_logger().info('Starting Motor Control Node')

        if not GPIO_AVAILABLE:
            self.get_logger().warning('Jetson.GPIO not available or model undetermined. Running in MOCK MODE.')

        # ROS2 Parameters mapping directly to your working robot script
        self.declare_parameter('pwm_left_pin', 33)
        self.declare_parameter('dir_left_pin', 29)
        self.declare_parameter('pwm_right_pin', 15)
        self.declare_parameter('dir_right_pin', 7)
        
        self.declare_parameter('wheel_base_cm', 40.0)      # distance between wheels
        self.declare_parameter('max_speed_cm_s', 20.0)     # max speed at 100% PWM
        self.declare_parameter('translation_speed_pct', 50.0)  # default % speed for lines
        self.declare_parameter('rotation_speed_pct', 40.0)     # default % speed for turns

        # Retrieve parameter values
        self.l_pwm = self.get_parameter('pwm_left_pin').value
        self.l_dir = self.get_parameter('dir_left_pin').value
        self.r_pwm = self.get_parameter('pwm_right_pin').value
        self.r_dir = self.get_parameter('dir_right_pin').value

        self.wheel_base = self.get_parameter('wheel_base_cm').value
        self.max_speed = self.get_parameter('max_speed_cm_s').value
        self.trans_speed = self.get_parameter('translation_speed_pct').value
        self.rot_speed = self.get_parameter('rotation_speed_pct').value

        # Setup GPIO
        self.setup_gpio()

        # Subscribe to VLM motion commands
        self.sub = self.create_subscription(String, '/vlm/motion_command', self.motion_cb, 10)
        self.get_logger().info('Motor Node Initialized and Ready')

    def setup_gpio(self):
        if not GPIO_AVAILABLE:
            return
        
        try:
            GPIO.setmode(GPIO.BOARD)
            GPIO.setwarnings(False)
            
            # Setup direction pins as output
            GPIO.setup([self.l_dir, self.r_dir], GPIO.OUT, initial=GPIO.LOW)
            
            # Setup PWM pins
            GPIO.setup(self.l_pwm, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(self.r_pwm, GPIO.OUT, initial=GPIO.LOW)
            
            # Initialize PWM at 1000Hz frequency
            self.pwm_left = GPIO.PWM(self.l_pwm, 1000)
            self.pwm_right = GPIO.PWM(self.r_pwm, 1000)
            
            self.pwm_left.start(0)
            self.pwm_right.start(0)
            self.get_logger().info('GPIO Hardware configured successfully (1000Hz PWM)')
        except Exception as e:
            self.get_logger().error(f'Failed to configure GPIO: {e}')

    def set_motors(self, left_speed, right_speed):
        """
        Sets motor direction and speed.
        left_speed and right_speed are in % (-100 to +100)
        """
        self.get_logger().debug(f'Setting speeds: Left={left_speed}%, Right={right_speed}%')
        
        if GPIO_AVAILABLE:
            # Left wheel direction and PWM speed
            GPIO.output(self.l_dir, GPIO.HIGH if left_speed < 0 else GPIO.LOW)
            self.pwm_left.ChangeDutyCycle(abs(left_speed))
            
            # Right wheel direction and PWM speed (symmetrical mounting offset)
            GPIO.output(self.r_dir, GPIO.LOW if right_speed < 0 else GPIO.HIGH)
            self.pwm_right.ChangeDutyCycle(abs(right_speed))
        else:
            # Mock mode logs
            self.get_logger().info(
                f'[MOCK MOTOR] GPIO outputs: '
                f'Left_Dir({self.l_dir})={"HIGH" if left_speed < 0 else "LOW"}, Speed={abs(left_speed)}% | '
                f'Right_Dir({self.r_dir})={"LOW" if right_speed < 0 else "HIGH"}, Speed={abs(right_speed)}%'
            )

    def stop_motors(self):
        """Stops both motors immediately."""
        self.get_logger().info('Stopping motors')
        if GPIO_AVAILABLE:
            self.pwm_left.ChangeDutyCycle(0)
            self.pwm_right.ChangeDutyCycle(0)
            GPIO.output(self.l_dir, GPIO.LOW)
            GPIO.output(self.r_dir, GPIO.LOW)
        else:
            self.get_logger().info('[MOCK MOTOR] Stop (PWM=0%)')

    def motion_cb(self, msg: String):
        try:
            command = json.loads(msg.data)
            distance = command.get('distance_cm', 0.0)
            angle = command.get('angle_deg', 0.0)
        except Exception as e:
            self.get_logger().error(f'Failed to parse motion command JSON: {e}')
            return

        if distance == 0.0 and angle == 0.0:
            self.get_logger().info('Zero motion command received, keeping motors stopped.')
            return

        self.get_logger().info(f'Executing motion command: Rotate {angle}° | Translate {distance} cm')

        # 1. Execute Rotation first
        if angle != 0.0:
            direction = 1 if angle > 0 else -1
            angle_rad = abs(angle) * math.pi / 180
            # Distance traveled by each wheel during in-place rotation
            arc_length = (self.wheel_base * angle_rad) / 2
            
            # Duration based on calibration formula
            duration = arc_length / (self.max_speed * (self.rot_speed / 100))
            
            self.get_logger().info(f'Starting rotation for {duration:.3f} seconds')
            # One wheel forward, one wheel backward
            self.set_motors(direction * self.rot_speed, -direction * self.rot_speed)
            time.sleep(duration)
            self.stop_motors()
            time.sleep(0.2)  # Short pause between moves

        # 2. Execute Translation next
        if distance != 0.0:
            direction = 1 if distance >= 0 else -1
            # Duration based on calibration formula
            duration = abs(distance) / (self.max_speed * (self.trans_speed / 100))
            
            self.get_logger().info(f'Starting translation for {duration:.3f} seconds')
            # Both wheels same direction
            self.set_motors(direction * self.trans_speed, direction * self.trans_speed)
            time.sleep(duration)
            self.stop_motors()

        self.get_logger().info('Motion command finished successfully')

    def destroy_node(self):
        self.stop_motors()
        if GPIO_AVAILABLE:
            try:
                self.pwm_left.stop()
                self.pwm_right.stop()
                GPIO.cleanup()
                self.get_logger().info('GPIO Cleaned up')
            except Exception as e:
                self.get_logger().warning(f'Failed to cleanup GPIO: {e}')
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = MotorNode()
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
