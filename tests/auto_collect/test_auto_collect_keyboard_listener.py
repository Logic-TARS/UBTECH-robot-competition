import importlib.util
import sys
import types
from pathlib import Path


def load_config_module():
    module_name = "src.lerobot.auto_collect.auto_collect_config"
    missing = object()
    stubbed_module_names = [module_name, "src.lerobot.robots.config"]
    previous_modules = {name: sys.modules.get(name, missing) for name in stubbed_module_names}
    sys.modules.pop(module_name, None)

    robots_config_module = types.ModuleType("src.lerobot.robots.config")
    robots_config_module.RobotConfig = object
    sys.modules["src.lerobot.robots.config"] = robots_config_module

    path = Path(__file__).resolve().parents[2] / "src/lerobot/auto_collect/auto_collect_config.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "src.lerobot.auto_collect"
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        for name, previous_module in previous_modules.items():
            if previous_module is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous_module
    return module


def load_base_module():
    module_name = "src.lerobot.auto_collect.auto_collect_base"
    missing = object()
    stubbed_module_names = [
        module_name,
        "src.lerobot.auto_collect.auto_collect_config",
        "src.lerobot.datasets.lerobot_dataset",
        "src.lerobot.datasets.pipeline_features",
        "src.lerobot.datasets.utils",
        "src.lerobot.datasets.video_utils",
        "src.lerobot.processor",
        "src.lerobot.utils.constants",
        "src.lerobot.utils.control_utils",
        "src.lerobot.robots.walker_s2_sim.isaac_sim_robot_interface",
        "numpy",
        "torch",
    ]
    previous_modules = {name: sys.modules.get(name, missing) for name in stubbed_module_names}

    for name in stubbed_module_names:
        sys.modules.pop(name, None)

    numpy_module = types.ModuleType("numpy")
    numpy_module.array = lambda value, *args, **kwargs: list(value)
    numpy_module.asarray = lambda value, *args, **kwargs: list(value)
    numpy_module.float32 = float
    numpy_module.ndarray = list
    sys.modules["numpy"] = numpy_module

    torch_module = types.ModuleType("torch")
    sys.modules["torch"] = torch_module

    config_module = types.ModuleType("src.lerobot.auto_collect.auto_collect_config")
    config_module.AutoCollectConfig = object
    sys.modules["src.lerobot.auto_collect.auto_collect_config"] = config_module

    dataset_module = types.ModuleType("src.lerobot.datasets.lerobot_dataset")
    dataset_module.LeRobotDataset = object
    sys.modules["src.lerobot.datasets.lerobot_dataset"] = dataset_module

    pipeline_features_module = types.ModuleType("src.lerobot.datasets.pipeline_features")
    pipeline_features_module.aggregate_pipeline_dataset_features = lambda **kwargs: {}
    pipeline_features_module.create_initial_features = lambda **kwargs: {}
    sys.modules["src.lerobot.datasets.pipeline_features"] = pipeline_features_module

    dataset_utils_module = types.ModuleType("src.lerobot.datasets.utils")
    dataset_utils_module.build_dataset_frame = lambda features, data, prefix=None: {}
    dataset_utils_module.combine_feature_dicts = lambda *args: {}
    sys.modules["src.lerobot.datasets.utils"] = dataset_utils_module

    video_utils_module = types.ModuleType("src.lerobot.datasets.video_utils")
    video_utils_module.VideoEncodingManager = object
    sys.modules["src.lerobot.datasets.video_utils"] = video_utils_module

    processor_module = types.ModuleType("src.lerobot.processor")
    processor_module.make_default_processors = lambda: (None, None, None)
    sys.modules["src.lerobot.processor"] = processor_module

    constants_module = types.ModuleType("src.lerobot.utils.constants")
    constants_module.ACTION = "action"
    constants_module.OBS_STR = "observation"
    sys.modules["src.lerobot.utils.constants"] = constants_module

    control_utils_module = types.ModuleType("src.lerobot.utils.control_utils")
    control_utils_module.consume_episode_rerecord_request = lambda events: False
    control_utils_module.consume_recording_stop_request = lambda events: False
    control_utils_module.init_keyboard_listener = lambda: (None, {})
    sys.modules["src.lerobot.utils.control_utils"] = control_utils_module

    robot_interface_module = types.ModuleType(
        "src.lerobot.robots.walker_s2_sim.isaac_sim_robot_interface"
    )
    robot_interface_module.CartesianTrajectoryPlanner = object
    sys.modules[
        "src.lerobot.robots.walker_s2_sim.isaac_sim_robot_interface"
    ] = robot_interface_module

    path = Path(__file__).resolve().parents[2] / "src/lerobot/auto_collect/auto_collect_base.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "src.lerobot.auto_collect"
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        for name, previous_module in previous_modules.items():
            if previous_module is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous_module
    return module


