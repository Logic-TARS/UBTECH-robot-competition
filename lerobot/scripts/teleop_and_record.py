"""
teleop_and_record.py - lerobot v3 (0.5.1) 下的遥操作数据采集脚本

核心修复:
  1. 将 dataset.consolidate() 替换为官方 0.5.1 标准的 dataset.finalize()，解决 Parquet 损坏问题。
  2. 引入官方的 VideoEncodingManager 上下文管理器，确保视频帧与动作数据安全对齐并落盘。
  3. 保留了终端实时打印 Action 和 Observation，便于检查数据。
  4. 交互逻辑：回车开始，[方向键左]重录，[方向键右]提前保存，[Q]退出。
"""

import argparse
import logging
import re
import sys
import time
from pathlib import Path

import torch

# 仅引入 keyboard 用于全局按键监听，彻底移除 mouse 避免误触
from pynput import keyboard

from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.robots.walker_s2_sim.walkers2sim import WalkerS2sim
from lerobot.robots.walker_s2_sim.walkers2simConfig import WalkerS2Config
from lerobot.teleoperators.walker_s2_keyboard.teleop import WalkerS2KeyboardTeleop
from lerobot.teleoperators.walker_s2_keyboard.teleop_config import WalkerS2KeyboardTeleopConfig

from lerobot.datasets.video_utils import VideoEncodingManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("PIL").setLevel(logging.WARNING)
logging.getLogger("h5py").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

DEFAULT_SAVE_PATH = "datasets/task4/v1"
TASK_NAME_TO_ID = {
    "Part_Sorting": 1,
    "Conveyor_Sorting": 2,
    "Foam_Inlaying": 3,
    "Packing_Box": 4,
}

# ==========================================
# 状态机：用于在后台线程和主线程间传递交互信号
# ==========================================
class UIState:
    start_recording = False
    end_episode_early = False
    redo_episode = False
    quit_program = False

    @classmethod
    def reset_episode_flags(cls):
        cls.start_recording = False
        cls.end_episode_early = False
        cls.redo_episode = False

ui_state = UIState()

def on_key_press(key):
    # 处理流程控制快捷键
    if key == keyboard.Key.enter:
        ui_state.start_recording = True
    elif key == keyboard.Key.left:
        ui_state.redo_episode = True
    elif key == keyboard.Key.right:
        ui_state.end_episode_early = True
    elif hasattr(key, 'char') and key.char and key.char.lower() == 'q':
        ui_state.quit_program = True

    # 同步给 teleop 实例处理遥操作控制（如 1/3/4/6 或 k/l）
    if hasattr(main, 'teleop'):
        main.teleop._on_press(key)

def on_key_release(key):
    if hasattr(main, 'teleop'):
        main.teleop._on_release(key)

