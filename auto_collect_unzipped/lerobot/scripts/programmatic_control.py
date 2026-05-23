#!/usr/bin/env python
"""
Task1 编程控制脚本 - 自主抓取与放置

使用方法:
    /isaac-sim/python.sh lerobot/scripts/programmatic_control.py \
        --robot.type=walker_s2_sim \
        --control.type=programmatic \
        --control.task=Part_Sorting

功能:
    - 通过编程方式控制机器人完成Task1（零件抓取-放置）任务
    - 不需要遥操作键盘输入
    - 预设动作序列：接近 -> 下移 -> 夹取 -> 抬起 -> 移动到箱子 -> 放置
"""

import logging
import random
import time
import numpy as np
import torch
from dataclasses import asdict
from pathlib import Path
from lerobot.common.robot_devices.robots.utils import make_robot_from_config
from lerobot.common.robot_devices.control_configs import ProgrammaticControlConfig
from lerobot.common.robot_devices.control_utils import (
    warmup_record, 
    log_timing_summary,
    sanity_check_dataset_robot_compatibility,
    sanity_check_dataset_name,
)
from lerobot.common.datasets.lerobot_dataset import LeRobotDataset
from lerobot.configs import parser


def get_part_type(part: dict, scene_builder) -> str:
    """
    通过 prim_path 判断零件类型 (Part A 或 Part B)
    
    Args:
        part: 零件信息字典，包含 'prim_path' 等字段
        scene_builder: SceneBuilder 实例，用于获取零件列表配置
    
    Returns:
        "part_a" 或 "part_b"
    """
    prim_path = part.get('prim_path', '')
    
    # 方式1: Task2 的路径前缀 /Root/Part_A_ 或 /Root/Part_B_
    if 'Part_A_' in prim_path or 'part_a_' in prim_path:
        return 'part_a'
    if 'Part_B_' in prim_path or 'part_b_' in prim_path:
        return 'part_b'
    
    # 方式2: Task1 通过 prim_path 在 parts_prim_paths 中的索引判断
    #   parts_prim_paths[0..num_a-1] = Part A, parts_prim_paths[num_a..] = Part B
    if scene_builder is not None and hasattr(scene_builder, 'parts_prim_paths'):
        parts_prim_paths = scene_builder.parts_prim_paths
        if prim_path in parts_prim_paths:
            idx = parts_prim_paths.index(prim_path)
            num_parts_per_type = scene_builder.part_cfg.get('num_parts', 2)
            if idx < num_parts_per_type:
                return 'part_a'
            else:
                return 'part_b'
    
    # 默认返回
    logging.warning(f"无法判断零件类型: {prim_path}，默认为 part_b")
    return 'part_b'


def quaternion_to_rpy(quat_xyzw):
    """
    将四元数 [x, y, z, w] 转换为 RPY (roll, pitch, yaw)
    返回单位：弧度 (radians)
    """

    x, y, z, w = quat_xyzw
    # 1. 计算 Roll (X轴旋转)
    sinr_cosp = 2 * (w * x + y * z)
    cosr_cosp = 1 - 2 * (x * x + y * y)
    roll = np.arctan2(sinr_cosp, cosr_cosp)

    # 2. 计算 Pitch (Y轴旋转)
    sinp = 2 * (w * y - z * x)
    
    # 处理万向节死锁 (Gimbal Lock)
    if abs(sinp) >= 1:
        # 如果 Pitch 接近 ±90度 (±π/2)，使用 copysign 确保符号正确
        pitch = np.copysign(np.pi / 2, sinp) 
    else:
        pitch = np.arcsin(sinp)

    # 3. 计算 Yaw (Z轴旋转)
    siny_cosp = 2 * (w * z + x * y)
    cosy_cosp = 1 - 2 * (y * y + z * z)
    yaw = np.arctan2(siny_cosp, cosy_cosp)

    return roll, pitch, yaw


