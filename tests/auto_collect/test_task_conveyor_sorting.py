import importlib.util
import json
import logging
import sys
import types
from pathlib import Path

import numpy as np


def load_task_module():
    module_name = "src.lerobot.auto_collect.task_conveyor_sorting"
    for name in [
        module_name,
        "src.lerobot.auto_collect.auto_collect_base",
        "src.lerobot.auto_collect.utils",
    ]:
        sys.modules.pop(name, None)

    base_module = types.ModuleType("src.lerobot.auto_collect.auto_collect_base")

    class DummyAutoCollectBase:
        def _raise_if_keyboard_requested(self):
            return None

    base_module.AutoCollectBase = DummyAutoCollectBase
    sys.modules["src.lerobot.auto_collect.auto_collect_base"] = base_module

    utils_module = types.ModuleType("src.lerobot.auto_collect.utils")
    utils_module.get_conveyor_sorting_part_type = lambda part, scene_builder=None: part.get("type", "part_b")
    sys.modules["src.lerobot.auto_collect.utils"] = utils_module

    path = Path(__file__).resolve().parents[2] / "src/lerobot/auto_collect/task_conveyor_sorting.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "src.lerobot.auto_collect"
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class DummyConfig:
    def __init__(self, task_cfg):
        self.task_cfg = task_cfg


class DummySceneBuilder:
    def __init__(self, parts, transform_offset=None):
        self.parts = parts
        self.transform_offset = np.asarray(transform_offset or [0.0, 0.0, 0.0], dtype=float)
        self.ConveyorBelt_cfg = {"ConveyorBelt_speed": [0.12, 0.0, 0.0]}
        self.conveyor_speed_calls = []

    def get_parts_world_poses(self):
        return self.parts

    def world_to_robot_coords(self, world_pos):
        return (np.asarray(world_pos, dtype=float) + self.transform_offset).tolist()

    def set_conveyor_speed(self, speed):
        self.conveyor_speed_calls.append(list(speed))

    def get_box_positions(self):
        return [
            np.array([0.48616, -0.062, 0.92], dtype=float),
            np.array([0.88616, -0.062, 0.92], dtype=float),
        ]


class DummyRobotInterface:
    def __init__(self, ee_pose):
        self.ee_pose = ee_pose
        self.arm_joint_initial_positions = np.arange(14, dtype=np.float32)
        self.finger_joint_initial_positions = np.arange(4, dtype=np.float32) + 20.0
        self.arm_joint_indices = list(range(14))
        self.finger_joint_indices = list(range(14, 18))
        self.joint_interpolator = DummyJointInterpolator()

    def get_ee_poses(self):
        return {"right": self.ee_pose}

    def get_joint_states(self):
        return {"all_positions": np.arange(18, dtype=np.float32) + 100.0}


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


class DummyRobot:
    def __init__(self, task_cfg, parts, ee_pose, transform_offset=None):
        self.config = DummyConfig(task_cfg)
        self._scene_builder = DummySceneBuilder(parts, transform_offset=transform_offset)
        self._robot_interface = DummyRobotInterface(ee_pose)
        self._hold_arm_positions = np.arange(14, dtype=np.float32) + 200.0
        self._hold_finger_positions = np.arange(4, dtype=np.float32) + 300.0
        self._right_gripping = True
        self.step_count = 0

    def step(self, render=True):
        self.step_count += 1


class DummyDataset:
    def __init__(self, root, episode_index=0, size=0):
        self.root = Path(root)
        self.episode_buffer = {"episode_index": episode_index, "size": size}


def test_stage_target_adds_configured_x_lead():
    module = load_task_module()
    task = module.TaskConveyorSorting()
    part = {"prim_path": "/World/Part_B_0", "position": [0.62, 0.27, 1.20]}
    robot = DummyRobot(
        {"grasp": {}},
        [part],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )

    pose = task._build_conveyor_stage_target(robot, part, stage="stage2", x_lead=0.30)

    assert np.allclose(pose["position"], [0.92, task._DEFAULT_TARGET_Y, task._DEFAULT_TARGET_Z])
    assert np.allclose(pose["rotation"], task._fixed_grasp_rpy)


def test_fixed_grasp_rpy_uses_measured_pose():
    module = load_task_module()
    task = module.TaskConveyorSorting()

    assert np.allclose(task._fixed_grasp_rpy, [-3.0671, -0.4860, -2.1871])


def test_place_rpy_selects_pose_by_part_type():
    module = load_task_module()
    task = module.TaskConveyorSorting()
    part_a = {"prim_path": "/World/Part_A_0", "position": [0.50, 0.20, 1.10], "type": "part_a"}
    part_b = {"prim_path": "/World/Part_B_0", "position": [0.62, 0.27, 1.20], "type": "part_b"}
    robot = DummyRobot(
        {"grasp": {}},
        [part_a, part_b],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )

    assert np.allclose(task._fixed_place_rpy_part_a, [-3.0671, -0.4860, -2.1871])
    assert np.allclose(task._fixed_place_rpy_part_b, [3.0965, -0.1994, -1.7034])
    assert np.allclose(task._get_place_rpy_for_part(robot, part_a), task._fixed_place_rpy_part_a)
    assert np.allclose(task._get_place_rpy_for_part(robot, part_b), task._fixed_place_rpy_part_b)

    part_b_pose = task._build_conveyor_stage_target(robot, part_b, stage="stage2")

    assert np.allclose(part_b_pose["rotation"], task._fixed_grasp_rpy)


