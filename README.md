# UBTECH Walker S2 Teleoperation Quickstart

本文档介绍脚本 `/home/1ctnltug/UBTECH/run_walker_s2_teleop.sh` 的用途、执行流程、可配置项、数据集行为与常见问题排查。

## 1. 脚本作用

`run_walker_s2_teleop.sh` 是一个一键启动脚本，用于在 Docker 容器 `isaac_sim_ubt` 中运行：

- `lerobot/scripts/teleop_and_record.py`
- 机器人类型：`walker_s2_sim`
- 控制模式：`teleoperate`（键盘遥操作）
- 默认任务：`Conveyor_Sorting`

它会自动完成以下工作：

1. 检查宿主机是否安装 `docker`
2. 检查容器是否存在
3. 如果容器未启动，自动 `docker start`
4. 自动判断是否分配 TTY（交互终端）
5. 在容器工作目录执行采集脚本

## 2. 脚本位置与内容

- 脚本路径：`/home/1ctnltug/UBTECH/run_walker_s2_teleop.sh`
- 当前默认启动参数：

```bash
/isaac-sim/python.sh lerobot/scripts/teleop_and_record.py \
  --robot.type=walker_s2_sim \
  --control.type=teleoperate \
  --control.task=Conveyor_Sorting \
  --control.fps=30 \
  --control.display_cameras=true \
  --control.teleop_time_s=100000000
```

## 3. 最常用启动方式

在仓库根目录执行：

```bash
bash /home/1ctnltug/UBTECH/run_walker_s2_teleop.sh
```

## 4. 可用任务（对应任务编号）

脚本中 `--control.task` 支持以下 4 个值：

1. `Part_Sorting`（任务 1）
2. `Conveyor_Sorting`（任务 2）
3. `Foam_Inlaying`（任务 3）
4. `Packing_Box`（任务 4）

如果要切换任务，直接修改脚本里的 `--control.task=...`。

## 5. 环境变量配置

脚本支持两个环境变量：

- `CONTAINER_NAME`：容器名（默认 `isaac_sim_ubt`）
- `CONTAINER_WORKDIR`：容器内工作目录（默认 `/workspace/GlobalHumanoidRobotChallenge2026_Baseline`）

示例：

```bash
CONTAINER_NAME=isaac_sim_ubt \
CONTAINER_WORKDIR=/workspace/GlobalHumanoidRobotChallenge2026_Baseline \
bash /home/1ctnltug/UBTECH/run_walker_s2_teleop.sh
```

## 6. 采集时的交互按键

在 `teleop_and_record.py` 里，流程控制按键是：

- `Enter`：开始当前 Episode 录制
- `→`（右方向键）：提前结束并保存当前 Episode
- `←`（左方向键）：丢弃当前 Episode 并重录
- `Q`：退出整个程序

说明：脚本已加入保护逻辑，避免“0 帧 Episode 保存”导致崩溃。

## 7. 数据集存储与续录规则（当前已实现）

你当前代码里的规则如下：

- 任务目录映射：
  - 任务 1 -> `datasets/task1`
  - 任务 2 -> `datasets/task2`
  - 任务 3 -> `datasets/task3`
  - 任务 4 -> `datasets/task4`
- 默认模式：`continue`（续录）
  - 未明确说明时，会续录该任务下最新的 `vN`
- 新建模式：`new`
  - 明确要求新建时，创建下一个版本目录 `v(N+1)`

可用参数（传给 `teleop_and_record.py`）：

- `--dataset_mode=continue|new`
- `--dataset.mode=continue|new`（兼容写法）
- `--new_dataset`（等价 `new`）

注意：当前 `run_walker_s2_teleop.sh` 没显式传 `dataset_mode`，因此默认就是 `continue`。

## 8. 常见问题与排查

### 8.1 容器不存在

报错：

```text
Error: container 'isaac_sim_ubt' does not exist.
```

处理：确认容器名，或用 `CONTAINER_NAME=...` 指定正确名称。

### 8.2 看不到画面

脚本默认 `--control.display_cameras=true`，应为有界面模式。

- 如果你手动改成 `false`，脚本会进入 headless
- 可在脚本内改回 `true`

### 8.3 数据集目录权限问题

若 `datasets` 出现 `Permission denied`，通常是容器内 root/nobody 写入造成。

建议：

1. 用容器 root 修复目录属主
2. 确保宿主机目录归属当前用户再继续采集

### 8.4 视频保存报 PyAV 错误

若出现 `add_stream_from_template` 相关报错，当前代码已加入 PyAV 兼容回退（低版本自动走 ffmpeg concat）。

## 9. 推荐工作流

1. 先确认任务（1/2/3/4）并改好 `--control.task`
2. 直接运行 `run_walker_s2_teleop.sh`
3. 默认续录上一次同任务数据集
4. 需要新建版本时，在脚本命令末尾补 `--dataset.mode=new`

## 10. 附：可直接复制的手动启动命令（不经脚本）

```bash
docker exec -it -w /workspace/GlobalHumanoidRobotChallenge2026_Baseline isaac_sim_ubt \
  bash -lc "/isaac-sim/python.sh lerobot/scripts/teleop_and_record.py \
    --robot.type=walker_s2_sim \
    --control.type=teleoperate \
    --control.task=Conveyor_Sorting \
    --control.fps=30 \
    --control.display_cameras=true \
    --control.teleop_time_s=100000000 \
    --dataset.mode=continue"
```

如果要新建数据集版本，把最后一行改成 `--dataset.mode=new`。
