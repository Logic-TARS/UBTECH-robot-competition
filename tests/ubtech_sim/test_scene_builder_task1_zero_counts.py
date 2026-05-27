import importlib.util
import sys
import types
from pathlib import Path


def load_scene_builder_module():
    module_name = "Ubtech_sim.source.SceneBuilder"
    sys.modules.pop(module_name, None)

    isaacsim_module = types.ModuleType("isaacsim")
    isaacsim_core_module = types.ModuleType("isaacsim.core")
    isaacsim_core_utils_module = types.ModuleType("isaacsim.core.utils")
    isaacsim_module.__path__ = []
    isaacsim_core_module.__path__ = []
    isaacsim_core_utils_module.__path__ = []
    sys.modules["isaacsim"] = isaacsim_module
    sys.modules["isaacsim.core"] = isaacsim_core_module
    sys.modules["isaacsim.core.utils"] = isaacsim_core_utils_module

    stage_module = types.ModuleType("isaacsim.core.utils.stage")
    stage_module.add_reference_to_stage = lambda *args, **kwargs: None
    sys.modules["isaacsim.core.utils.stage"] = stage_module

    prims_module = types.ModuleType("isaacsim.core.prims")
    prims_module.Articulation = object
    prims_module.XFormPrim = object
    prims_module.SingleRigidPrim = object
    prims_module.RigidPrim = object
    sys.modules["isaacsim.core.prims"] = prims_module

    cloner_module = types.ModuleType("isaacsim.core.cloner")
    cloner_module.Cloner = object
    sys.modules["isaacsim.core.cloner"] = cloner_module

    simulation_manager_module = types.ModuleType("isaacsim.core.simulation_manager")
    simulation_manager_module.SimulationManager = types.SimpleNamespace(
        get_physics_sim_view=lambda: None
    )
    sys.modules["isaacsim.core.simulation_manager"] = simulation_manager_module

    omni_replicator_module = types.ModuleType("omni.replicator")
    omni_replicator_module.__path__ = []
    rep_module = types.ModuleType("omni.replicator.core")
    sys.modules["omni.replicator"] = omni_replicator_module
    sys.modules["omni.replicator.core"] = rep_module

    omni_module = types.ModuleType("omni")
    omni_module.__path__ = []
    omni_usd_module = types.ModuleType("omni.usd")
    omni_module.usd = omni_usd_module
    sys.modules["omni"] = omni_module
    sys.modules["omni.usd"] = omni_usd_module

    pxr_module = types.ModuleType("pxr")
    usd_geom_module = types.ModuleType("pxr.UsdGeom")
    gf_module = types.ModuleType("pxr.Gf")
    pxr_module.UsdGeom = usd_geom_module
    pxr_module.Gf = gf_module
    sys.modules["pxr"] = pxr_module
    sys.modules["pxr.UsdGeom"] = usd_geom_module
    sys.modules["pxr.Gf"] = gf_module

    coordinate_module = types.ModuleType("Ubtech_sim.source.coordinate_utils")
    coordinate_module.CoordinateTransform = object
    sys.modules["Ubtech_sim.source.coordinate_utils"] = coordinate_module

    path = Path(__file__).resolve().parents[2] / "Ubtech_sim/source/SceneBuilder.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def make_builder(part_cfg):
    module = load_scene_builder_module()
    builder = module.SceneBuilder.__new__(module.SceneBuilder)
    builder.part_cfg = part_cfg
    return builder


def test_task1_part_plan_allows_one_type_to_have_zero_parts():
    builder = make_builder(
        {
            "part_a_assets": [],
            "part_b_assets": ["Collected_Part_B_blue/Part_B.usd"],
            "num_parts": 2,
            "num_parts_a": 0,
            "num_parts_b": 1,
        }
    )

    assert builder._get_task1_part_plan() == [
        ("part_a", [], 0),
        ("part_b", ["Collected_Part_B_blue/Part_B.usd"], 1),
    ]


def test_task1_part_plan_rejects_empty_asset_pool_only_when_count_positive():
    builder = make_builder(
        {
            "part_a_assets": [],
            "part_b_assets": ["Collected_Part_B_blue/Part_B.usd"],
            "num_parts_a": 1,
            "num_parts_b": 0,
        }
    )

    try:
        builder._get_task1_part_plan()
    except ValueError as exc:
        assert "part_a_assets" in str(exc)
    else:
        raise AssertionError("Expected missing part_a_assets to fail when num_parts_a > 0")


def test_task1_reset_converts_part_plan_to_path_creation_spec():
    builder = make_builder(
        {
            "part_a_assets": [],
            "part_b_assets": ["Collected_Part_B_blue/Part_B.usd"],
            "num_parts_a": 0,
            "num_parts_b": 1,
        }
    )
    builder._initial_parts_prim_paths = ["/Root/Part_B_0"]
    builder._delete_old_parts = lambda: None
    captured = {}

    def capture_create_parts_at_paths(**kwargs):
        captured.update(kwargs)
        return ["/Root/Part_B_0"]

    builder._create_parts_at_paths = capture_create_parts_at_paths

    builder._randomize_task1_assets()

    assert captured["part_pools"] == [
        (["Collected_Part_B_blue/Part_B.usd"], 1, "part_b")
    ]
    assert builder.parts_prim_paths == ["/Root/Part_B_0"]
