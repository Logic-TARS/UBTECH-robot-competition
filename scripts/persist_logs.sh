#!/usr/bin/env bash
# =============================================================================
#  persist_logs.sh — Snapshot training/output logs into git for durability
#
#  Intended to be run as a durable cron job.  Archives current log/data status
#  so progress is not lost across container rebuilds or working directory resets.
# =============================================================================
set -euo pipefail

REPO_DIR="/home/1ctnltug/UBTECH"
SNAPSHOT_DIR="${REPO_DIR}/.log_snapshots"

mkdir -p "${SNAPSHOT_DIR}"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SNAPSHOT_FILE="${SNAPSHOT_DIR}/status_${TIMESTAMP}.json"

cd "${REPO_DIR}"

# ---- Collect status summary ----
STATUS=$(python3 -c "
import json, os, glob

report = {
    'timestamp': '${TIMESTAMP}',
    'datasets': {},
    'models': [],
    'training_logs': {},
}

# Dataset info
for task in ['Part_Sorting', 'Conveyor_Sorting', 'Foam_Inlaying', 'Packing_Box']:
    task_dirs = sorted(glob.glob(f'datasets/{task}/batch1_*'))
    total_episodes = 0
    total_frames = 0
    batches = []
    for d in task_dirs:
        info_path = os.path.join(d, 'meta', 'info.json')
        if os.path.exists(info_path):
            data = json.load(open(info_path))
            ep = data.get('total_episodes', 0)
            fr = data.get('total_frames', 0)
            total_episodes += ep
            total_frames += fr
            batches.append({'dir': os.path.basename(d), 'episodes': ep, 'frames': fr})
    # Also check batch1/
    info_path = f'datasets/{task}/batch1/meta/info.json'
    if os.path.exists(info_path):
        data = json.load(open(info_path))
        ep = data.get('total_episodes', 0)
        fr = data.get('total_frames', 0)
        batches.append({'dir': 'batch1', 'episodes': ep, 'frames': fr})
    report['datasets'][task] = {
        'total_episodes': total_episodes,
        'total_frames': total_frames,
        'batches': batches,
    }

# Model checkpoints
for ckpt in sorted(glob.glob('outputs/train/*/checkpoints/*/pretrained_model/model.safetensors')):
    report['models'].append(ckpt)

# Training log tails
for logf in sorted(glob.glob('outputs/train/*.log')) + sorted(glob.glob('outputs/train/*_log.txt')):
    try:
        with open(logf) as f:
            lines = f.readlines()
            tail = lines[-50:] if len(lines) > 50 else lines
            report['training_logs'][logf] = ''.join(tail)
    except Exception:
        pass

print(json.dumps(report, indent=2, ensure_ascii=False))
")

echo "${STATUS}" > "${SNAPSHOT_FILE}"
echo "[PERSIST] Snapshot saved: ${SNAPSHOT_FILE}"

# ---- Git commit ----
# Only commit if there are meaningful changes
git add "${SNAPSHOT_FILE}" 2>/dev/null || true
if git diff --cached --quiet 2>/dev/null; then
    echo "[PERSIST] No new snapshot to commit."
else
    git commit -m "chore: persist log snapshot ${TIMESTAMP}" >/dev/null 2>&1 || true
    echo "[PERSIST] Committed."
fi
