# 数据集处理脚本说明

本目录包含数据集后处理相关的脚本和 Notebook，用于对 LeRobot 格式的数据集进行质量检查、数据清洗、格式转换和 episode 拆分等操作。

---

## 文件清单

| 文件                           | 类型             | 用途                                                        |
| ------------------------------ | ---------------- | ----------------------------------------------------------- |
| `process_dataset_v2.ipynb`   | Jupyter Notebook | 多功能数据处理工具集（查看、清洗、合并、分析）              |
| `process_dataset_v3.ipynb`   | Jupyter Notebook | 数据集质量检查与 episode 拆分（精简版）                     |
| `split_conveyor_episodes.py` | Python 脚本      | 将长 episode 按 part_info.json 拆分为短 episode（独立脚本） |
| `remove_part_info.py`        | Python 脚本      | 批量删除 LeRobot 数据集中的 part_info.json 文件             |

---

## 1. process_dataset_v2.ipynb

多功能数据处理工具集，包含数据查看、质量检查、特征合并、备份管理等工具 Cell。各 Cell 相互独立，按需运行。

**使用方式：**

1. 在 Jupyter 环境中打开 `process_dataset_v2.ipynb`
2. 修改目标 Cell 中 `DATA_DIR` / `DATA_FILE` 变量为你的数据集路径
3. 按顺序或按需执行目标 Cell
4. 所有路径变量已使用相对路径（基于 `PROJECT_ROOT`），Notebook 在 `dataset_post_process/` 目录下运行即可

**Cell 说明：**

### Cell 0-1：查看 data/*.parquet 文件（episodes 统计分析）

扫描 `meta/episodes/chunk-000/` 目录下的 parquet 文件，分析 `length` 列和 `episode_index` 的统计分布。

- **输入：** `DATA_DIR` → `meta/episodes/chunk-000/` 目录
- **输出：** 可选的 txt 分析日志
- **配置：** `SAVE_TO_TXT`, `TXT_PREFIX`

### Cell 2-3：查看 episode_index 分布

读取单个 parquet 文件，查看 `episode_index` 列的唯一值、最小/最大值、分布情况。

- **输入：** `parquet_path` → 单个 parquet 文件
- **输出：** 控制台打印 episode_index 统计

### Cell 4-5：处理 observation.environment_state 数据

将 `observation.environment_state`（28维）拼接到 `observation.state`（20维），使 `observation.state` 变为 48 维，然后删除 `observation.environment_state` 列。

- **输入：** `DATA_DIR` → `data/chunk-000/` 目录
- **配置：** `CREATE_BACKUP`（是否备份原文件）, `OVERWRITE_ORIGINAL`, `SAVE_LOG`
- **处理逻辑：** `np.concatenate([state, env_state])` 逐行拼接

### Cell 6-7：删除备份文件

递归搜索指定目录下的备份文件（`_backup`, `.bak` 等标识），支持预览和确认删除模式。

- **输入：** `DATA_DIR` → 搜索根目录
- **配置：** `BACKUP_KEYWORDS`, `CONFIRM_DELETE`, `RECURSIVE`

### Cell 8-9：查看夹爪数据（数组切片分析）

读取 parquet 文件中 `observation.state` 和 `action` 列的指定数组切片，分析其值分布。

- **输入：** `DATA_FILE` → 单个 parquet 文件
- **配置：** `ARRAY_SLICE`, `TARGET_COLUMNS`, `SAVE_TO_TXT`

### Cell 11-12：统计 action 数组指定位置的值分布

Cell 10 为空白分隔。分析 `action` 列中指定位置的元素值种类和分布。

- **输入：** `DATA_FILE` → 单个 parquet 文件
- **配置：** `POSITIONS`（要分析的位置索引）, `TARGET_COL`

### Cell 14-15：查看 meta 目录下所有 .jsonl 文件

递归扫描 meta 目录，分析所有 JSONL 文件的字段结构、数据类型、嵌套路径等 schema 信息。

- **输入：** `DATA_DIR` → `meta/` 目录
- **输出：** 可选的 txt schema 分析报告
- **配置：** `SAVE_TO_TXT`, `SHOW_NESTED_PATHS`, `SHOW_PER_FILE_DETAILS`

### Cell 16-17：对 meta 目录下的 jsonl 文件进行分别处理

批量处理 meta 目录下的 `episodes.jsonl`、`episodes_stats.jsonl`、`tasks.jsonl`：

| 文件                     | 处理内容                                                              |
| ------------------------ | --------------------------------------------------------------------- |
| `episodes.jsonl`       | `tasks` 数组所有元素统一为 "Part Sorting"                           |
| `episodes_stats.jsonl` | stats 中 min/max/mean/std 数组拼接 (20+28→48)，删除 env_state 统计项 |
| `tasks.jsonl`          | `task` 字段统一为 "Part Sorting"                                    |

- **输入：** `DATA_DIR` → `meta/` 目录
- **配置：** `PROCESS_EPISODES`, `PROCESS_EPISODES_STATS`, `PROCESS_TASKS`, `CREATE_BACKUP`, `OVERWRITE_ORIGINAL`