def test_get_place_pose_maps_part_a_left_and_part_b_right():
    module = load_task_module()
    task = module.TaskConveyorSorting()
    part_a = {"prim_path": "/World/Part_A_0", "position": [0.50, 0.20, 1.10], "type": "part_a"}
    part_b = {"prim_path": "/World/Part_B_0", "position": [0.62, 0.27, 1.20], "type": "part_b"}
    robot = DummyRobot(
        {"grasp": {}},
        [part_a, part_b],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )

    part_a_pose = task.get_place_pose(robot, part_a, np.array([0.0, 0.0, 0.0]))
    part_b_pose = task.get_place_pose(robot, part_b, np.array([0.0, 0.0, 0.0]))

    assert np.allclose(part_a_pose["right"]["position"], [0.48616, -0.062, 1.22])
    assert np.allclose(part_b_pose["right"]["position"], [0.88616, -0.062, 1.22])


def test_place_rpy_can_be_overridden_from_config():
    module = load_task_module()
    task = module.TaskConveyorSorting()
    part_b = {"prim_path": "/World/Part_B_0", "position": [0.62, 0.27, 1.20], "type": "part_b"}
    robot = DummyRobot(
        {"grasp": {"conveyor_part_b_place_rpy": [1.0, 2.0, 3.0]}},
        [part_b],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )

    assert np.allclose(task._get_place_rpy_for_part(robot, part_b), [1.0, 2.0, 3.0])


def test_structured_part_log_is_suppressed(monkeypatch):
    module = load_task_module()
    task = module.TaskConveyorSorting()
    part_b = {
        "prim_path": "/World/Part_B_0",
        "position": [0.62, 0.27, 1.20],
        "type": "part_b",
        "index": 3,
    }
    captured = []

    monkeypatch.setattr(module.logging, "log", lambda level, message: captured.append((level, message)))

    task._log_conveyor_event(
        module.logging.INFO,
        "selected_part",
        "cyan",
        **task._part_log_fields(part_b),
    )

    assert captured == []


def test_structured_part_log_does_not_print_to_terminal(capsys):
    module = load_task_module()
    task = module.TaskConveyorSorting()

    task._log_conveyor_event(
        module.logging.INFO,
        "close_ready",
        "green",
        part_key="/World/Part_B_0",
    )

    stdout = capsys.readouterr().out
    assert stdout == ""


def test_move_to_world_pose_uses_explicit_xyz_target():
    module = load_task_module()
    task = module.TaskConveyorSorting()
    captured = {}
    robot = DummyRobot(
        {"grasp": {}},
        [],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )

    def capture_joint_move(robot_arg, target_poses, dt, duration, dataset=None, single_task=None):
        captured["target_poses"] = target_poses
        captured["dt"] = dt
        captured["duration"] = duration

    task._joint_interpolate_to_pose = capture_joint_move
    rotation = np.array([-3.0671, -0.4860, -2.1871], dtype=np.float32)

    task._move_to_world_pose(
        robot,
        x=10.80,
        y=-0.1492,
        z=0.10,
        rotation=rotation,
        dt=0.02,
        duration=0.5,
        dataset=None,
        single_task="test",
    )

    assert np.allclose(captured["target_poses"]["right"]["position"], [10.80, -0.1492, 0.10])
    assert np.allclose(captured["target_poses"]["right"]["rotation"], rotation)
    assert captured["dt"] == 0.02
    assert captured["duration"] == 0.5


def test_stage_target_uses_converted_part_x_and_stage_configured_yz():
    module = load_task_module()
    task = module.TaskConveyorSorting()
    part = {"prim_path": "/World/Part_A_0", "position": [0.50, 0.20, 1.10]}
    robot = DummyRobot(
        {
            "grasp": {
                "conveyor_stage2_target_y": -0.1492,
                "conveyor_stage2_target_z": 0.10,
            }
        },
        [part],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        transform_offset=[10.0, 20.0, 30.0],
    )

    target_pose = task._build_conveyor_stage_target(
        robot,
        part,
        stage="stage2",
        x_lead=0.30,
    )

    assert np.allclose(target_pose["position"], [10.80, -0.1492, 0.10])


def test_stage_target_can_keep_previous_x_while_overriding_stage_yz():
    module = load_task_module()
    task = module.TaskConveyorSorting()
    part = {"prim_path": "/World/Part_A_0", "position": [0.50, 0.20, 1.10]}
    robot = DummyRobot(
        {
            "grasp": {
                "conveyor_stage3_target_y": -0.05,
                "conveyor_stage3_target_z": 0.12,
            }
        },
        [part],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        transform_offset=[10.0, 20.0, 30.0],
    )

    target_pose = task._build_conveyor_stage_target(
        robot,
        part,
        stage="stage3",
        fixed_x=8.88,
    )

    assert np.allclose(target_pose["position"], [8.88, -0.05, 0.12])


