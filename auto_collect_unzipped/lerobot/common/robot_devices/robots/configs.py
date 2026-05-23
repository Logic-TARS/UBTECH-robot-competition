# Copyright 2024 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import abc
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import yaml

import draccus

from lerobot.common.robot_devices.cameras.configs import (
    CameraConfig,
    IntelRealSenseCameraConfig,
    OpenCVCameraConfig,
)
from lerobot.common.robot_devices.motors.configs import (
    DynamixelMotorsBusConfig,
    FeetechMotorsBusConfig,
    MotorsBusConfig,
)


@dataclass
class RobotConfig(draccus.ChoiceRegistry, abc.ABC):
    @property
    def type(self) -> str:
        return self.get_choice_name(self.__class__)


# TODO(rcadene, aliberts): remove ManipulatorRobotConfig abstraction
@dataclass
class ManipulatorRobotConfig(RobotConfig):
    leader_arms: dict[str, MotorsBusConfig] = field(default_factory=lambda: {})
    follower_arms: dict[str, MotorsBusConfig] = field(default_factory=lambda: {})
    cameras: dict[str, CameraConfig] = field(default_factory=lambda: {})

    # Optionally limit the magnitude of the relative positional target vector for safety purposes.
    # Set this to a positive scalar to have the same value for all motors, or a list that is the same length
    # as the number of motors in your follower arms (assumes all follower arms have the same number of
    # motors).
    max_relative_target: list[float] | float | None = None

    # Optionally set the leader arm in torque mode with the gripper motor set to this angle. This makes it
    # possible to squeeze the gripper and have it spring back to an open position on its own. If None, the
    # gripper is not put in torque mode.
    gripper_open_degree: float | None = None

    mock: bool = False

    def __post_init__(self):
        if self.mock:
            for arm in self.leader_arms.values():
                if not arm.mock:
                    arm.mock = True
            for arm in self.follower_arms.values():
                if not arm.mock:
                    arm.mock = True
            for cam in self.cameras.values():
                if not cam.mock:
                    cam.mock = True

        if self.max_relative_target is not None and isinstance(self.max_relative_target, Sequence):
            for name in self.follower_arms:
                if len(self.follower_arms[name].motors) != len(self.max_relative_target):
                    raise ValueError(
                        f"len(max_relative_target)={len(self.max_relative_target)} but the follower arm with name {name} has "
                        f"{len(self.follower_arms[name].motors)} motors. Please make sure that the "
                        f"`max_relative_target` list has as many parameters as there are motors per arm. "
                        "Note: This feature does not yet work with robots where different follower arms have "
                        "different numbers of motors."
                    )


