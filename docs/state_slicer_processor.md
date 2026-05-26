# StateSlicerProcessor 说明

## 概述

`StateSlicerProcessorStep` 是一个观测预处理步骤，用于将 `observation.state` 截断为前 `n_dims` 维。当数据集的 state 维度超过模型的最大输入维度时使用（例如 48 维数据集 vs 32 维 pi0 模型），只保留前导的关节位置等关键维度。

**文件位置**: `src/lerobot/processor/state_slicer_processor.py`

## 基于 LeRobot 官方的什么类/接口

| 基类/机制 | 来源 | 说明 |
|---|---|---|
| `ObservationProcessorStep` | `src.lerobot.processor.pipeline` | LeRobot 官方的观测处理器步骤基类，定义了 `observation()`、`transform_features()`、`get_config()` 三个标准接口 |
| `ProcessorStepRegistry.register(name="state_slicer_processor")` | `src.lerobot.processor.pipeline` | LeRobot 官方的处理器步骤注册表，通过装饰器将步骤注册为可序列化/反序列化的流水线组件，注册名 `"state_slicer_processor"` |
| `@dataclass` | Python 标准库 | 配置参数通过 dataclass 字段声明，`n_dims: int = 20` |

### 核心类: `StateSlicerProcessorStep` (第 32 行)

```python
@dataclass
@ProcessorStepRegistry.register(name="state_slicer_processor")
class StateSlicerProcessorStep(ObservationProcessorStep):
    n_dims: int = 20

    def observation(self, observation):
        # 将 observation.state 截断为前 n_dims 维
        if OBS_STATE in observation:
            state = observation[OBS_STATE]
            observation[OBS_STATE] = state[..., :self.n_dims]
        return observation

    def transform_features(self, features):
        # 将特征定义中的 shape 更新为 (n_dims,)
        ...

    def get_config(self):
        # 返回序列化配置，用于保存/加载
        return {"n_dims": self.n_dims}
```

### 辅助函数: `slice_stats_for_state()` (第 64 行)

```python
def slice_stats_for_state(stats, n_dims):
    """将 observation.state 的统计数据截断到 n_dims 维。

    对 stats["observation.state"] 下的 mean、std、min、max、q01、q99 等
    所有统计量，将其最后一维截断为 n_dims，确保归一化统计与截断后的
    state 维度一致。
    """
```

---

## 所有调用/引用文件清单 (共 11 个源文件)

### 1. 模块导出 — `src/lerobot/processor/__init__.py`

| 行号 | 代码 | 作用 |
|---|---|---|
| 78 | `from .state_slicer_processor import StateSlicerProcessorStep, slice_stats_for_state` | 从实现模块导入，对外暴露 |
| 118 | `"slice_stats_for_state"` | 加入 `__all__` 导出列表 |
| 119 | `"StateSlicerProcessorStep"` | 加入 `__all__` 导出列表 |

---

### 2. ACT Policy — `src/lerobot/policies/act/processor_act.py`

| 行号 | 代码 | 作用 |
|---|---|---|
| 28 | `from src.lerobot.processor import ... StateSlicerProcessorStep ...` | 导入 |
| 58 | `StateSlicerProcessorStep(n_dims=20),` | 作为 `input_steps` 第 1 步（共 5 步），截断后进入 RenameObservations → AddBatchDimension → Device → Normalizer |

---

### 3. Diffusion Policy — `src/lerobot/policies/diffusion/processor_diffusion.py`

| 行号 | 代码 | 作用 |
|---|---|---|
| 29 | `from src.lerobot.processor import ... StateSlicerProcessorStep ...` | 导入 |
| 67 | `StateSlicerProcessorStep(n_dims=20),` | 作为 `input_steps` 第 1 步（共 5 步），流水线与 ACT 相同 |

---

### 4. pi0 Policy — `src/lerobot/policies/pi0/processor_pi0.py`

| 行号 | 代码 | 作用 |
|---|---|---|
| 33 | `from src.lerobot.processor import ... StateSlicerProcessorStep ...` | 导入 |
| 132 | `StateSlicerProcessorStep(n_dims=20),` | 作为 `input_steps` 第 1 步（共 7 步），后有 Pi0NewLine → Tokenizer → Device → Normalizer 等 |

---

