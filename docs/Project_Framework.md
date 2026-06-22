# Global Humanoid Robot Challenge Document

**Chinese Version:** [Project_Framework_zh.md](Project_Framework_zh.md)

## 1. System Overview

Global Humanoid Robot Challenge built on the LeRobot 0.5.1 framework, providing high-fidelity physics simulation and multiple control modes. This document details the architecture design and implementation details of the control system.

---

## 2. Technical Architecture

### 2.1 Core Components

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         LeRobot 0.5.1 Framework                          │
├───────────────────────────────────────┬──────────────────────────────────┤
│        Robot Base Class               │       Teleoperator Base Class    │
├───────────────────────────────────────┼──────────────────────────────────┤
│  WalkerS2sim                          │  WalkerS2KeyboardTeleop          │
│  - 20-dimensional state/action space  │  - pynput/evdev keyboard backend │
│  - 14 arm joints + 4 fingers + 2      │  - Single/dual arm switching     │
│    grippers                           │  - Speed levels                  │
│  - 4 cameras                          │  - Frame gating + queue merging  │
│  - Isaac Sim physics engine           │  - Callback mode support         │
│  - IK solver                          │                                  │
│  - Callback-driven control logic      │                                  │
├───────────────────────────────────────┴──────────────────────────────────┤
│  Optional Modules:                                                       │
│  - ROS2 Teleop Subscriber                                                │
│  - Head Stereo Visualizer                                                │
└──────────────────────────────────────────────────────────────────────────┘
```

### 2.2 State Space and Action Space

#### 2.2.1 State Dimension (20D)

```python
STATE_DIM = 20
STATE_NAMES = [
    # 14 arm joints (7 left + 7 right)
    "L_shoulder_pitch_joint.pos", "L_shoulder_roll_joint.pos", "L_shoulder_yaw_joint.pos",
    "L_elbow_roll_joint.pos", "L_elbow_yaw_joint.pos", "L_wrist_pitch_joint.pos", "L_wrist_roll_joint.pos",
    "R_shoulder_pitch_joint.pos", "R_shoulder_roll_joint.pos", "R_shoulder_yaw_joint.pos",
    "R_elbow_roll_joint.pos", "R_elbow_yaw_joint.pos", "R_wrist_pitch_joint.pos", "R_wrist_roll_joint.pos",
    # 4 finger joints (2 left + 2 right)
    "L_finger1_joint.pos", "L_finger2_joint.pos",
    "R_finger1_joint.pos", "R_finger2_joint.pos",
    # 2 gripper control commands (binary)
    "left_gripper",   # 1.0=close, -1.0=open
    "right_gripper",  # 1.0=close, -1.0=open
]
```

#### 2.2.2 Observation Format

```python
observation = {
    "observation.state": torch.Tensor(shape=(20,)),  # 20-dimensional joint state
    "observation.images.head_left": torch.Tensor(shape=(3, H, W)),
    "observation.images.head_right": torch.Tensor(shape=(3, H, W)),
    "observation.images.wrist_left": torch.Tensor(shape=(3, H, W)),
    "observation.images.wrist_right": torch.Tensor(shape=(3, H, W)),
}
```

#### 2.2.3 Action Format

```python
action = {
    "L_shoulder_pitch_joint.pos": 0.1,
    # ... 13 arm joints
    "L_finger1_joint.pos": 0.0,
    # ... 3 finger joints
    "left_gripper": 1.0,   # 1.0=close, -1.0=open
    "right_gripper": -1.0,
}
```

---

## 3. Keyboard Control Implementation

### 3.1 Keyboard Listener Architecture

Walker S2 keyboard teleoperation supports two backends:

| Backend | Application   | Import Module       |
| ------- | ------------- | ------------------- |
| pynput  | Local desktop | `pynput.keyboard` |
| evdev   | Docker/Remote | `evdev`           |

### 3.2 Key Mapping Table

#### 3.2.1 End-Effector Translation (Hold to Move Continuously)

| Key   | Action | Description                      |
| ----- | ------ | -------------------------------- |
| `1` | y_up   | End-effector +Y direction        |
| `3` | y_down | End-effector -Y direction        |
| `4` | x_down | End-effector -X direction        |
| `6` | x_up   | End-effector +X direction        |
| `7` | z_up   | End-effector +Z direction (up)   |
| `9` | z_down | End-effector -Z direction (down) |

#### 3.2.2 End-Effector Rotation (Hold to Rotate Continuously)

| Key   | Action  | Description                   |
| ----- | ------- | ----------------------------- |
| `y` | ry_up   | Rotate around Y-axis positive |
| `u` | ry_down | Rotate around Y-axis negative |
| `v` | rx_up   | Rotate around X-axis positive |
| `b` | rx_down | Rotate around X-axis negative |
| `n` | rz_up   | Rotate around Z-axis positive |
| `m` | rz_down | Rotate around Z-axis negative |

#### 3.2.3 Gripper Control

| Key   | Action        | Description   |
| ----- | ------------- | ------------- |
| `k` | gripper_open  | Open gripper  |
| `l` | gripper_close | Close gripper |

#### 3.2.4 System Control

| Key           | Action          | Description                        |
| ------------- | --------------- | ---------------------------------- |
| `o`         | toggle_arm      | Switch control arm (left ↔ right) |
| `0`         | toggle_bimanual | Toggle single/dual-arm sync mode   |
| `h`         | go_home         | Return to home position            |
| `+` / `=` | speed_up        | Increase speed level               |
| `-`         | speed_down      | Decrease speed level               |
| `q`         | quit            | Exit program                       |

### 3.3 Speed Levels

| Index | Speed (m/step) | Description   |
| ----- | -------------- | ------------- |
| 0     | 0.010          | Low (default) |
| 1     | 0.035          | Medium        |

**Note**: The current version has only two speed levels, with default speed index 0 (low speed).

### 3.4 Frame Gating Control Logic

To prevent duplicate processing within the same frame and key loss, the frame gating + queue merging mechanism is implemented in **WalkerS2KeyboardTeleop**.

```python
# In teleop.get_action_numpy()
if frame_id != self._last_keyboard_frame_id:
    self._last_keyboard_frame_id = frame_id
  
    # Queue snapshot captures short presses (press+release between frames)
    key_snapshot = {}
    while self._keyboard_cmd_queue:
        snap = self._keyboard_cmd_queue.popleft()
        for k, v in snap.items():
            if v:
                key_snapshot[k] = v
  
    # Real-time state captures continuous holds
    for k, v in self._pressed_keys.items():
        if v:
            key_snapshot[k] = v
  
    self._current_frame_keys = key_snapshot
