# UBTECH Walker S2 仿真遥操作与数据采集

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Isaac Sim](https://img.shields.io/badge/Isaac%20Sim-5.1-76B900)
![LeRobot](https://img.shields.io/badge/LeRobot-Teleoperation-FF6F00)
![Robot](https://img.shields.io/badge/Robot-Walker%20S2-4B8BBE)
![Dataset](https://img.shields.io/badge/Dataset-LeRobot%20Format-555555)

面向 2026 全球人形机器人挑战赛的 Walker S2 仿真遥操作与 LeRobot 数据采集工程。

本仓库提供 **Global Humanoid Robot Challenge 2026** 中 **UBTECH Walker S2** 相关任务使用的仿真接入、遥操作数据采集流程和容器化运行环境，整合 Isaac Sim、LeRobot、任务场景配置、双臂控制工具与 Hugging Face 数据集对接。

本比赛仓库基于 LeRobot 扩展，因此 Python 包名仍为 `lerobot`，并保留上游软件包元数据。

[English](README.md)

## 背景

Walker S2 比赛任务不只是一次性的仿真演示。可复用的工程流程需要统一协调 Isaac Sim 运行环境、机器人与场景资产、键盘遥操作、相机记录、任务选择、数据集版本以及 Hugging Face 访问。

本项目在 LeRobot 基础上构建这套流程，支持四类比赛场景，并提供场景构建、双臂逆运动学、抓取规划、坐标转换和结构化数据记录组件。

## 安装

### 依赖

- Linux
- Docker 与 NVIDIA Container Toolkit
- NVIDIA GPU，并确保 `nvidia-smi` 正常运行
- 图形模式需要 X11，也可使用项目提供的无头模式
- Isaac Sim 镜像 `isaac-sim-nijie-lerobot:v5`，或通过 `IMAGE_NAME` 指定兼容镜像
- `assets` 子模块需要具有 Hugging Face 仓库 `UBTECH-Robotics/challenge2026_assets` 的访问权限

克隆仓库并同时拉取仿真资产：

```bash
git clone --recurse-submodules https://github.com/Logic-TARS/UBTECH-robot-competition.git
cd UBTECH-robot-competition
```

如果克隆时没有拉取子模块，可单独初始化：

```bash
git submodule update --init --recursive
```

创建并进入 Isaac Sim + LeRobot 容器：

```bash
./run.sh
```

`run.sh` 会检查 Docker、NVIDIA GPU 和显示环境，挂载项目及缓存目录，并在容器内以 editable 模式安装本地源码。

## 使用

以图形模式启动容器：

```bash
./run.sh
```

不使用 X11 启动：

```bash
./run.sh --headless
```

容器创建完成后，启动带引导的 Walker S2 遥操作与数据采集流程：

```bash
./run_walker_s2_teleop.sh
```

通过环境变量切换任务或新建数据集版本：

```bash
TASK=Packing_Box ./run_walker_s2_teleop.sh
DATASET_MODE=new SAVE_PATH=datasets/task2/v3 ./run_walker_s2_teleop.sh
```

在容器中直接运行仿真入口：

```bash
/isaac-sim/python.sh Ubtech_sim/main.py
```

### 录制按键

| 按键 | 作用 |
|---|---|
| `Enter` | 开始录制当前 episode |
| 右方向键 | 结束并保存当前 episode |
| 左方向键 | 丢弃并重新录制当前 episode |
| `Q` | 退出程序 |

## 项目亮点

- 在 Isaac Sim 中接入 UBTECH Walker S2 机器人、比赛场景和仿真资产。
- 新增 `walker_s2_sim` LeRobot 机器人接口，用于键盘遥操作和数据记录。
- 支持 `Part_Sorting`、`Conveyor_Sorting`、`Foam_Inlaying` 和 `Packing_Box`。
- 提供容器启动脚本，检查 Docker、GPU、X11/headless、缓存挂载和 editable install。
- 提供引导式采集脚本，统一管理任务、数据集续录或新建、保存路径、Hugging Face 仓库、帧率、相机显示和视频编码。
- 包含双臂逆运动学、抓取规划、坐标转换、场景构建和结构化数据记录模块。
- 支持将物体位姿记录为 CSV、相机数据记录为 HDF5，并保存为 LeRobot 数据集格式。

## 项目成果

| 问题 | 实现方式 | 效果 |
|---|---|---|
| Isaac Sim 与 LeRobot 需要协调 Docker、GPU、显示和路径配置 | `run.sh` 检查宿主机并挂载项目、Isaac Sim 与 Hugging Face 缓存 | 团队成员可通过一条命令进入一致的容器运行环境 |
| 遥操作命令包含大量任务和数据集参数 | `run_walker_s2_teleop.sh` 统一默认值并提供交互式配置 | 减少手动参数，便于重复采集和切换任务 |
| 多任务数据容易写入错误任务或版本 | 使用 `TASK`、`DATASET_MODE` 和 `SAVE_PATH` 控制任务与数据集 | 四类任务共享一致的数据版本管理流程 |
| 双臂操作不能只依赖关节级命令 | 使用 `GraspPlanner`、`DualArmIK`、`CoordinateTransform` 和 `RobotArticulation` 组成控制链路 | 可将场景物体位姿转换为规划后的双臂 IK 目标 |
| 示教数据需要可复用的训练格式 | 使用 LeRobot 数据集及 `continue`、`new` 两种模式 | 数据可用于后续模仿学习、ACT、Diffusion Policy 或 VLA 流程 |


## 任务

| 编号 | 任务 | 说明 | 默认数据目录 |
|---|---|---|---|
| 1 | `Part_Sorting` | 零件分拣 | `datasets/task1` |
| 2 | `Conveyor_Sorting` | 传送带分拣 | `datasets/task2` |
| 3 | `Foam_Inlaying` | 泡棉嵌入 | `datasets/task3` |
| 4 | `Packing_Box` | 装箱 | `datasets/task4` |

## 架构

数据采集流程连接宿主机启动脚本、容器化 LeRobot 运行环境、Walker S2 仿真接口、任务场景和数据集写入器：

```text
宿主机
├── run.sh
│   └── Isaac Sim + LeRobot 容器
└── run_walker_s2_teleop.sh
    └── lerobot/scripts/teleop_and_record.py
        └── walker_s2_sim
            ├── 任务场景与相机
            ├── 键盘遥操作
            └── LeRobot 数据集记录
```

`Ubtech_sim` 包含底层仿真组件：

| 组件 | 职责 |
|---|---|
| `SceneBuilder` | 加载机器人、桌子、箱子、零件和任务场景 |
| `RobotArticulation` | 读取机器人状态并执行双臂控制 |
| `DualArmIK` | 使用阻尼最小二乘法求解双臂逆运动学 |
| `GraspPlanner` | 选择手臂并规划抓取姿态和 TCP 偏移 |
| `CoordinateTransform` | 将世界坐标转换到机器人基座坐标系 |
| `DataLogger` | 将物体位姿记录为 CSV，将相机帧记录为 HDF5 |

## 配置

| 环境变量 | 默认值 | 使用位置 |
|---|---|---|
| `IMAGE_NAME` | `isaac-sim-nijie-lerobot:v5` | `run.sh` |
| `CONTAINER_NAME` | `isaac_sim_ubt` | 两个启动脚本 |
| `CONTAINER_WORKSPACE` | `/workspace/lerobot_0.5.1` | `run.sh` |
| `CONTAINER_WORKDIR` | `/workspace/lerobot_0.5.1` | `run_walker_s2_teleop.sh` |
| `TASK` | `Conveyor_Sorting` | 遥操作启动脚本 |
| `DATASET_MODE` | `continue` | 遥操作启动脚本 |
| `SAVE_PATH` | `datasets/task2/v2` | 遥操作启动脚本 |
| `HF_REPO_ID` | `Logic-TARS/ubtech-task` | 遥操作启动脚本 |
| `FPS` | `30` | 遥操作启动脚本 |
| `DISPLAY_CAMERAS` | `true` | 遥操作启动脚本 |
| `VCODEC` | `h264` | 遥操作启动脚本 |

需要 Hugging Face 身份验证时，设置 `HF_TOKEN` 或将 token 写入 `.secrets/hf_token`。不要提交 token 或 `.secrets` 目录。

## 仓库结构

```text
.
├── run.sh                         # 创建并进入 Isaac Sim 容器
├── run_walker_s2_teleop.sh        # 启动引导式遥操作和数据采集
├── Ubtech_sim/                    # 仿真场景、配置和控制
│   ├── config/                    # 四个任务 YAML 文件
│   ├── source/                    # 场景、机器人、IK、规划和记录模块
│   └── main.py                    # 直接仿真入口
├── lerobot/                       # LeRobot 源码和 Walker S2 接入
├── assets/                        # 仿真资产子模块
├── datasets/                      # 本地数据集，不应提交大文件
└── docs/                          # LeRobot 补充文档
```

## 参考资料

- [UBTECH 仿真模块](Ubtech_sim/README.md)
- [LeRobot](https://github.com/huggingface/lerobot)


## 参与贡献

欢迎通过 [GitHub Issues](https://github.com/Logic-TARS/UBTECH-robot-competition/issues) 提问或反馈问题，也欢迎提交 Pull Request。

不要提交 `.secrets/`、`outputs/`、`logs/` 或大型生成数据集。采集数据前请检查 `TASK`、`SAVE_PATH` 和 `DATASET_MODE`。修改任务配置的 Pull Request 应说明受影响的 YAML 文件和任务。

## 许可证

[Apache-2.0](LICENSE) © 2024 The Hugging Face team。许可证文件同时包含所集成第三方项目的归属声明。
