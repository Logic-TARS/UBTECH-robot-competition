#!/usr/bin/env bash
# Wrapper to run eval_smolvla.py with correct PYTHONPATH inside Docker.
# Usage: ./scripts/run_eval_smolvla.sh [args for eval_smolvla.py]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"
PYTHONPATH="$REPO_DIR/src" /isaac-sim/python.sh "$REPO_DIR/src/lerobot/scripts/eval_smolvla.py" "$@"