```

**Purpose**:

1. Prevent duplicate processing within the same frame (physics callback called multiple times within one world.step)
2. Prevent loss of short presses (queue captures瞬时 events, real-time state captures continuous holds)

**Architecture Note**:

- WalkerS2sim obtains keyboard actions via `self._teleop.get_action_numpy(frame_id=...)`
- Frame gating logic is handled internally in teleop, as the keyboard listener resides there
- This design allows the same teleop to be shared by multiple robots

---

## 4. Control Modes Explained

### 4.1 Callback-Driven Control Architecture

Walker S2sim adopts a **callback-driven** control architecture, with `_robot_control_callback` method executing automatically at each physics step.

```python
def _robot_control_callback(self, step_size: float) -> None:
    """Automatically executed at each physics step: unified joint position control

    Control Logic:
    1. Initialization: Snapshot current joint states as hold target on first call
    2. Inference/Replay mode: Consume _pending_absolute_action to update hold target
    3. Teleoperation mode: Call teleop.get_action_numpy() to get keyboard actions
    4. go_home mode: Detect go_home key press, trigger interpolation back to initial position
    5. No input: Continue issuing hold target from previous frame
    """
```

### 4.2 Four Control Modes

#### 4.2.1 Teleoperation Mode

**Feature**: `send_action(None)`

**Flow**:

1. Callback invokes `teleop.get_action_numpy(frame_id)` to get keyboard actions
2. Frame gating logic processes key states (preventing key loss and duplicate processing)
3. IK solver calculates target joint positions
4. Updates `_hold_arm_positions` and `_hold_finger_positions`
5. Sends to robot for execution

**Code Path**:

```
lerobot_teleoperate.py → teleop_loop() → robot.send_action(None)
    → WalkerS2sim.send_action() → register callback
    → _robot_control_callback() → teleop.get_action_numpy()