def test_stage_target_ignores_legacy_global_yz_config():
    module = load_task_module()
    task = module.TaskConveyorSorting()
    part = {"prim_path": "/World/Part_A_0", "position": [0.50, 0.20, 1.10]}
    robot = DummyRobot(
        {
            "grasp": {
                "conveyor_target_y": -9.99,
                "conveyor_target_z": 9.99,
            }
        },
        [part],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        transform_offset=[10.0, 20.0, 30.0],
    )

    target_pose = task._build_conveyor_stage_target(
        robot,
        part,
        stage="stage2",
        x_lead=0.30,
    )

    assert np.allclose(
        target_pose["position"],
        [10.80, task._DEFAULT_TARGET_Y, task._DEFAULT_TARGET_Z],
    )


def test_stage_target_uses_configured_stage_x_before_x_lead_or_fixed_x():
    module = load_task_module()
    task = module.TaskConveyorSorting()
    part = {"prim_path": "/World/Part_A_0", "position": [0.50, 0.20, 1.10]}
    robot = DummyRobot(
        {
            "grasp": {
                "conveyor_stage2_target_x": 1.23,
                "conveyor_stage3_target_x": 2.34,
                "conveyor_stage4_target_x": 3.45,
            }
        },
        [part],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        transform_offset=[10.0, 20.0, 30.0],
    )

    stage2_pose = task._build_conveyor_stage_target(
        robot,
        part,
        stage="stage2",
        x_lead=0.30,
    )
    stage3_pose = task._build_conveyor_stage_target(
        robot,
        part,
        stage="stage3",
        fixed_x=8.88,
    )
    stage4_pose = task._build_conveyor_stage_target(
        robot,
        part,
        stage="stage4",
        fixed_x=8.88,
    )

    assert np.isclose(stage2_pose["position"][0], 1.23)
    assert np.isclose(stage3_pose["position"][0], 2.34)
    assert np.isclose(stage4_pose["position"][0], 3.45)


def test_stage_target_none_stage_x_falls_back_to_x_lead_or_fixed_x():
    module = load_task_module()
    task = module.TaskConveyorSorting()
    part = {"prim_path": "/World/Part_A_0", "position": [0.50, 0.20, 1.10]}
    robot = DummyRobot(
        {
            "grasp": {
                "conveyor_stage2_target_x": "none",
                "conveyor_stage3_target_x": "None",
                "conveyor_stage4_target_x": None,
            }
        },
        [part],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        transform_offset=[10.0, 20.0, 30.0],
    )

    stage2_pose = task._build_conveyor_stage_target(
        robot,
        part,
        stage="stage2",
        x_lead=0.30,
    )
    stage3_pose = task._build_conveyor_stage_target(
        robot,
        part,
        stage="stage3",
        fixed_x=8.88,
    )
    stage4_pose = task._build_conveyor_stage_target(
        robot,
        part,
        stage="stage4",
        fixed_x=8.88,
    )

    assert np.isclose(stage2_pose["position"][0], 10.80)
    assert np.isclose(stage3_pose["position"][0], 8.88)
    assert np.isclose(stage4_pose["position"][0], 8.88)


def test_timeout_uses_timelimit_seconds_only():
    module = load_task_module()
    task = module.TaskConveyorSorting()
    robot = DummyRobot(
        {"timelimit": 99},
        [],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )

    assert task._get_timeout_s(robot) == 99.0


def test_timeout_defaults_when_timelimit_is_missing():
    module = load_task_module()
    task = module.TaskConveyorSorting()
    robot = DummyRobot(
        {},
        [],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )

    assert task._get_timeout_s(robot) == task._DEFAULT_TIMEOUT_S


def test_execute_sequence_rerecords_when_waiting_for_part_times_out(monkeypatch):
    module = load_task_module()
    task = module.TaskConveyorSorting()
    robot = DummyRobot(
        {
            "timelimit": 100,
            "grasp": {"conveyor_wait_part_timeout_s": 2.0},
        },
        [],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )
    perf_times = iter([0.0, 0.0, 1.0, 2.1])
    wait_calls = []

    monkeypatch.setattr(module.time, "perf_counter", lambda: next(perf_times))

    def fail_if_waiting_after_timeout(*args, **kwargs):
        wait_calls.append((args, kwargs))
        if len(wait_calls) > 2:
            raise AssertionError("waiting for part timeout should rerecord the current episode")

    task._wait_for_parts = fail_if_waiting_after_timeout

    success = task._execute_sequence(
        robot=robot,
        parts=[],
        box_pos=np.array([0.0, 0.0, 0.0], dtype=np.float32),
        dt=0.02,
        dataset=None,
        single_task="Conveyor Sorting",
        objects_per_episode=1,
    )

    assert not success
    assert len(wait_calls) == 2


