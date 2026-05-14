# UBTECH Robot Competition 2026 参赛项目

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![Isaac Sim](https://img.shields.io/badge/Simulation-NVIDIA%20Isaac%20Sim-76B900)
![LeRobot](https://img.shields.io/badge/Robot%20Learning-LeRobot-FF6F00)
![Project](https://img.shields.io/badge/Project-Humanoid%20Manipulation-4B5563)

[English](README.md) · [官方 Baseline 文档](docs/official_baseline_README.md)

本仓库是我基于 **Global Humanoid Robot Challenge 2026 / UBTECH 官方 baseline** 整理和改造的参赛项目。原始 baseline 提供了 Isaac Sim 仿真、LeRobot 数据格式、遥操作采集、模仿学习训练和推理部署的完整入口；我的工作重点是围绕比赛任务进行环境理解、配置调试、传送带分拣任务适配、数据采集流程验证，以及后续策略训练所需的工程整理。

这个 README 面向作品集和求职展示：它不把官方框架包装成个人从零开发，而是明确说明我在现有 humanoid robot learning baseline 上完成的参赛工程实践。

## 项目背景

GHRC 2026 / UBTECH 机器人挑战赛面向人形机器人操作任务，要求参赛者在 Isaac Sim 中完成不同工业场景的感知、抓取、放置、分拣和装配动作。该 baseline 以 Hugging Face LeRobot 为核心训练框架，并使用 NVIDIA Isaac Sim 构建机器人仿真与任务场景。

项目覆盖的能力链路包括：

- Isaac Sim 仿真环境启动和任务场景加载
- Walker S2 机器人遥操作与双臂控制
- LeRobotDataset V2.1 格式的数据采集与回放
- ACT / Pi0 等模仿学习策略训练
- 训练后策略在仿真环境中的推理验证

## 我的主要工作

### 1. Baseline 工程梳理与复现

我对官方 baseline 的运行链路进行了整理，重点确认了从容器启动、仿真环境加载、遥操作、数据采集、训练到推理的完整流程。项目中的关键入口包括：

- `run.sh`：Isaac Sim + LeRobot 容器启动入口
- `run_walker_s2_teleop.sh`：Walker S2 遥操作启动脚本
- `lerobot/scripts/control_robot.py`：遥操作、数据采集、回放和推理统一入口
- `lerobot/scripts/train.py`：模仿学习策略训练入口
- `Ubtech_sim/config/`：比赛任务场景配置
- `Ubtech_sim/source/`：场景构建、机器人接口、IK、抓取规划等仿真逻辑

这部分工作的价值在于把官方大而全的 baseline 转化成可复现、可调试、适合继续做比赛实验的项目结构。

### 2. 传送带分拣任务适配

当前分支名为 `conveyor_speed_change`，项目重点之一是围绕 **Conveyor Belt Sorting** 任务进行配置和实验整理。该任务要求机器人识别并抓取传送带上的不同零件，将其分拣到对应箱体。

相关配置位于：

```text
Ubtech_sim/config/Conveyor_Sorting.yaml
```

该任务涉及：

- 传送带速度、方向和物体生成节奏
- 零件类型和随机姿态
- 抓取时机和末端执行器控制
- 分拣成功/失败判定
- 数据采集和策略训练样本质量

这类任务的难点不只是训练模型，还包括在仿真里调通稳定的物体运动、机器人抓取窗口、数据记录和任务 reset 逻辑。

### 3. Isaac Sim 与 LeRobot 集成理解

项目的核心技术挑战在于把 Isaac Sim 中的机器人仿真状态、相机图像、关节控制和 LeRobot 的数据/策略接口连接起来。仓库中相关模块包括：

- `Ubtech_sim/source/SceneBuilder.py`：任务场景构建与 USD 资源加载
- `Ubtech_sim/source/grasp_planner.py`：抓取规划相关逻辑
- `lerobot/common/robot_devices/robots/isaac_sim_robot_interface.py`：Isaac Sim 机器人接口
- `lerobot/common/robot_devices/robots/mobile_manipulator.py`：移动操作机器人抽象
- `lerobot/common/robot_devices/robots/configs.py`：机器人和任务配置入口

通过这个项目，我重点熟悉了机器人学习中从仿真到数据再到策略训练的工程闭环，而不是只停留在单个模型训练脚本上。

### 4. 面向模仿学习的数据与训练流程

Baseline 支持使用 LeRobotDataset V2.1 格式记录遥操作数据，并用 ACT / Pi0 等策略进行训练。典型流程是：

1. 在 Isaac Sim 中加载指定任务场景
2. 通过键盘/遥操作设备控制 Walker S2 完成任务
3. 将图像、状态和动作记录为 LeRobotDataset
4. 使用 ACT 或 Pi0 进行策略训练
5. 将训练后的策略放回仿真环境中评估

这套流程展示的是完整 robot learning pipeline：场景、机器人接口、数据质量、模型训练和推理评估都需要同时可控。

## 比赛任务概览

仓库保留了官方 baseline 中的多个任务定义：

| Task | Name | Focus |
| --- | --- | --- |
| Task 1 | Pick and Place | 零件抓取与放置 |
| Task 2 | Conveyor Belt Sorting | 传送带动态分拣 |
| Task 3 | Component Embedding | 零件嵌入泡棉槽位 |
| Task 4 | Packing Box | 折叠箱体关节操作 |

其中，当前分支更适合突出 Task 2 传送带分拣相关的配置改造和实验过程。

## 技术栈

- **仿真平台**：NVIDIA Isaac Sim
- **机器人学习框架**：Hugging Face LeRobot
- **机器人模型**：Walker S2 humanoid / mobile manipulator
- **学习方法**：Imitation Learning、ACT、Pi0
- **数据格式**：LeRobotDataset V2.1
- **运行环境**：Docker、NVIDIA Container Toolkit、CUDA
- **开发语言**：Python 3.11+

## 仓库结构

```text
.
├── Ubtech_sim/
│   ├── config/                 # Task YAML 配置，例如 Conveyor_Sorting.yaml
│   ├── source/                 # 场景构建、IK、机器人控制、抓取规划等
│   └── main.py                 # Isaac Sim 独立入口
├── lerobot/
│   ├── scripts/control_robot.py # 遥操作、采集、回放、推理入口
│   └── scripts/train.py         # 模仿学习训练入口
├── assets/                     # 仿真资产，通常通过子模块或 Hugging Face 下载
├── datasets/                   # LeRobotDataset 数据集目录
├── challenge2026_baseline/     # 预训练权重目录
├── run.sh                      # Docker/Isaac Sim 启动脚本
└── run_walker_s2_teleop.sh      # Walker S2 遥操作脚本
```

## 快速开始

### 1. 克隆仓库和子模块

```bash
git clone --recursive https://github.com/Logic-TARS/UBTECH-Robot-Competition-2026.git
cd UBTECH-Robot-Competition-2026
```

如果已经克隆但没有拉取子模块：

```bash
git submodule update --init --recursive
```

### 2. 下载数据和权重

```bash
pip install huggingface-hub

huggingface-cli download UBTECH-Robotics/challenge2026_dataset \
  --local-dir ./datasets \
  --repo-type dataset

huggingface-cli download UBTECH-Robotics/challenge2026_baseline \
  --local-dir ./challenge2026_baseline \
  --repo-type model
```

### 3. 启动容器

```bash
chmod +x run.sh
sudo ./run.sh
```

远程服务器或无显示环境可使用：

```bash
sudo ./run.sh --headless
```

### 4. 遥操作 Walker S2

```bash
/isaac-sim/python.sh lerobot/scripts/control_robot.py \
  --robot.type=walker_s2_sim \
  --control.type=teleoperate \
  --control.task=Conveyor_Sorting \
  --control.fps=30 \
  --control.display_cameras=true
```

### 5. 采集训练数据

```bash
/isaac-sim/python.sh lerobot/scripts/control_robot.py \
  --robot.type=walker_s2_sim \
  --control.type=record \
  --control.task=Conveyor_Sorting \
  --control.root=./datasets/Conveyor_Sorting/v1 \
  --control.single_task="Conveyor_Sorting" \
  --control.repo_id=local/Conveyor_Sorting \
  --control.num_episodes=50 \
  --control.fps=30 \
  --control.video=true \
  --control.push_to_hub=false
```

### 6. 训练 ACT 策略

```bash
/isaac-sim/python.sh lerobot/scripts/train.py \
  --dataset.repo_id=local/Conveyor_Sorting \
  --dataset.root=./datasets/Conveyor_Sorting/v1 \
  --policy.type=act \
  --policy.device=cuda \
  --policy.use_amp=true \
  --output_dir=challenge2026_baseline/Conveyor_Sorting/act_001 \
  --job_name=conveyor_sorting_act \
  --batch_size=8 \
  --steps=100000 \
  --save_checkpoint=true
```

## 当前成果与待补充内容

目前仓库已经保留并整理了 GHRC 2026 baseline 的主要仿真、数据采集、训练和推理入口，并围绕传送带分拣任务进行了配置理解和实验准备。后续建议继续补充以下材料，让项目更像完整作品集：

- 传送带速度调整前后的行为对比
- 遥操作采集的视频或 GIF
- 数据集规模：episode 数量、相机视角、动作维度、采样频率
- ACT / Pi0 训练曲线和推理成功率
- 失败案例分析：抓取时机、物体滑动、误分拣、reset 不稳定等
- 最终比赛成绩或阶段性得分

## 这个项目展示的能力

这个项目主要展示我在机器人学习和仿真工程方向的实践能力：能够阅读并改造复杂官方 baseline，理解 Isaac Sim 与 LeRobot 的接口关系，围绕具体比赛任务搭建数据采集和模仿学习流程，并针对动态分拣这类工业操作任务进行配置调试和实验设计。

对于机器人仿真、具身智能、模仿学习、数据采集平台或工业自动化相关岗位，这个仓库可以作为我参与大型机器人 baseline 改造和比赛任务落地的项目案例。

## 致谢与来源

本项目基于 UBTECH / GHRC 2026 官方 baseline、Hugging Face LeRobot 和 NVIDIA Isaac Sim 生态进行参赛开发。底层框架、部分资产、任务定义和预训练资源来自官方 baseline 与相关开源项目；本仓库重点展示我在此基础上的复现、配置、任务适配和实验整理工作。

## 作者

- GitHub: [Logic-TARS](https://github.com/Logic-TARS)
