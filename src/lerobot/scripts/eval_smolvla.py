#!/usr/bin/env python
"""Evaluate a trained SmolVLA policy on walker_s2_sim inside Isaac Sim.

Usage (inside Docker container):
    /isaac-sim/python.sh src/lerobot/scripts/eval_smolvla.py \\
        --checkpoint outputs/train/task1_smolvla/checkpoints/195000/pretrained_model \\
        --task Part_Sorting \\
        --n_episodes 50

    # With video recording (all episodes + custom camera):
    /isaac-sim/python.sh src/lerobot/scripts/eval_smolvla.py \\
        --checkpoint outputs/train/task1_smolvla/checkpoints/195000/pretrained_model \\
        --task Part_Sorting --n_episodes 10 --record --record_camera head_left

Output is saved to:
    outputs/eval/{task}/{train_name}/step_{step}/
        episode_{n}_{camera}.mp4   (if --record)
        eval_results.json
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Ensure src is importable when running from repo root
_repo_root = str(Path(__file__).resolve().parent.parent.parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Task description strings (must match training dataset meta/tasks.jsonlb format)
TASK_DESCRIPTIONS = {
    "Part_Sorting": "Pick and place parts correctly for the Part_Sorting task.",
    "Conveyor_Sorting": "Pick and place items correctly for the Conveyor_Sorting task.",
    "Foam_Inlaying": "Insert foam pieces correctly for the Foam_Inlaying task.",
    "Packing_Box": "Pack items into boxes correctly for the Packing_Box task.",
}


def load_policy_and_processors(checkpoint_path: str, device: str = "cuda"):
    """Load SmolVLA policy, preprocessor and postprocessor from a checkpoint directory."""
    import json
    import tempfile
    import torch
    import src.lerobot.policies  # registers smolvla config subclass
    from src.lerobot.policies.smolvla.configuration_smolvla import SmolVLAConfig
    from src.lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy
    from src.lerobot.processor import PolicyProcessorPipeline
    from safetensors.torch import load_file

    ckpt_dir = Path(checkpoint_path).resolve()
    if not ckpt_dir.is_dir():
        raise FileNotFoundError(f"Checkpoint directory not found: {ckpt_dir}")
    logger.info(f"Loading smolvla policy from {ckpt_dir}")

    config_path = ckpt_dir / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"config.json not found in {ckpt_dir}")
    with open(config_path) as f:
        config_dict = json.load(f)
    config_dict.pop("type", None)  # remove type if present; not a field on SmolVLAConfig
    import draccus
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
        json.dump(config_dict, tf)
        tmp_path = tf.name
    try:
        with draccus.config_type("json"):
            config = draccus.parse(SmolVLAConfig, tmp_path, args=[])
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    config.pretrained_path = ckpt_dir
    config.device = device

    policy = SmolVLAPolicy(config)
    model_path = ckpt_dir / "model.safetensors"
    state_dict = load_file(str(model_path), device=str(device))
    policy.load_state_dict(state_dict)
    policy.to(device)
    policy.eval()
    n_params = sum(p.numel() for p in policy.parameters())
    logger.info(f"Policy loaded: {n_params:,} params on {device}")

    # Load processor pipelines from checkpoint
    preprocessor = None
    postprocessor = None
    preprocessor_path = ckpt_dir / "policy_preprocessor.json"
    postprocessor_path = ckpt_dir / "policy_postprocessor.json"
    if preprocessor_path.exists() and postprocessor_path.exists():
        logger.info("Loading preprocessor / postprocessor from checkpoint")
        preprocessor = PolicyProcessorPipeline.from_pretrained(
            pretrained_model_name_or_path=ckpt_dir,
            config_filename="policy_preprocessor.json",
            overrides={"device_processor": {"device": device}},
        )
        postprocessor = PolicyProcessorPipeline.from_pretrained(
            pretrained_model_name_or_path=ckpt_dir,
            config_filename="policy_postprocessor.json",
        )
        logger.info("Processors loaded")
    else:
        logger.warning(
            "policy_preprocessor.json / policy_postprocessor.json not found in checkpoint "
            "— running without normalization (actions may be incorrectly scaled)"
        )

    return policy, preprocessor, postprocessor, config


def build_raw_observation(robot_state: "np.ndarray", cameras: dict, task: str,
                          env_state: "np.ndarray | None" = None) -> dict:
    """Build a raw observation dict ready for the preprocessor pipeline.

    The preprocessor handles slicing, normalization, tokenization, device transfer.
    Keys match what the training preprocessor expects:
        observation.state, observation.images.<cam>, task, observation.environment_state
    """
    import numpy as np
    import torch

    obs = {
        "observation.state": torch.from_numpy(robot_state).float(),
        "task": TASK_DESCRIPTIONS.get(task, TASK_DESCRIPTIONS["Part_Sorting"]),
    }
    if env_state is not None:
        obs["observation.environment_state"] = torch.from_numpy(env_state).float()

    for cam_name, img in cameras.items():
        if isinstance(img, np.ndarray):
            obs[f"observation.images.{cam_name}"] = torch.from_numpy(img).float().permute(2, 0, 1) / 255.0
        elif isinstance(img, torch.Tensor):
            if img.ndim == 3:
                obs[f"observation.images.{cam_name}"] = img.permute(2, 0, 1).float()
            else:
                obs[f"observation.images.{cam_name}"] = img.float()
    return obs


def build_robot_state(obs_sd: dict) -> "np.ndarray":
    """Extract 20D robot state from the flat observation dict returned by WalkerS2Sim."""
    import numpy as np
    import torch

    arm_joint_names = [
        "L_shoulder_pitch_joint", "L_shoulder_roll_joint", "L_shoulder_yaw_joint",
        "L_elbow_roll_joint", "L_elbow_yaw_joint", "L_wrist_pitch_joint", "L_wrist_roll_joint",
        "R_shoulder_pitch_joint", "R_shoulder_roll_joint", "R_shoulder_yaw_joint",
        "R_elbow_roll_joint", "R_elbow_yaw_joint", "R_wrist_pitch_joint", "R_wrist_roll_joint",
    ]
    finger_joint_names = ["L_finger1_joint", "L_finger2_joint", "R_finger1_joint", "R_finger2_joint"]
    state_parts = []
    for jn in arm_joint_names:
        key = f"{jn}.pos"
        val = obs_sd.get(key, 0.0)
        state_parts.append(val.cpu().numpy() if hasattr(val, "cpu") else float(val))
    for jn in finger_joint_names:
        key = f"{jn}.pos"
        val = obs_sd.get(key, 0.0)
        state_parts.append(val.cpu().numpy() if hasattr(val, "cpu") else float(val))
    state_parts.append(obs_sd.get("left_gripper", torch.tensor(1.0)).cpu().numpy() if hasattr(obs_sd.get("left_gripper", 1.0), "cpu") else float(obs_sd.get("left_gripper", 1.0)))
    state_parts.append(obs_sd.get("right_gripper", torch.tensor(1.0)).cpu().numpy() if hasattr(obs_sd.get("right_gripper", 1.0), "cpu") else float(obs_sd.get("right_gripper", 1.0)))
    return np.array(state_parts, dtype=np.float32)[:20]


def build_env_state(obs_sd: dict, num_objects: int = 4) -> "np.ndarray":
    """Extract N*7 env state from the flat observation dict."""
    import numpy as np

    env_state_parts = []
    for i in range(1, num_objects + 1):
        for suffix in ("x", "y", "z", "qx", "qy", "qz", "qw"):
            key = f"object_{i}_{suffix}"
            val = obs_sd.get(key, 0.0)
            env_state_parts.append(val.cpu().numpy() if hasattr(val, "cpu") else float(val))
    return np.array(env_state_parts, dtype=np.float32)


def apply_action_to_robot(robot, action_np: "np.ndarray"):
    """Write a 20D action to the robot's control targets."""
    import numpy as np
    robot._hold_arm_positions = action_np[:14].astype(np.float32)
    robot._hold_finger_positions = action_np[14:18].astype(np.float32)
    robot._right_gripping = bool(action_np[18] < 0)
    robot._left_gripping = bool(action_np[19] < 0)