@RobotConfig.register_subclass("aloha")
@dataclass
class AlohaRobotConfig(ManipulatorRobotConfig):
    # Specific to Aloha, LeRobot comes with default calibration files. Assuming the motors have been
    # properly assembled, no manual calibration step is expected. If you need to run manual calibration,
    # simply update this path to ".cache/calibration/aloha"
    calibration_dir: str = ".cache/calibration/aloha_default"

    # /!\ FOR SAFETY, READ THIS /!\
    # `max_relative_target` limits the magnitude of the relative positional target vector for safety purposes.
    # Set this to a positive scalar to have the same value for all motors, or a list that is the same length as
    # the number of motors in your follower arms.
    # For Aloha, for every goal position request, motor rotations are capped at 5 degrees by default.
    # When you feel more confident with teleoperation or running the policy, you can extend
    # this safety limit and even removing it by setting it to `null`.
    # Also, everything is expected to work safely out-of-the-box, but we highly advise to
    # first try to teleoperate the grippers only (by commenting out the rest of the motors in this yaml),
    # then to gradually add more motors (by uncommenting), until you can teleoperate both arms fully
    max_relative_target: int | None = 5

    leader_arms: dict[str, MotorsBusConfig] = field(
        default_factory=lambda: {
            "left": DynamixelMotorsBusConfig(
                # window_x
                port="/dev/ttyDXL_leader_left",
                motors={
                    # name: (index, model)
                    "waist": [1, "xm430-w350"],
                    "shoulder": [2, "xm430-w350"],
                    "shoulder_shadow": [3, "xm430-w350"],
                    "elbow": [4, "xm430-w350"],
                    "elbow_shadow": [5, "xm430-w350"],
                    "forearm_roll": [6, "xm430-w350"],
                    "wrist_angle": [7, "xm430-w350"],
                    "wrist_rotate": [8, "xl430-w250"],
                    "gripper": [9, "xc430-w150"],
                },
            ),
            "right": DynamixelMotorsBusConfig(
                # window_x
                port="/dev/ttyDXL_leader_right",
                motors={
                    # name: (index, model)
                    "waist": [1, "xm430-w350"],
                    "shoulder": [2, "xm430-w350"],
                    "shoulder_shadow": [3, "xm430-w350"],
                    "elbow": [4, "xm430-w350"],
                    "elbow_shadow": [5, "xm430-w350"],
                    "forearm_roll": [6, "xm430-w350"],
                    "wrist_angle": [7, "xm430-w350"],
                    "wrist_rotate": [8, "xl430-w250"],
                    "gripper": [9, "xc430-w150"],
                },
            ),
        }
    )

    follower_arms: dict[str, MotorsBusConfig] = field(
        default_factory=lambda: {
            "left": DynamixelMotorsBusConfig(
                port="/dev/ttyDXL_follower_left",
                motors={
                    # name: (index, model)
                    "waist": [1, "xm540-w270"],
                    "shoulder": [2, "xm540-w270"],
                    "shoulder_shadow": [3, "xm540-w270"],
                    "elbow": [4, "xm540-w270"],
                    "elbow_shadow": [5, "xm540-w270"],
                    "forearm_roll": [6, "xm540-w270"],
                    "wrist_angle": [7, "xm540-w270"],
                    "wrist_rotate": [8, "xm430-w350"],
                    "gripper": [9, "xm430-w350"],
                },
            ),
            "right": DynamixelMotorsBusConfig(
                port="/dev/ttyDXL_follower_right",
                motors={
                    # name: (index, model)
                    "waist": [1, "xm540-w270"],
                    "shoulder": [2, "xm540-w270"],
                    "shoulder_shadow": [3, "xm540-w270"],
                    "elbow": [4, "xm540-w270"],
                    "elbow_shadow": [5, "xm540-w270"],
                    "forearm_roll": [6, "xm540-w270"],
                    "wrist_angle": [7, "xm540-w270"],
                    "wrist_rotate": [8, "xm430-w350"],
                    "gripper": [9, "xm430-w350"],
                },
            ),
        }
    )

    # Troubleshooting: If one of your IntelRealSense cameras freeze during
    # data recording due to bandwidth limit, you might need to plug the camera
    # on another USB hub or PCIe card.
    cameras: dict[str, CameraConfig] = field(
        default_factory=lambda: {
            "cam_high": IntelRealSenseCameraConfig(
                serial_number=128422271347,
                fps=30,
                width=640,
                height=480,
            ),
            "cam_low": IntelRealSenseCameraConfig(
                serial_number=130322270656,
                fps=30,
                width=640,
                height=480,
            ),
            "cam_left_wrist": IntelRealSenseCameraConfig(
                serial_number=218622272670,
                fps=30,
                width=640,
                height=480,
            ),
            "cam_right_wrist": IntelRealSenseCameraConfig(
                serial_number=130322272300,
                fps=30,
                width=640,
                height=480,
            ),
        }
    )

    mock: bool = False


