#!/usr/bin/env bash
set -euo pipefail

export TASK_NUMBER="${TASK_NUMBER:-task2}"
export TASK="${TASK:-Conveyor_Sorting}"
export TASK_LABEL="${TASK_LABEL:-Task 2 Conveyor_Sorting}"
export REPO_ID="${REPO_ID:-local/task2_conveyor_sorting}"
export OBJECTS_PER_EPISODE="${OBJECTS_PER_EPISODE:-2}"
export SINGLE_TASK="${SINGLE_TASK:-Conveyor_Sorting}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/auto_collect_common.sh" "$@"
