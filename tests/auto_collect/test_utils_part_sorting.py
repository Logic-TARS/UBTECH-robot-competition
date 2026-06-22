from src.lerobot.auto_collect.utils import get_part_sorting_part_type


class DummySceneBuilder:
    def __init__(self):
        self.part_cfg = {"num_parts_a": 0, "num_parts_b": 1}
        self.parts_prim_paths = ["/Replicator/Ref_Xform"]
        self.part_type_by_prim_path = {"/Replicator/Ref_Xform": "part_b"}


def test_part_sorting_type_uses_scene_builder_type_map_before_index_fallback():
    scene_builder = DummySceneBuilder()

    assert (
        get_part_sorting_part_type(
            {"prim_path": "/Replicator/Ref_Xform"},
            scene_builder,
        )
        == "part_b"
    )