def make_task(base_module):
    class DummyAutoCollect(base_module.AutoCollectBase):
        def _execute_sequence(self, robot, parts, box_pos, dt, dataset, single_task, objects_per_episode):
            return True

        def compute_grasp_poses(self, part):
            return {}

        def check_grasp_success(self, robot, part):
            return True

        def get_place_pose(self, robot, part, box_pos):
            return {}

    return DummyAutoCollect()


class DummySceneBuilder:
    def get_box_positions(self):
        return []

    def get_parts_world_poses(self):
        return [{"prim_path": "/World/Part_0", "position": [0.0, 0.0, 0.0]}]


class DummyRobot:
    def __init__(self):
        self.is_connected = False
        self._scene_builder = DummySceneBuilder()
        self.reset_count = 0
        self.step_count = 0
        self.disconnect_count = 0

    def connect(self):
        self.is_connected = True

    def disconnect(self):
        self.disconnect_count += 1
        self.is_connected = False

    def reset(self):
        self.reset_count += 1

    def step(self, render=True):
        self.step_count += 1


def make_run_cfg(enable_keyboard_listener, return_home_after_part=True):
    return types.SimpleNamespace(
        arm_execution_mode="dual",
        task="Part_Sorting",
        record_data=False,
        single_task="Part Sorting",
        fps=30,
        num_episodes=1,
        max_retries=1,
        objects_per_episode=0,
        push_to_hub=False,
        enable_keyboard_listener=enable_keyboard_listener,
        return_home_after_part=return_home_after_part,
    )


def test_auto_collect_config_enables_keyboard_listener_by_default():
    module = load_config_module()

    cfg = module.AutoCollectConfig()

    assert cfg.enable_keyboard_listener is True


def test_auto_collect_config_returns_home_after_part_by_default():
    module = load_config_module()

    cfg = module.AutoCollectConfig()

    assert cfg.return_home_after_part is True


def test_keyboard_monitoring_disabled_skips_listener_initialization():
    module = load_base_module()
    task = make_task(module)

    def fail_if_called():
        raise AssertionError("keyboard listener should not start when disabled")

    module.init_keyboard_listener = fail_if_called

    listener, events = task._init_keyboard_monitoring(
        types.SimpleNamespace(enable_keyboard_listener=False)
    )

    assert listener is None
    assert events is None
    assert task._keyboard_events is None


def test_keyboard_monitoring_defaults_to_existing_enabled_behavior():
    module = load_base_module()
    task = make_task(module)
    listener = types.SimpleNamespace(stopped=False)
    events = {"stop_recording": False, "rerecord_episode": False}
    calls = []

    def capture_listener():
        calls.append(True)
        return listener, events

    module.init_keyboard_listener = capture_listener

    actual_listener, actual_events = task._init_keyboard_monitoring(types.SimpleNamespace())

    assert calls == [True]
    assert actual_listener is listener
    assert actual_events is events
    assert task._keyboard_events is events


def test_run_skips_keyboard_listener_when_disabled():
    module = load_base_module()
    task = make_task(module)
    robot = DummyRobot()

    def fail_if_called():
        raise AssertionError("keyboard listener should not start when disabled")

    module.init_keyboard_listener = fail_if_called

    task.run(robot, make_run_cfg(enable_keyboard_listener=False))

    assert task._keyboard_events is None
    assert robot.reset_count == 1
    assert robot.disconnect_count == 1


def test_run_applies_return_home_after_part_config():
    module = load_base_module()
    task = make_task(module)
    robot = DummyRobot()

    task.run(robot, make_run_cfg(enable_keyboard_listener=False, return_home_after_part=False))

    assert task.return_home_after_part is False