```

#### 4.2.2 Inference Mode

**Feature**: `send_action(action_dict)` with action dictionary from policy model

**Flow**:

1. Policy model outputs action dictionary
2. `send_action()` writes action to `_pending_absolute_action`
3. Callback consumes pending action, updates hold target
4. Sends directly to joint position controller

**Code Path**:

```
lerobot_record.py (with policy) → record_loop() → robot.send_action(action_dict)
    → WalkerS2sim.send_action() → _pending_absolute_action = action_array
    → _robot_control_callback() → consume pending action
```

#### 4.2.3 Replay Mode

**Feature**: `send_action(action_dict)` with action dictionary from dataset records

**Flow**:

1. Read action sequence from dataset
2. Call `send_action()` frame by frame
3. Callback consumes actions, updates hold target
4. Also restores environment object poses (if applicable)

**Code Path**:

```
lerobot_replay.py → replay_loop() → robot.send_action(action_dict)
    → WalkerS2sim.send_action() → _pending_absolute_action = action_array
    → _robot_control_callback() → consume pending action
```

#### 4.2.4 go_home Mode

**Feature**: Press `h` key to trigger

**Flow**:

1. Callback detects `keyboard_state.get("go_home")` key edge
2. Toggles `_go_home` flag
3. If triggered, linearly interpolates back to initial joint positions
4. Automatically returns to normal control after interpolation completes

**Parameters**:

- `_num_interpolation_steps`: Interpolation steps (default 200)

---

## 5. Callback and Teleoperation Interaction

### 5.1 Control Flow Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     Isaac Sim Physics Step                               │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│              WalkerS2sim._robot_control_callback()                       │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ 1. Check go_home key edge trigger                                  │  │
│  │ 2. Initialize hold target (first call only)                        │  │
│  │ 3. Read pending action (inference/replay mode)                     │  │
│  │ 4. Call teleop.get_action_numpy() (teleop mode)                    │  │
│  │ 5. Update _hold_arm_positions and _hold_finger_positions           │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│         WalkerS2KeyboardTeleop.get_action_numpy()                        │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ 1. Frame gate check: frame_id != last_keyboard_frame_id            │  │
│  │ 2. Queue snapshot: clear _keyboard_cmd_queue for short presses     │  │
│  │ 3. Real-time state: merge _pressed_keys for continuous holds       │  │
│  │ 4. Speed scaling: scale action magnitude by speed_index            │  │
│  │ 5. Dual-arm mirroring: mirror to other arm if enabled              │  │
│  │ 6. Return (left_delta, right_delta, left_gripper, right_gripper)   │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│              Isaac Sim RobotArticulation API                             │
│  - control_dual_arm_ik()                                                 │
│  - set_joint_positions()                                                 │
└──────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Frame Synchronization Mechanism

**Problem**: Isaac Sim physics callback frequency (200Hz) is higher than rendering frequency (30Hz), potentially causing multiple callback invocations within the same frame.

**Solution**: Frame gate ID mechanism

```python
# In teleop.get_action_numpy(frame_id=step_idx)
if frame_id != self._last_keyboard_frame_id:
    # New frame starts, process key snapshot
    self._last_keyboard_frame_id = frame_id
    # ... processing logic
else:
    # Repeated invocation within same frame, return cached action
    return self._cached_action
```

### 5.3 Anti-Key-Loss Mechanism

**Problem**: Quick key press and release (short press) may occur between two frames, causing key events to be lost.

**Solution**: Queue + real-time state dual capture

```python
# Queue captures short press events
while self._keyboard_cmd_queue:
    snap = self._keyboard_cmd_queue.popleft()
    for k, v in snap.items():
        if v:
            key_snapshot[k] = v

# Real-time state captures continuous holds
for k, v in self._pressed_keys.items():
    if v:
        key_snapshot[k] = v