def gradually_move_gripper(robot, side: str, target: float, steps: int = 30,
                           dataset=None, single_task=None):
    """
    逐步移动夹爪到目标位置（模拟遥操的平滑运动）
    
    Args:
        robot: 机器人实例
        side: "left" 或 "right"
        target: 1.0=张开, -1.0=闭合
        steps: 步数
        dataset: 可选，数据集实例，用于录制数据
        single_task: 可选，任务描述
    """
    gripper_step = 0.01
    g_open = robot._robot_interface.gripper_open_width
    g_close = robot._robot_interface.gripper_close_width
    g_lo, g_hi = min(g_open, g_close), max(g_open, g_close)
    
    if side == "left":
        indices = slice(0, 2)
        gripping_attr = "_left_gripping"
    else:
        indices = slice(2, 4)
        gripping_attr = "_right_gripping"
    
    # 获取当前关节位置作为 20维 action (14arm + 4finger + 2gripper)
    action_20d = np.zeros(20, dtype=np.float32)
    if robot._hold_arm_positions is not None:
        action_20d[:14] = robot._hold_arm_positions
    if robot._hold_finger_positions is not None:
        action_20d[14:18] = robot._hold_finger_positions
    # 夹爪控制指令
    action_20d[18] = 1.0 if getattr(robot, '_left_gripping', False) else -1.0
    action_20d[19] = 1.0 if getattr(robot, '_right_gripping', False) else -1.0
    action_tensor = torch.tensor(action_20d, dtype=torch.float32)
    
    for _ in range(steps):
        current = robot._hold_finger_positions[indices]
        delta = target * gripper_step
        robot._hold_finger_positions[indices] = np.clip(current + delta, g_lo, g_hi)
        setattr(robot, gripping_attr, target > 0)
        robot.step(render=True)
        
        # 如果启用了录制，则记录当前帧
        if dataset is not None:
            observation = robot.get_observation()
            frame = {**observation, "action": action_tensor, "task": single_task}
            dataset.add_frame(frame)


def compute_grasp_poses(part_pos: np.ndarray) -> dict:
        """
        计算右手抓取序列中各个阶段的末端执行器目标位姿
        
        Args:
            part_pos: 零件的世界坐标 [x, y, z]
            
        Returns:
            dict: 包含各阶段目标位姿的字典
        """
        # 右手抓取位置
        target_grasp_pos = part_pos["position"]
        target_grasp_rotation=np.array(quaternion_to_rpy(part_pos["orientation"]))
        
        # 接近位姿：从上方接近零件
        approach_pose = {
            'position': np.array([target_grasp_pos[0], target_grasp_pos[1],target_grasp_pos[2] + 0.25]),  # 从上方15cm处接近
            'rotation': target_grasp_rotation  
        }
        
        # 下降到位姿：接近零件表面
        descend_pose = {
            'position': np.array([target_grasp_pos[0], target_grasp_pos[1], target_grasp_pos[2]+0.1]),
            'rotation': target_grasp_rotation
        }
        
        # 抓取位姿：实际抓取零件
        grasp_pose = {
            'position': np.array([target_grasp_pos[0], target_grasp_pos[1], target_grasp_pos[2]+0.01]),
            'rotation': target_grasp_rotation
        }

        lift_pose = {
            'position': np.array([target_grasp_pos[0], target_grasp_pos[1], target_grasp_pos[2]+0.2]),
            'rotation': target_grasp_rotation
        }
        
        
        return {
            'approach': approach_pose,
            'descend': descend_pose,
            'grasp': grasp_pose,
            'lift': lift_pose
        }


def check_grasp_success(robot, part_prim_path: str, threshold: float = 0.05) -> bool:
    """
    检查抓取是否成功：通过比较零件位置和抓夹位置的偏差
    
    Args:
        robot: 机器人实例
        part_prim_path: 零件的 prim_path
        threshold: 距离阈值（米），超过此距离认为抓取失败
    
    Returns:
        True: 抓取成功（零件被夹爪抓住，距离较近）
        False: 抓取失败（零件未被抓起）
    """
    # 获取夹爪（末端执行器）位置
    ee_poses = robot._robot_interface.get_ee_poses()
    if ee_poses is None:
        logging.warning("无法获取末端执行器位姿")
        return False
    
    # 获取右手末端执行器位置
    right_ee = ee_poses.get("right")
    if right_ee is None:
        # 尝试获取第一个可用的末端执行器
        right_ee = ee_poses.get(list(ee_poses.keys())[0])
    if right_ee is None:
        logging.warning("无法获取右手末端执行器位姿")
        return False
    
    gripper_pos = np.array(right_ee[:3])  # [x, y, z]
    
    # 获取零件当前位置
    parts = robot.get_parts_positions()
    part_pos = None
    for p in parts:
        if p.get('prim_path') == part_prim_path:
            part_pos = np.array(p.get('position', [0, 0, 0]))
            break
    
    if part_pos is None:
        logging.warning(f"找不到零件: {part_prim_path}")
        return False
    part_pos=robot._scene_builder.world_to_robot_coords(part_pos)
    # 计算距离偏差
    distance = np.linalg.norm(gripper_pos - part_pos)

    logging.info(f"抓取检测: 零件位置={part_pos}, 夹爪位置={gripper_pos}, 距离={distance:.4f}m")
    
    if distance > threshold:
        logging.warning(f"抓取失败! 零件与夹爪距离 {distance:.4f}m 超过阈值 {threshold}m")
        return False
    
    logging.info(f"抓取成功! 零件与夹爪距离 {distance:.4f}m < {threshold}m")
    return True


