# UBTECH Walker S2 Simulation & Teleoperation

这个仓库是在 LeRobot 基础上接入 UBTECH Walker S2 / Isaac Sim 仿真的项目，主要用于 Global Humanoid Robot Challenge 2026 相关任务的仿真、遥操作和数据采集。

队友第一次拿到仓库时，优先看这份 README。更细的脚本说明在 [docs/run_walker_s2_teleop.md](docs/run_walker_s2_teleop.md)。

## 项目能做什么

- 启动 Isaac Sim 容器环境
- 加载 Walker S2 仿真机器人和比赛任务场景
- 使用 LeRobot 的 `walker_s2_sim` 机器人接口进行键盘遥操作
- 采集 LeRobot 格式数据集，支持续录和新建版本
- 支持 4 个任务场景：零件分拣、传送带分拣、泡沫嵌入、装箱

## 目录结构

```text
.
├── run.sh                         # 创建/启动 Isaac Sim + LeRobot Docker 容器
├── run_walker_s2_teleop.sh        # 一键进入容器并启动 Walker S2 遥操作采集
├── Ubtech_sim/                    # Isaac Sim 仿真环境、任务配置和场景构建代码
│   ├── config/                    # 4 个任务的 YAML 配置
│   ├── source/                    # 场景、机器人、IK、数据记录等模块
│   └── main.py                    # 仿真入口
├── lerobot/                       # LeRobot 代码及本项目新增的 Walker S2 接口
├── assets/                        # USD / URDF / STL 等仿真资产
├── datasets/                      # 本地采集的数据集，不建议直接提交大文件
└── docs/                          # 补充文档
```

## 环境要求

宿主机需要准备：

- Linux 系统
- NVIDIA GPU 和可用驱动
- Docker
- NVIDIA Container Toolkit
- 可用的 Isaac Sim / LeRobot Docker 镜像

默认镜像名在 [run.sh](run.sh) 里：

```bash
isaac_sim_lerobot_v1.0_patched:latest
```

如果你本机镜像名不同，可以启动时覆盖：

```bash
IMAGE_NAME=你的镜像名:tag ./run.sh
```

## 第一次启动

克隆仓库后，在项目根目录执行：

```bash
./run.sh
```

脚本会做这些事：

- 检查 Docker 和 NVIDIA GPU
- 检查图形显示环境
- 挂载当前项目到容器的 `/workspace/lerobot_0.5.1`
- 挂载 Isaac Sim 和 Hugging Face 缓存
- 进入容器并执行 `pip install -e . --no-deps`

如果服务器没有显示器或不需要图形界面：

```bash
./run.sh --headless
```

默认容器名是：

```bash
isaac_sim_ubt
```

如果想换容器名：

```bash
CONTAINER_NAME=my_ubtech_container ./run.sh
```

## 日常遥操作采集

确保容器已经由 `run.sh` 创建过，然后在仓库根目录执行：

```bash
./run_walker_s2_teleop.sh
```

这个脚本会在容器中运行：

```bash
/isaac-sim/python.sh lerobot/scripts/teleop_and_record.py \
  --robot.type=walker_s2_sim \
  --control.type=teleoperate \
  --control.task=Conveyor_Sorting \
  --control.fps=30 \
  --control.display_cameras=true \
  --control.teleop_time_s=100000000 \
  --dataset.mode=continue \
  --repo_id=Logic-TARS/ubtech-task \
  --save_path=datasets/task2/v2 \
  --vcodec=h264
```

默认任务是 `Conveyor_Sorting`，默认保存到 `datasets/task2/v2`，默认模式是续录。

## 采集按键

进入采集程序后，常用按键如下：

| 按键 | 作用 |
| --- | --- |
| `Enter` | 开始当前 episode 录制 |
| 右方向键 | 提前结束并保存当前 episode |
| 左方向键 | 丢弃当前 episode 并重录 |
| `Q` | 退出程序 |

脚本里的 `--control.teleop_time_s` 设置得很长，所以通常手动用右方向键结束并保存一集。

## 切换任务

当前支持 4 个任务：

| 任务编号 | `--control.task` | 配置文件 | 默认数据目录 |
| --- | --- | --- | --- |
| 1 | `Part_Sorting` | `Ubtech_sim/config/Part_Sorting.yaml` | `datasets/task1` |
| 2 | `Conveyor_Sorting` | `Ubtech_sim/config/Conveyor_Sorting.yaml` | `datasets/task2` |
| 3 | `Foam_Inlaying` | `Ubtech_sim/config/Foam_Inlaying.yaml` | `datasets/task3` |
| 4 | `Packing_Box` | `Ubtech_sim/config/Packing_Box.yaml` | `datasets/task4` |