@RobotConfig.register_subclass("koch")
@dataclass
class KochRobotConfig(ManipulatorRobotConfig):
    calibration_dir: str = ".cache/calibration/koch"
    # `max_relative_target` limits the magnitude of the relative positional target vector for safety purposes.
    # Set this to a positive scalar to have the same value for all motors, or a list that is the same length as
    # the number of motors in your follower arms.
    max_relative_target: int | None = None

    leader_arms: dict[str, MotorsBusConfig] = field(
        default_factory=lambda: {
            "main": DynamixelMotorsBusConfig(
                port="/dev/tty.usbmodem585A0085511",
                motors={
                    # name: (index, model)
                    "shoulder_pan": [1, "xl330-m077"],
                    "shoulder_lift": [2, "xl330-m077"],
                    "elbow_flex": [3, "xl330-m077"],
                    "wrist_flex": [4, "xl330-m077"],
                    "wrist_roll": [5, "xl330-m077"],
                    "gripper": [6, "xl330-m077"],
                },
            ),
        }
    )

    follower_arms: dict[str, MotorsBusConfig] = field(
        default_factory=lambda: {
            "main": DynamixelMotorsBusConfig(
                port="/dev/tty.usbmodem585A0076891",
                motors={
                    # name: (index, model)
                    "shoulder_pan": [1, "xl430-w250"],
                    "shoulder_lift": [2, "xl430-w250"],
                    "elbow_flex": [3, "xl330-m288"],
                    "wrist_flex": [4, "xl330-m288"],
                    "wrist_roll": [5, "xl330-m288"],
                    "gripper": [6, "xl330-m288"],
                },
            ),
        }
    )

    cameras: dict[str, CameraConfig] = field(
        default_factory=lambda: {
            "laptop": OpenCVCameraConfig(
                camera_index=0,
                fps=30,
                width=640,
                height=480,
            ),
            "phone": OpenCVCameraConfig(
                camera_index=1,
                fps=30,
                width=640,
                height=480,
            ),
        }
    )

    # ~ Koch specific settings ~
    # Sets the leader arm in torque mode with the gripper motor set to this angle. This makes it possible
    # to squeeze the gripper and have it spring back to an open position on its own.
    gripper_open_degree: float = 35.156

    mock: bool = False


@RobotConfig.register_subclass("koch_bimanual")
@dataclass
class KochBimanualRobotConfig(ManipulatorRobotConfig):
    calibration_dir: str = ".cache/calibration/koch_bimanual"
    # `max_relative_target` limits the magnitude of the relative positional target vector for safety purposes.
    # Set this to a positive scalar to have the same value for all motors, or a list that is the same length as
    # the number of motors in your follower arms.
    max_relative_target: int | None = None

    leader_arms: dict[str, MotorsBusConfig] = field(
        default_factory=lambda: {
            "left": DynamixelMotorsBusConfig(
                port="/dev/tty.usbmodem585A0085511",
                motors={
                    # name: (index, model)
                    "shoulder_pan": [1, "xl330-m077"],
                    "shoulder_lift": [2, "xl330-m077"],
                    "elbow_flex": [3, "xl330-m077"],
                    "wrist_flex": [4, "xl330-m077"],
                    "wrist_roll": [5, "xl330-m077"],
                    "gripper": [6, "xl330-m077"],
                },
            ),
            "right": DynamixelMotorsBusConfig(
                port="/dev/tty.usbmodem575E0031751",
                motors={
                    # name: (index, model)
                    "shoulder_pan": [1, "xl330-m077"],
                    "shoulder_lift": [2, "xl330-m077"],
                    "elbow_flex": [3, "xl330-m077"],
                    "wrist_flex": [4, "xl330-m077"],
                    "wrist_roll": [5, "xl330-m077"],
                    "gripper": [6, "xl330-m077"],
                },
            ),
        }
    )

    follower_arms: dict[str, MotorsBusConfig] = field(
        default_factory=lambda: {
            "left": DynamixelMotorsBusConfig(
                port="/dev/tty.usbmodem585A0076891",
                motors={
                    # name: (index, model)
                    "shoulder_pan": [1, "xl430-w250"],
                    "shoulder_lift": [2, "xl430-w250"],
                    "elbow_flex": [3, "xl330-m288"],
                    "wrist_flex": [4, "xl330-m288"],
                    "wrist_roll": [5, "xl330-m288"],
                    "gripper": [6, "xl330-m288"],
                },
            ),
            "right": DynamixelMotorsBusConfig(
                port="/dev/tty.usbmodem575E0032081",
                motors={
                    # name: (index, model)
                    "shoulder_pan": [1, "xl430-w250"],
                    "shoulder_lift": [2, "xl430-w250"],
                    "elbow_flex": [3, "xl330-m288"],
                    "wrist_flex": [4, "xl330-m288"],
                    "wrist_roll": [5, "xl330-m288"],
                    "gripper": [6, "xl330-m288"],
                },
            ),
        }
    )

    cameras: dict[str, CameraConfig] = field(
        default_factory=lambda: {
            "laptop": OpenCVCameraConfig(
                camera_index=0,
                fps=30,
                width=640,
                height=480,
            ),
            "phone": OpenCVCameraConfig(
                camera_index=1,
                fps=30,
                width=640,
                height=480,
            ),
        }
    )

    # ~ Koch specific settings ~
    # Sets the leader arm in torque mode with the gripper motor set to this angle. This makes it possible
    # to squeeze the gripper and have it spring back to an open position on its own.
    gripper_open_degree: float = 35.156

    mock: bool = False