def _interpolate_to_pose(robot, target_pose: dict, dt: float, duration: float, 
                         dataset=None, single_task=None):
    """
    平滑移动到目标位姿（使用 joint_interpolator 进行关节插值）
    
    Args:
        robot: 机器人实例
        target_pose: 目标位姿
        dt: 控制周期
        duration: 移动持续时间
        dataset: 可选，数据集实例，用于录制数据
        single_task: 可选，任务描述
    """
    import torch
    
    # 1. 获取当前末端执行器位姿
    ee_poses = robot._robot_interface.get_ee_poses()
    if ee_poses is None:
        logging.warning("无法获取末端执行器位姿")
        return
    
    # 2. 计算目标位姿
    target_pos = target_pose['position']
    target_rpy = target_pose['rotation']
    
    target_6d = np.array([
        target_pos[0], target_pos[1], target_pos[2],
        target_rpy[0], target_rpy[1], target_rpy[2]
    ], dtype=np.float32)
    
    logging.info(f"目标位姿: {target_6d}")
    # 3. 使用IK计算目标关节位置
    ik_result = robot._robot_interface.control_dual_arm_ik(
        step_size=0.02,
        left_target_xyzrpy=None,  # 左手保持不动
        right_target_xyzrpy=target_6d,  # 右手移动
    )
    
    if ik_result is None:
        logging.warning("IK求解失败")
        return
    logging.info(f"IK求解结果: {ik_result}")
    
    # 4. 获取目标关节位置
    target_joints_14d = np.zeros(14, dtype=np.float32)
    if robot._hold_arm_positions is not None:
        target_joints_14d[:14] = robot._hold_arm_positions.copy()
    else:
        target_joints_14d[:14]=robot._robot_interface.initial_joint_positions[:14]
    
    smoothed = ik_result.get('right_joint_positions', [])
    if len(smoothed) == 14:
        target_joints_14d = np.array(smoothed[:14], dtype=np.float32)
    elif len(smoothed) == 7:
        target_joints_14d[7:14] = np.array(smoothed, dtype=np.float32)
    
    # 获取手臂和手指的关节索引
    arm_finger_indices = (
        robot._robot_interface.arm_joint_indices + 
        robot._robot_interface.finger_joint_indices
    )
    
    
    # 目标关节位置 = 14个手臂关节 + 4个手指关节

    target_positions = np.concatenate([target_joints_14d, np.zeros(4)])
    # 获取手指当前位置
    finger_states = robot._robot_interface.get_joint_states()
    if finger_states:
        finger_positions = np.array(finger_states['finger_positions'])
        target_positions[14:18] = finger_positions
    
    
    # 6. 计算插值步数
    steps = int(duration / dt)
    logging.info(f"插值步数: {steps}")
    
    # 7. 设置关节插值器
    arm_finger_indices = robot._robot_interface.arm_joint_indices + robot._robot_interface.finger_joint_indices
    robot._robot_interface.joint_interpolator.set_target(
                start_q=torch.tensor(robot._robot_interface.get_joint_states()['all_positions'])[arm_finger_indices],
                target_q=torch.tensor(target_positions),
                num_steps=steps
            )
    
    for _ in range(steps):
        arm_finger_positions = robot._robot_interface.joint_interpolator.step()  # 执行一步插值
        if isinstance(arm_finger_positions, torch.Tensor):
            arm_finger_positions = arm_finger_positions.detach().cpu().numpy()
        else:
            arm_finger_positions = np.asarray(arm_finger_positions, dtype=np.float32)
        robot._hold_arm_positions = arm_finger_positions[:14]
        robot._hold_finger_positions = arm_finger_positions[14:18]
        robot.step(render=True)
        
        
        # 如果启用了录制，则记录当前帧
        if dataset is not None:
            observation = robot.get_observation()
            frame = {**observation, "action": robot.get_current_action(), "task": single_task}
            dataset.add_frame(frame)
    
    logging.info("关节插值移动完成")

