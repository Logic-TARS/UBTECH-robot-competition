#!/usr/bin/env bash
# =============================================================================
# FSM 自动数采启动脚本 — Task2 Conveyor Sorting
#
# 在 Docker 容器内启动 lerobot-record + FSM 自动采集。
# 支持可视化和无头模式。
#
# 用法:
#   ./start_fsm_collect.sh              # 可视化模式（默认）
#   HEADLESS=true ./start_fsm_collect.sh # 无头模式
#
# 其他可覆盖变量:
#   NUM_EPISODES=5  EPISODE_TIME_S=600  DATASET_ROOT=datasets/my_data
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

# ========================== 配置（可覆盖） ==========================
HEADLESS="${HEADLESS:-false}"
NUM_EPISODES="${NUM_EPISODES:-50}"
EPISODE_TIME_S="${EPISODE_TIME_S:-10000}"
DATASET_ROOT="${DATASET_ROOT:-datasets/Conveyor_Sorting/episode_task2_v1}"
REPO_ID="${REPO_ID:-local/task2_conveyor_sorting}"
IMAGE_NAME="${IMAGE_NAME:-isaacsim5.1_lerobot5.1_ubtech:v1}"
CONTAINER_NAME="${CONTAINER_NAME:-isaac_sim_fsm}"
RESET_TIME_S="${RESET_TIME_S:-10}"
FPS="${FPS:-30}"
VIDEO="${VIDEO:-false}"

# ========================== 颜色 ==========================
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }

DOCKER_TTY_ARGS=()
if [ -t 0 ] && [ -t 1 ]; then
    DOCKER_TTY_ARGS=(-it)
else
    warn "当前不是交互式 TTY，docker run 将不使用 -it"
fi

# ========================== 前置检查 ==========================
if ! command -v docker &>/dev/null; then
    echo "[ERROR] 请先安装 Docker"
    exit 1
fi

if [ "$HEADLESS" = "false" ] && [ -z "${DISPLAY:-}" ]; then
    echo "[ERROR] DISPLAY 未设置，无法启动可视化模式。使用 HEADLESS=true 运行无头模式。"
    exit 1
fi

# ========================== 清理旧容器 ==========================
if docker container inspect "$CONTAINER_NAME" &>/dev/null 2>&1; then
    warn "清除旧容器 ${CONTAINER_NAME} ..."
    docker rm -f "$CONTAINER_NAME" &>/dev/null || true
fi

# ========================== 启动容器并执行 ==========================
info "启动 Isaac Sim + FSM 自动数采..."
info "任务: Conveyor_Sorting | 采集 ${NUM_EPISODES} 个 episode"
info "模式: $([ "$HEADLESS" = "true" ] && echo '无头' || echo '可视化')"
info "输出: ${DATASET_ROOT}"
echo ""

if [ "$HEADLESS" = "false" ]; then
    xhost +local:docker &>/dev/null 2>&1 || true
fi

docker run "${DOCKER_TTY_ARGS[@]}" --rm \
    --name "$CONTAINER_NAME" \
    --entrypoint /bin/bash \
    --privileged \
    --network host \
    --gpus all \
    --shm-size=8g \
    $([ "$HEADLESS" = "false" ] && echo "-e DISPLAY=$DISPLAY -e QT_X11_NO_MITSHM=1 -e XAUTHORITY=/tmp/.docker.xauth -v /tmp/.X11-unix:/tmp/.X11-unix:rw") \
    -e NO_AT_BRIDGE=1 \
    -e ACCEPT_EULA=Y \
    -e PRIVACY_CONSENT=Y \
    -e XDG_RUNTIME_DIR=/tmp \
    -e PYTHONPATH=/workspace/GlobalHumanoidRobotChallenge_2026_Baseline \
    -v "${SCRIPT_DIR}:/workspace/GlobalHumanoidRobotChallenge_2026_Baseline:rw" \
    -v "${HOME}/.cache/isaac_sim_container/cache/kit:/root/.cache/kit:rw" \
    -v "${HOME}/.cache/isaac_sim_container/cache/ov:/root/.cache/ov:rw" \
    -v "${HOME}/.cache/isaac_sim_container/cache/pip:/root/.cache/pip:rw" \
    -v "${HOME}/.cache/isaac_sim_container/cache/glcache:/root/.cache/nvidia/GLCache:rw" \
    -v "${HOME}/.cache/isaac_sim_container/cache/computecache:/root/.cache/nvidia/ComputeCache:rw" \
    -v "${HOME}/.cache/isaac_sim_container/data:/root/.local/share/ov/data:rw" \
    -v "${HOME}/.cache/isaac_sim_container/documents:/root/Documents:rw" \
    -v "${HOME}/.cache/huggingface:/root/.cache/huggingface:rw" \
    "${IMAGE_NAME}" \
    -c "
pip install setuptools -q && \
cd /workspace/GlobalHumanoidRobotChallenge_2026_Baseline && \
pip install -e . --no-build-isolation --no-deps -q 2>&1 && \
HEADLESS=${HEADLESS} \
NUM_EPISODES=${NUM_EPISODES} \
EPISODE_TIME_S=${EPISODE_TIME_S} \
/isaac-sim/python.sh src/lerobot/scripts/lerobot_record.py \
  --robot.type=walker_s2_sim \
  --robot.headless=${HEADLESS} \
  --robot.head_viz_enabled=false \
  --teleop.type=walker_s2_keyboard \
  --task=Conveyor_Sorting \
  --dataset.root=${DATASET_ROOT} \
  --dataset.repo_id=${REPO_ID} \
  --dataset.num_episodes=${NUM_EPISODES} \
  --dataset.fps=${FPS} \
  --dataset.episode_time_s=${EPISODE_TIME_S} \
  --dataset.reset_time_s=${RESET_TIME_S} \
  --dataset.single_task=Conveyor_Sorting \
  --dataset.video=${VIDEO} \
  --dataset.push_to_hub=false \
  --dataset.num_image_writer_threads_per_camera=4 \
  --display_data=false \
  --play_sounds=false \
  --resume=false
"

if [ "$HEADLESS" = "false" ]; then
    xhost -local:docker &>/dev/null 2>&1 || true
fi

info "FSM 自动数采已退出"
