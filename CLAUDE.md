# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

GHRC 2026 (Global Humanoid Robot Challenge 2026) baseline — a humanoid robot simulation platform for the Walker S2 robot, built on **NVIDIA Isaac Sim 5.1** and the **LeRobot** framework (v0.5.1). End-to-end workflow: physics simulation → data collection → model training → policy deployment.

## Key Directories

| Path | Purpose |
|------|---------|
| `src/lerobot/` | Official LeRobot framework source (Hugging Face fork) |
| `lerobot/` | **Project-specific code** — custom robots, teleoperators, envs, policies, utils |
| `Ubtech_sim/` | Isaac Sim simulation environment (scene building, IK, grasp planning, data logging) |
| `assets/` | Git submodule — simulation assets (USD models, URDF, textures) |
| `datasets/` | Training datasets (e.g., `datasets/task1` with 200 episodes for Part Sorting) |
| `outputs/` | Training/eval run outputs and task pose logs |

## Competition Tasks (4)

The baseline supports 4 tasks configured via YAML in `Ubtech_sim/config/`:

| Task | Config | Description |
|------|--------|-------------|
| Part_Sorting | `Part_Sorting.yaml` | Sort parts into designated areas |
| Conveyor_Sorting | `Conveyor_Sorting.yaml` | Pick parts from conveyor belt (Task 2) |
| Foam_Inlaying | `Foam_Inlaying.yaml` | Precision foam inlaying |
| Packing_Box | `Packing_Box.yaml` | Box packing |

Select via `--task=TaskName` or by setting `task_name` in `WalkerS2Config`.

## Architecture

### LeRobot Framework (`src/lerobot/`)

Core pipeline components:

- **Datasets** (`src/lerobot/datasets/`): `LeRobotDataset` — standardized V3.0 format with streaming, video, image writing, transforms, stats computation
- **Policies** (`src/lerobot/policies/`): ACT, Diffusion, Pi0, Pi0_fast, Pi05, SmolVLA, Groot, SARM, XVLA, WallX, SAC, TDMPC, VQBeT. Each has config/model/processor triplet
- **Robots** (`src/lerobot/robots/`): Physical robot interfaces including `WalkerS2sim` (Isaac Sim articulation wrapper)
- **Teleoperators** (`src/lerobot/teleoperators/`): Keyboard, gamepad, leader-follower, and `WalkerS2KeyboardTeleop`
- **Cameras**, **Scripts**, **Configs**, **Envs**, **Processor** modules

### Walker S2 Isaac Sim Robot (`src/lerobot/robots/walker_s2_sim/`)

The Walker S2 sim robot is the central integration point. Key files:

| File | Purpose |
|------|---------|
| `walkers2sim.py` | Main `WalkerS2sim(Robot)` class — 14 DOF arms (7/arm), 4 gripper joints, 2 gripper commands = **20D state/action space**, 4 cameras (head_left, head_right, wrist_left, wrist_right), Isaac Sim lifecycle (connect/disconnect), keyboard teleop integration |
| `walkers2simConfig.py` | `WalkerS2Config(RobotConfig)` — registered as `"walker_s2_sim"`, loads task YAML, defines joint names, camera configs, speed levels, FSM parameters, head viz settings |
| `isaac_sim_robot_interface.py` | Low-level articulation wrapper — `JointInterpolator` (LERP), `IsaacSimRobotInterface` (connect to Isaac Sim ArticulationView, IK via Pinocchio, camera rendering, gripper control), runtime ~964 lines |
| `head_stereo_visualizer.py` | OpenCV multi-camera visualization window (head/wrist stereo pairs) |
| `ros2_teleop_subscriber.py` | Optional ROS2 joint command subscriber |
| `fsm/` | Finite State Machine auto-collection for Task2 Conveyor Sorting — `conveyor_sorting_fsm.py` (~78K FSM logic), `conveyor_sorting_fsm_agent.py` (agent wrapper) |

### Isaac Sim Simulation (`Ubtech_sim/`)

| File | Purpose |
|------|---------|
| `main.py` | Standalone entry point (outside Docker/LeRobot) — builds scene, runs grasp control loop |
| `source/SceneBuilder.py` | Scene construction (table, boxes, parts, robot) using USD + Replicator |
| `source/RobotArticulation.py` | Walker S2 articulation control interface |
| `source/DualArmIK.py` | Pinocchio-based dual-arm IK (weighted damped least squares) |
| `source/grasp_planner.py` | Grasp target planning and real-time tracking |
| `source/DataLogger.py` | Pose CSV + camera HDF5 logging |
| `source/conveyor_spawner.py` | Dynamic part spawning on conveyor belt (Task2) |

### FSM Auto-Collection (Task2)

The Conveyor Sorting task can run in **FSM mode** (automatic data collection without human teleoperation). Enabled via `fsm_mode: true` in config. The FSM (`fsm/conveyor_sorting_fsm.py`) manages states: approach → descend → grasp → lift → transfer → release. Use `collect_task2.sh` to run autonomous collection.

## Workflow

1. **Environment**: Docker container via `run.sh` (base `nvcr.io/nvidia/isaac-sim:5.1.0`)
2. **Data Collection**: Keyboard teleoperation → LeRobotDataset V3.0 format, OR FSM auto-collection for Task2
3. **Training**: Imitation learning (ACT, Diffusion, Pi0, SmolVLA, Groot) via `lerobot-train`
4. **Inference**: Deploy trained policy in simulation (`lerobot-eval`)
5. **Simulation**: Isaac Sim running the Ubtech_sim pipeline for task evaluation

## Commands

### Docker

