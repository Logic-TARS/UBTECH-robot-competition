#!/bin/bash
# SmolVLA v2 formal training — 200k steps with pretrained VLM, frozen vision, expert-only training
set -euo pipefail

cd /workspace/GlobalHumanoidRobotChallenge2026_Baseline

echo "=== SmolVLA v2 Training Start: $(date) ==="
echo "Output dir: outputs/train/task1_smolvla_v2"
echo "Steps: 200000 | Batch: 4 | Save freq: 10000"

/isaac-sim/python.sh src/lerobot/scripts/lerobot_train.py \
    --policy.type=smolvla \
    --policy.load_vlm_weights=true \
    --policy.freeze_vision_encoder=true \
    --policy.train_expert_only=true \
    --policy.train_state_proj=true \
    --policy.push_to_hub=false \
    --policy.repo_id=none \
    --dataset.repo_id=local/task1 \
    --dataset.root=./datasets/train/task1 \
    --output_dir=outputs/train/task1_smolvla_v2 \
    --steps=200000 \
    --batch_size=4 \
    --save_freq=10000 \
    --log_freq=50 \
    --wandb.enable=false

echo "=== Training End: $(date) ==="