def run_programmatic_control(robot, cfg: ProgrammaticControlConfig):
    """
    运行编程控制模式
    
    正确流程（使用 MobileManipulator 的 send_action + step 模式）：
    1. execute_action() - 更新 pending 动作
    2. step() - 触发 world.step()，callback 自动执行动作
    3. get_observation() - 获取观测（可选）
    
    Args:
        robot: 机器人实例
        cfg: 控制配置
    """
    logging.info("=" * 60)
    logging.info("进入编程控制模式 - Task1 自主抓取")
    logging.info("=" * 60)
    
    # 初始化数据集（如果启用录制）
    dataset = None
    if cfg.record_data:
        logging.info("=" * 60)
        logging.info("录制模式已启用！")
        logging.info("=" * 60)
        
        # 处理 root 参数
        root = cfg.root
        if root is None:
            # 默认使用当前目录下的 outputs 目录
            root = Path("./outputs/autonomous_grasp")
        elif isinstance(root, str):
            root = Path(root)
        
        if cfg.resume:
            # 加载已有数据集
            dataset = LeRobotDataset(
                cfg.repo_id,
                root=root,
            )
            if len(robot.cameras) > 0:
                logging.info("启动图像写入器...")
                dataset.start_image_writer(
                    num_processes=cfg.num_image_writer_processes,
                    num_threads=cfg.num_image_writer_threads_per_camera * len(robot.cameras),
                )
            sanity_check_dataset_robot_compatibility(dataset, robot, cfg.fps, cfg.video)
        else:
            # 创建新数据集
            sanity_check_dataset_name(cfg.repo_id, None)
            dataset = LeRobotDataset.create(
                cfg.repo_id,
                cfg.fps,
                root=root,
                robot=robot,
                use_videos=cfg.video,
                image_writer_processes=cfg.num_image_writer_processes,
                image_writer_threads=cfg.num_image_writer_threads_per_camera * len(robot.cameras),
            )
        logging.info(f"数据集: {cfg.repo_id}")
        logging.info(f"数据存储路径: {root}")
        logging.info(f"每 episode 将录制: {cfg.single_task}")
    
    # 连接机器人
    if not robot.is_connected:
        robot.connect()
        logging.info("机器人连接成功")
    
    # 等待物理稳定
    logging.info("等待物理稳定...")
    settle_steps = int(2.0 / (1.0 / cfg.fps))
    for _ in range(settle_steps):
        robot.step(render=True)
    
    # 获取零件位置
    parts = robot.get_parts_positions()
    if not parts:
        logging.error("未找到零件！")
        return
    
    logging.info(f"找到 {len(parts)} 个零件")
    for i, p in enumerate(parts):
        logging.info(f"  零件{i}: {p.get('prim_path', 'unknown')}, 位置: {p.get('position')}")
    
    # 获取箱子位置
    box_pos = robot.get_box_position()
    if box_pos is None:
        box_pos = np.array([1.2, 0.3, 1.05])
    logging.info(f"箱子位置: {box_pos}")
    
    dt = 1.0 / cfg.fps

    logging.info(f"基座变换矩阵: {robot._scene_builder.get_robot_world_transform()}")
    
    # ====== 外层 Episode 循环 ======#
    total_episodes = cfg.num_episodes if cfg.record_data else 1
    for episode_idx in range(total_episodes):
        if cfg.record_data:
            logging.info("=" * 60)
            logging.info(f"开始录制 Episode {episode_idx + 1}/{total_episodes}")
            logging.info(f"当前已录制: {dataset.num_episodes} episodes")
            logging.info("=" * 60)
        
        # 记录当前 episode 是否成功完成
        episode_success = False
        max_retries = 10  # 最大重试次数
        retry_count = 0
        
        try:
            while not episode_success and retry_count < max_retries:
                retry_count += 1
                if retry_count > 1:
                    logging.info("=" * 60)
                    logging.info(f"重新开始 Episode {episode_idx + 1} (第 {retry_count} 次尝试)")
                    logging.info("=" * 60)
                
                 # 松开夹爪
                gradually_move_gripper(robot, "right", -1.0, steps=30)
                        
                # 重置场景，重新开始整个 episode
                logging.info("重置场景...")
                robot.reset()
                
                # 重置录制数据集的 episode 缓冲
                if dataset is not None:
                    logging.info("重置录制数据集...")
                    dataset.clear_episode_buffer()


                # 重新获取零件位置
                parts = robot.get_parts_positions()
                if not parts:
                    logging.error("未找到零件！")
                    break

                # 随机打乱零件顺序
                random.shuffle(parts)

                first_part = True
                all_parts_success = True
                completed_objects = 0

                for part_idx, part in enumerate(parts):
                    grasp_poses = compute_grasp_poses(part_pos=part)
                    logging.info(f"\n处理零件 {part_idx + 1}/{len(parts)}")
                    
                    # ====== 阶段1: 接近零件 ======
                    logging.info("阶段1: 接近目标...")
                    dst_pose=grasp_poses["approach"]
                    logging.info(f"世界坐标系目标位置:{dst_pose}")
                    dst_pose["position"]=robot._scene_builder.world_to_robot_coords(dst_pose["position"])
                    dst_pose["rotation"]=np.array([-np.pi, 0.0, -1.9])
                    logging.info(f"机器人坐标系目标位置:{dst_pose}")
                    if first_part:
                        _interpolate_to_pose(robot,dst_pose , dt, 1, dataset, cfg.single_task)
                        first_part=False
                    else:
                        _interpolate_to_pose(robot,dst_pose , dt, 1, dataset, cfg.single_task)
                    
                    # =======阶段2 松开抓夹 ====#
                    logging.info("阶段2: 松开右手夹爪...")
                    gradually_move_gripper(robot, "right", -1.0, steps=2, dataset=dataset, single_task=cfg.single_task)  # 逐步张开右手

                    # ======阶段3  手臂下降 ======#
                    logging.info("阶段3: 手臂下降...")
                    dst_pose=grasp_poses["descend"]
                    logging.info(f"世界坐标系目标位置:{dst_pose}")
                    dst_pose["position"]=robot._scene_builder.world_to_robot_coords(dst_pose["position"])
                    dst_pose["rotation"]=np.array([-np.pi, -0.4,-1.9])
                    logging.info(f"机器人坐标系目标位置:{dst_pose}")
                    _interpolate_to_pose(robot,dst_pose , dt, 1, dataset, cfg.single_task)
                    dst_pose=grasp_poses["grasp"]
                    logging.info(f"世界坐标系目标位置:{dst_pose}")
                    dst_pose["position"]=robot._scene_builder.world_to_robot_coords(dst_pose["position"])
                    logging.info(f"机器人坐标系目标位置:{dst_pose}")
                    dst_pose["rotation"]=np.array([-np.pi, -0.55,-1.9])
                    logging.info(f"机器人坐标系目标位置:{dst_pose}")
                    _interpolate_to_pose(robot,dst_pose , dt, 1, dataset, cfg.single_task)
                    logging.info("阶段4: 闭合右手夹爪...")
                    gradually_move_gripper(robot, "right", 1.0, steps=5, dataset=dataset, single_task=cfg.single_task)  # 逐步闭合

                    # #==========阶段5 抬起 手臂=======#
                    logging.info("阶段5: 抬起手臂...")
                    dst_pose=grasp_poses["lift"]
                    logging.info(f"世界坐标系目标位置:{dst_pose}")
                    dst_pose["position"]=robot._scene_builder.world_to_robot_coords(dst_pose["position"])
                    dst_pose["rotation"]=np.array([-np.pi, -0.2, -1.9])
                    logging.info(f"机器人坐标系目标位置:{dst_pose}")
                    _interpolate_to_pose(robot,dst_pose , dt, 1.5, dataset, cfg.single_task)

                    # =======阶段6  移动到箱子（按类型分开放置）=======#    
                    logging.info("阶段6: 移动到箱子...")

                    # 根据零件类型选择放置位置偏移
                    part_type = get_part_type(part, robot._scene_builder)
                    if part_type == 'part_a':
                        place_offset = np.array([0 , -0.08, 0.18])      # Part A 放箱子右侧
                        logging.info("  → 检测到 Part A，放置偏移 +Y")
                    else:
                        place_offset = np.array([0, 0.06, 0.18])     # Part B 放箱子左侧
                        logging.info("  → 检测到 Part B，放置偏移 -Y")

                    logging.info(f"世界坐标系目标位置: {box_pos} + {place_offset}")
                    dst_pose["position"]=robot._scene_builder.world_to_robot_coords(box_pos + place_offset)
                    dst_pose["rotation"]=np.array([-np.pi, -0.2, -2.8])
                    logging.info(f"机器人坐标系目标位置:{dst_pose}")
                    _interpolate_to_pose(robot,dst_pose , dt, 1.5, dataset, cfg.single_task)

                    # ====== 检测抓取是否成功 ======#
                    logging.info("检测抓取是否成功...")
                    grasp_success = check_grasp_success(robot, part.get('prim_path', ''), threshold=0.08)
                    
                    if not grasp_success:
                        logging.error("=" * 60)
                        logging.error("抓取失败！零件位置与夹爪位置偏差过大！")
                        logging.error("=" * 60)
                        
                        
                        all_parts_success = False
                        break  # 跳出零件循环，重新开始整个 episode

                    logging.info("阶段7: 松开右手夹爪...")
                    gradually_move_gripper(robot, "right", -1.0, steps=5, dataset=dataset, single_task=cfg.single_task)  # 逐步张开右手
                    
                    logging.info(f"零件 {part_idx + 1} 处理完成")
                    completed_objects += 1
                    if cfg.objects_per_episode > 0 and completed_objects >= cfg.objects_per_episode:
                        logging.info(f"已达到本 episode 目标物体数 ({cfg.objects_per_episode})")
                        break
                
                # 检查是否所有零件都成功处理
                if all_parts_success:
                    episode_success = True
            
            # 检查是否因为重试次数过多而退出
            if retry_count >= max_retries and not episode_success:
                logging.error(f"重试次数超过上限 ({max_retries})，跳过当前 episode")
            
            if episode_success:
                logging.info(f"\n所有 {len(parts)} 个零件处理完成！")
                
                # ====== 保存 Episode ======#
                if cfg.record_data and dataset is not None:
                    dataset.save_episode()
                    logging.info(f"Episode {episode_idx + 1} 已保存！当前总 episode 数: {dataset.num_episodes}")
        
        except KeyboardInterrupt:
            logging.info("用户中断执行")
            break
        except Exception as e:
            logging.error(f"执行出错: {e}")
            import traceback
            traceback.print_exc()

    # Push to Hub after all episodes are done
    if cfg.record_data and dataset is not None and cfg.push_to_hub:
        logging.info(f"推送数据集到 Hugging Face Hub: {cfg.repo_id}")
        if cfg.path_in_repo:
            logging.info(f"  → 目标子目录: {cfg.path_in_repo}")
        dataset.push_to_hub(
            tags=cfg.tags if hasattr(cfg, 'tags') else None,
            private=getattr(cfg, 'private', False),
            path_in_repo=cfg.path_in_repo,
        )
        logging.info("数据集推送完成！")


@parser.wrap()
def programmatic_control(cfg: ProgrammaticControlConfig):
    """
    编程控制入口函数
    
    使用方式:
        /isaac-sim/python.sh lerobot/scripts/programmatic_control.py \
            --robot.type=walker_s2_sim \
            --control.type=programmatic \
            --control.task=Part_Sorting
    """
    # 初始化日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # 创建机器人
    robot = make_robot_from_config(cfg.robot)
    
    # 加载Task配置
    if robot.robot_type == "walker_s2_sim" and hasattr(robot, "config"):
        task = getattr(cfg.control, "task", "Part_Sorting")
        robot.config.load_from_yaml(task)
        logging.info(f"[WalkerS2Sim] 使用任务: {task}")
        logging.info(f"[WalkerS2Sim] 配置路径: {robot.config.task_cfg_path}")
    
    # 运行编程控制
    run_programmatic_control(robot, cfg.control)
    
    # 断开连接
    if robot.is_connected:
        robot.disconnect()
        logging.info("机器人已断开连接")


if __name__ == "__main__":
    programmatic_control()
