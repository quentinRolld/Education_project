#!/usr/bin/env python3
# -------------------------------
# file: robot_control/motor_node.py
# -------------------------------
import rclpy
from rclpy.node import Node
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from std_msgs.msg import String
from nav_msgs.msg import Odometry
import json
import time
import math
import threading

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
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
        
        self.declare_parameter('wheel_base_cm', 20.0)      # recalibrated from field test: 45deg command rotated 90deg
        self.declare_parameter('max_speed_cm_s', 60.0)     # recalibrated from field test: 10cm command covered 30cm at 50% pwm
        self.declare_parameter('translation_speed_pct', 10.0)  # default % speed for lines
        self.declare_parameter('rotation_speed_pct', 12.5)     # default % speed for turns

        # Wheel encoders: slotted disk + IR fork sensor on each wheel axle, single channel
        # (no direction info, so the commanded direction is used to sign the ticks)
        self.declare_parameter('use_encoders', True)
        self.declare_parameter('enc_left_pin', 11)
        self.declare_parameter('enc_right_pin', 13)
        self.declare_parameter('encoder_slots', 20)         # slots on the disk
        self.declare_parameter('wheel_diameter_cm', 6.5)    # measure on the robot
        self.declare_parameter('track_width_cm', 20.0)      # distance between the two wheel contact points, measure on the robot

        # Retrieve parameter values
        self.l_pwm = self.get_parameter('pwm_left_pin').value
        self.l_dir = self.get_parameter('dir_left_pin').value
        self.r_pwm = self.get_parameter('pwm_right_pin').value
        self.r_dir = self.get_parameter('dir_right_pin').value

        self.wheel_base = self.get_parameter('wheel_base_cm').value
        self.max_speed = self.get_parameter('max_speed_cm_s').value
        self.trans_speed = self.get_parameter('translation_speed_pct').value
        self.rot_speed = self.get_parameter('rotation_speed_pct').value

        self.use_encoders = self.get_parameter('use_encoders').value and GPIO_AVAILABLE
        self.enc_left = self.get_parameter('enc_left_pin').value
        self.enc_right = self.get_parameter('enc_right_pin').value
        self.track_width = self.get_parameter('track_width_cm').value
        # Both edges of each slot are counted, so 2 ticks per slot
        self.cm_per_tick = (math.pi * self.get_parameter('wheel_diameter_cm').value
                            / (2 * self.get_parameter('encoder_slots').value))

        # Signed tick counts, written from the GPIO callback thread
        self.tick_lock = threading.Lock()
        self.left_ticks = 0
        self.right_ticks = 0
        # Last commanded direction of each wheel, kept after a stop so coasting ticks are signed correctly
        self.left_sign = 1
        self.right_sign = 1

        # Odometry pose in the odom frame (m, rad), integrated from the ticks
        self.x = 0.0
        self.y = 0.0
        self.theta = 0.0
        self.prev_left_ticks = 0
        self.prev_right_ticks = 0
        self.prev_odom_time = self.get_clock().now()

        # Setup GPIO
        self.setup_gpio()
        if self.use_encoders:
            self.setup_encoders()

        # Motion commands block for their whole duration: give them their own callback group
        # so the odometry timer keeps running in parallel (MultiThreadedExecutor in main)
        self.sub = self.create_subscription(String, '/vlm/motion_command', self.motion_cb, 10,
                                            callback_group=MutuallyExclusiveCallbackGroup())
        self.odom_pub = self.create_publisher(Odometry, '/odom', 10)
        self.create_timer(0.05, self.publish_odom, callback_group=MutuallyExclusiveCallbackGroup())
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

    def setup_encoders(self):
        try:
            for pin, callback in ((self.enc_left, self.left_tick_cb), (self.enc_right, self.right_tick_cb)):
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                GPIO.add_event_detect(pin, GPIO.BOTH, callback=callback, bouncetime=1)
            self.get_logger().info(
                f'Wheel encoders on pins {self.enc_left}/{self.enc_right} ({self.cm_per_tick:.3f} cm per tick)'
            )
        except Exception as e:
            self.use_encoders = False
            self.get_logger().error(f'Failed to configure wheel encoders, falling back to timed moves: {e}')

    def left_tick_cb(self, channel):
        with self.tick_lock:
            self.left_ticks += self.left_sign

    def right_tick_cb(self, channel):
        with self.tick_lock:
            self.right_ticks += self.right_sign

    def get_ticks(self):
        with self.tick_lock:
            return self.left_ticks, self.right_ticks

    def publish_odom(self):
        left, right = self.get_ticks()
        now = self.get_clock().now()
        dt = (now - self.prev_odom_time).nanoseconds * 1e-9
        d_left = (left - self.prev_left_ticks) * self.cm_per_tick / 100.0
        d_right = (right - self.prev_right_ticks) * self.cm_per_tick / 100.0
        self.prev_left_ticks, self.prev_right_ticks, self.prev_odom_time = left, right, now

        # Differential drive: forward distance and heading change (counter-clockwise positive, REP 103)
        d_center = (d_left + d_right) / 2
        d_theta = (d_right - d_left) / (self.track_width / 100.0)
        self.x += d_center * math.cos(self.theta + d_theta / 2)
        self.y += d_center * math.sin(self.theta + d_theta / 2)
        self.theta = math.atan2(math.sin(self.theta + d_theta), math.cos(self.theta + d_theta))

        msg = Odometry()
        msg.header.stamp = now.to_msg()
        msg.header.frame_id = 'odom'
        msg.child_frame_id = 'base_link'
        msg.pose.pose.position.x = self.x
        msg.pose.pose.position.y = self.y
        msg.pose.pose.orientation.z = math.sin(self.theta / 2)
        msg.pose.pose.orientation.w = math.cos(self.theta / 2)
        if dt > 0:
            msg.twist.twist.linear.x = d_center / dt
            msg.twist.twist.angular.z = d_theta / dt
        self.odom_pub.publish(msg)

    def drive(self, left_speed, right_speed, target_cm, timed_duration):
        """
        Runs both wheels until they have covered target_cm on average (measured by the encoders),
        or for timed_duration seconds when the encoders are not available.
        """
        if not self.use_encoders:
            self.get_logger().info(f'Moving for {timed_duration:.3f} seconds (timed, no encoders)')
            self.set_motors(left_speed, right_speed)
            time.sleep(timed_duration)
            self.stop_motors()
            return

        start_left, start_right = self.get_ticks()
        start_time = time.monotonic()
        # Safety net in case a wheel is blocked or a sensor stops counting mid-move
        deadline = start_time + 2 * timed_duration + 2.0
        self.get_logger().info(f'Moving {target_cm:.1f} cm per wheel (encoders)')
        self.set_motors(left_speed, right_speed)

        while True:
            left, right = self.get_ticks()
            covered = (abs(left - start_left) + abs(right - start_right)) / 2 * self.cm_per_tick
            if covered >= target_cm:
                break
            now = time.monotonic()
            if left == start_left and right == start_right and now - start_time > 1.0:
                # Sensors unplugged or misaligned: finish this move on time instead of running forever
                self.get_logger().warning('No encoder ticks after 1s, finishing this move on time')
                time.sleep(max(0.0, timed_duration - (now - start_time)))
                break
            if now > deadline:
                self.get_logger().warning(f'Move timed out after {covered:.1f}/{target_cm:.1f} cm')
                break
            time.sleep(0.005)

        self.stop_motors()
        time.sleep(0.3)  # let the robot coast to a stop before reading the final ticks
        left, right = self.get_ticks()
        self.get_logger().info(
            f'Move done: left {abs(left - start_left) * self.cm_per_tick:.1f} cm, '
            f'right {abs(right - start_right) * self.cm_per_tick:.1f} cm '
            f'({abs(left - start_left)}/{abs(right - start_right)} ticks)'
        )

    def set_motors(self, left_speed, right_speed):
        """
        Sets motor direction and speed.
        left_speed and right_speed are in % (-100 to +100)
        """
        self.get_logger().debug(f'Setting speeds: Left={left_speed}%, Right={right_speed}%')
        with self.tick_lock:
            if left_speed != 0:
                self.left_sign = 1 if left_speed > 0 else -1
            if right_speed != 0:
                self.right_sign = 1 if right_speed > 0 else -1
        
        if GPIO_AVAILABLE and hasattr(self, 'pwm_left') and hasattr(self, 'pwm_right'):
            # Left wheel direction and PWM speed
            GPIO.output(self.l_dir, GPIO.LOW if left_speed < 0 else GPIO.HIGH)
            self.pwm_left.ChangeDutyCycle(abs(left_speed))

            # Right wheel direction and PWM speed (symmetrical mounting offset)
            GPIO.output(self.r_dir, GPIO.HIGH if right_speed < 0 else GPIO.LOW)
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
        if GPIO_AVAILABLE and hasattr(self, 'pwm_left') and hasattr(self, 'pwm_right'):
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
            # Distance traveled by each wheel during in-place rotation: the measured track width
            # is used with encoders, the calibrated wheel_base for timed moves
            arc_length = (self.track_width * angle_rad) / 2

            # Duration based on calibration formula
            duration = (self.wheel_base * angle_rad) / 2 / (self.max_speed * (self.rot_speed / 100))

            self.get_logger().info(f'Starting rotation of {angle}°')
            # One wheel forward, one wheel backward
            self.drive(direction * self.rot_speed, -direction * self.rot_speed, arc_length, duration)
            time.sleep(0.2)  # Short pause between moves

        # 2. Execute Translation next
        if distance != 0.0:
            direction = 1 if distance >= 0 else -1
            # Duration based on calibration formula
            duration = abs(distance) / (self.max_speed * (self.trans_speed / 100))
            
            self.get_logger().info(f'Starting translation of {distance} cm')
            # Both wheels same direction
            self.drive(direction * self.trans_speed, direction * self.trans_speed, abs(distance), duration)

        self.get_logger().info('Motion command finished successfully')

    def destroy_node(self):
        self.stop_motors()
        if GPIO_AVAILABLE:
            try:
                if hasattr(self, 'pwm_left'):
                    self.pwm_left.stop()
                if hasattr(self, 'pwm_right'):
                    self.pwm_right.stop()
                GPIO.cleanup()
                self.get_logger().info('GPIO Cleaned up')
            except Exception as e:
                self.get_logger().warning(f'Failed to cleanup GPIO: {e}')
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = MotorNode()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
