"""Conveyor belt sorting FSM state machine for Task 2.

Handles dynamic part spawning, moving target tracking, and sorting logic.
Parts are sorted: Part A → left box, Part B → right box.
"""

import enum
import logging
import math
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# FSM states for conveyor sorting
# ---------------------------------------------------------------------------

class ConveyorFSMState(enum.Enum):
    IDLE = "idle"
    WAIT_FOR_PART = "wait_for_part"        # Wait for next part to spawn
    TRACK_PART = "track_part"              # Track moving part, compute intercept
    READY = "ready"                        # Move to ready position
    APPROACH = "approach"                  # Approach part (predictive)
    DESCEND = "descend"                    # Descend to grasp height
    GRASP = "grasp"                        # Close gripper
    VERIFY_GRASP = "verify_grasp"          # Verify part picked up
    LIFT = "lift"                          # Lift part
    SORT_DECIDE = "sort_decide"            # Determine which box (A→left, B→right)
    TRANSPORT = "transport"                # Move to target box
    LOWER = "lower"                        # Lower into box
    RELEASE = "release"                    # Open gripper
    RETREAT = "retreat"                    # Retreat from box
    RETRY = "retry"                        # Retry failed grasp
    DONE = "done"                          # All parts sorted


# ---------------------------------------------------------------------------
# Grasp orientation helper (reused from PickPlaceFSM)
# ---------------------------------------------------------------------------

def compute_grasp_rpy(
    part_pos_base: np.ndarray,
    robot_position_world: np.ndarray,
    forearm_tilt_deg: float = 40.0,
) -> np.ndarray:
    """Compute grasp RPY with forearm tilt for conveyor parts.
    
    Args:
        part_pos_base: Part position in robot base frame [x, y, z]
        robot_position_world: Robot base position in world frame
        forearm_tilt_deg: Forearm tilt angle in degrees
        
    Returns:
        RPY angles [roll, pitch, yaw] in radians
    """
    # Default grasp orientation: gripper pointing down
    # Tilt forearm to avoid collisions
    tilt_rad = math.radians(forearm_tilt_deg)
    
    # Base grasp RPY (gripper down)
    # Roll=0, Pitch=-90° (tilt forward), Yaw depends on part position
    yaw = math.atan2(part_pos_base[1], part_pos_base[0])
    pitch = -math.pi / 2.0 + tilt_rad  # -90° + tilt
    roll = 0.0
    
    return np.array([roll, pitch, yaw], dtype=float)


# ---------------------------------------------------------------------------
# Conveyor Sorting FSM
# ---------------------------------------------------------------------------