```

---

## 6. Configuration Parameters Explained

### 6.1 Robot Configuration (WalkerS2Config)

| Parameter                | Type  | Default                                  | Description                      |
| ------------------------ | ----- | ---------------------------------------- | -------------------------------- |
| `type`                 | str   | `"walker_s2_sim"`                      | Robot type identifier            |
| `id`                   | str   | `"walker_s2_default"`                  | Robot unique identifier          |
| `task_name`            | str   | `"Foam_Inlaying"`                      | Task name                        |
| `task_cfg_path`        | str   | `"Ubtech_sim/config/Packing_Box.yaml"` | Task config file path            |
| `headless`             | bool  | `False`                                | Whether to run in headless mode  |
| `sim_width`            | int   | `1280`                                 | Simulation window width          |
| `sim_height`           | int   | `720`                                  | Simulation window height         |
| `physics_dt`           | float | `1/200`                                | Physics simulation step size     |
| `rendering_dt`         | float | `1/20`                                 | Rendering step size              |
| `speed_levels`         | list  | `[0.010, 0.035]`                       | Speed levels list                |
| `default_speed_index`  | int   | `0`                                    | Default speed index              |
| `head_viz_enabled`     | bool  | `True`                                 | Enable head camera visualization |
| `head_viz_window_name` | str   | `"walker_s2_cameras"`                  | Visualization window name        |
| `head_viz_scale`       | float | `1.0`                                  | Window scale ratio               |
| `head_viz_every_n`     | int   | `10`                                   | Update display every N frames    |
| `head_viz_window_x`    | int   | `40`                                   | Window X coordinate              |
| `head_viz_window_y`    | int   | `40`                                   | Window Y coordinate              |
| `head_viz_show_labels` | bool  | `True`                                 | Display camera labels            |

### 6.2 Keyboard Teleoperation Configuration (WalkerS2KeyboardTeleopConfig)

| Parameter               | Type | Default                  | Description                    |
| ----------------------- | ---- | ------------------------ | ------------------------------ |
| `type`                | str  | `"walker_s2_keyboard"` | Teleoperator type              |
| `id`                  | str  | `"walker_s2_teleop"`   | Teleoperator unique identifier |
| `speed_levels`        | list | `[0.010, 0.035]`       | Speed levels list              |
| `default_speed_index` | int  | `0`                    | Default speed index            |
| `initial_control_arm` | str  | `"left"`               | Initial control arm            |
| `toggle_arm_key`      | str  | `"o"`                  | Toggle control arm key         |
| `toggle_bimanual_key` | str  | `"0"`                  | Toggle dual-arm mode key       |
| `go_home_key`         | str  | `"h"`                  | Return to home position key    |
| `quit_key`            | str  | `"q"`                  | Quit key                       |
| `speed_up_key`        | str  | `"+"`                  | Speed up key                   |
| `speed_down_key`      | str  | `"-"`                  | Speed down key                 |

---

## 7. Data Flow Explained

### 7.1 Teleoperation Data Flow

```
Keyboard events → pynput/evdev listener → Event queue
                                    ↓
                        WalkerS2KeyboardTeleop._drain_pressed_keys()
                                    ↓
                        get_action_numpy(frame_id) → Frame gate check
                                    ↓
                        Queue snapshot + Real-time state → Key mapping → Speed scaling
                                    ↓
                        IK solver → Joint target positions
                                    ↓
                        RobotArticulation API → Isaac Sim execution
```

### 7.2 Inference/Replay Data Flow

```
Policy model / Dataset → Action dictionary → send_action(action_dict)
                                      ↓
                          _pending_absolute_action (atomic write)
                                      ↓
                          _robot_control_callback() consumes
                                      ↓
                          _hold_arm_positions update
                                      ↓
                          RobotArticulation API → Isaac Sim execution
```

---

## 8. Related Files

| File                                                              | Description                    |
| ----------------------------------------------------------------- | ------------------------------ |
| `src/lerobot/robots/walker_s2_sim/walkers2sim.py`               | Robot main implementation      |
| `src/lerobot/robots/walker_s2_sim/walkers2simConfig.py`         | Robot configuration            |
| `src/lerobot/teleoperators/walker_s2_keyboard/teleop.py`        | Keyboard teleop implementation |
| `src/lerobot/teleoperators/walker_s2_keyboard/teleop_config.py` | Keyboard teleop configuration  |
| `src/lerobot/robots/walker_s2_sim/isaac_sim_robot_interface.py` | Isaac Sim interface wrapper    |
| `src/lerobot/robots/walker_s2_sim/head_stereo_visualizer.py`    | Head camera visualizer         |
