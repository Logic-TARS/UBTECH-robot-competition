# UBTECH Walker S2 Simulation Teleoperation and Data Collection

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Isaac Sim](https://img.shields.io/badge/Isaac%20Sim-5.1-76B900)
![LeRobot](https://img.shields.io/badge/LeRobot-Teleoperation-FF6F00)
![Robot](https://img.shields.io/badge/Robot-Walker%20S2-4B8BBE)
![Dataset](https://img.shields.io/badge/Dataset-LeRobot%20Format-555555)

Walker S2 simulation teleoperation and LeRobot data collection for the 2026 humanoid robotics challenge.

This repository provides the simulation integration, teleoperation data-collection workflow, and containerized runtime used for **Global Humanoid Robot Challenge 2026** tasks with the **UBTECH Walker S2**. It combines Isaac Sim, LeRobot, task-scene configuration, dual-arm control utilities, and Hugging Face dataset integration.

This competition repository extends LeRobot, so it retains `lerobot` as its Python package name and preserves upstream package metadata.

[中文](README.zh-CN.md)

## Background

Walker S2 competition tasks require more than a one-off simulation demo. A reusable workflow must coordinate the Isaac Sim runtime, robot and scene assets, keyboard teleoperation, camera recording, task selection, dataset versioning, and Hugging Face access.

This project builds that workflow on top of LeRobot. It supports four competition scenes and provides reusable components for scene construction, dual-arm inverse kinematics, grasp planning, coordinate conversion, and structured data recording.

## Install

### Dependencies

- Linux
- Docker with NVIDIA Container Toolkit
- An NVIDIA GPU and a working `nvidia-smi`
- X11 for graphical mode, or the provided headless mode
- Access to the Isaac Sim image `isaac-sim-nijie-lerobot:v5`, or a compatible image supplied through `IMAGE_NAME`
- Access to the `UBTECH-Robotics/challenge2026_assets` Hugging Face repository for the `assets` submodule

Clone the repository with its simulation assets:

```bash
git clone --recurse-submodules https://github.com/Logic-TARS/UBTECH-robot-competition.git
cd UBTECH-robot-competition
```

If the repository was cloned without submodules, initialize them separately:

```bash
git submodule update --init --recursive
```

Create and enter the Isaac Sim + LeRobot container:

```bash
./run.sh
```

`run.sh` validates Docker, NVIDIA GPU access, and the display environment, mounts the project and cache directories, and installs the local source in editable mode inside the container.

## Usage

Start the container in graphical mode:

```bash
./run.sh
```

Start it without X11:

```bash
./run.sh --headless
```

After the container has been created, launch the guided Walker S2 teleoperation and recording workflow:

```bash
./run_walker_s2_teleop.sh
```

Select another task or create a new dataset version with environment variables:

```bash
TASK=Packing_Box ./run_walker_s2_teleop.sh
DATASET_MODE=new SAVE_PATH=datasets/task2/v3 ./run_walker_s2_teleop.sh
```

Run the simulation entry point directly from the container:

```bash
/isaac-sim/python.sh Ubtech_sim/main.py
```

### Recording Controls

| Key | Action |
|---|---|
| `Enter` | Start recording the current episode |
| Right arrow | Finish and save the current episode |
| Left arrow | Discard and rerecord the current episode |
| `Q` | Exit |

## Highlights

- Integrates the UBTECH Walker S2 robot, competition scenes, and simulation assets with Isaac Sim.
- Adds the `walker_s2_sim` LeRobot robot interface for keyboard teleoperation and data recording.
- Supports `Part_Sorting`, `Conveyor_Sorting`, `Foam_Inlaying`, and `Packing_Box`.
- Provides a container launcher with Docker, GPU, X11/headless, cache-mount, and editable-install checks.
- Provides a guided collection script for task selection, dataset creation or continuation, save paths, Hugging Face repositories, frame rate, camera display, and video encoding.
- Includes dual-arm inverse kinematics, grasp planning, coordinate conversion, scene construction, and structured recording modules.
- Records object poses to CSV, camera data to HDF5, and demonstrations in LeRobot dataset format.

## Results

| Challenge | Implementation | Outcome |
|---|---|---|
| Isaac Sim and LeRobot require coordinated Docker, GPU, display, and path configuration | `run.sh` validates the host and mounts project, Isaac Sim, and Hugging Face caches | Team members can enter a consistent containerized runtime through one command |
| Teleoperation commands contain many task and dataset parameters | `run_walker_s2_teleop.sh` centralizes defaults and guided configuration | Collection runs can be repeated or switched between tasks with fewer manual parameters |
| Multi-task data can be written to the wrong task or version | `TASK`, `DATASET_MODE`, and `SAVE_PATH` control task and dataset selection | Four task workflows share a consistent versioned collection process |
| Dual-arm manipulation requires planning beyond joint-level commands | `GraspPlanner`, `DualArmIK`, `CoordinateTransform`, and `RobotArticulation` form the control pipeline | Scene-object poses can be converted into planned dual-arm IK targets |
| Demonstrations need a reusable training format | Collection uses LeRobot datasets with `continue` and `new` modes | Recorded data can feed later imitation-learning, ACT, Diffusion Policy, or VLA workflows |

## Tasks

| ID | Task | Description | Default Data Directory |
|---|---|---|---|
| 1 | `Part_Sorting` | Part sorting | `datasets/task1` |
| 2 | `Conveyor_Sorting` | Conveyor sorting | `datasets/task2` |
| 3 | `Foam_Inlaying` | Foam inlaying | `datasets/task3` |
| 4 | `Packing_Box` | Box packing | `datasets/task4` |

## Architecture

The collection workflow connects the host launcher, containerized LeRobot runtime, Walker S2 simulation interface, task scene, and dataset writer:

```text
Host
├── run.sh
│   └── Isaac Sim + LeRobot container
└── run_walker_s2_teleop.sh
    └── lerobot/scripts/teleop_and_record.py
        └── walker_s2_sim
            ├── task scene and cameras
            ├── keyboard teleoperation
            └── LeRobot dataset recording
```

The `Ubtech_sim` package contains the lower-level simulation components:

| Component | Responsibility |
|---|---|
| `SceneBuilder` | Loads the robot, tables, boxes, parts, and task scene |
| `RobotArticulation` | Reads robot state and applies dual-arm control |
| `DualArmIK` | Solves dual-arm inverse kinematics with damped least squares |
| `GraspPlanner` | Selects an arm and plans target grasp poses and TCP offsets |
| `CoordinateTransform` | Converts world coordinates to the robot base frame |
| `DataLogger` | Records object poses to CSV and camera frames to HDF5 |

## Configuration

| Variable | Default | Used By |
|---|---|---|
| `IMAGE_NAME` | `isaac-sim-nijie-lerobot:v5` | `run.sh` |
| `CONTAINER_NAME` | `isaac_sim_ubt` | Both launchers |
| `CONTAINER_WORKSPACE` | `/workspace/lerobot_0.5.1` | `run.sh` |
| `CONTAINER_WORKDIR` | `/workspace/lerobot_0.5.1` | `run_walker_s2_teleop.sh` |
| `TASK` | `Conveyor_Sorting` | Teleoperation launcher |
| `DATASET_MODE` | `continue` | Teleoperation launcher |
| `SAVE_PATH` | `datasets/task2/v2` | Teleoperation launcher |
| `HF_REPO_ID` | `Logic-TARS/ubtech-task` | Teleoperation launcher |
| `FPS` | `30` | Teleoperation launcher |
| `DISPLAY_CAMERAS` | `true` | Teleoperation launcher |
| `VCODEC` | `h264` | Teleoperation launcher |

Set `HF_TOKEN` or place the token in `.secrets/hf_token` when Hugging Face authentication is required. Do not commit tokens or the `.secrets` directory.

## Repository Structure

```text
.
├── run.sh                         # Create and enter the Isaac Sim container
├── run_walker_s2_teleop.sh        # Launch guided teleoperation and recording
├── Ubtech_sim/                    # Simulation scenes, configuration, and control
│   ├── config/                    # Four task YAML files
│   ├── source/                    # Scene, robot, IK, planning, and logging modules
│   └── main.py                    # Direct simulation entry point
├── lerobot/                       # LeRobot source and Walker S2 integration
├── assets/                        # Simulation asset submodule
├── datasets/                      # Local datasets; large files should not be committed
└── docs/                          # Supplemental LeRobot documentation
```

## References

- [UBTECH simulation module](Ubtech_sim/README.md)
- [LeRobot](https://github.com/huggingface/lerobot)

## Contributing

Questions and bug reports are welcome through [GitHub Issues](https://github.com/Logic-TARS/UBTECH-robot-competition/issues), and pull requests are accepted.

Do not commit `.secrets/`, `outputs/`, `logs/`, or large generated datasets. Before collecting data, verify `TASK`, `SAVE_PATH`, and `DATASET_MODE`. Pull requests that change task configuration should identify the affected YAML file and task.

## License

[Apache-2.0](LICENSE) © 2024 The Hugging Face team. The license file also contains notices for incorporated third-party work.
