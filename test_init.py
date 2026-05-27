import sys
sys.path.insert(0, "/workspace/GlobalHumanoidRobotChallenge2026_Baseline/auto_collect_unzipped")
from lerobot.common.robot_devices.robots.utils import make_robot_from_config
from lerobot.common.robot_devices.control_configs import ProgrammaticControlConfig
print("imports OK")
cfg = ProgrammaticControlConfig(task="Packing_Box", num_episodes=1)
print("config OK")
robot = make_robot_from_config(cfg)
print("robot created OK")
