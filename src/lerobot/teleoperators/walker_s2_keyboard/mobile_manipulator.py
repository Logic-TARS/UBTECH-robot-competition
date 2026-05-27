"""
WalkerS2 dual-arm robot control class for Isaac Sim environment

This version can control both arms simultaneously, with unnecessary comments removed

Adapted for actual task4.yaml workflow:
- SceneBuilder loads scene and robot from yaml
- Robot USD: Collected_s2_v1_ecbg/s2_v1.usd
- Scene USD: Collected_Task4/SubUSDs/2_small_warehouse2.usd

Optional ROS2 teleoperation (Pico4 / bridge) - see ros2_teleop_subscriber module.
"""

from __future__ import annotations
import collections
import logging
import time
import threading
import os
from dataclasses import dataclass, field
from typing import Any, Optional
from pathlib import Path
import numpy as np
import torch

# LeRobot base classes and utilities
from lerobot.common.robot_devices.robots.utils import Robot
from lerobot.common.robot_devices.utils import RobotDeviceNotConnectedError
# Import configuration class
from lerobot.common.robot_devices.robots.configs import WalkerS2SimRobotConfig as WalkerS2Config
from lerobot.common.robot_devices.robots.isaac_sim_robot_interface import (
    IsaacSimRobotInterface,
    load_config,
)
from lerobot.common.robot_devices.robots.ros2_teleop_subscriber import (
    ROS2TeleopSubscriber,
    connect_ros2_teleop_if_enabled,
    stop_ros2_teleop,
)
from lerobot.common.robot_devices.robots.head_stereo_visualizer import HeadStereoVisualizer

logger = logging.getLogger(__name__)



@dataclass
class TimingMetric:
    count: int = 0
    total_s: float = 0.0
    min_s: float = field(default_factory=lambda: float("inf"))
    max_s: float = 0.0

    def update(self, duration_s: float) -> None:
        duration_s = max(float(duration_s), 0.0)
        self.count += 1
        self.total_s += duration_s
        self.min_s = min(self.min_s, duration_s)
        self.max_s = max(self.max_s, duration_s)

    def as_dict(self) -> dict[str, float | int]:
        if self.count == 0:
            return {
                "count": 0,
                "avg_s": 0.0,
                "min_s": 0.0,
                "max_s": 0.0,
            }

        return {
            "count": self.count,
            "avg_s": self.total_s / self.count,
            "min_s": self.min_s,
            "max_s": self.max_s,
        }

# Keyboard listener backend (pynput preferred, fallback to evdev for remote environments like RustDesk)
PYNPUT_AVAILABLE = False
EVDEV_AVAILABLE = False
keyboard = None

try:
    from pynput import keyboard
    PYNPUT_AVAILABLE = True
except ImportError:
    pass

try:
    import evdev  # noqa: F811
    EVDEV_AVAILABLE = True
except ImportError:
    pass


class EvdevKeyboardListener:
    """Keyboard listener based on evdev, reads /dev/input devices directly.

    Suitable for remote desktop environments like RustDesk/VNC where pynput cannot capture key events.
    Requires root privileges or current user in the input group.
    """

    # evdev KEY_* code -> character mapping (only keys needed for teleoperation)
    _CODE_TO_CHAR: dict[int, str] = {
        2: "1", 3: "2", 4: "3", 5: "4", 6: "5", 7: "6", 8: "7", 9: "8", 10: "9", 11: "0",
        12: "-", 13: "=",
        16: "q", 17: "w", 18: "e", 19: "r", 20: "t", 21: "y", 22: "u",
        23: "i", 24: "o", 25: "p",
        30: "a", 31: "s", 32: "d", 33: "f", 34: "g", 35: "h",
        36: "j", 37: "k", 38: "l",
        44: "z", 45: "x", 46: "c", 47: "v", 48: "b", 49: "n", 50: "m",
        52: ".",  # KEY_DOT
        78: "+",  # KEY_KPPLUS (numpad +)
    }
    _SPECIAL_KEY_NAMES: dict[int, str] = {
        108: "down",  # KEY_DOWN (down arrow)
    }

    def __init__(self, on_press=None, on_release=None):
        self._on_press = on_press
        self._on_release = on_release
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _find_keyboard_device(self):
        """Automatically find the first input device supporting KEY events"""
        import evdev as _evdev
        for path in _evdev.list_devices():
            dev = _evdev.InputDevice(path)
            caps = dev.capabilities(verbose=False)
            if 1 in caps:  # EV_KEY = 1
                return dev
        return None

    def _run(self):
        import evdev as _evdev
        import select as _select

        dev = self._find_keyboard_device()
        if dev is None:
            print("[EvdevKeyboardListener] No keyboard device found, keyboard control unavailable")
            return

        print(f"[EvdevKeyboardListener] 使用设备: {dev.path} ({dev.name})")
        try:
            while not self._stop_event.is_set():
                r, _, _ = _select.select([dev.fd], [], [], 0.1)
                if not r:
                    continue
                for event in dev.read():
                    if event.type != 1:  # EV_KEY
                        continue
                    char = self._CODE_TO_CHAR.get(event.code)
                    key_name = self._SPECIAL_KEY_NAMES.get(event.code)
                    if char is None and key_name is None:
                        continue
                    key_obj = type("EvdevKey", (), {"char": char, "name": key_name})()
                    if event.value == 1:  # press
                        if self._on_press:
                            self._on_press(key_obj)
                    elif event.value == 0:  # release
                        if self._on_release:
                            self._on_release(key_obj)
        except Exception as e:
            print(f"[EvdevKeyboardListener] 错误: {e}")
        finally:
            try:
                dev.close()
            except Exception:
                pass



# =========================================================================
# Main robot class - MobileManipulator
# =========================================================================

