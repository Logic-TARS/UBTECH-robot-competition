#!/usr/bin/env bash
# =============================================================================
#  Unified auto-collection launcher for UBTECH tasks.
#
#  This file is intended to be called by task-specific wrappers:
#    scripts/auto_collect_task1.sh
#    scripts/auto_collect_task2.sh
#    scripts/auto_collect_task3.sh
#    scripts/auto_collect_task4.sh
#
#  Common overrides:
#    IMAGE_NAME=isaacsim5.1_lerobot5.1_ubtech:v1
#    NUM_EPISODES=50
#    REPO_ID=local/my_dataset
#    FPS=30
#    OBJECTS_PER_EPISODE=2
# =============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info() { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

HEADLESS=0
for arg in "$@"; do
    case "$arg" in
        --headless) HEADLESS=1 ;;
        -h|--help)
            cat <<EOF
Usage:
  $0 [--headless]

Environment overrides:
  IMAGE_NAME, CONTAINER_NAME, HOST_WORKSPACE, CONTAINER_WORKSPACE
  TASK, TASK_LABEL, REPO_ID, NUM_EPISODES, FPS, VIDEO
  OBJECTS_PER_EPISODE, RECORD_DATA, PUSH_TO_HUB, RESUME
EOF
            exit 0
            ;;
        *) error "未知参数: $arg"; exit 1 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

TASK="${TASK:?TASK must be set by the task wrapper}"
TASK_LABEL="${TASK_LABEL:-${TASK}}"
TASK_NUMBER="${TASK_NUMBER:-task}"

IMAGE_NAME="${IMAGE_NAME:-isaacsim5.1_lerobot5.1_ubtech:v1}"
CONTAINER_NAME="${CONTAINER_NAME:-isaac_sim_auto_collect_${TASK_NUMBER}}"
HOST_WORKSPACE="${HOST_WORKSPACE:-${PROJECT_ROOT}}"
CONTAINER_WORKSPACE="${CONTAINER_WORKSPACE:-/workspace/GlobalHumanoidRobotChallenge2026_Baseline}"
SHM_SIZE="${SHM_SIZE:-8g}"

ISAAC_CACHE_ROOT="${ISAAC_CACHE_ROOT:-${HOME}/.cache/isaac_sim_container}"
HF_CACHE="${HF_CACHE:-${HOME}/.cache/huggingface}"

REPO_ID="${REPO_ID:-local/${TASK}}"
ROOT_DIR="${ROOT_DIR:-datasets/${TASK}/batch1}"
NUM_EPISODES="${NUM_EPISODES:-50}"
RECORD_DATA="${RECORD_DATA:-true}"
FPS="${FPS:-30}"
VIDEO="${VIDEO:-true}"
OBJECTS_PER_EPISODE="${OBJECTS_PER_EPISODE:-1}"
PUSH_TO_HUB="${PUSH_TO_HUB:-false}"
RESUME="${RESUME:-false}"
HEAD_VIZ_ENABLED="${HEAD_VIZ_ENABLED:-false}"
SINGLE_TASK="${SINGLE_TASK:-${TASK}}"
AUTO_COLLECT_ENTRY="${AUTO_COLLECT_ENTRY:-auto_collect_unzipped/lerobot/scripts/programmatic_control.py}"

info "任务        : ${TASK_LABEL} (${TASK})"
info "镜像        : ${IMAGE_NAME}"
info "容器名      : ${CONTAINER_NAME}"
info "Headless    : $([ "$HEADLESS" -eq 1 ] && echo '是' || echo '否')"
info "数据集 ID   : ${REPO_ID}"
info "输出目录    : ${ROOT_DIR}"
info "Episode 数  : ${NUM_EPISODES}"
info "FPS         : ${FPS}"

if ! command -v docker &>/dev/null; then
    error "未找到 docker，请先安装 Docker"
    exit 1
fi

if [ "$(id -u)" -ne 0 ] && ! docker info &>/dev/null 2>&1; then
    warn "无 docker 权限，自动以 sudo 重新执行..."
    exec sudo --preserve-env=DISPLAY,HEADLESS,IMAGE_NAME,CONTAINER_NAME,HOST_WORKSPACE,CONTAINER_WORKSPACE,SHM_SIZE,ISAAC_CACHE_ROOT,HF_CACHE,TASK,TASK_LABEL,TASK_NUMBER,REPO_ID,ROOT_DIR,NUM_EPISODES,RECORD_DATA,FPS,VIDEO,OBJECTS_PER_EPISODE,PUSH_TO_HUB,RESUME,HEAD_VIZ_ENABLED,SINGLE_TASK,AUTO_COLLECT_ENTRY \
        "$0" "$@"
fi

if ! command -v nvidia-smi &>/dev/null || ! nvidia-smi &>/dev/null; then
    error "未找到 NVIDIA GPU 驱动"
    exit 1
fi

for d in cache/kit cache/ov cache/pip cache/glcache cache/computecache data documents; do
    mkdir -p "${ISAAC_CACHE_ROOT}/${d}"
done
mkdir -p "${HF_CACHE}"

