# GHRC 2026 Model Training Notes

Source: https://docs.ubtrobot.com/GHRC2026_TechnicalDocuments/docs/4

Page title: 模型训练

The official training page covers these policy families:

- ACT
- Diffusion Policy (DP)
- PI0
- PI05
- SmolVLA

## SmolVLA

The SmolVLA section provides fine-tuning examples for the `lerobot/smolvla_base`
pretrained policy. The official short command uses the Isaac Sim Python runtime:

```bash
/isaac-sim/python.sh src/lerobot/scripts/lerobot_train.py \
  --policy.path=lerobot/smolvla_base \
  --dataset.repo_id=your_org/your_dataset \
  --batch_size=64 \
  --steps=20000 \
  --output_dir=challenge2026_baseline/Part_Sorting/smolvla \
  --job_name=part_sorting_smolvla \
  --policy.device=cuda \
  --wandb.enable=true
```

Replace `your_org/your_dataset` with the real dataset repo ID. The official
page also notes that `challenge2026_baseline/Part_Sorting/smolvla` should be
replaced if you want a different checkpoint output path.

## Local Task1 Command

This repository has a local Task1 LeRobot dataset at:

```bash
datasets/task1
```

Local dataset summary checked on this machine:

- Episodes: 200
- Frames: 539039
- FPS: 20
- Tasks: 100
- Main task family: `Autonomous Part Sorting`

Recommended Task1 SmolVLA command for this workspace:

```bash
/isaac-sim/python.sh src/lerobot/scripts/lerobot_train.py \
  --policy.path=lerobot/smolvla_base \
  --dataset.repo_id=task1 \
  --dataset.root=datasets/task1 \
  --dataset.video_backend=pyav \
  --batch_size=64 \
  --steps=20000 \
  --output_dir=challenge2026_baseline/Part_Sorting/smolvla \
  --job_name=part_sorting_smolvla \
  --policy.device=cuda \
  --wandb.enable=false
```

Use `--wandb.enable=true` only if WandB is configured.

## Detailed SmolVLA Template

The official page also provides a detailed SmolVLA command using
`--policy.type=smolvla` and explicit hyperparameters:

```bash
/isaac-sim/python.sh src/lerobot/scripts/lerobot_train.py \
  --dataset.repo_id=your_org/your_dataset \
  --dataset.root=datasets/Part_Sorting/ \
  --policy.type=smolvla \
  --policy.vlm_model_name=HuggingFaceTB/SmolVLM2-500M-Video-Instruct \
  --policy.load_vlm_weights=true \
  --policy.dtype=float32 \
  --policy.n_obs_steps=1 \
  --policy.chunk_size=50 \
  --policy.n_action_steps=50 \
  --policy.max_state_dim=32 \
  --policy.max_action_dim=32 \
  --policy.num_steps=10 \
  --policy.tokenizer_max_length=48 \
  --policy.image_resolution='[224,224]' \
  --policy.empty_cameras=0 \
  --policy.freeze_vision_encoder=true \
  --policy.train_expert_only=true \
  --policy.train_state_proj=true \
  --policy.gradient_checkpointing=false \
  --policy.compile_model=false \
  --policy.compile_mode=max-autotune \
  --policy.attention_mode=cross_attn \
  --policy.num_vlm_layers=16 \
  --policy.self_attn_every_n_layers=2 \
  --policy.expert_width_multiplier=0.75 \
  --policy.optimizer_lr=1e-4 \
  --policy.optimizer_betas='[0.9,0.95]' \
  --policy.optimizer_eps=1e-8 \
  --policy.optimizer_weight_decay=1e-10 \
  --policy.optimizer_grad_clip_norm=10.0 \
  --policy.scheduler_warmup_steps=1000 \
  --policy.scheduler_decay_steps=30000 \
  --policy.scheduler_decay_lr=2.5e-6 \
  --policy.min_period=0.004 \
  --policy.max_period=4.0 \
  --output_dir=challenge2026_baseline/Part_Sorting/smolvla \
  --job_name=part_sorting_smolvla \
  --resume=false \
  --seed=1000 \
  --num_workers=8 \
  --batch_size=8 \
  --steps=100000 \
  --eval_freq=0 \
  --log_freq=200 \
  --save_checkpoint=true \
  --save_freq=5000 \
  --wandb.entity=your_wandb_entity
```

For local Task1, change the dataset arguments to:

```bash
--dataset.repo_id=task1
--dataset.root=datasets/task1
```

Remove `--wandb.entity=your_wandb_entity` or set `--wandb.enable=false` if WandB
is not being used.
