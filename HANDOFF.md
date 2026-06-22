# 任务交接文档：四任务脚本跑通 + 75% 准确率

**日期**: 2026-05-28（创建），2026-06-21（更新）
**目标**: 将 Part_Sorting / Conveyor_Sorting / Foam_Inlaying / Packing_Box 四个任务的自动采集 → 训练 → 评估流程全部跑通，每个任务的评估准确率 (pc_success) 达到 ≥75%。

## 2026-06-21 状态更新

### 关键发现
1. **Task 1 eval 阻塞 bug 已修复** — `SceneBuilder.check_success()` 方法此前不存在，eval 脚本调用了不存在的方法，异常被吞，导致成功率永远 0%。已在 `Ubtech_sim/source/SceneBuilder.py` 新增该方法，通过箱体 Y 轴切分判定 Part A/B 归位。0% 的 eval 结果不能证明模型失败。
2. **Task 1 SmolVLA 195k checkpoint 不完整** — 仅含 `config.json` + `model.safetensors`，缺 preprocessor/postprocessor/training_state。训练在 195k 保存检查点时崩溃。190k 是最后一个完整 checkpoint。
3. **SmolVLA 训练配置问题** — `load_vlm_weights=false`，403M 参数从随机初始化训练。`prepare_state()` 未消费 `environment_state`（28D 物体位姿），模型只能靠视觉判断物体位置。
4. **SmolVLM2 模型缓存不完整** — `HuggingFaceTB/SmolVLM2-500M-Video-Instruct` 未下载到本地，eval 会报 OSError。需宿主机 `huggingface-cli download` 后再跑。

### 当前数据/训练/评估现状
| 任务 | 采集 | 训练 | 评估 |
|------|------|------|------|
| Task 1 Part_Sorting | ✅ batch1 ×4 | SmolVLA 190k (完整) | ⚠️ eval bug 已修复，待重评 |
| Task 2 Conveyor_Sorting | ✅ batch1 ×6 | ACT 100k | 未评 |
| Task 3 Foam_Inlaying | ✅ batch1 ×4 | 未训 | 未评 |
| Task 4 Packing_Box | ✅ batch1 ×1 | 未训 | 未评 |

### 下一步优先级
1. 下载 SmolVLM2 模型到本地 HF cache
2. 用 190k checkpoint 重新评估 Task 1（10 episodes → 50 episodes）
3. 根据真实 eval 结果决定 Task 1 是否重训
4. 启动 Task 2 ACT eval

---

## 1. 环境状态（已就绪）

| 项目 | 状态 | 说明 |
|------|------|------|
| Docker | ✅ 已安装 | v28.2.2 |
| NVIDIA GPU | ✅ 可用 | RTX5880-Ada-24Q, 24GB 显存 |
| Isaac Sim 镜像 | ✅ 已存在 | `isaacsim5.1_lerobot5.1_ubtech:v1` (23.8GB) |
| 项目代码 | ✅ 挂载 | 容器内 `/workspace/GlobalHumanoidRobotChallenge2026_Baseline` |

---

## 2. 数据集现状

### 2.1 各任务采集情况

| 任务 | 目录 | 有效 episodes | 状态 |
|------|------|---------------|------|
| **Task 1: Part_Sorting** | `datasets/Part_Sorting/batch1_20260528_060209/` | **100** episodes (25,800 frames) | ✅ 数据充足 |
| **Task 2: Conveyor_Sorting** | `datasets/Conveyor_Sorting/batch1_20260528_110841/` | **17** episodes (10,602 frames) | ⚠️ 不足，需补采 |
| **Task 3: Foam_Inlaying** | `datasets/Foam_Inlaying/batch1_20260527_092815/` | **1** episode (675 frames) | ❌ 严重不足 |
| **Task 4: Packing_Box** | `datasets/Packing_Box/batch1/` | **0** episodes | ❌ 无数据 |

> **注意**: `batch1/` 目录（非时间戳目录）的 info.json 显示 episodes=0，是空的。实际数据在带时间戳的子目录中。

### 2.2 已有训练数据

| 数据集 | 路径 | Episodes | Frames | FPS |
|--------|------|----------|--------|-----|
| Task 1 训练集 | `datasets/train/task1/` | 200 | 539,039 | 20 |