def parse_args():
    parser = argparse.ArgumentParser(description="WalkerS2 遥操作数据采集")
    # Native args
    parser.add_argument("--num_episodes", type=int, default=5, help="采集 episode 数量")
    parser.add_argument("--fps", type=int, default=30, help="采集帧率")
    parser.add_argument("--task", type=str, default="packing_box", help="任务描述文字")
    parser.add_argument("--repo_id", type=str, default="sjj/test", help="HuggingFace dataset repo_id")
    parser.add_argument("--save_path", type=str, default=DEFAULT_SAVE_PATH, help="本地保存路径")
    parser.add_argument(
        "--task_cfg",
        type=str,
        default="Ubtech_sim/config/Foam_Inlaying.yaml",
        help="Isaac Sim 场景配置 YAML 路径",
    )
    parser.add_argument("--headless", action="store_true", help="无头模式运行仿真")
    parser.add_argument("--episode_time_s", type=float, default=60.0, help="每个 episode 最长时间(秒)")
    parser.add_argument("--resume", action="store_true", help="从已有数据集继续采集")
    parser.add_argument("--vcodec", type=str, default="h264", help="视频编码器，默认 h264")
    parser.add_argument(
        "--dataset_mode",
        type=str,
        choices=("continue", "new"),
        default="continue",
        help="数据集模式：continue=续录最近数据集，new=新建版本目录",
    )
    parser.add_argument(
        "--new_dataset",
        action="store_true",
        help="显式新建数据集（等价于 --dataset_mode=new）",
    )

    # Compatibility args from control_robot style CLI
    parser.add_argument("--robot.type", dest="robot_type", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--control.type", dest="control_type", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--control.task", dest="control_task", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--control.fps", dest="control_fps", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument(
        "--control.display_cameras",
        dest="control_display_cameras",
        type=str,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--control.teleop_time_s",
        dest="control_teleop_time_s",
        type=float,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--dataset.mode", dest="control_dataset_mode", type=str, default=None, help=argparse.SUPPRESS)

    args = parser.parse_args()

    # Validate and map compatibility args
    if args.robot_type is not None and args.robot_type != "walker_s2_sim":
        raise ValueError(f"仅支持 --robot.type=walker_s2_sim，当前为: {args.robot_type}")

    if args.control_type is not None and args.control_type != "teleoperate":
        raise ValueError(f"仅支持 --control.type=teleoperate，当前为: {args.control_type}")

    task_cfg_map = {
        "Foam_Inlaying": "Ubtech_sim/config/Foam_Inlaying.yaml",
        "Conveyor_Sorting": "Ubtech_sim/config/Conveyor_Sorting.yaml",
        "Packing_Box": "Ubtech_sim/config/Packing_Box.yaml",
        "Part_Sorting": "Ubtech_sim/config/Part_Sorting.yaml",
    }
    if args.control_task is not None:
        args.task_cfg = task_cfg_map.get(args.control_task, args.control_task)
        args.task = args.control_task

    if args.control_fps is not None:
        args.fps = args.control_fps

    if args.control_teleop_time_s is not None:
        args.episode_time_s = args.control_teleop_time_s

    if args.control_display_cameras is not None:
        value = args.control_display_cameras.strip().lower()
        if value in {"true", "1", "yes", "y", "on"}:
            args.headless = False
        elif value in {"false", "0", "no", "n", "off"}:
            args.headless = True
        else:
            raise ValueError(
                f"--control.display_cameras 仅支持 true/false，当前为: {args.control_display_cameras}"
            )

    if args.control_dataset_mode is not None:
        mode = args.control_dataset_mode.strip().lower()
        if mode not in {"continue", "new"}:
            raise ValueError(f"--dataset.mode 仅支持 continue/new，当前为: {args.control_dataset_mode}")
        args.dataset_mode = mode

    if args.new_dataset:
        args.dataset_mode = "new"

    # 兼容旧参数：显式 resume 也归为 continue
    if args.resume:
        args.dataset_mode = "continue"

    return args

def resolve_save_path(save_path: Path, resume: bool) -> Path:
    """在非 resume 模式下，若目录已存在则自动选择下一个可用版本目录。"""
    if resume or not save_path.exists():
        return save_path

    base_name = save_path.name
    parent = save_path.parent
    match = re.match(r"^(.*?)(\d+)$", base_name)
    if match:
        prefix = match.group(1)
        index = int(match.group(2))
    else:
        prefix = f"{base_name}_"
        index = 1

    while True:
        index += 1
        candidate = parent / f"{prefix}{index}"
        if not candidate.exists():
            return candidate


def infer_task_name(args) -> str:
    """优先从 control.task 推断任务名；否则从 task_cfg 文件名推断。"""
    if args.control_task in TASK_NAME_TO_ID:
        return args.control_task

    task_cfg_name = Path(args.task_cfg).stem
    if task_cfg_name in TASK_NAME_TO_ID:
        return task_cfg_name

    if args.task in TASK_NAME_TO_ID:
        return args.task

    raise ValueError(
        f"无法识别任务，请使用 {list(TASK_NAME_TO_ID.keys())} 之一。当前 task/control.task/task_cfg 为: "
        f"{args.task} / {args.control_task} / {args.task_cfg}"
    )


def _find_latest_version_dir(task_root: Path) -> Path | None:
    if not task_root.exists():
        return None
    candidates = []
    for p in task_root.iterdir():
        if not p.is_dir():
            continue
        m = re.fullmatch(r"v(\d+)", p.name)
        if m:
            candidates.append((int(m.group(1)), p))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[-1][1]


def _next_version_dir(task_root: Path) -> Path:
    latest = _find_latest_version_dir(task_root)
    if latest is None:
        return task_root / "v1"
    latest_num = int(re.fullmatch(r"v(\d+)", latest.name).group(1))
    return task_root / f"v{latest_num + 1}"


def resolve_dataset_target(args) -> tuple[Path, bool]:
    """
    返回 (save_path, use_resume)。
    默认按任务映射到 datasets/task{1..4}：
      - continue: 续录该任务最后一个版本
      - new: 新建下一个版本
    若用户显式传入 --save_path（非默认值），则遵循该路径。
    """
    user_provided_save_path = args.save_path != DEFAULT_SAVE_PATH
    if user_provided_save_path:
        base = Path(args.save_path)
        if args.dataset_mode == "continue":
            return base, base.exists()
        return resolve_save_path(base, resume=False), False

    task_name = infer_task_name(args)
    task_id = TASK_NAME_TO_ID[task_name]
    task_root = Path("datasets") / f"task{task_id}"

    if args.dataset_mode == "continue":
        latest = _find_latest_version_dir(task_root)
        if latest is None:
            return task_root / "v1", False
        return latest, True

    return _next_version_dir(task_root), False

def wait_for_start_signal(teleop: WalkerS2KeyboardTeleop, robot: WalkerS2sim, auto_start: bool = False):
    """等待操作者按下 Enter 键后才开始录制"""
    if auto_start:
        logger.info("检测到 headless 模式，自动开始录制当前 Episode。")
        UIState.reset_episode_flags()
        return True

    logger.info("*" * 50)
    logger.info("等待中: 请按下 [Enter] 键开始录制当前 Episode。")
    logger.info("随时可按 [Q] 键退出整个程序。")
    logger.info("*" * 50)
    
    UIState.reset_episode_flags()
    
    while not ui_state.start_recording and not ui_state.quit_program:
        teleop.sync_to_robot(robot)
        robot.step(render=True)
        time.sleep(0.01)

    if ui_state.quit_program:
        return False
    return True

def record_episode(
    teleop: WalkerS2KeyboardTeleop,
    robot: WalkerS2sim,
    dataset: LeRobotDataset,
    task_description: str,
    fps: int,
    episode_time_s: float,
) -> str:
    """
    录制一个 episode。
    Returns 状态字符串: "success", "redo", "quit"
    """
    dt = 1.0 / fps
    max_steps = int(episode_time_s * fps)
    step_count = 0

    UIState.reset_episode_flags()

    logger.info(f"开始录制（最多 {max_steps} 步 / {episode_time_s:.0f}s）")
    # 更新了终端打印的操作提示
    logger.info("操作提示: [方向键右 ->]->保存并进入下一集 | [方向键左 <-]->重新录制本集 | [Q]->退出程序")

    while step_count < max_steps:
        t_start = time.perf_counter()

        if ui_state.quit_program:
            logger.info("检测到退出信号 [Q]，准备退出程序。")
            return "quit"
        if ui_state.redo_episode:
            ui_state.redo_episode = False
            logger.warning("检测到 [方向键左 <-]，丢弃当前数据，重新录制本集！")
            return "redo"
        if ui_state.end_episode_early:
            ui_state.end_episode_early = False
            if step_count == 0:
                # 首帧前按下右键时，避免生成空 episode 导致 save_episode 报错
                logger.warning("检测到 [方向键右 ->]，但当前 Episode 尚未采集任何帧，忽略本次结束请求。")
            else:
                logger.info("检测到 [方向键右 ->]，提前结束并保存当前 Episode。")
                return "success"
        if teleop._pressed_keys.get("quit", False):
            return "quit"

        teleop.sync_to_robot(robot)
        
        # 1. 获取 Action
        record_action = robot.send_action(None)
        if isinstance(record_action, torch.Tensor):
            record_action = record_action.to(torch.float32)
        else:
            record_action = torch.tensor(record_action, dtype=torch.float32)

        # 2. 仿真步进
        robot.step(render=True)
        
        # 3. 获取 Observation
        obs = robot.get_observation()
        # 强制转换 obs 中的所有浮点数组
        processed_obs = {}
        for k, v in obs.items():
            if isinstance(v, torch.Tensor):
                processed_obs[k] = v.to(dtype=torch.float32)
            else:
                processed_obs[k] = torch.tensor(v, dtype=torch.float32)
                
        # 每秒打印 1 次，防止刷屏，便于比对数据
        if step_count % fps == 0:
            logger.info(f"--- 录制中 | 第 {step_count} 帧 ---")
            action_list = [round(x, 3) for x in record_action.tolist()]
            logger.info(f"Action (20维): {action_list}")
            
            if "observation.state" in obs:
                obs_list = [round(x, 3) for x in obs["observation.state"].tolist()]
                logger.info(f"observation State (20维): {obs_list}")

        frame_data = {
            "action": record_action,
            "task": task_description,
            **obs,
        }
        dataset.add_frame(frame_data)

        # 维持目标帧率
        elapsed = time.perf_counter() - t_start
        if elapsed < dt:
            time.sleep(dt - elapsed)

        step_count += 1

    logger.info("时间到，当前 Episode 录制完成。")
    return "success"

def main():
    args = parse_args()

    robot_cfg = WalkerS2Config(task_cfg_path=args.task_cfg, headless=args.headless)
    robot = WalkerS2sim(robot_cfg)
    teleop_cfg = WalkerS2KeyboardTeleopConfig(speed_levels=[0.015, 0.035, 0.05], default_speed_index=1)
    main.teleop = WalkerS2KeyboardTeleop(teleop_cfg)

    # 启动键盘监听器，去掉了鼠标监听器
    k_listener = keyboard.Listener(on_press=on_key_press, on_release=on_key_release)
    k_listener.start()

    dataset = None
    final_save_path = Path(args.save_path)

    try:
        logger.info("正在连接机器人...")
        robot.connect()
        logger.info("正在连接键盘遥操作器...")
        main.teleop.connect()

        dataset_features = {}
        dataset_features.update(robot.observation_features)
        dataset_features.update(robot.action_features)

        save_path, use_resume = resolve_dataset_target(args)
        final_save_path = save_path
        mode_text = "续录" if use_resume else "新建"
        logger.info(f"数据集策略: {args.dataset_mode}，当前模式: {mode_text}，保存路径: {save_path}")

        if use_resume and save_path.exists():
            dataset = LeRobotDataset(repo_id=args.repo_id, root=save_path)
            # 兼容恢复录制时的图片写入器
            if hasattr(robot, "cameras") and len(robot.cameras) > 0:
                dataset.start_image_writer(num_processes=0, num_threads=4 * len(robot.cameras))
        else:
            dataset = LeRobotDataset.create(
                repo_id=args.repo_id,
                root=save_path,
                fps=args.fps,
                robot_type="walker_s2_sim",
                features=dataset_features,
                use_videos=True,
                vcodec=args.vcodec,
                image_writer_processes=0,
                image_writer_threads=4 * len(robot.cameras),
            )

        logger.info(f"开始采集 {args.num_episodes} 个 episodes，保存路径: {save_path}")

        episode_idx = 0
        
        with VideoEncodingManager(dataset):
            while episode_idx < args.num_episodes:
                logger.info(f"\n========== Episode {episode_idx + 1}/{args.num_episodes} ==========")

                if not wait_for_start_signal(main.teleop, robot, auto_start=args.headless):
                    break 

                status = record_episode(
                    teleop=main.teleop,
                    robot=robot,
                    dataset=dataset,
                    task_description=args.task,
                    fps=args.fps,
                    episode_time_s=args.episode_time_s,
                )

                if status == "quit":
                    break
                elif status == "redo":
                    dataset.clear_episode_buffer()
                    logger.info("正在重置场景以备重新采集...")
                    robot.reset()
                    continue 
                elif status == "success":
                    try:
                        dataset.save_episode()
                    except ValueError as e:
                        if "add one or several frames" in str(e):
                            logger.warning("当前 Episode 没有有效帧，已跳过保存并保持在当前 Episode。请先操作机器人再按右键结束。")
                            dataset.clear_episode_buffer()
                            robot.reset()
                            continue
                        raise

                    episode_idx += 1
                    logger.info(f"Episode {episode_idx} 已成功保存到缓冲区 (累计 {len(dataset)} 帧)")
                    
                    if episode_idx < args.num_episodes:
                        logger.info("正在重置场景，准备下一集...")
                        robot.reset()

    except KeyboardInterrupt:
        logger.info("收到 Ctrl+C，正在退出...")
    except Exception as e:
        logger.error(f"发生错误: {e}", exc_info=True)
    finally:
        logger.info("正在关闭系统并保存数据...")
        k_listener.stop()
        
        if dataset is not None:
            logger.info("正在执行 dataset.finalize() 闭合 Parquet 文件并写入元数据...")
            try:
                dataset.finalize()
                logger.info("数据集元数据合并完成！Parquet 文件安全！")
            except Exception as e:
                logger.error(f"关闭数据集时出错: {e}")

        try:
            main.teleop.disconnect()
            robot.disconnect()
        except Exception:
            pass
        logger.info(f"数据采集结束！数据集最终位置: {final_save_path}")

if __name__ == "__main__":
    main()