def test_stage6_selects_place_rpy_by_part_type_without_mutating_place_poses():
    module = load_task_module()
    task = module.TaskConveyorSorting()
    part_b = {"prim_path": "/World/Part_B_0", "position": [0.62, 0.27, 1.20], "type": "part_b"}
    robot = DummyRobot(
        {"grasp": {}},
        [part_b],
        [0.614, 9.99, 1.18, 0.0, 0.0, 0.0],
    )
    original_place_rpy = np.array([9.0, 8.0, 7.0], dtype=np.float32)
    place_poses = {
        "right": {
            "position": np.array([0.48616, -0.062, 1.10], dtype=np.float32),
            "rotation": original_place_rpy.copy(),
        }
    }
    captured_place_targets = []

    task._log_runtime_poses = lambda *args, **kwargs: None
    task.move_gripper = lambda *args, **kwargs: None
    task._move_to_world_pose = lambda *args, **kwargs: None
    task._wait_and_close_gripper_when_ready = lambda *args, **kwargs: True

    def capture_joint_move(robot_arg, target_poses, dt, duration, dataset=None, single_task=None):
        captured_place_targets.append(target_poses)

    task._joint_interpolate_to_pose = capture_joint_move

    success = task._run_grasp_stages(
        robot=robot,
        part=part_b,
        grasp_poses={"right": {"active": True}},
        place_poses=place_poses,
        dt=0.02,
        dataset=None,
        single_task="test",
        check_success_fn=lambda: True,
    )

    assert success
    assert np.allclose(place_poses["right"]["rotation"], original_place_rpy)
    assert np.allclose(
        captured_place_targets[-1]["right"]["rotation"],
        task._fixed_place_rpy_part_b,
    )


def test_stage6_prepare_pose_uses_place_xy_and_configured_z_before_final_place(caplog):
    module = load_task_module()
    task = module.TaskConveyorSorting()
    part_b = {"prim_path": "/World/Part_B_0", "position": [0.62, 0.27, 1.20], "type": "part_b"}
    robot = DummyRobot(
        {"grasp": {"conveyor_stage6_prepare_target_z": 0.42}},
        [part_b],
        [0.614, 9.99, 1.18, 0.0, 0.0, 0.0],
    )
    place_poses = {
        "right": {
            "position": np.array([0.48616, -0.062, 1.10], dtype=np.float32),
            "rotation": task._fixed_place_rpy_part_b.copy(),
        }
    }
    captured_place_targets = []

    task._log_runtime_poses = lambda *args, **kwargs: None
    task.move_gripper = lambda *args, **kwargs: None
    task._move_to_world_pose = lambda *args, **kwargs: None
    task._wait_and_close_gripper_when_ready = lambda *args, **kwargs: True

    def capture_joint_move(robot_arg, target_poses, dt, duration, dataset=None, single_task=None):
        captured_place_targets.append(target_poses)

    task._joint_interpolate_to_pose = capture_joint_move

    caplog.set_level(logging.INFO)

    success = task._run_grasp_stages(
        robot=robot,
        part=part_b,
        grasp_poses={"right": {"active": True}},
        place_poses=place_poses,
        dt=0.02,
        dataset=None,
        single_task="test",
        check_success_fn=lambda: True,
    )

    assert success
    assert len(captured_place_targets) == 2
    assert np.allclose(
        captured_place_targets[0]["right"]["position"],
        [0.48616, -0.062, 1.10],
    )
    assert np.allclose(
        captured_place_targets[1]["right"]["position"],
        [0.48616, -0.062, 0.42],
    )
    messages = [record.getMessage() for record in caplog.records]
    assert messages.index("阶段6 [right]: 移动到投放位置...") < messages.index(
        "阶段6预定位 [right]: 移动到投放位置 XY / 配置 Z..."
    ) < messages.index("阶段7 [right]: 松开夹爪...")


def test_stage5_grasp_failure_releases_gripper_before_returning_false():
    module = load_task_module()
    task = module.TaskConveyorSorting()
    part_b = {"prim_path": "/World/Part_B_0", "position": [0.62, 0.27, 1.20], "type": "part_b"}
    robot = DummyRobot(
        {"grasp": {}},
        [part_b],
        [0.614, 9.99, 1.18, 0.0, 0.0, 0.0],
    )
    gripper_targets = []

    task._log_runtime_poses = lambda *args, **kwargs: None
    task._move_to_world_pose = lambda *args, **kwargs: None

    def capture_gripper(robot_arg, targets, dt, duration, dataset=None, single_task=None):
        gripper_targets.append(targets["right"])
        robot_arg._right_gripping = targets["right"] >= 0.0

    task.move_gripper = capture_gripper

    def close_during_wait(*args, **kwargs):
        task.move_gripper(robot, {"right": 1.0}, 0.02, 0.1)
        return True

    task._wait_and_close_gripper_when_ready = close_during_wait

    success = task._run_grasp_stages(
        robot=robot,
        part=part_b,
        grasp_poses={"right": {"active": True}},
        place_poses={
            "right": {
                "position": np.array([0.48616, -0.062, 1.10], dtype=np.float32),
                "rotation": task._fixed_place_rpy_part_b.copy(),
            }
        },
        dt=0.02,
        dataset=None,
        single_task="test",
        check_success_fn=lambda: False,
    )

    assert not success
    assert gripper_targets == [-1.0, 1.0, -1.0]
    assert not robot._right_gripping


