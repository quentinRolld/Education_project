import sys
if sys.prefix == '/usr':
    sys.real_prefix = sys.prefix
    sys.prefix = sys.exec_prefix = '/home/kant/robot_ILiAD/robot_agent_ws/install/robot_vlm'
