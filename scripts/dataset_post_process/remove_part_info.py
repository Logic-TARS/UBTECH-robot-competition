#!/usr/bin/env python3
"""
删除 LeRobot 数据集目录下 meta/ 文件夹中的 part_info.json 文件。

用法:
    python remove_part_info.py /path/to/datasets
    python remove_part_info.py /path/to/datasets --no-log
    python remove_part_info.py /path/to/datasets --log-dir /tmp/logs
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path


def setup_logger(log_dir: str) -> logging.Logger:
    """配置日志记录器，同时输出到控制台和 txt 文件。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"remove_part_info_{timestamp}.txt")
    logger = logging.getLogger("remove_part_info")
    logger.setLevel(logging.INFO)

    # 文件日志处理器
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                                      datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(fh)

    # 控制台日志处理器
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(ch)

    logger.info(f"日志文件: {log_file}")
    return logger


def find_dataset_dirs(root: str) -> list[Path]:
    """查找 LeRobot 数据集目录（包含 meta/ 子目录的文件夹）。"""
    datasets = []
    root_path = Path(root)
    for entry in root_path.iterdir():
        if entry.is_dir() and (entry / "meta").is_dir():
            datasets.append(entry)
    return sorted(datasets)


def remove_part_info(dataset_dir: Path, logger: logging.Logger | None) -> bool:
    """删除数据集 meta/ 目录下的 part_info.json 文件。返回 True 表示已删除。"""
    part_info = dataset_dir / "meta" / "part_info.json"
    if part_info.exists():
        try:
            # 尝试读取文件内容以便记录 key 信息
            info = {}
            try:
                with open(part_info, "r") as f:
                    info = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

            part_info.unlink()
            msg = f"已删除: {part_info}"
            if info:
                msg += f" | 内容 keys: {list(info.keys())}"
            if logger:
                logger.info(msg)
            else:
                print(msg)
            return True
        except OSError as e:
            err = f"删除失败 {part_info}: {e}"
            if logger:
                logger.error(err)
            else:
                print(err, file=sys.stderr)
            return False
    else:
        if logger:
            logger.debug(f"未找到 (跳过): {part_info}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="删除 LeRobot 数据集 meta/ 目录下的 part_info.json 文件"
    )
    parser.add_argument("root_dir", help="包含 LeRobot 数据集的根目录路径")
    parser.add_argument(
        "--no-log", action="store_true",
        help="禁用文件日志，仅输出到控制台"
    )
    parser.add_argument(
        "--log-dir", default=None,
        help="日志输出目录 (默认: 与 root_dir 相同)"
    )
    args = parser.parse_args()

    root = os.path.abspath(args.root_dir)
    if not os.path.isdir(root):
        print(f"错误: '{root}' 不是有效的目录", file=sys.stderr)
        sys.exit(1)

    logger = None
    if not args.no_log:
        log_dir = args.log_dir or root
        os.makedirs(log_dir, exist_ok=True)
        logger = setup_logger(log_dir)

    if logger:
        logger.info(f"扫描目录: {root}")
    else:
        print(f"扫描目录: {root}")

    datasets = find_dataset_dirs(root)

    if logger:
        logger.info(f"找到 {len(datasets)} 个数据集")
    else:
        print(f"找到 {len(datasets)} 个数据集")

    deleted_count = 0
    for ds in datasets:
        if remove_part_info(ds, logger):
            deleted_count += 1

    summary = f"完成: 已删除 {deleted_count} 个文件, 共扫描 {len(datasets)} 个数据集"
    if logger:
        logger.info(summary)
    else:
        print(summary)


if __name__ == "__main__":
    main()
