# **Global Humanoid Robot Challenge 2026**架构文档

**English Version:** [Project_Framework.md](Project_Framework.md)

## 1. 系统概述

Global Humanoid Robot Challenge 2026 仿真器是基于 LeRobot 0.5.1 框架实现的人形机器人仿真平台，提供高保真物理仿真和多种控制模式。本文档详细说明控制系统的架构设计和实现细节。

---

## 2. 技术架构

### 2.1核心组件

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         LeRobot 0.5.1 Framework                          │
├───────────────────────────────────────┬──────────────────────────────────┤
│        Robot Base Class               │       Teleoperator Base Class    │
├───────────────────────────────────────┼──────────────────────────────────┤
│  WalkerS2sim                          │  WalkerS2KeyboardTeleop          │
│  - 20 维状态/动作空间                  │  - pynput/evdev 键盘后端          │
│  - 14 臂关节 + 4 手指 + 2 夹持器         │  - 单臂/双臂切换                    │
│  - 4 相机观测                          │  - 速度分级                        │
│  - Isaac Sim 物理引擎                  │  - 帧门控 + 队列合并防丢键          │
│  - IK 求解器                           │  - 回调模式支持                    │
│  - 回调驱动控制逻辑                    │                                  │
├───────────────────────────────────────┴──────────────────────────────────┤
│  Optional Modules:                                                       │
│  - ROS2 Teleop Subscriber                                                │
│  - Head Stereo Visualizer                                                │
└──────────────────────────────────────────────────────────────────────────┘
```

### 2.2 状态空间和动作空间

#### 2.2.1 状态维度 (20D)

```python
STATE_DIM = 20
STATE_NAMES = [
    # 14 臂关节 (7 左 + 7 右)
    "L_shoulder_pitch_joint.pos", "L_shoulder_roll_joint.pos", "L_shoulder_yaw_joint.pos",
    "L_elbow_roll_joint.pos", "L_elbow_yaw_joint.pos", "L_wrist_pitch_joint.pos", "L_wrist_roll_joint.pos",
    "R_shoulder_pitch_joint.pos", "R_shoulder_roll_joint.pos", "R_shoulder_yaw_joint.pos",
    "R_elbow_roll_joint.pos", "R_elbow_yaw_joint.pos", "R_wrist_pitch_joint.pos", "R_wrist_roll_joint.pos",
    # 4 手指关节 (2 左 + 2 右)
    "L_finger1_joint.pos", "L_finger2_joint.pos",
    "R_finger1_joint.pos", "R_finger2_joint.pos",
    # 2 夹持器控制指令 (二值化)
    "left_gripper",   # 1.0=close, -1.0=open
    "right_gripper",  # 1.0=close, -1.0=open
]
```

#### 2.2.2 观测格式

```python
observation = {
    "observation.state": torch.Tensor(shape=(20,)),  # 20 维关节状态
    "observation.images.head_left": torch.Tensor(shape=(3, H, W)),
    "observation.images.head_right": torch.Tensor(shape=(3, H, W)),
    "observation.images.wrist_left": torch.Tensor(shape=(3, H, W)),
    "observation.images.wrist_right": torch.Tensor(shape=(3, H, W)),
}
```

#### 2.2.3 动作格式

```python
action = {
    "L_shoulder_pitch_joint.pos": 0.1,
    # ... 13 个臂关节
    "L_finger1_joint.pos": 0.0,
    # ... 3 个手指关节
    "left_gripper": 1.0,   # 1.0=close, -1.0=open
    "right_gripper": -1.0,
}
```

---

## 3. 键盘控制实现

### 3.1 键盘监听器架构

Walker S2 键盘遥操作支持两种后端：

| 后端   | 适用场景        | 导入模块            |
| ------ | --------------- | ------------------- |
| pynput | 本地桌面环境    | `pynput.keyboard` |
| evdev  | Docker/远程桌面 | `evdev`           |

### 3.2 按键映射表

#### 3.2.1 末端执行器位移（按住持续移动）

| 按键  | 动作   | 说明                   |
| ----- | ------ | ---------------------- |
| `1` | y_up   | 末端 +Y 方向移动       |
| `3` | y_down | 末端 -Y 方向移动       |
| `4` | x_down | 末端 -X 方向移动       |
| `6` | x_up   | 末端 +X 方向移动       |
| `7` | z_up   | 末端 +Z 方向移动（上） |
| `9` | z_down | 末端 -Z 方向移动（下） |

#### 3.2.2 末端执行器旋转（按住持续旋转）

| 按键  | 动作    | 说明            |
| ----- | ------- | --------------- |
| `y` | ry_up   | 绕 Y 轴正向旋转 |
| `u` | ry_down | 绕 Y 轴负向旋转 |
| `v` | rx_up   | 绕 X 轴正向旋转 |
| `b` | rx_down | 绕 X 轴负向旋转 |
| `n` | rz_up   | 绕 Z 轴正向旋转 |
| `m` | rz_down | 绕 Z 轴负向旋转 |

#### 3.2.3 夹爪控制

| 按键  | 动作          | 说明     |
| ----- | ------------- | -------- |
| `k` | gripper_open  | 夹爪张开 |
| `l` | gripper_close | 夹爪关闭 |

#### 3.2.4 系统控制

| 按键          | 动作            | 说明                   |
| ------------- | --------------- | ---------------------- |
| `o`         | toggle_arm      | 切换控制臂（左 ↔ 右） |
| `0`         | toggle_bimanual | 切换单臂/双臂同步模式  |
| `h`         | go_home         | 切换到 home 位置       |
| `+` / `=` | speed_up        | 提升移动速度等级       |
| `-`         | speed_down      | 降低移动速度等级       |
| `q`         | quit            | 退出程序               |

### 3.3 速度分级

| 索引 | 速度 (m/step) | 说明         |
| ---- | ------------- | ------------ |
| 0    | 0.010         | 低速（默认） |
| 1    | 0.035         | 中速         |

**注意**: 当前版本只有两级速度，默认速度索引为 0（低速）。

### 3.4 帧门控控制逻辑

为防止同一帧重复处理和按键丢失，帧门控 + 队列合并机制在 **WalkerS2KeyboardTeleop** 中实现。

```python
# 在 teleop.get_action_numpy() 中
if frame_id != self._last_keyboard_frame_id:
    self._last_keyboard_frame_id = frame_id
  
    # 队列快照捕获短按 (press+release 发生在两帧之间)
    key_snapshot = {}
    while self._keyboard_cmd_queue:
        snap = self._keyboard_cmd_queue.popleft()
        for k, v in snap.items():
            if v:
                key_snapshot[k] = v
  
    # 实时状态捕获持续按住
    for k, v in self._pressed_keys.items():
        if v:
            key_snapshot[k] = v
  
    self._current_frame_keys = key_snapshot