```bash
./run.sh                    # Interactive (requires display)
./run.sh --headless         # Headless mode (no display needed)
```

Environment overrides: `IMAGE_NAME`, `CONTAINER_NAME`, `HEADLESS`, `HOST_WORKSPACE`.

### Data Recording (Keyboard Teleoperation)

```bash
# Inside Docker container (use /isaac-sim/python.sh):
/isaac-sim/python.sh src/lerobot/scripts/lerobot_record.py \
    --robot.type=walker_s2_sim \
    --robot.headless=false \
    --teleop.type=walker_s2_keyboard \
    --task=Part_Sorting \
    --dataset.root=datasets/my_dataset \
    --dataset.repo_id=local/my_dataset \
    --dataset.num_episodes=10 \
    --dataset.fps=30 \
    --dataset.video=false
```

### Task2 FSM Auto-Collection

```bash
# Outside Docker (or inside):
./collect_task2.sh
# Overridable env vars: NUM_EPISODES, DATASET_ROOT, HEADLESS, VIDEO, etc.
```

### Training

```bash
# Inside Docker:
/isaac-sim/python.sh src/lerobot/scripts/lerobot_train.py \
    --policy.path=lerobot/smolvla_base \
    --dataset.repo_id=task1 \
    --dataset.root=datasets/task1 \
    --dataset.video_backend=pyav \
    --batch_size=64 \
    --steps=20000 \
    --output_dir=outputs/train/my_run \
    --policy.device=cuda \
    --wandb.enable=false
```

With explicit policy type (e.g., SmolVLA with full hyperparameters):

```bash
/isaac-sim/python.sh src/lerobot/scripts/lerobot_train.py \
    --dataset.repo_id=your_org/your_dataset \
    --policy.type=smolvla \
    --policy.vlm_model_name=HuggingFaceTB/SmolVLM2-500M-Video-Instruct \
    --policy.load_vlm_weights=true \
    --policy.dtype=float32 \
    --policy.n_obs_steps=1 \
    --policy.chunk_size=50 \
    --policy.n_action_steps=50 \
    --policy.max_state_dim=32 \
    --policy.max_action_dim=32 \
    --policy.num_steps=10 \
    --output_dir=outputs/train/my_run \
    --batch_size=8 \
    --steps=100000
```

### Evaluation

```bash
/isaac-sim/python.sh src/lerobot/scripts/lerobot_eval.py --policy.path=outputs/train/my_run
```

### Replay

```bash
lerobot-replay --robot.type=walker_s2_sim --dataset.repo_id=...
```

### Simulation Standalone

```bash
python Ubtech_sim/main.py
```

### Linting

```bash
ruff check src/lerobot/    # Lint source
ruff format src/lerobot/   # Auto-format
```

Test: `pytest` (config in `pyproject.toml`, test extras via `lerobot[test]`).

## Available CLI Scripts

All defined in `pyproject.toml` under `[project.scripts]`:

| Command | Purpose |
|---------|---------|
| `lerobot-record` | Keyboard teleoperation + recording |
| `lerobot-replay` | Replay dataset episodes |
| `lerobot-train` | Train imitation learning policy |
| `lerobot-eval` | Evaluate trained policy |
| `lerobot-teleoperate` | Teleoperation only (no recording) |
| `lerobot-calibrate` | Calibrate robot |
| `lerobot-find-cameras` | Discover camera devices |
| `lerobot-dataset-viz` | Visualize dataset episodes |
| `lerobot-edit-dataset` | Edit/manage datasets |
| `lerobot-info` | Show dataset information |
| `lerobot-find-port` | Find motor serial ports |
| `lerobot-setup-motors` | Setup motor configurations |
| `lerobot-setup-can` | Setup CAN bus for motors |

## Key Configuration

- **Policy configs**: `PreTrainedConfig` variants (draccus-based dataclasses). Training uses `TrainPipelineConfig`.
- **Robot config**: `WalkerS2Config` loaded from `src/lerobot/robots/walker_s2_sim/walkers2simConfig.py`
- **Task configs**: YAML files in `Ubtech_sim/config/` — define scene layout, parts, grasp parameters, FSM settings
- **Walker S2 state space**: 20D = 14 arm joints (7/arm) + 4 finger joints + 2 gripper commands
- **4 cameras**: `head_left`, `head_right`, `wrist_left`, `wrist_right` (RGB, 640x480, 30fps)

## Key Dependencies

- **PyTorch** (>=2.2.1), **torchvision**, **torchcodec**
- **NVIDIA Isaac Sim 5.1** (base Docker image `nvcr.io/nvidia/isaac-sim:5.1.0`)
- **Hugging Face**: `datasets`, `diffusers`, `huggingface-hub`, `accelerate`, `transformers`
- **Pinocchio** (robot kinematics), **gymnasium** (env interface)
- **wandb** (experiment tracking), **draccus** (config management)

## Environment Variables

- `DISPLAY` — Required for non-headless mode (X11 forwarding)
- `PYTHONPATH` — Set to workspace root inside container
- `ACCEPT_EULA`, `PRIVACY_CONSENT` — Required for Isaac Sim EULA
- `UBTECH_HEADLESS` — Headless mode for standalone simulation
- `UBTECH_TASK_CONFIG` — Override task config path for `Ubtech_sim/main.py`
- `IMAGE_NAME`, `CONTAINER_NAME`, `HEADLESS`, `HOST_WORKSPACE` — Docker run.sh overrides

## Memory & Context

- `outputs/train/` — Training run outputs (excluded from git)
- `datasets/` — Training datasets (large, excluded from git)
- `logs/` — Execution logs (excluded from git)
- WandB logging is configured via `WandBConfig` in training configs