@RobotConfig.register_subclass("moss")
@dataclass
class MossRobotConfig(ManipulatorRobotConfig):
    calibration_dir: str = ".cache/calibration/moss"
    # `max_relative_target` limits the magnitude of the relative positional target vector for safety purposes.
    # Set this to a positive scalar to have the same value for all motors, or a list that is the same length as
    # the number of motors in your follower arms.
    max_relative_target: int | None = None

    leader_arms: dict[str, MotorsBusConfig] = field(
        default_factory=lambda: {
            "main": FeetechMotorsBusConfig(
                port="/dev/tty.usbmodem58760431091",
                motors={
                    # name: (index, model)
                    "shoulder_pan": [1, "sts3215"],
                    "shoulder_lift": [2, "sts3215"],
                    "elbow_flex": [3, "sts3215"],
                    "wrist_flex": [4, "sts3215"],
                    "wrist_roll": [5, "sts3215"],
                    "gripper": [6, "sts3215"],
                },
            ),
        }
    )

    follower_arms: dict[str, MotorsBusConfig] = field(
        default_factory=lambda: {
            "main": FeetechMotorsBusConfig(
                port="/dev/tty.usbmodem585A0076891",
                motors={
                    # name: (index, model)
                    "shoulder_pan": [1, "sts3215"],
                    "shoulder_lift": [2, "sts3215"],
                    "elbow_flex": [3, "sts3215"],
                    "wrist_flex": [4, "sts3215"],
                    "wrist_roll": [5, "sts3215"],
                    "gripper": [6, "sts3215"],
                },
            ),
        }
    )

    cameras: dict[str, CameraConfig] = field(
        default_factory=lambda: {
            "laptop": OpenCVCameraConfig(
                camera_index=0,
                fps=30,
                width=640,
                height=480,
            ),
            "phone": OpenCVCameraConfig(
                camera_index=1,
                fps=30,
                width=640,
                height=480,
            ),
        }
    )

    mock: bool = False