```

**作用**:

1. 防止同一帧被重复处理（physics callback 在一次 world.step 内被调用多次）
2. 防止丢短按（队列捕获瞬时事件，实时状态捕获持续按住）

**架构说明**:

- WalkerS2sim 通过 `self._teleop.get_action_numpy(frame_id=...)` 获取键盘动作
- 帧门控逻辑在 teleop 内部处理，因为键盘监听器在 teleop 中
- 这种设计使得同一个 teleop 可以被多个机器人共享

---

## 4. 控制模式详解

### 4.1 回调驱动控制架构

Walker S2sim 采用**回调驱动**的控制架构，核心是 `_robot_control_callback` 方法，在每个物理步自动执行。

```python
def _robot_control_callback(self, step_size: float) -> None:
    """每个物理步自动执行：统一关节位置控制

    控制逻辑:
    1. 初始化：首次调用时快照当前关节状态作为保持目标
    2. 推理/回放模式：消费 _pending_absolute_action 更新保持目标
    3. 遥操作模式：调用 teleop.get_action_numpy() 获取键盘动作
    4. go_home 模式：检测 go_home 按键，触发插值回到初始位置
    5. 无输入：持续发出上一帧的保持目标
    """
```

### 4.2 四种控制模式

#### 4.2.1 遥操作模式 (Teleoperation)

**特征**: `send_action(None)`

**流程**:

1. callback 调用 `teleop.get_action_numpy(frame_id)` 获取键盘动作
2. 帧门控逻辑处理按键状态（防止丢键和重复处理）
3. IK 求解器计算目标关节位置
4. 更新 `_hold_arm_positions` 和 `_hold_finger_positions`
5. 发送到机器人执行

**代码路径**:

```
lerobot_teleoperate.py → teleop_loop() → robot.send_action(None)
    → WalkerS2sim.send_action() → 注册 callback
    → _robot_control_callback() → teleop.get_action_numpy()