### 2.3 已有模型

| 模型 | 路径 | 训练步数 | 说明 |
|------|------|----------|------|
| Task 1 SmolVLA (190k) | `outputs/train/task1_smolvla/checkpoints/190000/pretrained_model/` | 190K/200K | 最后一个完整 checkpoint，可评估 |
| Task 1 SmolVLA (195k) | `outputs/train/task1_smolvla/checkpoints/195000/pretrained_model/` | 195K/200K | ❌ 不完整，缺 preprocessor/postprocessor，不可 resume |
| Task 2 ACT | `outputs/train/task2_act/checkpoints/` | 10K-100K | 每 10k 一个 checkpoint |

---

## 3. 关键脚本与命令

### 3.1 数据自动采集

```bash
# 通用模式（在宿主机运行）
./scripts/auto_collect_task{N}.sh --headless

# 可通过环境变量覆盖参数
NUM_EPISODES=50 REPO_ID=local/task1_data ./scripts/auto_collect_task1.sh --headless
```

**各任务脚本参数差异**:

| 任务 | 脚本 | TASK | OBJECTS_PER_EPISODE | REPO_ID |
|------|------|------|---------------------|---------|
| Task 1 | `auto_collect_task1.sh` | Part_Sorting | 2 | local/task1_part_sorting |
| Task 2 | `auto_collect_task2.sh` | Conveyor_Sorting | 2 | local/task2_conveyor_sorting |
| Task 3 | `auto_collect_task3.sh` | Foam_Inlaying | 3 | local/task3_foam_inlaying |
| Task 4 | `auto_collect_task4.sh` | Packing_Box | 1 | local/task4_packing_box |

**采集流程**: 宿主机脚本 → 启动 Docker 容器 → 容器内执行 `programmatic_control.py` → 数据写入 `datasets/{TASK}/batch1/`

### 3.2 训练

```bash
# 在容器内执行（使用 Isaac Sim Python）
/isaac-sim/python.sh src/lerobot/scripts/lerobot_train.py \
    --policy=act \
    --dataset.repo_id=local/task1 \
    --dataset.root=./datasets/train/task1 \
    --output_dir=outputs/train/task1_act \
    --steps=100000 \
    --eval_freq=10000 \
    --save_freq=10000 \
    --batch_size=8 \
    --policy.device=cuda
```

**关键参数**:
- `--policy`: `act`（推荐）或 `smolvla`
- `--dataset.repo_id`: 数据集标识符
- `--dataset.root`: 本地数据集路径（必须指向包含 `meta/info.json` 的目录）
- `--steps`: 训练步数（推荐 100K-200K）
- `--batch_size`: 根据显存调整（24GB 显存建议 8-16）

### 3.3 评估

```bash
# 在容器内执行
/isaac-sim/python.sh src/lerobot/scripts/lerobot_eval.py \
    --robot.type=walker_s2_sim \
    --task=Part_Sorting \
    -p outputs/train/task1_act/checkpoints/last/pretrained_model \
    --eval.n_episodes=50 \
    --eval.batch_size=10
```

**评估指标**: `pc_success`（百分比成功率），目标 ≥75%

---

## 4. 已知问题与解决方案

### 问题 1: 训练时数据集路径错误

**现象**: `RepositoryNotFoundError: 401 Client Error`  
**原因**: 训练脚本尝试从 HuggingFace 加载 `local/task1`，而不是本地路径  
**解决**: 必须同时指定 `--dataset.repo_id` 和 `--dataset.root`，且 `root` 必须是包含 `meta/info.json` 的目录

### 问题 2: batch1 目录为空

**现象**: `datasets/{Task}/batch1/meta/info.json` 显示 episodes=0  
**原因**: 采集脚本默认写入 `batch1/`，但之前采集可能写入了时间戳目录  
**解决**: 
- 方案 A: 手动将时间戳目录内容复制到 `batch1/`
- 方案 B: 修改采集脚本的 ROOT_DIR 参数
- 方案 C: 训练时直接指向时间戳目录

### 问题 3: 采集数据不足

**现象**: episodes 数量太少（<30），无法训练出好模型  
**解决**: 增加 `NUM_EPISODES` 参数，建议每个任务至少 50-100 episodes