@RobotConfig.register_subclass("so100")
@dataclass
class So100RobotConfig(ManipulatorRobotConfig):
    calibration_dir: str = ".cache/calibration/so100"
    # `max_relative_target` limits the magnitude of the relative positional target vector for safety purposes.
    # Set this to a positive scalar to have the same value for all motors, or a list that is the same length as
    # the number of motors in your follower arms.
    max_relative_target: int | None = None

    leader_arms: dict[str, MotorsBusConfig] = field(
        default_factory=lambda: {
            "main": FeetechMotorsBusConfig(
                port="/dev/tty.usbmodem58760431091",
                motors={
                    # name: (index, model)
                    "shoulder_pan": [1, "sts3215"],
                    "shoulder_lift": [2, "sts3215"],
                    "elbow_flex": [3, "sts3215"],
                    "wrist_flex": [4, "sts3215"],
                    "wrist_roll": [5, "sts3215"],
                    "gripper": [6, "sts3215"],
                },
            ),
        }
    )

    follower_arms: dict[str, MotorsBusConfig] = field(
        default_factory=lambda: {
            "main": FeetechMotorsBusConfig(
                port="/dev/tty.usbmodem585A0076891",
                motors={
                    # name: (index, model)
                    "shoulder_pan": [1, "sts3215"],
                    "shoulder_lift": [2, "sts3215"],
                    "elbow_flex": [3, "sts3215"],
                    "wrist_flex": [4, "sts3215"],
                    "wrist_roll": [5, "sts3215"],
                    "gripper": [6, "sts3215"],
                },
            ),
        }
    )

    cameras: dict[str, CameraConfig] = field(
        default_factory=lambda: {
            "laptop": OpenCVCameraConfig(
                camera_index=0,
                fps=30,
                width=640,
                height=480,
            ),
            "phone": OpenCVCameraConfig(
                camera_index=1,
                fps=30,
                width=640,
                height=480,
            ),
        }
    )

    mock: bool = False








