#!/usr/bin/env python
"""Standalone evaluation for walker_s2_sim policies.

This script evaluates a trained ACT policy on the walker_s2_sim robot
inside Isaac Sim. It bypasses the standard lerobot_eval.py pipeline
(which requires EnvConfig) and uses the robot directly.

Usage (inside Docker container):
    /isaac-sim/python.sh src/lerobot/scripts/eval_walker_s2.py \
        --checkpoint outputs/train/task2_act/checkpoints/100000/pretrained_model \
        --task Conveyor_Sorting \
        --n_episodes 50 \
        --device cuda
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import torch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def load_policy(checkpoint_path: str, device: str = "cuda"):
    """Load pretrained ACT policy from checkpoint using the standard LeRobot loader."""
    from src.lerobot.configs.policies import PreTrainedConfig
    from src.lerobot.configs.types import FeatureType, PolicyFeature
    from src.lerobot.policies.act.modeling_act import ACTPolicy

    ckpt_dir = Path(checkpoint_path)

    logger.info(f"Loading policy from {ckpt_dir}")
    config = PreTrainedConfig.from_pretrained(ckpt_dir)
    config.pretrained_path = ckpt_dir

    # Fix: from_pretrained may leave input_features as raw dicts.
    # Convert them to PolicyFeature objects if needed.
    if config.input_features:
        fixed = {}
        for key, val in config.input_features.items():
            if isinstance(val, dict):
                ft_type = FeatureType(val.get("type", "STATE"))
                shape = tuple(val.get("shape", []))
                fixed[key] = PolicyFeature(type=ft_type, shape=shape)
            else:
                fixed[key] = val
        config.input_features = fixed
    if config.output_features:
        fixed = {}
        for key, val in config.output_features.items():
            if isinstance(val, dict):
                ft_type = FeatureType(val.get("type", "ACTION"))
                shape = tuple(val.get("shape", []))
                fixed[key] = PolicyFeature(type=ft_type, shape=shape)
            else:
                fixed[key] = val
        config.output_features = fixed

    policy = ACTPolicy(config)
    model_path = ckpt_dir / "model.safetensors"
    from safetensors.torch import load_file
    policy.load_state_dict(load_file(str(model_path), device=str(device)))
    policy.to(device)
    policy.eval()
    logger.info(f"Policy loaded: {sum(p.numel() for p in policy.parameters())} params on {device}")
    return policy


def build_observation_dict(robot, obs_state: np.ndarray, cameras: dict):
    """Build observation dict matching LeRobot policy input format."""
    obs = {
        "observation.state": torch.tensor(obs_state, dtype=torch.float32).unsqueeze(0),
    }
    for cam_name, img in cameras.items():
        # Convert (H, W, 3) uint8 -> (1, 3, H, W) float32 normalized
        img_tensor = torch.tensor(img, dtype=torch.float32).permute(2, 0, 1).unsqueeze(0) / 255.0
        # ImageNet normalization
        mean = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
        std = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
        img_tensor = (img_tensor - mean) / std
        obs[f"observation.images.{cam_name}"] = img_tensor
    return obs


def reset_episode(robot, task_name: str):
    try:
        robot.reset()
        logger.info(f"Episode reset for {task_name}")
        return True
    except Exception as e:
        logger.error(f"Reset failed: {e}")
        return False


def check_task_success(robot, task_name: str) -> bool:
    """Check if the task was completed successfully.

    For Conveyor_Sorting: checks if all parts are in the correct bins.
    This uses the task-specific YAML config's success criteria.
    """
    try:
        if robot._scene_builder is not None:
            success = robot._scene_builder.check_success()
            return success
    except Exception:
        pass
    return False


def evaluate_policy(checkpoint_path: str, task_name: str, n_episodes: int = 50,
                    device: str = "cuda", max_steps_per_episode: int = 500,
                    output_dir: str = None):
    """Run evaluation: create robot, load policy, run episodes, compute metrics."""
    logger.info(f"=== Evaluation: {task_name} ===")
    logger.info(f"Checkpoint: {checkpoint_path}")
    logger.info(f"Episodes: {n_episodes}, Max steps: {max_steps_per_episode}")

    # 1. Load policy
    policy = load_policy(checkpoint_path, device)

    # 2. Create robot and connect to Isaac Sim
    from src.lerobot.robots import make_robot_from_config
    from src.lerobot.robots.walker_s2_sim.walkers2simConfig import WalkerS2Config

    robot_config = WalkerS2Config(headless=True)
    robot_config.load_from_yaml(task_name)
    robot = make_robot_from_config(robot_config)
    robot.connect()

    logger.info(f"Robot connected. Running {n_episodes} episodes...")

    # 3. Run evaluation episodes
    successes = []
    rewards = []
    for ep in range(n_episodes):
        logger.info(f"--- Episode {ep+1}/{n_episodes} ---")

        # Reset
        if not reset_episode(robot, task_name):
            logger.warning(f"Reset failed for episode {ep+1}, skipping")
            successes.append(0.0)
            rewards.append(0.0)
            continue

        # Wait for scene to stabilize
        for _ in range(50):
            robot.step(render=False)

        ep_reward = 0.0
        ep_success = False

        for step in range(max_steps_per_episode):
            # Get observation
            obs_state_dict = robot.get_observation()
            if obs_state_dict is None:
                logger.warning(f"Got None observation at step {step}")
                break

            # Build state vector (20D: 14 arm + 4 finger + 2 gripper)
            state_parts = []
            if "arm_positions" in obs_state_dict:
                state_parts.extend(obs_state_dict["arm_positions"])
            if "finger_positions" in obs_state_dict:
                state_parts.extend(obs_state_dict["finger_positions"])
            # Gripper commands
            state_parts.append(-1.0 if robot._right_gripping else 1.0)
            state_parts.append(-1.0 if robot._left_gripping else 1.0)

            obs_state = np.array(state_parts, dtype=np.float32)[:20]

            # Get camera images
            cameras = {}
            for cam_name in ["head_left", "head_right", "wrist_left", "wrist_right"]:
                img = robot.get_camera_image(cam_name)
                if img is not None:
                    cameras[cam_name] = img

            if len(cameras) < 4:
                logger.warning(f"Only got {len(cameras)} cameras at step {step}")
                break

            # Build observation and run policy
            obs_dict = build_observation_dict(robot, obs_state, cameras)
            with torch.no_grad():
                action = policy.select_action(obs_dict)

            action_np = action.squeeze(0).cpu().numpy()  # (20,)

            # Apply action: set arm positions, finger positions, gripper
            robot._hold_arm_positions = action_np[:14].astype(np.float32)
            robot._hold_finger_positions = action_np[14:18].astype(np.float32)
            robot._right_gripping = action_np[18] < 0
            robot._left_gripping = action_np[19] < 0

            # Step simulation
            robot.step(render=False)

            # Check success
            if step == max_steps_per_episode - 1:
                ep_success = check_task_success(robot, task_name)

        successes.append(1.0 if ep_success else 0.0)
        rewards.append(ep_reward)
        logger.info(f"Episode {ep+1}: success={ep_success}, reward={ep_reward:.3f}")

    # 4. Compute metrics
    pc_success = np.mean(successes) * 100.0
    avg_reward = np.mean(rewards)

    results = {
        "per_episode": [
            {"episode_ix": i, "success": bool(s), "reward": float(r)}
            for i, (s, r) in enumerate(zip(successes, rewards))
        ],
        "aggregated": {
            "pc_success": float(pc_success),
            "avg_reward": float(avg_reward),
            "n_episodes": n_episodes,
            "task": task_name,
            "checkpoint": checkpoint_path,
        }
    }

    logger.info(f"\n{'='*50}")
    logger.info(f"EVALUATION RESULTS: {task_name}")
    logger.info(f"  pc_success: {pc_success:.1f}%")
    logger.info(f"  avg_reward: {avg_reward:.3f}")
    logger.info(f"  n_episodes: {n_episodes}")
    logger.info(f"{'='*50}")

    # Save results
    if output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        results_file = out_path / "eval_results.json"
        with open(results_file, "w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"Results saved to {results_file}")

    # Cleanup
    robot.disconnect()

    return results


def main():
    parser = argparse.ArgumentParser(description="Evaluate walker_s2_sim policy")
    parser.add_argument("--checkpoint", type=str, required=True,
                        help="Path to pretrained model checkpoint")
    parser.add_argument("--task", type=str, default="Conveyor_Sorting",
                        choices=["Part_Sorting", "Conveyor_Sorting", "Foam_Inlaying", "Packing_Box"],
                        help="Task name")
    parser.add_argument("--n_episodes", type=int, default=50,
                        help="Number of evaluation episodes")
    parser.add_argument("--device", type=str, default="cuda",
                        help="Device for inference")
    parser.add_argument("--max_steps", type=int, default=500,
                        help="Max steps per episode")
    parser.add_argument("--output_dir", type=str, default=None,
                        help="Output directory for results")
    args = parser.parse_args()

    results = evaluate_policy(
        checkpoint_path=args.checkpoint,
        task_name=args.task,
        n_episodes=args.n_episodes,
        device=args.device,
        max_steps_per_episode=args.max_steps,
        output_dir=args.output_dir,
    )

    # Print summary for shell
    pc = results["aggregated"]["pc_success"]
    print(f"\nSUMMARY: {args.task} - pc_success={pc:.1f}% ({'PASS' if pc >= 75.0 else 'FAIL'} >= 75%)")


if __name__ == "__main__":
    main()
