import importlib.util
import json
import sys
import types
from pathlib import Path

import numpy as np


def load_task_module():
    module_name = "src.lerobot.auto_collect.task_foam_inlaying"
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
    utils_module.get_foam_inlaying_part_type = lambda part, scene_builder=None: part.get("type", "part_b")
    sys.modules["src.lerobot.auto_collect.utils"] = utils_module

    path = Path(__file__).resolve().parents[2] / "src/lerobot/auto_collect/task_foam_inlaying.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "src.lerobot.auto_collect"
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class DummyDataset:
    def __init__(self, root, episode_index=0, size=0):
        self.root = Path(root)
        self.episode_buffer = {"episode_index": episode_index, "size": size}


class DummySceneBuilder:
    def __init__(self, parts=None):
        self.parts = parts or []

    def get_parts_world_poses(self):
        return self.parts


class DummyJointInterpolator:
    def set_target(self, start_q, target_q, num_steps):
        self.start_q = np.asarray(start_q, dtype=np.float32)
        self.target_q = np.asarray(target_q, dtype=np.float32)
        self.num_steps = num_steps
        self.step_idx = 0

    def step(self):
        self.step_idx += 1
        ratio = self.step_idx / self.num_steps
        return self.start_q + (self.target_q - self.start_q) * ratio


class DummyRobotInterface:
    def __init__(self):
        self.arm_joint_initial_positions = np.arange(14, dtype=np.float32)
        self.finger_joint_initial_positions = np.arange(4, dtype=np.float32) + 20.0
        self.arm_joint_indices = list(range(14))
        self.finger_joint_indices = list(range(14, 18))
        self.joint_interpolator = DummyJointInterpolator()

    def get_joint_states(self):
        return {"all_positions": np.arange(18, dtype=np.float32) + 100.0}


class DummyRobot:
    def __init__(self, parts=None):
        self._scene_builder = DummySceneBuilder(parts)
        self._robot_interface = DummyRobotInterface()
        self._hold_arm_positions = np.arange(14, dtype=np.float32) + 200.0
        self._hold_finger_positions = np.arange(4, dtype=np.float32) + 300.0
        self._left_gripping = True
        self._right_gripping = True
        self.step_count = 0

    def step(self, render=True):
        self.step_count += 1


def test_on_episode_start_clears_part_frame_ranges():
    module = load_task_module()
    task = module.TaskFoamInlaying()
    task._current_episode_part_frames = [{"frame_start_index": 0, "frame_end_index": 8}]

    task._on_episode_start([])

    assert task._current_episode_part_frames == []


def test_sequential_sequence_returns_home_and_skips_part_frame_ranges_by_default(tmp_path):
    module = load_task_module()
    task = module.TaskFoamInlaying()
    part_a = {
        "prim_path": "/World/Foam_A_0",
        "position": [0.20, 0.27, 1.20],
        "type": "part_a",
    }
    part_b = {
        "prim_path": "/World/Foam_B_0",
        "position": [1.20, 0.27, 1.20],
        "type": "part_b",
    }
    robot = DummyRobot([part_a, part_b])
    dataset = DummyDataset(tmp_path)
    grasp_lengths = iter([9, 4])
    home_calls = []
    task._current_episode_part_frames = []
    task._group_parts_by_arm = lambda parts: ([part_a], [part_b])

    def record_grasp_frames(**kwargs):
        kwargs["dataset"].episode_buffer["size"] += next(grasp_lengths)
        return True

    def capture_home(**kwargs):
        home_calls.append((kwargs["arm_side"], kwargs["dataset"].episode_buffer["size"]))

    task._execute_single_part = record_grasp_frames
    task._return_arm_home = capture_home

    success = task._execute_sequential_sequence(
        robot=robot,
        parts=[part_a, part_b],
        box_pos=np.array([0.0, 0.0, 0.0], dtype=np.float32),
        dt=0.02,
        dataset=dataset,
        single_task="Foam Inlaying",
        objects_per_episode=2,
        mode="left_then_right",
    )

    assert success
    assert home_calls == [("left", 9), ("right", 13)]
    assert task._current_episode_part_frames == []


def test_sequential_sequence_records_part_frame_ranges_when_home_return_disabled(tmp_path):
    module = load_task_module()
    task = module.TaskFoamInlaying()
    task.return_home_after_part = False
    part_a = {
        "prim_path": "/World/Foam_A_0",
        "position": [0.20, 0.27, 1.20],
        "type": "part_a",
    }
    part_b = {
        "prim_path": "/World/Foam_B_0",
        "position": [1.20, 0.27, 1.20],
        "type": "part_b",
    }
    robot = DummyRobot([part_a, part_b])
    dataset = DummyDataset(tmp_path)
    grasp_lengths = iter([9, 4])
    home_calls = []
    task._current_episode_part_frames = []
    task._group_parts_by_arm = lambda parts: ([part_a], [part_b])

    def record_grasp_frames(**kwargs):
        kwargs["dataset"].episode_buffer["size"] += next(grasp_lengths)
        return True

    def capture_home(**kwargs):
        home_calls.append((kwargs["arm_side"], kwargs["dataset"].episode_buffer["size"]))

    task._execute_single_part = record_grasp_frames
    task._return_arm_home = capture_home

    success = task._execute_sequential_sequence(
        robot=robot,
        parts=[part_a, part_b],
        box_pos=np.array([0.0, 0.0, 0.0], dtype=np.float32),
        dt=0.02,
        dataset=dataset,
        single_task="Foam Inlaying",
        objects_per_episode=2,
        mode="left_then_right",
    )

    assert success
    assert home_calls == []
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
        ("Foam_A_0", "part_a", "/World/Foam_A_0", 0, 8),
        ("Foam_B_0", "part_b", "/World/Foam_B_0", 9, 12),
    ]


