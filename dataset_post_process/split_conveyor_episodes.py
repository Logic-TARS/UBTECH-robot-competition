#!/usr/bin/env python3
"""
将自动采集生成的长 episode 按 meta/part_info.json 拆分为单零件短 episode。

适用场景:
    自动数采（Task 1 Part_Sorting / Task 2 Conveyor_Sorting）在一个 episode 内
    连续抓取多个零件，每个零件对应一段连续的帧范围（frame_start_index ~ frame_end_index），
    记录在 meta/part_info.json 中。本脚本按这些帧范围将长 episode 切割为独立的短 episode，
    每个短 episode 只包含一个零件的抓取-放置过程，便于后续训练。

纯离线处理：不启动 Isaac Sim，只读取源 LeRobotDataset 的 observation/action 帧，
通过 LeRobotDataset.create() 写出新数据集。

────────────────────────────────────────────────────────────
运行示例
────────────────────────────────────────────────────────────

  单数据集模式:
    python split_conveyor_episodes.py single \
        --source-root datasets/Part_Sorting/auto/test \
        --output-root datasets/Part_Sorting/auto/test_short_parts

    /isaac-sim/python.sh split_conveyor_episodes.py single \
        --source-root datasets/Part_Sorting/auto/test \
        --output-root datasets/Part_Sorting/auto/test_short_parts

  目录批量模式:
    python split_conveyor_episodes.py directory \
        --source-dir datasets/Part_Sorting/auto \
        --output-parent-dir datasets/Part_Sorting/auto_short_parts

    /isaac-sim/python.sh split_conveyor_episodes.py directory \
        --source-dir datasets/Part_Sorting/auto \
        --output-parent-dir datasets/Part_Sorting/auto_short_parts

  常用选项:
    --no-preserve-visual-obs    不保留视频/图像观测，仅保留 state/action
    --overwrite                  允许覆盖已有输出目录
    --task "Part Sorting"        指定新 episode 的 task 文本

  查看帮助:
    python split_conveyor_episodes.py --help
    python split_conveyor_episodes.py single --help
    python split_conveyor_episodes.py directory --help
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np

# ── 修复路径 ──────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent.resolve()
_repo_root_str = str(REPO_ROOT)
if _repo_root_str not in sys.path:
    sys.path.insert(0, _repo_root_str)

# # Hugging Face datasets 会创建 cache lock 文件。默认 ~/.cache 在部分环境中可能是只读，
# # 因此在导入 LeRobotDataset 前把 cache 放到仓库内可写目录。
# HF_CACHE_ROOT = REPO_ROOT / ".cache" / "huggingface"
# os.environ.setdefault("HF_HOME", str(HF_CACHE_ROOT))
# os.environ.setdefault("HF_DATASETS_CACHE", str(HF_CACHE_ROOT / "datasets"))
# os.environ.setdefault("HF_HUB_CACHE", str(HF_CACHE_ROOT / "hub"))
# (HF_CACHE_ROOT / "datasets").mkdir(parents=True, exist_ok=True)
# (HF_CACHE_ROOT / "hub").mkdir(parents=True, exist_ok=True)

from src.lerobot.datasets.lerobot_dataset import LeRobotDataset

# ── Monkey-patch: 绕过 os.chmod 权限问题 ──────────────────────
# LeRobotDataset.create() 向上递归 chmod 777 父目录，
# 当父目录属于 root 时会抛出 PermissionError。
_original_chmod = os.chmod


def _noop_chmod(path, mode, *args, **kwargs):
    """忽略 chmod 调用（目录权限已满足需求，无需再修改）"""
    try:
        _original_chmod(path, mode, *args, **kwargs)
    except PermissionError:
        pass  # 无权限修改时静默跳过


os.chmod = _noop_chmod

# ========== 命令行参数解析 ========================================

_args = None  # 模块级配置，由 main() 设置


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="将长 episode 按 meta/part_info.json 拆分为单零件短 episode"
    )
    subparsers = parser.add_subparsers(dest="mode", help="处理模式")

    # === single 模式 ===
    single = subparsers.add_parser("single", help="处理单个数据集")
    single.add_argument("--source-root", type=Path, required=True,
                        help="源数据集根目录 (必须含 meta/part_info.json)")
    single.add_argument("--output-root", type=Path, required=True,
                        help="输出数据集根目录")
    single.add_argument("--output-repo-id", type=str, default="",
                        help="输出 repo_id (默认用源目录名)")
    _add_common_args(single)

    # === directory 模式 ===
    directory = subparsers.add_parser("directory", help="批量处理目录下所有数据集")
    directory.add_argument("--source-dir", type=Path, required=True,
                           help="源数据集父目录")
    directory.add_argument("--output-parent-dir", type=Path, required=True,
                           help="输出父目录")
    directory.add_argument("--output-name-suffix", type=str, default="_short_parts",
                           help="输出目录名后缀 (默认: _short_parts)")
    directory.add_argument("--output-repo-id-suffix", type=str, default="_short_parts",
                           help="输出 repo_id 后缀 (默认: _short_parts)")
    directory.add_argument("--recursive", action="store_true", default=True,
                           help="递归扫描子目录 (默认开启)")
    directory.add_argument("--no-recursive", action="store_false", dest="recursive",
                           help="不递归扫描子目录")
    _add_common_args(directory)

    return parser.parse_args()


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    """为 subparser 添加通用参数"""
    parser.add_argument("--no-preserve-visual-obs", action="store_false",
                        dest="preserve_visual_obs", default=True,
                        help="不保留视频/图像观测，仅保留 state/action")
    parser.add_argument("--source-video-backend", type=str, default="pyav",
                        help="源视频解码后端 (默认: pyav)")
    parser.add_argument("--output-video-codec", type=str, default="libsvtav1",
                        help="输出视频编码器 (默认: libsvtav1)")
    parser.add_argument("--image-writer-processes", type=int, default=8,
                        help="写图像并发进程数 (默认: 8)")
    parser.add_argument("--image-writer-threads", type=int, default=4,
                        help="每相机写图像线程数 (默认: 4)")
    parser.add_argument("--overwrite", action="store_true", default=False,
                        help="允许覆盖已有输出目录")
    parser.add_argument("--task", type=str, default=None, dest="single_task",
                        help="新 episode 的 task 文本 (默认沿用源数据集)")
# ================================================================

DEFAULT_FRAME_KEYS = {"index", "episode_index", "frame_index", "timestamp", "task_index"}


def _dataset_has_part_info(dataset_root: Path) -> bool:
    return (dataset_root / "meta" / "info.json").exists() and (dataset_root / "meta" / "part_info.json").exists()


def discover_source_datasets() -> list[Path]:
    if _args.mode == "single":
        return [Path(_args.source_root)]
    if _args.mode != "directory":
        raise ValueError(f"Unsupported _args.mode: {_args.mode!r}")

    base = Path(_args.source_dir)
    info_paths = base.rglob("meta/info.json") if _args.recursive else base.glob("*/meta/info.json")
    roots = sorted({path.parent.parent for path in info_paths})
    return [root for root in roots if _dataset_has_part_info(root)]


def make_output_root(source_root: Path) -> Path:
    if _args.mode == "single":
        return Path(_args.output_root)
    return Path(_args.output_parent_dir) / f"{source_root.name}{_args.output_name_suffix}"


def make_output_repo_id(source_root: Path) -> str:
    if _args.mode == "single" and _args.output_repo_id:
        return _args.output_repo_id
    return f"{source_root.name}{_args.output_repo_id_suffix}"


def load_part_info(source_root: Path) -> list[dict]:
    path = source_root / "meta" / "part_info.json"
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    episodes = data.get("episodes", data if isinstance(data, list) else None)
    if not isinstance(episodes, list):
        raise ValueError(f"Invalid part_info format: {path}")
    return episodes


def output_features_from_source(source_dataset: LeRobotDataset) -> dict:
    features = copy.deepcopy(source_dataset.meta.features)
    if _args.preserve_visual_obs:
        return features
    return {
        key: value
        for key, value in features.items()
        if value.get("dtype") not in {"image", "video"}
    }


def as_numpy(value):
    if hasattr(value, "detach"):
        return value.detach().cpu().numpy()
    if hasattr(value, "cpu") and hasattr(value, "numpy"):
        return value.cpu().numpy()
    if isinstance(value, np.ndarray):
        return value
    return np.asarray(value)


def normalize_feature_value(key: str, value, feature: dict):
    dtype = feature.get("dtype")
    if dtype in {"image", "video"}:
        array = as_numpy(value)
        expected_shape = tuple(feature.get("shape", ()))
        if array.ndim == 3 and expected_shape and tuple(array.shape) != expected_shape:
            if array.shape[0] in (1, 3, 4) and len(expected_shape) == 3 and expected_shape[-1] in (1, 3, 4):
                array = np.moveaxis(array, 0, -1)
        if array.dtype != np.uint8:
            if np.issubdtype(array.dtype, np.floating) and array.max(initial=0) <= 1.0:
                array = np.clip(array * 255.0, 0, 255).astype(np.uint8)
            else:
                array = array.astype(np.uint8)
        return array

    if dtype == "string":
        return str(value)

    array = as_numpy(value)
    if dtype:
        array = array.astype(np.dtype(dtype), copy=False)
    return array


def build_absolute_to_row_index(source_dataset: LeRobotDataset) -> dict[int, int]:
    return {
        int(as_numpy(abs_idx).reshape(-1)[0]): row_idx
        for row_idx, abs_idx in enumerate(source_dataset.hf_dataset["index"])
    }


def get_source_frame(
    source_dataset: LeRobotDataset,
    absolute_frame_index: int,
    include_visual: bool,
    absolute_to_row_index: dict[int, int],
) -> dict:
    row_index = absolute_to_row_index.get(int(absolute_frame_index))
    if row_index is None:
        raise IndexError(f"Global frame index {absolute_frame_index} not found in source dataset")
    if include_visual:
        return source_dataset[row_index]
    return source_dataset.hf_dataset[row_index]


def build_output_frame(source_item: dict, output_features: dict, task: str) -> dict:
    frame = {"task": task}
    for key, feature in output_features.items():
        if key in DEFAULT_FRAME_KEYS:
            continue
        if key not in source_item:
            raise KeyError(f"Source frame missing feature {key!r}")
        frame[key] = normalize_feature_value(key, source_item[key], feature)
    return frame


def episode_task(source_dataset: LeRobotDataset, source_item: dict) -> str:
    if _args.task is not None:
        return _args.task
    task = source_item.get("task")
    if task is not None:
        return str(task)
    task_index = source_item.get("task_index")
    if task_index is not None:
        task_index = int(as_numpy(task_index).reshape(-1)[0])
        return str(source_dataset.meta.tasks.iloc[task_index].name)
    if len(source_dataset.meta.tasks) > 0:
        return str(source_dataset.meta.tasks.index[0])
    return source_dataset.repo_id


def validate_part_range(source_dataset: LeRobotDataset, source_episode: dict, part: dict) -> tuple[int, int]:
    episode_index = int(source_episode["episode_index"])
    ep_meta = source_dataset.meta.episodes[episode_index]
    episode_length = int(source_episode.get("episode_frame_length", ep_meta["length"]))

    start = int(part["frame_start_index"])
    end = int(part["frame_end_index"])
    if start < 0 or end < start or end >= episode_length:
        raise ValueError(
            f"Invalid frame range for episode {episode_index}, part {part.get('part_name')}: {start}-{end}, "
            f"episode_length={episode_length}"
        )
    return start, end


def split_one_dataset(source_root: Path, output_root: Path, output_repo_id: str) -> dict:
    source_root = Path(source_root)
    output_root = Path(output_root)

    if not _dataset_has_part_info(source_root):
        raise FileNotFoundError(f"Missing meta/info.json or meta/part_info.json under {source_root}")

    if output_root.exists():
        if not _args.overwrite:
            raise FileExistsError(f"Output already exists: {output_root}. use --overwrite to replace it.")
        shutil.rmtree(output_root)

    print(f"\n=== Split dataset ===")
    print(f"source: {source_root}")
    print(f"output: {output_root}")

    source_dataset = LeRobotDataset(
        repo_id=source_root.name,
        root=source_root,
        video_backend=_args.source_video_backend,
    )
    part_info_episodes = load_part_info(source_root)
    absolute_to_row_index = build_absolute_to_row_index(source_dataset)
    output_features = output_features_from_source(source_dataset)
    use_videos = any(feature.get("dtype") == "video" for feature in output_features.values())
    camera_count = sum(
        1
        for feature in output_features.values()
        if feature.get("dtype") in {"image", "video"}
    )

    output_dataset = LeRobotDataset.create(
        repo_id=output_repo_id,
        fps=source_dataset.fps,
        features=output_features,
        root=output_root,
        robot_type=source_dataset.meta.robot_type,
        use_videos=use_videos,
        video_backend=source_dataset.video_backend,
        vcodec=_args.output_video_codec,
        image_writer_processes=_args.image_writer_processes if camera_count else 0,
        image_writer_threads=_args.image_writer_threads * camera_count,
        streaming_encoding=False,
        metadata_buffer_size=1,
    )

    created_episodes = 0

    try:
        for source_episode in part_info_episodes:
            source_episode_index = int(source_episode["episode_index"])
            ep_meta = source_dataset.meta.episodes[source_episode_index]
            episode_from_index = int(ep_meta["dataset_from_index"])

            for part_idx, part in enumerate(source_episode.get("parts", [])):
                start, end = validate_part_range(source_dataset, source_episode, part)
                output_dataset.clear_episode_buffer(delete_images=False)

                first_abs_idx = episode_from_index + start
                first_item = get_source_frame(
                    source_dataset, first_abs_idx, _args.preserve_visual_obs, absolute_to_row_index
                )
                task = episode_task(source_dataset, first_item)

                for local_frame_idx in range(start, end + 1):
                    abs_idx = episode_from_index + local_frame_idx
                    source_item = first_item if abs_idx == first_abs_idx else get_source_frame(
                        source_dataset, abs_idx, _args.preserve_visual_obs, absolute_to_row_index
                    )
                    output_dataset.add_frame(build_output_frame(source_item, output_features, task))

                new_episode_index = int(output_dataset.episode_buffer["episode_index"])
                new_episode_length = int(output_dataset.episode_buffer["size"])
                output_dataset.save_episode()

                created_episodes += 1
                print(
                    f"  new_ep={new_episode_index:04d} "
                    f"source_ep={source_episode_index} part={part.get('part_name')} "
                    f"frames={start}-{end} length={new_episode_length}"
                )
    finally:
        output_dataset.finalize()

    print(f"created short episodes: {created_episodes}")
    return {
        "source_root": str(source_root),
        "output_root": str(output_root),
        "created_episodes": created_episodes,
    }


# ── 主入口 ──────────────────────────────────────────────────
if __name__ == "__main__":
    _args = parse_args()
    source_roots = discover_source_datasets()
    if not source_roots:
        raise RuntimeError("No source LeRobot datasets with meta/part_info.json found.")

    results = []
    for source_root in source_roots:
        results.append(
            split_one_dataset(
                source_root=source_root,
                output_root=make_output_root(source_root),
                output_repo_id=make_output_repo_id(source_root),
            )
        )

    print("\n=== Done ===")
    for result in results:
        print(result)