@RobotConfig.register_subclass("walker_s2_sim")
@dataclass
class WalkerS2SimRobotConfig(RobotConfig):
    """
    Configuration for Walker S2 dual-arm robot in Isaac Sim simulation environment.
    
    This robot is controlled via RobotArticulation API in Isaac Sim, not through
    real motor buses. It features 14 DOF (7 per arm) and 4 cameras.
    """
    
    # Task configuration mapping
    TASK_CONFIGS = {
        "Part_Sorting": {
            "config_path": "config/Part_Sorting.yaml",
            "desc": "Part_Sorting",
        },
        "Conveyor_Sorting": {
            "config_path": "config/Conveyor_Sorting.yaml",
            "desc": "Conveyor_Sorting",
        },
        "Foam_Inlaying": {
            "config_path": "config/Foam_Inlaying.yaml",
            "desc": "Foam_Inlaying",
        },
        "Packing_Box": {
            "config_path": "config/Packing_Box.yaml",
            "desc": "Packing_Box",
        },
    }

    # Isaac Sim specific settings
    task_name: str = "Foam_Inlaying"  # Default task name
    task_cfg: dict = field(default_factory=dict)
    root_path: str = "Ubtech_sim"
    task_cfg_path: str = str(Path("Ubtech_sim") / "config" / "Packing_Box.yaml")

    def load_from_yaml(self, task: Optional[str] = None) -> dict:
        """Load task yaml config and update task_cfg/task_cfg_path.
        
        Also syncs top-level config keys (like fsm_mode) from YAML to config attributes.
        """
        effective_task = task if task in self.TASK_CONFIGS else "Foam_Inlaying"
        task_cfg = self.TASK_CONFIGS[effective_task]

        full_config_path = Path(self.root_path) / task_cfg["config_path"]
        if not full_config_path.is_absolute():
            project_root = Path(__file__).parent.parent.parent.parent.parent
            full_config_path = project_root / full_config_path

        config_path = Path(full_config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file does not exist: {config_path}")

        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)

        yaml_dir = config_path.parent
        if "root_path" in cfg:
            cfg["root_path"] = str((yaml_dir / cfg["root_path"]).resolve())

        self.task_cfg_path = str(config_path)
        self.task_cfg = cfg
        self.task_name = effective_task
        
        # Sync top-level config keys from YAML to config attributes
        # This allows YAML to override default config values like fsm_mode
        config_keys_to_sync = ['fsm_mode', 'fsm_pos_tol', 'fsm_approach_height', 
                               'fsm_grasp_frames', 'fsm_release_frames', 'fsm_rot_weight',
                               'fsm_max_ee_step', 'fsm_descend_step', 'fsm_grasp_height',
                               'fsm_drop_height', 'fsm_smooth_alpha', 'fsm_ik_null_weight',
                               'fsm_forearm_tilt_deg', 'fsm_preferred_arm', 'fsm_state_timeout_frames',
                               'timelimit']
        for key in config_keys_to_sync:
            if key in cfg:
                if hasattr(self, key):
                    setattr(self, key, cfg[key])
                    logging.info(f"[Config] Synced {key}={cfg[key]} from YAML")
                else:
                    logging.warning(f"[Config] YAML has key {key} but config doesn't have this attribute")
        
        return cfg
    
    # Robot configuration
    prim_path: str = "/Root/Ref_Xform/Ref" # SceneBuilder 加载机器人时会保存这个 prim 路径，供后续控制使用 TODO
    robot_name: str = "walkerS2"
    urdf_path: str = str(Path("assets") / "resources" / "s2.urdf")
    # Isaac Sim configuration
    headless: bool = False
    sim_width: int = 1280
    sim_height: int = 720
    physics_dt: float = 1.0 / 200.0
    rendering_dt: float = 1.0 / 20.0
    

    # Control settings
    # Speed levels for keyboard control (rad/step)
    speed_levels: list[float] = field(default_factory=lambda: [0.010, 0.035, 0.15])
    default_speed_index: int = 1  # Default speed level index for control
    tracking_interp_steps: int = 100
    
    # Joint limits for safety (in radians)
    joint_limit_lower: float = -3.2
    joint_limit_upper: float = 3.2
    
    teleop_time_s: Optional[float] = None  # None 表示无限时长

    # ROS2 / Pico4 遥操作（可选，需 rclpy；未安装时自动跳过）
    enable_ros2_teleop: bool = True
    ros2_joint_commands_topic: str = "/isaac/joint_position_commands"

    # VLM teleoperation mode (MiniMax M2.7 or compatible)
    vlm_mode: bool = False
    vlm_api_key: str = ""  # MiniMax API key (or env var MINIMAX_API_KEY)
    vlm_model: str = "MiniMax-M2.7"
    vlm_base_url: str = "https://api.minimaxi.com/anthropic/v1"  # Anthropic-compatible endpoint for vision
    vlm_query_interval_s: float = 1.0  # Seconds between VLM queries
    vlm_image_resize: list[int] = field(default_factory=lambda: [320, 240])  # Downsample for API [width, height]
    vlm_hold_between_queries: bool = True  # Continue last command while VLM thinks
    vlm_extra_context: str = ""  # Additional task context appended to prompt
    vlm_speed_index: int = 0  # Speed level for VLM mode (0=slowest 0.010, 1=medium 0.035, 2=fast 0.15)
    vlm_max_duration_frames: int = 15  # Cap VLM duration_frames to this value (max 0.5s at 30fps)

    # FSM automation mode (pick-and-place state machine for autonomous data collection)
    fsm_mode: bool = False
    fsm_pos_tol: float = 0.05  # Position convergence tolerance (m) — relaxed to handle IK approximation errors
    fsm_approach_height: float = 0.28  # Height above part/box for approach/retreat (m)
    fsm_grasp_frames: int = 100  # Total frames in GRASP state (settle + close) before lifting
    fsm_grasp_settle_frames: int = 80  # Frames to wait with gripper OPEN before closing (let EE fully descend)
    fsm_release_frames: int = 30  # Frames to hold at release position before retreating (gripper needs time to open)
    fsm_state_timeout_frames: int = 1500  # Max frames per convergence state before force-transition (~15s @ 100Hz)
    fsm_rot_weight: float = 0.1  # IK rotation weight (lower = more position-focused)
    fsm_max_ee_step: float = 0.002  # Max EE position movement per physics step (m), controls FSM speed
    fsm_descend_step: float = 0.005  # Slower descent step (m) for safe approach to part/box
    fsm_grasp_height: float = 0.01  # Height above part position for grasp (m)
    fsm_drop_height: float = 0.10  # Height above box position for release (m)
    fsm_smooth_alpha: float = 0.10  # EMA alpha for IK joint smoothing in FSM mode (lower=slower/smoother)
    fsm_ik_null_weight: float = 0.30  # Null-space bias toward neutral posture (0=off, 0.25-0.35=human-like)
    fsm_forearm_tilt_deg: float = 30.0  # Tilt EE from vertical toward robot body (deg), raises forearm to avoid table collision
    fsm_preferred_arm: str = "right"  # Arm to use for pick-and-place: "right", "left", or "auto" (X-based selection)

    # Local OpenCV multi-camera visualization
    head_viz_enabled: bool = True
    head_viz_window_name: str = "walker_s2_cameras"
    head_viz_scale: float = 1.0
    head_viz_every_n: int = 10
    head_viz_window_x: int = 40
    head_viz_window_y: int = 40
    head_viz_show_labels: bool = True

    camera_width: int = 640
    camera_height: int = 480
    camera_fps: int = 30

    # dummy camera 添加两个额外视角方便观察没有使用, 位置和朝向可以根据实际场景调整
    dummy_cameras_cfg: dict = field(default_factory=lambda: {
        'dummy_camera_top':{
            'translation': [-2.54145,-0.06363,2.4821],
            'orientation': [ 0.942732,-0.008441,0.333388,0.006151],
            'prim_path':"//Root/Ref_Xform/Ref/head_pitch_link/head_stereo_left/dummy_camera_top"
        },
        'dummy_camera_side':{
            # Part_Sorting: [2.06555,-0.02631,0.95453]
            # Conveyor_Sorting: [4.15,0.0,1.1]
            'translation': [4.15,0.0,1.1],
            'orientation': [ 0.942732,-0.008441,0.333388,0.006151],
            'prim_path': "/Replicator/Ref_Xform/Ref/dummy_camera_side"
        }
    })


    # walker S2 has 4 cameras: head_left, head_right, wrist_left, wrist_right. In simulation, we can use OpenCV cameras
    cameras: dict[str, CameraConfig] = field(
        default_factory=lambda: {
            "head_left": OpenCVCameraConfig(
                camera_index=0,  # Will be overridden by simulation
                fps=30,
                width=640,
                height=480,
            ),
            "head_right": OpenCVCameraConfig(
                camera_index=1,
                fps=30,
                width=640,
                height=480,
            ),
            "wrist_left": OpenCVCameraConfig(
                camera_index=2,
                fps=30,
                width=640,
                height=480,
            ),
            "wrist_right": OpenCVCameraConfig(
                camera_index=3,
                fps=30,
                width=640,
                height=480,
            ),
        }
    )
    
    # Arm joint configuration (14 joints total: 7 left + 7 right)
    # These are the expected joint names in Isaac Sim
    left_arm_joint_names: list[str] = field(
        default_factory=lambda: [
"L_shoulder_pitch_joint", "L_shoulder_roll_joint", "L_shoulder_yaw_joint",
            "L_elbow_roll_joint", "L_elbow_yaw_joint", "L_wrist_pitch_joint", "L_wrist_roll_joint",
        ]
    )
    
    right_arm_joint_names: list[str] = field(
        default_factory=lambda: [
  "R_shoulder_pitch_joint", "R_shoulder_roll_joint", "R_shoulder_yaw_joint",
            "R_elbow_roll_joint", "R_elbow_yaw_joint", "R_wrist_pitch_joint", "R_wrist_roll_joint",

        
        ]
    )
    
    # Keyboard control mapping placeholder
    teleop_keymap: dict = field(default_factory=dict)
    mock: bool = False
    
    def __post_init__(self):
        # Validate joint configuration
        if len(self.left_arm_joint_names) != 7 or len(self.right_arm_joint_names) != 7:
            raise ValueError(
                f"Walker S2 robot requires exactly 7 joints per arm. "
                f"Got {len(self.left_arm_joint_names)} left and "
                f"{len(self.right_arm_joint_names)} right joints."
            )
        
        # Combine all arm joint names for reference
        self.all_arm_joint_names = self.left_arm_joint_names + self.right_arm_joint_names
        
        # Set mock to True for simulation environment (no real hardware)
        if not self.mock:
            # In simulation, we don't use real motors, so this is effectively mock mode
            # for the underlying device layers, but the robot itself is "real" in sim
            pass
        
        # Update camera names to match expected format in mobile_manipulator.py
        # Ensure camera configs have correct names
        for cam_name, cam_config in self.cameras.items():
            if hasattr(cam_config, 'name'):
                cam_config.name = cam_name