if docker container inspect "$CONTAINER_NAME" &>/dev/null 2>&1; then
    info "清除旧容器 ${CONTAINER_NAME} ..."
    docker rm -f "$CONTAINER_NAME" &>/dev/null || true
fi

DOCKER_ARGS=(
    --name "$CONTAINER_NAME"
    --privileged
    --network host
    --user root
    --gpus all
    --shm-size="$SHM_SIZE"
    --restart no
)

VIDEO_GID="$(getent group video 2>/dev/null | cut -d: -f3 || true)"
if [ -n "$VIDEO_GID" ]; then
    DOCKER_ARGS+=(--group-add "$VIDEO_GID")
fi
for grp in plugdev input; do
    GID="$(getent group "$grp" 2>/dev/null | cut -d: -f3 || true)"
    [ -n "$GID" ] && DOCKER_ARGS+=(--group-add "$GID")
done

if [ "$HEADLESS" -eq 0 ]; then
    if [ -z "${DISPLAY:-}" ]; then
        error "DISPLAY 未设置，请连接显示器或使用 --headless"
        exit 1
    fi
    info "配置 X11 显示转发..."
    xhost +local:docker &>/dev/null 2>&1 || true
    xhost +SI:localuser:root &>/dev/null 2>&1 || true
    DOCKER_ARGS+=(
        -e DISPLAY="$DISPLAY"
        -e QT_X11_NO_MITSHM=1
        -e XAUTHORITY=/tmp/.docker.xauth
        -v /tmp/.X11-unix:/tmp/.X11-unix:rw
    )
else
    info "无头模式，跳过 X11 配置"
fi

DOCKER_ARGS+=(
    -v "${HOST_WORKSPACE}:${CONTAINER_WORKSPACE}:rw"
    -w "${CONTAINER_WORKSPACE}"
    -v "${ISAAC_CACHE_ROOT}/cache/kit:/root/.cache/kit:rw"
    -v "${ISAAC_CACHE_ROOT}/cache/ov:/root/.cache/ov:rw"
    -v "${ISAAC_CACHE_ROOT}/cache/pip:/root/.cache/pip:rw"
    -v "${ISAAC_CACHE_ROOT}/cache/glcache:/root/.cache/nvidia/GLCache:rw"
    -v "${ISAAC_CACHE_ROOT}/cache/computecache:/root/.cache/nvidia/ComputeCache:rw"
    -v "${ISAAC_CACHE_ROOT}/data:/root/.local/share/ov/data:rw"
    -v "${ISAAC_CACHE_ROOT}/documents:/root/Documents:rw"
    -v "${HF_CACHE}:/root/.cache/huggingface:rw"
)

for dev_path in /dev/bus/usb /dev/input /run/udev /var/run/dbus; do
    [ -e "$dev_path" ] && DOCKER_ARGS+=(-v "${dev_path}:${dev_path}:rw")
done
for cam in /dev/video*; do
    [ -e "$cam" ] && DOCKER_ARGS+=(-v "${cam}:${cam}")
done

DOCKER_ARGS+=(
    -e NO_AT_BRIDGE=1
    -e ACCEPT_EULA=Y
    -e PRIVACY_CONSENT=Y
    -e XDG_RUNTIME_DIR=/tmp
    -e QT_QPA_PLATFORM=offscreen
    -e "PYTHONPATH=${CONTAINER_WORKSPACE}/auto_collect_unzipped:${CONTAINER_WORKSPACE}:${CONTAINER_WORKSPACE}/src"
)

HEADLESS_FLAG="false"
[ "$HEADLESS" -eq 1 ] && HEADLESS_FLAG="true"

INIT_CMD="pip install -e . --no-deps --no-build-isolation -q && \
echo '[INIT] 启动 ${TASK_LABEL} 自动数采...' && \
/isaac-sim/python.sh ${AUTO_COLLECT_ENTRY} \
    --robot.type=walker_s2_sim \
    --robot.headless=${HEADLESS_FLAG} \
    --robot.head_viz_enabled=${HEAD_VIZ_ENABLED} \
    --control.type=programmatic \
    --control.task=${TASK} \
    --control.root=${ROOT_DIR} \
    --control.repo_id=${REPO_ID} \
    --control.num_episodes=${NUM_EPISODES} \
    --control.fps=${FPS} \
    --control.video=${VIDEO} \
    --control.objects_per_episode=${OBJECTS_PER_EPISODE} \
    --control.single_task='${SINGLE_TASK}' \
    --control.record_data=${RECORD_DATA} \
    --control.push_to_hub=${PUSH_TO_HUB} \
    --control.resume=${RESUME}"

echo ""
echo -e "${CYAN}执行命令:${NC}"
echo -e "${CYAN}  ${INIT_CMD}${NC}"
echo ""

info "启动容器并开始 ${TASK_LABEL} 自动数据采集..."
docker run -it --rm \
    "${DOCKER_ARGS[@]}" \
    --entrypoint /bin/bash \
    "${IMAGE_NAME}" \
    -c "${INIT_CMD}"

if [ "$HEADLESS" -eq 0 ]; then
    xhost -local:docker &>/dev/null 2>&1 || true
    xhost -SI:localuser:root &>/dev/null 2>&1 || true
fi

info "数采结束，容器已退出。"
