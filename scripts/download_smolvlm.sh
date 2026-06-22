#!/usr/bin/env bash
set -euo pipefail

REPO_ID="${REPO_ID:-HuggingFaceTB/SmolVLM2-500M-Video-Instruct}"
PROXY_URL="${PROXY_URL:-http://127.0.0.1:7897}"
HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
HF_HUB_CACHE="${HF_HUB_CACHE:-$HF_HOME/hub}"

export REPO_ID
export HTTP_PROXY="$PROXY_URL"
export HTTPS_PROXY="$PROXY_URL"
export ALL_PROXY="$PROXY_URL"
export http_proxy="$PROXY_URL"
export https_proxy="$PROXY_URL"
export all_proxy="$PROXY_URL"
export HF_HOME
export HF_HUB_CACHE

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif [ -x /isaac-sim/python.sh ]; then
    PYTHON_BIN="/isaac-sim/python.sh"
  else
    echo "[ERROR] Cannot find python3 or /isaac-sim/python.sh" >&2
    exit 1
  fi
fi

echo "[INFO] Repo       : $REPO_ID"
echo "[INFO] Proxy      : $PROXY_URL"
echo "[INFO] HF_HOME    : $HF_HOME"
echo "[INFO] Hub cache  : $HF_HUB_CACHE"
echo "[INFO] Python     : $PYTHON_BIN"

echo "[INFO] Checking proxy..."
curl -x "$PROXY_URL" -sSf -o /dev/null https://huggingface.co
echo "[INFO] Proxy OK"

"$PYTHON_BIN" - <<'PY'
import os
from pathlib import Path

from huggingface_hub import snapshot_download

repo_id = os.environ["REPO_ID"]
cache_dir = os.environ["HF_HUB_CACHE"]

path = snapshot_download(
    repo_id=repo_id,
    cache_dir=cache_dir,
    resume_download=True,
    local_files_only=False,
)
print(f"[INFO] Snapshot path: {path}")

weights = []
for pattern in ("*.safetensors", "*.bin"):
    weights.extend(Path(path).rglob(pattern))

if not weights:
    raise SystemExit("[ERROR] Download finished but no *.safetensors or *.bin weights found in snapshot")

print("[INFO] Weight files:")
for p in weights:
    print(f"  {p} ({p.stat().st_size / 1024**3:.2f} GiB)")
PY

echo "[INFO] Done"