class ConveyorSortingFSM:
    """Finite state machine for conveyor belt sorting.
    
    Each call to :meth:`step` returns the current end-effector target and
    gripper command. Handles moving parts, dynamic spawning, and dual-box sorting.
    
    Args:
        config: Robot config object carrying FSM params
        box_positions_world: List of two box positions [left_box, right_box] in world frame
        robot_position_world: Robot base position in world frame [x,y,z]
        robot_rotation_deg: Robot base rotation in degrees [roll, pitch, yaw] (ZYX)
        conveyor_config: Conveyor-specific configuration dict
    """
    
    def __init__(
        self,
        config,
        box_positions_world: list,
        robot_position_world: list | np.ndarray,
        robot_rotation_deg: list | np.ndarray,
        conveyor_config: dict,
        box_scales: list | None = None,
    ):
        # Configuration from config object
        self._config = config
        self._pos_tol = getattr(config, "fsm_pos_tol", 0.03)
        self._approach_height = getattr(config, "fsm_approach_height", 0.20)
        self._descend_height = getattr(config, "fsm_descend_height", 0.02)  # DESCEND state height above part
        self._descend_pos_tol = getattr(config, "fsm_descend_pos_tol", 0.045)
        self._grasp_frames = getattr(config, "fsm_grasp_frames", 25)
        self._release_frames = getattr(config, "fsm_release_frames", 35)
        self._rot_weight = getattr(config, "fsm_rot_weight", 0.1)
        self._max_ee_step = getattr(config, "fsm_max_ee_step", 0.005)
        self._descend_step = getattr(config, "fsm_descend_step", 0.005)
        self._ik_null_weight = getattr(config, "fsm_ik_null_weight", 0.30)
        self._forearm_tilt_deg = getattr(config, "fsm_forearm_tilt_deg", 35.0)

        # Cached grasp RPY. Recomputed once per state entry using the
        # rotation-matrix approach (ported from Part_Sorting). The SAME
        # orientation is used across all states (TRACK_PART/APPROACH/DESCEND/
        # GRASP/LIFT/TRANSPORT/LOWER/RETREAT) so IK has a smooth, reachable
        # target and the forearm does not flare externally.
        self._grasp_rpy: Optional[np.ndarray] = None

        # Expose for caller to pass to IK solver
        self.ik_null_weight = self._ik_null_weight
        
        # Gripper widths (will be set by FSMAgent from robot interface)
        self.gripper_open_width: float = -0.0215
        self.gripper_close_width: float = 0.01
        
        # Box positions (world frame)
        self._box_left_world = np.asarray(box_positions_world[0], dtype=float)   # Part A
        self._box_right_world = np.asarray(box_positions_world[1], dtype=float)  # Part B
        
        # Box scales for computing bounds (world frame)
        self._box_scales = box_scales
        if box_scales is not None and len(box_scales) >= 2:
            self._box_left_scale = np.asarray(box_scales[0], dtype=float)
            self._box_right_scale = np.asarray(box_scales[1], dtype=float)
            # Calculate box bounds
            self._box_left_bounds = self._calculate_box_bounds(self._box_left_world, self._box_left_scale)
            self._box_right_bounds = self._calculate_box_bounds(self._box_right_world, self._box_right_scale)
        else:
            # Default bounds (±0.15m around center)
            self._box_left_bounds = self._calculate_box_bounds(self._box_left_world, np.array([0.3, 0.3, 0.3]))
            self._box_right_bounds = self._calculate_box_bounds(self._box_right_world, np.array([0.3, 0.3, 0.3]))
        
        # Robot configuration
        self._robot_position_world = np.asarray(robot_position_world, dtype=float)
        rot_deg = np.asarray(robot_rotation_deg, dtype=float)
        R_base_to_world = self._euler_zyx_to_rotation_matrix(*rot_deg)
        self._R_world_to_base = R_base_to_world.T
        self._R_base_to_world = R_base_to_world
        
        # Conveyor configuration
        self._conveyor_speed = conveyor_config.get('conveyor_speed', 0.1)
        self._grab_zone_x_min = conveyor_config.get('conveyor_grab_zone_x_min', 0.10)
        self._grab_zone_x_max = conveyor_config.get('conveyor_grab_zone_x_max', 0.60)
        self._total_parts = conveyor_config.get('total_parts_to_sort', 8)
        
        # Internal state
        self._state = ConveyorFSMState.IDLE
        self._current_part_index: int = 0
        self._current_part_type: Optional[str] = None  # 'part_a' or 'part_b'
        self._frame_counter: int = 0
        self._current_arm: str = "right"
        self._current_ee: Optional[dict] = None
        
        # Frozen part position: once gripper closes, freeze the part position
        # This prevents the target from moving during LIFT/TRANSPORT
        self._grasped_part_position: Optional[np.ndarray] = None  # World frame, frozen at grasp
        
        # Cached targets
        self._cached_active_target: Optional[np.ndarray] = None
        self._cached_other_target: Optional[np.ndarray] = None
        self._cached_grip_cmd: float = 0.0
        
        # Part tracking
        self._part_positions_world: list[np.ndarray] = []
        self._part_prim_paths: list[str | None] = []
        self._sorted_part_indices: set = set()
        self._parts_spawned = 0
        self._parts_sorted = 0
        self._sorted_count_a = 0
        self._sorted_count_b = 0
        
        # Grasp verification
        self._gripper_finger_width: Optional[float] = None
        self._grasp_failed_in_verify: bool = False
        self._gripper_close_start_frame: Optional[int] = None
        
        # Retry tracking
        self._failed_parts: dict = {}
        self._max_retries: int = getattr(config, "fsm_max_grasp_retries", 3)
        self._skipped_parts: list = []  # Part indices skipped after max retries
        self._grasp_verify_frames: int = getattr(config, "fsm_grasp_verify_frames", 3)
        self._table_height: float = getattr(config, "fsm_table_height", 1.20)
        self._grasp_depth_offset: float = getattr(config, "fsm_grasp_depth_offset", 0.02)  # sixforce_link height relative to part center
        self._grasp_lookahead_time: float = getattr(config, "fsm_grasp_lookahead_time", 0.20)
        self._grasp_xy_tol: float = getattr(config, "fsm_grasp_xy_tol", 0.015)
        self._grasp_z_tol: float = getattr(config, "fsm_grasp_z_tol", 0.020)
        self._grasp_min_frames: int = getattr(config, "fsm_grasp_min_frames", 10)
        self._grasp_force_close_frames: int = getattr(config, "fsm_grasp_force_close_frames", 0)
        self._gripper_close_settle_frames: int = getattr(config, "fsm_gripper_close_settle_frames", 12)
        self._lift_min_frames: int = getattr(config, "fsm_lift_min_frames", 20)
        
        # State timeout
        self._state_frame_counter: int = 0
        self._state_timeout: int = getattr(config, "fsm_state_timeout_frames", 800)
        
        # Logging
        self._last_logged_state: Optional[ConveyorFSMState] = None
        
        # Episode success tracking
        self._episode_success: Optional[bool] = None  # None = not yet evaluated
        
        logger.info(
            f"[ConveyorFSM] Initialized: {self._total_parts} parts to sort, "
            f"conveyor speed {self._conveyor_speed} m/s, "
            f"grab zone [{self._grab_zone_x_min:.2f}, {self._grab_zone_x_max:.2f}]"
        )
    
    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    
    @property
    def state(self) -> ConveyorFSMState:
        """Current FSM state."""
        return self._state
    
    @property
    def current_arm(self) -> str:
        """Currently active arm."""
        return self._current_arm
    
    @property
    def current_part_index(self) -> int:
        """Current part index being processed."""
        return self._current_part_index
    
    @property
    def is_task_done(self) -> bool:
        """Whether all parts have been sorted."""
        return self._state == ConveyorFSMState.DONE
    
    @property
    def episode_success(self) -> Optional[bool]:
        """Whether the episode was successful (all parts in correct boxes).
        
        Returns:
            None if not yet evaluated, True if successful, False if needs retry
        """
        return self._episode_success
    
    @property
    def ik_rot_weight(self):
        """IK rotation weight (varies by state)."""
        if self._state in [
            ConveyorFSMState.TRACK_PART,
            ConveyorFSMState.READY,
            ConveyorFSMState.APPROACH,
            ConveyorFSMState.DESCEND,
            ConveyorFSMState.GRASP,
            ConveyorFSMState.RETRY,
            ConveyorFSMState.TRANSPORT,
            ConveyorFSMState.LOWER,
            ConveyorFSMState.RETREAT,
        ]:
            return 0.02  # Low rotation weight for position priority
        return self._rot_weight
    
    @property
    def ik_step_size_multiplier(self) -> float:
        """Return step size multiplier based on current state.
        
        TRANSPORT with Part A uses extra-slow speed to prevent the part from
        being flung off the gripper during motion.
        
        RETRY and retry-APPROACH use faster speed to catch up with the moving part.
        """
        # During retry, the arm needs to move faster to catch up with the part
        # that has moved further along the conveyor.
        is_retry = self._failed_parts.get(self._current_part_index, 0) > 0
        
        if self._state == ConveyorFSMState.TRANSPORT:
            if self._current_part_type == 'part_a':
                return 0.08  # 8% for Part A — grip-safe
            return 0.25  # 25% for Part B
        elif self._state == ConveyorFSMState.LIFT:
            # LIFT happens right after gripper clamps — very slow for Part A to
            # avoid flinging the freshly-grasped part upward.
            if self._current_part_type == 'part_a':
                return 0.08  # 8% for Part A — matches TRANSPORT for zero jerk
            return 0.55  # 55% for Part B
        elif self._state in [ConveyorFSMState.LOWER, ConveyorFSMState.RETREAT]:
            return 0.50  # 50% step size
        elif self._state == ConveyorFSMState.RETRY:
            return 1.0  # Full speed to reposition quickly after failed grasp
        elif self._state == ConveyorFSMState.APPROACH:
            return 1.0 if is_retry else 0.70  # Full speed on retry to catch up
        elif self._state == ConveyorFSMState.DESCEND:
            return 1.0 if is_retry else 1.0  # Full speed descent, especially on retry
        return 1.0  # Normal speed for other states
    
    @property
    def fsm_smooth_alpha_override(self) -> Optional[float]:
        """Return smooth_alpha override based on current state.
        
        This is the PRIMARY speed control. Lower alpha = slower/smoother.
        EMA: new_pos = alpha * target + (1 - alpha) * current_pos
        
        TRANSPORT with Part A uses extra-low alpha for gentle motion.
        """
        if self._state == ConveyorFSMState.TRANSPORT:
            if self._current_part_type == 'part_a':
                return 0.04  # 4% per step — smooth for Part A grip safety
            return 0.08  # 8% per step for Part B
        elif self._state == ConveyorFSMState.LIFT:
            # Smooth LIFT for Part A so there's zero jerk from GRASP→LIFT→TRANSPORT.
            if self._current_part_type == 'part_a':
                return 0.04  # 4% per step — same as TRANSPORT for uniform smoothness
            return None  # Default for Part B (faster)
        elif self._state in [ConveyorFSMState.LOWER, ConveyorFSMState.RETREAT]:
            return 0.08  # 8% per step
        return None  # Use default (0.10) for other states
    
    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    
    def start(self, num_parts: int = 8) -> None:
        """Start the FSM (transition from IDLE to WAIT_FOR_PART)."""
        if self._state != ConveyorFSMState.IDLE:
            return
        self._total_parts = num_parts
        self._transition_to(ConveyorFSMState.WAIT_FOR_PART)
        logger.info(f"[ConveyorFSM] Started — {self._total_parts} parts to sort")
    
    def reset(self) -> None:
        """Reset FSM to IDLE for a new episode."""
        self._state = ConveyorFSMState.IDLE
        self._current_part_index = 0
        self._current_part_type = None
        self._current_arm = "right"
        self._frame_counter = 0
        self._state_frame_counter = 0
        self._current_ee = None
        self._cached_active_target = None
        self._cached_other_target = None
        self._cached_grip_cmd = 0.0
        self._part_positions_world = []
        self._part_prim_paths: list[str | None] = []
        self._sorted_part_indices = set()
        self._parts_spawned = 0
        self._parts_sorted = 0
        self._sorted_count_a = 0
        self._sorted_count_b = 0
        self._last_logged_state = None
        self._gripper_finger_width = None
        self._grasp_failed_in_verify = False
        self._gripper_close_start_frame = None
        self._failed_parts = {}
        self._skipped_parts = []  # Reset skipped parts tracking
        self._episode_success = None  # Reset episode success tracking
        logger.info("[ConveyorFSM] Reset to IDLE")
    
    # ------------------------------------------------------------------
    # Main step function
    # ------------------------------------------------------------------
    
    def step(
        self,
        ee_poses: dict[str, np.ndarray] | None,
        part_poses_world: list[dict] | None,
    ) -> tuple[
        Optional[np.ndarray],  # left_target_xyzrpy
        Optional[np.ndarray],  # right_target_xyzrpy
        float,                 # left_gripper_cmd
        float,                 # right_gripper_cmd
        bool,                  # is_done
    ]:
        """Step the FSM forward by one frame.
        
        Args:
            ee_poses: Dict with 'left' and 'right' EE poses in base frame
            part_poses_world: List of part world positions from SceneBuilder
            
        Returns:
            (left_target, right_target, left_grip, right_grip, is_done)
        """
        # Cache EE poses
        self._current_ee = ee_poses
        
        # Update part positions
        if part_poses_world:
            self._part_positions_world = [
                np.asarray(p['position'], dtype=float) for p in part_poses_world
            ]
            self._part_prim_paths = [
                p.get('prim_path') if isinstance(p, dict) else None for p in part_poses_world
            ]
            self._parts_spawned = len(self._part_positions_world)
        
        # Check state transitions
        self._check_transition()
        
        # Compute targets for current state
        left_target, right_target, grip_cmd = self._compute_targets()
        
        # Cache for output
        self._cached_grip_cmd = grip_cmd
        
        # Log state changes
        if self._state != self._last_logged_state:
            logger.info(
                f"[ConveyorFSM] Transition: {self._last_logged_state.value if self._last_logged_state else 'NONE'} "
                f"→ {self._state.value}"
            )
            self._last_logged_state = self._state
        
        is_done = self._state == ConveyorFSMState.DONE
        
        return left_target, right_target, grip_cmd, grip_cmd, is_done
    
    # ------------------------------------------------------------------
    # Target computation
    # ------------------------------------------------------------------
    
    # States that track moving parts on the conveyor — target MUST be
    # recomputed every frame so the arm always chases the latest predicted
    # part position. Using a frozen cached target causes the arm to lag
    # behind the conveyor motion (especially on retry, where the arm starts
    # high and has further to travel).
    _MOVING_TARGET_STATES = frozenset({
        ConveyorFSMState.TRACK_PART,
        ConveyorFSMState.READY,
        ConveyorFSMState.APPROACH,
        ConveyorFSMState.DESCEND,
        ConveyorFSMState.GRASP,
        ConveyorFSMState.RETRY,
    })

    def _compute_targets(self):
        """Compute target poses for current state.
        
        Returns:
            (left_target, right_target, grip_cmd)
        """
        if self._state in [ConveyorFSMState.IDLE, ConveyorFSMState.DONE]:
            return None, None, 0.0
        
        # For states that chase a moving part, ALWAYS recompute to avoid
        # chasing a stale predicted-position that the part has already passed.
        if self._state in self._MOVING_TARGET_STATES:
            self._compute_and_cache_target()
        # Recompute target if not cached
        elif self._cached_active_target is None:
            self._compute_and_cache_target()
        
        # Return targets based on active arm
        if self._current_arm == "right":
            return None, self._cached_active_target, self._cached_grip_cmd
        else:
            return self._cached_active_target, None, self._cached_grip_cmd
    
    def _compute_and_cache_target(self) -> None:
        """Compute and cache target pose for current state."""
        if self._current_ee is None:
            self._cached_active_target = None
            return
        
        current_ee_pose = self._current_ee.get(self._current_arm)
        if current_ee_pose is None:
            self._cached_active_target = None
            return

        # Compute the grasp RPY once per state entry and reuse it across all
        # states (matching Part_Sorting). This fixed, human-like orientation
        # is always IK-reachable because it is defined by a physical tilt of
        # world-down toward the robot body — no per-state yaw/pitch
        # variations that previously caused IK failures and external
        # forearm rotation.
        self._grasp_rpy = self._compute_grasp_rpy()

        if self._state == ConveyorFSMState.WAIT_FOR_PART:
            # Wait in neutral position
            self._cached_active_target = self._neutral_pos()
            # Open gripper while waiting for next part
            self._cached_grip_cmd = -1.0  # Open gripper
            
        elif self._state == ConveyorFSMState.TRACK_PART:
            # Track part, move to ready position above it
            target = self._track_pos()
            if target is not None:
                self._cached_active_target = target
                # Open gripper BEFORE approaching to avoid colliding with part
                self._cached_grip_cmd = -1.0  # Open gripper
                
        elif self._state == ConveyorFSMState.READY:
            target = self._ready_pos()
            if target is not None:
                self._cached_active_target = target
                # Keep gripper open while positioning above part
                self._cached_grip_cmd = -1.0  # Open gripper
                
        elif self._state == ConveyorFSMState.APPROACH:
            target = self._approach_pos()
            if target is not None:
                self._cached_active_target = target
                # Keep gripper open during approach
                self._cached_grip_cmd = -1.0  # Open gripper
                
        elif self._state == ConveyorFSMState.DESCEND:
            target = self._descend_pos()
            if target is not None:
                self._cached_active_target = target
                # Keep gripper open until reaching grasp position
                self._cached_grip_cmd = -1.0  # Open gripper
                
        elif self._state == ConveyorFSMState.GRASP:
            target = self._grasp_pos()
            if target is not None:
                self._cached_active_target = target
                # Keep gripper open here; _check_transition owns the exact
                # close timing after fresh alignment checks.
                self._cached_grip_cmd = -1.0
            
        elif self._state == ConveyorFSMState.VERIFY_GRASP:
            # VERIFY_GRASP now runs AFTER LIFT — hold at LIFT height while
            # verifying (don't descend back down).
            self._cached_active_target = self._lift_pos()
            self._cached_grip_cmd = 1.0  # Keep gripper closed
            
        elif self._state == ConveyorFSMState.LIFT:
            target = self._lift_pos()
            if target is not None:
                self._cached_active_target = target
                self._cached_grip_cmd = 1.0  # Keep gripper closed while lifting
                
        elif self._state == ConveyorFSMState.SORT_DECIDE:
            # Brief pause to decide sorting
            self._cached_active_target = self._lift_pos()
            self._cached_grip_cmd = 1.0  # Keep gripper closed
            
        elif self._state == ConveyorFSMState.TRANSPORT:
            target = self._transport_pos()
            if target is not None:
                self._cached_active_target = target
                self._cached_grip_cmd = 1.0  # Keep gripper closed during transport
                
        elif self._state == ConveyorFSMState.LOWER:
            target = self._lower_pos()
            if target is not None:
                self._cached_active_target = target
                self._cached_grip_cmd = 1.0  # Keep gripper closed while lowering
                
        elif self._state == ConveyorFSMState.RELEASE:
            self._cached_active_target = self._lower_pos()
            self._cached_grip_cmd = -1.0  # Open gripper (negative = open)
            
        elif self._state == ConveyorFSMState.RETREAT:
            target = self._retreat_pos()
            if target is not None:
                self._cached_active_target = target
                self._cached_grip_cmd = -1.0  # Keep gripper open while retreating
                
        elif self._state == ConveyorFSMState.RETRY:
            target = self._retry_pos()
            if target is not None:
                self._cached_active_target = target
                # Open gripper before retrying grasp
                self._cached_grip_cmd = -1.0  # Open gripper
    
    # ------------------------------------------------------------------
    # Position computations
    # ------------------------------------------------------------------
    
    def _calculate_box_bounds(self, box_center: np.ndarray, box_scale: np.ndarray) -> dict:
        """Calculate box boundary ranges from center and scale.
        
        Args:
            box_center: Box center position [x, y, z] in world frame
            box_scale: Box scale [sx, sy, sz]
            
        Returns:
            Dict with 'x', 'y', 'z' keys, each containing [min, max]
        """
        return {
            'x': [float(box_center[0] - box_scale[0] / 2), float(box_center[0] + box_scale[0] / 2)],
            'y': [float(box_center[1] - box_scale[1] / 2), float(box_center[1] + box_scale[1] / 2)],
            'z': [float(box_center[2] - box_scale[2] / 2), float(box_center[2] + box_scale[2] / 2)],
        }
    
    def _is_part_in_box(self, part_pos: np.ndarray, box_bounds: dict) -> bool:
        """Check if a part position is within box boundaries.
        
        Args:
            part_pos: Part position [x, y, z] in world frame
            box_bounds: Dict with 'x', 'y', 'z' keys containing [min, max]
            
        Returns:
            True if part is within box bounds
        """
        x_in = box_bounds['x'][0] <= part_pos[0] <= box_bounds['x'][1]
        y_in = box_bounds['y'][0] <= part_pos[1] <= box_bounds['y'][1]
        z_in = box_bounds['z'][0] <= part_pos[2] <= box_bounds['z'][1]
        return x_in and y_in and z_in
    
    def _verify_parts_in_boxes(self) -> tuple[bool, str]:
        """Verify that all sorted parts are in their correct boxes.
        
        Part A → right box, Part B → left box (matches ``_determine_target_box``).
        Checks the frozen grasp positions of all sorted parts.
        
        Returns:
            Tuple of (all_correct, details_message)
        """
        # We need to track where each part was placed
        # For now, we'll check current part positions in the world
        # This assumes parts stay where they were released
        
        parts_a_correct = 0
        parts_b_correct = 0
        parts_a_total = 0
        parts_b_total = 0
        
        # Check all part positions
        for idx in range(len(self._part_positions_world)):
            # Skip unsorted parts AND skipped parts (failed retries)
            if idx not in self._sorted_part_indices or idx in self._skipped_parts:
                continue  # Skip unsorted parts
            
            part_type = self._identify_part_type(idx)
            part_pos = self._part_positions_world[idx]
            
            if part_pos is None:
                continue
            
            if part_type == 'part_a':
                parts_a_total += 1
                if self._is_part_in_box(part_pos, self._box_right_bounds):
                    parts_a_correct += 1
                    logger.debug(f"[ConveyorFSM] Part {idx} (A) correctly placed in right box")
                else:
                    logger.warning(f"[ConveyorFSM] Part {idx} (A) NOT in right box: pos={part_pos}")
            else:  # part_b
                parts_b_total += 1
                if self._is_part_in_box(part_pos, self._box_left_bounds):
                    parts_b_correct += 1
                    logger.debug(f"[ConveyorFSM] Part {idx} (B) correctly placed in left box")
                else:
                    logger.warning(f"[ConveyorFSM] Part {idx} (B) NOT in left box: pos={part_pos}")
        
        all_correct = (parts_a_correct == parts_a_total and 
                      parts_b_correct == parts_b_total and
                      parts_a_total > 0 and parts_b_total > 0)
        
        details = (f"Parts in boxes: A={parts_a_correct}/{parts_a_total}, "
                  f"B={parts_b_correct}/{parts_b_total}")
        
        # If any parts were skipped (failed retries), episode is not successful
        if self._skipped_parts:
            all_correct = False
            details += f" (skipped {len(self._skipped_parts)} parts: {self._skipped_parts})"
        
        return all_correct, details
    
    def _get_current_part_world(self) -> Optional[np.ndarray]:
        """Get current part world position."""
        if 0 <= self._current_part_index < len(self._part_positions_world):
            return self._part_positions_world[self._current_part_index]
        return None
    
    def _predict_part_position(self, lookahead_time: float = 0.5) -> Optional[np.ndarray]:
        """Predict part position after lookahead time accounting for conveyor motion."""
        part_world = self._get_current_part_world()
        if part_world is None:
            return None
        
        # Simple linear prediction
        predicted_x = part_world[0] + self._conveyor_speed * lookahead_time
        return np.array([predicted_x, part_world[1], part_world[2]], dtype=float)
    
    def _world_to_base(self, pos_world: np.ndarray) -> np.ndarray:
        """Transform world position to robot base frame."""
        pos_rel = pos_world - self._robot_position_world
        return self._R_world_to_base @ pos_rel
    
    def _base_to_world(self, pos_base: np.ndarray) -> np.ndarray:
        """Transform base position to world frame."""
        return self._R_base_to_world @ pos_base + self._robot_position_world
    
    def _neutral_pos(self) -> Optional[np.ndarray]:
        """Neutral waiting position."""
        if self._current_ee is None:
            return None
        current = self._current_ee.get(self._current_arm)
        if current is None:
            return None
        
        # High neutral position
        neutral = current.copy()
        neutral[2] = max(neutral[2], 0.30)  # Keep Z >= 0.30m
        return neutral
    
    def _track_pos(self) -> Optional[np.ndarray]:
        """Track part moving position.

        Uses the SAME fixed grasp RPY as all other states (ported from
        Part_Sorting). Orientation is built by tilting world-down toward the
        robot body by ``_forearm_tilt_deg``; this is always reachable by IK
        and keeps the forearm pointing naturally downward (no external
        rotation / folding).
        """
        predicted = self._predict_part_position(lookahead_time=0.3)
        if predicted is None:
            return None

        pos_base = self._world_to_base(predicted)
        approach_z = pos_base[2] + self._approach_height
        return np.concatenate([pos_base[:2], [approach_z], self._grasp_rpy])
    
    def _ready_pos(self) -> Optional[np.ndarray]:
        """Ready position above part.
        
        Use natural vertical orientation - same as TRACK_PART for smooth transition.
        """
        return self._track_pos()  # Uses same natural pose as tracking
    
    def _approach_pos(self) -> Optional[np.ndarray]:
        """Approach position (directly above part at approach height).

        Target is recomputed every frame (see ``_MOVING_TARGET_STATES``) so
        the arm continuously tracks the moving part instead of chasing a
        frozen prediction. A small lookahead still helps the arm aim slightly
        ahead to account for the remaining travel time.
        
        During retry, use minimal lookahead to target the part's CURRENT position
        rather than over-predicting — the part has already moved during the failed
        grasp attempt, and we need to reach it where it IS, not where it will be.
        """
        # During retry, use minimal lookahead to avoid over-predicting.
        # The part has already moved further down the conveyor after the failed
        # grasp, so we want to target where it IS now, not 3.5cm ahead.
        is_retry = self._failed_parts.get(self._current_part_index, 0) > 0
        lookahead = 0.15 if is_retry else 0.3
        predicted = self._predict_part_position(lookahead_time=lookahead)
        if predicted is None:
            return None

        pos_base = self._world_to_base(predicted)
        approach_z = pos_base[2] + self._approach_height
        return np.concatenate([pos_base[:2], [approach_z], self._grasp_rpy])
    
    def _descend_pos(self) -> Optional[np.ndarray]:
        """Descend to grasp height.

        Target is recomputed every frame; lookahead accounts for the time
        the arm still needs to finish descending to grasp height.
        
        During retry, descend closer to the conveyor surface to improve
        grasp reliability — the default 2cm gap is often too high after
        a failed grasp attempt. Also use minimal lookahead to target the
        part's current position rather than over-predicting.
        """
        is_retry = self._failed_parts.get(self._current_part_index, 0) > 0
        # Minimal lookahead on retry: target where part IS, not where it will be
        lookahead = 0.15 if is_retry else 0.35
        predicted = self._predict_part_position(lookahead_time=lookahead)
        if predicted is None:
            return None

        pos_base = self._world_to_base(predicted)
        # On retry, descend deeper (closer to conveyor) to improve grasp reliability
        # Default: 2cm above part, Retry: 1cm above part
        descend_height = 0.01 if is_retry else self._descend_height
        descend_z = pos_base[2] + descend_height
        return np.concatenate([pos_base[:2], [descend_z], self._grasp_rpy])
    
    def _grasp_pos(self) -> Optional[np.ndarray]:
        """Grasp position (at part surface).
        
        The gripper needs to descend below the part center to properly surround it.
        For a part sitting on the conveyor, the gripper fingers need to reach down
        to grasp the part from the sides, which requires going below the part's Z position.
        
        Target is recomputed every frame while the part is still moving (i.e.
        before the gripper has closed and frozen the part position). A small
        lookahead (~0.4s on retry) matches the typical dwell in GRASP state
        between convergence and gripper close, so the part catches up to the
        target as the gripper clamps.
        """
        # Use frozen position if part is already grasped
        if self._grasped_part_position is not None:
            part_world = self._grasped_part_position
        else:
            # On retry, add a modest lookahead so the target is ahead of the
            # part by about the time it takes to finish descending + close.
            # But keep it minimal to avoid over-predicting.
            is_retry = self._failed_parts.get(self._current_part_index, 0) > 0
            lookahead = 0.15 if is_retry else self._grasp_lookahead_time
            part_world = self._predict_part_position(lookahead_time=lookahead)
            if part_world is None:
                part_world = self._get_current_part_world()
        
        if part_world is None:
            return None
        
        pos_base = self._world_to_base(part_world)
        # sixforce_link is above the finger contact patch; keep it slightly
        # above the part center instead of driving it below the conveyor.
        grasp_z = pos_base[2] + self._grasp_depth_offset
        
        # Safety: Don't go below minimum Z (avoid hitting conveyor/table)
        # Lowered from 0.03 to 0.01 to allow the gripper to fully approach the
        # conveyor surface during retry (part sits very close to conveyor top).
        min_safe_z = 0.01  # 1cm minimum in base frame
        if grasp_z < min_safe_z:
            logger.warning(
                f"[ConveyorFSM] Grasp Z {grasp_z:.3f} below minimum {min_safe_z:.3f}, clamping"
            )
            grasp_z = min_safe_z
        
        # Same fixed grasp RPY as all other states.
        return np.concatenate([pos_base[:2], [grasp_z], self._grasp_rpy])
    
    def _lift_pos(self) -> Optional[np.ndarray]:
        """Lift position (after grasping).

        IMPORTANT: Use frozen part position from grasp moment, not current
        conveyor position. Once grasped, the part moves with the gripper.

        ORIENTATION: Same fixed grasp RPY as all other states — zero
        orientation change between GRASP→LIFT→TRANSPORT.
        """
        if self._grasped_part_position is None:
            logger.warning("[ConveyorFSM-LIFT] No grasped part position frozen, using current position")
            part_world = self._get_current_part_world()
        else:
            part_world = self._grasped_part_position

        if part_world is None:
            return None

        pos_base = self._world_to_base(part_world)
        # Part A is large/heavy — minimal lift to reduce vertical acceleration.
        if self._current_part_type == 'part_a':
            lift_z = pos_base[2] + 0.10  # Lift only 10cm for Part A
        else:
            lift_z = pos_base[2] + 0.15  # Lift 15cm for Part B
        return np.concatenate([pos_base[:2], [lift_z], self._grasp_rpy])
    
    def _transport_pos(self) -> Optional[np.ndarray]:
        """Transport to target box.

        Same fixed grasp RPY — identical to LIFT. IK converges easily.
        """
        target_box = self._determine_target_box()
        if target_box is None:
            return None

        box_base = self._world_to_base(target_box)
        # Part B target box is on the right side — trajectory passes close to
        # conveyor belt, so use higher clearance to avoid collision.
        if self._current_part_type == 'part_b':
            transport_z = box_base[2] + 0.35  # 35cm above box for Part B — clears conveyor
        else:
            transport_z = box_base[2] + 0.25  # 25cm for Part A — shorter travel
        return np.concatenate([box_base[:2], [transport_z], self._grasp_rpy])
    
    def _lower_pos(self) -> Optional[np.ndarray]:
        """Lower into box.

        Same fixed grasp RPY — consistent with TRANSPORT.
        """
        target_box = self._determine_target_box()
        if target_box is None:
            return None

        box_base = self._world_to_base(target_box)
        lower_z = box_base[2] + 0.05  # 5cm into box
        return np.concatenate([box_base[:2], [lower_z], self._grasp_rpy])
    
    def _retreat_pos(self) -> Optional[np.ndarray]:
        """Retreat from box.

        Same fixed grasp RPY — consistent with LOWER/TRANSPORT.
        """
        target_box = self._determine_target_box()
        if target_box is None:
            return None

        box_base = self._world_to_base(target_box)
        # Match TRANSPORT height to avoid dropping during the retreat arc.
        if self._current_part_type == 'part_b':
            retreat_z = box_base[2] + 0.35  # 35cm above box for Part B
        else:
            retreat_z = box_base[2] + 0.25  # 25cm for Part A
        return np.concatenate([box_base[:2], [retreat_z], self._grasp_rpy])
    
    def _retry_pos(self) -> Optional[np.ndarray]:
        """Retry position — track the CURRENT part position (not neutral).
        
        After a failed grasp, the part has moved further down the conveyor.
        Going to a neutral position wastes time. Instead, approach from the
        current part position to catch up quickly.
        """
        return self._approach_pos()  # Track current part, same as APPROACH
    
    def _determine_target_box(self) -> Optional[np.ndarray]:
        """Determine target box based on part type.
        
        Part A → right box
        Part B → left box
        """
        if self._current_part_type == 'part_a':
            return self._box_right_world
        elif self._current_part_type == 'part_b':
            return self._box_left_world
        else:
            logger.warning(f"[ConveyorFSM] Unknown part type: {self._current_part_type}")
            return None
    
    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------
    
    def _skip_current_part(self, reason: str) -> None:
        """Mark the current part as skipped and transition back to WAIT_FOR_PART.
        
        Used when a retry cannot complete (part out of reach, IK stuck, or
        state timed out). Ensures the skipped part is not re-selected and the
        episode progresses toward DONE.
        """
        part_idx = self._current_part_index
        if part_idx not in self._skipped_parts:
            self._skipped_parts.append(part_idx)
            self._parts_sorted += 1
            logger.warning(
                f"[ConveyorFSM] Skipping part {part_idx} ({reason}) — "
                f"total skipped={len(self._skipped_parts)}, sorted={self._parts_sorted}/{self._total_parts}"
            )
        self._transition_to(ConveyorFSMState.WAIT_FOR_PART)
    
    def _check_transition(self) -> None:
        """Check if current state should transition to next state."""
        # Don't count timeout frames while target is None
        target = self._cached_active_target
        # Allow timeout counting for READY, APPROACH, DESCEND, etc. (exclude only IDLE, DONE, GRASP, RELEASE, VERIFY_GRASP)
        if target is not None and self._state not in (ConveyorFSMState.IDLE, ConveyorFSMState.DONE, ConveyorFSMState.GRASP, ConveyorFSMState.RELEASE, ConveyorFSMState.VERIFY_GRASP):
            self._state_frame_counter += 1
        
        # Per-state timeout overrides — states that chase a moving part on
        # the conveyor must abort much sooner than the global timeout so the
        # FSM can skip to the next part instead of idling on unreachable IK.
        # Global timeout stays high for states like TRANSPORT/LOWER where
        # physics-heavy motion legitimately takes longer.
        per_state_timeout = {
            ConveyorFSMState.APPROACH: 90,   # ~1.5s at 60Hz
            ConveyorFSMState.DESCEND: 120,   # ~2.0s at 60Hz
            ConveyorFSMState.RETRY: 90,      # ~1.5s at 60Hz
            ConveyorFSMState.TRACK_PART: 90, # ~1.5s at 60Hz
            ConveyorFSMState.READY: 60,      # ~1.0s at 60Hz
        }.get(self._state, self._state_timeout)
        timed_out = self._state_frame_counter >= per_state_timeout
        
        # Debug: Log READY state issues
        if self._state == ConveyorFSMState.READY and self._state_frame_counter % 100 == 0:
            logger.warning(
                f"[ConveyorFSM-DEBUG] READY state: target={target is not None}, "
                f"timeout_counter={self._state_frame_counter}/{self._state_timeout}, "
                f"timed_out={timed_out}, part_idx={self._current_part_index}"
            )
            if target is not None and self._current_ee and self._current_arm in self._current_ee:
                pos_error = np.linalg.norm(target[:3] - self._current_ee[self._current_arm][:3])
                logger.warning(f"[ConveyorFSM-DEBUG] Position error: {pos_error:.3f}m, tol: {self._pos_tol:.3f}m")
            
            # Log part tracking info
            if self._current_part_index < len(self._part_positions_world):
                part_world = self._part_positions_world[self._current_part_index]
                logger.warning(f"[ConveyorFSM-DEBUG] Part {self._current_part_index} world pos: {part_world}")
                logger.warning(f"[ConveyorFSM-DEBUG] Parts spawned: {self._parts_spawned}, sorted: {self._parts_sorted}")
        
        # Debug: Log WAIT_FOR_PART state
        if self._state == ConveyorFSMState.WAIT_FOR_PART and self._state_frame_counter % 600 == 0:
            logger.debug(
                f"[ConveyorFSM-DEBUG] WAIT_FOR_PART: parts_spawned={self._parts_spawned}, "
                f"parts_sorted={self._parts_sorted}, total_parts={self._total_parts}"
            )
            logger.debug(f"[ConveyorFSM-DEBUG] Part positions: {self._part_positions_world}")
            logger.debug(f"[ConveyorFSM-DEBUG] Grab zone: [{self._grab_zone_x_min}, {self._grab_zone_x_max}]")
            logger.debug(f"[ConveyorFSM-DEBUG] Has available part: {self._has_available_part()}")
        
        if self._state == ConveyorFSMState.WAIT_FOR_PART:
            # If all parts are accounted for (sorted or skipped), finish the
            # episode immediately instead of idling here until timeout.
            if self._parts_sorted >= self._total_parts:
                success, details = self._verify_parts_in_boxes()
                self._episode_success = success
                logger.info(f"[ConveyorFSM] Episode evaluation: {details}, success={success}")
                self._transition_to(ConveyorFSMState.DONE)
            # Check if new part available in grab zone
            elif self._has_available_part():
                self._select_next_part()
                self._transition_to(ConveyorFSMState.TRACK_PART)
            elif timed_out:
                # Check if all parts spawned and sorted
                if self._parts_sorted >= self._total_parts:
                    # Verify part positions before transitioning to DONE
                    success, details = self._verify_parts_in_boxes()
                    self._episode_success = success
                    logger.info(f"[ConveyorFSM] Episode evaluation: {details}, success={success}")
                    self._transition_to(ConveyorFSMState.DONE)
        
        elif self._state == ConveyorFSMState.TRACK_PART:
            # Transition as soon as part is anywhere in grab zone (do not wait
            # for it to reach the tight center) to minimize conveyor dwell.
            if self._is_part_in_grasp_position() or timed_out:
                # Skip READY — it just hovers at the same height as TRACK_PART.
                self._transition_to(ConveyorFSMState.APPROACH)
        
        elif self._state == ConveyorFSMState.READY:
            if self._is_converged(target) or timed_out:
                self._transition_to(ConveyorFSMState.APPROACH)
        
        elif self._state == ConveyorFSMState.APPROACH:
            # If the part drifted past the grab zone during retry, the target
            # is unreachable and IK will keep failing — abort instead of hanging.
            if self._is_part_out_of_grasp_reach():
                logger.warning(
                    f"[ConveyorFSM] Part {self._current_part_index} exited grab zone during APPROACH "
                    f"(X={self._get_current_part_world()[0]:.3f} > {self._grab_zone_x_max:.3f})"
                )
                self._skip_current_part("APPROACH: part out of grab zone")
            elif timed_out:
                # APPROACH timeout almost always means IK cannot reach the
                # target (part too far, obstructed, or unreachable pose).
                # Skip so we don't loop back to this part.
                logger.warning(
                    f"[ConveyorFSM] APPROACH timed out for part "
                    f"{self._current_part_index} — IK likely cannot reach target."
                )
                self._skip_current_part("APPROACH: timeout / IK unreachable")
            elif self._is_converged(target):
                self._transition_to(ConveyorFSMState.DESCEND)
        
        elif self._state == ConveyorFSMState.DESCEND:
            self._frame_counter += 1
            if self._frame_counter % 20 == 0 and target is not None:
                self._log_tracking_error("DESCEND", target)
            # If the part drifted past the grab zone (e.g. after multiple retries),
            # stop chasing it — it's already out of reach.
            if self._is_part_out_of_grasp_reach():
                logger.warning(
                    f"[ConveyorFSM] Part {self._current_part_index} exited grab zone during DESCEND "
                    f"(X={self._get_current_part_world()[0]:.3f} > {self._grab_zone_x_max:.3f})"
                )
                self._skip_current_part("DESCEND: part out of grab zone")
            # IK solver stuck detection: if joint positions barely change for 30+ frames,
            # the target is unreachable (e.g. retry chased part too far down conveyor).
            elif self._is_ik_stuck_in_descend():
                logger.warning(
                    f"[ConveyorFSM] IK solver stuck in DESCEND (part {self._current_part_index})"
                )
                self._skip_current_part("DESCEND: IK stuck")
            elif timed_out:
                logger.warning(
                    f"[ConveyorFSM] DESCEND timed out for part {self._current_part_index}"
                )
                self._skip_current_part("DESCEND: timeout")
            elif self._is_converged_custom(target, self._descend_pos_tol):
                self._transition_to(ConveyorFSMState.GRASP)
                self._frame_counter = 0
        
        elif self._state == ConveyorFSMState.GRASP:
            # Same out-of-reach check: if part drifted past grab zone, abort.
            if self._is_part_out_of_grasp_reach():
                logger.warning(
                    f"[ConveyorFSM] Part {self._current_part_index} exited grab zone during GRASP, "
                    f"aborting."
                )
                self._transition_to(ConveyorFSMState.WAIT_FOR_PART)
            else:
                self._frame_counter += 1
            if self._frame_counter == 1:
                # Log grasp position details
                if self._current_ee and self._current_arm in self._current_ee:
                    current_z = self._current_ee[self._current_arm][2]
                    target = self._grasp_pos()
                    if target is not None:
                        logger.info(
                            f"[ConveyorFSM] GRASP state entered for part {self._current_part_index}, "
                            f"current_z={current_z:.3f}, target_z={target[2]:.3f}, "
                            f"depth_offset={self._grasp_depth_offset:.3f}, "
                            f"z_distance={abs(current_z - target[2]):.3f}"
                        )
                else:
                    logger.info(
                        f"[ConveyorFSM] GRASP state entered for part {self._current_part_index}, "
                        f"will hold for {self._grasp_frames} frames"
                    )
            
            target = self._grasp_pos()
            if target is not None:
                self._cached_active_target = target
                # Only close gripper AFTER reaching grasp position
                # Use stricter tolerance for Z-axis convergence (3cm instead of 6cm)
                # AND require minimum descent time to ensure actual movement
                has_converged = self._is_grasp_aligned(target)
                min_descent_frames = self._grasp_min_frames

                # Safety fallback: if IK stays stuck (right_success=False persists),
                # _is_converged will never be True. Keep disabled by default
                # because closing in midair produces bad Task2 demonstrations.
                force_close = (
                    self._grasp_force_close_frames > 0
                    and self._frame_counter >= self._grasp_force_close_frames
                )
                if force_close and self._frame_counter == self._grasp_force_close_frames:
                    logger.warning(
                        f"[ConveyorFSM-GRASP] IK did not converge after "
                        f"{self._grasp_force_close_frames} frames, force-closing gripper."
                    )

                if (has_converged and self._frame_counter >= min_descent_frames) or force_close:
                    # Both converged AND spent enough time descending, close gripper
                    self._cached_grip_cmd = 1.0  # Close gripper
                    
                    # CRITICAL: Freeze part position at grasp moment
                    if self._grasped_part_position is None:
                        self._grasped_part_position = self._get_current_part_world()
                        self._set_current_part_conveyor_follow(False)
                        self._gripper_close_start_frame = self._frame_counter
                        if self._grasped_part_position is not None:
                            logger.info(
                                f"[ConveyorFSM-GRASP] Part position frozen at grasp: "
                                f"{self._grasped_part_position}"
                            )
                    
                    if self._frame_counter == min_descent_frames:
                        logger.info(
                            f"[ConveyorFSM-GRASP] Closing gripper at frame {self._frame_counter}, "
                            f"converged={has_converged}"
                        )
                    self._log_grasp_alignment(target)
                    
                    # After closing gripper, wait enough frames for physical closure to apply grip force
                    close_elapsed = 0
                    if self._gripper_close_start_frame is not None:
                        close_elapsed = self._frame_counter - self._gripper_close_start_frame
                    if close_elapsed >= self._gripper_close_settle_frames:
                        logger.info(
                            f"[ConveyorFSM] GRASP complete ({self._frame_counter} frames), "
                            f"close_elapsed={close_elapsed} frames, transitioning to LIFT (verify-after-lift)"
                        )
                        self._transition_to(ConveyorFSMState.LIFT)
                        self._frame_counter = 0
                else:
                    # Still descending or not converged yet, keep gripper open
                    self._cached_grip_cmd = -1.0  # Keep gripper open during descent
                    if self._frame_counter == 0:
                        logger.info(
                            f"[ConveyorFSM-GRASP] Starting descent, keeping gripper open. "
                            f"Need {min_descent_frames} frames minimum, "
                            f"xy_tol={self._grasp_xy_tol*100:.1f}cm, z_tol={self._grasp_z_tol*100:.1f}cm"
                        )
            
            # Log progress every 10 frames
            if self._frame_counter % 10 == 0 and self._current_ee and self._current_arm in self._current_ee:
                target = self._grasp_pos()
                if target is not None:
                    current_z = self._current_ee[self._current_arm][2]
                    z_error = abs(current_z - target[2])
                    logger.info(
                        f"[ConveyorFSM-GRASP] frame={self._frame_counter}, "
                        f"current_z={current_z:.3f}, target_z={target[2]:.3f}, "
                        f"z_error={z_error:.3f}"
                    )
        
        elif self._state == ConveyorFSMState.LIFT:
            self._frame_counter += 1
            lift_ready = self._frame_counter >= self._lift_min_frames
            if (lift_ready and self._is_converged(target)) or timed_out:
                # Gripper is now at LIFT height — move to VERIFY_GRASP for a
                # settled check (both position-based lift + finger_width).
                logger.info(
                    f"[ConveyorFSM] LIFT complete after {self._frame_counter} frames, "
                    f"transitioning to VERIFY_GRASP"
                )
                self._transition_to(ConveyorFSMState.VERIFY_GRASP)
                self._frame_counter = 0

        elif self._state == ConveyorFSMState.VERIFY_GRASP:
            # Verification happens AFTER lift — the part has had time to leave
            # the conveyor surface, so both position lift and finger width are
            # meaningful signals. Combined check: pass if EITHER signal is OK
            # (finger_width proves contact, position proves actual lift).
            self._frame_counter += 1
            if self._frame_counter >= self._grasp_verify_frames or timed_out:
                # Log verification details
                if self._gripper_finger_width is not None:
                    logger.info(
                        f"[ConveyorFSM-VERIFY] frame={self._frame_counter}, "
                        f"finger_width={self._gripper_finger_width:.4f}, "
                        f"open_width={self.gripper_open_width:.4f}, "
                        f"close_width={self.gripper_close_width:.4f}"
                    )

                # Position-based check (primary signal — the part must have
                # actually risen with the gripper).
                position_ok = self._verify_grasp_by_position()
                # Finger-width check (secondary — rejects obvious failures
                # like fully-closed-empty or never-closed).
                finger_ok = self._verify_grasp()

                # Grasp is successful only if BOTH checks pass.
                grasp_ok = position_ok and finger_ok

                logger.info(
                    f"[ConveyorFSM-VERIFY] part={self._current_part_index}, "
                    f"position_ok={position_ok}, finger_ok={finger_ok}, "
                    f"grasp_ok={grasp_ok}"
                )

                if grasp_ok:
                    logger.info(
                        f"[ConveyorFSM] Grasp verified after LIFT for part "
                        f"{self._current_part_index}"
                    )
                    self._transition_to(ConveyorFSMState.SORT_DECIDE)
                    self._frame_counter = 0
                else:
                    logger.warning(
                        f"[ConveyorFSM] Grasp verification FAILED after LIFT for part "
                        f"{self._current_part_index} "
                        f"(position_ok={position_ok}, finger_ok={finger_ok})"
                    )
                    self._handle_grasp_failure()
        
        elif self._state == ConveyorFSMState.SORT_DECIDE:
            # Immediate transition to transport
            self._frame_counter += 1
            if self._frame_counter >= 5:  # Brief pause
                self._transition_to(ConveyorFSMState.TRANSPORT)
        
        elif self._state == ConveyorFSMState.TRANSPORT:
            transport_tol = self._pos_tol * 2.0
            if self._is_converged_custom(target, transport_tol) or timed_out:
                if timed_out:
                    logger.warning(f"[ConveyorFSM] TRANSPORT timed out after {self._state_frame_counter} frames")
                self._transition_to(ConveyorFSMState.LOWER)
        
        elif self._state == ConveyorFSMState.LOWER:
            lower_tol = self._pos_tol * 2.0
            if self._is_converged_custom(target, lower_tol) or timed_out:
                if timed_out:
                    logger.warning(f"[ConveyorFSM] LOWER timed out after {self._state_frame_counter} frames")
                self._transition_to(ConveyorFSMState.RELEASE)
                self._frame_counter = 0
        
        elif self._state == ConveyorFSMState.RELEASE:
            self._frame_counter += 1
            if self._frame_counter >= self._release_frames:
                self._transition_to(ConveyorFSMState.RETREAT)
        
        elif self._state == ConveyorFSMState.RETREAT:
            if self._is_converged(target) or timed_out:
                if timed_out:
                    logger.warning(f"[ConveyorFSM] RETREAT timed out after {self._state_frame_counter} frames")
                
                # Update sorted counts
                self._parts_sorted += 1
                if self._current_part_type == 'part_a':
                    self._sorted_count_a += 1
                else:
                    self._sorted_count_b += 1
                
                self._sorted_part_indices.add(self._current_part_index)
                logger.info(
                    f"[ConveyorFSM] Part {self._current_part_index} ({self._current_part_type}) sorted "
                    f"(Total: {self._parts_sorted}/{self._total_parts}, A:{self._sorted_count_a}, B:{self._sorted_count_b})"
                )
                
                # Check if done
                if self._parts_sorted >= self._total_parts:
                    # Verify part positions before transitioning to DONE
                    success, details = self._verify_parts_in_boxes()
                    self._episode_success = success
                    logger.info(f"[ConveyorFSM] Episode evaluation: {details}, success={success}")
                    logger.info(f"[ConveyorFSM] Transitioning to DONE state")
                    self._transition_to(ConveyorFSMState.DONE)
                else:
                    self._transition_to(ConveyorFSMState.WAIT_FOR_PART)
        
        elif self._state == ConveyorFSMState.RETRY:
            # Skip neutral position — go directly back to APPROACH to chase the
            # current part. The part has moved further during the failed grasp
            # attempt, so we need to catch up immediately.
            if self._is_converged(target) or timed_out:
                self._transition_to(ConveyorFSMState.APPROACH)
    
    def _has_available_part(self) -> bool:
        """Check if there's an available part in the grab zone.

        Skipped parts (max-retries exhausted) are excluded to prevent the
        FSM from re-selecting the same un-graspable part in a loop.
        """
        for idx, part_pos in enumerate(self._part_positions_world):
            if idx in self._sorted_part_indices:
                continue
            if idx in self._skipped_parts:
                continue
            if self._grab_zone_x_min <= part_pos[0] <= self._grab_zone_x_max:
                return True
        return False
    
    def _select_next_part(self) -> None:
        """Select next part to grasp from conveyor.
        
        Strategy:
        - Find parts within grab zone
        - Prefer parts closer to grab_zone_x_max (about to exit)
        - Skip already sorted parts
        """
        best_part_idx = None
        best_priority = -1
        best_part_type = None
        
        for idx, part_pos in enumerate(self._part_positions_world):
            # Skip sorted parts
            if idx in self._sorted_part_indices:
                continue
            # Skip parts that exhausted max retries — they're un-graspable,
            # so don't loop back to them.
            if idx in self._skipped_parts:
                continue
            
            part_type = self._identify_part_type(idx)
            
            # Check if in grab zone
            if part_pos[0] < self._grab_zone_x_min or part_pos[0] > self._grab_zone_x_max:
                continue
            
            # Priority: parts further along conveyor (higher X)
            priority = part_pos[0]
            
            if priority > best_priority:
                best_priority = priority
                best_part_idx = idx
                best_part_type = part_type
        
        if best_part_idx is not None:
            self._current_part_index = best_part_idx
            self._current_part_type = best_part_type
            self._grasp_failed_in_verify = False
            logger.info(
                f"[ConveyorFSM] Selected part {best_part_idx} ({best_part_type}) "
                f"at X={best_priority:.3f}"
            )
        else:
            logger.warning("[ConveyorFSM] No available part found in grab zone")
    
    def _identify_part_type(self, part_idx: int) -> str:
        """Identify part type (part_a or part_b).
        
        This should ideally use vision or metadata. For now, we can use
        prim path patterns or assume alternating types.
        """
        # Placeholder: alternate based on index
        # In real implementation, use vision system or scene metadata
        return 'part_a' if part_idx % 2 == 0 else 'part_b'
    
    def _is_part_in_grasp_position(self) -> bool:
        """Check if current part is in good grasp position.

        Wide acceptance: anywhere in the grab zone is OK. The arm will keep
        tracking the predicted part position during APPROACH/DESCEND, so we
        don't need to wait for the part to reach the center first. This
        minimizes the time a part spends on the conveyor before being grasped.

        """
        part_world = self._get_current_part_world()
        if part_world is None:
            return False

        return self._grab_zone_x_min <= part_world[0] <= self._grab_zone_x_max
    
    def _is_part_out_of_grasp_reach(self) -> bool:
        """Check if the part has drifted past the grab zone (X > grab_zone_x_max).

        Used during DESCEND/GRASP to detect when a retry chased the part past
        the end of the reachable conveyor. If so, abort immediately rather than
        hanging in IK-failure limbo.
        """
        part_world = self._get_current_part_world()
        if part_world is None:
            return False  # Can't read position → don't abort
        # Give retries a bit more slack — the part may have drifted forward during
        # the failed grasp attempt. +10cm extension for retries.
        is_retry = self._failed_parts.get(self._current_part_index, 0) > 0
        x_max = self._grab_zone_x_max + (0.10 if is_retry else 0.0)
        return part_world[0] > x_max
    
    def _is_ik_stuck_in_descend(self) -> bool:
        """Detect if IK solver is stuck in DESCEND (joint values barely changing).
        
        When the part has moved too far down the conveyor during retries, the
        IK target becomes unreachable but the solver keeps iterating with
        microscopic changes. We detect this by comparing joint positions over
        recent frames.
        """
        if not hasattr(self, '_descend_joint_history'):
            self._descend_joint_history = []
        
        # Read current right arm joint positions
        try:
            if self._current_ee and self._current_arm in self._current_ee:
                pass  # We need the actual joint states, not just EE pose
            else:
                return False
        except Exception:
            return False
        
        # For simplicity, use right_success=False persistence as the indicator.
        # If the IK solver has been failing for 30+ frames during DESCEND,
        # it's stuck. We track this via the frame counter and success flag.
        # Since we already have _frame_counter in DESCEND state, and we can
        # check if IK has been failing via the cached active target not converging.
        # 
        # Simpler approach: if DESCEND has been running for 200+ frames (~6.7s)
        # without converging, the part is unreachable.
        descend_timeout_frames = 200
        return self._frame_counter >= descend_timeout_frames
    
    def _verify_grasp(self) -> bool:
        """Quick finger-width check after gripper close.
        
        This is a preliminary check — the definitive verification happens
        after LIFT via _verify_grasp_by_position(). Here we only reject
        obvious failures (gripper fully closed = no part, or never closed).
        """
        if self._gripper_finger_width is None:
            logger.warning("[ConveyorFSM-VERIFY] No gripper feedback, assuming success")
            return True
        
        # Only fail if gripper is fully closed (nothing between fingers)
        # or never closed at all. Let position-based check handle the rest.
        fully_closed = abs(self._gripper_finger_width - self.gripper_close_width) < 0.001
        never_closed = self._gripper_finger_width < (self.gripper_open_width + 0.005)
        
        grasp_success = not fully_closed and not never_closed
        
        logger.info(
            f"[ConveyorFSM-VERIFY] finger_width={self._gripper_finger_width:.4f}, "
            f"close_width={self.gripper_close_width:.4f}, "
            f"fully_closed={fully_closed}, never_closed={never_closed}, success={grasp_success}"
        )
        
        return grasp_success
    
    def _verify_grasp_by_position(self) -> bool:
        """Position-based grasp verification: did the part rise with the gripper?

        After LIFT completes, we compare the part's CURRENT world-Z with the
        frozen grasp-Z. If the part is still near conveyor height (didn't rise),
        the grasp failed (part fell or was never held).

        This is more reliable than finger_width alone because it directly
        measures the physical outcome.
        """
        if self._grasped_part_position is None:
            # No reference — fall back to assuming success
            return True

        # Get the part's real-time position from the simulation
        current_part_pos = self._get_current_part_world()
        if current_part_pos is None:
            # Can't read position — assume success rather than false-fail
            return True

        grasp_z = self._grasped_part_position[2]  # Z when gripper closed
        current_z = current_part_pos[2]
        # If part rose at least 3cm from grasp position → it's being held.
        # If it's at or below grasp-Z → it fell back to conveyor or never left.
        z_lift = current_z - grasp_z
        min_lift_threshold = 0.03  # Must have risen at least 3cm

        success = z_lift >= min_lift_threshold
        logger.info(
            f"[ConveyorFSM-LIFT-VERIFY] part={self._current_part_index}, "
            f"grasp_z={grasp_z:.3f}, current_z={current_z:.3f}, "
            f"z_lift={z_lift:.3f}, threshold={min_lift_threshold}, success={success}"
        )
        return success
    
    def _handle_grasp_failure(self) -> None:
        """Handle grasp failure with retry logic."""
        part_idx = self._current_part_index
        current_retries = self._failed_parts.get(part_idx, 0)
        self._set_current_part_conveyor_follow(True)
        
        # Use < to allow exactly _max_retries retry attempts (not counting initial attempt)
        # e.g., if _max_retries=3, allow retries when current_retries is 0, 1, 2 (3 retries total)
        if current_retries < self._max_retries:
            self._failed_parts[part_idx] = current_retries + 1
            logger.warning(
                f"[ConveyorFSM] Grasp failed for part {part_idx}, "
                f"retry {current_retries + 1}/{self._max_retries}"
            )
            self._transition_to(ConveyorFSMState.RETRY)
        else:
            logger.error(f"[ConveyorFSM] Part {part_idx} failed after {current_retries} retries (max: {self._max_retries}), skipping")
            # Add to skipped parts instead of sorted parts - this part was never placed in a box
            if part_idx not in self._skipped_parts:
                self._skipped_parts.append(part_idx)
            # Still count as "sorted" for FSM progression purposes
            self._parts_sorted += 1
            
            if self._parts_sorted >= self._total_parts:
                # Verify part positions before transitioning to DONE
                success, details = self._verify_parts_in_boxes()
                self._episode_success = success
                logger.info(f"[ConveyorFSM] Episode evaluation: {details}, success={success}")
                self._transition_to(ConveyorFSMState.DONE)
            else:
                self._transition_to(ConveyorFSMState.WAIT_FOR_PART)
    
    def _transition_to(self, new_state: ConveyorFSMState) -> None:
        """Transition to new state."""
        old = self._state
        self._state = new_state
        self._state_frame_counter = 0
        self._frame_counter = 0
        self._cached_active_target = None  # Force recomputation
        
        if new_state != old:
            logger.info(f"[ConveyorFSM] {old.value} -> {new_state.value}")
        
        # Clear frozen part position when starting new part OR retrying
        # (RETRY must use CURRENT part position, not stale frozen position from
        # the failed grasp attempt — the part has moved along the conveyor).
        if new_state in (
            ConveyorFSMState.WAIT_FOR_PART,
            ConveyorFSMState.TRACK_PART,
            ConveyorFSMState.READY,
            ConveyorFSMState.RETRY,
        ):
            if self._grasped_part_position is not None:
                logger.info(
                    f"[ConveyorFSM] Clearing frozen part position for {new_state.value}, "
                    f"previous={self._grasped_part_position}"
                )
                self._grasped_part_position = None
    
    # ------------------------------------------------------------------
    # Convergence checks
    # ------------------------------------------------------------------
    
    def _is_converged(self, target: np.ndarray) -> bool:
        """Check if EE has converged to target with default tolerance."""
        return self._is_converged_custom(target, self._pos_tol)
    
    def _is_converged_custom(self, target: np.ndarray, tol: float) -> bool:
        """Check if EE has converged to target with custom tolerance."""
        if target is None or self._current_ee is None:
            return False
        
        current_ee_pose = self._current_ee.get(self._current_arm)
        if current_ee_pose is None:
            return False
        
        pos_error = np.linalg.norm(target[:3] - current_ee_pose[:3])
        converged = pos_error < tol
        
        if converged and self._state_frame_counter % 50 == 0:
            logger.debug(
                f"[ConveyorFSM-CONV] state={self._state.value} arm={self._current_arm}: "
                f"err={pos_error:.3f}m, tol={tol:.3f}, CONVERGED"
            )
        
        return converged

    def _is_grasp_aligned(self, target: np.ndarray) -> bool:
        """Check grasp alignment with separate horizontal and vertical tolerances."""
        if target is None or self._current_ee is None:
            return False

        current_ee_pose = self._current_ee.get(self._current_arm)
        if current_ee_pose is None:
            return False

        delta = target[:3] - current_ee_pose[:3]
        xy_error = float(np.linalg.norm(delta[:2]))
        z_error = float(abs(delta[2]))
        aligned = xy_error <= self._grasp_xy_tol and z_error <= self._grasp_z_tol

        if self._frame_counter % 15 == 0 or aligned:
            part_world = self._get_current_part_world()
            part_base = self._world_to_base(part_world) if part_world is not None else None
            part_xy_error = (
                float(np.linalg.norm(part_base[:2] - current_ee_pose[:2]))
                if part_base is not None else float("nan")
            )
            logger.info(
                f"[ConveyorFSM-GRASP-ALIGN] frame={self._frame_counter}, "
                f"target_delta=({delta[0]:+.3f},{delta[1]:+.3f},{delta[2]:+.3f}), "
                f"xy_err={xy_error:.3f}/{self._grasp_xy_tol:.3f}, "
                f"z_err={z_error:.3f}/{self._grasp_z_tol:.3f}, "
                f"ee_to_part_xy={part_xy_error:.3f}, aligned={aligned}"
            )

        return aligned

    def _log_grasp_alignment(self, target: np.ndarray) -> None:
        """Log final gripper/part alignment at the moment the fingers close."""
        if target is None or self._current_ee is None:
            return

        current_ee_pose = self._current_ee.get(self._current_arm)
        part_world = self._get_current_part_world()
        if current_ee_pose is None or part_world is None:
            return

        part_base = self._world_to_base(part_world)
        target_delta = target[:3] - current_ee_pose[:3]
        part_delta = part_base[:3] - current_ee_pose[:3]
        logger.info(
            f"[ConveyorFSM-GRASP-CLOSE] part={self._current_part_index}, "
            f"target_delta=({target_delta[0]:+.3f},{target_delta[1]:+.3f},{target_delta[2]:+.3f}), "
            f"part_delta=({part_delta[0]:+.3f},{part_delta[1]:+.3f},{part_delta[2]:+.3f}), "
            f"lookahead={self._grasp_lookahead_time:.2f}s"
        )

    def _set_current_part_conveyor_follow(self, enabled: bool) -> None:
        """Enable/disable explicit conveyor motion for the current spawned part."""
        if self._current_part_index < 0 or self._current_part_index >= len(self._part_prim_paths):
            return
        prim_path = self._part_prim_paths[self._current_part_index]
        if not prim_path:
            return

        try:
            import omni.usd
            from pxr import Sdf

            stage = omni.usd.get_context().get_stage()
            prim = stage.GetPrimAtPath(prim_path)
            if not prim.IsValid():
                return
            attr = prim.GetAttribute("ubtech:conveyorFollow")
            if not attr:
                attr = prim.CreateAttribute("ubtech:conveyorFollow", Sdf.ValueTypeNames.Bool)
            attr.Set(bool(enabled))
            logger.info(
                f"[ConveyorFSM] conveyorFollow={enabled} for part "
                f"{self._current_part_index} ({prim_path})"
            )
        except Exception as e:
            logger.debug(f"[ConveyorFSM] Failed to set conveyorFollow on {prim_path}: {e}")

    def _log_tracking_error(self, label: str, target: np.ndarray) -> None:
        """Log moving-target tracking diagnostics for FSM tuning."""
        if target is None or self._current_ee is None:
            return

        current_ee_pose = self._current_ee.get(self._current_arm)
        part_world = self._get_current_part_world()
        if current_ee_pose is None or part_world is None:
            return

        part_base = self._world_to_base(part_world)
        target_delta = target[:3] - current_ee_pose[:3]
        part_delta = part_base[:3] - current_ee_pose[:3]
        logger.info(
            f"[ConveyorFSM-{label}-TRACK] frame={self._frame_counter}, "
            f"part_world=({part_world[0]:+.3f},{part_world[1]:+.3f},{part_world[2]:+.3f}), "
            f"part_base=({part_base[0]:+.3f},{part_base[1]:+.3f},{part_base[2]:+.3f}), "
            f"target=({target[0]:+.3f},{target[1]:+.3f},{target[2]:+.3f}), "
            f"ee=({current_ee_pose[0]:+.3f},{current_ee_pose[1]:+.3f},{current_ee_pose[2]:+.3f}), "
            f"target_delta=({target_delta[0]:+.3f},{target_delta[1]:+.3f},{target_delta[2]:+.3f}), "
            f"part_delta=({part_delta[0]:+.3f},{part_delta[1]:+.3f},{part_delta[2]:+.3f})"
        )
    
    # ------------------------------------------------------------------
    # Helper functions
    # ------------------------------------------------------------------
    
    @staticmethod
    def _euler_zyx_to_rotation_matrix(roll_deg: float, pitch_deg: float, yaw_deg: float) -> np.ndarray:
        """Convert ZYX Euler angles (degrees) to rotation matrix."""
        roll = math.radians(roll_deg)
        pitch = math.radians(pitch_deg)
        yaw = math.radians(yaw_deg)
        
        cr, sr = math.cos(roll), math.sin(roll)
        cp, sp = math.cos(pitch), math.sin(pitch)
        cy, sy = math.cos(yaw), math.sin(yaw)
        
        R = np.array([
            [cy*cp, cy*sp*sr - sy*cr, cy*sp*cr + sy*sr],
            [sy*cp, sy*sp*sr + cy*cr, sy*sp*cr - cy*sr],
            [  -sp,            cp*sr,            cp*cr],
        ], dtype=float)
        
        return R
    
    def _compute_grasp_rpy(self) -> np.ndarray:
        """Compute a fixed grasp RPY with forearm tilt (ported from Part_Sorting).

        Build the end-effector orientation from physical directions:

        - EE Z-axis = world-down, rotated toward the robot body by
          ``_forearm_tilt_deg`` (around base-frame -X).
        - EE X-axis = base-forward projected perpendicular to Z.
        - EE Y-axis = Z × X.

        This produces a human-like downward-pointing pose that is always
        IK-reachable because the orientation depends only on the robot base
        rotation and a fixed tilt — NOT on the target's yaw relative to the
        base. Result: no elbow flaring, no shoulder_yaw oscillation, and
        smooth transitions across all FSM states.
        """
        tilt_rad = math.radians(self._forearm_tilt_deg)

        # World-down direction expressed in the base frame.
        world_down_base = self._R_world_to_base @ np.array([0.0, 0.0, -1.0])

        # Tilt axis: rotate the grasp-Z toward the robot body (-X in base).
        tilt_axis_base = np.array([-1.0, 0.0, 0.0])
        R_tilt = self._axis_angle_to_rotation(tilt_axis_base, tilt_rad)
        z_grasp = R_tilt @ world_down_base
        z_grasp /= np.linalg.norm(z_grasp)

        # X-axis: project base-forward into the plane perpendicular to Z.
        base_forward = self._R_world_to_base @ np.array([1.0, 0.0, 0.0])
        x_grasp = base_forward - np.dot(base_forward, z_grasp) * z_grasp
        if np.linalg.norm(x_grasp) < 1e-6:
            x_grasp = self._R_world_to_base @ np.array([0.0, 1.0, 0.0])
            x_grasp = x_grasp - np.dot(x_grasp, z_grasp) * z_grasp
        x_grasp /= np.linalg.norm(x_grasp)

        y_grasp = np.cross(z_grasp, x_grasp)
        y_grasp /= np.linalg.norm(y_grasp)

        R_grasp = np.column_stack([x_grasp, y_grasp, z_grasp])
        if np.linalg.det(R_grasp) < 0:
            R_grasp[:, 1] = -R_grasp[:, 1]

        return self._rotation_matrix_to_rpy(R_grasp)

    @staticmethod
    def _axis_angle_to_rotation(axis: np.ndarray, angle: float) -> np.ndarray:
        """Rodrigues rotation formula: rotation matrix from axis + angle (rad)."""
        axis = axis / np.linalg.norm(axis)
        K = np.array([
            [0, -axis[2], axis[1]],
            [axis[2], 0, -axis[0]],
            [-axis[1], axis[0], 0],
        ])
        return np.eye(3) + math.sin(angle) * K + (1 - math.cos(angle)) * (K @ K)

    @staticmethod
    def _rotation_matrix_to_rpy(R: np.ndarray) -> np.ndarray:
        """Convert rotation matrix to RPY angles (roll, pitch, yaw)."""
        if abs(R[2, 0]) < 1.0:
            pitch = -math.asin(R[2, 0])
            roll = math.atan2(R[2, 1] / math.cos(pitch), R[2, 2] / math.cos(pitch))
            yaw = math.atan2(R[1, 0] / math.cos(pitch), R[0, 0] / math.cos(pitch))
        else:
            roll = math.atan2(R[2, 1], R[2, 2])
            yaw = math.atan2(R[1, 0], R[0, 0])
            pitch = -math.asin(R[2, 0])
        
        return np.array([roll, pitch, yaw], dtype=float)
