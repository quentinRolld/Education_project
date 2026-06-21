# user text --> llm --> llm text --> llm speech

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import os
import hailo
import numpy as np

# 1. Download the Llama 7B model
model_name = "meta-llama/Llama-7b-hf"
model = AutoModelForCausalLM.from_pretrained(model_name)
tokenizer = AutoTokenizer.from_pretrained(model_name)

# 2. Export the model to ONNX
# Prepare dummy input to trace the model
dummy_input = tokenizer("Hello, how are you?", return_tensors="pt").input_ids
# Export the model to ONNX format
onnx_model_path = "llama_7b.onnx"
torch.onnx.export(model, dummy_input, onnx_model_path, input_names=["input_ids"], output_names=["output"])

# 3. Convert the ONNX model to HEF (Hailo Executable File) - So it can be red by hailo
command = "hailo_dataflow_compiler --input_model llama_7b.onnx --output_model llama_7b.hef"
exit_code = os.system(command)
# Check if the command was successful
if exit_code == 0:
    print("Command executed successfully.")
else:
    print(f"Command failed with exit code {exit_code}.")

# 4. Load the HEF file and run inference with HailoRT runtime
# Initialize HailoRT runtime
runtime = hailo.HailoRT()
# Load the HEF file
hef_file = "llama_7b.hef"
model = runtime.load_model(hef_file)
# Prepare input (dummy input similar to the input used in the export)
input_ids = tokenizer("Hello, how are you?", return_tensors="pt").input_ids
input_data = np.array(input_ids.numpy(), dtype=np.int32)
# Run inference
outputs = model.run([input_data])
# Extract the output
output = outputs[0]
# Convert the output to text
output_ids = torch.tensor(output).squeeze(0)
output_text = tokenizer.decode(output_ids, skip_special_tokens=True)
print("Output:", output_text)