def test_stage2_move_uses_configured_target_y():
    module = load_task_module()
    task = module.TaskConveyorSorting()
    part_b = {"prim_path": "/World/Part_B_0", "position": [0.62, 0.27, 1.20], "type": "part_b"}
    robot = DummyRobot(
        {
            "grasp": {
                "conveyor_stage2_target_y": -0.321,
                "conveyor_stage2_target_z": 0.123,
            }
        },
        [part_b],
        [0.614, 9.99, 1.18, 0.0, 0.0, 0.0],
    )
    move_targets = []

    task._log_runtime_poses = lambda *args, **kwargs: None
    task.move_gripper = lambda *args, **kwargs: None
    task._wait_and_close_gripper_when_ready = lambda *args, **kwargs: True
    task._joint_interpolate_to_pose = lambda *args, **kwargs: None

    def capture_move(robot_arg, x, y, z, rotation, dt, duration, dataset, single_task):
        move_targets.append((x, y, z, duration))

    task._move_to_world_pose = capture_move

    task._run_grasp_stages(
        robot=robot,
        part=part_b,
        grasp_poses={"right": {"active": True}},
        place_poses={
            "right": {
                "position": np.array([0.48616, -0.062, 1.10], dtype=np.float32),
                "rotation": task._fixed_place_rpy_part_b.copy(),
            }
        },
        dt=0.02,
        dataset=None,
        single_task="test",
        check_success_fn=lambda: False,
    )

    assert np.isclose(move_targets[0][1], -0.321)
    assert np.isclose(move_targets[0][2], 0.123)


def test_stage2_move_duration_can_be_configured():
    module = load_task_module()
    task = module.TaskConveyorSorting()
    part_b = {"prim_path": "/World/Part_B_0", "position": [0.62, 0.27, 1.20], "type": "part_b"}
    robot = DummyRobot(
        {"grasp": {"conveyor_stage2_duration": 1.2}},
        [part_b],
        [0.614, 9.99, 1.18, 0.0, 0.0, 0.0],
    )
    move_targets = []

    task._log_runtime_poses = lambda *args, **kwargs: None
    task.move_gripper = lambda *args, **kwargs: None
    task._wait_and_close_gripper_when_ready = lambda *args, **kwargs: True
    task._joint_interpolate_to_pose = lambda *args, **kwargs: None
    task._move_to_world_pose = (
        lambda robot_arg, x, y, z, rotation, dt, duration, dataset, single_task:
        move_targets.append(duration)
    )

    task._run_grasp_stages(
        robot=robot,
        part=part_b,
        grasp_poses={"right": {"active": True}},
        place_poses={
            "right": {
                "position": np.array([0.48616, -0.062, 1.10], dtype=np.float32),
                "rotation": task._fixed_place_rpy_part_b.copy(),
            }
        },
        dt=0.02,
        dataset=None,
        single_task="test",
        check_success_fn=lambda: False,
    )

    assert move_targets[0] == 1.2


def test_grasp_stages_move_from_stage2_directly_to_stage3():
    module = load_task_module()
    task = module.TaskConveyorSorting()
    part_b = {"prim_path": "/World/Part_B_0", "position": [0.62, 0.27, 1.20], "type": "part_b"}
    robot = DummyRobot(
        {
            "grasp": {
                "conveyor_stage2_target_x": 0.6049,
                "conveyor_stage2_target_y": -0.1156,
                "conveyor_stage2_target_z": 0.2,
                "conveyor_stage2_duration": 0.3,
                "conveyor_stage3_target_x": 0.6049,
                "conveyor_stage3_target_y": -0.1156,
                "conveyor_stage3_target_z": 0.0914,
            }
        },
        [part_b],
        [0.614, 9.99, 1.18, 0.0, 0.0, 0.0],
    )
    move_targets = []

    task._log_runtime_poses = lambda *args, **kwargs: None
    task.move_gripper = lambda *args, **kwargs: None
    task._wait_and_close_gripper_when_ready = lambda *args, **kwargs: True
    task._joint_interpolate_to_pose = lambda *args, **kwargs: None

    def capture_move(robot_arg, x, y, z, rotation, dt, duration, dataset, single_task):
        move_targets.append(
            {
                "position": [x, y, z],
                "rotation": np.asarray(rotation, dtype=np.float32),
                "duration": duration,
            }
        )

    task._move_to_world_pose = capture_move

    task._run_grasp_stages(
        robot=robot,
        part=part_b,
        grasp_poses={"right": {"active": True}},
        place_poses={
            "right": {
                "position": np.array([0.48616, -0.062, 1.10], dtype=np.float32),
                "rotation": task._fixed_place_rpy_part_b.copy(),
            }
        },
        dt=0.02,
        dataset=None,
        single_task="test",
        check_success_fn=lambda: False,
    )

    assert np.allclose(move_targets[0]["position"], [0.6049, -0.1156, 0.2])
    assert move_targets[0]["duration"] == 0.3
    assert np.allclose(move_targets[1]["position"], [0.6049, -0.1156, 0.0914])
    assert move_targets[1]["duration"] == 0.2


