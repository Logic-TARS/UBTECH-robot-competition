#!/usr/bin/env bash
set -euo pipefail

export TASK_NUMBER="${TASK_NUMBER:-task4}"
export TASK="${TASK:-Packing_Box}"
export TASK_LABEL="${TASK_LABEL:-Task 4 Packing_Box}"
export REPO_ID="${REPO_ID:-local/task4_packing_box}"
export OBJECTS_PER_EPISODE="${OBJECTS_PER_EPISODE:-1}"
export SINGLE_TASK="${SINGLE_TASK:-Packing_Box}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/auto_collect_common.sh" "$@"
