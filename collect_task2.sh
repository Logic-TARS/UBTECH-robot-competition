#!/usr/bin/env bash
set -euo pipefail

# Automatically collect Task2 (Conveyor_Sorting) data with the local GHRC2026
# LeRobot recorder. The keyboard teleop object is still attached for framework
# compatibility, but the robot motion is driven by the Task2 conveyor FSM.
#
# Override examples:
#   NUM_EPISODES=10 DATASET_ROOT=datasets/Conveyor_Sorting/test ./collect_task2.sh
#   VIDEO=true HEADLESS=true REPO_ID=my_org/task2_conveyor ./collect_task2.sh

TASK="${TASK:-Conveyor_Sorting}"
DATASET_ROOT="${DATASET_ROOT:-datasets/Conveyor_Sorting/episode_task2_v1}"
REPO_ID="${REPO_ID:-local/task2_conveyor_sorting}"
NUM_EPISODES="${NUM_EPISODES:-50}"
FPS="${FPS:-30}"
EPISODE_TIME_S="${EPISODE_TIME_S:-10000}"
RESET_TIME_S="${RESET_TIME_S:-10}"
HEADLESS="${HEADLESS:-true}"
DISPLAY_DATA="${DISPLAY_DATA:-false}"
HEAD_VIZ_ENABLED="${HEAD_VIZ_ENABLED:-false}"
VIDEO="${VIDEO:-false}"

exec /isaac-sim/python.sh src/lerobot/scripts/lerobot_record.py \
  --robot.type=walker_s2_sim \
  --robot.headless="${HEADLESS}" \
  --robot.head_viz_enabled="${HEAD_VIZ_ENABLED}" \
  --teleop.type=walker_s2_keyboard \
  --task="${TASK}" \
  --dataset.root="${DATASET_ROOT}" \
  --dataset.repo_id="${REPO_ID}" \
  --dataset.num_episodes="${NUM_EPISODES}" \
  --dataset.fps="${FPS}" \
  --dataset.episode_time_s="${EPISODE_TIME_S}" \
  --dataset.reset_time_s="${RESET_TIME_S}" \
  --dataset.single_task="${TASK}" \
  --dataset.video="${VIDEO}" \
  --dataset.push_to_hub=false \
  --dataset.num_image_writer_threads_per_camera=4 \
  --display_data="${DISPLAY_DATA}" \
  --play_sounds=false \
  --resume=false
