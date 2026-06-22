# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Walker S2 humanoid robot simulation, data collection, and training baseline for the Global Humanoid Robot Challenge 2026. Built on LeRobot 0.5.1 with Isaac Sim 5.1. Docker is the primary runtime — all training/eval/teleop runs inside the Isaac Sim container.

## Build & Run

```bash
# Build Docker image (first time, ~10 min)
docker build -t ubtech:v0 .

# Launch container
./run.sh              # interactive (requires display)
./run.sh --headless   # headless (remote server)

# Env var overrides: IMAGE_NAME, HOST_WORKSPACE, HEADLESS=1
```

Container workspace inside Docker: `/workspace/GlobalHumanoidRobotChallenge2026_Baseline`

### Download assets (as needed)

```bash
pip install huggingface-hub
huggingface-cli download UBTECH-Robotics/challenge2026_dataset --local-dir ./datasets --repo-type dataset
huggingface-cli download UBTECH-Robotics/challenge2026_baseline --local-dir ./challenge2026_baseline --repo-type model
```

## Essential Commands (inside container)

```bash
# Training (use /isaac-sim/python.sh, NOT system python)
/isaac-sim/python.sh src/lerobot/scripts/lerobot_train.py \
    --policy=act --dataset.repo_id=local/task1 \
    --dataset.root=./datasets/Part_Sorting/batch1 \
    --output_dir=outputs/train/task1_act --steps=100000

# Evaluation
/isaac-sim/python.sh src/lerobot/scripts/lerobot_eval.py \
    --robot.type=walker_s2_sim --task=Part_Sorting \
    -p outputs/train/task1_act/checkpoints/last/pretrained_model \
    --eval.n_episodes=50

# SmolVLA evaluation (separate script)
PYTHONPATH=src /isaac-sim/python.sh src/lerobot/scripts/eval_smolvla.py \
    --checkpoint outputs/train/task1_smolvla/checkpoints/195000/pretrained_model \
    --task Part_Sorting --n_episodes 50

# Keyboard teleoperation
/isaac-sim/python.sh src/lerobot/scripts/lerobot_teleoperate.py \
    --robot.type=walker_s2_sim --task=Part_Sorting \
    --teleop.type=walker_s2_keyboard \
    --teleop.evdev_device_path=/dev/input/event2

# Auto-collection (from host, via shell wrapper)
NUM_EPISODES=50 ./scripts/auto_collect_task1.sh --headless

# Auto-collection (inside container, module-based)
/isaac-sim/python.sh -m lerobot.scripts.auto_collect_main \
    --robot.type=walker_s2_sim --auto_collect.task=Part_Sorting \
    --auto_collect.repo_id=local/task1 --auto_collect.num_episodes=10
```

### Keyboard teleop keymap

| Key | Action |
|-----|--------|
| `1` / `3` | End-effector ±Y translation |
| `4` / `6` | End-effector ±X translation |
| `7` / `9` | End-effector ±Z translation |
| `U` / `J` | End-effector ±Rx rotation |
| `I` / `K` | End-effector ±Ry rotation |
| `O` / `L` | End-effector ±Rz rotation |
| `F` | Toggle gripper open/close |
| `T` | Switch left/right arm |
| `R` | Start/stop recording |

## Lint & Test

```bash
ruff format . && ruff check . --fix        # format + lint
pre-commit run --all-files                  # full pre-commit (ruff, mypy, typos, bandit)
pytest tests/                               # all tests
pytest tests/auto_collect/test_task_part_sorting.py -xvs  # single test file
```

Line length 110, target py312.

## Architecture

**4 supported tasks**: `Part_Sorting`, `Conveyor_Sorting`, `Foam_Inlaying`, `Packing_Box`

**20D state/action space**: 14 arm joints + 4 finger joints + 2 gripper commands. 4 camera observations: `head_left`, `head_right`, `wrist_left`, `wrist_right` (480x640 each). Episode length 500 steps at 30 FPS.

**Key directories:**
- `src/lerobot/` — Installed editable in container; changes take effect on next run
  - `robots/walker_s2_sim/` — Robot class with callback-driven physics-step control (200Hz via `_robot_control_callback`)
  - `teleoperators/walker_s2_keyboard/` — Keyboard teleop with pynput/evdev backends
  - `policies/` — ACT, diffusion, pi0/pi05, smolvla, sarm, tdmpc, vqbet, xvla, groot, etc. (see `policies/factory.py`)
  - `envs/configs.py` — `WalkerS2SimEnv` registered as `walker_s2_sim`; default `headless=True`, 30 FPS
  - `scripts/auto_collect_main.py` — Programmatic auto-collection; `_COLLECTOR_REGISTRY` maps task name → collector class
- `Ubtech_sim/` — Isaac Sim scene building, IK solver, grasp planner, data logger (standalone, not LeRobot-integrated)
- `assets/` — Git submodule with simulation USD resources
- `scripts/` — Per-task auto-collection wrappers (`auto_collect_task{1..4}.sh` → `auto_collect_common.sh`)

**Dataset convention**: `datasets/<TaskName>/<batch_name>/meta/info.json` — `dataset.root` must point to the batch directory containing `meta/`.

**Training**: Uses HuggingFace Accelerate for multi-GPU. `effective_batch_size = batch_size * num_processes`. Checkpoints saved to `outputs/train/<name>/checkpoints/<step>/`.

**Evaluation metric**: `pc_success` — target ≥75%. Eval supports batched parallel environments via `eval.batch_size`.

**Critical runtime constraints**: Always use `/isaac-sim/python.sh` (not `python`) — Isaac Sim bundles its own Python interpreter. Inside container, `PYTHONPATH=src` is sometimes needed for scripts not launched via the LeRobot CLI framework.
