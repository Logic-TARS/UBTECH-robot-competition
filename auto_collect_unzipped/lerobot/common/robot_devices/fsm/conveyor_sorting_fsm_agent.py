"""Agent wrapper for ConveyorSortingFSM.

Drives the conveyor sorting FSM each physics step, handling part spawning,
state queries, and target computation.
"""

import logging
from typing import Optional

import numpy as np

from .conveyor_sorting_fsm import ConveyorSortingFSM

logger = logging.getLogger(__name__)


class ConveyorSortingFSMAgent:
    """Agent that drives a :class:`ConveyorSortingFSM` each physics step.
    
    Responsibilities:
    1. Manage ConveyorPartSpawner lifecycle (spawn parts dynamically)
    2. Query current EE poses from robot interface
    3. Query current part world positions from SceneBuilder
    4. Call ``fsm.step()`` and return targets / gripper commands
    5. Manage FSM lifecycle (start, reset, pause/resume)
    
    Args:
        fsm: Initialized :class:`ConveyorSortingFSM` instance
        scene_builder: SceneBuilder instance (has ``get_parts_world_poses()``)
        robot_interface: IsaacSimRobotInterface instance (has ``get_ee_poses()``)
        spawner: ConveyorPartSpawner instance for dynamic part spawning
    """
    
    def __init__(self, fsm: ConveyorSortingFSM, scene_builder, robot_interface, spawner):
        self._fsm = fsm
        self._scene_builder = scene_builder
        self._robot_interface = robot_interface
        self._spawner = spawner
        
        # Lazy-start: FSM stays IDLE until resume() is called
        self._paused: bool = True
        self._started: bool = False
    
    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    
    def start(self) -> None:
        """Start the FSM and spawner."""
        if self._started:
            return
        
        # Determine number of parts from config
        num_parts = getattr(self._fsm, '_total_parts', 8)
        
        # Set gripper widths from robot interface
        self._fsm.gripper_open_width = getattr(
            self._robot_interface, "gripper_open_width", -0.0215
        )
        self._fsm.gripper_close_width = getattr(
            self._robot_interface, "gripper_close_width", 0.01
        )
        
        self._fsm.start(num_parts=num_parts)
        self._started = True
        self._paused = False
        
        # Start spawner
        self._spawner.reset()
        
        logger.info(f"[ConveyorFSMAgent] Started with {num_parts} parts")
    
    def pause(self) -> None:
        """Pause the FSM."""
        self._paused = True
    
    def resume(self) -> None:
        """Resume the FSM, auto-starting if not yet started."""
        self._paused = False
        if not self._started:
            self.start()
    
    def reset(self) -> None:
        """Reset the FSM and spawner for a new episode."""
        self._fsm.reset()
        self._spawner.reset()
        self._started = False
        self._paused = True
        logger.info("[ConveyorFSMAgent] Reset complete")
    
    # ------------------------------------------------------------------
    # Per-step interface
    # ------------------------------------------------------------------
    
    def step(self) -> tuple[
        Optional[np.ndarray],  # left_target_xyzrpy
        Optional[np.ndarray],  # right_target_xyzrpy
        float,                 # left_gripper_cmd
        float,                 # right_gripper_cmd
        bool,                  # is_done
    ]:
        """Called from ``_robot_control_callback`` each physics step.
        
        Returns:
            (left_target, right_target, left_grip, right_grip, is_done)
        """
        if self._paused or not self._started:
            return None, None, 0.0, 0.0, False
        
        # Update spawner (check if need to spawn new part)
        try:
            self._spawner.update()
        except Exception as e:
            logger.error(f"[ConveyorFSMAgent] Spawner update failed: {e}")
        
        # Query current state
        ee_poses = self._query_ee_poses()
        part_poses = self._query_part_poses()
        
        # Query gripper finger position for grasp verification
        gripper_width = self._query_gripper_width()
        if gripper_width is not None:
            self._fsm._gripper_finger_width = gripper_width
        
        # Step FSM
        return self._fsm.step(ee_poses, part_poses)
    
    @property
    def fsm(self) -> ConveyorSortingFSM:
        """Direct access to the underlying FSM."""
        return self._fsm
    
    @property
    def is_task_done(self) -> bool:
        """Whether all parts have been sorted."""
        return self._fsm.is_task_done
    
    @property
    def episode_success(self) -> Optional[bool]:
        """Whether the episode was successful (all parts in correct boxes).
        
        Returns:
            None if not yet evaluated, True if successful, False if needs retry
        """
        return self._fsm.episode_success
    
    @property
    def is_running(self) -> bool:
        """Whether FSM is currently running."""
        return self._started and not self._paused
    
    @property
    def current_state(self) -> str:
        """Current FSM state name."""
        return self._fsm.state.value
    
    @property
    def current_arm(self) -> str:
        """Currently active arm."""
        return self._fsm.current_arm
    
    @property
    def current_part_index(self) -> int:
        """Current part index being processed."""
        return self._fsm.current_part_index
    
    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    
    def _query_ee_poses(self) -> Optional[dict]:
        """Get current end-effector poses from robot interface."""
        try:
            return self._robot_interface.get_ee_poses()
        except Exception as e:
            logger.warning(f"[ConveyorFSMAgent] Failed to get EE poses: {e}")
            return None
    
    def _query_part_poses(self) -> Optional[list]:
        """Get current part world positions from SceneBuilder."""
        try:
            if self._scene_builder is None:
                return None
            get_poses = getattr(self._scene_builder, "get_parts_world_poses", None)
            if callable(get_poses):
                return get_poses()
            return None
        except Exception as e:
            logger.warning(f"[ConveyorFSMAgent] Failed to get part poses: {e}")
            return None
    
    def _query_gripper_width(self) -> Optional[float]:
        """Get current gripper finger width for grasp verification.
        
        Returns:
            Average finger width (m), or None if unavailable
        """
        try:
            states = self._robot_interface.get_joint_states()
            if states and "finger_positions" in states:
                fingers = states["finger_positions"]
                # Return average of all finger positions
                return sum(fingers) / len(fingers)
            return None
        except Exception as e:
            logger.debug(f"[ConveyorFSMAgent] Failed to get gripper width: {e}")
            return None