### Cell 18-19：处理 info.json 文件

处理 `meta/info.json`，将 `observation.environment_state` 的特征定义合并到 `observation.state` 中：

- `features.observation.state.names` 拼接（20+28→48 个 name）
- `features.observation.state.shape` 更新 `[20]` → `[48]`
- 删除 `features.observation.environment_state`
- **输入：** `DATA_DIR` → 数据集根目录（包含 `meta/info.json`）
- **配置：** `CREATE_BACKUP`, `OVERWRITE_ORIGINAL`, `SAVE_LOG`

### 数据处理流程总览（v2 常用流程）

| 步骤 | Cell  | 目标文件                      | 核心操作                                                                  |
| ---- | ----- | ----------------------------- | ------------------------------------------------------------------------- |
| 1    | 4-5   | `data/chunk-000/*.parquet`  | `observation.state`(20) + `observation.environment_state`(28) → (48) |
| 2    | 16-17 | `meta/episodes_stats.jsonl` | stats 数组拼接 (20+28→48)                                                |
| 3    | 16-17 | `meta/tasks.jsonl`          | `task` 字段统一为 "Part Sorting"                                        |
| 4    | 16-17 | `meta/episodes.jsonl`       | `tasks` 数组所有元素统一为 "Part Sorting"                               |
| 5    | 18-19 | `meta/info.json`            | names 拼接，shape 更新 [20]→[48]                                         |

---

## 2. process_dataset_v3.ipynb

精简版数据集处理 Notebook，专注于三个核心操作：异常检测、异常删除、episode 拆分。

**使用方式：**

1. 在 Jupyter 环境中打开 `process_dataset_v3.ipynb`
2. 按顺序执行 Cell
3. 所有路径变量已使用相对路径（基于 `PROJECT_ROOT` = `Path.cwd().parent.resolve()`）

**Cell 说明：**

### Cell 0-1：检测 length 列异常值

扫描 parquet 文件中 `length` 列，找出不等于 `NORMAL_LENGTH` 的异常行，记录对应的 `episode_index`。用于数据质量检查，发现帧数不完整的 episode。

- **输入：** `DATA_DIR` → `meta/episodes/chunk-000/` 目录
- **配置：** `NORMAL_LENGTH`（正常帧数，如 768）
- **输出：** 控制台报告 + 可选的 txt 日志，异常 episode_index 列表供下一步使用

### Cell 2-3：调用 lerobot_edit_dataset 删除异常 episode

使用 LeRobot 官方的 `lerobot_edit_dataset.py` 脚本，根据上一步检测出的异常 episode_index 列表，从数据集中删除对应的 episode。

- **输入：** `DATASET_ROOT` → 数据集根目录
- **配置：** `ANOMALY_EPISODE_INDICES`（异常 episode 列表）, `IN_PLACE`（是否原地修改）
- **注意：** 首次运行建议设 `IN_PLACE = False` 验证结果后再原地修改

### Cell 4-5：将长 episode 按 part_info 拆分为短 episode

根据 `meta/part_info.json` 中记录的零件帧范围，将一个包含多个零件操作的长 episode 拆分为多个独立的短 episode。支持保留或移除视频观测数据。

- **输入：** `SOURCE_DATASET_ROOT` → 源数据集根目录（必须含 `meta/part_info.json`）
- **配置：**
  - `PROCESS_MODE`：`"single_dataset"` 或 `"directory"`（批量处理）
  - `PRESERVE_VISUAL_OBS`：是否保留视频/图像观测
  - `OVERWRITE_OUTPUT`：是否允许覆盖已有输出
- **输出：** 新的 LeRobot 数据集，每个 episode 只包含单个零件操作

---

## 3. split_conveyor_episodes.py

独立的 Python 脚本，功能与 `process_dataset_v3.ipynb` 的 Cell 4-5 相同，支持 Part_Sorting 和 Conveyor_Sorting 两种任务。**通过命令行参数传递配置，无需修改脚本代码。**

**使用方式：**

```bash
# 单数据集模式
python dataset_post_process/split_conveyor_episodes.py single \
    --source-root datasets/Part_Sorting/auto/test \
    --output-root datasets/Part_Sorting/auto/test_short_parts

# 目录批量模式
python dataset_post_process/split_conveyor_episodes.py directory \
    --source-dir datasets/Part_Sorting/auto \
    --output-parent-dir datasets/Part_Sorting/auto_short_parts

# 使用 isaac-sim python 运行
/isaac-sim/python.sh dataset_post_process/split_conveyor_episodes.py single \
    --source-root datasets/Part_Sorting/auto/test \
    --output-root datasets/Part_Sorting/auto/test_short_parts

# 查看帮助
python split_conveyor_episodes.py --help
python split_conveyor_episodes.py single --help
python split_conveyor_episodes.py directory --help
```

**参数说明：**

