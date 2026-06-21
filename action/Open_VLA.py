
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32MultiArray

from transformers import AutoModelForCausalLM, AutoTokenizer

model_name = "meta-llama/Llama-7b-hf"
model = AutoModelForCausalLM.from_pretrained(model_name)
tokenizer = AutoTokenizer.from_pretrained(model_name)

# classe qui prends en entrée une image et une phrase et qui renvoie une action
# * entrée : 
#   - image webcam récupérée sur le topic image
#   - une phrase constituée de la phrase input_utilisateur et de la réponse LLM
# * sortie : 
#   - une action sous la forme : 
#
class Vision_language_to_action(Node):
    def __init__(self):
        super().__init__('vision_language_to_action_node')
        self.subscription = self.create_subscription(
            Float32MultiArray,
            '/image',
            self.image_callback,
            10
        )
        self.subscription = self.create_subscription(
            Float32MultiArray,
            '/user_text_input',
            self.user_text_callback,
            10
        )
        self.subscription = self.create_subscription(
            Float32MultiArray,
            '/llm_text_output',
            self.llm_text_callback,
            10
        )
    
    def raw_data_processing(self):
        # Tokenize the input data
    
    def OpenVLA_model(self):
        # Import OpenVLA model from https://github.com/openvla/openvla
        


def main(args=None):
    rclpy.init(args=args)
    vision_language_to_action_node = Vision_language_to_action()
    rclpy.spin(vision_language_to_action_node)
    vision_language_to_action_node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()