### 问题 4: auto_collect_unzipped 目录不完整

**现象**: `auto_collect_unzipped/lerobot/scripts/programmatic_control.py` 不存在  
**原因**: 该目录只包含 `__pycache__` 文件，实际脚本在 Docker 镜像内  
**解决**: 不需要修改此目录，采集脚本通过 Docker 执行

### 问题 5: eval_smolvla.py 调用不存在的 check_success()（已修复）

**现象**: Task 1 SmolVLA eval 始终 0%，日志无报错  
**原因**: `SceneBuilder` 没有 `check_success()` 方法，eval_smolvla.py L208 调用该方法抛出 `AttributeError`，被 `except Exception: pass` 吞没  
**解决**: 2026-06-21 已在 `Ubtech_sim/source/SceneBuilder.py` 新增 `check_success()` 方法，按箱体 Y 轴切分判定任务成功；同时修复了 eval_smolvla.py 的异常静默吞没

### 问题 6: SmolVLM2 模型未下载（eval 阻塞）

**现象**: `OSError: Can't load processor for 'HuggingFaceTB/SmolVLM2-500M-Video-Instruct'`  
**原因**: 容器内无法访问 HuggingFace，模型未缓存  
**解决**: 宿主机执行 `huggingface-cli download HuggingFaceTB/SmolVLM2-500M-Video-Instruct --local-dir <cache路径>`

### 问题 7: 195k checkpoint 不完整

**现象**: 从 195k resume 失败  
**原因**: 训练在 195k 保存 checkpoint 时崩溃（`error running python`），只保存了 `config.json` + `model.safetensors`，缺 `training_state/` 和 processor 文件  
**解决**: 使用 190k checkpoint（完整）；后续训练注意 checkpoint 保存失败的容错

---

## 5. 执行计划（按顺序）

### Phase 1: 数据采集（每个任务 50-100 episodes）

```bash
# Task 1: Part_Sorting（已有 100 episodes，可跳过或追加）
NUM_EPISODES=50 ./scripts/auto_collect_task1.sh --headless

# Task 2: Conveyor_Sorting（需补采至 50+）
NUM_EPISODES=50 ./scripts/auto_collect_task2.sh --headless

# Task 3: Foam_Inlaying（需从零采集 50+）
NUM_EPISODES=50 ./scripts/auto_collect_task3.sh --headless

# Task 4: Packing_Box（需从零采集 50+）
NUM_EPISODES=50 ./scripts/auto_collect_task4.sh --headless
```

**预计耗时**: 每个任务约 30-60 分钟（取决于 episode 长度和 GPU 性能）

### Phase 2: 数据预处理

将采集的数据整理为训练格式：

```bash
# 对每个任务，确认 datasets/{Task}/batch1/meta/info.json 存在且 episodes > 0
# 如果数据在时间戳目录，复制到 batch1/
cp -r datasets/Part_Sorting/batch1_20260528_060209/* datasets/Part_Sorting/batch1/
```

### Phase 3: 模型训练

```bash
# 进入容器
./run.sh --headless

# Task 1: Part_Sorting
/isaac-sim/python.sh src/lerobot/scripts/lerobot_train.py \
    --policy=act \
    --dataset.repo_id=local/task1 \
    --dataset.root=./datasets/Part_Sorting/batch1 \
    --output_dir=outputs/train/task1_act \
    --steps=100000 --eval_freq=10000 --save_freq=10000

# Task 2: Conveyor_Sorting
/isaac-sim/python.sh src/lerobot/scripts/lerobot_train.py \
    --policy=act \
    --dataset.repo_id=local/task2 \
    --dataset.root=./datasets/Conveyor_Sorting/batch1 \
    --output_dir=outputs/train/task2_act \
    --steps=100000 --eval_freq=10000 --save_freq=10000

# Task 3: Foam_Inlaying
/isaac-sim/python.sh src/lerobot/scripts/lerobot_train.py \
    --policy=act \
    --dataset.repo_id=local/task3 \
    --dataset.root=./datasets/Foam_Inlaying/batch1 \
    --output_dir=outputs/train/task3_act \
    --steps=100000 --eval_freq=10000 --save_freq=10000

# Task 4: Packing_Box
/isaac-sim/python.sh src/lerobot/scripts/lerobot_train.py \
    --policy=act \
    --dataset.repo_id=local/task4 \
    --dataset.root=./datasets/Packing_Box/batch1 \
    --output_dir=outputs/train/task4_act \
    --steps=100000 --eval_freq=10000 --save_freq=10000
```

