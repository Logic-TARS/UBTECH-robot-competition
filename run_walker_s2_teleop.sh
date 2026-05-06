#!/usr/bin/env bash
set -euo pipefail

# ========================== 中文输出工具 ==========================
if [[ -t 1 ]]; then
  RED=$'\033[0;31m'
  GREEN=$'\033[0;32m'
  YELLOW=$'\033[1;33m'
  CYAN=$'\033[0;36m'
  BOLD=$'\033[1m'
  NC=$'\033[0m'
else
  RED=''
  GREEN=''
  YELLOW=''
  CYAN=''
  BOLD=''
  NC=''
fi

info() { echo -e "${GREEN}[信息]${NC} $*"; }
warn() { echo -e "${YELLOW}[提醒]${NC} $*" >&2; }
error() { echo -e "${RED}[错误]${NC} $*" >&2; }

CONTAINER_NAME="${CONTAINER_NAME:-isaac_sim_ubt}"
CONTAINER_WORKDIR="${CONTAINER_WORKDIR:-/workspace/lerobot_0.5.1}"
HF_REPO_ID="${HF_REPO_ID:-Logic-TARS/ubtech-task}"
DATASET_MODE="${DATASET_MODE:-continue}"
SAVE_PATH="${SAVE_PATH:-datasets/task2/v2}"
TASK="${TASK:-Conveyor_Sorting}"
FPS="${FPS:-30}"
DISPLAY_CAMERAS="${DISPLAY_CAMERAS:-true}"
TELEOP_TIME_S="${TELEOP_TIME_S:-100000000}"
VCODEC="${VCODEC:-h264}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HF_TOKEN_FILE="${HF_TOKEN_FILE:-${SCRIPT_DIR}/.secrets/hf_token}"

AVAILABLE_TASKS=(
  Part_Sorting
  Conveyor_Sorting
  Foam_Inlaying
  Packing_Box
)

usage() {
  cat <<EOF
${BOLD}Walker S2 遥操作采集启动脚本${NC}

用途：
  在 Docker 容器中启动 Isaac Sim + LeRobot 的 Walker S2 遥操作/数据采集程序。

最常用启动方式：
  ./run_walker_s2_teleop.sh

第一次使用前请确认：
  1. 已先运行 ./run.sh 创建过容器，容器名通常是 ${CONTAINER_NAME}
  2. Docker 正常可用：docker ps -a
  3. 需要上传/访问 Hugging Face 时，已设置 HF_TOKEN 或写入 .secrets/hf_token

启动后的基本按键：
  Enter       开始录制当前 Episode
  方向键右    结束并保存当前 Episode，进入下一集
  方向键左    放弃并重录当前 Episode
  Q           退出程序

可选任务：
  Part_Sorting      零件分拣
  Conveyor_Sorting  传送带分拣（默认）
  Foam_Inlaying     泡棉嵌入
  Packing_Box       装箱

常用示例：
  TASK=Packing_Box ./run_walker_s2_teleop.sh
  SAVE_PATH=datasets/task2/v3 ./run_walker_s2_teleop.sh
  DATASET_MODE=new SAVE_PATH=datasets/task2/v3 ./run_walker_s2_teleop.sh
  CONTAINER_NAME=你的容器名 ./run_walker_s2_teleop.sh

可覆盖的环境变量：
  CONTAINER_NAME      Docker 容器名，默认 ${CONTAINER_NAME}
  CONTAINER_WORKDIR   容器内项目目录，默认 ${CONTAINER_WORKDIR}
  TASK                任务名，默认 ${TASK}
  DATASET_MODE        数据集模式，默认 ${DATASET_MODE}，常用 new 或 continue
  SAVE_PATH           数据保存路径，默认 ${SAVE_PATH}
  HF_REPO_ID          Hugging Face 数据集仓库，默认 ${HF_REPO_ID}
  HF_TOKEN_FILE       token 文件，默认 ${HF_TOKEN_FILE}
  FPS                 采集帧率，默认 ${FPS}
  DISPLAY_CAMERAS     是否显示相机画面，默认 ${DISPLAY_CAMERAS}
  TELEOP_TIME_S       单次遥操作最长秒数，默认 ${TELEOP_TIME_S}
  VCODEC              视频编码，默认 ${VCODEC}
  QUIET_GUIDE=1       启动时不显示新手引导
  SKIP_PROMPT=1       启动时不询问配置，直接使用默认值/环境变量

更多说明：
  docs/run_walker_s2_teleop.md
EOF
}