def main():
    parser = argparse.ArgumentParser(description="Evaluate smolvla on walker_s2_sim")
    parser.add_argument("--checkpoint", type=str, required=True)
    parser.add_argument("--task", type=str, default="Part_Sorting",
                        choices=["Part_Sorting", "Conveyor_Sorting", "Foam_Inlaying", "Packing_Box"])
    parser.add_argument("--n_episodes", type=int, default=50)
    parser.add_argument("--device", type=str, default="cuda")
    parser.add_argument("--max_steps", type=int, default=500)
    parser.add_argument("--output_dir", type=str, default=None,
                        help="Output directory for videos and results. Auto-derived from --checkpoint and "
                             "--task if not set: outputs/eval/{task}/{train_name}/step_{step}/")
    parser.add_argument("--record", action="store_true",
                        help="Record all episode camera frames as MP4 videos")
    parser.add_argument("--record_camera", type=str, default="head_right",
                        help="Camera to record (default: head_right)")
    args = parser.parse_args()

    # 1. Create robot and connect FIRST (starts SimulationApp)
    from src.lerobot.robots import make_robot_from_config
    from src.lerobot.robots.walker_s2_sim.walkers2simConfig import WalkerS2Config

    robot_config = WalkerS2Config(headless=True)
    robot_config.load_from_yaml(args.task)
    robot = make_robot_from_config(robot_config)
    robot.connect()
    logger.info(f"Robot connected. Running {args.n_episodes} episodes...")

    # 2. Load policy + processors AFTER SimulationApp is running
    policy, preprocessor, postprocessor, config = load_policy_and_processors(args.checkpoint, args.device)
    use_env_state = getattr(config, "use_environment_state", False)
    has_processors = preprocessor is not None and postprocessor is not None

    # 3. Run episodes
    import numpy as np
    import torch

    # Derive output directory: use explicit arg, else parse from checkpoint path
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        ckpt_path = Path(args.checkpoint).resolve()
        # ckpt: outputs/train/<train_name>/checkpoints/<step>/pretrained_model
        step_dir = ckpt_path.parent  # e.g. 195000/
        train_name = step_dir.parent.parent.name  # e.g. task1_smolvla
        step = step_dir.name  # e.g. 195000
        output_dir = Path("outputs/eval") / args.task / train_name / f"step_{step}"
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Output dir: {output_dir}")

    # Setup recording if requested
    video_writer = None
    if args.record:
        import cv2

    successes = []
    for ep in range(args.n_episodes):
        logger.info(f"--- Episode {ep+1}/{args.n_episodes} ---")
        if args.record:
            rec_path = str(output_dir / f"episode_{ep}_{args.record_camera}.mp4")
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            video_writer = cv2.VideoWriter(rec_path, fourcc, 20.0, (640, 480))
            logger.info(f"Recording to {rec_path}")
        try:
            robot.reset()
        except Exception as e:
            logger.warning(f"Reset failed: {e}")
            successes.append(0.0)
            continue

        # Settle physics
        for _ in range(50):
            robot.step(render=False)

        ep_success = False
        for step in range(args.max_steps):
            obs_sd = robot.get_observation()
            if obs_sd is None:
                break

            robot_state = build_robot_state(obs_sd)
            env_state = build_env_state(obs_sd) if use_env_state else None

            camera_keys = [k for k in obs_sd if k in robot.CAMERA_NAMES]
            if len(camera_keys) < 4:
                logger.warning(f"Only {len(camera_keys)} cameras at step {step}")
                break

            obs_dict = build_raw_observation(robot_state, {k: obs_sd[k] for k in camera_keys},
                                             args.task, env_state=env_state)

            # Record frame
            if video_writer is not None and args.record_camera in obs_sd:
                img = obs_sd[args.record_camera]
                if isinstance(img, np.ndarray):
                    frame_bgr = img[..., ::-1].copy()  # RGB -> BGR for cv2
                else:
                    frame_bgr = (img.cpu().numpy()[..., ::-1] * 255).astype(np.uint8)
                video_writer.write(frame_bgr)

            if has_processors:
                obs_dict = preprocessor(obs_dict)

            with torch.no_grad():
                action = policy.select_action(obs_dict)

            if has_processors:
                # postprocessor expects a dict, e.g. {"action": tensor}
                action = postprocessor({"action": action})["action"]

            action_np = action.squeeze(0).cpu().numpy()
            apply_action_to_robot(robot, action_np)
            robot.step(render=False)

            if step == args.max_steps - 1:
                try:
                    ep_success = robot._scene_builder.check_success()
                except AttributeError:
                    logger.error("check_success() missing from SceneBuilder — eval will always return 0%")
                except Exception as e:
                    logger.warning(f"check_success() failed: {type(e).__name__}: {e}")

        successes.append(1.0 if ep_success else 0.0)
        logger.info(f"Episode {ep+1}: success={ep_success}")
        if video_writer is not None:
            video_writer.release()
            logger.info(f"Video saved: {rec_path}")
            video_writer = None

    # 4. Results
    pc_success = np.mean(successes) * 100.0
    results = {
        "aggregated": {"pc_success": float(pc_success), "n_episodes": args.n_episodes,
                       "task": args.task, "checkpoint": args.checkpoint},
        "per_episode": [{"episode_ix": i, "success": bool(s)} for i, s in enumerate(successes)],
    }

    logger.info(f"\n{'='*50}")
    logger.info(f"RESULTS: {args.task} - pc_success={pc_success:.1f}% "
                f"({'PASS' if pc_success >= 75 else 'FAIL'} >= 75%)")
    logger.info(f"{'='*50}")

    with open(output_dir / "eval_results.json", "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Results saved to {output_dir / 'eval_results.json'}")

    robot.disconnect()
    print(f"\nSUMMARY: {args.task} - pc_success={pc_success:.1f}% "
          f"({'PASS' if pc_success >= 75 else 'FAIL'} >= 75%)")
    os._exit(0)


def _main():
    """Wrapper that ensures os._exit even on exception."""
    try:
        main()
    except Exception as e:
        logger.exception(f"Eval failed: {e}")
        os._exit(1)
    else:
        os._exit(0)


if __name__ == "__main__":
    _main()