@RobotConfig.register_subclass("stretch")
@dataclass
class StretchRobotConfig(RobotConfig):
    # `max_relative_target` limits the magnitude of the relative positional target vector for safety purposes.
    # Set this to a positive scalar to have the same value for all motors, or a list that is the same length as
    # the number of motors in your follower arms.
    max_relative_target: int | None = None

    cameras: dict[str, CameraConfig] = field(
        default_factory=lambda: {
            "navigation": OpenCVCameraConfig(
                camera_index="/dev/hello-nav-head-camera",
                fps=10,
                width=1280,
                height=720,
                rotation=-90,
            ),
            "head": IntelRealSenseCameraConfig(
                name="Intel RealSense D435I",
                fps=30,
                width=640,
                height=480,
                rotation=90,
            ),
            "wrist": IntelRealSenseCameraConfig(
                name="Intel RealSense D405",
                fps=30,
                width=640,
                height=480,
            ),
        }
    )

    mock: bool = False


@RobotConfig.register_subclass("lekiwi")
@dataclass
class LeKiwiRobotConfig(RobotConfig):
    # `max_relative_target` limits the magnitude of the relative positional target vector for safety purposes.
    # Set this to a positive scalar to have the same value for all motors, or a list that is the same length as
    # the number of motors in your follower arms.
    max_relative_target: int | None = None

    # Network Configuration
    ip: str = "192.168.0.193"
    port: int = 5555
    video_port: int = 5556

    cameras: dict[str, CameraConfig] = field(
        default_factory=lambda: {
            "front": OpenCVCameraConfig(
                camera_index="/dev/video0", fps=30, width=640, height=480, rotation=90
            ),
            "wrist": OpenCVCameraConfig(
                camera_index="/dev/video2", fps=30, width=640, height=480, rotation=180
            ),
        }
    )

    calibration_dir: str = ".cache/calibration/lekiwi"

    leader_arms: dict[str, MotorsBusConfig] = field(
        default_factory=lambda: {
            "main": FeetechMotorsBusConfig(
                port="/dev/tty.usbmodem585A0077581",
                motors={
                    # name: (index, model)
                    "shoulder_pan": [1, "sts3215"],
                    "shoulder_lift": [2, "sts3215"],
                    "elbow_flex": [3, "sts3215"],
                    "wrist_flex": [4, "sts3215"],
                    "wrist_roll": [5, "sts3215"],
                    "gripper": [6, "sts3215"],
                },
            ),
        }
    )

    follower_arms: dict[str, MotorsBusConfig] = field(
        default_factory=lambda: {
            "main": FeetechMotorsBusConfig(
                port="/dev/ttyACM0",
                motors={
                    # name: (index, model)
                    "shoulder_pan": [1, "sts3215"],
                    "shoulder_lift": [2, "sts3215"],
                    "elbow_flex": [3, "sts3215"],
                    "wrist_flex": [4, "sts3215"],
                    "wrist_roll": [5, "sts3215"],
                    "gripper": [6, "sts3215"],
                    "left_wheel": (7, "sts3215"),
                    "back_wheel": (8, "sts3215"),
                    "right_wheel": (9, "sts3215"),
                },
            ),
        }
    )

    teleop_keys: dict[str, str] = field(
        default_factory=lambda: {
            # Movement
            "forward": "w",
            "backward": "s",
            "left": "a",
            "right": "d",
            "rotate_left": "z",
            "rotate_right": "x",
            # Speed control
            "speed_up": "r",
            "speed_down": "f",
            # quit teleop
            "quit": "q",
        }
    )

    mock: bool = False