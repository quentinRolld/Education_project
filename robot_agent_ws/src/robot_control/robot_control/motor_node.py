#!/usr/bin/env python3
# -------------------------------
# file: robot_control/motor_node.py
# -------------------------------
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import json
import time

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
            self.get_logger().warning('Jetson.GPIO not available. Running in MOCK MODE.')

        # ROS2 Parameters for hardware pin configuration (using physical BOARD pins)
        # Adjust these defaults based on your physical wiring
        self.declare_parameter('left_pwm_pin', 32)      # ENA
        self.declare_parameter('left_dir1_pin', 11)     # IN1
        self.declare_parameter('left_dir2_pin', 12)     # IN2

        self.declare_parameter('right_pwm_pin', 33)     # ENB
        self.declare_parameter('right_dir1_pin', 13)    # IN3
        self.declare_parameter('right_dir2_pin', 15)    # IN4

        # Speed and calibration parameters
        self.declare_parameter('translation_speed_pct', 50.0)  # Duty cycle % (0 to 100)
        self.declare_parameter('rotation_speed_pct', 40.0)     # Duty cycle % (0 to 100)
        self.declare_parameter('sec_per_cm', 0.05)            # Calibration: seconds needed to travel 1 cm
        self.declare_parameter('sec_per_deg', 0.015)          # Calibration: seconds needed to rotate 1 degree

        # Retrieve parameter values
        self.l_pwm = self.get_parameter('left_pwm_pin').value
        self.l_dir1 = self.get_parameter('left_dir1_pin').value
        self.l_dir2 = self.get_parameter('left_dir2_pin').value
        
        self.r_pwm = self.get_parameter('right_pwm_pin').value
        self.r_dir1 = self.get_parameter('right_dir1_pin').value
        self.r_dir2 = self.get_parameter('right_dir2_pin').value

        self.trans_speed = self.get_parameter('translation_speed_pct').value
        self.rot_speed = self.get_parameter('rotation_speed_pct').value
        self.sec_per_cm = self.get_parameter('sec_per_cm').value
        self.sec_per_deg = self.get_parameter('sec_per_deg').value

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
            
            # Setup direction pins as output
            GPIO.setup(self.l_dir1, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(self.l_dir2, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(self.r_dir1, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(self.r_dir2, GPIO.OUT, initial=GPIO.LOW)
            
            # Setup PWM pins
            GPIO.setup(self.l_pwm, GPIO.OUT)
            GPIO.setup(self.r_pwm, GPIO.OUT)
            
            # Initialize PWM at 50Hz frequency
            self.pwm_left = GPIO.PWM(self.l_pwm, 50)
            self.pwm_right = GPIO.PWM(self.r_pwm, 50)
            
            self.pwm_left.start(0)
            self.pwm_right.start(0)
            self.get_logger().info('GPIO Hardware configured successfully')
        except Exception as e:
            self.get_logger().error(f'Failed to configure GPIO: {e}')

    def set_motors(self, left_speed_pct, right_speed_pct, left_forward=True, right_forward=True):
        """Sets the direction pins and PWM duty cycles for both motors."""
        self.get_logger().debug(f'Setting motors: L_speed={left_speed_pct}% (Fwd={left_forward}), R_speed={right_speed_pct}% (Fwd={right_forward})')
        
        if GPIO_AVAILABLE:
            # Left motor direction
            GPIO.output(self.l_dir1, GPIO.HIGH if left_forward else GPIO.LOW)
            GPIO.output(self.l_dir2, GPIO.LOW if left_forward else GPIO.HIGH)
            
            # Right motor direction
            GPIO.output(self.r_dir1, GPIO.HIGH if right_forward else GPIO.LOW)
            GPIO.output(self.r_dir2, GPIO.LOW if right_forward else GPIO.HIGH)
            
            # Set speed (duty cycle)
            self.pwm_left.ChangeDutyCycle(left_speed_pct)
            self.pwm_right.ChangeDutyCycle(right_speed_pct)
        else:
            # Mock mode logs
            self.get_logger().info(
                f'[MOCK MOTOR] L_pins: ({self.l_dir1}={1 if left_forward else 0}, {self.l_dir2}={0 if left_forward else 1}), '
                f'R_pins: ({self.r_dir1}={1 if right_forward else 0}, {self.r_dir2}={0 if right_forward else 1}) | '
                f'PWM: L={left_speed_pct}%, R={right_speed_pct}%'
            )

    def stop_motors(self):
        """Stops both motors immediately."""
        self.get_logger().info('Stopping motors')
        if GPIO_AVAILABLE:
            self.pwm_left.ChangeDutyCycle(0)
            self.pwm_right.ChangeDutyCycle(0)
            GPIO.output(self.l_dir1, GPIO.LOW)
            GPIO.output(self.l_dir2, GPIO.LOW)
            GPIO.output(self.r_dir1, GPIO.LOW)
            GPIO.output(self.r_dir2, GPIO.LOW)
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
            duration = abs(angle) * self.sec_per_deg
            # Clockwise (+) turn: left wheel forward, right wheel backward
            # Counterclockwise (-) turn: left wheel backward, right wheel forward
            left_fwd = (angle > 0.0)
            right_fwd = (angle < 0.0)
            
            self.get_logger().info(f'Starting rotation for {duration:.3f} seconds')
            self.set_motors(self.rot_speed, self.rot_speed, left_fwd, right_fwd)
            time.sleep(duration)
            self.stop_motors()
            time.sleep(0.2)  # Short pause between moves

        # 2. Execute Translation next
        if distance != 0.0:
            duration = abs(distance) * self.sec_per_cm
            # Forward (+): both wheels forward
            # Backward (-): both wheels backward
            fwd = (distance > 0.0)
            
            self.get_logger().info(f'Starting translation for {duration:.3f} seconds')
            self.set_motors(self.trans_speed, self.trans_speed, fwd, fwd)
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
