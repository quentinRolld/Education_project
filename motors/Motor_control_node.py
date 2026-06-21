import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32MultiArray
import RPi.GPIO as GPIO  


class MotorControlNode(Node):
    def __init__(self):
        super().__init__('motor_control_node')
        self.subscription = self.create_subscription(
            Float32MultiArray,
            '/motor_instructions',
            self.motor_instructions_callback,
            10
        )
        # GPIO port definition
        self.in1_motor1 = 24
        self.in2_motor1 = 23
        self.en_1 = 25
        #self.in1_motor2 =
        #self.in2_motor2 =
        #self.en_2 =

        # GPIO Initialization
        GPIO.setmode(GPIO.BCM)
        # Motor 1
        GPIO.setup(self.in1_motor1,GPIO.OUT)
        GPIO.setup(self.in2_motor1,GPIO.OUT)
        GPIO.setup(self.en_1,GPIO.OUT)
        GPIO.output(self.in1_motor1,GPIO.LOW)
        GPIO.output(self.in2_motor1,GPIO.LOW)
        # Motor 2
        #GPIO.setup(self.in1_motor2,GPIO.OUT)
        #GPIO.setup(self.in2_motor2,GPIO.OUT)
        #GPIO.setup(self.en_2,GPIO.OUT)
        #GPIO.output(self.in1_motor2,GPIO.LOW)
        #GPIO.output(self.in2_motor2,GPIO.LOW)
        # PWM Initialization
        p=GPIO.PWM(en_1,1000)
        #p=GPIO.PWM(en_2,1000)

    def motor_rates_callback(self, msg):
        # Retrieve motor instruction from message
        # Motor 1
        motor_1_direction = msg.direction1
        self.en_1 = msg.speed1
        # Motor 2
        motor_2_direction = msg.direction2
        self.en_2 = msg.speed2
        # Apply computed angles to the servos
        self.apply_motor_values(direc1, speed1, direc2, speed2)

    def apply_motor_values(self, direc1, speed1, direc2, speed2):
        
        # Motor 1
        # direction
        if direc1=="forward":
            GPIO.output(self.in1_1,GPIO.HIGH)
            GPIO.output(self.in2_1,GPIO.LOW)
        elif direc1=="backward":
            GPIO.output(self.in1_1,GPIO.LOW)
            GPIO.output(self.in2_1,GPIO.HIGH)
        elif direc1=="stop":
            GPIO.output(self.in1_1,GPIO.LOW)
            GPIO.output(self.in2_1,GPIO.LOW)
        else:
            self.get_logger().warn("Received invalid direction")
        # speed
        if speed1 <= 25:
            p.ChangeDutyCycle(25)
        elif speed1 >= 75:
            p.ChangeDutyCycle(75)
        else :
            p.ChangeDutyCycle(self.en_1)

        # Motor 2
        # direction
        if direc2=="forward":
            GPIO.output(self.in1_2,GPIO.HIGH)
            GPIO.output(self.in2_2,GPIO.LOW)
        elif direc2=="backward":
            GPIO.output(self.in1_2,GPIO.LOW)
            GPIO.output(self.in2_2,GPIO.HIGH)
        elif direc2=="stop":
            GPIO.output(self.in1_2,GPIO.LOW)
            GPIO.output(self.in2_2,GPIO.LOW)
        else:
            self.get_logger().warn("Received invalid direction")
        # speed
        if speed1 <= 25:
            p.ChangeDutyCycle(25)
        elif speed1 >= 75:
            p.ChangeDutyCycle(75)
        else :
            p.ChangeDutyCycle(self.en_2)


def main(args=None):
    rclpy.init(args=args)
    motor_control_node = MotorControlNode()
    rclpy.spin(motor_control_node)
    motor_control_node.destroy_node()
    GPIO.cleanup()
    rclpy.shutdown()

if __name__ == '__main__':
    main()