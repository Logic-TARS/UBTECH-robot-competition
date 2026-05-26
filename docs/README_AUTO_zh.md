# Global Humanoid Robot Challenge 2026 Baseline Lerobot-0.5.1

**English Version:** [README_V3.0.md](README_V3.0.md)

[![License](https://img.shields.io/badge/License-Apache_2.0-yellow.svg)](https://opensource.org/licenses/Apache-2.0)

全球人形机器人挑战赛 2026（Global Humanoid Robot Challenge 2026）官方基线代码仓库，基于 [LeRobot](https://github.com/huggingface/lerobot) 框架构建的人形机器人仿真平台，提供物理仿真、数据采集、模型训练到部署的完整工作流。

---

## 项目概述

本仓库面向 **全球人形机器人挑战赛 2026 (GHRC 2026)** 参赛者与研发团队，提供统一的基线实现：

- 基于 **NVIDIA Isaac Sim** 搭建高保真机器人仿真环境
- 通过键盘遥操作完成数据录制，输出标准化 **LeRobotDataset V2.1** 格式
- 基于模仿学习算法（ACT、Pi0 等）进行模型训练与微调
- 使用官方预训练权重快速复现与对比实验

---

## 核心能力

| 能力                     | 说明                                                                                                                 |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------- |
| 🤖**仿真环境**     | 基于 NVIDIA Isaac Sim 的高保真 Walker S2 机器人仿真，支持 20 维状态空间（14 臂关节 + 4 手指关节 + 2 夹持器控制指令） |
| 📊**数据采集**     | 支持键盘遥操作；输出**LeRobotDataset V2.1** 格式                                                               |
| 🧠**模型训练**     | 支持**ACT**、**Pi0** 等模仿学习算法                                                                      |
| 📦**预训练权重**   | 官方基线权重，可直接部署或微调                                                                                       |
| 🎥**四目实时显示** | 支持 4 个 RGB 相机实时预览（head_left, head_right, wrist_left, wrist_right）                                         |

---

## 资源说明

本项目部分大文件托管于 Hugging Face，首次使用前请先完成下载：

| 资源类别                | 本地目录                    | 远程地址                                                                                                    |
| ----------------------- | --------------------------- | ----------------------------------------------------------------------------------------------------------- |
| 🤖 仿真环境与机器人资产 | `assets/`（Git 子模块）   | [UBTECH-Robotics/challenge2026_assets](https://huggingface.co/UBTECH-Robotics/challenge2026_assets)            |
| 📊 训练数据集           | `datasets/`               | [UBTECH-Robotics/challenge2026_dataset](https://huggingface.co/datasets/UBTECH-Robotics/challenge2026_dataset) |
| 🏋️ 预训练模型权重     | `challenge2026_baseline/` | [UBTECH-Robotics/challenge2026_baseline](https://huggingface.co/UBTECH-Robotics/challenge2026_baseline)        |

### 快速下载

```bash
# 安装 huggingface-cli
pip install huggingface-hub

# 获取仿真资产（推荐使用 Git 子模块）
git submodule update --init --recursive

# 或手动下载到 ./assets
# huggingface-cli download UBTECH-Robotics/challenge2026_assets --local-dir ./assets --repo-type model

# 下载训练数据集
huggingface-cli download UBTECH-Robotics/challenge2026_dataset --local-dir ./datasets --repo-type dataset

# 下载预训练权重 未开放
huggingface-cli download UBTECH-Robotics/challenge2026_baseline --local-dir ./challenge2026_baseline --repo-type model
```

---

## 系统要求

### 基础环境

- NVIDIA GPU
- Docker
- NVIDIA Container Toolkit
- CUDA 12.8+
- Python 3.11+

### 推荐配置

- NVIDIA Isaac Sim 5.1.0+
- RTX 4090 或更高等级 GPU

---

## 构建环境

本仓库通过根目录下的 [Dockerfile](Dockerfile) 构建运行环境，基础镜像为 `nvcr.io/nvidia/isaac-sim:5.1.0`。镜像内会安装 Isaac Sim 所需的常用依赖，并将项目拷贝到容器中的 `/workspace/GlobalHumanoidRobotChallenge2026_Baseline`。

### 1. 构建前准备

- 已安装 Docker
- 已安装 NVIDIA Container Toolkit
- 主机可以正常使用 NVIDIA GPU
- 已获取本仓库的代码、`assets/` 子模块、`datasets/` 和 `challenge2026_baseline/` 等资源

### 2. 构建镜像

在项目根目录执行：

```bash
docker build -t ubtech:v0 .
```

如需指定其他镜像名，可以通过构建参数覆盖：

```bash
# 构建 Docker 镜像
# -t 镜像名:版本
# .  表示使用当前目录下的 Dockerfile
docker build \
    -t your-images-name:latest \
    .

```

## 查找键盘对应的 evdev 路径

使用键盘遥操作前，需要先确定键盘对应的 evdev 设备路径（`/dev/input/eventX`）。默认情况下，系统会自动遍历所有 `/dev/input/event*` 设备。

**方法一：通过设备 ID 查找（推荐）**

```bash
ls -la /dev/input/by-id/
# 找到包含 keyboard 字样的设备链接，例如：
# usb-046D_C328-if01-event-kbd -> /dev/input/event2
```

**方法二：查看所有输入设备**

```bash
cat /proc/bus/input/devices | grep -A 3 -i keyboard
# 在 handlers 行中查找 eventX
```

**方法三：使用 evtest 工具（交互式测试）**

```bash
apt install evtest
evtest
# 选择键盘对应的 event 设备，按下按键测试是否匹配
```

> ⚠️ 在 Docker 容器中运行时，需确保容器已正确挂载输入设备。

## 快速开始

### 1. 启动运行环境

本项目使用 Docker 容器化部署，从项目根目录启动：

```bash
chmod +x run.sh
sudo ./run.sh
```

#### 可自定义环境变量

| 环境变量                | 说明                 | 默认值                                                   |
| ----------------------- | -------------------- | -------------------------------------------------------- |
| `IMAGE_NAME`          | Docker 镜像名称      | `ubtech:v0 `                                           |
| `CONTAINER_NAME`      | 容器名称             | `isaac_sim_lerobot`                                    |
| `HOST_WORKSPACE`      | 主机项目目录路径     | `run.sh` 所在目录                                      |
| `CONTAINER_WORKSPACE` | 容器内工作目录路径   | `/workspace/GlobalHumanoidRobotChallenge2026_Baseline` |
| `SHM_SIZE`            | 共享内存大小         | `8g`                                                   |
| `ISAAC_CACHE_ROOT`    | Isaac Sim 缓存目录   | `${HOME}/.cache/isaac_sim_container`                   |
| `HF_CACHE`            | HuggingFace 缓存目录 | `${HOME}/.cache/huggingface`                           |
| `HEADLESS`            | 是否启用无头模式     | `0`（否）                                              |

#### 使用示例

```bash
# 基本启动
./run.sh

# 无头模式（远程服务器）
./run.sh --headless

# 自定义镜像名
IMAGE_NAME=my_custom_image:v1 ./run.sh

# 自定义挂载路径
HOST_WORKSPACE=/my/project/path ./run.sh
```

> ⚠️ 首次运行前请确保已完成 Docker、NVIDIA Container Toolkit 安装。

---

## 功能模块

### 2. 遥操作 (Teleoperate)

使用键盘控制 Walker S2 机器人进行遥操作：

```bash
# task1
/isaac-sim/python.sh src/lerobot/scripts/lerobot_teleoperate.py \
    --robot.type=walker_s2_sim \
    --robot.headless=false \
    --task=Part_Sorting \
    --teleop.type=walker_s2_keyboard \
    --teleop.evdev_device_path=/dev/input/event4 \
    --display_data=false

# task2
/isaac-sim/python.sh src/lerobot/scripts/lerobot_teleoperate.py \
    --robot.type=walker_s2_sim \
    --robot.headless=false \
    --task=Conveyor_Sorting \
    --teleop.type=walker_s2_keyboard \
    --display_data=false
  
# task3
/isaac-sim/python.sh src/lerobot/scripts/lerobot_teleoperate.py \
    --robot.type=walker_s2_sim \
    --robot.headless=false \
    --task=Foam_Inlaying \
    --teleop.type=walker_s2_keyboard \
    --teleop.evdev_device_path=/dev/input/event2 \
    --display_data=false
  
# task4
/isaac-sim/python.sh src/lerobot/scripts/lerobot_teleoperate.py \
    --robot.type=walker_s2_sim \
    --robot.headless=false \
    --task=Packing_Box \
    --teleop.type=walker_s2_keyboard \
    --teleop.evdev_device_path=/dev/input/event4 \
    --display_data=false

```

| 参数                           | 说明                                                                   | 默认值                   |
| ------------------------------ | ---------------------------------------------------------------------- | ------------------------ |
| `--robot.type`               | 机器人类型                                                             | `walker_s2_sim`        |
| `--robot.headless`           | 是否无头模式                                                           | `false`                |
| `--task`                     | 任务名称（Part_Sorting, Conveyor_Sorting, Foam_Inlaying, Packing_Box） | `Foam_Inlaying`        |
| `--teleop.type`              | 遥操作设备类型                                                         | `walker_s2_keyboard`   |
| `--teleop.evdev_device_path` | 键盘 evdev 设备路径                                                    | `自动遍历（推荐指定）` |
| `--display_data`             | 是否显示相机画面                                                       | `false`                |

#### 键盘映射

**末端执行器位移（按住持续移动）**

| 按键  | 动作                   |
| ----- | ---------------------- |
| `1` | 末端 +Y 方向移动       |
| `3` | 末端 -Y 方向移动       |
| `4` | 末端 -X 方向移动      |
| `6` | 末端 +X 方向移动      |
| `7` | 末端 +Z 方向移动（上） |
| `9` | 末端 -Z 方向移动（下） |

**末端执行器旋转（按住持续旋转）**

| 按键  | 动作             |
| ----- | ---------------- |
| `y` | 绕 Y 轴正向旋转  |
| `u` | 绕 Y 轴负向旋转  |
| `v` | 绕 X 轴正向旋转 |
| `b` | 绕 X 轴负向旋转 |
| `n` | 绕 Z 轴正向旋转  |
| `m` | 绕 Z 轴负向旋转  |

**夹爪控制**

| 按键  | 动作     |
| ----- | -------- |
| `k` | 夹爪张开 |
| `l` | 夹爪关闭 |

**系统控制**

| 按键          | 动作                        |
| ------------- | --------------------------- |
| `o`         | 切换控制臂（左 ↔ 右）      |
| `0`         | 切换单臂 / 双臂同步控制模式 |
| `h`         | 切换到 home 位置            |
| `+` / `=` | 提升移动速度等级            |
| `-`         | 降低移动速度等级            |
| `q`         | 退出遥操作                  |

#### 速度分级

| 索引 | 速度 (m/step) | 说明         |
| ---- | ------------- | ------------ |
| 0    | 0.010         | 低速（默认） |
| 1    | 0.035         | 中速         |

---

### 3. 数据采集 (Record)

通过键盘遥操作录制人类示教数据：

```bash

# task1
/isaac-sim/python.sh src/lerobot/scripts/lerobot_record.py \
    --robot.type=walker_s2_sim \
    --robot.headless=false \
    --task=Part_Sorting \
    --teleop.type=walker_s2_keyboard \
    --teleop.evdev_device_path=/dev/input/event2 \
    --dataset.repo_id=your_org/Part_Sorting \
    --dataset.root=datasets/Part_Sorting/record/v0 \
    --dataset.num_episodes=10 \
    --dataset.single_task="Part Sorting" \
    --dataset.video=true \
    --dataset.fps=30 \
    --dataset.episode_time_s=1000000 \
    --dataset.push_to_hub=false \
    --play_sounds=false
  
# task2
/isaac-sim/python.sh src/lerobot/scripts/lerobot_record.py \
    --robot.type=walker_s2_sim \
    --robot.headless=false \
    --task=Conveyor_Sorting \
    --teleop.type=walker_s2_keyboard \
    --teleop.evdev_device_path=/dev/input/event2 \
    --dataset.repo_id=your_org/Conveyor_Sorting \
    --dataset.root=datasets/Conveyor_Sorting/record/v0 \
    --dataset.num_episodes=10 \
    --dataset.single_task="Conveyor Sorting" \
    --dataset.video=true \
    --dataset.fps=30 \
    --dataset.episode_time_s=1000000 \
    --dataset.push_to_hub=false \
    --play_sounds=false
  
# task3
/isaac-sim/python.sh src/lerobot/scripts/lerobot_record.py \
    --robot.type=walker_s2_sim \
    --robot.headless=false \
    --task=Foam_Inlaying \
    --teleop.type=walker_s2_keyboard \
    --teleop.evdev_device_path=/dev/input/event2 \
    --dataset.repo_id=your_org/Foam_Inlaying \
    --dataset.root=datasets/Foam_Inlaying/record/v0 \
    --dataset.num_episodes=10 \
    --dataset.single_task="Foam Inlaying" \
    --dataset.video=true \
    --dataset.fps=30 \
    --dataset.episode_time_s=1000000 \
    --dataset.push_to_hub=false \
    --play_sounds=false

# task4
/isaac-sim/python.sh src/lerobot/scripts/lerobot_record.py \
    --robot.type=walker_s2_sim \
    --robot.headless=false \
    --task=Packing_Box \
    --teleop.type=walker_s2_keyboard \
    --teleop.evdev_device_path=/dev/input/event4 \
    --dataset.repo_id=your_org/Packing_Box \
    --dataset.root=datasets/Packing_Box/record/v0 \
    --dataset.num_episodes=10 \
    --dataset.single_task="Packing_Box" \
    --dataset.video=true \
    --dataset.fps=30 \
    --dataset.episode_time_s=1000000 \
    --dataset.push_to_hub=false \
    --play_sounds=false
```

| 参数                           | 说明                           | 默认值 / 备注            |
| ------------------------------ | ------------------------------ | ------------------------ |
| `--robot.type`               | 机器人类型                     | `walker_s2_sim`        |
| `--robot.headless`           | 是否无头模式                   | `false`                |
| `--task`                     | 任务名称                       | `Foam_Inlaying`        |
| `--teleop.type`              | 遥操作设备类型                 | `walker_s2_keyboard`   |
| `--teleop.evdev_device_path` | 键盘 evdev 设备路径            | `自动遍历（推荐指定）` |
| `--dataset.repo_id`          | 数据集 ID（Hugging Face 格式） | `必填`                 |
| `--dataset.root`             | 本地保存路径（替代 repo_id）   | `None`                 |
| `--dataset.num_episodes`     | 录制 episode 数量              | `50`                   |
| `--dataset.single_task`      | 任务描述                       | `必填`                 |
| `--dataset.video`            | 是否录制视频                   | `true`                 |
| `--dataset.fps`              | 帧率                           | `30`                   |
| `--dataset.episode_time_s`   | 每集录制时长（秒）             | `60`                   |
| `--dataset.push_to_hub`      | 是否上传到 Hugging Face        | `false`                |
| `--play_sounds`              | 是否播放提示音                 | `false`                |

> ⚠️ `play_sounds`参数必须false，镜像中没有安装语音播放依赖

#### 数据集结构

```
datasets/packing_box/
├── data
│   └── chunk-000
│       └── file-000.parquet
├── meta
│   ├── episodes
│   │   └── chunk-000
│   │       └── file-000.parquet
│   ├── info.json
│   ├── stats.json
│   └── tasks.parquet
└── videos
    ├── observation.images.head_left
    │   └── chunk-000
    │       └── file-000.mp4
    ├── observation.images.head_right
    │   └── chunk-000
    │       └── file-000.mp4
    ├── observation.images.wrist_left
    │   └── chunk-000
    │       └── file-000.mp4
    └── observation.images.wrist_right
        └── chunk-000
            └── file-000.mp4
```

---

### 4. 自动数采 (Auto-Collect)

编程式自动数据采集，无需键盘遥操作，机器人自主完成零件抓取-放置流水线并录制数据。

#### 架构说明

自动数采基于**模板方法模式**实现，代码位于 `src/lerobot/auto_collect/`：

```
AutoCollectBase（基类）
├── [通用机器人控制]
│   ├── gradually_move_gripper()        # 逐步移动夹爪（单臂/双臂）
│   ├── move_gripper()                  # 关节插值移动夹爪（单臂/双臂）
│   ├── _joint_interpolate_to_pose()    # 关节空间插值移动手臂（单臂/双臂）
│   └── _cartesian_interpolate_to_pose() # 笛卡尔空间插值 + 逐帧 IK（单臂/双臂）
├── [共享辅助]
│   ├── _build_dataset()                # 构建 LeRobotDataset
│   ├── _connect_and_settle()           # 连接机器人 + 物理稳定
│   ├── _build_action_dict()            # 从机器人状态构建动作字典
│   ├── _record_frame()                 # 录制单帧
│   ├── _check_grasp_success_for_arm()  # 检查指定手臂是否抓取成功
│   ├── _group_parts_by_arm()           # 按手臂侧分组零件
│   └── get_arm_side()                  # 返回零件对应的手臂侧
├── run()                               # Episode 循环 + 数据集管理
└── [抽象接口 — 子类必须实现]
    ├── compute_grasp_poses()           # 计算抓取位姿
    ├── check_grasp_success()           # 判断抓取是否成功
    ├── get_place_pose()                # 计算放置目标位姿
    └── _execute_sequence()             # 执行完整抓取-放置流水线

TaskPartSorting / TaskConveyorSorting / TaskFoamInlaying / TaskPackingBox（全部继承 AutoCollectBase）
```

**双臂控制通过 `is_dual_arm` 和 `arm_execution_mode` 类属性控制：** 基类默认 `is_dual_arm = False`（单臂模式），子类覆盖为 `True` 即可启用双臂 episode 执行。各任务子类通过实现 `_execute_sequence()` 定义具体的单臂/双臂抓取-放置流水线。

| 任务                      | 子类                    | `is_dual_arm` | 手臂策略     | 核心差异                                                                  |
| ------------------------- | ----------------------- | --------------- | ------------ | ------------------------------------------------------------------------- |
| Task 1 - Part_Sorting     | `TaskPartSorting`     | `False`       | 右手单臂     | 按 A/B 类型偏移放入箱子                                                   |
| Task 2 - Conveyor_Sorting | `TaskConveyorSorting` | `False`       | 右手单臂     | 实时读取传送带零件位置，处理 8 个零件直到完成或超时                       |
| Task 3 - Foam_Inlaying    | `TaskFoamInlaying`    | `True`        | 左右双臂同时 | 小工件→左臂→小孔，大工件→右臂→大孔                                    |
| Task 4 - Packing_Box      | `TaskPackingBox`      | —              | 双臂 replay  | 继承 AutoCollectBase，从已有数据集回放 action，映射 18→20 维后录制新数据 |

#### 使用方法

```bash
# Task 1 - Part Sorting
/isaac-sim/python.sh -m lerobot.scripts.auto_collect_main \
    --robot.type=walker_s2_sim \
    --auto_collect.task=Part_Sorting \
    --auto_collect.repo_id=sjj/Part_Sorting_auto \
    --auto_collect.root=datasets/Part_Sorting/auto/test \
    --auto_collect.num_episodes=1 \
    --auto_collect.single_task="Part Sorting" \
    --auto_collect.record_data=true \
    --auto_collect.video=true \
    --auto_collect.fps=30

# Task 2 - Conveyor Sorting（单臂自动分拣）
# 每个 episode 处理 8 个传送带零件，直到全部完成或 Conveyor_Sorting.yaml 的 timelimit 超时
/isaac-sim/python.sh -m lerobot.scripts.auto_collect_main \
    --robot.type=walker_s2_sim \
    --auto_collect.task=Conveyor_Sorting \
    --auto_collect.repo_id=sjj/Conveyor_Sorting_auto \
    --auto_collect.root=datasets/Conveyor_Sorting/auto/episode_250_v1 \
    --auto_collect.num_episodes=250 \
    --auto_collect.single_task="Conveyor Sorting" \
    --auto_collect.record_data=true \
    --auto_collect.video=true \
    --auto_collect.fps=30


/isaac-sim/python.sh -m lerobot.scripts.auto_collect_main \
    --robot.type=walker_s2_sim \
    --auto_collect.task=Conveyor_Sorting \
    --auto_collect.repo_id=sjj/Conveyor_Sorting_auto \
    --auto_collect.root=datasets/Conveyor_Sorting/auto/episode_250_v2 \
    --auto_collect.num_episodes=250 \
    --auto_collect.single_task="Conveyor Sorting" \
    --auto_collect.record_data=true \
    --auto_collect.video=true \
    --auto_collect.fps=30

/isaac-sim/python.sh -m lerobot.scripts.auto_collect_main \
    --robot.type=walker_s2_sim \
    --auto_collect.task=Conveyor_Sorting \
    --auto_collect.repo_id=sjj/Conveyor_Sorting_auto \
    --auto_collect.root=datasets/Conveyor_Sorting/auto/episode_250_v3 \
    --auto_collect.num_episodes=250 \
    --auto_collect.single_task="Conveyor Sorting" \
    --auto_collect.record_data=true \
    --auto_collect.video=true \
    --auto_collect.fps=30


/isaac-sim/python.sh -m lerobot.scripts.auto_collect_main \
    --robot.type=walker_s2_sim \
    --auto_collect.task=Conveyor_Sorting \
    --auto_collect.repo_id=sjj/Conveyor_Sorting_auto \
    --auto_collect.root=datasets/Conveyor_Sorting/auto/episode_250_v4 \
    --auto_collect.num_episodes=250 \
    --auto_collect.single_task="Conveyor Sorting" \
    --auto_collect.record_data=true \
    --auto_collect.video=true \
    --auto_collect.fps=30

# Task 3 - Foam Inlaying
/isaac-sim/python.sh -m lerobot.scripts.auto_collect_main \
    --robot.type=walker_s2_sim \
    --auto_collect.task=Foam_Inlaying \
    --auto_collect.repo_id=sjj/Foam_Inlaying_auto \
    --auto_collect.root=datasets/Foam_Inlaying/auto/v0 \
    --auto_collect.num_episodes=2 \
    --auto_collect.single_task="Foam Inlaying" \
    --auto_collect.record_data=true \
    --auto_collect.video=true \
    --auto_collect.fps=30 \
    --auto_collect.vcodec=h264 \
    --auto_collect.arm_execution_mode=right_then_left

# Task 4 - Packing_Box（replay 回放式自动数采）
# 原理：从已有数据集中读取指定 episode 的 action，映射键名（18D→20D）后回放到机器人
# 每 replay 一次源 episode 生成一条采集 episode，通过 num_episodes 控制采集数量
/isaac-sim/python.sh -m lerobot.scripts.auto_collect_main \
  --robot.type=walker_s2_sim \
  --auto_collect.task=Packing_Box \
  --auto_collect.repo_id=sjj/Packing_Box_auto \
  --auto_collect.root=datasets/Packing_Box/auto/episode_1000 \
  --auto_collect.num_episodes=1000 \
  --auto_collect.single_task="Packing Box" \
  --auto_collect.record_data=true \
  --auto_collect.video=true \
  --auto_collect.fps=30 \
  --auto_collect.source_repo_id=packing_box_episode_50 \
  --auto_collect.source_root=datasets/Packing_Box/packing_box_episode_50 \
  --auto_collect.source_episode=21 \
  --auto_collect.source_step_interval=5
```

> **Task 2 (Conveyor_Sorting) 说明：** 该任务使用简化的单臂自动数采逻辑，不导入参考 FSM 文件。程序每轮实时查询传送带零件世界坐标，用固定 RPY 和实时 xyz 生成抓取位姿；`part_a` 放入右侧箱，`part_b` 放入左侧箱。每个 episode 默认处理 8 个零件，若超过 `Ubtech_sim/config/Conveyor_Sorting.yaml` 中的 `timelimit` 仍未完成，则当前 episode 失败并按 `--auto_collect.max_retries` 重试。

> **Task 4 (Packing_Box) 说明：** 与其他任务不同，Packing_Box 采用 replay 回放模式而非 IK 规划模式。通过 `--auto_collect.source_repo_id` 和 `--auto_collect.source_root` 指定源数据集路径，`--auto_collect.source_episode` 指定要回放的源 episode 索引。`--auto_collect.num_episodes` 控制 replay 次数（每次 reset 后重放同一源 episode 并录制一条新 episode）。任务将 18 维动作（14 臂关节 + 4 手指关节）映射为 20 维（增加 `left_gripper`/`right_gripper` 默认值 0）。`source_step_interval` 控制帧采样密度，`1` 为逐帧，`2` 为隔一帧取一帧。

#### 参数说明

| 参数                                                   | 说明                                                 | 默认值                     |
| ------------------------------------------------------ | ---------------------------------------------------- | -------------------------- |
| `--auto_collect.task`                                | 任务名称                                             | `Part_Sorting`           |
| `--auto_collect.repo_id`                             | 数据集 ID（HF 格式）                                 | 必填                       |
| `--auto_collect.root`                                | 数据集本地存储路径                                   | `./outputs/auto_collect` |
| `--auto_collect.num_episodes`                        | 录制 episode 数量                                    | `1`                      |
| `--auto_collect.fps`                                 | 控制频率 (Hz)                                        | `30`                     |
| `--auto_collect.record_data`                         | 是否录制数据                                         | `true`                   |
| `--auto_collect.video`                               | 是否录制视频                                         | `true`                   |
| `--auto_collect.single_task`                         | 任务描述（不填则自动使用 task 名）                   | None                       |
| `--auto_collect.max_retries`                         | 单 episode 抓取失败最大重试次数                      | `10`                     |
| `--auto_collect.objects_per_episode`                 | 每 episode 最大物体数（0=全部）                      | `0`                      |
| `--auto_collect.push_to_hub`                         | 采集完成后是否推送到 HF Hub                          | `false`                  |
| `--auto_collect.vcodec`                              | 视频编码器（h264/auto/libsvtav1）                    | `h264`                   |
| `--auto_collect.video_encoding_batch_size`           | 批量编码前的 episode 数                              | `1`                      |
| `--auto_collect.streaming_encoding`                  | 是否启用流式编码                                     | `false`                  |
| `--auto_collect.encoder_queue_maxsize`               | 流式编码每相机帧缓冲上限                             | `30`                     |
| `--auto_collect.encoder_threads`                     | 编码器线程数（None=自动）                            | `None`                   |
| `--auto_collect.arm_execution_mode`                  | 双臂执行模式（dual/left_then_right/right_then_left） | `dual`                   |
| `--auto_collect.num_image_writer_processes`          | 写入 PNG 的子进程数                                  | `8`                      |
| `--auto_collect.num_image_writer_threads_per_camera` | 每相机写入线程数                                     | `4`                      |
| `--auto_collect.source_repo_id`                      | **（replay）** 源数据集标识                    | `packing_box_episode_50` |
| `--auto_collect.source_root`                         | **（replay）** 源数据集根目录                  | `datasets/Packing_Box`   |
| `--auto_collect.source_episode`                      | **（replay）** 源 episode 索引                 | `0`                      |
| `--auto_collect.source_step_interval`                | **（replay）** 帧采样间隔（每隔N帧取1帧）      | `1`                      |

#### 采集流程

1. 连接机器人并加载任务场景
2. 等待物理引擎稳定
3. 每 episode：
   - 松开双臂夹爪 → 重置场景（零件随机化）
   - 根据任务子类的 `is_dual_arm` 标志选择执行策略：
     - **单臂模式**（`is_dual_arm=False`）：随机打乱零件 → 逐个执行单臂抓取-放置流水线
     - **双臂模式**（`is_dual_arm=True`）：随机打乱零件 → 按左右臂分组配对 → 双臂同时执行抓取-放置流水线，任一手臂失败即重试
   - 零件抓取失败 → 重新开始当前 episode（最多重试 `max_retries` 次）
   - 所有零件成功 → `dataset.save_episode()`
   - **replay 模式**（Packing_Box）：加载源数据集指定 episode → 每次 reset 后逐帧读取 action → 映射键名（18D→20D）→ `send_action` 回放 → 录制帧 → `dataset.save_episode()`，重复 `num_episodes` 次
4. 完成后可选推送至 Hugging Face Hub

#### 扩展新任务

1. 在 `auto_collect/` 下创建新子类，继承 `AutoCollectBase`
2. 实现 4 个抽象方法：`compute_grasp_poses`、`check_grasp_success`、`get_place_pose`、`_execute_sequence`
3. 双臂任务设置 `is_dual_arm = True`，可选覆盖 `get_arm_side(part)`（默认右手）和 `_on_episode_start()`
4. 在 `auto_collect_main.py` 的 `_COLLECTOR_REGISTRY` 中注册

```python
class TaskNewExample(AutoCollectBase):
    # 双臂任务
    is_dual_arm = True

    def get_arm_side(self, part):
        return "left" if part["type"] == "small" else "right"

    def compute_grasp_poses(self, part):
        # 返回 {"left": {stages}, "right": {stages}}
        return {
            side: {
                "approach": {"position": ..., "rotation": ...},
                "descend": {"position": ..., "rotation": ...},
                "grasp": {"position": ..., "rotation": ...},
                "lift": {"position": ..., "rotation": ...},
            }
            for side in ("left", "right")
        }

    def check_grasp_success(self, robot, part):
        return self._check_grasp_success_for_arm(robot, part, "right")

    def get_place_pose(self, robot, part, box_pos):
        return {"right": {"position": box_pos, "rotation": ...}}

    def _execute_sequence(self, robot, parts, box_pos, dt, dataset, single_task, objects_per_episode):
        # 实现具体抓取-放置流水线，调用 _joint_interpolate_to_pose / gradually_move_gripper 等基类方法
        ...

# 注册
_COLLECTOR_REGISTRY["New_Task"] = TaskNewExample
```

---

回放已录制的数据集进行验证：

```bash
# task1
/isaac-sim/python.sh src/lerobot/scripts/lerobot_replay.py \
    --robot.type=walker_s2_sim \
    --robot.headless=false \
    --task=Part_Sorting \
    --dataset.repo_id=your_org/your_dataset \
    --dataset.root=datasets/Part_Sorting/record/v0 \
    --dataset.episode=0 \
    --play_sounds=false
  
# task2
/isaac-sim/python.sh src/lerobot/scripts/lerobot_replay.py \
    --robot.type=walker_s2_sim \
    --robot.headless=false \
    --task=Conveyor_Sorting \
    --dataset.repo_id=your_org/your_dataset \
    --dataset.root=datasets/Conveyor_Sorting/record/v0 \
    --dataset.episode=0 \
    --play_sounds=false
  
# task3
/isaac-sim/python.sh src/lerobot/scripts/lerobot_replay.py \
    --robot.type=walker_s2_sim \
    --robot.headless=false \
    --task=Foam_Inlaying \
    --dataset.repo_id=your_org/your_dataset \
    --dataset.root=datasets/Foam_Inlaying/record/v0 \
    --dataset.episode=0 \
    --play_sounds=false
  
# task4
/isaac-sim/python.sh src/lerobot/scripts/lerobot_replay.py \
    --robot.type=walker_s2_sim \
    --robot.headless=false \
    --task=Packing_Box \
    --dataset.repo_id=your_org/your_dataset \
    --dataset.root=datasets/Packing_Box/record/v0 \
    --dataset.episode=0 \
    --play_sounds=false
```

| 参数                  | 说明                               | 默认值 / 备注     |
| --------------------- | ---------------------------------- | ----------------- |
| `--robot.type`      | 机器人类型                         | `walker_s2_sim` |
| `--task`            | 任务名称（必须与录制时一致）       | `Foam_Inlaying` |
| `--dataset.repo_id` | 数据集来源                         | 必填              |
| `--dataset.root`    | 本地数据集路径（替代 repo_id）     | None              |
| `--dataset.episode` | 要回放的 episode 索引（从 0 开始） | 必填              |
| `--play_sounds`     | 是否播放提示音                     | `false`         |

> ⚠️ `play_sounds`参数必须false，镜像中没有安装语音播放依赖

#### 环境状态恢复机制

回放时，系统会自动恢复数据集中的环境物体位姿到仿真场景中：

1. **数据来源**: `observation.state` 列包含机器人状态（前 20 维）和环境物体位姿（后续维度）
2. **恢复时机**: 在 `robot.connect()` 之后、开始回放之前
3. **恢复流程**:
   - 从首帧提取环境物体位姿（跳过前 20 维机器人状态）
   - 调用 `robot.set_environment_state()` 恢复物体位姿
   - 推进物理仿真 50 步让物体稳定

**环境状态维度计算**:

| 任务             | 维度计算公式                    | 说明       |
| ---------------- | ------------------------------- | ---------- |
| Part_Sorting     | `num_parts × 2 × 7`         | 2 类零件   |
| Conveyor_Sorting | `num_parts × 2 × 7`         | 2 类零件   |
| Packing_Box      | `num_boxes × num_parts × 7` | 多个箱子   |
| Foam_Inlaying    | `0`                           | 无追踪物体 |

每个物体 7 维：`[x, y, z, qx, qy, qz, qw]`

### 5. 模型训练

#### ACT

以下是针对 Task 4 使用 **ACT** 策略、附带完整超参数的训练示例：

```bash

# 简洁训练命令
/isaac-sim/python.sh src/lerobot/scripts/lerobot_train.py \
    --dataset.repo_id=your_name/task_name \
    --dataset.video_backend=pyav \
    --policy.type=act \
    --output_dir=your_save_dir \
    --dataset.root=local_dataset_dir \
    --job_name=Foam_Inlaying \
    --policy.device=cuda \
    --wandb.enable=false \
    --policy.repo_id=none \
    --policy.push_to_hub=false 

# 多卡训练命令
/isaac-sim/python.sh -m accelerate.commands.launch \
    --num_processes=4 \
    $PWD/src/lerobot/scripts/lerobot_train.py \
    --dataset.repo_id=sjj/test \
    --dataset.root=datasets/Part_Sorting/Part_Sorting_fix \
    --policy.type=act \
    --policy.device=cuda \
    --policy.repo_id=none \
    --policy.push_to_hub=false \
    --output_dir=challenge2026_baseline/Part_Sorting/act/train_5_5 \
    --job_name=Part_Sorting \
    --wandb.enable=false \
    --batch_size=12 \
    --steps=100000


# 详细训练命令 task3
/isaac-sim/python.sh src/lerobot/scripts/lerobot_train.py \
  --dataset.repo_id=sjj/Part_Sorting \
  --dataset.root=datasets/Part_Sorting/test3 \
  --dataset.video_backend=pyav \
  --policy.type=act \
  --policy.n_obs_steps=1 \
  --policy.chunk_size=50 \
  --policy.n_action_steps=50 \
  --policy.vision_backbone=resnet18 \
  --policy.pretrained_backbone_weights=ResNet18_Weights.IMAGENET1K_V1 \
  --policy.dim_model=256 \
  --policy.n_heads=4 \
  --policy.dim_feedforward=1024 \
  --policy.n_encoder_layers=4 \
  --policy.n_decoder_layers=1 \
  --policy.use_vae=true \
  --policy.latent_dim=32 \
  --policy.n_vae_encoder_layers=4 \
  --policy.dropout=0.1 \
  --policy.kl_weight=10.0 \
  --policy.optimizer_lr=1e-5 \
  --policy.optimizer_weight_decay=1e-4 \
  --policy.optimizer_lr_backbone=1e-5 \
  --policy.device=cuda \
  --policy.use_amp=true \
  --policy.push_to_hub=false \
  --output_dir=challenge2026_baseline/Part_Sorting/act/test \
  --job_name=task4_act \
  --resume=false \
  --seed=1000 \
  --num_workers=8 \
  --batch_size=8 \
  --steps=1\
  --eval_freq=0 \
  --log_freq=200 \
  --save_checkpoint=true \
  --save_freq=5000 \
  --wandb.entity=your_wandb_entity
```

> 请将 `your_org/Packing_Box_dataset` 替换为您自己的数据集 repo ID，将 `your_wandb_entity` 替换为您的 WandB 用户名或团队名。若不使用 WandB，可删除 `--wandb.entity` 参数。

**数据集与输出参数**

| 参数                | 说明                                   | 默认值 / 备注 |
| ------------------- | -------------------------------------- | ------------- |
| `dataset.repo_id` | 数据集 ID（Hugging Face 或本地组织名） | 必填          |
| `dataset.root`    | 数据集本地根路径                       | 必填          |
| `output_dir`      | 检查点与日志保存目录                   | 必填          |
| `job_name`        | 任务标识（显示在日志 / WandB 中）      | 可选          |
| `resume`          | 是否从上次检查点续训                   | `false`     |
| `seed`            | 全局随机种子                           | `1000`      |

**训练循环参数**

| 参数                | 说明                       | 默认值 / 备注 |
| ------------------- | -------------------------- | ------------- |
| `steps`           | 总训练步数                 | `100000`    |
| `batch_size`      | 每步样本数                 | `8`         |
| `num_workers`     | DataLoader 工作进程数      | `8`         |
| `eval_freq`       | 评估间隔步数（0 表示禁用） | `0`         |
| `log_freq`        | 日志打印间隔步数           | `200`       |
| `save_checkpoint` | 是否保存检查点             | `true`      |
| `save_freq`       | 检查点保存间隔步数         | `5000`      |

**ACT 策略参数**

| 参数                                   | 说明                   | 默认值 / 备注                      |
| -------------------------------------- | ---------------------- | ---------------------------------- |
| `policy.type`                        | 策略算法类型           | `act` / `pi0`                  |
| `policy.device`                      | 运行设备               | `cuda` / `cpu`                 |
| `policy.use_amp`                     | 是否开启混合精度训练   | `true`                           |
| `policy.n_obs_steps`                 | 观测步数               | `1`                              |
| `policy.chunk_size`                  | 动作块长度             | `50`                             |
| `policy.n_action_steps`              | 每次推理执行的动作步数 | `50`                             |
| `policy.vision_backbone`             | 视觉编码器架构         | `resnet18`                       |
| `policy.pretrained_backbone_weights` | 主干网络预训练权重     | `ResNet18_Weights.IMAGENET1K_V1` |
| `policy.dim_model`                   | Transformer 模型维度   | `256`                            |
| `policy.n_heads`                     | 注意力头数             | `4`                              |
| `policy.dim_feedforward`             | 前馈网络维度           | `1024`                           |
| `policy.n_encoder_layers`            | 编码器层数             | `4`                              |
| `policy.n_decoder_layers`            | 解码器层数             | `1`                              |
| `policy.use_vae`                     | 是否启用 VAE 隐空间    | `true`                           |
| `policy.latent_dim`                  | VAE 隐变量维度         | `32`                             |
| `policy.n_vae_encoder_layers`        | VAE 编码器层数         | `4`                              |
| `policy.dropout`                     | Dropout 比率           | `0.1`                            |
| `policy.kl_weight`                   | KL 散度损失权重        | `10.0`                           |
| `policy.optimizer_lr`                | 主网络学习率           | `1e-5`                           |
| `policy.optimizer_weight_decay`      | 权重衰减               | `1e-4`                           |
| `policy.optimizer_lr_backbone`       | 主干网络学习率         | `1e-5`                           |

**WandB 参数**

| 参数             | 说明                 | 默认值 / 备注              |
| ---------------- | -------------------- | -------------------------- |
| `wandb.enable` | 是否启用 WandB 日志  | `true` / `false`       |
| `wandb.entity` | WandB 用户名或团队名 | 例如 `your_wandb_entity` |

#### Diffusion Policy (DP)

以下是使用 **Diffusion Policy** 策略、附带完整超参数的训练示例：

```bash
/isaac-sim/python.sh src/lerobot/scripts/lerobot_train.py \
  --dataset.repo_id=your_org/Packing_Box_dataset \
  --dataset.root=./challenge2026_dataset/Packing_Box/packing_box_episode_50 \
  --policy.type=diffusion \
  --policy.n_obs_steps=2 \
  --policy.horizon=16 \
  --policy.n_action_steps=8 \
  --policy.vision_backbone=resnet18 \
  --policy.pretrained_backbone_weights=null \
  --policy.resize_shape=null \
  --policy.crop_ratio=1.0 \
  --policy.crop_shape=null \
  --policy.crop_is_random=true \
  --policy.use_group_norm=true \
  --policy.spatial_softmax_num_keypoints=32 \
  --policy.use_separate_rgb_encoder_per_camera=false \
  --policy.down_dims='[512,1024,2048]' \
  --policy.kernel_size=5 \
  --policy.n_groups=8 \
  --policy.diffusion_step_embed_dim=128 \
  --policy.use_film_scale_modulation=true \
  --policy.noise_scheduler_type=DDPM \
  --policy.num_train_timesteps=100 \
  --policy.beta_schedule=squaredcos_cap_v2 \
  --policy.beta_start=0.0001 \
  --policy.beta_end=0.02 \
  --policy.prediction_type=epsilon \
  --policy.clip_sample=true \
  --policy.clip_sample_range=1.0 \
  --policy.num_inference_steps=null \
  --policy.compile_model=false \
  --policy.compile_mode=reduce-overhead \
  --policy.do_mask_loss_for_padding=false \
  --policy.optimizer_lr=1e-4 \
  --policy.optimizer_betas='[0.95,0.999]' \
  --policy.optimizer_eps=1e-8 \
  --policy.optimizer_weight_decay=1e-6 \
  --policy.scheduler_name=cosine \
  --policy.scheduler_warmup_steps=500 \
  --output_dir=challenge2026_baseline/Packing_Box/diffusion_001/ \
  --job_name=task4_diffusion \
  --resume=false \
  --seed=1000 \
  --num_workers=8 \
  --batch_size=32 \
  --steps=100000 \
  --eval_freq=0 \
  --log_freq=200 \
  --save_checkpoint=true \
  --save_freq=5000 \
  --wandb.entity=your_wandb_entity
```

> 请将 `your_org/Packing_Box_dataset` 替换为您自己的数据集 repo ID，将 `your_wandb_entity` 替换为您的 WandB 用户名或团队名。若不使用 WandB，可删除 `--wandb.entity` 参数。

**数据集与输出参数**

| 参数                | 说明                                   | 默认值 / 备注 |
| ------------------- | -------------------------------------- | ------------- |
| `dataset.repo_id` | 数据集 ID（Hugging Face 或本地组织名） | 必填          |
| `dataset.root`    | 数据集本地根路径                       | 必填          |
| `output_dir`      | 检查点与日志保存目录                   | 必填          |
| `job_name`        | 任务标识（显示在日志 / WandB 中）      | 可选          |
| `resume`          | 是否从上次检查点续训                   | `false`     |
| `seed`            | 全局随机种子                           | `1000`      |

**训练循环参数**

| 参数                | 说明                       | 默认值 / 备注 |
| ------------------- | -------------------------- | ------------- |
| `steps`           | 总训练步数                 | `100000`    |
| `batch_size`      | 每步样本数                 | `32`        |
| `num_workers`     | DataLoader 工作进程数      | `8`         |
| `eval_freq`       | 评估间隔步数（0 表示禁用） | `0`         |
| `log_freq`        | 日志打印间隔步数           | `200`       |
| `save_checkpoint` | 是否保存检查点             | `true`      |
| `save_freq`       | 检查点保存间隔步数         | `5000`      |

**Diffusion Policy 策略参数 - 输入输出结构**

| 参数                      | 说明                   | 默认值 / 备注 |
| ------------------------- | ---------------------- | ------------- |
| `policy.type`           | 策略算法类型           | `diffusion` |
| `policy.n_obs_steps`    | 观测步数               | `2`         |
| `policy.horizon`        | 动作预测 horizon       | `16`        |
| `policy.n_action_steps` | 每次推理执行的动作步数 | `8`         |

**Diffusion Policy 策略参数 - 视觉主干网络**

| 参数                                           | 说明                          | 默认值 / 备注 |
| ---------------------------------------------- | ----------------------------- | ------------- |
| `policy.vision_backbone`                     | 视觉编码器架构                | `resnet18`  |
| `policy.pretrained_backbone_weights`         | 主干网络预训练权重            | `null`      |
| `policy.resize_shape`                        | 图像预处理 resize 尺寸 (H, W) | `null`      |
| `policy.crop_ratio`                          | crop 尺寸比例 (0, 1]          | `1.0`       |
| `policy.crop_shape`                          | crop 尺寸 (H, W)              | `null`      |
| `policy.crop_is_random`                      | 是否随机 crop（训练时随机）   | `true`      |
| `policy.use_group_norm`                      | 是否使用 GroupNorm 替代 BN    | `true`      |
| `policy.spatial_softmax_num_keypoints`       | SpatialSoftmax 关键点数量     | `32`        |
| `policy.use_separate_rgb_encoder_per_camera` | 是否为每个相机使用独立编码器  | `false`     |

**Diffusion Policy 策略参数 - UNet 架构**

| 参数                                 | 说明                     | 默认值 / 备注       |
| ------------------------------------ | ------------------------ | ------------------- |
| `policy.down_dims`                 | UNet 下采样维度          | `[512,1024,2048]` |
| `policy.kernel_size`               | 卷积核大小               | `5`               |
| `policy.n_groups`                  | GroupNorm 分组数         | `8`               |
| `policy.diffusion_step_embed_dim`  | diffusion 步数嵌入维度   | `128`             |
| `policy.use_film_scale_modulation` | 是否使用 FiLM scale 调制 | `true`            |

**Diffusion Policy 策略参数 - 噪声调度器**

| 参数                            | 说明                  | 默认值 / 备注            |
| ------------------------------- | --------------------- | ------------------------ |
| `policy.noise_scheduler_type` | 噪声调度器类型        | `DDPM` / `DDIM`      |
| `policy.num_train_timesteps`  | 训练时 diffusion 步数 | `100`                  |
| `policy.beta_schedule`        | beta 调度             | `squaredcos_cap_v2`    |
| `policy.beta_start`           | beta 起始值           | `0.0001`               |
| `policy.beta_end`             | beta 结束值           | `0.02`                 |
| `policy.prediction_type`      | 预测类型              | `epsilon` / `sample` |
| `policy.clip_sample`          | 是否裁剪样本          | `true`                 |
| `policy.clip_sample_range`    | 裁剪范围              | `1.0`                  |
| `policy.num_inference_steps`  | 推理步数              | `null`（等同训练步数） |

**Diffusion Policy 策略参数 - 优化器与调度器**

| 参数                              | 说明         | 默认值 / 备注    |
| --------------------------------- | ------------ | ---------------- |
| `policy.optimizer_lr`           | 学习率       | `1e-4`         |
| `policy.optimizer_betas`        | Adam betas   | `[0.95,0.999]` |
| `policy.optimizer_eps`          | Adam eps     | `1e-8`         |
| `policy.optimizer_weight_decay` | 权重衰减     | `1e-6`         |
| `policy.scheduler_name`         | 学习率调度器 | `cosine`       |
| `policy.scheduler_warmup_steps` | warmup 步数  | `500`          |

**Diffusion Policy 策略参数 - 其他**

| 参数                                | 说明                   | 默认值 / 备注       |
| ----------------------------------- | ---------------------- | ------------------- |
| `policy.compile_model`            | 是否编译模型           | `false`           |
| `policy.compile_mode`             | 编译模式               | `reduce-overhead` |
| `policy.do_mask_loss_for_padding` | 是否 mask padding 损失 | `false`           |

**WandB 参数**

| 参数             | 说明                 | 默认值 / 备注              |
| ---------------- | -------------------- | -------------------------- |
| `wandb.enable` | 是否启用 WandB 日志  | `true` / `false`       |
| `wandb.entity` | WandB 用户名或团队名 | 例如 `your_wandb_entity` |

#### π₀ (PI0)

以下是使用 **π₀ (PI0)** 策略、附带完整超参数的训练示例：

```bash
# 安装pi0依赖
/isaac-sim/python.sh -m pip install -e ".[pi]"

# 简洁训练命令
/isaac-sim/python.sh src/lerobot/scripts/lerobot_train.py \
  --policy.path=lerobot/smolvla_base \
  --dataset.repo_id=${HF_USER}/mydataset \
  --batch_size=64 \
  --steps=20000 \
  --output_dir=outputs/train/my_smolvla \
  --job_name=my_smolvla_training \
  --policy.device=cuda \
  --wandb.enable=true

# 详细训练命令
/isaac-sim/python.sh src/lerobot/scripts/lerobot_train.py \
  --dataset.repo_id=your_org/Packing_Box_dataset \
  --dataset.root=./challenge2026_dataset/Packing_Box/packing_box_episode_50 \
  --policy.type=pi0 \
  --policy.paligemma_variant=gemma_2b \
  --policy.action_expert_variant=gemma_300m \
  --policy.dtype=float32 \
  --policy.n_obs_steps=1 \
  --policy.chunk_size=50 \
  --policy.n_action_steps=50 \
  --policy.max_state_dim=32 \
  --policy.max_action_dim=32 \
  --policy.num_inference_steps=10 \
  --policy.time_sampling_beta_alpha=1.5 \
  --policy.time_sampling_beta_beta=1.0 \
  --policy.time_sampling_scale=0.999 \
  --policy.time_sampling_offset=0.001 \
  --policy.min_period=0.004 \
  --policy.max_period=4.0 \
  --policy.image_resolution='[224,224]' \
  --policy.empty_cameras=0 \
  --policy.gradient_checkpointing=false \
  --policy.compile_model=false \
  --policy.compile_mode=max-autotune \
  --policy.freeze_vision_encoder=false \
  --policy.train_expert_only=false \
  --policy.optimizer_lr=2.5e-5 \
  --policy.optimizer_betas='[0.9,0.95]' \
  --policy.optimizer_eps=1e-8 \
  --policy.optimizer_weight_decay=0.01 \
  --policy.optimizer_grad_clip_norm=1.0 \
  --policy.scheduler_warmup_steps=1000 \
  --policy.scheduler_decay_steps=30000 \
  --policy.scheduler_decay_lr=2.5e-6 \
  --policy.tokenizer_max_length=48 \
  --output_dir=challenge2026_baseline/Packing_Box/pi0_001/ \
  --job_name=task4_pi0 \
  --resume=false \
  --seed=1000 \
  --num_workers=8 \
  --batch_size=8 \
  --steps=100000 \
  --eval_freq=0 \
  --log_freq=200 \
  --save_checkpoint=true \
  --save_freq=5000 \
  --wandb.entity=your_wandb_entity
```

> 请将 `your_org/Packing_Box_dataset` 替换为您自己的数据集 repo ID，将 `your_wandb_entity` 替换为您的 WandB 用户名或团队名。若不使用 WandB，可删除 `--wandb.entity` 参数。

**数据集与输出参数**

| 参数                | 说明                                   | 默认值 / 备注 |
| ------------------- | -------------------------------------- | ------------- |
| `dataset.repo_id` | 数据集 ID（Hugging Face 或本地组织名） | 必填          |
| `dataset.root`    | 数据集本地根路径                       | 必填          |
| `output_dir`      | 检查点与日志保存目录                   | 必填          |
| `job_name`        | 任务标识（显示在日志 / WandB 中）      | 可选          |
| `resume`          | 是否从上次检查点续训                   | `false`     |
| `seed`            | 全局随机种子                           | `1000`      |

**训练循环参数**

| 参数                | 说明                       | 默认值 / 备注 |
| ------------------- | -------------------------- | ------------- |
| `steps`           | 总训练步数                 | `100000`    |
| `batch_size`      | 每步样本数                 | `8`         |
| `num_workers`     | DataLoader 工作进程数      | `8`         |
| `eval_freq`       | 评估间隔步数（0 表示禁用） | `0`         |
| `log_freq`        | 日志打印间隔步数           | `200`       |
| `save_checkpoint` | 是否保存检查点             | `true`      |
| `save_freq`       | 检查点保存间隔步数         | `5000`      |

**π₀ 策略参数 - 模型架构**

| 参数                             | 说明               | 默认值 / 备注  |
| -------------------------------- | ------------------ | -------------- |
| `policy.type`                  | 策略算法类型       | `pi0`        |
| `policy.paligemma_variant`     | PaliGemma 模型变体 | `gemma_2b`   |
| `policy.action_expert_variant` | Action Expert 变体 | `gemma_300m` |
| `policy.dtype`                 | 数据类型           | `float32`    |

**π₀ 策略参数 - 输入输出结构**

| 参数                      | 说明                   | 默认值 / 备注 |
| ------------------------- | ---------------------- | ------------- |
| `policy.n_obs_steps`    | 观测步数               | `1`         |
| `policy.chunk_size`     | 动作块大小             | `50`        |
| `policy.n_action_steps` | 执行动作步数           | `50`        |
| `policy.max_state_dim`  | 状态维度上限（填充至） | `32`        |
| `policy.max_action_dim` | 动作维度上限（填充至） | `32`        |

**π₀ 策略参数 - Flow Matching**

| 参数                                | 说明             | 默认值 / 备注 |
| ----------------------------------- | ---------------- | ------------- |
| `policy.num_inference_steps`      | 推理去噪步数     | `10`        |
| `policy.time_sampling_beta_alpha` | 时间采样 beta α | `1.5`       |
| `policy.time_sampling_beta_beta`  | 时间采样 beta β | `1.0`       |
| `policy.time_sampling_scale`      | 时间采样 scale   | `0.999`     |
| `policy.time_sampling_offset`     | 时间采样 offset  | `0.001`     |
| `policy.min_period`               | 最小周期         | `0.004`     |
| `policy.max_period`               | 最大周期         | `4.0`       |

**π₀ 策略参数 - 图像与相机**

| 参数                        | 说明                     | 默认值 / 备注 |
| --------------------------- | ------------------------ | ------------- |
| `policy.image_resolution` | 图像分辨率 (H, W)        | `[224,224]` |
| `policy.empty_cameras`    | 空相机数量（补充空相机） | `0`         |

**π₀ 策略参数 - 训练设置**

| 参数                              | 说明               | 默认值 / 备注    |
| --------------------------------- | ------------------ | ---------------- |
| `policy.gradient_checkpointing` | 是否启用梯度检查点 | `false`        |
| `policy.compile_model`          | 是否编译模型       | `false`        |
| `policy.compile_mode`           | 编译模式           | `max-autotune` |

**π₀ 策略参数 - 微调设置**

| 参数                             | 说明                     | 默认值 / 备注 |
| -------------------------------- | ------------------------ | ------------- |
| `policy.freeze_vision_encoder` | 是否冻结视觉编码器       | `false`     |
| `policy.train_expert_only`     | 是否仅训练 Action Expert | `false`     |

**π₀ 策略参数 - 优化器**

| 参数                                | 说明         | 默认值 / 备注  |
| ----------------------------------- | ------------ | -------------- |
| `policy.optimizer_lr`             | 学习率       | `2.5e-5`     |
| `policy.optimizer_betas`          | AdamW betas  | `[0.9,0.95]` |
| `policy.optimizer_eps`            | AdamW eps    | `1e-8`       |
| `policy.optimizer_weight_decay`   | 权重衰减     | `0.01`       |
| `policy.optimizer_grad_clip_norm` | 梯度裁剪范数 | `1.0`        |

**π₀ 策略参数 - 学习率调度器**

| 参数                              | 说明         | 默认值 / 备注 |
| --------------------------------- | ------------ | ------------- |
| `policy.scheduler_warmup_steps` | warmup 步数  | `1000`      |
| `policy.scheduler_decay_steps`  | decay 步数   | `30000`     |
| `policy.scheduler_decay_lr`     | decay 学习率 | `2.5e-6`    |

**π₀ 策略参数 - Tokenizer**

| 参数                            | 说明               | 默认值 / 备注 |
| ------------------------------- | ------------------ | ------------- |
| `policy.tokenizer_max_length` | tokenizer 最大长度 | `48`        |

**WandB 参数**

| 参数             | 说明                 | 默认值 / 备注              |
| ---------------- | -------------------- | -------------------------- |
| `wandb.enable` | 是否启用 WandB 日志  | `true` / `false`       |
| `wandb.entity` | WandB 用户名或团队名 | 例如 `your_wandb_entity` |

#### π₀.₅ (PI05)

以下是使用 **π₀.₅ (PI05)** 策略、附带完整超参数的训练示例。π₀.₅ 是 π₀ 的增强版本，支持开放世界泛化，主要差异包括使用 QUANTILES 归一化、更长的 tokenizer 长度以及 AdaRMS conditioning。

```bash
# 安装pi05依赖
/isaac-sim/python.sh -m pip install -e ".[pi]"

# 简洁训练命令
/isaac-sim/python.sh src/lerobot/scripts/lerobot_train.py \
    --dataset.repo_id=your_dataset \
    --policy.type=pi05 \
    --output_dir=./outputs/pi05_training \
    --job_name=pi05_training \
    --policy.repo_id=your_repo_id \
    --policy.pretrained_path=lerobot/pi05_base \
    --policy.compile_model=true \
    --policy.gradient_checkpointing=true \
    --wandb.enable=true \
    --policy.dtype=bfloat16 \
    --policy.freeze_vision_encoder=false \
    --policy.train_expert_only=false \
    --steps=3000 \
    --policy.device=cuda \
    --batch_size=32

# 详细训练命令
/isaac-sim/python.sh src/lerobot/scripts/lerobot_train.py \
  --dataset.repo_id=your_org/Packing_Box_dataset \
  --dataset.root=./challenge2026_dataset/Packing_Box/packing_box_episode_50 \
  --policy.type=pi05 \
  --policy.paligemma_variant=gemma_2b \
  --policy.action_expert_variant=gemma_300m \
  --policy.dtype=float32 \
  --policy.n_obs_steps=1 \
  --policy.chunk_size=50 \
  --policy.n_action_steps=50 \
  --policy.max_state_dim=32 \
  --policy.max_action_dim=32 \
  --policy.num_inference_steps=10 \
  --policy.time_sampling_beta_alpha=1.5 \
  --policy.time_sampling_beta_beta=1.0 \
  --policy.time_sampling_scale=0.999 \
  --policy.time_sampling_offset=0.001 \
  --policy.min_period=0.004 \
  --policy.max_period=4.0 \
  --policy.image_resolution='[224,224]' \
  --policy.empty_cameras=0 \
  --policy.gradient_checkpointing=false \
  --policy.compile_model=false \
  --policy.compile_mode=max-autotune \
  --policy.freeze_vision_encoder=false \
  --policy.train_expert_only=false \
  --policy.optimizer_lr=2.5e-5 \
  --policy.optimizer_betas='[0.9,0.95]' \
  --policy.optimizer_eps=1e-8 \
  --policy.optimizer_weight_decay=0.01 \
  --policy.optimizer_grad_clip_norm=1.0 \
  --policy.scheduler_warmup_steps=1000 \
  --policy.scheduler_decay_steps=30000 \
  --policy.scheduler_decay_lr=2.5e-6 \
  --policy.tokenizer_max_length=200 \
  --output_dir=challenge2026_baseline/Packing_Box/pi05_001/ \
  --job_name=task4_pi05 \
  --resume=false \
  --seed=1000 \
  --num_workers=8 \
  --batch_size=8 \
  --steps=100000 \
  --eval_freq=0 \
  --log_freq=200 \
  --save_checkpoint=true \
  --save_freq=5000 \
  --wandb.entity=your_wandb_entity
```

> 请将 `your_org/Packing_Box_dataset` 替换为您自己的数据集 repo ID，将 `your_wandb_entity` 替换为您的 WandB 用户名或团队名。若不使用 WandB，可删除 `--wandb.entity` 参数。

**数据集与输出参数**

| 参数                | 说明                                   | 默认值 / 备注 |
| ------------------- | -------------------------------------- | ------------- |
| `dataset.repo_id` | 数据集 ID（Hugging Face 或本地组织名） | 必填          |
| `dataset.root`    | 数据集本地根路径                       | 必填          |
| `output_dir`      | 检查点与日志保存目录                   | 必填          |
| `job_name`        | 任务标识（显示在日志 / WandB 中）      | 可选          |
| `resume`          | 是否从上次检查点续训                   | `false`     |
| `seed`            | 全局随机种子                           | `1000`      |

**训练循环参数**

| 参数                | 说明                       | 默认值 / 备注 |
| ------------------- | -------------------------- | ------------- |
| `steps`           | 总训练步数                 | `100000`    |
| `batch_size`      | 每步样本数                 | `8`         |
| `num_workers`     | DataLoader 工作进程数      | `8`         |
| `eval_freq`       | 评估间隔步数（0 表示禁用） | `0`         |
| `log_freq`        | 日志打印间隔步数           | `200`       |
| `save_checkpoint` | 是否保存检查点             | `true`      |
| `save_freq`       | 检查点保存间隔步数         | `5000`      |

**π₀.₅ 策略参数 - 模型架构**

| 参数                             | 说明               | 默认值 / 备注  |
| -------------------------------- | ------------------ | -------------- |
| `policy.type`                  | 策略算法类型       | `pi05`       |
| `policy.paligemma_variant`     | PaliGemma 模型变体 | `gemma_2b`   |
| `policy.action_expert_variant` | Action Expert 变体 | `gemma_300m` |
| `policy.dtype`                 | 数据类型           | `float32`    |

**π₀.₅ 策略参数 - 输入输出结构**

| 参数                      | 说明                   | 默认值 / 备注 |
| ------------------------- | ---------------------- | ------------- |
| `policy.n_obs_steps`    | 观测步数               | `1`         |
| `policy.chunk_size`     | 动作块大小             | `50`        |
| `policy.n_action_steps` | 执行动作步数           | `50`        |
| `policy.max_state_dim`  | 状态维度上限（填充至） | `32`        |
| `policy.max_action_dim` | 动作维度上限（填充至） | `32`        |

**π₀.₅ 策略参数 - Flow Matching**

| 参数                                | 说明             | 默认值 / 备注 |
| ----------------------------------- | ---------------- | ------------- |
| `policy.num_inference_steps`      | 推理去噪步数     | `10`        |
| `policy.time_sampling_beta_alpha` | 时间采样 beta α | `1.5`       |
| `policy.time_sampling_beta_beta`  | 时间采样 beta β | `1.0`       |
| `policy.time_sampling_scale`      | 时间采样 scale   | `0.999`     |
| `policy.time_sampling_offset`     | 时间采样 offset  | `0.001`     |
| `policy.min_period`               | 最小周期         | `0.004`     |
| `policy.max_period`               | 最大周期         | `4.0`       |

**π₀.₅ 策略参数 - 图像与相机**

| 参数                        | 说明                     | 默认值 / 备注 |
| --------------------------- | ------------------------ | ------------- |
| `policy.image_resolution` | 图像分辨率 (H, W)        | `[224,224]` |
| `policy.empty_cameras`    | 空相机数量（补充空相机） | `0`         |

**π₀.₅ 策略参数 - 训练设置**

| 参数                              | 说明               | 默认值 / 备注    |
| --------------------------------- | ------------------ | ---------------- |
| `policy.gradient_checkpointing` | 是否启用梯度检查点 | `false`        |
| `policy.compile_model`          | 是否编译模型       | `false`        |
| `policy.compile_mode`           | 编译模式           | `max-autotune` |

**π₀.₅ 策略参数 - 微调设置**

| 参数                             | 说明                     | 默认值 / 备注 |
| -------------------------------- | ------------------------ | ------------- |
| `policy.freeze_vision_encoder` | 是否冻结视觉编码器       | `false`     |
| `policy.train_expert_only`     | 是否仅训练 Action Expert | `false`     |

**π₀.₅ 策略参数 - 优化器**

| 参数                                | 说明         | 默认值 / 备注  |
| ----------------------------------- | ------------ | -------------- |
| `policy.optimizer_lr`             | 学习率       | `2.5e-5`     |
| `policy.optimizer_betas`          | AdamW betas  | `[0.9,0.95]` |
| `policy.optimizer_eps`            | AdamW eps    | `1e-8`       |
| `policy.optimizer_weight_decay`   | 权重衰减     | `0.01`       |
| `policy.optimizer_grad_clip_norm` | 梯度裁剪范数 | `1.0`        |

**π₀.₅ 策略参数 - 学习率调度器**

| 参数                              | 说明         | 默认值 / 备注 |
| --------------------------------- | ------------ | ------------- |
| `policy.scheduler_warmup_steps` | warmup 步数  | `1000`      |
| `policy.scheduler_decay_steps`  | decay 步数   | `30000`     |
| `policy.scheduler_decay_lr`     | decay 学习率 | `2.5e-6`    |

**π₀.₅ 策略参数 - Tokenizer**

| 参数                            | 说明               | 默认值 / 备注             |
| ------------------------------- | ------------------ | ------------------------- |
| `policy.tokenizer_max_length` | tokenizer 最大长度 | `200`（π₀ 为 `48`） |

**π₀ 与 π₀.₅ 主要差异说明**

| 特性           | π₀                                        | π₀.₅                                      |
| -------------- | ------------------------------------------- | -------------------------------------------- |
| 时间条件注入   | 通过 `action_time_mlp_*` 将时间与动作拼接 | 通过 `time_mlp_*` 使用 AdaRMS conditioning |
| AdaRMS         | 不使用                                      | 在 Action Expert 中使用                      |
| Tokenizer 长度 | 48 tokens                                   | 200 tokens                                   |
| 离散状态输入   | False（使用 `state_proj` 层）             | True                                         |
| 参数量         | 较高（包含状态嵌入层）                      | 较低（无状态嵌入层）                         |
| 状态归一化     | MEAN_STD                                    | QUANTILES                                    |
| 动作归一化     | MEAN_STD                                    | QUANTILES                                    |

**WandB 参数**

| 参数             | 说明                 | 默认值 / 备注              |
| ---------------- | -------------------- | -------------------------- |
| `wandb.enable` | 是否启用 WandB 日志  | `true` / `false`       |
| `wandb.entity` | WandB 用户名或团队名 | 例如 `your_wandb_entity` |

#### SmolVLA

以下是使用 **SmolVLA** 策略进行微调的训练示例。SmolVLA 基于 SmolVLM2-500M-Video-Instruct 视觉语言模型构建，支持开放世界泛化。

```bash
# 安装 SmolVLA 依赖
/isaac-sim/python.sh -m pip install -e ".[smolvla]"

# 简洁训练命令
/isaac-sim/python.sh src/lerobot/scripts/lerobot_train.py \
  --policy.path=lerobot/smolvla_base \
  --dataset.repo_id=${HF_USER}/mydataset \
  --batch_size=64 \
  --steps=20000 \
  --output_dir=outputs/train/my_smolvla \
  --job_name=my_smolvla_training \
  --policy.device=cuda \
  --wandb.enable=true

# 详细训练命令
/isaac-sim/python.sh src/lerobot/scripts/lerobot_train.py \
  --dataset.repo_id=your_org/Packing_Box_dataset \
  --dataset.root=./challenge2026_dataset/Packing_Box/packing_box_episode_50 \
  --policy.type=smolvla \
  --policy.vlm_model_name=HuggingFaceTB/SmolVLM2-500M-Video-Instruct \
  --policy.load_vlm_weights=true \
  --policy.dtype=float32 \
  --policy.n_obs_steps=1 \
  --policy.chunk_size=50 \
  --policy.n_action_steps=50 \
  --policy.max_state_dim=32 \
  --policy.max_action_dim=32 \
  --policy.num_steps=10 \
  --policy.tokenizer_max_length=48 \
  --policy.image_resolution='[224,224]' \
  --policy.empty_cameras=0 \
  --policy.freeze_vision_encoder=true \
  --policy.train_expert_only=true \
  --policy.train_state_proj=true \
  --policy.gradient_checkpointing=false \
  --policy.compile_model=false \
  --policy.compile_mode=max-autotune \
  --policy.attention_mode=cross_attn \
  --policy.num_vlm_layers=16 \
  --policy.self_attn_every_n_layers=2 \
  --policy.expert_width_multiplier=0.75 \
  --policy.optimizer_lr=1e-4 \
  --policy.optimizer_betas='[0.9,0.95]' \
  --policy.optimizer_eps=1e-8 \
  --policy.optimizer_weight_decay=1e-10 \
  --policy.optimizer_grad_clip_norm=10.0 \
  --policy.scheduler_warmup_steps=1000 \
  --policy.scheduler_decay_steps=30000 \
  --policy.scheduler_decay_lr=2.5e-6 \
  --policy.min_period=0.004 \
  --policy.max_period=4.0 \
  --output_dir=challenge2026_baseline/Packing_Box/smolvla_001/ \
  --job_name=task4_smolvla \
  --resume=false \
  --seed=1000 \
  --num_workers=8 \
  --batch_size=8 \
  --steps=100000 \
  --eval_freq=0 \
  --log_freq=200 \
  --save_checkpoint=true \
  --save_freq=5000 \
  --wandb.entity=your_wandb_entity
```

> 请将 `your_org/Packing_Box_dataset` 替换为您自己的数据集 repo ID，将 `your_wandb_entity` 替换为您的 WandB 用户名或团队名。若不使用 WandB，可删除 `--wandb.entity` 参数。

**数据集与输出参数**

| 参数                | 说明                                   | 默认值 / 备注 |
| ------------------- | -------------------------------------- | ------------- |
| `dataset.repo_id` | 数据集 ID（Hugging Face 或本地组织名） | 必填          |
| `dataset.root`    | 数据集本地根路径                       | 必填          |
| `output_dir`      | 检查点与日志保存目录                   | 必填          |
| `job_name`        | 任务标识（显示在日志 / WandB 中）      | 可选          |
| `resume`          | 是否从上次检查点续训                   | `false`     |
| `seed`            | 全局随机种子                           | `1000`      |

**训练循环参数**

| 参数                | 说明                       | 默认值 / 备注 |
| ------------------- | -------------------------- | ------------- |
| `steps`           | 总训练步数                 | `100000`    |
| `batch_size`      | 每步样本数                 | `8`         |
| `num_workers`     | DataLoader 工作进程数      | `8`         |
| `eval_freq`       | 评估间隔步数（0 表示禁用） | `0`         |
| `log_freq`        | 日志打印间隔步数           | `200`       |
| `save_checkpoint` | 是否保存检查点             | `true`      |
| `save_freq`       | 检查点保存间隔步数         | `5000`      |

**SmolVLA 策略参数 - 模型架构**

| 参数                        | 说明                    | 默认值 / 备注                                  |
| --------------------------- | ----------------------- | ---------------------------------------------- |
| `policy.type`             | 策略算法类型            | `smolvla`                                    |
| `policy.vlm_model_name`   | VLM 骨干模型            | `HuggingFaceTB/SmolVLM2-500M-Video-Instruct` |
| `policy.load_vlm_weights` | 是否加载预训练 VLM 权重 | `true`                                       |
| `policy.dtype`            | 数据类型                | `float32`                                    |

**SmolVLA 策略参数 - 输入输出结构**

| 参数                      | 说明                   | 默认值 / 备注 |
| ------------------------- | ---------------------- | ------------- |
| `policy.n_obs_steps`    | 观测步数               | `1`         |
| `policy.chunk_size`     | 动作块大小             | `50`        |
| `policy.n_action_steps` | 执行动作步数           | `50`        |
| `policy.max_state_dim`  | 状态维度上限（填充至） | `32`        |
| `policy.max_action_dim` | 动作维度上限（填充至） | `32`        |

**SmolVLA 策略参数 - 解码与 Tokenizer**

| 参数                            | 说明               | 默认值 / 备注 |
| ------------------------------- | ------------------ | ------------- |
| `policy.num_steps`            | 推理去噪步数       | `10`        |
| `policy.tokenizer_max_length` | Tokenizer 最大长度 | `48`        |
| `policy.use_cache`            | 是否使用注意力缓存 | `true`      |

**SmolVLA 策略参数 - 图像与相机**

| 参数                                | 说明                     | 默认值 / 备注 |
| ----------------------------------- | ------------------------ | ------------- |
| `policy.image_resolution`         | 图像预处理分辨率 (H, W)  | `[224,224]` |
| `policy.empty_cameras`            | 空相机数量（补充空相机） | `0`         |
| `policy.add_image_special_tokens` | 是否使用图像特殊 token   | `false`     |

**SmolVLA 策略参数 - 微调设置**

| 参数                             | 说明                     | 默认值 / 备注 |
| -------------------------------- | ------------------------ | ------------- |
| `policy.freeze_vision_encoder` | 是否冻结视觉编码器       | `true`      |
| `policy.train_expert_only`     | 是否仅训练 Action Expert | `true`      |
| `policy.train_state_proj`      | 是否训练状态投影层       | `true`      |

**SmolVLA 策略参数 - Transformer 架构**

| 参数                                | 说明                         | 默认值 / 备注  |
| ----------------------------------- | ---------------------------- | -------------- |
| `policy.attention_mode`           | 注意力模式                   | `cross_attn` |
| `policy.num_vlm_layers`           | VLM 使用层数                 | `16`         |
| `policy.self_attn_every_n_layers` | 每隔 N 层插入自注意力层      | `2`          |
| `policy.expert_width_multiplier`  | Action Expert 隐藏层宽度比例 | `0.75`       |

**SmolVLA 策略参数 - 优化器**

| 参数                                | 说明         | 默认值 / 备注  |
| ----------------------------------- | ------------ | -------------- |
| `policy.optimizer_lr`             | 学习率       | `1e-4`       |
| `policy.optimizer_betas`          | AdamW betas  | `[0.9,0.95]` |
| `policy.optimizer_eps`            | AdamW eps    | `1e-8`       |
| `policy.optimizer_weight_decay`   | 权重衰减     | `1e-10`      |
| `policy.optimizer_grad_clip_norm` | 梯度裁剪范数 | `10.0`       |

**SmolVLA 策略参数 - 学习率调度器**

| 参数                              | 说明         | 默认值 / 备注 |
| --------------------------------- | ------------ | ------------- |
| `policy.scheduler_warmup_steps` | warmup 步数  | `1000`      |
| `policy.scheduler_decay_steps`  | decay 步数   | `30000`     |
| `policy.scheduler_decay_lr`     | decay 学习率 | `2.5e-6`    |

**SmolVLA 策略参数 - 训练设置**

| 参数                              | 说明               | 默认值 / 备注    |
| --------------------------------- | ------------------ | ---------------- |
| `policy.gradient_checkpointing` | 是否启用梯度检查点 | `false`        |
| `policy.compile_model`          | 是否编译模型       | `false`        |
| `policy.compile_mode`           | 编译模式           | `max-autotune` |

**WandB 参数**

| 参数             | 说明                 | 默认值 / 备注              |
| ---------------- | -------------------- | -------------------------- |
| `wandb.enable` | 是否启用 WandB 日志  | `true` / `false`       |
| `wandb.entity` | WandB 用户名或团队名 | 例如 `your_wandb_entity` |

---

### 6. 策略推理 (Inference)

使用训练好的策略模型进行推理并自动录制结果：

```bash
# 设置haggface镜像
export HF_ENDPOINT=https://hf-mirror.com 
/isaac-sim/python.sh src/lerobot/scripts/lerobot_record.py \
    --robot.type=walker_s2_sim \
    --robot.headless=false \
    --task=Part_Sorting \
    --policy.path=challenge2026_baseline/Part_Sorting/smolvla/750_5_14/0450000 \
    --dataset.repo_id=sjj/eval_Part_Sorting \
    --dataset.single_task="Part Sorting" \
    --dataset.num_episodes=2 \
    --dataset.push_to_hub=false \
    --dataset.episode_time_s=100000000 \
    --dataset.num_image_writer_processes=4 \
    --dataset.root=${workspaceFolder}/datasets/Part_Sorting/test1 \
    --dataset.video=true \
    --play_sounds=false

/isaac-sim/python.sh src/lerobot/scripts/lerobot_record.py \
    --robot.type=walker_s2_sim \
    --robot.headless=false \
    --task=Part_Sorting \
    --policy.path=challenge2026_baseline/Part_Sorting/act/train_5_7/080000/pretrained_model \
    --dataset.repo_id=sjj/eval_Part_Sorting \
    --dataset.single_task="Part Sorting" \
    --dataset.num_episodes=2 \
    --dataset.push_to_hub=false \
    --dataset.episode_time_s=100000000 \
    --dataset.num_image_writer_processes=4 \
    --dataset.root=${workspaceFolder}/datasets/Part_Sorting/infer-smolvla \
    --dataset.video=true \
    --play_sounds=false
```

| 参数                         | 说明                                                                   | 默认值 / 备注              |
| ---------------------------- | ---------------------------------------------------------------------- | -------------------------- |
| `--robot.type`             | 机器人类型                                                             | `walker_s2_sim`          |
| `--robot.headless`         | 是否无头模式                                                           | `false`                  |
| `--task`                   | 任务名称（Part_Sorting, Conveyor_Sorting, Foam_Inlaying, Packing_Box） | `Foam_Inlaying`          |
| `--policy.path`            | 策略模型检查点路径（本地或 HuggingFace）                               | 必填                       |
| `--dataset.repo_id`        | 数据集标识符，推理模式应为 `xx/eval_xx` 格式                         | 必填                       |
| `--dataset.single_task`    | 任务描述                                                               | 必填（或由 task 自动设置） |
| `--dataset.num_episodes`   | 推理回合数                                                             | `50`                     |
| `--dataset.root`           | 推理结果保存路径                                                       | 必填                       |
| `--dataset.video`          | 是否录制视频                                                           | `true`                   |
| `--dataset.fps`            | 帧率                                                                   | `30`                     |
| `--dataset.episode_time_s` | 每回合时长（秒）                                                       | `60`                     |
| `--dataset.push_to_hub`    | 是否上传到 Hugging Face                                                | `false`                  |
| `--play_sounds`            | 是否播放语音提示                                                       | `true`                   |

**注意**:

1. 策略推理使用 `lerobot_record.py` 脚本，通过 `--policy.path` 参数指定策略模型路径。脚本会自动加载模型并在仿真环境中执行推理，同时录制结果数据。
2. 推理模式下，`--dataset.repo_id` 参数应使用 `xx/eval_xx` 格式（如 `sjj/eval_Part_Sorting`），以区别于数据采集模式下的正式数据集命名。
3. `${workspaceFolder}` 应替换为实际的工作目录路径。

---

### 7. 四目实时显示 (4-Camera Real-time Display)

Walker S2 仿真器支持 4 个 RGB 相机的实时预览功能，通过 `HeadStereoVisualizer` 类实现头部双目相机的并排显示。该功能在遥操作、数据采集、回放和推理四种模式下均可使用。

#### 6.1 相机配置参数说明

| 参数                             | 说明                   | 默认值                  |
| -------------------------------- | ---------------------- | ----------------------- |
| `--robot.head_viz_enabled`     | 是否启用头部相机可视化 | `true`                |
| `--robot.head_viz_window_name` | 可视化窗口名称         | `"walker_s2_cameras"` |
| `--robot.head_viz_scale`       | 窗口缩放比例           | `1.0`                 |
| `--robot.head_viz_every_n`     | 每 N 帧更新一次显示    | `10`                  |
| `--robot.head_viz_window_x`    | 窗口 X 坐标            | `40`                  |
| `--robot.head_viz_window_y`    | 窗口 Y 坐标            | `40`                  |
| `--robot.head_viz_show_labels` | 是否显示相机标签       | `true`                |
| `--display_data`               | 是否在终端显示数据     | `false`               |

**参数说明**:

- `head_viz_enabled`: 控制是否开启头部相机可视化窗口
- `head_viz_every_n`: 控制可视化更新频率，较大的值可降低 CPU 负载
- `display_data`: 控制是否在终端打印关节状态数据

#### 6.2 相机名称与位置

| 相机名称        | 位置     | 用途     |
| --------------- | -------- | -------- |
| `head_left`   | 头部左侧 | 前置广角 |
| `head_right`  | 头部右侧 | 前置广角 |
| `wrist_left`  | 左手腕   | 手眼相机 |
| `wrist_right` | 右手腕   | 手眼相机 |

#### 6.3 可视化窗口布局

```
┌─────────────────────────────────────────┐
│        walker_s2_cameras                │
├─────────────────────┬───────────────────┤
│                     │                   │
│     head_left       │    head_right     │
│                     │                   │
├─────────────────────┴───────────────────┤
│   wrist_left    │     wrist_right       │
└─────────────────────────────────────────┘
```

#### 6.4 四种模式下的示例命令

**模式一：遥操作 (Teleoperate)**

```bash
/isaac-sim/python.sh src/lerobot/scripts/lerobot_teleoperate.py \
    --robot.type=walker_s2_sim \
    --robot.headless=false \
    --task=Packing_Box \
    --teleop.type=walker_s2_keyboard \
    --teleop.fps=30 \
    --robot.head_viz_enabled=true \
    --robot.head_viz_window_name="walker_s2_cameras" \
    --robot.head_viz_every_n=1 \
    --display_data=false

```

**模式二：数据采集 (Record)**

```bash
/isaac-sim/python.sh src/lerobot/scripts/lerobot_record.py \
    --robot.type=walker_s2_sim \
    --robot.headless=false \
    --task=Packing_Box \
    --teleop.type=walker_s2_keyboard \
    --dataset.root=./datasets/packing_box \
    --dataset.num_episodes=10 \
    --dataset.single_task="Packing box task" \
    --dataset.video=true \
    --robot.head_viz_enabled=true \
    --robot.head_viz_every_n=10 \
    --display_data=false \
    --play_sounds=false
```

**模式三：数据回放 (Replay)**

```bash
/isaac-sim/python.sh src/lerobot/scripts/lerobot_replay.py \
    --robot.type=walker_s2_sim \
    --task=Packing_Box \
    --dataset.root=./datasets/packing_box \
    --dataset.episode=0 \
    --robot.head_viz_enabled=true \
    --robot.head_viz_every_n=5 \
    --display_data=false \
    --play_sounds=false
```

**模式四：策略推理 (Inference)**

```bash
/isaac-sim/python.sh src/lerobot/scripts/lerobot_record.py \
    --robot.type=walker_s2_sim \
    --robot.headless=false \
    --task=Packing_Box \
    --policy.path=your_checkpoint_dir \
    --dataset.root=./datasets/packing_box/inference \
    --dataset.num_episodes=10 \
    --dataset.video=true \
    --robot.head_viz_enabled=true \
    --robot.head_viz_every_n=5 \
    --display_data=false \
    --play_sounds=false
```

---

## 任务定义

### Task 1：抓取 - 放置（Part_Sorting）

**任务目标：** 从工作台上抓取零件，并放入指定料盒。

**评分规则：**

| 指标     | 分值 | 说明                                      |
| -------- | ---- | ----------------------------------------- |
| 抬升评分 | 40   | 零件 Z 高度达到阈值，每个 10 分，满分 40  |
| 入箱评分 | 40   | 零件成功进入正确箱体，每个 10 分，满分 40 |
| 时间评分 | 20   | 40 秒内完成满分，超时每 10 秒扣 5 分      |
| 总分     | 100  | 总分达到 100 判定成功                     |

**配置文件：** `Ubtech_sim/config/Part_Sorting.yaml`

**关键参数：**

| 参数                    | 数值               | 说明               |
| ----------------------- | ------------------ | ------------------ |
| `task_number`         | 1                  | 任务编号           |
| `num_parts`           | 2                  | 每种类别生成的数量 |
| `part_distance`       | 0.4                | 零件间距 (m)       |
| `scatter_area.center` | [0.75, 0.28, 1.04] | 物体散布中心       |
| `scatter_area.size`   | [0.30, 0.23]       | 散布范围半宽 (m)   |

---

### Task 2：工件传送带分拣（Conveyor_Sorting）

**任务目标：** 对运行中的传送带进行实时感知，识别舵机组装件（B 零件）与正交减速器（A 零件），并分别放入传送带左右两侧指定料箱。

**场景元素：** 桌子、传送带、零件、料箱。

**传送带参数：**

| 参数         | 数值                                 |
| ------------ | ------------------------------------ |
| 速度         | 0.02 m/s                             |
| 运行方向     | 沿 X 轴，行程 1000 mm                |
| 尺寸         | 长 1500 mm × 宽 300 mm，高 1000 mm  |
| 零件出现间隔 | 每 5–10 s 随机出现一个，总时长 80 s |
| 出现位置     | 传送带起点中轴，出现姿态随机         |

**零件清单：**

| 编号   | 名称       | 尺寸               | 颜色 |
| ------ | ---------- | ------------------ | ---- |
| A 零件 | 正交减速器 | 最大边长 40–60 mm | 蓝色 |
| B 零件 | 舵机组装件 | 80 × 50 × 45 mm  | 原色 |

**评分规则：** 每轮 10 个工件（5×A + 5×B），共 10 轮，满分 1000 分。

| 评分项             | 分值       | 说明                                 |
| ------------------ | ---------- | ------------------------------------ |
| 分拣成功           | 10 分/个   | 工件完全脱离夹爪并静止在正确料箱内部 |
| 分拣失败           | 0 分       | 工件掉落或放入错误料箱               |
| 抓取成功但分拣错误 | 仅得抓取分 | 抓取计分，分拣不计分                 |
| 单轮总分           | 80 分      | —                                   |

**配置文件：** `Ubtech_sim/config/Conveyor_Sorting.yaml`

**关键参数：**

| 参数                    | 数值                 | 说明               |
| ----------------------- | -------------------- | ------------------ |
| `task_number`         | 2                    | 任务编号           |
| `num_parts`           | 5                    | 每种类别生成的数量 |
| `use_scatter_area`    | true                 | 启用散布区域       |
| `scatter_area.center` | [0.12, 0.26859, 1.2] | 传送带入口中心     |
| `scatter_area.size`   | [0.06, 0.04]         | 散布范围 (m)       |

---

### Task 3：工件嵌装（Foam_Inlaying）

**任务目标：** 将料箱中指定数量、指定类别的工件全部正确嵌装至航空箱泡棉的对应槽位。

**场景元素：** 桌子、带槽泡棉、料箱。

**时间限制：** ≤ 2 分钟；每超时 30 秒扣 5 分（扣完为止）。

**零件清单：**

| 编号   | 名称              | 尺寸              | 颜色     |
| ------ | ----------------- | ----------------- | -------- |
| A 零件 | 28 步进电机（小） | 50 × 20 × 25 mm | 两种颜色 |
| B 零件 | 舵机组装件（大）  | 80 × 50 × 45 mm | 两种颜色 |

**泡棉参数：** 600 × 400 × 100 mm，居中放置于桌面；6 个槽位（每类 3 个），槽深 60 mm。任务开始前泡棉内无工件，工件随机分布在左侧料箱中（大 3 + 小 3）。

**评分规则：** 每轮 100 分，共 10 轮，满分 1000 分。

| 评分项     | 分值                  | 说明                                                          |
| ---------- | --------------------- | ------------------------------------------------------------- |
| 嵌装成功率 | 15 分/个 × 6 = 90 分 | 工件完全脱离夹爪并放入对应类别槽位内                          |
| 嵌装效率   | 10 分                 | 2 分钟内完成全部嵌装；每超 30 s 扣 5 分；未完成全部类别不得分 |

**完成判定标准：**

1. 数量完整性：6 个工件全部放置。
2. 位置正确性：每个工件放入与其类别对应的专用槽位，不允许错槽。
3. 稳定性：工件不悬空、不明显倾斜、不与其他工件发生干涉。
4. 姿态要求：两类电机均无强制方向约束，完整嵌入槽位即可。

**配置文件：** `Ubtech_sim/config/Foam_Inlaying.yaml`

**关键参数：**

| 参数              | 数值             | 说明                   |
| ----------------- | ---------------- | ---------------------- |
| `task_number`   | 4                | 任务编号               |
| `tcp_offset`    | [0.0, 0.0, 0.22] | 末端工具坐标系偏移 (m) |
| `lift_height`   | 0.17             | 抬升高度 (m)           |
| `ik_rot_weight` | 0.1              | IK 旋转权重            |

---

### Task 4：装箱（Packing_Box）

**任务目标：** 控制折叠箱四个关节完成装箱动作。

**评分规则：**

| 指标     | 分值 | 说明                                  |
| -------- | ---- | ------------------------------------- |
| 短边闭合 | 30   | 两个短边关节达到目标，每个 15 分      |
| 长边闭合 | 30   | 两个长边关节达到目标，每个 15 分      |
| 时间评分 | 40   | 120 秒内完成满分，超时每 10 秒扣 5 分 |
| 协同系数 | —   | 单臂 ×0.7，双臂协同 ×1.0            |
| 总分     | 100  | 连续 10 步稳定判定成功                |

**关键参数：**

| 参数         | 数值                     | 说明      |
| ------------ | ------------------------ | --------- |
| 短边目标关节 | [-3.3219733, -3.3213105] | 关节 2、3 |
| 长边目标关节 | [-3.4906585, -3.4906585] | 关节 0、1 |
| 关节阈值     | 0.2 rad                  | 判定阈值  |

**配置文件：** `Ubtech_sim/config/Packing_Box.yaml`

---

## 项目结构

```text
.
├── challenge2026_baseline/         # 预训练模型权重（从 HF 下载）
│   ├── Part_Sorting/
│   ├── Conveyor_Sorting/
│   ├── Foam_Inlaying/
│   └── Packing_Box/
├── datasets/                       # 本地训练数据集目录
│   ├── Part_Sorting/
│   ├── Conveyor_Sorting/
│   ├── Foam_Inlaying/
│   └── Packing_Box/
├── assets/                         # 仿真资产（Git 子模块）
│   └── resources/                  # USD、URDF 等资源文件
├── Ubtech_sim/                     # 仿真环境与任务逻辑
│   ├── config/                     # Part_Sorting.yaml ~ Packing_Box.yaml
│   ├── source/                     # SceneBuilder、IK 等
│   └── main.py
├── src/lerobot/                    # LeRobot 核心代码
│   ├── auto_collect/               # 自动数采模块
│   │   ├── auto_collect_base.py    # 基类（模板方法）
│   │   ├── auto_collect_config.py  # 配置 dataclass
│   │   ├── task_part_sorting.py    # Task 1 子类
│   │   ├── task_foam_inlaying.py   # Task 3 子类
│   │   ├── task_packing_box.py     # Task 4 子类（replay 回放式）
│   │   └── utils.py                # 工具函数
│   └── scripts/
│       ├── auto_collect_main.py    # 自动数采主入口
│       ├── lerobot_record.py       # 数据采集
│       ├── lerobot_replay.py       # 数据回放
│       ├── lerobot_teleoperate.py  # 遥操作
│       ├── lerobot_train.py        # 模型训练
│       └── lerobot_eval.py         # 模型评估
├── Dockerfile
├── run.sh                          # 容器启动脚本
└── pyproject.toml
```

---

## 仿真架构说明

### Assets

`assets/` 通过 Git 子模块管理，对应 Hugging Face 仓库 `challenge2026_assets`，主要存放：

- USD 场景资源
- URDF 机器人模型
- 箱体、零件、任务场景文件

核心目录：`assets/resources/`

### Ubtech_sim

`Ubtech_sim/` 负责场景配置、任务逻辑、机器人控制与仿真流程封装：

- 任务 YAML：`Ubtech_sim/config/`
- 仿真源码：`Ubtech_sim/source/`
- 独立运行入口：`Ubtech_sim/main.py`

### LeRobot 集成方式

LeRobot 的 `walker_s2_sim` 通过 `WalkerS2SimRobotConfig` 读取 `task_cfg_path`，再解析其中的 `root_path` 指向 `assets/resources/`。

示例 `Ubtech_sim/config/Part_Sorting.yaml`：

```yaml
root_path: "../../assets/resources/"
scene_usd: "Collected_Task4/SubUSDs/2_small_warehouse2.usd"
```

---

## Ubtech_sim 模块说明

### 模块结构

| 目录/文件     | 说明                                                  |
| ------------- | ----------------------------------------------------- |
| `source/`   | Python 源码（SceneBuilder、IK、RobotArticulation 等） |
| `config/`   | 任务配置：Part_Sorting.yaml ~ Packing_Box.yaml        |
| `main.py`   | 独立 Isaac Sim 运行入口                               |
| `README.md` | 模块说明文档                                          |

### 核心组件

| 模块                     | 说明                                               |
| ------------------------ | -------------------------------------------------- |
| `config_loader`        | 加载 YAML 并解析绝对路径                           |
| `SceneBuilder`         | 构建仿真场景，加载桌子、箱子、零件、机器人等       |
| `RobotArticulation`    | WalkerS2 控制接口，封装双臂 IK、力传感器与相机数据 |
| `DualArmIK`            | 基于 Pinocchio 的双臂逆运动学                      |
| `GraspPlanner`         | 抓取目标规划、选臂与姿态跟踪                       |
| `DataLogger`           | 记录 CSV 位姿数据与 HDF5 图像数据                  |
| `HeadStereoVisualizer` | 头部双目相机实时可视化                             |

### 使用方式

**方式一：独立运行**

```bash
python Ubtech_sim/main.py
```

**方式二：通过 LeRobot 调用**

在 `src/lerobot/robots/configs.py` 中配置 `WalkerS2SimRobotConfig`：

```python
root_path: str = "Ubtech_sim"
task_cfg_path: str = "Ubtech_sim/config/Packing_Box.yaml"
```

### 常见目录映射

| 路径                              | 用途                 |
| --------------------------------- | -------------------- |
| `Ubtech_sim/config/*.yaml`      | 仿真任务配置         |
| `Ubtech_sim/source/*.py`        | 仿真逻辑实现         |
| `assets/resources/`             | USD、URDF 等资源文件 |
| `assets/resources/s2.urdf`      | WalkerS2 URDF        |
| `assets/resources/Collected_*/` | 场景文件             |

---

## 数据集说明

`datasets/` 目录存放各任务训练数据，采用 **LeRobotDataset V2.1** 标准：

```text
datasets/
├── Part_Sorting/
├── Conveyor_Sorting/
├── Foam_Inlaying/
└── Packing_Box/
```

| 类型 | 格式说明                        |
| ---- | ------------------------------- |
| 视频 | MP4，按相机与 episode 组织      |
| 状态 | 关节位置、速度、力矩（Parquet） |
| 动作 | 目标关节或末端位姿              |
| 频率 | 默认 `30 Hz`                  |
| 格式 | LeRobotDataset V2.1             |

---

## Git 子模块管理

### 初始化项目

```bash
git clone --recursive https://github.com/UBTECH-Robotics/WalkerS2Sim.git
cd WalkerS2Sim

# 若已单独克隆：
git submodule update --init --recursive
```

### 更新子模块

```bash
git pull
git submodule update --remote --merge

# 仅更新 assets：
cd assets
git pull origin main
cd ..
```

### 子模块关系说明

- 主项目保存对子模块的提交引用
- 子模块具备独立 Git 历史
- 更新子模块后需在主项目中执行 `git add assets` 并提交指针变化

---

## 开发指南

### 代码规范

- Python 3.11+
- 遵循 PEP 8
- 推荐使用 `pre-commit` 执行提交前检查

### 安装开发依赖

```bash
pip install -e ".[dev]"
pre-commit install
```

---

## 相关资源

| 仓库                                                                                          | 说明               |
| --------------------------------------------------------------------------------------------- | ------------------ |
| 🤗[LeRobot](https://github.com/huggingface/lerobot)                                              | 机器人学习底层框架 |
| 🤗[challenge2026_assets](https://huggingface.co/UBTECH-Robotics/challenge2026_assets)            | 仿真资产           |
| 🤗[challenge2026_dataset](https://huggingface.co/datasets/UBTECH-Robotics/challenge2026_dataset) | 训练数据集         |
| 🤗[challenge2026_baseline](https://huggingface.co/UBTECH-Robotics/challenge2026_baseline)        | 预训练权重         |

---

## 许可证

本项目采用 [Apache 2.0](LICENSE) 许可证。

## 致谢

| 项目                                                        | 说明               |
| ----------------------------------------------------------- | ------------------ |
| [Hugging Face LeRobot](https://github.com/huggingface/lerobot) | 开源机器人学习框架 |
| [NVIDIA Isaac Sim](https://developer.nvidia.com/isaac-sim)     | 机器人仿真平台     |

---

**Global Humanoid Robot Challenge 2026** | UBTECH Robotics