```

#### 4.2.2 推理模式 (Inference)

**特征**: `send_action(action_dict)` 传入策略输出的动作字典

**流程**:

1. 策略模型输出动作字典
2. `send_action()` 将动作写入 `_pending_absolute_action`
3. callback 消费 pending action，更新保持目标
4. 直接发送到关节位置控制器

**代码路径**:

```
lerobot_record.py (with policy) → record_loop() → robot.send_action(action_dict)
    → WalkerS2sim.send_action() → _pending_absolute_action = action_array
    → _robot_control_callback() → 消费 pending action
```

#### 4.2.3 回放模式 (Replay)

**特征**: `send_action(action_dict)` 传入数据集记录的动作字典

**流程**:

1. 从数据集读取动作序列
2. 逐帧调用 `send_action()`
3. callback 消费动作，更新保持目标
4. 同时恢复环境物体位姿（如适用）

**代码路径**:

```
lerobot_replay.py → replay_loop() → robot.send_action(action_dict)
    → WalkerS2sim.send_action() → _pending_absolute_action = action_array
    → _robot_control_callback() → 消费 pending action
```

#### 4.2.4 go_home 模式

**特征**: 按下 `h` 键触发

**流程**:

1. callback 检测 `keyboard_state.get("go_home")` 按键边缘
2. 切换 `_go_home` 标志
3. 如触发，线性插值回到初始关节位置
4. 插值完成后自动恢复正常控制

**参数**:

- `_num_interpolation_steps`: 插值步数（默认 200 步）

---

## 5. 回调与遥操作的交互

### 5.1控制流图

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        Isaac Sim Physics Step                            │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                  WalkerS2sim._robot_control_callback()                   │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ 1. 检查 go_home 按键边缘触发                                        │  │
│  │ 2. 初始化保持目标（仅首次）                                        │  │
│  │ 3. 读取 pending action（推理/回放模式）                             │  │
│  │ 4. 调用 teleop.get_action_numpy()（遥操作模式）                    │  │
│  │ 5. 更新 _hold_arm_positions 和 _hold_finger_positions              │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                   WalkerS2KeyboardTeleop.get_action_numpy()              │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ 1. 帧门控检查：frame_id != last_keyboard_frame_id                  │  │
│  │ 2. 队列快照：清空 _keyboard_cmd_queue 捕获短按                     │  │
│  │ 3. 实时状态：合并 _pressed_keys 捕获持续按住                       │  │
│  │ 4. 速度分级：根据 speed_index 缩放动作幅度                         │  │
│  │ 5. 双臂镜像：如启用双臂模式，镜像到另一臂                          │  │
│  │ 6. 返回 (left_delta, right_delta, left_gripper, right_gripper)     │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                     Isaac Sim RobotArticulation API                      │
│  - control_dual_arm_ik()                                                 │
│  - set_joint_positions()                                                 │
└──────────────────────────────────────────────────────────────────────────┘
```

### 5.2 帧同步机制

**问题**: Isaac Sim 的物理回调频率 (200Hz) 高于渲染频率 (30Hz)，可能导致同一帧内 callback 被调用多次。

**解决方案**: 帧门控 ID 机制

```python
# 在 teleop.get_action_numpy(frame_id=step_idx) 中
if frame_id != self._last_keyboard_frame_id:
    # 新帧开始，处理按键快照
    self._last_keyboard_frame_id = frame_id
    # ... 处理逻辑
else:
    # 同一帧内的重复调用，返回缓存的动作
    return self._cached_action
```

### 5.3 防丢键机制

**问题**: 用户快速按下并释放按键（短按）可能发生在两帧之间，导致按键事件丢失。

**解决方案**: 队列 + 实时状态双重捕获

```python
# 队列捕获短按事件
while self._keyboard_cmd_queue:
    snap = self._keyboard_cmd_queue.popleft()
    for k, v in snap.items():
        if v:
            key_snapshot[k] = v

# 实时状态捕获持续按住
for k, v in self._pressed_keys.items():
    if v:
        key_snapshot[k] = v
```

---

## 6. 配置参数详解

### 6.1 机器人配置 (WalkerS2Config)