class MobileManipulator(Robot):
    """
    WalkerS2 dual-arm robot control class - supports 14 arm joints and keyboard teleoperation
    
    Core features:
    1. Control 14 arm joints out of 34 total (7 left arm + 7 right arm)
    2. Support dual-arm end-effector pose control (6D: x,y,z,rx,ry,rz)
    3. Support continuous gripper open/close control
    4. Support real-time keyboard teleoperation with switchable control arm
    5. Integrated 4 HD cameras (head stereo + two wrist cameras)
    
    Keyboard control mapping:
    - K: Gripper open direction
    - L: Gripper close direction
    - 2: Toggle gripper control mode(position/effort)
    - 0: Toggle single/dual arm mode
    - 5: Switch current control arm
    - +/-: Adjust speed level
    - Q: Exit program
    
    Attributes:
        robot_type: Robot type identifier
        name: Robot name
        CAMERA_NAMES: Camera list [head_left, head_right, wrist_left, wrist_right]
        config: Configuration object
        current_control_arm: Current control arm ("left" or "right")
        switch_control_arm: Flag for switching control arm
    """
    
    robot_type: str = "walker_s2_sim"
    name: str = "walkerS2"
    
    CAMERA_NAMES = ["head_left", "head_right", "wrist_left", "wrist_right"]
    STATE_DIM = 20  # 14arm joints + 4Finger joint + 2Gripperclose指令 -1 close 1 open
    STATE_NAMES = [
        "L_shoulder_pitch_joint.pos", 
        "L_shoulder_roll_joint.pos", 
        "L_shoulder_yaw_joint.pos",
        "L_elbow_roll_joint.pos", 
        "L_elbow_yaw_joint.pos", 
        "L_wrist_pitch_joint.pos", 
        "L_wrist_roll_joint.pos",
        "R_shoulder_pitch_joint.pos", 
        "R_shoulder_roll_joint.pos", 
        "R_shoulder_yaw_joint.pos",
        "R_elbow_roll_joint.pos", 
        "R_elbow_yaw_joint.pos", 
        "R_wrist_pitch_joint.pos", 
        "R_wrist_roll_joint.pos",
        "L_finger1_joint.pos",
        "L_finger2_joint.pos",
        "R_finger1_joint.pos",
        "R_finger2_joint.pos",
        "left_gripper_control",
        "right_gripper_control"
    ]
        
    ACTION_DIM = 20  # 14arm joints + 4Finger joint + 2Gripperclose指令 -1 close 1 open
    ACTION_NAMES = [
        "L_shoulder_pitch_joint.pos", 
        "L_shoulder_roll_joint.pos", 
        "L_shoulder_yaw_joint.pos",
        "L_elbow_roll_joint.pos", 
        "L_elbow_yaw_joint.pos", 
        "L_wrist_pitch_joint.pos", 
        "L_wrist_roll_joint.pos",
        "R_shoulder_pitch_joint.pos", 
        "R_shoulder_roll_joint.pos", 
        "R_shoulder_yaw_joint.pos",
        "R_elbow_roll_joint.pos", 
        "R_elbow_yaw_joint.pos", 
        "R_wrist_pitch_joint.pos", 
        "R_wrist_roll_joint.pos",
        "L_finger1_joint.pos",
        "L_finger2_joint.pos",
        "R_finger1_joint.pos",
        "R_finger2_joint.pos",
        "left_gripper_control",
        "right_gripper_control"
    ]
    MOTION_AXES = ("x", "y", "z", "rx", "ry", "rz")
    BIMANUAL_MIRROR_SIGNS = np.array([1.0, -1.0, 1.0, -1.0, 1.0, -1.0], dtype=np.float32)

    def __init__(self, config: WalkerS2Config | dict | None = None):
        super().__init__()
        self.logs = {}  # For log_control_info
        self._timing_metrics: dict[str, TimingMetric] = {
            "send_action": TimingMetric(),
            "get_observation": TimingMetric(),
            "dt_s": TimingMetric(),
        }
        
        # Keyboard control state
        self.current_control_arm: str = "left"  # "left" 或 "right"，Currently controlled arm
        self.gripper_control_mode: str = "position"  # "position" 或 "effort"
        self.bimanual_control_enabled: bool = False
        
        # Process configuration
        if isinstance(config, dict):
            # config_path = config.get('config_path', '')
            self.config = WalkerS2Config(**{k: v for k, v in config.items()})
            # self.config.config_path = config_path
        elif config is None:
            self.config = WalkerS2Config()
        else:
            self.config = config
        
        if self.config.task_cfg_path:
            try:

                self.config.task_cfg = load_config(self.config.task_cfg_path)
                # logger.info(f"Load config from yaml: {self.config.task_cfg_path}")
                # logger.info(f"root_path: {self.config.task_cfg.get('root_path', 'N/A')}")
                # logger.info(f"scene_usd: {self.config.task_cfg.get('scene_usd', 'N/A')}")
            except Exception as e:
                # logger.error(f"加载 yaml failed: {e}")
                raise
        
        # Ensure config has camera parameters
        if not hasattr(self.config, 'camera_width'):
            self.config.camera_width = 640
        if not hasattr(self.config, 'camera_height'):
            self.config.camera_height = 480
        
        # Isaac Sim Core组件
        self._kit = None
        self._world = None
        self._scene_builder = None
        self._data_logger = None
        self._robot_interface: Optional[IsaacSimRobotInterface] = None
        
        # State - only store14arm joints
        self._arm_joint_indices: list[int] = []  # 在34关节中的索引
        self._current_positions: torch.Tensor | None = None  # 14值
        
        # Keyboard control
        self._speed_index = self.config.default_speed_index
        self._pressed_keys: dict[str, bool] = {}
        self._keyboard_listener = None

        # Simulation render frequency: default render every physics step
        self._render_every_n = 1
        self._send_action_step_idx = 0

        # 线性插值回到初始位置
        self._go_home = False
        self._num_interpolation_steps = 200

        # ---- Callback control related state ----
        self._callback_lock = threading.Lock()
        self._callbacks_registered = False
        # Inference mode: send_action Write to pending, callback consumes and executes
        # Teleoperation mode: Callback directly reads keyboard state, no pending needed
        self._pending_absolute_action: Optional[np.ndarray] = None
        # Frame counter: callback only in each world.step() 的第一物理子步执行键盘+IK计算
        self._last_keyboard_frame_id: int = -1
        # Camera image cache (updated by render callback)
        self._latest_camera_rgb: dict[str, np.ndarray] = {}
        # Persistent joint target: core state for unified joint position control
        # Snapshot current state at initialization, update only when new commands received, continuously issue when no commands
        self._hold_arm_positions: Optional[np.ndarray] = None   # (14,) Arm joint hold target
        self._hold_finger_positions: Optional[np.ndarray] = None  # (4,) Finger joint hold target
        # 夹持Mode标记：close指令→True（持续施力），open指令→False（停止施力），无指令→D持
        self._left_gripping: bool = False
        self._right_gripping: bool = False

        # ---- Keyboard signal queue ----
        # On each key change, snapshot current _pressed_keys to queue, ensure no signals lost.
        # Callback consumes one per world.step() frame, all physics substeps in that frame track same target.
        # maxlen prevents infinite accumulation in extreme cases (256 entries ≈ few seconds of key buffer).
        self._keyboard_cmd_queue: collections.deque[dict[str, bool]] = collections.deque(maxlen=256)
        # Keyboard snapshot currently being tracked this frame (taken from queue by callback)
        self._current_frame_keys: Optional[dict[str, bool]] = None

        # ROS2 teleoperation
        self._ros2_teleop: Optional[ROS2TeleopSubscriber] = None
        self._head_visualizer = HeadStereoVisualizer(
            enabled=getattr(self.config, "head_viz_enabled", False),
            window_name=getattr(self.config, "head_viz_window_name", "walker_s2_cameras"),
            scale=getattr(self.config, "head_viz_scale", 1.0),
            every_n=getattr(self.config, "head_viz_every_n", 1),
            window_x=getattr(self.config, "head_viz_window_x", 40),
            window_y=getattr(self.config, "head_viz_window_y", 40),
            show_labels=getattr(self.config, "head_viz_show_labels", True),
        )
        
        self._init_keyboard_listener()
        # logger.info(f"MobileManipulator Initialization complete")

    def step(self, render: bool = True):
        if not self.is_connected or self._world is None:
            raise RobotDeviceNotConnectedError("Not connected")
        self._world.step(render=render)
        self._send_action_step_idx += 1

    def get_parts_positions(self):
        """Compatibility helper for legacy programmatic collection scripts."""
        if self._scene_builder is None:
            return []
        get_poses = getattr(self._scene_builder, "get_parts_world_poses", None)
        if get_poses is None:
            return []
        return get_poses()

    def get_box_position(self):
        """Return the first configured box position for legacy scripts."""
        if self._scene_builder is None:
            return None
        get_positions = getattr(self._scene_builder, "get_box_positions", None)
        if get_positions is None:
            return None
        positions = get_positions()
        return positions[0] if positions else None

    def get_current_action(self) -> torch.Tensor:
        """Return the current 20D action tensor for legacy data recorders."""
        return self.send_action(None)

    # ---- Callback register / unregister ----

    def _register_world_callbacks(self) -> None:
        """Register physics and render callbacks with World, enabling control logic to execute automatically at each physics step."""
        if self._world is None or self._callbacks_registered:
            return

        self._world.add_physics_callback("robot_control", self._robot_control_callback)
        self._world.add_physics_callback("score_input_record", self._score_input_record_callback)
        self._world.add_physics_callback("foam_sync", self._foam_sync_callback)
        self._world.add_render_callback("camera_images", self._camera_images_callback)
        self._callbacks_registered = True
        logger.info("Physics/render callbacks registered")

    def _unregister_world_callbacks(self) -> None:
        """Unregister all registered callbacks."""
        if self._world is None or not self._callbacks_registered:
            return

        remove_physics = getattr(self._world, "remove_physics_callback", None)
        remove_render = getattr(self._world, "remove_render_callback", None)
        if callable(remove_physics):
            for cb_name in ["robot_control", "score_input_record", "foam_sync"]:
                try:
                    remove_physics(cb_name)
                except Exception:
                    pass
        if callable(remove_render):
            try:
                remove_render("camera_images")
            except Exception:
                pass
        self._callbacks_registered = False

    # ---- Callback implementation ----

    def _robot_control_callback(self, step_size: float) -> None:
        """Execute automatically at each physics step: unified joint position control.

        Control logic:
        1. Initialize: snapshot current joint state as hold target on first call
        2. Inference mode：Consume _pending_absolute_action to update hold target
        3. Teleoperation mode：Directly read keyboard state, compute delta and solve IK
        4. No input: continuously issue previous frame hold target
        """
        if not self.is_connected:
            return

        if self._send_action_step_idx > 0 and self._send_action_step_idx % 200 == 0 and self._send_action_step_idx != getattr(self, '_last_logged_step', -1):
            self._last_logged_step = self._send_action_step_idx
            logger.info(f"[callback] step={self._send_action_step_idx}, step_size={step_size:.4f}")

        # Initialize hold target (execute only once, snapshot current joint state)
        if self._hold_arm_positions is None:
            states = self._robot_interface.get_joint_states()
            if states:
                self._hold_arm_positions = np.array(states['arm_positions'], dtype=np.float32)
                self._hold_finger_positions = np.array(states['finger_positions'], dtype=np.float32)
                logger.info("[callback] Snapshot initial joint state as hold target")
            else:
                return

        # 读取并消费Inference mode的 pending action
        with self._callback_lock:
            abs_action = self._pending_absolute_action
            if abs_action is not None:
                abs_action = abs_action.copy()
                self._pending_absolute_action = None

        if (abs_action is not None) and (not self._go_home):
            # ====== Inference/playback mode: directly use recorded joint positions ======
            # action 布局: [0:14]=arm, [14:18]=finger_positions, [18]=left_cmd, [19]=right_cmd
            self._hold_arm_positions = abs_action[:14].copy()
            if abs_action.shape[0] >= 18:
                self._hold_finger_positions = abs_action[14:18].copy()
            if abs_action.shape[0] >= 20:
                self._left_gripping = float(abs_action[18]) > 0
                self._right_gripping = float(abs_action[19]) > 0
        elif not self._go_home:
            # ====== Teleoperation mode：合并队列快照+实时状态，不丢信号不延迟 ======
            # world.step() 会触发多物理子步（如10），每都调用此回调。
            # Only read keyboard state and compute IK in first physics substep of each frame (world.step),
            # All subsequent substeps in that frame reuse same target, avoid redundant IK computation.
            current_frame = self._send_action_step_idx
            if current_frame != self._last_keyboard_frame_id:
                self._last_keyboard_frame_id = current_frame

                # Merge all queue snapshots + real-time state: any True wins
                # - Queue snapshot captures short presses between frames (press+release both between two frames)
                # - Real-time state captures sustained holds (no new events queued)
                key_snapshot = {}
                while self._keyboard_cmd_queue:
                    snap = self._keyboard_cmd_queue.popleft()
                    for k, v in snap.items():
                        if v:
                            key_snapshot[k] = True
                for k, v in self._pressed_keys.items():
                    if v:
                        key_snapshot[k] = True

                self._current_frame_keys = key_snapshot

                ros2_data = None
                if self._ros2_teleop is not None:
                    ros2_data = self._ros2_teleop.get_latest(max_age_s=0.5)

                if ros2_data is not None:
                    # ROS2 has providedarm joints目标（bridge 侧已完成 IK）
                    self._hold_arm_positions = np.asarray(
                        ros2_data["arm_positions"], dtype=np.float32
                    ).copy()
                    if ros2_data["finger_positions"] is not None:
                        self._hold_finger_positions = np.asarray(
                            ros2_data["finger_positions"], dtype=np.float32
                        ).copy()
                    _, _, left_gripper, right_gripper, _ = self._compute_keyboard_delta(key_snapshot)
                    if ros2_data["finger_positions"] is None:
                        gripper_step = 0.002
                        g_open = self._robot_interface.gripper_open_width
                        g_close = self._robot_interface.gripper_close_width
                        g_lo, g_hi = min(g_open, g_close), max(g_open, g_close)
                        if abs(left_gripper) > 0.01:
                            self._hold_finger_positions[:2] = np.clip(
                                self._hold_finger_positions[:2] + left_gripper * gripper_step, g_lo, g_hi)
                            self._left_gripping = left_gripper > 0
                        if abs(right_gripper) > 0.01:
                            self._hold_finger_positions[2:4] = np.clip(
                                self._hold_finger_positions[2:4] + right_gripper * gripper_step, g_lo, g_hi)
                            self._right_gripping = right_gripper > 0
                else:
                    left_delta, right_delta, left_gripper, right_gripper, _ = self._compute_keyboard_delta(key_snapshot)
                    has_left_input = np.linalg.norm(left_delta) > 1e-8
                    has_right_input = np.linalg.norm(right_delta) > 1e-8

                    if has_left_input or has_right_input:
                        ee_poses = self._robot_interface.get_ee_poses()
                        if ee_poses is not None:
                            left_target = np.asarray(ee_poses['left'][:6] + left_delta, dtype=np.float32) if has_left_input else None
                            right_target = np.asarray(ee_poses['right'][:6] + right_delta, dtype=np.float32) if has_right_input else None

                            ik_result = self._robot_interface.control_dual_arm_ik(
                                step_size=step_size,
                                left_target_xyzrpy=left_target,
                                right_target_xyzrpy=right_target,
                            )
                            if ik_result and 'smoothed_positions' in ik_result:
                                sp = ik_result['smoothed_positions']
                                offset = 0
                                if 'left_joint_positions' in ik_result:
                                    self._hold_arm_positions[:7] = np.array(sp[offset:offset+7], dtype=np.float32)
                                    offset += 7
                                if 'right_joint_positions' in ik_result:
                                    self._hold_arm_positions[7:14] = np.array(sp[offset:offset+7], dtype=np.float32)

                    gripper_step = 0.002
                    g_open = self._robot_interface.gripper_open_width
                    g_close = self._robot_interface.gripper_close_width
                    g_lo, g_hi = min(g_open, g_close), max(g_open, g_close)
                    if abs(left_gripper) > 0.01:
                        self._hold_finger_positions[:2] = np.clip(
                            self._hold_finger_positions[:2] + left_gripper * gripper_step, g_lo, g_hi)
                        self._left_gripping = left_gripper > 0
                    if abs(right_gripper) > 0.01:
                        self._hold_finger_positions[2:4] = np.clip(
                            self._hold_finger_positions[2:4] + right_gripper * gripper_step, g_lo, g_hi)
                        self._right_gripping = right_gripper > 0

        else:
            print('[_robot_control_callback] Returning to initial position with interpolation...')
            arm_finger_indices = self._robot_interface.arm_joint_indices + self._robot_interface.finger_joint_indices
            if not self._robot_interface.joint_interpolator.interp_active:
                print('[_robot_control_callback] Starting interpolation to initial position...')
                self._robot_interface.joint_interpolator.set_target(
                    start_q=torch.tensor(self._robot_interface.get_joint_states()['all_positions'])[arm_finger_indices],
                    target_q=torch.tensor(self._robot_interface.initial_joint_positions)[arm_finger_indices],
                    num_steps=self._num_interpolation_steps
                )
            arm_finger_positions = self._robot_interface.joint_interpolator.step()  # 执行一步插值
            if isinstance(arm_finger_positions, torch.Tensor):
                arm_finger_positions = arm_finger_positions.detach().cpu().numpy()
            else:
                arm_finger_positions = np.asarray(arm_finger_positions, dtype=np.float32)
            self._hold_arm_positions = arm_finger_positions[:14]
            self._hold_finger_positions = arm_finger_positions[14:18]
            self._left_gripping = False
            self._right_gripping = False
            if self._robot_interface.joint_interpolator.is_finished():
                self._go_home = False  # 插值回到初始位置后，重置标记回到正常控制流程
                all_positions = self._robot_interface.get_joint_states()['all_positions']
                self._robot_interface.reset_ik(all_positions)  # 同步重置IK状态，防止突然跳动
                print('[_robot_control_callback] Interpolation to initial position completed.')
        # 统一下发保持目标（joint positions控制）
        self._robot_interface.set_arm_joint_positions(
            target_arm_positions=self._hold_arm_positions.tolist(),
            task_num=self.config.task_cfg.get("task_number", 1)
        )
        self._robot_interface.set_finger_positions(
            target_fingers=self._hold_finger_positions.tolist(),
            task_num=self.config.task_cfg.get("task_number", 1)
        )

        
        # Gripper控制：Force control during gripping, position control when not gripping (consistent with teleoperation)
        close_tau = self._robot_interface.gripper_close_tau   # 100.0
        efforts = [0.0, 0.0, 0.0, 0.0]
        finger_pos = self._hold_finger_positions.copy()

        if self._left_gripping:
            # Left hand gripping: force control, no position target issued
            efforts[0] = close_tau
            efforts[1] = close_tau
            finger_pos[0] = float('nan')
            finger_pos[1] = float('nan')
        if self._right_gripping:
            # Right hand gripping: force control, no position target issued
            efforts[2] = close_tau
            efforts[3] = close_tau
            finger_pos[2] = float('nan')
            finger_pos[3] = float('nan')

        self._robot_interface.apply_finger_efforts(efforts)

    def _score_input_record_callback(self, step_size: float) -> None:
        """Record score/target object transform at each physics step (if SceneBuilder provides interface)."""
        if self._scene_builder is None:
            return
        get_transforms = getattr(self._scene_builder, "get_target_object_transforms", None)
        if callable(get_transforms):
            get_transforms(step_size)

    def _foam_sync_callback(self, _step_size: float) -> None:
        """task4 specific: sync foam to box at each step."""
        if self._scene_builder is None:
            return
        sync_foam = getattr(self._scene_builder, "sync_foam_to_box", None)
        if callable(sync_foam):
            sync_foam()

    def _camera_images_callback(self, _step: float) -> None:
        """渲染回调：在每次渲染后抓取camera images并缓存。"""
        if not self.is_connected:
            return

        camera_data: dict[str, np.ndarray] = {}
        for cam_name in self.CAMERA_NAMES:
            try:
                rgb = self._robot_interface.get_camera_rgb(cam_name)
                if rgb is not None:
                    camera_data[cam_name] = rgb
            except Exception:
                continue

        if camera_data:
            with self._callback_lock:
                self._latest_camera_rgb = {name: frame.copy() for name, frame in camera_data.items()}
            self._head_visualizer.update_cameras(camera_data)

    @property
    def is_connected(self) -> bool:
        return self._robot_interface is not None

    @property
    def camera_features(self) -> dict[str, Any]:
        features = {}
        for cam_name in self.CAMERA_NAMES:
            features[f"observation.images.{cam_name}"] = {
                "shape": (3, self.config.camera_height, self.config.camera_width),
                "names": ["channels", "height", "width"],
                "dtype": "video",
            }
        return features

    @property
    def env_state_dim(self) -> int:
        """Environment object poses = num_objects * 7 (x,y,z,qx,qy,qz,qw per object)"""
        task_cfg = getattr(self.config, 'task_cfg', {})
        if not task_cfg:
            return 0
        task = task_cfg.get('task_number', 0)
        if task == 1:
            n = task_cfg.get('part', {}).get('num_parts', 2) * 2
        elif task == 2:
            n = task_cfg.get('part', {}).get('num_parts', 5) * 2
        elif task == 3:
            num_boxes = len(task_cfg.get('box', {}).get('box_position', []))
            num_parts = task_cfg.get('part', {}).get('num_parts', 3)
            n = num_boxes * num_parts
        elif task == 4:
            n = 0  # 箱子为静态 XFormPrim，位置固定，无需记录
        else:
            n = 0
        return n * 7

    @property
    def motor_features(self) -> dict[str, Any]:
        feats = {
            "observation.state": {
                "dtype": "float32",
                "shape": (self.STATE_DIM,),
                "names": self.STATE_NAMES,
            },
            "action": {
                "dtype": "float32",
                "shape": (self.ACTION_DIM,),
                "names": self.ACTION_NAMES,
            },
        }
        dim = self.env_state_dim
        if dim > 0:
            num_obj = dim // 7
            names = []
            for i in range(num_obj):
                names.extend([f"obj{i}_{c}" for c in ["x","y","z","qx","qy","qz","qw"]])
            feats["observation.environment_state"] = {
                "dtype": "float32",
                "shape": (dim,),
                "names": names,
            }
        return feats


    @property
    def features(self) -> dict[str, Any]:
        return {**self.motor_features, **self.camera_features}

    @property
    def has_camera(self) -> bool:
        return True

    @property
    def num_cameras(self) -> int:
        return len(self.CAMERA_NAMES)

    @property
    def available_arms(self) -> list[str]:
        return ["left", "right"]

    def record_timing(self, metric_name: str, duration_s: float) -> None:
        metric = self._timing_metrics.setdefault(metric_name, TimingMetric())
        metric.update(duration_s)

    def get_timing_stats(self) -> dict[str, dict[str, float | int]]:
        return {
            name: metric.as_dict()
            for name, metric in self._timing_metrics.items()
            if metric.count > 0
        }

    def print_timing_stats(self) -> None:
        stats = self.get_timing_stats()
        if not stats:
            # logger.info("No timing statistics data available yet")
            return

        lines = ["=== Timing statistics summary ==="]
        for metric_name in ["send_action", "get_observation", "dt_s"]:
            if metric_name not in stats:
                continue

            metric_stats = stats[metric_name]
            lines.append(
                "{name}: count={count}, avg={avg:.2f} ms, min={min_v:.2f} ms, max={max_v:.2f} ms".format(
                    name=metric_name,
                    count=metric_stats["count"],
                    avg=metric_stats["avg_s"] * 1000,
                    min_v=metric_stats["min_s"] * 1000,
                    max_v=metric_stats["max_s"] * 1000,
                )
            )

        summary = "\n".join(lines)
    # logger.info(summary)
        print(summary)
    
    # task4需要获取箱子初始位置用于重置
    def get_box_joints(self):
        """Get box joint initial positions"""
        box_joints = self._scene_builder.box_articulation.get_joint_positions()
        return box_joints
    
    def connect(self) -> None:
        """
        连接机器人并初始化 Isaac Sim 仿真环境
        
        连接Flow:
        1. 创建 SimulationApp 应用
        2. Load specified scene USD file
        3. Create physics World and initialize
        4. Build scene via SceneBuilder (load table, parts, etc.)
        5. 启动仿真运行
        6. 创建机器人接口并初始化
        7. 设置 14 arm joints的初始状态
        
        Exceptions:
            ValueError: 当 task_cfg_path、root_path 或 scene_usd 配置缺失时抛出
            FileNotFoundError: 当场景 USD 文件不存在时抛出
            RuntimeError: 当关节初始化failed时抛出
        """
        if self.is_connected:
            logger.info("Already connected")
            return

        if not self.config.task_cfg_path:
            raise ValueError("Must provide task_cfg_path to load scene")

        # Step 1: 创建 SimulationApp
        from isaacsim import SimulationApp
        logger.info("Step 1: 创建 SimulationApp...")
        self._kit = SimulationApp({
            "width": self.config.sim_width,
            "height": self.config.sim_height,
            "headless": self.config.headless,
        })
        logger.info("SimulationApp 创建成功")

        # Step 2: Load scene USD（关键！之前Missing这一步）
        from isaacsim.core.api import World
        import omni.usd as omni_usd


        logger.info("Step 2: Load scene USD...")
        import os
        scene_path = os.path.join(self.config.task_cfg.get("root_path", ""), self.config.task_cfg.get("scene_usd", ""))
        logger.info(f"场景路径: {scene_path}")
        
        if not os.path.exists(scene_path):
            raise FileNotFoundError(f"场景 USD 文件不存在: {scene_path}")
        
        omni_usd.get_context().open_stage(scene_path)
        logger.info("Scene USD loaded successfully")

        # Step 3: Create World (now World will be based on loaded scene)
        logger.info("Step 3: 创建 World...")
        if World is None:
            raise ImportError("isaacsim.core.api.World 不可用")
        
        self._world = World(
            stage_units_in_meters=1.0,
            physics_dt=self.config.physics_dt,
            rendering_dt=self.config.rendering_dt,
        )
        self._world.initialize_physics()
        logger.info("World Initialization complete")

        # Step 4: SceneBuilder Build scene (add table, parts, boxes, etc.)
        logger.info("Step 4: SceneBuilder 构建场景...")
        try:
            logger.info("导入 SceneBuilder 和 DataLogger...")
            ecbg_root = Path(__file__).parent.parent.parent.parent.parent / "Ubtech_sim"
            if str(ecbg_root) not in os.sys.path:
                os.sys.path.insert(0, str(ecbg_root))
                logger.info(f"已将 {ecbg_root} 插入 sys.path 首位")
            from source.SceneBuilder import SceneBuilder
            from source.DataLogger import DataLogger
            
            # 创建 DataLogger（禁用文件记录）
            data_logger = DataLogger(
                enabled=False,
                csv_path="",
                camera_enabled=False,
                camera_hdf5_path="",
            )
            self._data_logger = data_logger
            
            # Build scene (this will load table, boxes, parts, etc.)
            self._scene_builder = SceneBuilder(self.config.task_cfg, data_logger=data_logger)
            self._scene_builder.build_all() 
            self._scene_builder.build_robot()
            logger.info("SceneBuilder scene construction complete")
            
            
            # 启动仿真
            self._world.play()
            logger.info("World 开始运行")

            # 关键：预热物理引擎，确保 physics_view 创建完成
            for i in range(10):
                self._world.step(render=False)
            logger.info("物理引擎预热完成（10 步）")
            
        except ImportError as e:
            logger.error(f"无法导入 SceneBuilder: {e}")
            raise
        except Exception as e:
            logger.error(f"场景构建failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

        # Step 5: 创建机器人接口（连接到 SceneBuilder 创建的机器人）
        logger.info(f"Step 5: 创建机器人接口...")
        
        actual_prim_path = self.config.prim_path
        
        self._robot_interface = IsaacSimRobotInterface(
            prim_path=actual_prim_path,
            name=self.config.robot_name,
            world=self._world,
            urdf_path=self.config.urdf_path,
        )
        self._robot_interface.initialize()
        
        # 设置14arm joints的初始目标位置
        self._setup_joints()

        self._ros2_teleop = connect_ros2_teleop_if_enabled(
            self.config,
            list(IsaacSimRobotInterface.arm_joint_names),
            list(IsaacSimRobotInterface.finger_joint_names),
        )

        self._head_visualizer.start()

        self._register_world_callbacks()

        # 初始化保持目标：从当前joint states快照一次，作为初始控制量（不随状态变化而变化）
        states = self._robot_interface.get_joint_states()
        if states:
            self._hold_arm_positions = np.array(states['arm_positions'], dtype=np.float32)
            self._hold_finger_positions = np.array(states['finger_positions'], dtype=np.float32)
            logger.info("Snapshot current joint state as initial hold target")

        logger.info(f"Connection successful! Controlling {len(self._arm_joint_indices)} arm joints")

    def reset(self) -> None:
        """重置环境：场景物体恢复初始Pose/随机化，机器人恢复初始关节，控制接口保持不变。"""
        # 1. Unregister callbacks to prevent callback interference during world.step reset
        self._unregister_world_callbacks()

        # 2. Reset scene（Task1/3: 删除旧零件+创建新随机零件，Task2: Reposition，Task4: Reset joints）
        self._scene_builder.reset()

        # 2.5 Task1/3 删除了旧 prim 并创建新 prim，物理视图失效，需要 world.reset() 重建
        #     （产生的关节 stiffness/restitution Warning是机器人模型自带的，无害）
        task_num = self.config.task_cfg.get('task_number', 0)
        if task_num in (1, 3):
            logger.info("[reset] Reinitialize physics simulation (due to prim deletion/creation)...")
            self._world.reset()
            # world.reset() 会覆盖 USD 层的Pose，必须在此之后用 SingleRigidPrim 重新散布
            self._scene_builder.scatter_after_reset()
            # pose_json = 'task1_parts_poses_init.json' if task_num == 1 else None
            # self._scene_builder.set_parts_world_poses(json_file_path=pose_json)

        # 3. 重置机器人关节到初始Pose
        self._robot_interface.reset()

        # 4. 推进物理仿真，让新Pose生效 + 物理稳定（防止零件穿模/悬浮）
        settle_steps = int(1.0 / self.config.physics_dt)  # ~1s settle time
        for _ in range(settle_steps):
            self._robot_interface._world.step(render=False)

        self._send_action_step_idx = 0

        # 5. 清空 pending 控制状态和Keyboard signal queue
        with self._callback_lock:
            self._pending_absolute_action = None
            self._latest_camera_rgb = {}
        self._last_keyboard_frame_id = -1
        self._keyboard_cmd_queue.clear()
        self._current_frame_keys = None
        self._pressed_keys = {}
        self._left_gripping = False
        self._right_gripping = False

        # 6. 重新快照joint states作为保持目标（初始控制量）
        states = self._robot_interface.get_joint_states()
        if states:
            self._hold_arm_positions = np.array(states['arm_positions'], dtype=np.float32)
            self._hold_finger_positions = np.array(states['finger_positions'], dtype=np.float32)
        else:
            self._hold_arm_positions = None
            self._hold_finger_positions = None

        # 7. 重新注册回调
        self._register_world_callbacks()
        logger.info("[IsaacSim]Environment reset")


    def reset_body(self):
        """重置机器人身体位置（不改变arm joints）"""
        if self._robot_interface._articulation is None:
            raise RuntimeError("Articulation uninitialized")
        
        # 获取body indexes
        body_indices = [idx for idx in self._robot_interface._all_dof_indices if idx not in (self._robot_interface.arm_joint_indices or self._robot_interface.finger_joint_indices)]
        body_initial_positions = [self._robot_interface.initial_joint_positions[idx] for idx in body_indices]
        self._robot_interface._articulation.set_joint_positions(
            torch.tensor(body_initial_positions, dtype=torch.float32),
            joint_indices=torch.tensor(body_indices, dtype=torch.int32),
        )
        
        self._robot_interface._articulation.set_joint_velocities(
            torch.zeros(len(body_indices), dtype=torch.float32),
            joint_indices=torch.tensor(body_indices, dtype=torch.int32),
        )

    def _setup_joints(self) -> None:
        """设置14arm joints的索引和初始位置"""
        # 从接口获取14arm joints在34总关节中的索引
        self._arm_joint_indices = self._robot_interface.arm_joint_indices
        
        logger.info(f"arm_joint_indices: {self._arm_joint_indices}")
        logger.info(f"arm_joint_indices 长度: {len(self._arm_joint_indices)}")
        
        if len(self._arm_joint_indices) != 14:
            raise RuntimeError(f"Joint index count error: Expected14，got {len(self._arm_joint_indices)}")
        
        # 获取joint states
        states = self._robot_interface.get_joint_states()
        logger.info(f"states: {states is not None}")
        if states:
            logger.info(f"states.keys(): {states.keys() if isinstance(states, dict) else 'not dict'}")
            if 'arm_positions' in states:
                logger.info(f"arm_positions 长度: {len(states['arm_positions'])}")
            if 'all_positions' in states:
                logger.info(f"all_positions 长度: {len(states['all_positions'])}")
        
        if states is None or 'arm_positions' not in states:
            raise RuntimeError("无法获取joint states或Missing arm_positions")
        
        # 使用Return的14arm joints位置
        arm_positions_list = states['arm_positions']
        # self._target_positions = torch.tensor(arm_positions_list, dtype=torch.float32)
        # self._current_positions = self._target_positions.clone()
        
        logger.info(f"14arm joints已设置，初始位置: {arm_positions_list}")

    def disconnect(self) -> None:
        """
        Disconnect from robot and cleanup resources
        
        Cleanup operations：
        1. Stop keyboard listener
        2. Cleanup robot interface resources
        3. Stop physics simulation
        4. Close SimulationApp
        
        安全的资源释放，不会因为部分操作failed而中断整体清理过程。
        """
        if not self.is_connected:
            return

        self._stop_keyboard_listener()

        stop_ros2_teleop(self._ros2_teleop)
        self._ros2_teleop = None

        self._head_visualizer.stop()

        self._unregister_world_callbacks()
        
        if self._robot_interface:
            self._robot_interface.cleanup()
            self._robot_interface = None
        self._data_logger = None
        
        if self._world:
            try:
                self._world.stop()
            except Exception:
                pass
            self._world = None
        
        if self._kit:
            try:
                self._kit.close()
            except Exception as e:
                # logger.warning(f"Close SimulationApp 时出错: {e}")
                pass
            self._kit = None
        
        # logger.info("已断开连接")

    def _init_keyboard_listener(self) -> None:
        """
        初始化键盘监听（优先 pynput，回退到 evdev）

        pynput 依赖 X11 输入监控，在 RustDesk/VNC 等远程桌面下不工作。
        evdev 直接读取 /dev/input 设备，绕过 X11，可在任何环境工作。
        """
        self._pressed_keys = {
            "speed_up": False, "speed_down": False,
            "quit": False,
            "switch_control_arm": False,
            "toggle_bimanual_mode": False,
            "toggle_gripper_mode": False,
            "toggle_go_home": False,
            "x_up": False, "x_down": False,
            "y_up": False, "y_down": False,
            "z_up": False, "z_down": False,
            "rx_up": False, "rx_down": False,
            "ry_up": False, "ry_down": False,
            "rz_up": False, "rz_down": False,
            "gripper_open": False, "gripper_close": False,
        }

        # 优先使用 evdev：直接读取 /dev/input，在 Docker / RustDesk / VNC 等
        # 远程桌面环境下均可靠工作；pynput 依赖 X11，在这些环境中常静默失效。
        if EVDEV_AVAILABLE:
            try:
                listener = EvdevKeyboardListener(
                    on_press=self._on_key_press,
                    on_release=self._on_key_release,
                )
                listener.start()
                self._keyboard_listener = listener
                logger.info("键盘监听已启动 (evdev)")
                return
            except Exception as e:
                logger.warning(f"evdev 启动failed: {e}，尝试 pynput 后端")

        if PYNPUT_AVAILABLE:
            try:
                self._keyboard_listener = keyboard.Listener(
                    on_press=self._on_key_press,
                    on_release=self._on_key_release,
                )
                self._keyboard_listener.start()
                logger.info("键盘监听已启动 (pynput)")
                return
            except Exception as e:
                logger.warning(f"pynput 启动failed: {e}")

        logger.warning("evdev 和 pynput 均不可用，Keyboard control功能被禁用")

    def _stop_keyboard_listener(self) -> None:
        if self._keyboard_listener:
            self._keyboard_listener.stop()
            self._keyboard_listener = None



    @property
    def leader_arms(self) -> dict:
        """Simulation environment has no leader arms, returns empty dict"""
        return {}

    @property
    def follower_arms(self) -> dict:
        """Simulation environment has no follower arms, returns empty dict"""
        return {}

    @property
    def cameras(self) -> dict:
        """Return camera configuration"""
        return self.config.cameras if hasattr(self.config, 'cameras') else {}

    def _teleop_key(self, action_name: str, default: str) -> str:
        keymap = getattr(self.config, "teleop_keymap", {})
        value = keymap.get(action_name, default)
        return str(value).lower()

    def _resolve_key_action(self, char: str | None = None) -> str | None:
        if char is None:
            return None
        key_to_action_task4 = {
            self._teleop_key("x_up", "1"): "x_up",
            self._teleop_key("x_down", "3"): "x_down",
            self._teleop_key("y_up", "4"): "y_up",
            self._teleop_key("y_down", "6"): "y_down",
            self._teleop_key("z_up", "7"): "z_up",
            self._teleop_key("z_down", "9"): "z_down",
            self._teleop_key("rx_up", "y"): "rx_up",
            self._teleop_key("rx_down", "u"): "rx_down",
            self._teleop_key("ry_up", "v"): "ry_up",
            self._teleop_key("ry_down", "b"): "ry_down",
            self._teleop_key("rz_up", "n"): "rz_up",
            self._teleop_key("rz_down", "m"): "rz_down",
            self._teleop_key("gripper_open", "k"): "gripper_open",
            self._teleop_key("gripper_close", "l"): "gripper_close",
        }
        return key_to_action_task4.get(char)

    def _apply_active_arm_delta(
        self, active_delta: np.ndarray, active_gripper: float
    ) -> tuple[np.ndarray, np.ndarray, float, float]:
        left_delta = np.zeros(6, dtype=np.float32)
        right_delta = np.zeros(6, dtype=np.float32)
        left_gripper = 0.0
        right_gripper = 0.0

        if self.current_control_arm == "left":
            left_delta = active_delta.copy()
            left_gripper = active_gripper
            if self.bimanual_control_enabled:
                right_delta = active_delta * self.BIMANUAL_MIRROR_SIGNS
                right_gripper = active_gripper
        else:
            right_delta = active_delta.copy()
            right_gripper = active_gripper
            if self.bimanual_control_enabled:
                left_delta = active_delta * self.BIMANUAL_MIRROR_SIGNS
                left_gripper = active_gripper

        return left_delta, right_delta, left_gripper, right_gripper


    def _enqueue_keyboard_snapshot(self) -> None:
        """将当前 _pressed_keys 快照入队，保证每次按键变化都被记录。

        该方法在键盘监听线程中调用，deque 本身是线程安全的。
        maxlen=256 保证不会无限堆积。
        """
        self._keyboard_cmd_queue.append(dict(self._pressed_keys))

    def _on_key_press(self, key) -> bool | None:
        """
        Handle key press event
        
        Keyboard mapping:
        - Speed: +/- 调整Speed level
        - Exit: Q Exit程序
        - Switch: J Switch控制的机械臂(左<->右)
        - Mode: 2 Toggle gripper control mode(position/effort)
        - Mode: 0 Switch单双臂Control mode
        - Pose: 1/3/4/6/7/9/y/u/g/h/n/m
        - Gripper: K(open方向)/L(Close direction)

        Args:
            key: 按键对象

        Returns:
            bool | None: Return False 表示程序应Exit，否则Return None
        """
        try:
            char = getattr(key, "char", None)
            char = char.lower() if char is not None else None
            key_name = getattr(key, "name", None)
            print(f"[keyboard] press: char={char}, name={key_name}")

            go_home_key = self._teleop_key("toggle_go_home", "down")
            if key_name == go_home_key or (char is not None and char == go_home_key):
                # 防止按住下方向键时因键盘重复触发导致反复切换
                if not self._pressed_keys["toggle_go_home"]:
                    self._pressed_keys["toggle_go_home"] = True
                    self._go_home = not self._go_home
                return None

            # 处理Exit
            if char == self._teleop_key("quit", "q"):
                self._pressed_keys["quit"] = True
                # logger.info("按下Exit键 (Q)")
                return False
            
            if char == self._teleop_key("switch_control_arm", "o"):
                self._pressed_keys["switch_control_arm"] = True
                self.current_control_arm = "right" if self.current_control_arm == "left" else "left"
                # logger.info(f"Switch控制机械臂: {self.current_control_arm}")
                self._enqueue_keyboard_snapshot()
                return None

            if char == self._teleop_key("toggle_bimanual_mode", "0"):
                self._pressed_keys["toggle_bimanual_mode"] = True
                self.bimanual_control_enabled = not self.bimanual_control_enabled
                mode_name = "Dual-arm simultaneous control" if self.bimanual_control_enabled else "Single-arm control"
                # logger.info(f"SwitchControl mode: {mode_name}")
                return None

            if char == self._teleop_key("toggle_gripper_mode", "2"):
                # 防止按住按键时因键盘重复触发导致连续Switch
                if not self._pressed_keys["toggle_gripper_mode"]:
                    self._pressed_keys["toggle_gripper_mode"] = True
                    self.gripper_control_mode = (
                        "effort" if self.gripper_control_mode == "position" else "position"
                    )
                return None
            
            # 处理Speed调整
            if char in (self._teleop_key("speed_up", "+"), "="):
                self._speed_index = min(self._speed_index + 1, len(self.config.speed_levels) - 1)
                # logger.info(f"Speed提升: {self.config.speed_levels[self._speed_index]:.3f}")
                return None
            elif char == self._teleop_key("speed_down", "-"):
                self._speed_index = max(self._speed_index - 1, 0)
                # logger.info(f"Speed降低: {self.config.speed_levels[self._speed_index]:.3f}")
                return None

            action_name = self._resolve_key_action(char)
            if action_name is not None:
                self._pressed_keys[action_name] = True
                self._enqueue_keyboard_snapshot()
                return None


        except Exception as e:
            print(f"[keyboard] Handle error: {e}", flush=True)

        return None
    
    def _on_key_release(self, key) -> None:
        """
        Handle key release event
        
        Record all released key states

        Args:
            key: 按键对象
        """
        try:
            char = getattr(key, "char", None)
            char = char.lower() if char is not None else None
            key_name = getattr(key, "name", None)
            go_home_key = self._teleop_key("toggle_go_home", "down")

            if key_name == go_home_key or (char is not None and char == go_home_key):
                self._pressed_keys["toggle_go_home"] = False
                return None

            if char == self._teleop_key("switch_control_arm", "j"):
                self._pressed_keys["switch_control_arm"] = False
                return None

            if char == self._teleop_key("toggle_bimanual_mode", "0"):
                self._pressed_keys["toggle_bimanual_mode"] = False
                return None

            if char == self._teleop_key("toggle_gripper_mode", "2"):
                self._pressed_keys["toggle_gripper_mode"] = False
                return None

            action_name = self._resolve_key_action(char)
            if action_name is not None:
                self._pressed_keys[action_name] = False
                self._enqueue_keyboard_snapshot()

        except Exception as e:
            # logger.error(f"键盘释放Handle error: {e}", exc_info=True)
            pass

    def _compute_keyboard_delta(self, key_snapshot: dict[str, bool] | None = None) -> tuple[np.ndarray, np.ndarray, float, float, np.ndarray]:
        """
        Compute end-effector delta from keyboard input
        
        Return双臂的末端Pose增量和Gripper控制指令。根据Currently controlled arm
        (current_control_arm) 计算对应臂的位移和姿态增量。
        
        Args:
            key_snapshot: 可选的按键快照字典。为 None 时读取 _pressed_keys（兼容旧调用）。
        
        增量格式：
        - left_delta: [x, y, z, rx, ry, rz] (左臂末端Pose增量)
        - right_delta: [x, y, z, rx, ry, rz] (右臂末端Pose增量)  
        - left_gripper: 左臂Gripper方向指令 (1.0=open方向, -1.0=Close direction, 0.0=不动)
        - right_gripper: 右臂Gripper方向指令 (1.0=open方向, -1.0=Close direction, 0.0=不动)
        
        Returns:
            tuple: (left_delta, right_delta, left_gripper, right_gripper, action)
                其中每 delta 是 6 D数组 [x, y, z, rx, ry, rz]
        """
        keys = key_snapshot if key_snapshot is not None else self._pressed_keys
        step = self.config.speed_levels[self._speed_index]
        
        active_delta = np.zeros(6, dtype=np.float32)
        active_gripper = 0.0

        for index, axis in enumerate(self.MOTION_AXES):
            if keys.get(f"{axis}_up"):
                active_delta[index] += step
            if keys.get(f"{axis}_down"):
                active_delta[index] -= step

        # K(open) → -1.0 → 回调中步进向 open_width 方向
        # L(close) → +1.0 → 回调中步进向 close_width 方向
        if keys.get("gripper_open"):
            active_gripper = -1.0
        if keys.get("gripper_close"):
            active_gripper = 1.0

        left_delta, right_delta, left_gripper, right_gripper = self._apply_active_arm_delta(
            active_delta, active_gripper
        )
        
        action = np.concatenate([left_delta, right_delta, [left_gripper], [right_gripper]])
        # Note: This is teleoperation internal delta command (14D), not external record/training action.
        assert action.shape == (14,), f"计算的 action Dimension error: {action.shape}, content: {action.tolist()}"
        return left_delta, right_delta, left_gripper, right_gripper, action

    # ===================== Core修改：CSV保存逻辑 =====================
    def write_gripper_torque_log(self, timestamp, control_arm, pre_tau, post_tau, file_path="gripper_torque_log.csv"):
        """
        写入Gripper力矩日志到CSV文件
        :param timestamp: timestamp（float）
        :param control_arm: control arm name（str，如"left"/"right"/"both"）
        :param pre_tau: torque before control（np.array/list）
        :param post_tau: torque after control（np.array/list）
        :param file_path: log file path
        """
        import csv
        # 定义CSV列名
        fieldnames = ["timestamp", "control arm name", "pre_tau", "post_tau"]
        
        # 转换为可序列化的格式（numpy数组转List）
        pre_tau_list = pre_tau.tolist() if isinstance(pre_tau, np.ndarray) else pre_tau
        post_tau_list = post_tau.tolist() if isinstance(post_tau, np.ndarray) else post_tau
        
        # Check if file exists, write header if not
        file_exists = os.path.exists(file_path)
        
        try:
            with open(file_path, mode='a', newline='', encoding='utf-8') as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                
                # Add header on first write
                if not file_exists:
                    writer.writeheader()
                
                # Write data row
                writer.writerow({
                    "timestamp": timestamp,
                    "control arm name": control_arm,
                    "pre_tau": pre_tau_list,  # 力矩数组（如[0.12, 0.15]）
                    "post_tau": post_tau_list
                })
        except Exception as e:
            print(f">>>[ERROR] 写入CSV日志failed: {e}")


    def send_action(self, action: torch.Tensor | None = None) -> torch.Tensor:
        """Set control intent or construct action tensor for recording.

        - 推理/回放Mode (action is not None): 写入 _pending_absolute_action，
          Consumed and executed by _robot_control_callback in next physics step.
        - Teleoperation mode (action is None): Actual control already by _robot_control_callback
          Directly read keyboard state complete, here only construct action tensor for data recording.
        """
        send_action_start_t = time.perf_counter()
        try:
            if not self.is_connected:
                raise RobotDeviceNotConnectedError("Not connected")

            if action is not None:
                # ====== Mode A: 推理/回放（所有 task 统一 20 D） ======
                action_np = action.detach().cpu().numpy() if isinstance(action, torch.Tensor) else np.asarray(action)
                action_np = action_np.reshape(-1)

                if action_np.shape[0] != self.ACTION_DIM:
                    raise ValueError(f"推理动作Dimension error: Expected {self.ACTION_DIM}，got {action_np.shape[0]}")

                # Write to pending (callback will consume in next physics step)
                with self._callback_lock:
                    self._pending_absolute_action = action_np.copy()

                target_action = torch.tensor(action_np, dtype=torch.float32)

            else:
                # ====== Mode B: Teleoperation (only construct action tensor for recording) ======
                # Actual control completed by directly reading keyboard in _robot_control_callback

                # Construct action tensor for recording (unified 20D)
                joints_states = self._robot_interface.get_joint_states()
                if joints_states and 'arm_positions' in joints_states:
                    arm_pos = torch.tensor(joints_states['arm_positions'], dtype=torch.float32)
                    gripper_pos = torch.tensor(joints_states.get('finger_positions'), dtype=torch.float32)

                    # Use callback-maintained grip state (sticky) instead of instantaneous keyboard state
                    # 1.0 = gripping (force control)，-1.0 = open中（位控）
                    lg = torch.tensor(1.0 if self._left_gripping else -1.0, dtype=torch.float32)
                    rg = torch.tensor(1.0 if self._right_gripping else -1.0, dtype=torch.float32)
                    target_action = torch.cat([arm_pos, gripper_pos, lg.unsqueeze(0), rg.unsqueeze(0)])
                else:
                    target_action = torch.zeros(self.ACTION_DIM, dtype=torch.float32)

            return target_action

        finally:
            duration_s = time.perf_counter() - send_action_start_t
            self.record_timing("send_action", duration_s)

    def get_observation(self) -> dict[str, torch.Tensor]:
        """
        Get current robot observation (joint states + camera RGB)
        
        观测content：
        1. joint states: 20 joint positions（14 arm joints + 4 finger joints + 2 gripper control commands）
        2. camera images: 
        - observation.images.head_left: Head left stereo camera RGB
        - observation.images.head_right: Head right stereo camera RGB
        - observation.images.wrist_left: Left wrist camera RGB
        - observation.images.wrist_right: Right wrist camera RGB
        
        Return：
            dict[str, torch.Tensor]: Observation dict, containing:
                - "observation.state": shape (18,) float32，18 joint positions
                - "observation.images.{camera_name}": shape (3, H, W) float32，
                camera images数据，已归一化到 [0, 1]
                
        Exceptions:
            RobotDeviceNotConnectedError: 当机器人Not connected时抛出
            
        Notes:
            - Joint positions default to radians
            - Camera images automatically converted to float and normalized
            - 如果Camera获取failed，使用零矩阵代替
        """
        get_observation_start_t = time.perf_counter()
        try:
            if not self.is_connected:
                raise RobotDeviceNotConnectedError("Not connected")

            obs = {}

            # 获取 14 arm joints + 4 Gripper位置，共 18 D（不读取 sixforce）
            try:
                joints_states = self._robot_interface.get_joint_states()
                if joints_states and "arm_positions" in joints_states:
                    arm_pos = torch.tensor(joints_states["arm_positions"], dtype=torch.float32)
                    gripper_pos = torch.tensor(joints_states.get("finger_positions", [0.0] * 4), dtype=torch.float32)
                    lg_state = torch.tensor(1.0 if self._left_gripping else -1.0, dtype=torch.float32)
                    rg_state = torch.tensor(1.0 if self._right_gripping else -1.0, dtype=torch.float32)
                    state = torch.cat([arm_pos, gripper_pos, lg_state.unsqueeze(0), rg_state.unsqueeze(0)])
                    if state.numel() != self.STATE_DIM:
                        raise RuntimeError(f"state Dimension error: Expected {self.STATE_DIM}，got {state.numel()}")
                    obs["observation.state"] = state
                    self._current_positions = arm_pos.clone()  # 仅保留arm joints，便于Debug打印
                else:
                    raise RuntimeError("无法获取joint states或Missing arm_positions")
            except Exception as e:
                logger.warning(f"[observation] Failed to get joint states: {e}，Using zero values。")
                obs["observation.state"] = torch.zeros(self.STATE_DIM, dtype=torch.float32)
                self._current_positions = torch.zeros(14, dtype=torch.float32)

            # Camera images: prioritize render callback cache, read directly on cache miss
            black_frame = torch.zeros(
                (3, self.config.camera_height, self.config.camera_width), dtype=torch.float32
            )
            for cam_name in self.CAMERA_NAMES:
                img_key = f"observation.images.{cam_name}"
                try:
                    with self._callback_lock:
                        rgb_cached = self._latest_camera_rgb.get(cam_name)
                        rgb = None if rgb_cached is None else rgb_cached.copy()
                    if rgb is None:
                        rgb = self._robot_interface.get_camera_rgb(cam_name)
                    if rgb is None:
                        raise RuntimeError("Return None")
                    obs[img_key] = torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0
                except Exception as e:
                    logger.warning(f"[observation] Get camera {cam_name} failed: {e}，Using black image。")
                    obs[img_key] = black_frame.clone()

            # Environment object poses
            dim = self.env_state_dim
            if dim > 0:
                try:
                    if self._scene_builder is not None:
                        env_flat = self._scene_builder.get_object_poses_flat()
                        if env_flat.shape[0] == dim:
                            obs["observation.environment_state"] = torch.from_numpy(env_flat)
                        else:
                            logger.warning(f"[observation] env_state dimension mismatch: Expected {dim}, got {env_flat.shape[0]}")
                            obs["observation.environment_state"] = torch.zeros(dim, dtype=torch.float32)
                    else:
                        obs["observation.environment_state"] = torch.zeros(dim, dtype=torch.float32)
                except Exception as e:
                    logger.warning(f"[observation] 获取物体Posefailed: {e}")
                    obs["observation.environment_state"] = torch.zeros(dim, dtype=torch.float32)

            self._last_observation = obs
            return obs
        finally:
            duration_s = time.perf_counter() - get_observation_start_t
            self.record_timing("get_observation", duration_s)
    
    
    def teleop_step(self, record_data: bool = False) -> tuple[dict, dict] | None:
        """
        Execute single teleop step, get observation and action
        
        Convenience interface combining send_action() and get_observation(),
        for real-time teleoperation demo or data collection.
        
        Flow:
        1. Send keyboard or external action to robot
        2. Get current observation (joint states + camera images)
        3. 如果 record_data=True，Return (观测, 动作)；否则Return None
        
        Args:
            record_data: Whether to record and return data, default False
            
        Returns:
            - 如果 record_data=False: Return None
            - 如果 record_data=True: Return (obs, action)
                - obs: 观测字典，见 get_observation() 文档
                - action: 动作字典，containing "action" 键
                
        Exceptions:
            RobotDeviceNotConnectedError: 当机器人Not connected时抛出
            
        示例：
            >>> robot.connect()
            >>> # 仅发送动作，不记录
            >>> robot.teleop_step(record_data=False)
            >>> 
            >>> # 发送动作并记录数据用于学习
            >>> obs, action = robot.teleop_step(record_data=True)
            >>> print(obs.keys())  # Observation keys
            >>> print(action["action"].shape)  # Action dimensions
        """
        # 1. 设置控制意图（写入 pending 状态）
        action_tensor = self.send_action(None)
        # 2. 推进物理仿真（触发回调执行实际控制）
        render_now = (self._send_action_step_idx % self._render_every_n) == 0
        self.step(render=render_now)
        # 3. 读取观测
        obs = self.get_observation()

        if not record_data:
            return None

        return (obs, {"action": action_tensor})

    def calibrate(self, arm_name: str | None = None) -> None:
        """
        Calibrate robot (Isaac Sim simulation environment requires no calibration)
        
        This method is a virtual implementation, as robots in simulation environment don't need actual calibration.
        Real robot implementation may require recalibrating origin or sensors.
        
        Args:
            arm_name: 可选，指定要校准的机械臂 ("left" 或 "right")
        """
        # logger.info("Isaac Sim 仿真环境无需校准")

    def print_logs(self) -> None:
        """
        Print robot current status information
        
        Output content:
        - Connection status
        - Current speed level and value
        - arm joints总数
        - Joint index mapping
        - Current joint positions
        - Currently controlled arm
        """
        if not self.is_connected:
            print("Not connected")
            return
            
        print(f"Speed level: {self._speed_index} ({self.config.speed_levels[self._speed_index]:.3f})")
        print(f"arm joints数: 14")
        print(f"Joint index mapping: {self._arm_joint_indices}")
        print(f"Current control arm: {self.current_control_arm}")
        print(f"Control mode: {'Dual-arm simultaneous control' if self.bimanual_control_enabled else 'Single-arm control'}")
        if self._current_positions is not None:
            print(f"Current position: {self._current_positions.tolist()}")

    def __del__(self):
        """Cleanup on destruction"""
        try:
            self.disconnect()
        except Exception:
            pass


# =========================================================================
# Factory function
# =========================================================================

def make_mobile_manipulator(config: Any) -> MobileManipulator:
    """
    创建 MobileManipulator 实例的Factory function
    
    This is a convenience function for standardized robot instantiation.
    
    Args:
        config: 机器人配置对象，可以是：
            - WalkerS2Config: 配置对象
            - dict: 配置字典，应containing 'config_path' 键
            - None: 使用默认配置
            
    Returns:
        MobileManipulator: 初始化后的机器人实例（Not connected）
    """
    return MobileManipulator(config)