def test_close_gripper_uses_live_part_world_x_range_from_config():
    module = load_task_module()
    task = module.TaskConveyorSorting()
    part_a = {"prim_path": "/World/Part_A_0", "position": [0.70, 0.27, 1.20], "type": "part_a"}
    part_b = {"prim_path": "/World/Part_B_0", "position": [0.70, 0.27, 1.20], "type": "part_b"}
    robot = DummyRobot(
        {
            "grasp": {
                "conveyor_close_world_x_min": 0.71,
                "conveyor_close_world_x_max": 0.73,
            }
        },
        [part_a, part_b],
        [999.0, 9.99, 1.18, 0.0, 0.0, 0.0],
    )

    assert not task._should_close_gripper(robot, part_a)
    assert not task._should_close_gripper(robot, part_b)

    part_a["position"][0] = 0.71
    part_b["position"][0] = 0.72
    assert task._should_close_gripper(robot, part_a)
    assert task._should_close_gripper(robot, part_b)

    part_a["position"][0] = 0.73
    assert task._should_close_gripper(robot, part_a)

    part_a["position"][0] = 0.7301
    part_b["position"][0] = 0.7099
    assert not task._should_close_gripper(robot, part_a)
    assert not task._should_close_gripper(robot, part_b)


def test_record_start_part_uses_configured_world_x_threshold():
    module = load_task_module()
    task = module.TaskConveyorSorting()
    leading_part = {"prim_path": "/World/Part_B_0", "position": [0.69, 0.27, 1.20]}
    trailing_part = {"prim_path": "/World/Part_A_0", "position": [0.50, 0.27, 1.20]}
    robot = DummyRobot(
        {"grasp": {"conveyor_record_start_x": 0.70}},
        [leading_part, trailing_part],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )

    assert task._get_record_start_part(robot, [leading_part, trailing_part]) is None

    leading_part["position"][0] = 0.71

    assert task._get_record_start_part(robot, [leading_part, trailing_part]) is leading_part


def test_execute_sequence_pauses_conveyor_before_home_return_and_restores_after():
    module = load_task_module()
    task = module.TaskConveyorSorting()
    task._TARGET_PARTS_PER_EPISODE = 1
    part_b = {"prim_path": "/World/Part_B_0", "position": [0.72, 0.27, 1.20], "type": "part_b"}
    robot = DummyRobot(
        {"timelimit": 10, "grasp": {}},
        [part_b],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )
    call_order = []

    def capture_speed(speed):
        call_order.append(("speed", list(speed)))
        robot._scene_builder.conveyor_speed_calls.append(list(speed))

    robot._scene_builder.set_conveyor_speed = capture_speed
    def place_part_b_in_right_bin(**kwargs):
        part_b["position"] = [0.88616, -0.062, 0.92]
        return True

    task._run_grasp_stages = place_part_b_in_right_bin
    task._return_right_arm_home = lambda **kwargs: call_order.append(("home", None))

    success = task._execute_sequence(
        robot=robot,
        parts=[],
        box_pos=np.array([0.0, 0.0, 0.0], dtype=np.float32),
        dt=0.02,
        dataset=None,
        single_task="Conveyor Sorting",
        objects_per_episode=1,
    )

    assert success
    assert call_order == [
        ("speed", [0.0, 0.0, 0.0]),
        ("home", None),
        ("speed", [0.12, 0.0, 0.0]),
    ]


def test_execute_sequence_respects_objects_per_episode_limit():
    module = load_task_module()
    task = module.TaskConveyorSorting()
    task._TARGET_PARTS_PER_EPISODE = 8
    part_b = {"prim_path": "/World/Part_B_0", "position": [0.72, 0.27, 1.20], "type": "part_b"}
    robot = DummyRobot(
        {"timelimit": 10, "grasp": {}},
        [part_b],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )
    completed_parts = []

    def complete_and_place_part(**kwargs):
        completed_parts.append(kwargs["part"]["prim_path"])
        part_b["position"] = [0.88616, -0.062, 0.92]
        return True

    task._run_grasp_stages = complete_and_place_part
    task._return_right_arm_home = lambda **kwargs: None

    def fail_if_waiting_for_more_parts(*args, **kwargs):
        raise AssertionError("objects_per_episode=1 should finish after one processed part")

    task._wait_for_parts = fail_if_waiting_for_more_parts

    success = task._execute_sequence(
        robot=robot,
        parts=[],
        box_pos=np.array([0.0, 0.0, 0.0], dtype=np.float32),
        dt=0.02,
        dataset=None,
        single_task="Conveyor Sorting",
        objects_per_episode=1,
    )

    assert success
    assert completed_parts == ["/World/Part_B_0"]


def test_wait_for_parts_checks_keyboard_even_without_recording():
    module = load_task_module()
    task = module.TaskConveyorSorting()
    task._WAIT_STEP_S = 0.04
    robot = DummyRobot(
        {"grasp": {}},
        [],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )
    keyboard_checks = []
    recorded_frames = []

    task._raise_if_keyboard_requested = lambda: keyboard_checks.append(True)
    task._record_frame = lambda robot_arg, dataset, single_task: recorded_frames.append(single_task)

    task._wait_for_parts(
        robot=robot,
        dt=0.02,
        dataset=None,
        single_task="Conveyor Sorting",
    )

    assert keyboard_checks == [True, True]
    assert robot.step_count == 2
    assert recorded_frames == []


