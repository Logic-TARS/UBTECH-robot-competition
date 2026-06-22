#!/usr/bin/env bash
set -euo pipefail

export TASK_NUMBER="${TASK_NUMBER:-task1}"
export TASK="${TASK:-Part_Sorting}"
export TASK_LABEL="${TASK_LABEL:-Task 1 Part_Sorting}"
export REPO_ID="${REPO_ID:-local/task1_part_sorting}"
export OBJECTS_PER_EPISODE="${OBJECTS_PER_EPISODE:-2}"
export SINGLE_TASK="${SINGLE_TASK:-Part_Sorting}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/auto_collect_common.sh" "$@"
