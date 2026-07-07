# 🦾 UBTECH Walker S2 仿真遥操作与数据采集项目

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Isaac Sim](https://img.shields.io/badge/Isaac%20Sim-5.1-76B900)
![LeRobot](https://img.shields.io/badge/LeRobot-Teleoperation-FF6F00)
![Robot](https://img.shields.io/badge/Robot-Walker%20S2-4B8BBE)
![Dataset](https://img.shields.io/badge/Dataset-LeRobot%20Format-555555)

> 本仓库用于展示我在 **Global Humanoid Robot Challenge 2026 / UBTECH Walker S2** 相关任务中的仿真环境接入、遥操作数据采集与工程化部署工作。  
> 项目基于 **Isaac Sim + LeRobot + Walker S2 仿真接口**，完成容器化运行、任务场景加载、键盘遥操作、LeRobot 格式数据集采集、Hugging Face 数据集对接与多任务配置管理。

---

## ✅ 项目亮点 / 可验证结果

- **Walker S2 仿真接入**：在 Isaac Sim 中加载 UBTECH Walker S2 机器人、比赛任务场景和仿真资产。
- **LeRobot 遥操作采集链路**：新增 / 接入 `walker_s2_sim` 机器人接口，通过 `teleop_and_record.py` 完成键盘遥操作与数据记录。
- **四类任务场景支持**：支持 `Part_Sorting`、`Conveyor_Sorting`、`Foam_Inlaying`、`Packing_Box` 四个任务场景。
- **Docker 一键运行环境**：封装 `run.sh`，自动检查 Docker、NVIDIA GPU、X11 / headless、缓存挂载和 editable install。
- **一键采集脚本**：封装 `run_walker_s2_teleop.sh`，支持任务选择、数据集续录 / 新建、保存路径、Hugging Face repo、FPS、相机显示和视频编码配置。
- **双臂 IK 与抓取规划模块**：`Ubtech_sim` 中包含 Walker S2 双臂 IK、抓取目标规划、世界坐标到机器人基座坐标转换、场景构建和数据记录模块。
- **数据记录能力**：支持目标物体位姿 CSV 记录、相机图像 HDF5 记录，以及 LeRobot 数据集格式保存。

---

## 🧩 问题—方法—效果

| 问题 | 解决方法 | 产生效果 |
|---|---|---|
| 原始 Isaac Sim / LeRobot 环境依赖复杂，队友首次部署容易卡在 Docker、GPU、X11 和路径配置上 | 编写 `run.sh`，自动检查 Docker、NVIDIA GPU、DISPLAY，挂载 Isaac Sim / Hugging Face 缓存，并支持 `--headless` 模式 | 降低部署门槛，使团队成员可以一键进入可用的 Isaac Sim + LeRobot 容器环境 |
| Walker S2 仿真任务需要稳定采集遥操作数据，但手动命令长、参数多、容易写错 | 封装 `run_walker_s2_teleop.sh`，统一管理任务名、FPS、相机显示、数据集模式、保存路径、HF repo 和 token | 将数据采集流程标准化，支持日常续录、新建版本和不同任务快速切换 |
| 多任务场景配置分散，任务切换容易导致保存路径和任务名不一致 | 将 4 个任务统一为 `Part_Sorting`、`Conveyor_Sorting`、`Foam_Inlaying`、`Packing_Box`，并通过环境变量 `TASK` / `SAVE_PATH` 控制 | 支持 4 类比赛任务场景快速切换，减少采集数据写错目录或覆盖版本的风险 |
| Walker S2 双臂抓取任务需要目标规划、坐标转换和 IK 控制，不能只靠底层关节命令 | 在 `Ubtech_sim` 中实现 `GraspPlanner`、`DualArmIK`、`CoordinateTransform`、`RobotArticulation` 等模块 | 形成从场景对象位姿到双臂 IK 控制的仿真控制链路，为后续策略学习和示教数据采集提供基础 |
| 比赛数据需要可复用、可上传和可追踪版本，而不是零散本地文件 | 采用 LeRobot 数据集格式，支持 `continue` 续录和 `new` 新建版本，并对接 Hugging Face dataset repo | 形成可持续扩展的数据采集工作流，便于后续模仿学习 / VLA / ACT / Diffusion Policy 训练使用 |

---

## 📊 实验结果 / 工程结果

| 指标 | 结果 |
|---|---|
| 比赛 / 项目方向 | Global Humanoid Robot Challenge 2026 / UBTECH Walker S2 仿真任务 |
| 机器人平台 | UBTECH Walker S2 |
| 仿真平台 | Isaac Sim 5.1 |
| 数据框架 | LeRobot |
| 运行方式 | Docker + NVIDIA GPU + Isaac Sim container |
| 遥操作入口 | `lerobot/scripts/teleop_and_record.py` |
| 机器人接口 | `walker_s2_sim` |
| 默认采集 FPS | 30 |
| 默认数据集模式 | `continue` 续录 |
| 默认任务 | `Conveyor_Sorting` |
| 支持任务数 | 4 个任务场景 |
| 支持任务 | `Part_Sorting`、`Conveyor_Sorting`、`Foam_Inlaying`、`Packing_Box` |
| 默认数据集仓库 | `Logic-TARS/ubtech-task` |
| 本地保存路径 | `datasets/task*/v*` |
| 仿真核心模块 | 场景构建、Walker S2 加载、双臂 IK、抓取规划、数据记录 |
| 已采集 episode 数 | 待补充 |
| 已采集数据总量 | 待补充 |
| 下游训练结果 | 待补充 |

> 可继续补充：每个任务的数据集条数、累计时长、成功率、示教视频、Hugging Face 数据集链接、下游 imitation learning / VLA 训练结果。

---

## 🧾 简历表述

> 面向 Global Humanoid Robot Challenge 2026 的 UBTECH Walker S2 仿真操作任务，基于 Isaac Sim 与 LeRobot 搭建 humanoid robot 遥操作数据采集链路，完成 Walker S2 仿真机器人接入、Docker 容器化运行、四类任务场景加载、键盘遥操作、LeRobot 格式数据集保存和 Hugging Face 数据集对接；针对 Isaac Sim 环境部署复杂、采集命令参数繁多和多任务数据版本易混乱等问题，封装 `run.sh` 与 `run_walker_s2_teleop.sh`，支持 GPU / X11 / headless 检查、任务切换、续录 / 新建数据集版本、保存路径配置和采集参数统一管理；同时在 `Ubtech_sim` 中维护双臂 IK、抓取规划、坐标转换、场景构建和 CSV / HDF5 数据记录模块，为后续模仿学习与具身策略训练提供可复用数据基础。

---

## 🎯 任务说明与技术难点

本项目面向 Walker S2 在仿真场景中的遥操作和数据采集，重点不是单次控制 demo，而是构建可持续扩展的数据生产管线。

当前支持 4 个任务：

| 任务编号 | 任务名 | 说明 | 默认数据目录 |
|---|---|---|---|
| 1 | `Part_Sorting` | 零件分拣 | `datasets/task1` |
| 2 | `Conveyor_Sorting` | 传送带分拣 | `datasets/task2` |
| 3 | `Foam_Inlaying` | 泡棉嵌入 | `datasets/task3` |
| 4 | `Packing_Box` | 装箱 | `datasets/task4` |

主要难点：

- **仿真环境重**：Isaac Sim 依赖 NVIDIA GPU、Docker、X11 / headless、缓存挂载和专用镜像。
- **遥操作采集链路长**：需要同时处理机器人接口、任务选择、相机显示、数据集保存、视频编码和 Hugging Face token。
- **多任务数据管理**：不同任务需要保存到不同数据目录，且需要区分续录和新建版本。
- **双臂控制复杂**：Walker S2 需要双臂 IK、目标姿态规划和坐标系转换支持。
- **后续训练可用性**：采集数据必须保持 LeRobot 格式，才能用于模仿学习或 VLA 训练。

---

## 🧠 核心方案

### 1. Docker + Isaac Sim 一键环境

`run.sh` 负责创建 / 启动 Isaac Sim + LeRobot 容器：

```bash
./run.sh

# 无显示器或服务器环境
./run.sh --headless

# 覆盖镜像名
IMAGE_NAME=my_image:v2 ./run.sh
```

脚本能力：

- 检查 Docker；
- 检查 NVIDIA GPU / `nvidia-smi`；
- 检查 X11 显示环境；
- 支持 headless 模式；
- 挂载项目目录到容器；
- 挂载 Isaac Sim cache，减少重复编译和下载；
- 挂载 Hugging Face cache；
- 自动执行 `pip install -e . --no-deps`。

### 2. Walker S2 遥操作采集入口

日常数据采集使用：

```bash
./run_walker_s2_teleop.sh
```

底层调用：

```bash
/isaac-sim/python.sh lerobot/scripts/teleop_and_record.py \
  --robot.type=walker_s2_sim \
  --control.type=teleoperate \
  --control.task=Conveyor_Sorting \
  --control.fps=30 \
  --control.display_cameras=true \
  --dataset.mode=continue \
  --repo_id=Logic-TARS/ubtech-task \
  --save_path=datasets/task2/v2 \
  --vcodec=h264
```

常用按键：

| 按键 | 作用 |
|---|---|
| `Enter` | 开始当前 episode 录制 |
| 右方向键 | 结束并保存当前 episode |
| 左方向键 | 丢弃当前 episode 并重录 |
| `Q` | 退出程序 |

### 3. 多任务与数据集版本管理

切换任务：

```bash
TASK=Packing_Box ./run_walker_s2_teleop.sh
```

新建数据集版本：

```bash
DATASET_MODE=new SAVE_PATH=datasets/task2/v3 ./run_walker_s2_teleop.sh
```

续录默认数据集：

```bash
./run_walker_s2_teleop.sh
```

常用环境变量：

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `TASK` | `Conveyor_Sorting` | 采集任务 |
| `DATASET_MODE` | `continue` | `continue` 续录；`new` 新建 |
| `SAVE_PATH` | `datasets/task2/v2` | 本地保存路径 |
| `HF_REPO_ID` | `Logic-TARS/ubtech-task` | Hugging Face dataset repo id |
| `FPS` | `30` | 采集帧率 |
| `DISPLAY_CAMERAS` | `true` | 是否显示相机画面 |
| `VCODEC` | `h264` | 视频编码 |

### 4. `Ubtech_sim` 仿真模块

`Ubtech_sim` 负责 Isaac Sim 场景、机器人和控制模块：

```text
Ubtech_sim/
├── config/                    # 四个任务的 YAML 配置
├── source/
│   ├── config_loader.py       # 配置加载与路径解析
│   ├── coordinate_utils.py    # 世界坐标 ↔ Pinocchio 基座坐标变换
│   ├── grasp_planner.py       # 抓取目标规划与实时跟踪
│   ├── DataLogger.py          # 位姿 CSV / 相机 HDF5 数据记录
│   ├── DualArmIK.py           # 基于 Pinocchio 的双臂 IK 求解器
│   ├── RobotArticulation.py   # Walker S2 Articulation 控制接口
│   └── SceneBuilder.py        # 场景构建
└── main.py                    # 仿真入口
```

核心模块说明：

| 模块 | 作用 |
|---|---|
| `SceneBuilder` | 加载桌子、箱子、零件、机器人和任务场景 |
| `RobotArticulation` | 获取关节状态、传感器数据，执行双臂控制 |
| `DualArmIK` | 基于 Pinocchio 的双臂阻尼最小二乘 IK |
| `GraspPlanner` | 根据目标物体位姿选择手臂、计算抓取姿态和 TCP 偏移 |
| `DataLogger` | 记录目标物体位姿 CSV 和相机图像 HDF5 |
| `CoordinateTransform` | 处理世界坐标系与机器人基座坐标系转换 |

---

## 🛠 技术栈

| Area | Tools / Components |
|---|---|
| Simulator | Isaac Sim 5.1 |
| Robot | UBTECH Walker S2 |
| Data Framework | LeRobot |
| Container | Docker, NVIDIA Container Toolkit |
| Kinematics | Pinocchio, Damped Least Squares IK |
| Dataset | LeRobot format, Hugging Face dataset repo |
| Recording | CSV, HDF5, h264 video |

---

## 📁 仓库结构

```text
.
├── run.sh                         # 创建 / 启动 Isaac Sim + LeRobot Docker 容器
├── run_walker_s2_teleop.sh        # 一键启动 Walker S2 遥操作采集
├── Ubtech_sim/                    # Isaac Sim 仿真环境、任务配置和场景构建代码
│   ├── config/                    # 4 个任务 YAML 配置
│   ├── source/                    # 场景、机器人、IK、数据记录等模块
│   └── main.py                    # 仿真入口
├── lerobot/                       # LeRobot 代码及 Walker S2 接口
├── assets/                        # USD / URDF / STL 等仿真资产
├── datasets/                      # 本地采集数据集，不建议提交大文件
└── docs/                          # 补充文档
```

---

## 🚀 常用命令

### 1. 启动容器

```bash
./run.sh
```

### 2. 无头模式启动

```bash
./run.sh --headless
```

### 3. 启动默认任务采集

```bash
./run_walker_s2_teleop.sh
```

### 4. 切换任务采集

```bash
TASK=Part_Sorting ./run_walker_s2_teleop.sh
TASK=Foam_Inlaying ./run_walker_s2_teleop.sh
TASK=Packing_Box ./run_walker_s2_teleop.sh
```

### 5. 新建数据集版本

```bash
DATASET_MODE=new SAVE_PATH=datasets/task2/v3 ./run_walker_s2_teleop.sh
```

### 6. 直接运行仿真入口

```bash
/isaac-sim/python.sh Ubtech_sim/main.py
```

---

## 📝 后续可补充材料

为了让该项目更适合简历和面试展示，建议继续补充：

- 每个任务已采集 episode 数量、总时长、成功率；
- LeRobot 数据集样例截图；
- 遥操作采集 GIF / MP4；
- Walker S2 双臂 IK 抓取过程视频；
- Hugging Face dataset 页面链接；
- 下游训练结果，例如 ACT / Diffusion Policy / VLA 在四个任务上的成功率；
- 不同任务的数据目录版本说明。

---

## 协作约定

- 不提交 `.secrets/`、`outputs/`、`logs/`、大型 `datasets/` 文件。
- 采集数据前确认 `TASK`、`SAVE_PATH` 和 `DATASET_MODE`，避免写错任务或版本。
- 修改任务配置时，在 commit 或 PR 中说明改了哪个 YAML、影响哪个任务。
- 代码改动尽量小步提交，提交信息写清楚改动模块。

---

## 参考文档

- [Ubtech_sim 仿真模块说明](Ubtech_sim/README.md)
- [LeRobot 中文 README](README_zh.md)
