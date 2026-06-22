# AGENTS.md — Global Humanoid Robot Challenge 2026

## Project Overview

Walker S2 humanoid robot simulation, data collection, and training baseline for the Global Humanoid Robot Challenge 2026. Built on LeRobot 0.5.1 framework with Isaac Sim 5.1.

## Quick Start

```bash
# Build Docker image (first time ~10 min)
docker build -t ubtech:v0 .

# Launch container (auto editable install)
./run.sh              # interactive
./run.sh --headless   # headless/remote
```

Container workspace: `/workspace/GlobalHumanoidRobotChallenge2026_Baseline`

## Essential Commands

### Data Collection

```bash
# Auto-collection (inside container)
./scripts/auto_collect_task1.sh --headless  # Part_Sorting
./scripts/auto_collect_task2.sh --headless  # Conveyor_Sorting
./scripts/auto_collect_task3.sh --headless  # Foam_Inlaying
./scripts/auto_collect_task4.sh --headless  # Packing_Box

# Override params
NUM_EPISODES=50 REPO_ID=local/task1_data ./scripts/auto_collect_task1.sh --headless
```

### Training & Inference

```bash
# Training (inside container, use /isaac-sim/python.sh)
/isaac-sim/python.sh src/lerobot/scripts/lerobot_train.py \
    --policy=act \
    --dataset.repo_id=UBTECH-Robotics/challenge2026_dataset \
    --output_dir=outputs/train

# Inference
/isaac-sim/python.sh src/lerobot/scripts/lerobot_eval.py \
    --robot.type=walker_s2_sim \
    --task=Part_Sorting \
    -p outputs/train/checkpoints/last/pretrained_model
```

### Teleoperation

```bash
# Keyboard teleoperation (inside container)
/isaac-sim/python.sh src/lerobot/scripts/lerobot_teleoperate.py \
    --robot.type=walker_s2_sim \
    --task=Part_Sorting \
    --teleop.type=walker_s2_keyboard \
    --teleop.evdev_device_path=/dev/input/event2
```

## Code Structure

- `src/lerobot/` — Main source (installed editable in container)
  - `auto_collect/` — Task-specific auto-collection scripts (Part_Sorting, Conveyor_Sorting, Foam_Inlaying, Packing_Box)
  - `robots/walker_s2_sim/` — Robot implementation with callback-driven control
  - `teleoperators/walker_s2_keyboard/` — Keyboard teleoperation (pynput/evdev backends)
  - `policies/` — ML policies (ACT, diffusion, pi0, smolvla, etc.)
  - `scripts/` — Entry points (train, eval, teleoperate, record, etc.)
- `Ubtech_sim/` — Isaac Sim scene building, IK, grasp planning
- `auto_collect_unzipped/` — Extracted auto-collection runtime (used by scripts)
- `assets/` — Git submodule for simulation resources (HF repo)
- `tests/` — Unit tests (pytest)

## Linting & Formatting

```bash
# Ruff (format + lint) — configured in pyproject.toml
ruff format .
ruff check . --fix

# Pre-commit hooks (ruff, mypy, typos, bandit, prettier)
pre-commit run --all-files
```

- Line length: 110, target: py312
- Lint rules: E, W, F, I, B, C4, T20, N, UP, SIM
- Mypy: partially enabled (configs, optim, model, cameras, motors, transport)

## Testing

```bash
pytest tests/
pytest tests/auto_collect/test_task_part_sorting.py  # single file
```

Tests use pytest with mock/stub patterns for Isaac Sim dependencies.

## Key Architectural Notes

- **20D state/action space**: 14 arm joints + 4 finger joints + 2 gripper commands
- **Callback-driven control**: `_robot_control_callback()` runs at each physics step (200Hz)
- **4 camera observations**: head_left, head_right, wrist_left, wrist_right
- **4 supported tasks**: Part_Sorting, Conveyor_Sorting, Foam_Inlaying, Packing_Box
- **Docker is primary runtime**: All dev/execution happens inside Isaac Sim container
- Code is mounted read-write; `pip install -e .` makes edits live

## Environment Requirements

- NVIDIA GPU + drivers
- Docker + NVIDIA Container Toolkit
- Python 3.12 (container uses Isaac Sim's Python)

## Resources

- Training data: `huggingface-cli download UBTECH-Robotics/challenge2026_dataset --local-dir ./datasets`
- Pretrained weights: `huggingface-cli download UBTECH-Robotics/challenge2026_baseline --local-dir ./challenge2026_baseline`
