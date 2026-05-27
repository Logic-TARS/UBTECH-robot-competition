import importlib.util
import json
import sys
import types
from pathlib import Path

import numpy as np
import pytest


def load_task_module():
    module_name = "src.lerobot.auto_collect.task_part_sorting"
    for name in [
        module_name,
        "src.lerobot.auto_collect.auto_collect_base",
        "src.lerobot.auto_collect.utils",
    ]:
        sys.modules.pop(name, None)

    base_module = types.ModuleType("src.lerobot.auto_collect.auto_collect_base")
    base_module.AutoCollectBase = object
    sys.modules["src.lerobot.auto_collect.auto_collect_base"] = base_module

    utils_module = types.ModuleType("src.lerobot.auto_collect.utils")
    utils_module.get_part_sorting_part_type = lambda part, scene_builder=None: part.get("type", "part_b")
    sys.modules["src.lerobot.auto_collect.utils"] = utils_module

    path = Path(__file__).resolve().parents[2] / "src/lerobot/auto_collect/task_part_sorting.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "src.lerobot.auto_collect"
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class DummySceneBuilder:
    def __init__(self, parts):
        self.parts = parts

    def get_parts_world_poses(self):
        return self.parts


class DummyRobot:
    def __init__(self, parts):
        self._scene_builder = DummySceneBuilder(parts)


class DummyDataset:
    def __init__(self, root, episode_index=0, size=0):
        self.root = Path(root)
        self.episode_buffer = {"episode_index": episode_index, "size": size}


def test_on_episode_start_clears_part_frame_ranges():
    module = load_task_module()
    task = module.TaskPartSorting()
    task._current_episode_part_frames = [{"frame_start_index": 0, "frame_end_index": 8}]

    task._on_episode_start([])

    assert task._current_episode_part_frames == []


def test_execute_sequence_returns_home_and_skips_part_frame_ranges_by_default(tmp_path):
    module = load_task_module()
    task = module.TaskPartSorting()
    part_a = {
        "prim_path": "/World/Part_A_0",
        "position": [0.71, 0.27, 1.20],
        "type": "part_a",
    }
    part_b = {
        "prim_path": "/World/Part_B_0",
        "position": [0.72, 0.27, 1.20],
        "type": "part_b",
    }
    robot = DummyRobot([part_a, part_b])
    dataset = DummyDataset(tmp_path)
    grasp_lengths = iter([9, 4])

    task._on_episode_start([part_a, part_b])

    def record_grasp_frames(**kwargs):
        kwargs["dataset"].episode_buffer["size"] += next(grasp_lengths)
        return True

    home_sizes = []
    task._run_grasp_stages = record_grasp_frames
    task._return_right_arm_home = lambda **kwargs: home_sizes.append(kwargs["dataset"].episode_buffer["size"])

    success = task._execute_sequence(
        robot=robot,
        parts=[part_a, part_b],
        box_pos=np.array([0.0, 0.0, 0.0], dtype=np.float32),
        dt=0.02,
        dataset=dataset,
        single_task="Part Sorting",
        objects_per_episode=2,
    )

    assert success
    assert home_sizes == [9, 13]
    assert task._current_episode_part_frames == []


def test_execute_sequence_records_part_frame_ranges_when_home_return_disabled(tmp_path):
    module = load_task_module()
    task = module.TaskPartSorting()
    task.return_home_after_part = False
    part_a = {
        "prim_path": "/World/Part_A_0",
        "position": [0.71, 0.27, 1.20],
        "type": "part_a",
    }
    part_b = {
        "prim_path": "/World/Part_B_0",
        "position": [0.72, 0.27, 1.20],
        "type": "part_b",
    }
    robot = DummyRobot([part_a, part_b])
    dataset = DummyDataset(tmp_path)
    grasp_lengths = iter([9, 4])

    task._on_episode_start([part_a, part_b])

    def record_grasp_frames(**kwargs):
        kwargs["dataset"].episode_buffer["size"] += next(grasp_lengths)
        return True

    home_sizes = []
    task._run_grasp_stages = record_grasp_frames
    task._return_right_arm_home = lambda **kwargs: home_sizes.append(kwargs["dataset"].episode_buffer["size"])

    success = task._execute_sequence(
        robot=robot,
        parts=[part_a, part_b],
        box_pos=np.array([0.0, 0.0, 0.0], dtype=np.float32),
        dt=0.02,
        dataset=dataset,
        single_task="Part Sorting",
        objects_per_episode=2,
    )

    assert success
    assert home_sizes == []
    assert [
        (
            entry["part_name"],
            entry["part_type"],
            entry["prim_path"],
            entry["frame_start_index"],
            entry["frame_end_index"],
        )
        for entry in task._current_episode_part_frames
    ] == [
        ("Part_A_0", "part_a", "/World/Part_A_0", 0, 8),
        ("Part_B_0", "part_b", "/World/Part_B_0", 9, 12),
    ]


def test_execute_sequence_errors_when_required_part_frame_range_is_missing(tmp_path):
    module = load_task_module()
    task = module.TaskPartSorting()
    task.return_home_after_part = False
    part = {
        "prim_path": "/World/Part_A_0",
        "position": [0.71, 0.27, 1.20],
        "type": "part_a",
    }
    robot = DummyRobot([part])
    dataset = DummyDataset(tmp_path)
    task._run_grasp_stages = lambda **kwargs: True

    with pytest.raises(RuntimeError, match="frame_start_index"):
        task._execute_sequence(
            robot=robot,
            parts=[part],
            box_pos=np.array([0.0, 0.0, 0.0], dtype=np.float32),
            dt=0.02,
            dataset=dataset,
            single_task="Part Sorting",
            objects_per_episode=1,
        )


def test_on_episode_saved_writes_part_info_json(tmp_path):
    module = load_task_module()
    task = module.TaskPartSorting()
    dataset = DummyDataset(tmp_path)
    task._current_episode_part_frames = [
        {
            "part_name": "Part_A_0",
            "part_type": "part_a",
            "prim_path": "/World/Part_A_0",
            "frame_start_index": 0,
            "frame_end_index": 8,
        },
        {
            "part_name": "Part_B_0",
            "part_type": "part_b",
            "prim_path": "/World/Part_B_0",
            "frame_start_index": 9,
            "frame_end_index": 12,
        },
    ]

    task._on_episode_saved(dataset, episode_index=3, episode_length=13)

    part_info_path = tmp_path / "meta" / "part_info.json"
    assert part_info_path.exists()
    data = json.loads(part_info_path.read_text(encoding="utf-8"))
    assert data["episodes"] == [
        {
            "episode_index": 3,
            "episode_frame_length": 13,
            "parts": task._current_episode_part_frames,
        }
    ]
