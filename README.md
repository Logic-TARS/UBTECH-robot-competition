# Global Humanoid Robot Challenge 2026 Baseline

基于 [LeRobot](https://github.com/huggingface/lerobot) 框架的 Walker S2 人形机器人仿真、数据采集与训练基线。

---

## 环境要求

- NVIDIA GPU + 驱动
- Docker + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
- Python 3.11+

---

## 快速开始

只需三步：

```bash
# 1. 拉取代码（含仿真资源子模块）
git clone --recursive <repo-url>
cd UBTECH

# 2. 构建 Docker 镜像（首次约 10 分钟）
docker build -t ubtech:v0 .

# 3. 一键启动
./run.sh
```

进入容器后即可使用以下命令。

### 资源下载（按需）

训练数据和预训练权重托管在 Hugging Face，需要时拉取：

```bash
pip install huggingface-hub

# 训练数据集
huggingface-cli download UBTECH-Robotics/challenge2026_dataset --local-dir ./datasets --repo-type dataset

# 预训练权重
huggingface-cli download UBTECH-Robotics/challenge2026_baseline --local-dir ./challenge2026_baseline --repo-type model
```

---

## run.sh 用法

```bash
./run.sh                  # 交互模式
./run.sh --headless       # 无头模式（远程服务器）
IMAGE_NAME=my:v1 ./run.sh # 自定义镜像名
```

启动后自动进入容器的 `/workspace/GlobalHumanoidRobotChallenge2026_Baseline` 目录，项目代码以可编辑模式安装，宿主机的代码修改即时生效。

---

## 容器内常用命令

### 遥操作（手动采集）

```bash
# 启动仿真 + 键盘遥操作（Part_Sorting 为例）
/isaac-sim/python.sh src/lerobot/scripts/lerobot_teleoperate.py \
    --robot.type=walker_s2_sim \
    --task=Part_Sorting \
    --teleop.type=walker_s2_keyboard \
    --teleop.evdev_device_path=/dev/input/event2
```

支持的任务：`Part_Sorting`、`Conveyor_Sorting`、`Foam_Inlaying`、`Packing_Box`

### 自动采集

```bash
# 免人工干预，自动循环采集 Part_Sorting 数据
/isaac-sim/python.sh src/lerobot/scripts/auto_collect_main.py \
    --robot.type=walker_s2_sim \
    --auto_collect.task=Part_Sorting \
    --auto_collect.repo_id=local/task1_data \
    --auto_collect.num_episodes=50
```

### 训练

```bash
python lerobot/scripts/lerobot_train.py \
    --policy=act \
    --dataset.repo_id=UBTECH-Robotics/challenge2026_dataset \
    --output_dir=outputs/train
```

### 推理

```bash
python lerobot/scripts/lerobot_eval.py \
    --robot.type=walker_s2_sim \
    --task=Part_Sorting \
    -p outputs/train/checkpoints/last/pretrained_model
```

---

## 键盘遥操作按键

| 按键 | 功能 |
|------|------|
| `1` / `3` | 末端 ±Y 平移 |
| `4` / `6` | 末端 ±X 平移 |
| `7` / `9` | 末端 ±Z 平移 |
| `U` / `J` | 末端 ±Rx 旋转 |
| `I` / `K` | 末端 ±Ry 旋转 |
| `O` / `L` | 末端 ±Rz 旋转 |
| `F` | 夹爪闭合 / 张开 |
| `T` | 切换左右臂 |
| `R` | 录制开始 / 停止 |

---

## 项目结构

```
UBTECH/
├── src/          # 项目源码
├── lerobot/      # LeRobot 框架
├── Ubtech_sim/   # Isaac Sim 仿真场景
├── tests/        # 测试
├── assets/       # 仿真资源（Git submodule）
├── datasets/     # 数据集
├── outputs/      # 训练 / 推理输出
├── docs/         # 详细文档
├── scripts/      # 辅助脚本
├── Dockerfile
├── pyproject.toml
├── setup.py
├── run.sh        # 一键启动
└── README.md
```