print_beginner_guide() {
  if [[ "${QUIET_GUIDE:-0}" == "1" ]]; then
    return
  fi

  cat <<EOF
${CYAN}${BOLD}
================ Walker S2 遥操作采集 ================
${NC}${BOLD}你现在要做的事：${NC}
  1. 脚本会检查 Docker 和容器，然后进入容器启动仿真。
  2. Isaac Sim 窗口打开后，按终端提示操作。
  3. 每一集录制完成后，按方向键右保存；按 Q 退出。

${BOLD}本次配置：${NC}
  容器名        : ${CONTAINER_NAME}
  容器工作目录  : ${CONTAINER_WORKDIR}
  任务          : ${TASK}
  数据集模式    : ${DATASET_MODE}
  保存路径      : ${SAVE_PATH}
  HF Repo       : ${HF_REPO_ID}
  帧率          : ${FPS}
  显示相机      : ${DISPLAY_CAMERAS}
  视频编码      : ${VCODEC}

${BOLD}常用改法：${NC}
  换任务：TASK=Packing_Box ./run_walker_s2_teleop.sh
  新版本：DATASET_MODE=new SAVE_PATH=datasets/task2/v3 ./run_walker_s2_teleop.sh
  看帮助：./run_walker_s2_teleop.sh --help
${CYAN}======================================================${NC}

EOF
}

validate_task() {
  local task="$1"
  local candidate
  for candidate in "${AVAILABLE_TASKS[@]}"; do
    if [[ "${candidate}" == "${task}" ]]; then
      return 0
    fi
  done

  error "未知任务：${task}"
  echo "可选任务：" >&2
  printf '  - %s\n' "${AVAILABLE_TASKS[@]}" >&2
  echo "示例：TASK=Conveyor_Sorting ./run_walker_s2_teleop.sh" >&2
  exit 1
}

ask_with_default() {
  local prompt="$1"
  local default_value="$2"
  local answer

  read -r -p "${prompt} [默认: ${default_value}]: " answer
  if [[ -n "${answer}" ]]; then
    printf '%s' "${answer}"
  else
    printf '%s' "${default_value}"
  fi
}

ask_yes_no() {
  local prompt="$1"
  local default_value="${2:-Y}"
  local answer

  while true; do
    read -r -p "${prompt} [Y/n]: " answer
    answer="${answer:-${default_value}}"
    case "${answer}" in
      y|Y|yes|YES|Yes|是|好|开始) return 0 ;;
      n|N|no|NO|No|否|不|取消) return 1 ;;
      *) warn "请输入 Y 或 n。" ;;
    esac
  done
}

ask_task() {
  local default_task="$1"
  local answer

  while true; do
    echo "请选择任务：" >&2
    echo "  1) Part_Sorting      零件分拣" >&2
    echo "  2) Conveyor_Sorting  传送带分拣" >&2
    echo "  3) Foam_Inlaying     泡棉嵌入" >&2
    echo "  4) Packing_Box       装箱" >&2
    read -r -p "输入序号或任务名 [默认: ${default_task}]: " answer
    answer="${answer:-${default_task}}"

    case "${answer}" in
      1) printf '%s' "Part_Sorting"; return 0 ;;
      2) printf '%s' "Conveyor_Sorting"; return 0 ;;
      3) printf '%s' "Foam_Inlaying"; return 0 ;;
      4) printf '%s' "Packing_Box"; return 0 ;;
      Part_Sorting|Conveyor_Sorting|Foam_Inlaying|Packing_Box)
        printf '%s' "${answer}"
        return 0
        ;;
      *)
        warn "任务名不正确，请重新选择。"
        ;;
    esac
  done
}

ask_dataset_mode() {
  local default_mode="$1"
  local answer

  while true; do
    read -r -p "数据集模式：continue=续录，new=新建 [默认: ${default_mode}]: " answer
    answer="${answer:-${default_mode}}"
    case "${answer}" in
      continue|new)
        printf '%s' "${answer}"
        return 0
        ;;
      *)
        warn "请输入 continue 或 new。"
        ;;
    esac
  done
}

ask_true_false() {
  local prompt="$1"
  local default_value="$2"
  local answer

  while true; do
    read -r -p "${prompt} true/false [默认: ${default_value}]: " answer
    answer="${answer:-${default_value}}"
    case "${answer}" in
      true|True|TRUE|y|Y|yes|YES|Yes|是|显示)
        printf '%s' "true"
        return 0
        ;;
      false|False|FALSE|n|N|no|NO|No|否|不显示)
        printf '%s' "false"
        return 0
        ;;
      *)
        warn "请输入 true 或 false。"
        ;;
    esac
  done
}