| 参数                     | 类型  | 默认值                                   | 说明                |
| ------------------------ | ----- | ---------------------------------------- | ------------------- |
| `type`                 | str   | `"walker_s2_sim"`                      | 机器人类型标识符    |
| `id`                   | str   | `"walker_s2_default"`                  | 机器人唯一标识      |
| `task_name`            | str   | `"Foam_Inlaying"`                      | 任务名称            |
| `task_cfg_path`        | str   | `"Ubtech_sim/config/Packing_Box.yaml"` | 任务配置文件路径    |
| `headless`             | bool  | `False`                                | 是否无头模式        |
| `sim_width`            | int   | `1280`                                 | 仿真窗口宽度        |
| `sim_height`           | int   | `720`                                  | 仿真窗口高度        |
| `physics_dt`           | float | `1/200`                                | 物理仿真步长        |
| `rendering_dt`         | float | `1/20`                                 | 渲染步长            |
| `speed_levels`         | list  | `[0.010, 0.035]`                       | 速度级别列表        |
| `default_speed_index`  | int   | `0`                                    | 默认速度索引        |
| `head_viz_enabled`     | bool  | `True`                                 | 启用头部相机可视化  |
| `head_viz_window_name` | str   | `"walker_s2_cameras"`                  | 可视化窗口名称      |
| `head_viz_scale`       | float | `1.0`                                  | 窗口缩放比例        |
| `head_viz_every_n`     | int   | `10`                                   | 每 N 帧更新一次显示 |
| `head_viz_window_x`    | int   | `40`                                   | 窗口 X 坐标         |
| `head_viz_window_y`    | int   | `40`                                   | 窗口 Y 坐标         |
| `head_viz_show_labels` | bool  | `True`                                 | 显示相机标签        |

### 6.2 键盘遥操作配置 (WalkerS2KeyboardTeleopConfig)

| 参数                    | 类型 | 默认值                   | 说明               |
| ----------------------- | ---- | ------------------------ | ------------------ |
| `type`                | str  | `"walker_s2_keyboard"` | 遥操作器类型       |
| `id`                  | str  | `"walker_s2_teleop"`   | 遥操作器唯一标识   |
| `speed_levels`        | list | `[0.010, 0.035]`       | 速度级别列表       |
| `default_speed_index` | int  | `0`                    | 默认速度索引       |
| `initial_control_arm` | str  | `"left"`               | 初始控制臂         |
| `toggle_arm_key`      | str  | `"o"`                  | 切换控制臂按键     |
| `toggle_bimanual_key` | str  | `"0"`                  | 切换双臂模式按键   |
| `go_home_key`         | str  | `"h"`                  | 回到 home 位置按键 |
| `quit_key`            | str  | `"q"`                  | 退出按键           |
| `speed_up_key`        | str  | `"+"`                  | 加速按键           |
| `speed_down_key`      | str  | `"-"`                  | 减速按键           |

---

## 7. 数据流详解

### 7.1 遥操作数据流

```
键盘事件 → pynput/evdev 监听器 → 事件队列
                                    ↓
                        WalkerS2KeyboardTeleop._drain_pressed_keys()
                                    ↓
                        get_action_numpy(frame_id) → 帧门控检查
                                    ↓
                        队列快照 + 实时状态 → 按键映射 → 速度缩放
                                    ↓
                        IK 求解器 → 关节目标位置
                                    ↓
                        RobotArticulation API → Isaac Sim 执行
```

### 7.2 推理/回放数据流

```
策略模型 / 数据集 → 动作字典 → send_action(action_dict)
                                      ↓
                          _pending_absolute_action (原子写入)
                                      ↓
                          _robot_control_callback() 消费
                                      ↓
                          _hold_arm_positions 更新
                                      ↓
                          RobotArticulation API → Isaac Sim 执行
```

## 8. 相关文件

| 文件                                                              | 说明               |
| ----------------------------------------------------------------- | ------------------ |
| `src/lerobot/robots/walker_s2_sim/walkers2sim.py`               | 机器人主实现       |
| `src/lerobot/robots/walker_s2_sim/walkers2simConfig.py`         | 机器人配置         |
| `src/lerobot/teleoperators/walker_s2_keyboard/teleop.py`        | 键盘遥操作实现     |
| `src/lerobot/teleoperators/walker_s2_keyboard/teleop_config.py` | 键盘遥操作配置     |
| `src/lerobot/robots/walker_s2_sim/isaac_sim_robot_interface.py` | Isaac Sim 接口封装 |
| `src/lerobot/robots/walker_s2_sim/head_stereo_visualizer.py`    | 头部相机可视化     |