**预计耗时**: 每个任务约 8-12 小时（100K steps @ ~1.35 step/s）

### Phase 4: 模型评估

```bash
# Task 1
/isaac-sim/python.sh src/lerobot/scripts/lerobot_eval.py \
    --robot.type=walker_s2_sim --task=Part_Sorting \
    -p outputs/train/task1_act/checkpoints/last/pretrained_model \
    --eval.n_episodes=50

# Task 2
/isaac-sim/python.sh src/lerobot/scripts/lerobot_eval.py \
    --robot.type=walker_s2_sim --task=Conveyor_Sorting \
    -p outputs/train/task2_act/checkpoints/last/pretrained_model \
    --eval.n_episodes=50

# Task 3
/isaac-sim/python.sh src/lerobot/scripts/lerobot_eval.py \
    --robot.type=walker_s2_sim --task=Foam_Inlaying \
    -p outputs/train/task3_act/checkpoints/last/pretrained_model \
    --eval.n_episodes=50

# Task 4
/isaac-sim/python.sh src/lerobot/scripts/lerobot_eval.py \
    --robot.type=walker_s2_sim --task=Packing_Box \
    -p outputs/train/task4_act/checkpoints/last/pretrained_model \
    --eval.n_episodes=50
```

### Phase 5: 调优（如果准确率 < 75%）

可能的调优方向：
1. **增加数据量**: 采集更多 episodes（100-200）
2. **调整超参数**: 学习率、batch size、训练步数
3. **更换策略**: 从 `act` 换成 `smolvla`（Task 1 已有 SmolVLA 训练经验）
4. **数据增强**: 启用 `image_transforms`（随机裁剪、颜色抖动等）

---

## 6. 关键文件索引

```
UBTECH/
├── scripts/
│   ├── auto_collect_task1.sh      # Task 1 采集入口
│   ├── auto_collect_task2.sh      # Task 2 采集入口
│   ├── auto_collect_task3.sh      # Task 3 采集入口
│   ├── auto_collect_task4.sh      # Task 4 采集入口
│   └── auto_collect_common.sh     # 通用采集逻辑（Docker 启动）
├── src/lerobot/scripts/
│   ├── lerobot_train.py           # 训练脚本
│   └── lerobot_eval.py            # 评估脚本
├── datasets/
│   ├── Part_Sorting/batch1/       # Task 1 数据
│   ├── Conveyor_Sorting/batch1/   # Task 2 数据
│   ├── Foam_Inlaying/batch1/      # Task 3 数据
│   ├── Packing_Box/batch1/        # Task 4 数据
│   └── train/task1/               # Task 1 训练数据集
├── outputs/train/
│   └── task1_smolvla/             # Task 1 已训练模型
└── auto_collect_unzipped/         # 采集运行时（仅含 __pycache__）
```

---

## 7. 注意事项

1. **采集脚本需要在宿主机运行**，它们会自动启动 Docker 容器
2. **训练和评估必须在容器内运行**，使用 `/isaac-sim/python.sh`
3. **数据集路径必须指向包含 `meta/info.json` 的目录**，不能只指向上级目录
4. **评估需要 Isaac Sim 环境**，只能在容器内执行
5. **每次训练建议保存多个 checkpoint**（`--save_freq=10000`），以便选择最佳模型
6. **Task 1 已有 SmolVLA 模型**（195K steps），可直接评估作为 baseline

---

## 8. 快速验证命令

```bash
# 检查数据集是否就绪
for task in Part_Sorting Conveyor_Sorting Foam_Inlaying Packing_Box; do
    echo "=== $task ==="
    python3 -c "import json; d=json.load(open('datasets/$task/batch1/meta/info.json')); print(f'  episodes={d[\"total_episodes\"]}, frames={d[\"total_frames\"]}')" 2>/dev/null || echo "  NO DATA"
done

# 检查模型是否就绪
ls -la outputs/train/task*/checkpoints/last/pretrained_model/model.safetensors 2>/dev/null
```