interactive_prompt() {
  if [[ "${SKIP_PROMPT:-0}" == "1" ]]; then
    return
  fi

  if [[ ! -t 0 || ! -t 1 ]]; then
    warn "当前不是交互式终端，跳过启动询问，直接使用默认值/环境变量。"
    return
  fi

  echo ""
  echo "${BOLD}启动前确认配置${NC}"
  CONTAINER_NAME="$(ask_with_default "Docker 容器名" "${CONTAINER_NAME}")"
  CONTAINER_WORKDIR="$(ask_with_default "容器内项目目录" "${CONTAINER_WORKDIR}")"
  TASK="$(ask_task "${TASK}")"
  validate_task "${TASK}"
  DATASET_MODE="$(ask_dataset_mode "${DATASET_MODE}")"
  SAVE_PATH="$(ask_with_default "数据保存路径" "${SAVE_PATH}")"
  HF_REPO_ID="$(ask_with_default "Hugging Face repo id" "${HF_REPO_ID}")"
  FPS="$(ask_with_default "采集帧率 FPS" "${FPS}")"
  DISPLAY_CAMERAS="$(ask_true_false "是否显示相机画面" "${DISPLAY_CAMERAS}")"

  echo ""
  echo "${BOLD}请确认本次启动配置：${NC}"
  echo "  任务          : ${TASK}"
  echo "  数据集模式    : ${DATASET_MODE}"
  echo "  保存路径      : ${SAVE_PATH}"
  echo "  HF Repo       : ${HF_REPO_ID}"
  echo "  帧率          : ${FPS}"
  echo "  显示相机      : ${DISPLAY_CAMERAS}"
  echo "  容器名        : ${CONTAINER_NAME}"
  echo "  容器工作目录  : ${CONTAINER_WORKDIR}"

  if ! ask_yes_no "确认开始启动吗？" "Y"; then
    warn "已取消启动。"
    exit 0
  fi
}

case "${1:-}" in
  -h|--help|help)
    usage
    exit 0
    ;;
  --list-tasks)
    printf '%s\n' "${AVAILABLE_TASKS[@]}"
    exit 0
    ;;
  "")
    ;;
  *)
    error "不认识的参数：$1"
    echo "查看帮助：./run_walker_s2_teleop.sh --help" >&2
    exit 1
    ;;
esac

if [[ -z "${HF_TOKEN:-}" ]] && [[ -f "${HF_TOKEN_FILE}" ]]; then
  HF_TOKEN="$(<"${HF_TOKEN_FILE}")"
  export HF_TOKEN
  info "已从 ${HF_TOKEN_FILE} 读取 HF_TOKEN。"
fi

validate_task "${TASK}"

interactive_prompt

if ! command -v docker >/dev/null 2>&1; then
  error "宿主机上找不到 docker 命令。请先安装 Docker，或确认当前终端能运行 docker。"
  exit 1
fi

if ! docker ps -a --format '{{.Names}}' | grep -Fxq "${CONTAINER_NAME}"; then
  error "容器 '${CONTAINER_NAME}' 不存在。"
  echo "处理建议：" >&2
  echo "  1. 先运行 ./run.sh 创建/启动默认容器。" >&2
  echo "  2. 如果容器名不同，使用：CONTAINER_NAME=真实容器名 ./run_walker_s2_teleop.sh" >&2
  echo "  3. 查看已有容器：docker ps -a" >&2
  exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -Fxq "${CONTAINER_NAME}"; then
  info "容器 '${CONTAINER_NAME}' 当前未运行，正在启动..."
  docker start "${CONTAINER_NAME}" >/dev/null
else
  info "容器 '${CONTAINER_NAME}' 已在运行。"
fi

if [[ -z "${HF_TOKEN:-}" && -z "${HUGGINGFACE_HUB_TOKEN:-}" ]]; then
  warn "未检测到 HF_TOKEN。如果只在本地保存数据通常没关系；如需访问 Hugging Face，请设置 HF_TOKEN 或写入 ${HF_TOKEN_FILE}。"
fi

TTY_FLAG="-i"
if [[ -t 0 && -t 1 ]]; then
  TTY_FLAG="-it"
fi

EXEC_ENV_ARGS=()
for proxy_var in \
  http_proxy https_proxy all_proxy no_proxy \
  HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY \
  HF_TOKEN HUGGINGFACE_HUB_TOKEN HF_HOME; do
  proxy_val="${!proxy_var-}"
  if [[ -n "${proxy_val}" ]]; then
    EXEC_ENV_ARGS+=(-e "${proxy_var}=${proxy_val}")
  fi
done

print_beginner_guide
info "即将进入容器并启动遥操作程序，请保持这个终端窗口打开。"

CONTAINER_CMD=(
  /isaac-sim/python.sh
  lerobot/scripts/teleop_and_record.py
  --robot.type=walker_s2_sim
  --control.type=teleoperate
  "--control.task=${TASK}"
  "--control.fps=${FPS}"
  "--control.display_cameras=${DISPLAY_CAMERAS}"
  "--control.teleop_time_s=${TELEOP_TIME_S}"
  "--dataset.mode=${DATASET_MODE}"
  "--repo_id=${HF_REPO_ID}"
  "--save_path=${SAVE_PATH}"
  "--vcodec=${VCODEC}"
)
printf -v CONTAINER_CMD_STR '%q ' "${CONTAINER_CMD[@]}"

docker exec ${TTY_FLAG} "${EXEC_ENV_ARGS[@]}" -w "${CONTAINER_WORKDIR}" "${CONTAINER_NAME}" \
  bash -lc "${CONTAINER_CMD_STR}"

# Available values for --control.task (4 total):
# 1) Part_Sorting
# 2) Conveyor_Sorting
# 3) Foam_Inlaying
# 4) Packing_Box