def test_dual_sequence_returns_home_and_skips_part_frame_ranges_by_default(tmp_path):
    module = load_task_module()
    task = module.TaskFoamInlaying()
    left_part = {
        "prim_path": "/World/Foam_A_0",
        "position": [0.20, 0.27, 1.20],
        "type": "part_a",
    }
    right_part = {
        "prim_path": "/World/Foam_B_0",
        "position": [1.20, 0.27, 1.20],
        "type": "part_b",
    }
    robot = DummyRobot([left_part, right_part])
    dataset = DummyDataset(tmp_path)
    home_calls = []
    task._current_episode_part_frames = []
    task._group_parts_by_arm = lambda parts: ([left_part], [right_part])
    task._refresh_part_pose = lambda robot, part: part
    task.compute_grasp_poses = lambda part: {task.get_arm_side(part): {"active": True}}
    task.get_place_pose = lambda robot, part, box_pos: {task.get_arm_side(part): {"active": True}}

    def record_pair_frames(**kwargs):
        kwargs["dataset"].episode_buffer["size"] += 6
        return True

    def capture_home(**kwargs):
        home_calls.append((kwargs["arm_side"], kwargs["dataset"].episode_buffer["size"]))

    task._run_grasp_stages = record_pair_frames
    task._return_arm_home = capture_home

    success = task._execute_dual_sequence(
        robot=robot,
        parts=[left_part, right_part],
        box_pos=np.array([0.0, 0.0, 0.0], dtype=np.float32),
        dt=0.02,
        dataset=dataset,
        single_task="Foam Inlaying",
        objects_per_episode=2,
    )

    assert success
    assert home_calls == [("left", 6), ("right", 6)]
    assert task._current_episode_part_frames == []


def test_dual_sequence_records_each_part_when_home_return_disabled(tmp_path):
    module = load_task_module()
    task = module.TaskFoamInlaying()
    task.return_home_after_part = False
    left_part = {
        "prim_path": "/World/Foam_A_0",
        "position": [0.20, 0.27, 1.20],
        "type": "part_a",
    }
    right_part = {
        "prim_path": "/World/Foam_B_0",
        "position": [1.20, 0.27, 1.20],
        "type": "part_b",
    }
    robot = DummyRobot([left_part, right_part])
    dataset = DummyDataset(tmp_path)
    home_calls = []
    task._current_episode_part_frames = []
    task._group_parts_by_arm = lambda parts: ([left_part], [right_part])
    task._refresh_part_pose = lambda robot, part: part
    task.compute_grasp_poses = lambda part: {task.get_arm_side(part): {"active": True}}
    task.get_place_pose = lambda robot, part, box_pos: {task.get_arm_side(part): {"active": True}}

    def record_pair_frames(**kwargs):
        kwargs["dataset"].episode_buffer["size"] += 6
        return True

    def capture_home(**kwargs):
        home_calls.append((kwargs["arm_side"], kwargs["dataset"].episode_buffer["size"]))

    task._run_grasp_stages = record_pair_frames
    task._return_arm_home = capture_home

    success = task._execute_dual_sequence(
        robot=robot,
        parts=[left_part, right_part],
        box_pos=np.array([0.0, 0.0, 0.0], dtype=np.float32),
        dt=0.02,
        dataset=dataset,
        single_task="Foam Inlaying",
        objects_per_episode=2,
    )

    assert success
    assert home_calls == []
    assert [
        (entry["prim_path"], entry["frame_start_index"], entry["frame_end_index"])
        for entry in task._current_episode_part_frames
    ] == [
        ("/World/Foam_A_0", 0, 5),
        ("/World/Foam_B_0", 0, 5),
    ]


def test_on_episode_saved_writes_part_info_json(tmp_path):
    module = load_task_module()
    task = module.TaskFoamInlaying()
    dataset = DummyDataset(tmp_path)
    task._current_episode_part_frames = [
        {
            "part_name": "Foam_A_0",
            "part_type": "part_a",
            "prim_path": "/World/Foam_A_0",
            "frame_start_index": 0,
            "frame_end_index": 8,
        },
        {
            "part_name": "Foam_B_0",
            "part_type": "part_b",
            "prim_path": "/World/Foam_B_0",
            "frame_start_index": 9,
            "frame_end_index": 12,
        },
    ]

    assert hasattr(task, "_on_episode_saved")
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


def test_return_arm_home_steps_without_recording_frames(monkeypatch):
    module = load_task_module()
    module.torch = types.SimpleNamespace(
        tensor=lambda value: np.asarray(value, dtype=np.float32),
        Tensor=(),
    )
    task = module.TaskFoamInlaying()
    robot = DummyRobot()
    recorded_frames = []
    task._record_frame = lambda robot_arg, dataset, single_task: recorded_frames.append(single_task)

    task._return_arm_home(
        robot=robot,
        arm_side="right",
        dt=0.5,
        dataset=object(),
        single_task="Foam Inlaying",
        duration=1.0,
    )

    assert robot.step_count == 2
    assert recorded_frames == []
    assert np.allclose(
        robot._hold_arm_positions[7:14],
        robot._robot_interface.arm_joint_initial_positions[7:14],
    )
    assert np.allclose(
        robot._hold_finger_positions[2:4],
        robot._robot_interface.finger_joint_initial_positions[2:4],
    )
    assert not robot._right_gripping