def test_execute_sequence_returns_home_and_skips_part_frame_ranges_by_default(tmp_path):
    module = load_task_module()
    task = module.TaskConveyorSorting()
    task._TARGET_PARTS_PER_EPISODE = 2
    part_a = {"prim_path": "/World/Part_A_0", "position": [0.71, 0.27, 1.20], "type": "part_a"}
    part_b = {"prim_path": "/World/Part_B_0", "position": [0.72, 0.27, 1.20], "type": "part_b"}
    robot = DummyRobot(
        {"timelimit": 10, "grasp": {}},
        [part_a, part_b],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )
    dataset = DummyDataset(tmp_path)
    grasp_lengths = iter([9, 4])

    def record_grasp_frames(**kwargs):
        kwargs["dataset"].episode_buffer["size"] += next(grasp_lengths)
        part = kwargs["part"]
        if part["type"] == "part_a":
            part["position"][:] = [0.48616, -0.062, 0.92]
        else:
            part["position"][:] = [0.88616, -0.062, 0.92]
        return True

    home_sizes = []
    task._run_grasp_stages = record_grasp_frames
    task._return_right_arm_home = lambda **kwargs: home_sizes.append(kwargs["dataset"].episode_buffer["size"])

    success = task._execute_sequence(
        robot=robot,
        parts=[],
        box_pos=np.array([0.0, 0.0, 0.0], dtype=np.float32),
        dt=0.02,
        dataset=dataset,
        single_task="Conveyor Sorting",
        objects_per_episode=2,
    )

    assert success
    assert home_sizes == [9, 13]
    assert task._current_episode_part_frames == []


def test_execute_sequence_records_part_frame_ranges_when_home_return_disabled(tmp_path):
    module = load_task_module()
    task = module.TaskConveyorSorting()
    task.return_home_after_part = False
    task._TARGET_PARTS_PER_EPISODE = 2
    part_a = {"prim_path": "/World/Part_A_0", "position": [0.71, 0.27, 1.20], "type": "part_a"}
    part_b = {"prim_path": "/World/Part_B_0", "position": [0.72, 0.27, 1.20], "type": "part_b"}
    robot = DummyRobot(
        {"timelimit": 10, "grasp": {}},
        [part_a, part_b],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )
    dataset = DummyDataset(tmp_path)
    grasp_lengths = iter([9, 4])

    def record_grasp_frames(**kwargs):
        kwargs["dataset"].episode_buffer["size"] += next(grasp_lengths)
        part = kwargs["part"]
        if part["type"] == "part_a":
            part["position"][:] = [0.48616, -0.062, 0.92]
        else:
            part["position"][:] = [0.88616, -0.062, 0.92]
        return True

    home_sizes = []
    task._run_grasp_stages = record_grasp_frames
    task._return_right_arm_home = lambda **kwargs: home_sizes.append(kwargs["dataset"].episode_buffer["size"])

    success = task._execute_sequence(
        robot=robot,
        parts=[],
        box_pos=np.array([0.0, 0.0, 0.0], dtype=np.float32),
        dt=0.02,
        dataset=dataset,
        single_task="Conveyor Sorting",
        objects_per_episode=2,
    )

    assert success
    assert home_sizes == []
    assert [
        (entry["frame_start_index"], entry["frame_end_index"])
        for entry in task._current_episode_part_frames
    ] == [(0, 8), (9, 12)]


def test_execute_sequence_does_not_record_wait_frames_before_part_is_grabbable(tmp_path):
    module = load_task_module()
    task = module.TaskConveyorSorting()
    task.return_home_after_part = False
    task._TARGET_PARTS_PER_EPISODE = 1
    part_b = {"prim_path": "/World/Part_B_0", "position": [0.60, 0.27, 1.20], "type": "part_b"}
    robot = DummyRobot(
        {
            "timelimit": 10,
            "grasp": {
                "conveyor_record_start_x": 0.50,
                "conveyor_grab_zone_x_min": 0.70,
                "conveyor_grab_zone_x_max": 1.20,
            },
        },
        [part_b],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )
    dataset = DummyDataset(tmp_path)

    def wait_without_recording(robot_arg, dt, dataset, single_task):
        assert dataset is None
        part_b["position"][0] = 0.72

    def record_grasp_frames(**kwargs):
        kwargs["dataset"].episode_buffer["size"] += 3
        part_b["position"] = [0.88616, -0.062, 0.92]
        return True

    task._wait_for_parts = wait_without_recording
    task._run_grasp_stages = record_grasp_frames
    task._return_right_arm_home = lambda **kwargs: None

    success = task._execute_sequence(
        robot=robot,
        parts=[],
        box_pos=np.array([0.0, 0.0, 0.0], dtype=np.float32),
        dt=0.02,
        dataset=dataset,
        single_task="Conveyor Sorting",
        objects_per_episode=1,
    )

    assert success
    assert dataset.episode_buffer["size"] == 3
    assert task._current_episode_part_frames[0]["frame_start_index"] == 0
    assert task._current_episode_part_frames[0]["frame_end_index"] == 2


