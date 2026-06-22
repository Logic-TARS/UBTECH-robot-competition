"""Task 4 - Packing Box: IK-based auto data collection for the box-packing task.

The robot picks up foam pieces from the table and packs them into the box.
Single-arm task using the right arm, similar to Task 1 (Part_Sorting).
"""

import json
import logging
from collections.abc import Callable
from pathlib import Path

import numpy as np

from .auto_collect_base import AutoCollectBase


class TaskPackingBox(AutoCollectBase):
    """IK-based auto data collection for the Packing_Box task.

    Right arm picks up foam pieces and places them into the box.
    """

    _DEFAULT_HOME_RETURN_STEPS = 2

    def __init__(self):
        super().__init__()
        self._current_episode_part_frames: list[dict] = []

    def _get_episode_parts(self, robot) -> list[dict]:
        foam_part = self._get_foam_part(robot)
        if foam_part is not None:
            return [foam_part]
        return []

    def _get_foam_part(self, robot) -> dict | None:
        scene_builder = getattr(robot, "_scene_builder", None)
        if scene_builder is not None:
            cfg = getattr(scene_builder, "cfg", {})
            foam_cfg = cfg.get("foam", {})
            foam_pos = foam_cfg.get("foam_position")
            if foam_pos:
                return {
                    "prim_path": "/foam_piece",
                    "position": list(foam_pos),
                    "orientation": [0.0, 0.0, 0.0, 1.0],
                }
        return None

    def compute_grasp_poses(self, part: dict) -> dict:
        """Compute approach/descend/grasp/lift poses (world coordinates)."""
        target_pos = np.array(part["position"])

        return {
            "right": {
                "approach": {
                    "position": np.array([target_pos[0], target_pos[1], target_pos[2] + 0.25]),
                    "rotation": np.array([-np.pi, 0.0, -1.9]),
                },
                "grasp": {
                    "position": np.array([target_pos[0], target_pos[1], target_pos[2] + 0.01]),
                    "rotation": np.array([-np.pi, -0.6, -1.9]),
                },
                "lift": {
                    "position": np.array([target_pos[0], target_pos[1], target_pos[2] + 0.20]),
                    "rotation": np.array([-np.pi, -0.2, -1.9]),
                },
            },
        }

    def check_grasp_success(self, robot, part: dict, threshold: float = 0.08) -> bool:
        """Check grasp success by gripper-to-part distance."""
        return self._check_grasp_success_for_arm(robot, part, arm_side="right", threshold=threshold)

    def get_place_pose(self, robot, part: dict, box_pos: np.ndarray) -> dict:
        """Return box position as the place target."""
        place_offset = np.array([0.0, 0.0, 0.18])
        return {
            "right": {
                "position": box_pos + place_offset,
                "rotation": np.array([-np.pi, -0.2, -2.8]),
            },
        }

    def _on_episode_start(self, parts: list[dict] | None = None) -> None:
        del parts
        self._current_episode_part_frames = []

    def _on_episode_saved(self, dataset, episode_index: int, episode_length: int) -> None:
        if dataset is None or not self._current_episode_part_frames:
            return

        part_info_path = Path(dataset.root) / "meta" / "part_info.json"
        part_info_path.parent.mkdir(parents=True, exist_ok=True)

        part_info = self._load_part_info(part_info_path)
        episode_info = {
            "episode_index": int(episode_index),
            "episode_frame_length": int(episode_length),
            "parts": list(self._current_episode_part_frames),
        }

        episodes = [
            ep
            for ep in part_info.get("episodes", [])
            if int(ep.get("episode_index", -1)) != int(episode_index)
        ]
        episodes.append(episode_info)
        episodes.sort(key=lambda ep: int(ep.get("episode_index", -1)))
        part_info["episodes"] = episodes

        part_info_path.write_text(
            json.dumps(part_info, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_part_info(self, part_info_path: Path) -> dict:
        if not part_info_path.exists():
            return {"episodes": []}
        try:
            loaded = json.loads(part_info_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"episodes": []}
        if isinstance(loaded, dict) and isinstance(loaded.get("episodes"), list):
            return loaded
        if isinstance(loaded, list):
            return {"episodes": loaded}
        return {"episodes": []}

    def _get_part_frame_start(self, dataset) -> int | None:
        if dataset is None:
            return None
        episode_buffer = getattr(dataset, "episode_buffer", None)
        if not episode_buffer:
            return None
        return int(episode_buffer.get("size", 0))

    def _record_completed_part_frame_range(self, robot, dataset, part, frame_start_index):
        if dataset is None or frame_start_index is None:
            return
        episode_buffer = getattr(dataset, "episode_buffer", None)
        if not episode_buffer:
            return
        frame_end = int(episode_buffer.get("size", 0)) - 1
        if frame_end < frame_start_index:
            return
        scene_builder = getattr(robot, "_scene_builder", None)
        self._current_episode_part_frames.append({
            "part_name": self._get_part_name(part),
            "part_type": "foam",
            "prim_path": str(part.get("prim_path", "")),
            "frame_start_index": int(frame_start_index),
            "frame_end_index": int(frame_end),
        })

    def _get_part_name(self, part: dict) -> str:
        for key in ("name", "part_name"):
            value = part.get(key)
            if value:
                return str(value)
        prim_path = str(part.get("prim_path", ""))
        if prim_path:
            return prim_path.rstrip("/").split("/")[-1]
        return str(part.get("index", "unknown"))

    def _run_grasp_stages(
        self,
        robot,
        grasp_poses: dict,
        place_poses: dict,
        dt: float,
        dataset,
        single_task: str,
        check_success_fn: Callable[[], bool],
    ) -> bool:
        """Execute 7-stage grasp-place pipeline (right arm only)."""
        active_arms = [arm for arm in ("right",) if grasp_poses.get(arm)]
        if not active_arms:
            return True

        logging.info("阶段1 [right]: 接近目标...")
        target_poses = {}
        for arm in active_arms:
            p = grasp_poses[arm]["approach"]
            target_poses[arm] = {
                "position": robot._scene_builder.world_to_robot_coords(p["position"]),
                "rotation": p["rotation"],
            }
        self._joint_interpolate_to_pose(robot, target_poses, dt, 0.8, dataset, single_task)

        if (
            not robot._right_gripping
            and abs(robot._hold_finger_positions[2:4].mean() - robot._robot_interface.gripper_open_width)
            < 0.005
        ):
            logging.info("阶段2 [right]: 夹爪已打开，跳过...")
        else:
            logging.info("阶段2 [right]: 松开夹爪...")
            self.move_gripper(
                robot, {"right": -1.0}, dt, 0.3, dataset=dataset, single_task=single_task,
            )

        logging.info("阶段3 [right]: 抓取...")
        target_poses = {}
        for arm in active_arms:
            p = grasp_poses[arm]["grasp"]
            target_poses[arm] = {
                "position": robot._scene_builder.world_to_robot_coords(p["position"]),
                "rotation": p["rotation"],
            }
        self._joint_interpolate_to_pose(robot, target_poses, dt, 0.8, dataset, single_task)

        logging.info("阶段3b [right]: 闭合夹爪...")
        self.move_gripper(
            robot, {"right": 1.0}, dt, 0.5, dataset=dataset, single_task=single_task,
        )

        logging.info("阶段4 [right]: 抬起手臂...")
        target_poses = {}
        for arm in active_arms:
            p = grasp_poses[arm]["lift"]
            target_poses[arm] = {
                "position": robot._scene_builder.world_to_robot_coords(p["position"]),
                "rotation": p["rotation"],
            }
        self._joint_interpolate_to_pose(robot, target_poses, dt, 0.8, dataset, single_task)

        logging.info("阶段5 [right]: 移动到放置位置...")
        target_poses = {}
        for arm in active_arms:
            pp = place_poses.get(arm)
            if pp is not None:
                target_poses[arm] = {
                    "position": robot._scene_builder.world_to_robot_coords(pp["position"]),
                    "rotation": pp["rotation"],
                }
        self._joint_interpolate_to_pose(robot, target_poses, dt, 1.1, dataset, single_task)

        logging.info("阶段6: 检测抓取是否成功...")
        success = check_success_fn()
        if not success:
            logging.error("抓取失败！")
            return False

        logging.info("阶段7 [right]: 松开夹爪...")
        self.move_gripper(
            robot, {"right": -1.0}, dt, 0.3, dataset=dataset, single_task=single_task,
        )

        return True

    def _execute_sequence(
        self,
        robot,
        parts: list[dict],
        box_pos: np.ndarray,
        dt: float,
        dataset,
        single_task: str,
        objects_per_episode: int,
    ) -> bool:
        """Single-arm episode: process parts one by one."""
        if not parts:
            logging.error("无可处理零件")
            return False
        completed = 0
        for part_idx, part in enumerate(parts):
            parts = robot._scene_builder.get_parts_world_poses()
            if part_idx >= len(parts):
                break
            part = parts[part_idx]
            logging.info(f"\n处理零件 {part_idx + 1}/{len(parts)}")
            grasp_poses = self.compute_grasp_poses(part)
            if not grasp_poses:
                continue
            place_poses = self.get_place_pose(robot, part, box_pos)
            part_frame_start = self._get_part_frame_start(dataset)
            success = self._run_grasp_stages(
                robot=robot,
                grasp_poses=grasp_poses,
                place_poses=place_poses,
                dt=dt,
                dataset=dataset,
                single_task=single_task,
                check_success_fn=lambda current_part=part: self.check_grasp_success(robot, current_part),
            )
            if not success:
                return False
            self._record_completed_part_frame_range(
                robot=robot, dataset=dataset, part=part, frame_start_index=part_frame_start,
            )
            completed += 1
            logging.info(f"零件 {part_idx + 1} 处理完成")
            if objects_per_episode > 0 and completed >= objects_per_episode:
                logging.info(f"已达到本 episode 目标物体数 ({objects_per_episode})")
                break
        return True
