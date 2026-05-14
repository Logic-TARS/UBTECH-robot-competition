# UBTECH Robot Competition 2026

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Isaac Sim](https://img.shields.io/badge/Simulation-NVIDIA%20Isaac%20Sim-76B900)](https://developer.nvidia.com/isaac-sim)
[![LeRobot](https://img.shields.io/badge/Robot%20Learning-LeRobot-FF6F00)](https://github.com/huggingface/lerobot)
[![Project](https://img.shields.io/badge/Project-Humanoid%20Manipulation-4B5563)]()

[中文](README.zh-CN.md) · [Official Baseline Reference](docs/official_baseline_README.md)

> Competition-ready humanoid robot manipulation pipeline built on the GHRC 2026 / UBTECH official baseline. This repo focuses on **environment understanding, conveyor belt sorting adaptation, data collection pipeline validation, and imitation learning engineering** — not reinventing the framework, but making it work for real competition tasks.

---

## Background

The Global Humanoid Robot Challenge (GHRC) 2026 tasks participants with completing industrial manipulation scenarios in NVIDIA Isaac Sim — picking, sorting, placing, and assembly. The official baseline provides the full stack:

- **Isaac Sim** simulation environment
- **Walker S2** humanoid robot teleoperation
- **LeRobotDataset V2.1** data format
- **ACT / Pi0** imitation learning training
- **Docker** containerized deployment

My role: understand the baseline, adapt it to specific competition tasks, debug the pipeline, and prepare it for strategy training and evaluation.

## What I Did

### 1. Baseline Engineering & Reproducibility

Organized the official baseline into a reproducible, debuggable project structure. Key entry points:

| Component | Description |
|-----------|-------------|
| `run.sh` | Docker + Isaac Sim container launcher |
| `run_walker_s2_teleop.sh` | Walker S2 teleoperation launcher |
| `lerobot/scripts/control_robot.py` | Unified teleoperate / record / replay / inference entry point |
| `lerobot/scripts/train.py` | Imitation learning trainer (ACT / Pi0) |
| `Ubtech_sim/config/` | Competition task YAML configurations |
| `Ubtech_sim/source/` | Scene building, robot control, IK, grasp planning |

The value: turning a large, opaque official baseline into something you can actually run, debug, and experiment with.

### 2. Conveyor Belt Sorting Task

The current branch (`conveyor_speed_change`) focuses on **Conveyor Belt Sorting** — the robot must identify parts moving on a conveyor belt and sort them into correct bins.

- `Ubtech_sim/config/Conveyor_Sorting.yaml` — task configuration
- Conveyor speed, direction, and object spawn timing
- Part types with random poses (blue reducer A / natural servo assembly B)
- Grasp timing and end-effector control
- Sorting success/failure detection

The difficulty here is not just the model — it's getting stable object physics, robot grasp windows, data logging, and task reset logic working together in simulation.

### 3. Isaac Sim + LeRobot Integration

Connecting Isaac Sim simulation state (camera images, joint control) with LeRobot's data and policy interface is the core technical challenge. Relevant modules:

| Module | Purpose |
|--------|---------|
| `Ubtech_sim/source/SceneBuilder.py` | Task scene construction and USD asset loading |
| `Ubtech_sim/source/grasp_planner.py` | Grasp planning and real-time tracking |
| `lerobot/common/robot_devices/robots/isaac_sim_robot_interface.py` | Isaac Sim robot interface |
| `lerobot/common/robot_devices/robots/mobile_manipulator.py` | Mobile manipulator abstraction |
| `lerobot/common/robot_devices/robots/configs.py` | Robot and task configuration entry |

### 4. Data Pipeline & Training Flow

The baseline supports end-to-end imitation learning:

1. Load a task scene in Isaac Sim
2. Teleoperate Walker S2 to complete the task
3. Record images, states, and actions as LeRobotDataset V2.1
4. Train with ACT or Pi0
5. Deploy the trained policy back into simulation for evaluation

This demonstrates understanding of the full robot learning pipeline — not just training a model, but keeping the scene, robot interface, data quality, training, and evaluation all under control.

## Competition Tasks

| Task | Name | Focus |
| --- | --- | --- |
| Task 1 | Part Sorting | Pick and place parts into bins |
| Task 2 | Conveyor Belt Sorting | Dynamic sorting on moving conveyor |
| Task 3 | Foam Inlaying | Insert parts into foam cutouts |
| Task 4 | Packing Box | Manipulate folding box joints |

Task 2 (Conveyor Sorting) is the primary focus of the current branch.

## Tech Stack

| Area | Technology |
| --- | --- |
| Simulation | NVIDIA Isaac Sim 5.1+ |
| Robot Learning | Hugging Face LeRobot |
| Robot Platform | Walker S2 humanoid / mobile manipulator |
| Learning Methods | Imitation Learning, ACT, Pi0 |
| Data Format | LeRobotDataset V2.1 |
| Runtime | Docker, NVIDIA Container Toolkit, CUDA 12.8+ |
| Language | Python 3.11+ |

## Quick Start

```bash
# 1. Clone with submodules
git clone --recursive https://github.com/Logic-TARS/UBTECH-Robot-Competition-2026.git
cd UBTECH-Robot-Competition-2026

# 2. Download data and pretrained weights
pip install huggingface-hub
huggingface-cli download UBTECH-Robotics/challenge2026_dataset \
  --local-dir ./datasets --repo-type dataset
huggingface-cli download UBTECH-Robotics/challenge2026_baseline \
  --local-dir ./challenge2026_baseline --repo-type model

# 3. Launch container
sudo ./run.sh
```

### Teleoperate Walker S2

```bash
/isaac-sim/python.sh lerobot/scripts/control_robot.py \
  --robot.type=walker_s2_sim \
  --control.type=teleoperate \
  --control.task=Conveyor_Sorting \
  --control.fps=30 \
  --control.display_cameras=true
```

### Record Training Data

```bash
/isaac-sim/python.sh lerobot/scripts/control_robot.py \
  --robot.type=walker_s2_sim \
  --control.type=record \
  --control.task=Conveyor_Sorting \
  --control.root=./datasets/Conveyor_Sorting/v1 \
  --control.repo_id=local/Conveyor_Sorting \
  --control.num_episodes=50 \
  --control.fps=30 \
  --control.video=true \
  --control.push_to_hub=false
```

### Train ACT Policy

```bash
/isaac-sim/python.sh lerobot/scripts/train.py \
  --dataset.repo_id=local/Conveyor_Sorting \
  --dataset.root=./datasets/Conveyor_Sorting/v1 \
  --policy.type=act \
  --policy.device=cuda \
  --policy.use_amp=true \
  --output_dir=challenge2026_baseline/Conveyor_Sorting/act_001 \
  --batch_size=8 \
  --steps=100000
```

## Repository Structure

```text
.
├── Ubtech_sim/
│   ├── config/              # Task YAML configs (Conveyor_Sorting.yaml, etc.)
│   ├── source/              # SceneBuilder, IK, grasp planning, robot control
│   └── main.py              # Standalone Isaac Sim entry point
├── lerobot/                 # LeRobot core (scripts, policies, robot interfaces)
├── assets/                  # Simulation assets (git submodule)
├── datasets/                # LeRobotDataset training data
├── challenge2026_baseline/  # Pretrained weights
├── docs/
│   └── official_baseline_README.md  # Original official baseline docs
├── run.sh                   # Docker container launcher
├── Dockerfile
└── pyproject.toml
```

## Skills Demonstrated

This project showcases practical abilities in robot learning and simulation engineering:

- **Reading and adapting large official baselines** — understanding the architecture, finding the right configuration points, and making targeted changes
- **Isaac Sim + LeRobot integration** — connecting simulation state, camera data, joint control with a data/policy framework
- **Competition task engineering** — configuring conveyor dynamics, grasp timing, object spawning, and reset logic for reliable data collection
- **Full pipeline thinking** — from scene setup → teleoperation → data recording → policy training → evaluation, each stage affects the next

## Current Status & Next Steps

The baseline pipeline is organized and the conveyor sorting task is configured. Next steps for a complete competition submission:

- Conveyor speed variation behavior comparison
- Teleoperation demo video / GIF
- Dataset statistics (episodes, camera views, action dimensions, sampling rate)
- ACT / Pi0 training curves and inference success rates
- Failure case analysis (grasp timing, object slipping, mis-sorting, reset instability)
- Final competition score or阶段性 results

## Acknowledgements

This project builds on the UBTECH / GHRC 2026 official baseline, [Hugging Face LeRobot](https://github.com/huggingface/lerobot), and [NVIDIA Isaac Sim](https://developer.nvidia.com/isaac-sim). The underlying frameworks, robot assets, task definitions, and pretrained resources belong to their respective maintainers. This repository documents my configuration, adaptation, and experimental work on top of that foundation.

## Author

- GitHub: [Logic-TARS](https://github.com/Logic-TARS)
