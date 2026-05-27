#!/usr/bin/env bash
set -euo pipefail

export TASK_NUMBER="${TASK_NUMBER:-task3}"
export TASK="${TASK:-Foam_Inlaying}"
export TASK_LABEL="${TASK_LABEL:-Task 3 Foam_Inlaying}"
export REPO_ID="${REPO_ID:-local/task3_foam_inlaying}"
export OBJECTS_PER_EPISODE="${OBJECTS_PER_EPISODE:-3}"
export SINGLE_TASK="${SINGLE_TASK:-Foam_Inlaying}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/auto_collect_common.sh" "$@"