### 5. pi0.5 Policy — `src/lerobot/policies/pi05/processor_pi05.py`

| 行号 | 代码 | 作用 |
|---|---|---|
| 35 | `from src.lerobot.processor import ... StateSlicerProcessorStep ...` | 导入 |
| 131 | `StateSlicerProcessorStep(n_dims=20),` | 作为 `input_steps` 第 1 步（共 7 步），注意 pi0.5 的 Normalizer 在 Tokenizer 之前，因为分词器需要已归一化的状态 |

---

### 6. SmolVLA Policy — `src/lerobot/policies/smolvla/processor_smolvla.py`

| 行号 | 代码 | 作用 |
|---|---|---|
| 32 | `from src.lerobot.processor import ... StateSlicerProcessorStep ...` | 导入 |
| 71 | `StateSlicerProcessorStep(n_dims=20),` | 作为 `input_steps` 第 1 步（共 7 步），后有 SmolVLANewLine → Tokenizer → Device → Normalizer |

---

### 7. 训练脚本 — `src/lerobot/scripts/lerobot_train.py`

| 行号 | 代码 | 作用 |
|---|---|---|
| 39 | `from src.lerobot.processor import StateSlicerProcessorStep, slice_stats_for_state` | 同时导入类和辅助函数 |
| 257 | `truncated_stats = slice_stats_for_state(dataset.meta.stats, n_dims=20)` | **关键**：在创建处理器之前，将数据集统计量（mean/std/min/max/q01/q99）从 48 维截断到 20 维，否则 Normalizer 的 stats 维度与切片后的 state 维度不匹配 |
| 300 | `preprocessor.steps.insert(0, StateSlicerProcessorStep(n_dims=20))` | **仅预训练模型路径**：从 JSON 反序列化的处理器配置不包含切片步骤，因此手动插入到流水线第 0 位。非预训练模型的切片步骤已由策略工厂包含 |

**数据流**（训练时）：
```
dataset.meta.stats (48 维)
  → slice_stats_for_state() → truncated_stats (20 维)
    → NormalizerProcessorStep(stats=truncated_stats)
      → 归一化时与 StateSlicerProcessorStep 截断后的 20 维 state 匹配
```

---

### 8. 策略工厂 — `src/lerobot/policies/factory.py`

| 行号 | 代码 | 作用 |
|---|---|---|
| 471-473 | `# Truncate observation.state to 20 dims ...` / `# StateSlicerProcessorStep in the processor pipeline.` | 注释说明特征截断与流水线中 StateSlicerProcessorStep 的对应关系 |
| 474-478 | `if OBS_STATE in features and features[OBS_STATE].shape[0] > 20: features[OBS_STATE] = PolicyFeature(type=..., shape=(20,))` | 当从环境（非数据集）解析特征时，若 state 维度 > 20，将模型 `input_features` 声明截断为 (20,)，确保模型结构定义与实际流入数据维度一致 |

---

### 9. `lerobot_record.py` — 不使用

`src/lerobot/scripts/lerobot_record.py` **不引用** `StateSlicerProcessorStep` 或 `slice_stats_for_state`。数据录制不需要截断 state，录制时直接保存完整的 observation 原始维度。

---

## 流水线顺序（所有 5 个 Policy 通用）

```
StateSlicerProcessorStep (截断 observation.state 到 20 维)
  → RenameObservationsProcessorStep (重命名观测键)
    → AddBatchDimensionProcessorStep (添加 batch 维度)
      → [策略特定步骤] (Pi0NewLine / Tokenizer / SmolVLANewLine 等)
        → DeviceProcessorStep (移动到 GPU)
          → NormalizerProcessorStep (归一化，使用 slice_stats_for_state 截断后的 stats)
```

## 设计意图

数据集的 `observation.state` 包含 48 维（20 维关节位置 + 28 维物体位姿），而 pi0/smolvla/pi05 等模型的 `max_state_dim` 限制为 32 或更少。`StateSlicerProcessorStep` 取前 20 维（关节位置），丢弃后 28 维（物体位姿），使模型能正常接收状态输入。

三个配套机制确保一致性：
1. **StateSlicerProcessorStep** — 运行时截断 state 数据
2. **slice_stats_for_state()** — 同步截断归一化统计量
3. **factory.py 特征截断** — 同步截断模型 `input_features` 声明
