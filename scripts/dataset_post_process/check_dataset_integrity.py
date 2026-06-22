#!/usr/bin/env python
"""Standalone data integrity checker for LeRobot datasets.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
作用：检查 LeRobot 数据集的完整性与一致性，验证 meta/info.json、meta/episodes
      parquet、data parquet、videos mp4 之间的交叉数据是否匹配。

不依赖 lerobot 内部模块，仅需 pandas + av（PyAV），可独立运行。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Usage:
    python dataset_post_process/check_dataset_integrity.py /path/to/dataset
    python dataset_post_process/check_dataset_integrity.py /path/to/dataset --json      # JSON output
    python dataset_post_process/check_dataset_integrity.py /path/to/dataset --no-video  # Skip video checks

检查内容（6 大类）：
────────────────────────────────────────────────────────────────────────────

1. 文件结构 (File Structure)
   - meta/info.json          是否存在且可解析
   - meta/episodes/*.parquet 是否存在
   - data/*.parquet          是否存在
   - videos/ 目录            是否与声明的 video features 一致

2. info.json 一致性 (info.json Consistency)
   - total_episodes  是否等于 meta/episodes 中的实际 episode 数量
   - total_frames    是否等于所有 episode length 之和
   - total_frames    是否等于 data parquet 总行数
   - fps             是否 > 0
   - splits          范围是否在 [0, total_episodes) 内

3. Episode 元数据完整性 (Episode Metadata Integrity)
   - episode_index   是否从 0 到 N-1 连续，无缺口、无重复
   - dataset_to_index - dataset_from_index == length  （逐 episode 验证）
   - index 链连续性   上一个 episode 的 to_index 是否等于下一个的 from_index
   - **视频时间戳 vs 声明帧数**  ← 最常见的错误
     对每个 episode 的每个摄像头：
       round((to_timestamp - from_timestamp) * fps) == length
     若不相等，说明 meta/episodes 中记录的视频时间戳与实际帧数不一致，
     会导致 delete_episodes 等操作在 _copy_and_reindex_videos 中断言失败。

4. Data Parquet 完整性 (Data Parquet Integrity)
   - 总行数         是否等于 info.json total_frames
   - 逐 episode 行数  是否等于该 episode 声明的 length
   - index 字段      在每个 episode 内是否连续（相邻行差值全为 1）
   - orphan episode  是否有 data parquet 有但 meta 没有的 episode，反之亦然

5. 视频文件完整性 (Video File Integrity)
   - 所有 episode 引用的 (video_key, chunk_index, file_index) 对应 mp4 是否存在
   - 视频文件的实际帧数是否 ≥ 该文件内 episode 所需的最大 to_frame
   - 各摄像头总帧数是否一致（排除不同步问题）

6. 汇总 (Summary)
   - PASS / FAIL / WARN 计数
   - 列出所有异常 episode 及其具体差异值（diff）
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd

# ── Helpers ──────────────────────────────────────────────────────────────────

_STATUS = {"pass": 0, "fail": 0, "warn": 0}
_ISSUES: list[str] = []  # failed episode details for summary


def _msg(status: str, text: str) -> None:
    _STATUS[status] += 1
    label = {"pass": "PASS", "fail": "FAIL", "warn": "WARN"}[status]
    print(f"[{label}] {text}")


def _load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def _load_parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


# ── Check functions ──────────────────────────────────────────────────────────


def check_file_structure(root: Path) -> dict[str, Any]:
    """Verify essential files and directories exist."""
    print("\n─── File Structure ──────────────────────────────────────────")

    info_path = root / "meta" / "info.json"
    if info_path.exists():
        _msg("pass", "meta/info.json exists")
    else:
        _msg("fail", "meta/info.json MISSING")
        return {"info": None}

    info = _load_json(info_path)

    ep_dir = root / "meta" / "episodes"
    ep_files = sorted(ep_dir.rglob("*.parquet")) if ep_dir.exists() else []
    if ep_files:
        _msg("pass", f"meta/episodes/ has {len(ep_files)} parquet file(s)")
    else:
        _msg("fail", "meta/episodes/ has NO parquet files")

    data_dir = root / "data"
    data_files = sorted(data_dir.rglob("*.parquet")) if data_dir.exists() else []
    if data_files:
        _msg("pass", f"data/ has {len(data_files)} parquet file(s)")
    else:
        _msg("fail", "data/ has NO parquet files")

    # Video keys from info.json
    video_keys = [k for k, v in info.get("features", {}).items() if v.get("dtype") == "video"]
    videos_dir = root / "videos"
    if video_keys and not videos_dir.exists():
        _msg("warn", f"videos/ dir MISSING but {len(video_keys)} video feature(s) declared")
    elif video_keys:
        _msg("pass", f"videos/ dir exists with key(s): {video_keys}")
    else:
        _msg("pass", "no video features declared")

    return {
        "info": info,
        "ep_files": ep_files,
        "data_files": data_files,
        "video_keys": video_keys,
    }


def check_info_json(info: dict, ep_df: pd.DataFrame, data_row_count: int) -> None:
    """Cross-validate info.json totals against actual data."""
    print("\n─── info.json Consistency ───────────────────────────────────")

    declared_episodes = info.get("total_episodes")
    declared_frames = info.get("total_frames")
    fps = info.get("fps")
    actual_episodes = len(ep_df)

    if declared_episodes is None:
        _msg("fail", "total_episodes missing from info.json")
    elif declared_episodes == actual_episodes:
        _msg("pass", f"total_episodes ({declared_episodes}) == actual episodes ({actual_episodes})")
    else:
        _msg("fail", f"total_episodes ({declared_episodes}) != actual episodes ({actual_episodes})")

    if declared_frames is None:
        _msg("fail", "total_frames missing from info.json")
    else:
        sum_lengths = int(ep_df["length"].sum())
        if declared_frames == sum_lengths:
            _msg("pass", f"total_frames ({declared_frames}) == sum of episode lengths ({sum_lengths})")
        else:
            _msg("fail", f"total_frames ({declared_frames}) != sum of episode lengths ({sum_lengths})")

        if declared_frames == data_row_count:
            _msg("pass", f"total_frames ({declared_frames}) == parquet row count ({data_row_count})")
        else:
            _msg("fail", f"total_frames ({declared_frames}) != parquet row count ({data_row_count})")

    if fps is not None and fps > 0:
        _msg("pass", f"fps={fps}")
    else:
        _msg("fail", f"fps invalid: {fps}")

    # Check splits range
    splits = info.get("splits", {})
    if splits:
        for split_name, split_range in splits.items():
            try:
                parts = split_range.split(":")
                start, end = int(parts[0]), int(parts[1])
                if 0 <= start < end <= declared_episodes:
                    _msg("pass", f"split '{split_name}': {split_range} valid")
                else:
                    _msg("fail", f"split '{split_name}': {split_range} out of range [0, {declared_episodes})")
            except (ValueError, IndexError):
                _msg("fail", f"split '{split_name}': bad range format '{split_range}'")


def check_episode_metadata(
    ep_df: pd.DataFrame, info: dict, video_keys: list[str]
) -> None:
    """Validate episode metadata internal consistency."""
    print("\n─── Episode Metadata Integrity ──────────────────────────────")

    # Check episode_indices are 0..N-1 contiguous
    indices = sorted(ep_df["episode_index"].tolist())
    expected = list(range(len(indices)))
    if indices == expected:
        _msg("pass", f"episode_indices are 0..{len(indices)-1} contiguous, no gaps")
    else:
        gaps = sorted(set(expected) - set(indices))
        dups = [i for i in indices if indices.count(i) > 1]
        if gaps:
            _msg("fail", f"gap(s) in episode_indices: {gaps}")
        if dups:
            _msg("fail", f"duplicate episode_index: {sorted(set(dups))}")

    # Per-episode checks
    mismatched_video_eps: dict[str, set[int]] = {}  # video_key -> set of episode indices
    mismatched_data_range: list[int] = []
    broken_chain: list[int] = []
    prev_to_idx = None

    for _, row in ep_df.sort_values("episode_index").iterrows():
        ei = row["episode_index"]

        # dataset_to_index - dataset_from_index == length
        declared_len = row["length"]
        calc_len = row["dataset_to_index"] - row["dataset_from_index"]
        if declared_len != calc_len:
            mismatched_data_range.append(ei)

        # Index chain continuity
        if prev_to_idx is not None and row["dataset_from_index"] != prev_to_idx:
            broken_chain.append(ei)
        prev_to_idx = row["dataset_to_index"]

        # Video timestamp range vs declared length
        fps = info.get("fps", 30)
        for vk in video_keys:
            col_from = f"videos/{vk}/from_timestamp"
            col_to = f"videos/{vk}/to_timestamp"
            if col_from in row.index and col_to in row.index:
                from_ts = row[col_from]
                to_ts = row[col_to]
                if pd.notna(from_ts) and pd.notna(to_ts):
                    v_frames = round((to_ts - from_ts) * fps)
                    if declared_len != v_frames:
                        diff = v_frames - declared_len
                        if vk not in mismatched_video_eps:
                            mismatched_video_eps[vk] = set()
                        mismatched_video_eps[vk].add(ei)
                        _ISSUES.append(
                            f"EP{ei}: length={declared_len}, "
                            f"{vk} frames_from_timestamps={v_frames} (diff={diff:+d})"
                        )

    if mismatched_data_range:
        _msg("fail", f"dataset_to/from range != length: episodes {mismatched_data_range}")
    else:
        _msg("pass", "all episodes: dataset_to_index - dataset_from_index == length")

    if broken_chain:
        _msg("fail", f"index chain broken before episodes: {broken_chain}")
    else:
        _msg("pass", "dataset index chain is continuous across episodes")

    if mismatched_video_eps:
        # Merge all video-key mismatches into a single episode set
        all_mismatched = set()
        for vk, eps in mismatched_video_eps.items():
            all_mismatched.update(eps)
        _msg(
            "fail",
            f"video timestamp range != length: {len(all_mismatched)} episode(s) "
            f"({sorted(all_mismatched)})",
        )
    else:
        _msg("pass", "all episodes: video timestamp range matches declared length")


def check_data_parquet(
    data_files: list[Path], ep_df: pd.DataFrame, info_total_frames: int
) -> dict[int, int]:
    """Validate data parquet files."""
    print("\n─── Data Parquet Integrity ─────────────────────────────────")

    all_dfs = []
    for df_path in data_files:
        df = _load_parquet(df_path)
        all_dfs.append(df)
    data_df = pd.concat(all_dfs, ignore_index=True) if len(all_dfs) > 1 else all_dfs[0]

    total_rows = len(data_df)

    if total_rows == info_total_frames:
        _msg("pass", f"total parquet rows ({total_rows}) == info.json total_frames ({info_total_frames})")
    else:
        _msg("fail", f"total parquet rows ({total_rows}) != info.json total_frames ({info_total_frames})")

    # Per-episode row count vs declared length
    per_ep_rows: dict[int, int] = {}
    mismatched_rows: list[int] = []
    broken_index: list[int] = []

    for ei in sorted(data_df["episode_index"].unique()):
        ep_data = data_df[data_df["episode_index"] == ei]
        row_count = len(ep_data)
        per_ep_rows[ei] = row_count

        # Check against declared length
        declared = ep_df[ep_df["episode_index"] == ei]
        if len(declared) == 1:
            declared_len = declared.iloc[0]["length"]
            if row_count != declared_len:
                mismatched_rows.append(ei)

        # Check index continuity
        idx = ep_data["index"].values
        if not (idx[1:] - idx[:-1] == 1).all():
            broken_index.append(ei)

    if mismatched_rows:
        _msg("fail", f"parquet rows != declared length: episodes {mismatched_rows}")
    else:
        _msg("pass", "all episodes: parquet row count == declared length")

    if broken_index:
        _msg("fail", f"index field not continuous: episodes {broken_index}")
    else:
        _msg("pass", "index field is continuous within each episode")

    # Check for orphan episodes (in parquet but not in meta)
    meta_indices = set(ep_df["episode_index"].tolist())
    data_indices = set(data_df["episode_index"].unique())
    orphans = data_indices - meta_indices
    missing = meta_indices - data_indices
    if orphans:
        _msg("warn", f"episodes in data but NOT in meta: {sorted(orphans)}")
    if missing:
        _msg("warn", f"episodes in meta but NOT in data: {sorted(missing)}")
    if not orphans and not missing:
        _msg("pass", "episode indices match between meta and data parquet")

    return per_ep_rows


def check_videos(
    root: Path, video_keys: list[str], ep_df: pd.DataFrame, info: dict
) -> None:
    """Validate video files exist and have sufficient frames."""
    print("\n─── Video File Integrity ────────────────────────────────────")

    if not video_keys:
        _msg("pass", "no video features — skipping video checks")
        return

    fps = info.get("fps", 30)

    # Collect all unique (video_key, chunk_index, file_index) combos from episodes
    file_sets: dict[str, set[tuple[int, int]]] = {vk: set() for vk in video_keys}
    for _, row in ep_df.iterrows():
        for vk in video_keys:
            ci = row.get(f"videos/{vk}/chunk_index")
            fi = row.get(f"videos/{vk}/file_index")
            if pd.notna(ci) and pd.notna(fi):
                file_sets[vk].add((int(ci), int(fi)))

    video_path_template = info.get("video_path", "videos/{video_key}/chunk-{chunk_index:03d}/file-{file_index:03d}.mp4")

    missing_files: list[str] = []
    insufficient_frames: list[str] = []
    existed_files: list[str] = []

    for vk in video_keys:
        for ci, fi in sorted(file_sets[vk]):
            rel_path = video_path_template.format(video_key=vk, chunk_index=ci, file_index=fi)
            full_path = root / rel_path

            if not full_path.exists():
                missing_files.append(rel_path)
                continue

            existed_files.append(rel_path)

            # Get max frame range needed from episodes that reference this file
            max_to_frame = 0
            for _, row in ep_df.iterrows():
                r_ci = row.get(f"videos/{vk}/chunk_index")
                r_fi = row.get(f"videos/{vk}/file_index")
                if pd.notna(r_ci) and pd.notna(r_fi) and int(r_ci) == ci and int(r_fi) == fi:
                    to_ts = row.get(f"videos/{vk}/to_timestamp")
                    if pd.notna(to_ts):
                        to_frame = round(to_ts * fps)
                        if to_frame > max_to_frame:
                            max_to_frame = to_frame

            # Check actual frame count
            try:
                import av
                container = av.open(str(full_path))
                video_stream = container.streams.video[0]
                actual_frames = video_stream.frames
                container.close()

                if max_to_frame > actual_frames:
                    insufficient_frames.append(
                        f"{rel_path}: needs >= {max_to_frame} frames, has {actual_frames}"
                    )
            except Exception as e:
                _msg("fail", f"cannot read {rel_path}: {e}")

    if missing_files:
        _msg("fail", f"{len(missing_files)} video file(s) MISSING: {missing_files[:5]}{'...' if len(missing_files) > 5 else ''}")
    else:
        _msg("pass", f"all {len(existed_files)} referenced video file(s) exist")

    if insufficient_frames:
        _msg("fail", f"{len(insufficient_frames)} video file(s) have insufficient frames")
        for item in insufficient_frames[:5]:
            _msg("fail", f"  {item}")
    else:
        _msg("pass", "all video files have sufficient frames for declared episode ranges")

    # Check all cameras have identical frame counts
    try:
        import av
        cam_frames: dict[str, int] = {}
        for vk in video_keys:
            total = 0
            for ci, fi in sorted(file_sets[vk]):
                rel_path = video_path_template.format(video_key=vk, chunk_index=ci, file_index=fi)
                full_path = root / rel_path
                if full_path.exists():
                    container = av.open(str(full_path))
                    video_stream = container.streams.video[0]
                    total += video_stream.frames
                    container.close()
            cam_frames[vk] = total

        if len(set(cam_frames.values())) <= 1:
            _msg("pass", f"all {len(video_keys)} camera(s) have same total frames: {list(cam_frames.values())[0]}")
        else:
            _msg("fail", f"camera frame counts differ: {cam_frames}")
    except ImportError:
        _msg("warn", "PyAV not available, skipping camera frame count check")


# ── Main ─────────────────────────────────────────────────────────────────────


def check_dataset(root: Path, check_video: bool = True) -> dict[str, int]:
    """Run all integrity checks on a LeRobot dataset."""
    global _STATUS, _ISSUES
    _STATUS = {"pass": 0, "fail": 0, "warn": 0}
    _ISSUES = []

    print(f"=== Checking dataset: {root} ===")

    # 1. File structure
    ctx = check_file_structure(root)
    if ctx["info"] is None:
        print("\nCannot continue without valid info.json")
        return _STATUS

    # Load episode metadata
    ep_dfs = []
    for f in ctx["ep_files"]:
        ep_dfs.append(_load_parquet(f))
    ep_df = pd.concat(ep_dfs, ignore_index=True) if len(ep_dfs) > 1 else ep_dfs[0]

    # Count data rows (no per-episode breakdown yet)
    data_row_count = 0
    for f in ctx["data_files"]:
        df = _load_parquet(f)
        data_row_count += len(df)

    # 2. info.json consistency
    check_info_json(ctx["info"], ep_df, data_row_count)

    # 3. Episode metadata integrity
    check_episode_metadata(ep_df, ctx["info"], ctx["video_keys"])

    # 4. Data parquet integrity
    check_data_parquet(ctx["data_files"], ep_df, ctx["info"].get("total_frames", 0))

    # 5. Video integrity
    if check_video:
        check_videos(root, ctx["video_keys"], ep_df, ctx["info"])

    # ── Summary ──
    print("\n─── Summary ─────────────────────────────────────────────────")
    print(f"  PASS: {_STATUS['pass']}, FAIL: {_STATUS['fail']}, WARN: {_STATUS['warn']}")

    if _ISSUES:
        # Deduplicate and keep unique episode-key pairs
        unique = list(dict.fromkeys(_ISSUES))
        bad_eps = sorted(set(
            int(line.split(":")[0].replace("EP", "").strip())
            for line in unique
        ))
        print(f"\n  Episodes with issues: {bad_eps}")
        print(f"  Details ({len(unique)} issue(s)):")
        for line in unique:
            print(f"    {line}")

    return _STATUS


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check LeRobot dataset integrity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("dataset_root", type=str, help="Path to dataset root directory")
    parser.add_argument("--no-video", action="store_true", help="Skip video file checks")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    root = Path(args.dataset_root)
    if not root.exists():
        print(f"ERROR: Dataset root not found: {root}")
        sys.exit(1)

    if args.json:
        # Re-run with JSON output capture
        status = check_dataset(root, check_video=not args.no_video)
        print()  # separator
        print(json.dumps(status))
    else:
        status = check_dataset(root, check_video=not args.no_video)
        if status["fail"] > 0:
            sys.exit(1)


if __name__ == "__main__":
    main()