| 参数                           | 适用模式  | 说明                                        | 默认值           |
| ------------------------------ | --------- | ------------------------------------------- | ---------------- |
| `{single,directory}`         | 必选      | 处理模式子命令                              | -                |
| `--source-root`              | single    | 源数据集根目录 (必须含 meta/part_info.json) | 必填             |
| `--output-root`              | single    | 输出数据集根目录                            | 必填             |
| `--output-repo-id`           | single    | 输出 repo_id                                | 源目录名         |
| `--source-dir`               | directory | 源数据集父目录                              | 必填             |
| `--output-parent-dir`        | directory | 输出父目录                                  | 必填             |
| `--output-name-suffix`       | directory | 输出目录名后缀                              | `_short_parts` |
| `--output-repo-id-suffix`    | directory | 输出 repo_id 后缀                           | `_short_parts` |
| `--recursive/--no-recursive` | directory | 是否递归扫描子目录                          | 开启             |
| `--no-preserve-visual-obs`   | 通用      | 不保留视频，仅保留 state/action             | 保留             |
| `--source-video-backend`     | 通用      | 源视频解码后端                              | `pyav`         |
| `--output-video-codec`       | 通用      | 输出视频编码器                              | `libsvtav1`    |
| `--image-writer-processes`   | 通用      | 写图像并发进程数                            | `8`            |
| `--image-writer-threads`     | 通用      | 每相机写图像线程数                          | `4`            |
| `--overwrite`                | 通用      | 允许覆盖已有输出目录                        | 不覆盖           |
| `--task`                     | 通用      | 新 episode 的 task 文本                     | 沿用源数据       |

**工作原理：**

1. 加载源 LeRobotDataset 和 `meta/part_info.json`
2. 按每个 part 的 `frame_start_index` ~ `frame_end_index` 范围提取帧
3. 通过 `LeRobotDataset.create()` 写出新的短 episode 数据集

---

## 4. remove_part_info.py

独立的 Python 脚本，用于批量删除 LeRobot 数据集中的 `meta/part_info.json` 文件。适用于拆分完成后清理临时元数据的场景。

**使用方式：**

```bash
# 基本用法（日志输出到目标目录）
python dataset_post_process/remove_part_info.py datasets/Part_Sorting/auto/

/isaac-sim/python.sh dataset_post_process/remove_part_info.py datasets/Part_Sorting/auto/


# 关闭文件日志，仅输出到控制台
python dataset_post_process/remove_part_info.py datasets/Part_Sorting/auto/ --no-log

/isaac-sim/python.sh dataset_post_process/remove_part_info.py datasets/Part_Sorting/auto/ --no-log

# 指定日志输出目录
python dataset_post_process/remove_part_info.py datasets/Part_Sorting/auto/ --log-dir /tmp/logs

/isaac-sim/python.sh dataset_post_process/remove_part_info.py datasets/Part_Sorting/auto/ --no-log


```

**参数说明：**

| 参数          | 说明                                  | 默认值           |
| ------------- | ------------------------------------- | ---------------- |
| `root_dir`  | 必选，包含 LeRobot 数据集的根目录路径 | -                |
| `--no-log`  | 禁用文件日志，仅输出到控制台          | 启用文件日志     |
| `--log-dir` | 日志文件输出目录                      | 与 root_dir 相同 |

**工作原理：**

1. 扫描 `root_dir` 下所有包含 `meta/` 子目录的文件夹，识别为 LeRobot 数据集
2. 检查每个数据集的 `meta/part_info.json` 是否存在
3. 存在则删除，并记录文件内容中的顶层 key 信息
4. 不存在则跳过（debug 级别日志）
5. 日志文件命名格式：`remove_part_info_YYYYMMDD_HHMMSS.txt`

---

## 路径说明

所有脚本的路径已从绝对路径改为相对路径：

- **Notebook (.ipynb)：** 使用 `PROJECT_ROOT = Path.cwd().parent.resolve()` 或 `REPO_ROOT = Path.cwd().parent.resolve()` 定位项目根目录，数据集路径通过 `PROJECT_ROOT / "datasets/..."` 构造
- **Python 脚本 (.py)：** 使用 `REPO_ROOT = Path(__file__).parent.parent.resolve()` 基于脚本自身位置定位项目根目录

**运行前提：** 确保在 `dataset_post_process/` 目录下启动 Jupyter Notebook 或执行 Python 脚本。

---

## 典型工作流

### 新数据集的完整处理流程：

1. **质量检查：** 运行 `process_dataset_v3.ipynb` Cell 0-1，检测帧数异常的 episode
2. **删除异常：** 运行 Cell 2-3，删除异常 episode（可选）
3. **特征合并：** 运行 `process_dataset_v2.ipynb` Cell 4-5，合并 observation.state
4. **元数据处理：** 运行 Cell 16-17 和 Cell 18-19，更新 jsonl 和 info.json
5. **Episode 拆分：** 运行 `process_dataset_v3.ipynb` Cell 4-5 或 `split_conveyor_episodes.py`