要切换任务，编辑 [run_walker_s2_teleop.sh](run_walker_s2_teleop.sh) 中这一行：

```bash
--control.task=Conveyor_Sorting \
```

例如切到装箱任务：

```bash
--control.task=Packing_Box \
```

同时建议把保存路径也切到对应任务目录：

```bash
SAVE_PATH=datasets/task4/v1 ./run_walker_s2_teleop.sh
```

## 数据集保存规则

脚本支持用环境变量覆盖数据集相关配置：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATASET_MODE` | `continue` | `continue` 续录；`new` 新建 |
| `SAVE_PATH` | `datasets/task2/v2` | 数据保存路径 |
| `HF_REPO_ID` | `Logic-TARS/ubtech-task` | Hugging Face dataset repo id |
| `HF_TOKEN_FILE` | `.secrets/hf_token` | 本地 token 文件路径 |

日常续录：

```bash
./run_walker_s2_teleop.sh
```

新建一个版本：

```bash
DATASET_MODE=new SAVE_PATH=datasets/task2/v3 ./run_walker_s2_teleop.sh
```

保存到自己的 Hugging Face 数据集：

```bash
HF_REPO_ID=你的用户名/你的数据集 ./run_walker_s2_teleop.sh
```

如果需要 Hugging Face token：

```bash
mkdir -p .secrets
printf '%s' '你的_HF_TOKEN' > .secrets/hf_token
chmod 600 .secrets/hf_token
```

也可以直接用环境变量：

```bash
export HF_TOKEN='你的_HF_TOKEN'
```

不要把 `.secrets/`、大数据集、缓存目录提交到 GitHub。

## 常用命令

启动容器：

```bash
./run.sh
```

无头模式启动容器：

```bash
./run.sh --headless
```

启动默认任务采集：

```bash
./run_walker_s2_teleop.sh
```

新建数据集版本：

```bash
DATASET_MODE=new SAVE_PATH=datasets/task2/v3 ./run_walker_s2_teleop.sh
```

使用其他容器名：

```bash
CONTAINER_NAME=isaac_sim_ubt ./run_walker_s2_teleop.sh
```

使用其他容器工作目录：

```bash
CONTAINER_WORKDIR=/workspace/lerobot_0.5.1 ./run_walker_s2_teleop.sh
```

## 直接运行仿真入口

如果只想运行 `Ubtech_sim` 里的仿真入口，可以在容器内执行：

```bash
/isaac-sim/python.sh Ubtech_sim/main.py
```

任务场景由 `Ubtech_sim/config/*.yaml` 控制。资产路径默认使用：

```yaml
root_path: "../assets/resources/"
```

## 常见问题

### 1. `docker command not found`

宿主机没有安装 Docker，或当前 shell 找不到 `docker` 命令。先安装 Docker 并确认：

```bash
docker --version
```

### 2. `nvidia-smi` 失败

Isaac Sim 需要 NVIDIA GPU。先确认宿主机驱动正常：

```bash
nvidia-smi
```

### 3. `DISPLAY 未设置`

图形模式需要可用显示器和 X11。没有图形环境时使用：

```bash
./run.sh --headless
```

### 4. `container 'isaac_sim_ubt' does not exist`

说明还没创建默认容器，先运行：

```bash
./run.sh
```

如果你的容器名不是 `isaac_sim_ubt`：

```bash
CONTAINER_NAME=你的容器名 ./run_walker_s2_teleop.sh
```

### 5. 视频编码报错

脚本固定使用：

```bash
--vcodec=h264
```

这是为了避开 Isaac Sim Python 环境里可能不支持 `libsvtav1` 的问题。除非确认环境支持，不建议改成其他编码器。

### 6. 数据目录权限错误

如果 `datasets/` 写入失败，通常是容器内用户和宿主机文件属主不一致。可以在宿主机修正目录权限：

```bash
sudo chown -R "$USER:$USER" datasets
```

## 协作约定

- 代码改动尽量小步提交，提交信息写清楚改了哪个任务或哪个模块
- 不提交 `.secrets/`、`outputs/`、`logs/`、大型 `datasets/` 文件
- 修改任务配置时，在 PR 或 commit 里说明改了哪个 YAML、影响哪个任务
- 采集数据前确认 `SAVE_PATH` 和 `DATASET_MODE`，避免把新数据写错版本

## 参考文档

- [Walker S2 遥操作脚本说明](docs/run_walker_s2_teleop.md)
- [Ubtech_sim 仿真模块说明](Ubtech_sim/README.md)
- [LeRobot 中文 README](README_zh.md)