def test_execute_sequence_succeeds_after_processed_part_is_in_correct_bin():
    module = load_task_module()
    task = module.TaskConveyorSorting()
    task._TARGET_PARTS_PER_EPISODE = 1
    part_b = {
        "prim_path": "/World/Part_B_0",
        "position": [0.72, 0.27, 1.20],
        "type": "part_b",
    }
    robot = DummyRobot(
        {"timelimit": 10, "grasp": {}},
        [part_b],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )

    def complete_and_place_in_right_bin(**kwargs):
        part_b["position"] = [0.88616, -0.062, 1.80]
        return True

    task._run_grasp_stages = complete_and_place_in_right_bin
    task._return_right_arm_home = lambda **kwargs: None

    success = task._execute_sequence(
        robot=robot,
        parts=[],
        box_pos=np.array([0.0, 0.0, 0.0], dtype=np.float32),
        dt=0.02,
        dataset=None,
        single_task="Conveyor Sorting",
        objects_per_episode=1,
    )

    assert success


def test_execute_sequence_fails_after_processed_part_is_in_wrong_bin():
    module = load_task_module()
    task = module.TaskConveyorSorting()
    task._TARGET_PARTS_PER_EPISODE = 1
    part_b = {
        "prim_path": "/World/Part_B_0",
        "position": [0.72, 0.27, 1.20],
        "type": "part_b",
    }
    robot = DummyRobot(
        {"timelimit": 10, "grasp": {}},
        [part_b],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )

    def complete_and_place_in_left_bin(**kwargs):
        part_b["position"] = [0.48616, -0.062, 0.92]
        return True

    task._run_grasp_stages = complete_and_place_in_left_bin
    task._return_right_arm_home = lambda **kwargs: None

    success = task._execute_sequence(
        robot=robot,
        parts=[],
        box_pos=np.array([0.0, 0.0, 0.0], dtype=np.float32),
        dt=0.02,
        dataset=None,
        single_task="Conveyor Sorting",
        objects_per_episode=1,
    )

    assert not success


def test_on_episode_saved_writes_part_info_json(tmp_path):
    module = load_task_module()
    task = module.TaskConveyorSorting()
    dataset = DummyDataset(tmp_path)
    task._current_episode_part_frames = [
        {
            "part_name": "Part_B_0",
            "part_type": "part_b",
            "prim_path": "/World/Part_B_0",
            "frame_start_index": 0,
            "frame_end_index": 8,
        },
        {
            "part_name": "Part_A_0",
            "part_type": "part_a",
            "prim_path": "/World/Part_A_0",
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


def test_return_right_arm_home_steps_without_recording_frames(monkeypatch):
    module = load_task_module()
    torch_module = types.ModuleType("torch")
    torch_module.tensor = lambda value: np.asarray(value, dtype=np.float32)
    monkeypatch.setitem(sys.modules, "torch", torch_module)

    task = module.TaskConveyorSorting()
    robot = DummyRobot(
        {"grasp": {}},
        [],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )
    recorded_frames = []
    task._record_frame = lambda robot_arg, dataset, single_task: recorded_frames.append(single_task)

    task._return_right_arm_home(
        robot,
        dt=0.02,
        dataset=object(),
        single_task="Conveyor Sorting",
    )

    assert robot.step_count == 12
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


def test_return_right_arm_home_lifts_current_right_pose_before_joint_home(monkeypatch):
    module = load_task_module()
    torch_module = types.ModuleType("torch")
    torch_module.tensor = lambda value: np.asarray(value, dtype=np.float32)
    monkeypatch.setitem(sys.modules, "torch", torch_module)

    task = module.TaskConveyorSorting()
    robot = DummyRobot(
        {"grasp": {"conveyor_home_return_steps": 1}},
        [],
        [0.48616, -0.062, 0.42, -3.0, -0.4, -2.1],
    )
    lift_targets = []
    recorded_frames = []

    def capture_lift(robot_arg, target_poses, dt, duration, dataset=None, single_task=None):
        lift_targets.append((target_poses, dt, duration, dataset, single_task))

    task._joint_interpolate_to_pose = capture_lift
    task._record_frame = lambda robot_arg, dataset, single_task: recorded_frames.append(single_task)

    task._return_right_arm_home(
        robot,
        dt=0.02,
        dataset=object(),
        single_task="Conveyor Sorting",
    )

    assert len(lift_targets) == 1
    target_poses, lift_dt, duration, lift_dataset, lift_task = lift_targets[0]
    assert np.allclose(target_poses["right"]["position"], [0.48616, -0.062, 0.72])
    assert np.allclose(target_poses["right"]["rotation"], [-3.0, -0.4, -2.1])
    assert lift_dt == 0.02
    assert duration == 0.4
    assert lift_dataset is None
    assert lift_task is None
    assert recorded_frames == []
