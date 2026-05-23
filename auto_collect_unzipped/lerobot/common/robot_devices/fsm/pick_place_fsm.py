"""Pick-and-place FSM state machine for Part_Sorting task.

Cycles through: APPROACH → DESCEND → GRASP → LIFT → TRANSPORT → LOWER → RELEASE → RETREAT
for each part, then advances to the next part or signals DONE.

The FSM outputs absolute end-effector target poses (xyzrpy in robot base frame)
and gripper commands, which are consumed by the physics callback to drive the robot
through the existing IK pipeline.
"""

import enum
import logging
import math
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# FSM states
# ---------------------------------------------------------------------------

class FSMState(enum.Enum):
    IDLE = "idle"
    READY = "ready"       # vertical lift with grasp RPY before any horizontal move
    APPROACH = "approach"
    DESCEND = "descend"
    GRASP = "grasp"
    LIFT = "lift"
    VERIFY_GRASP = "verify_grasp"  # Verify part picked up successfully
    TRANSPORT = "transport"
    LOWER = "lower"
    RELEASE = "release"
    RETREAT = "retreat"
    RETRY_APPROACH = "retry_approach"  # Retry grasping failed part
    DONE = "done"


# ---------------------------------------------------------------------------
# Grasp orientation helper
# ---------------------------------------------------------------------------

def _rotation_between_vectors(v_from: np.ndarray, v_to: np.ndarray) -> np.ndarray:
    """Compute minimal rotation matrix from *v_from* to *v_to* (Rodrigues)."""
    v_from = v_from / np.linalg.norm(v_from)
    v_to = v_to / np.linalg.norm(v_to)
    cross = np.cross(v_from, v_to)
    dot = np.dot(v_from, v_to)

    if dot > 0.9999:
        return np.eye(3)
    if dot < -0.9999:
        perp = np.array([1, 0, 0]) if abs(v_from[0]) < 0.9 else np.array([0, 1, 0])
        axis = np.cross(v_from, perp)
        axis /= np.linalg.norm(axis)
        return 2 * np.outer(axis, axis) - np.eye(3)

    skew = np.array([
        [0, -cross[2], cross[1]],
        [cross[2], 0, -cross[0]],
        [-cross[1], cross[0], 0],
    ])
    return np.eye(3) + skew + skew @ skew / (1 + dot)


# ---------------------------------------------------------------------------
# PickPlaceFSM
# ---------------------------------------------------------------------------

class PickPlaceFSM:
    """Finite state machine for Part_Sorting pick-and-place.

    Each call to :meth:`step` returns the current end-effector target and
    gripper command.  The caller (``PickPlaceFSMAgent``) is responsible for obtaining
    EE poses and part positions and passing them in.

    Args:
        config: Robot config object (WalkerS2SimRobotConfig) carrying FSM params.
        box_position_world: Box (target container) position in **world** frame [x,y,z].
        robot_position_world: Robot base position in **world** frame [x,y,z].
        robot_rotation_deg: Robot base rotation in degrees [roll, pitch, yaw] (ZYX).
    """

    def __init__(
        self,
        config,
        box_position_world: list | np.ndarray | None = None,
        robot_position_world: list | np.ndarray | None = None,
        robot_rotation_deg: list | np.ndarray | None = None,
        box_compartments: dict | None = None,
        part_types: list[str] | None = None,
    ):
        # Tolerances and timing from config
        self._config = config
        self._pos_tol = getattr(config, "fsm_pos_tol", 0.025)
        self._approach_height = getattr(config, "fsm_approach_height", 0.18)
        self._grasp_frames = getattr(config, "fsm_grasp_frames", 30)
        self._release_frames = getattr(config, "fsm_release_frames", 40)  # Increased from 20 to 40 frames (0.4s)
        self._rot_weight = getattr(config, "fsm_rot_weight", 0.1)
        self._max_ee_step = getattr(config, "fsm_max_ee_step", 0.005)
        self._descend_step = getattr(config, "fsm_descend_step", 0.005)
        self._ik_null_weight = getattr(config, "fsm_ik_null_weight", 0.30)
        self._forearm_tilt_deg = getattr(config, "fsm_forearm_tilt_deg", 35.0)
        self._max_forearm_tilt_deg = getattr(config, "fsm_max_forearm_tilt_deg", 85.0)  # Max tilt for near-box parts (increased to 85°)

        # Expose for caller (mobile_manipulator) to pass to IK solver
        self.ik_null_weight = self._ik_null_weight
        # Note: ik_rot_weight is now a property that varies by state
        # self.ik_rot_weight = self._rot_weight  # Removed, use @property instead

        # Scene geometry (world frame)
        self._box_position_world = np.asarray(
            box_position_world if box_position_world is not None else [1.2, 0.3, 1.05],
            dtype=float,
        )
        
        # Compartment-aware placement configuration
        self._box_compartments = box_compartments or {}
        self._part_types = part_types or []  # List of part types: ['part_a', 'part_b', ...]
        
        if self._box_compartments:
            logger.info(
                f"[FSM] Compartment mode enabled: "
                f"Part A → lower compartment, Part B → upper compartment"
            )
        
        self._robot_position_world = np.asarray(
            robot_position_world if robot_position_world is not None else [0.7, -0.2, 0.9],
            dtype=float,
        )
        rot_deg = np.asarray(
            robot_rotation_deg if robot_rotation_deg is not None else [0, 0, 90],
            dtype=float,
        )
        # Build world-to-base rotation matrix (Euler ZYX degrees → R)
        # The Euler angles describe the base orientation IN the world frame,
        # so R = R_base_to_world.  The world-to-base transform uses R.T.
        R_base_to_world = self._euler_zyx_to_rotation_matrix(*rot_deg)
        self._R_world_to_base = R_base_to_world.T
        self._R_base_to_world = R_base_to_world

        # Gripper widths (will be set by PickPlaceFSMAgent from robot interface)
        self.gripper_open_width: float = -0.0215
        self.gripper_close_width: float = 0.01

        # Internal state
        self._state = FSMState.IDLE
        self._current_part_index: int = 0
        self._frame_counter: int = 0
        self._log_counter: int = 0  # Dedicated counter for throttling info logs
        self._current_arm: str = "right"
        self._current_ee: Optional[dict] = None  # xyzrpy in base frame (cached)
        self._other_arm_target: Optional[np.ndarray] = None  # hold pose for idle arm

        # Cached targets — computed ONCE when entering a state, not every step.
        # This prevents the rotation from wobbling as the EE moves.
        self._cached_active_target: Optional[np.ndarray] = None  # xyzrpy in base frame
        self._cached_other_target: Optional[np.ndarray] = None   # xyzrpy in base frame
        self._cached_grip_cmd: float = 0.0

        # Fixed grasp RPY (computed once on first use)
        self._grasp_rpy: Optional[np.ndarray] = None



        # Part tracking (world positions, updated each step)
        self._part_positions_world: list[np.ndarray] = []
        self._num_parts: int = 0
        
        # Part type tracking for compartment placement
        self._current_part_type: Optional[str] = None  # 'part_a' or 'part_b'

        # Logging
        self._last_logged_state: Optional[FSMState] = None

        # State timeout: force-transition if convergence takes too long
        self._state_frame_counter: int = 0  # frames spent in current state
        self._state_timeout: int = getattr(config, "fsm_state_timeout_frames", 600)  # ~6s @ 100Hz

        # Grasp failure detection and retry
        self._failed_parts: dict = {}  # {part_index: retry_count}
        self._max_retries: int = getattr(config, "fsm_max_grasp_retries", 4)
        self._retry_queue: list = []  # Part indices pending retry
        self._skipped_parts: list = []  # Part indices skipped after max retries
        self._grasp_verify_frames: int = getattr(config, "fsm_grasp_verify_frames", 3)
        self._table_height: float = getattr(config, "fsm_table_height", 1.04)  # Table surface Z
        self._gripper_finger_width: Optional[float] = None  # Current gripper finger width for verification
        self._grasp_failed_in_verify: bool = False  # Track if current cycle failed grasp verification

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> FSMState:
        return self._state

    @property
    def is_task_done(self) -> bool:
        return self._state == FSMState.DONE

    @property
    def current_arm(self) -> str:
        return self._current_arm
    
    @property
    def current_part_index(self) -> int:
        return self._current_part_index
    
    @property
    def ik_rot_weight(self) -> float:
        """Return rotation weight based on current state.
        
        TRANSPORT, LOWER, RETREAT, and READY states use very low rotation weight (0.02) because
        the robot just needs to reach the position, not the exact orientation.
        RELEASE and other states use the default rotation weight (0.1).
        """
        if self._state in [FSMState.TRANSPORT, FSMState.LOWER, FSMState.RETREAT, FSMState.READY]:
            return 0.02  # Very low - position matters more
        return self._rot_weight
    
    @property
    def ik_step_size_multiplier(self) -> float:
        """Return step size multiplier based on current state.
        
        NOTE: The actual speed is primarily controlled by smooth_alpha (EMA smoothing).
        step_size is secondary. For TRANSPORT, we use both reduced step_size AND
        the caller should use a smaller smooth_alpha for very slow movement.
        """
        if self._state == FSMState.TRANSPORT:
            return 0.15  # 15% step size for TRANSPORT
        elif self._state in [FSMState.LOWER, FSMState.RETREAT]:
            return 0.4  # 40% step size
        elif self._state in [FSMState.APPROACH, FSMState.LIFT]:
            return 0.6  # 60% step size
        return 1.0  # Normal speed for other states
    
    @property
    def fsm_smooth_alpha_override(self) -> Optional[float]:
        """Return smooth_alpha override based on current state.
        
        This is the PRIMARY speed control. Lower alpha = slower/smoother movement.
        EMA formula: new_pos = alpha * target + (1 - alpha) * current_pos
        
        TRANSPORT uses 0.03 (3% per step) for extremely slow, smooth motion.
        Default is 0.10 (10% per step).
        """
        if self._state == FSMState.TRANSPORT:
            return 0.03  # 3% per step - extremely slow and smooth for part transport
        elif self._state in [FSMState.LOWER, FSMState.RETREAT]:
            return 0.06  # 6% per step - slower for smooth placement and retreat
        return None  # Use default smooth_alpha (0.10) for other states
    
    @property
    def current_forearm_tilt_deg(self) -> float:
        """Return dynamic forearm tilt angle based on part distance to box.
        
        For parts near the box, increase tilt angle to avoid forearm collision.
        The closer the part is to the box, the larger the tilt angle.
        
        Returns:
            Tilt angle in degrees (35° for far parts, up to 75° for near-box parts)
        """
        part_world = self._get_current_part_world()
        if part_world is None:
            return self._forearm_tilt_deg
        
        # Calculate distance to box
        distance_to_box = np.linalg.norm(part_world[:2] - self._box_position_world[:2])
        
        # Debug: always log distance for every part
        logger.info(
            f"[FSM-TILT] Part position: {part_world[:2]}, Box position: {self._box_position_world[:2]}, "
            f"distance={distance_to_box:.3f}m"
        )
        
        # If part is near box (< 35cm), increase tilt angle
        if distance_to_box < 0.35:  # Increased threshold from 25cm to 35cm
            # Linear interpolation: closer = more tilt
            # distance_to_box: 0.35m -> base tilt (35°)
            # distance_to_box: 0.0m -> max tilt (85°)
            tilt_range = self._max_forearm_tilt_deg - self._forearm_tilt_deg
            tilt_increase = tilt_range * (0.35 - distance_to_box) / 0.35
            current_tilt = self._forearm_tilt_deg + tilt_increase
            
            logger.info(
                f"[FSM-TILT] >>> Part near box: dist={distance_to_box:.3f}m, "
                f"tilt={current_tilt:.1f}° (base={self._forearm_tilt_deg}°, max={self._max_forearm_tilt_deg}°)"
            )
            return current_tilt
        
        return self._forearm_tilt_deg

    def start(self, num_parts: int = 4) -> None:
        """Start the FSM (transition from IDLE to READY for the first part)."""
        if self._state != FSMState.IDLE:
            return
        self._num_parts = num_parts
        self._current_part_index = 0
        self._transition_to(FSMState.READY)
        logger.info(
            f"[FSM] Started — {self._num_parts} parts to sort, "
            f"first arm={self._current_arm}"
        )

    def reset(self) -> None:
        """Reset FSM to IDLE for a new episode."""
        self._state = FSMState.IDLE
        self._current_part_index = 0
        self._current_arm = "right"  # reset arm selection for new episode
        self._frame_counter = 0
        self._state_frame_counter = 0
        self._current_ee = None
        self._other_arm_target = None
        self._cached_active_target = None
        self._cached_other_target = None
        self._cached_grip_cmd = 0.0
        self._grasp_rpy = None
        self._part_positions_world = []
        self._num_parts = 0
        self._last_logged_state = None
        self._current_part_type = None  # reset part type tracking
        
        # Reset retry tracking
        self._failed_parts = {}
        self._retry_queue = []
        self._skipped_parts = []
        self._gripper_finger_width = None
        self._grasp_failed_in_verify = False

    def step(
        self,
        ee_poses: dict[str, np.ndarray] | None,
        part_poses_world: list[dict] | None,
    ) -> tuple[
        Optional[np.ndarray],  # left_target_xyzrpy (base frame)
        Optional[np.ndarray],  # right_target_xyzrpy (base frame)
        float,                 # left_gripper_cmd (1=open, -1=close, 0=hold)
        float,                 # right_gripper_cmd
        bool,                  # is_done
    ]:
        """Advance one physics step.

        Returns:
            (left_target, right_target, left_grip, right_grip, is_done)
            Targets are 6D xyzrpy in robot base frame, or None to hold position.
        """
        # Cache current EE poses
        if ee_poses is not None:
            self._current_ee = ee_poses

        # Update part positions
        if part_poses_world is not None:
            new_count = len(part_poses_world)
            if new_count != self._num_parts:
                logger.info(
                    f"[FSM] Part count changed: {self._num_parts} → {new_count} "
                    f"(current_part_index={self._current_part_index})"
                )
            self._part_positions_world = [
                np.asarray(p["position"], dtype=float) for p in part_poses_world
            ]
            
            # CRITICAL: Check if any part has fallen off the table (Z too low)
            # If so, mark it as skipped to avoid infinite retry attempts
            for idx, pos in enumerate(self._part_positions_world):
                if pos[2] < 0.85:  # Z < 0.85m indicates part fell off table
                    if idx not in self._skipped_parts:
                        self._skipped_parts.append(idx)
                        logger.warning(
                            f"[FSM] Part {idx} fell off table (Z={pos[2]:.3f}m < 0.85m), "
                            f"marking as skipped"
                        )
                    # Remove from retry queue if present
                    if idx in self._retry_queue:
                        self._retry_queue.remove(idx)
                        logger.info(f"[FSM] Removed fallen part {idx} from retry queue")
                    # Remove from failed_parts if present
                    if idx in self._failed_parts:
                        del self._failed_parts[idx]
            
            # Dynamically grow _num_parts if more parts appear on the table
            # (handles the case where FSMAgent.start() queried poses before all
            # parts were loaded, getting an incomplete count)
            if len(self._part_positions_world) > self._num_parts:
                old = self._num_parts
                self._num_parts = len(self._part_positions_world)
                if old > 0:
                    logger.info(
                        f"[FSM] num_parts updated: {old} → {self._num_parts} "
                        f"(detected {len(self._part_positions_world)} parts on table)"
                    )

        # Default outputs
        left_target = None
        right_target = None
        left_grip = 0.0
        right_grip = 0.0

        if self._state == FSMState.IDLE or self._state == FSMState.DONE:
            return left_target, right_target, left_grip, right_grip, self.is_task_done

        # Lazy target computation: if cached target is None (e.g. part positions
        # weren't available when entering the state), compute it now.
        if self._cached_active_target is None and self._part_positions_world:
            self._compute_and_cache_target()

        # Use cached targets (computed once when entering state)
        if self._cached_active_target is not None:
            target_base = self._cached_active_target
        else:
            target_base = None

        grip_cmd = self._cached_grip_cmd

        # Assign target to active arm, hold position for the other
        if self._current_arm == "left":
            left_target = target_base
            right_target = self._cached_other_target
            left_grip = grip_cmd
        else:
            right_target = target_base
            left_target = self._cached_other_target
            right_grip = grip_cmd

        # Check transition (may update _cached_grip_cmd for new state)
        self._check_transition()

        # Re-read grip command after potential state transition
        grip_cmd = self._cached_grip_cmd
        if self._current_arm == "left":
            left_grip = grip_cmd
        else:
            right_grip = grip_cmd

        return left_target, right_target, left_grip, right_grip, self.is_task_done

    # ------------------------------------------------------------------
    # State target computation
    # ------------------------------------------------------------------

    def _compute_and_cache_target(self) -> None:
        """Compute active arm target + idle arm hold pose + grip command.

        Called ONCE when entering a new state (from _transition_to),
        not every step.  This prevents rotation from wobbling.
        """
        # Cache the idle arm's current position so it holds still
        self._cache_other_arm_target()
        self._cached_other_target = self._other_arm_target

        # Compute grasp RPY dynamically based on current part position
        # This allows forearm tilt angle to adjust for near-box parts
        self._grasp_rpy = self._compute_grasp_rpy()

        # Compute position + rotation for active arm
        pos, grip = self._state_position_and_grip()
        if pos is not None:
            # All states use the fixed grasp RPY (forearm tilted 30° up).
            # The READY state first lifts the arm vertically into this RPY,
            # so subsequent states can move horizontally without the forearm
            # dropping into the table.
            rpy = self._grasp_rpy
            self._cached_active_target = np.concatenate([pos, rpy])
            
            # Log target computation for debugging TRANSPORT state
            if self._state in [FSMState.TRANSPORT, FSMState.LOWER, FSMState.RELEASE]:
                logger.info(
                    f"[FSM-TARGET] Cached target for {self._state.value}: "
                    f"pos={np.round(pos, 3)}, arm={self._current_arm}"
                )
        else:
            self._cached_active_target = None
            logger.warning(
                f"[FSM-TARGET] Failed to compute target for {self._state.value}! "
                f"_state_position_and_grip returned None."
            )
        self._cached_grip_cmd = grip

    def _state_position_and_grip(self) -> tuple[Optional[np.ndarray], float]:
        """Return (position_base_3d, grip_cmd) for the current state.

        Gripper convention (matching physics callback):
            +1.0 = close (move fingers toward close width)
            -1.0 = open  (move fingers toward open width)
            0.0  = hold current position
        """
        state = self._state
        # Height offsets: must clear part/box height + gripper length to avoid
        # hitting the table or box rim before the fingers surround the object.
        # Walker S2 gripper ~8cm long; with 30° tilt the vertical projection is
        # ~7cm.  Part height is ~5-6cm.  8cm gives ~1-2cm clearance above part top.
        GRASP_HEIGHT = getattr(self._config, "fsm_grasp_height", 0.05)  # Lowered from 0.07 to 0.05 for full table contact
        DROP_HEIGHT  = getattr(self._config, "fsm_drop_height",  0.08)
        
        # For retry attempts, adjust grasp height slightly lower (2mm) to compensate
        # for potential positioning errors
        is_retry = state in (FSMState.RETRY_APPROACH, FSMState.DESCEND) and self._retry_queue
        grasp_height_adjustment = -0.002 if is_retry else 0.0
        
        if state == FSMState.READY:
            return self._ready_pos(), -1.0  # open gripper
        elif state == FSMState.APPROACH or state == FSMState.RETRY_APPROACH:
            return self._above_part_pos(self._approach_height), -1.0  # open gripper early
        elif state == FSMState.DESCEND:
            return self._above_part_pos(GRASP_HEIGHT + grasp_height_adjustment), -1.0  # keep open
        elif state == FSMState.GRASP:
            return self._above_part_pos(GRASP_HEIGHT + grasp_height_adjustment), -1.0   # start OPEN — will close after settle period
        elif state == FSMState.LIFT:
            return self._above_part_pos(self._approach_height), 1.0   # keep closed
        elif state == FSMState.VERIFY_GRASP:
            # Hold position during verification
            return self._above_part_pos(self._approach_height), 1.0   # keep closed
        elif state == FSMState.TRANSPORT:
            return self._above_box_pos(self._approach_height), 1.0   # keep closed
        elif state == FSMState.LOWER:
            return self._above_box_pos(DROP_HEIGHT), 1.0  # keep closed until RELEASE
        elif state == FSMState.RELEASE:
            return self._above_box_pos(DROP_HEIGHT), -1.0  # open gripper here
        elif state == FSMState.RETREAT:
            # If grasp failed in verify, retreat from part position (not box)
            if self._grasp_failed_in_verify:
                return self._above_part_pos(self._approach_height), -1.0  # retreat from part
            return self._above_box_pos(self._approach_height), -1.0  # keep open
        return None, 0.0

    def _ready_pos(self) -> Optional[np.ndarray]:
        """Compute a safe ready position: current XY, high Z, grasp RPY.

        This lifts the arm straight up from its current pose into the grasp
        orientation (forearm tilted up) BEFORE any horizontal movement, so the
        forearm never sweeps across the table.

        Returns None if the current EE is not yet available — the lazy
        computation in step() will retry on the next frame.
        """
        ee = self._current_ee.get(self._current_arm) if self._current_ee else None
        if ee is not None and len(ee) >= 3:
            # Keep current XY, set Z to approach_height + safety margin
            ready_z = self._approach_height + 0.10  # extra 10cm above approach for elbow clearance
            return np.array([ee[0], ee[1], ready_z])
        # Don't fall back to part position — that would create a far-away
        # target that causes IK failure.  Return None and let the lazy
        # computation retry when the EE becomes available.
        logger.info(f"[FSM] _ready_pos: EE not available for arm={self._current_arm}, deferring target computation")
        return None

    def _above_part_pos(self, height_offset: float) -> Optional[np.ndarray]:
        """Position above the current part in base frame.
        
        For right arm: shifts target slightly in -Y direction to compensate for
        gripper tilt. Since the gripper is tilted, the finger tips are offset
        from the target center. This offset ensures the finger tips align with
        the part's center of mass.
        """
        part_world = self._get_current_part_world()
        if part_world is None:
            return None
        
        base_pos = self._world_pos_to_base(part_world, height_offset)
        
        # For right arm, shift target slightly toward body (-Y in base frame) to
        # compensate for gripper tilt. The gripper fingertips are offset from
        # the target center due to the tilt angle.
        if self._current_arm == 'right':
            gripper_tilt_offset = 0.01  # 1cm offset to compensate for tilt
            base_pos[1] -= gripper_tilt_offset  # Shift in -Y direction (toward body)
        
        return base_pos

    def _above_box_pos(self, height_offset: float) -> np.ndarray:
        """Position above the box in base frame.
        
        If compartments are configured, routes Part A to lower compartment
        and Part B to upper compartment based on current part type.
        """
        # Determine target position based on part type and compartment config
        target_world = self._get_placement_position_for_current_part()
        
        # Log the target for debugging
        part_type = self._get_current_part_type()
        logger.info(
            f"[FSM-TARGET] _above_box_pos: part_type={part_type}, "
            f"target_world={target_world}, height_offset={height_offset}"
        )
        
        result = self._world_pos_to_base(target_world, height_offset)
        logger.info(f"[FSM-TARGET] _above_box_pos result (base frame): {result}")
        
        # CRITICAL FIX: Validate target is within reachable workspace
        # If target is too far, use a safer intermediate position
        workspace_bounds = {
            'x': (0.25, 0.75),  # Conservative bounds for right arm
            'y': (-0.55, 0.15),
            'z': (0.25, 0.65)
        }
        
        if (result[0] < workspace_bounds['x'][0] or result[0] > workspace_bounds['x'][1] or
            result[1] < workspace_bounds['y'][0] or result[1] > workspace_bounds['y'][1] or
            result[2] < workspace_bounds['z'][0] or result[2] > workspace_bounds['z'][1]):
            
            logger.warning(
                f"[FSM-TARGET] Target {np.round(result, 3)} outside safe workspace! "
                f"Clamping to bounds."
            )
            # Clamp to workspace bounds
            result[0] = np.clip(result[0], workspace_bounds['x'][0], workspace_bounds['x'][1])
            result[1] = np.clip(result[1], workspace_bounds['y'][0], workspace_bounds['y'][1])
            result[2] = np.clip(result[2], workspace_bounds['z'][0], workspace_bounds['z'][1])
            logger.info(f"[FSM-TARGET] Clamped target: {result}")
        
        return result
    
    def _get_placement_position_for_current_part(self) -> np.ndarray:
        """Get the placement position for the current part based on its type.
        
        Returns:
            World position [x, y, z] for placement
            - Part A → lower compartment (Y < box_center_y)
            - Part B → upper compartment (Y > box_center_y)
        """
        # If no compartment config, use default box center
        if not self._box_compartments:
            return self._box_position_world
        
        # Determine current part type
        part_type = self._get_current_part_type()
        
        if part_type == 'part_a':
            # Part A goes to LOWER compartment
            placement_pos = np.asarray(
                self._box_compartments.get('lower_compartment', {}).get('center', self._box_position_world),
                dtype=float
            )
            logger.debug(f"[FSM] Part A → lower compartment: {placement_pos}")
        elif part_type == 'part_b':
            # Part B goes to UPPER compartment
            placement_pos = np.asarray(
                self._box_compartments.get('upper_compartment', {}).get('center', self._box_position_world),
                dtype=float
            )
            # CRITICAL: Move Part B 2cm inward along Y-axis to avoid box edge
            # Negative Y moves away from the edge (toward box interior)
            placement_pos[1] -= 0.02  # 2cm offset
            logger.debug(f"[FSM] Part B → upper compartment: {placement_pos} (with -2cm Y offset)")
        else:
            # Fallback to box center if type unknown
            placement_pos = self._box_position_world
            logger.warning(f"[FSM] Unknown part type '{part_type}', using default box position")
        
        return placement_pos
    
    def _get_current_part_type(self) -> Optional[str]:
        """Get the type of the current part being processed.
        
        Returns:
            'part_a', 'part_b', or None if not available
        """
        # If we have explicit part_types list, use it
        if self._part_types and self._current_part_index < len(self._part_types):
            part_type = self._part_types[self._current_part_index]
            logger.debug(
                f"[FSM] _get_current_part_type: index={self._current_part_index}, "
                f"type={part_type}, part_types_list={self._part_types}"
            )
            return part_type
        
        # Fallback: try to infer from part position or return None
        logger.warning(
            f"[FSM] _get_current_part_type: No part types available! "
            f"current_index={self._current_part_index}, part_types={self._part_types}"
        )
        return None

    def _world_pos_to_base(self, world_xyz: np.ndarray, height_offset: float) -> np.ndarray:
        """Convert world XYZ to base-frame XYZ with a height offset (up in base Z)."""
        base = self._world_to_base(world_xyz)
        base[2] += height_offset
        return base

    def _compute_grasp_rpy(self) -> np.ndarray:
        """Compute a fixed grasp RPY with forearm tilt.

        The EE Z-axis points mostly down (-Z world) but is tilted toward the
        robot body by ``_forearm_tilt_deg`` so the forearm angles upward
        instead of being horizontal.  This prevents the forearm from
        colliding with parts / box on the table.
        
        For parts near the box, the tilt angle is dynamically increased to
        avoid forearm collision.

        Convention (Walker S2 EE frame):
            Z-axis = gripper approach direction
            X-axis = forward along forearm
        """
        # Use dynamic tilt angle based on part distance to box
        current_tilt = self.current_forearm_tilt_deg
        tilt_rad = math.radians(current_tilt)
        
        # Debug: log every time this function is called
        logger.info(f"[FSM-RPY] _compute_grasp_rpy called, tilt={current_tilt:.1f}°")

        # In base frame, world-down direction
        world_down_base = self._R_world_to_base @ np.array([0.0, 0.0, -1.0])

        # Tilt direction: from target toward robot body (in base frame).
        # In base frame the robot body is behind the base origin, so we tilt
        # the Z-axis toward -X_base (backward toward the robot body).
        tilt_axis_base = np.array([-1.0, 0.0, 0.0])  # rotate toward robot body

        # Apply tilt: rotate world_down around tilt_axis by tilt_rad
        R_tilt = self._axis_angle_to_rotation(tilt_axis_base, tilt_rad)
        z_grasp = R_tilt @ world_down_base
        z_grasp /= np.linalg.norm(z_grasp)

        # X-axis: perpendicular to Z, in the plane of Z and base_forward
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

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def _check_transition(self) -> None:
        """Check if the current state's transition condition is met.

        Convergence-based states (READY, APPROACH, DESCEND, LIFT, TRANSPORT,
        LOWER, RETREAT) have a timeout.  If the arm doesn't converge within
        fsm_state_timeout_frames, force-transition so the FSM doesn't get stuck.
        """
        # Don't count timeout frames while target is still being deferred
        # (e.g., _ready_pos returned None because EE wasn't available yet)
        target = self._cached_active_target
        if target is None and self._state not in (FSMState.IDLE, FSMState.DONE, FSMState.GRASP, FSMState.RELEASE):
            # Target missing — recompute lazily
            self._compute_and_cache_target()
            target = self._cached_active_target

        if target is not None:
            self._state_frame_counter += 1
        timed_out = self._state_frame_counter >= self._state_timeout
        if self._state == FSMState.READY:
            # CRITICAL: Check if current part has fallen off the table
            if self._current_part_index < len(self._part_positions_world):
                part_z = self._part_positions_world[self._current_part_index][2]
                if part_z < 0.85:  # Part fell off table
                    logger.warning(
                        f"[FSM-READY] Part {self._current_part_index} fell off table (Z={part_z:.3f}m), "
                        f"skipping"
                    )
                    # Mark as skipped and move to next part
                    if self._current_part_index not in self._skipped_parts:
                        self._skipped_parts.append(self._current_part_index)
                    # Remove from retry queue if present
                    if self._current_part_index in self._retry_queue:
                        self._retry_queue.remove(self._current_part_index)
                    if self._current_part_index in self._failed_parts:
                        del self._failed_parts[self._current_part_index]
                    
                    self._current_part_index += 1
                    if self._current_part_index >= self._num_parts:
                        # All parts done
                        if self._retry_queue:
                            # Process retry queue
                            retry_idx = self._retry_queue.pop(0)
                            if retry_idx in self._failed_parts:
                                self._current_part_index = retry_idx
                                self._select_arm_for_current_part()
                                self._transition_to(FSMState.RETRY_APPROACH)
                            else:
                                self._transition_to(FSMState.DONE)
                        else:
                            self._transition_to(FSMState.DONE)
                    else:
                        # Move to next part
                        self._select_arm_for_current_part()
                        self._transition_to(FSMState.READY)
                    return
            
            # READY state: transition to high Z position, needs relaxed tolerance
            # since it's moving from RETREAT position which may be far away
            ready_tol = self._pos_tol * 2.0  # 2x tolerance for ready position
            if self._is_converged_custom(target, ready_tol) or timed_out:
                if timed_out:
                    logger.warning(f"[FSM] READY timed out after {self._state_frame_counter} frames — forcing transition")
                self._transition_to(FSMState.APPROACH)

        elif self._state == FSMState.APPROACH:
            if self._is_converged(target) or timed_out:
                if timed_out:
                    logger.warning(f"[FSM] APPROACH timed out after {self._state_frame_counter} frames — forcing transition")
                self._transition_to(FSMState.DESCEND)

        elif self._state == FSMState.DESCEND:
            if self._is_converged(target) or timed_out:
                if timed_out:
                    logger.warning(f"[FSM] DESCEND timed out after {self._state_frame_counter} frames — forcing transition")
                self._transition_to(FSMState.GRASP)
                self._frame_counter = 0

        elif self._state == FSMState.GRASP:
            self._frame_counter += 1
            # After settle period: switch grip from open to close
            settle_frames = getattr(self._config, "fsm_grasp_settle_frames", 80)
            if self._frame_counter == settle_frames:
                self._cached_grip_cmd = 1.0  # close gripper after settling
                logger.info(f"[FSM] GRASP settle done ({settle_frames} frames), closing gripper")
            if self._frame_counter >= self._grasp_frames:
                self._transition_to(FSMState.LIFT)

        elif self._state == FSMState.LIFT:
            if self._is_converged(target) or timed_out:
                if timed_out:
                    logger.warning(f"[FSM] LIFT timed out after {self._state_frame_counter} frames — forcing transition")
                self._transition_to(FSMState.VERIFY_GRASP)  # Verify grasp before transport

        elif self._state == FSMState.VERIFY_GRASP:
            self._frame_counter += 1
            if self._frame_counter >= self._grasp_verify_frames:
                # Run dual-method grasp verification
                grasp_success = self._verify_grasp_success()
                
                if grasp_success:
                    logger.info("[FSM-VERIFY] Grasp verification PASSED")
                    self._grasp_failed_in_verify = False
                    
                    # CRITICAL: If this part was previously marked as failed but now succeeded,
                    # remove it from failed_parts to prevent is_grasp_retry from staying True
                    if self._current_part_index in self._failed_parts:
                        logger.info(
                            f"[FSM-RETRY] Part {self._current_part_index} succeeded on retry, "
                            f"clearing failure flag"
                        )
                        del self._failed_parts[self._current_part_index]
                    
                    self._transition_to(FSMState.TRANSPORT)
                else:
                    # Grasp failed - decide whether to retry
                    part_idx = self._current_part_index
                    current_retries = self._failed_parts.get(part_idx, 0)
                    
                    if current_retries < self._max_retries:
                        # Will retry this part later
                        self._failed_parts[part_idx] = current_retries + 1
                        
                        # CRITICAL: Only add to retry queue if not already queued
                        # This prevents duplicate entries causing infinite loops
                        if part_idx not in self._retry_queue:
                            self._retry_queue.append(part_idx)
                            logger.warning(
                                f"[FSM-RETRY] Part {part_idx} grasp FAILED, "
                                f"queued for retry (attempt {current_retries + 1}/{self._max_retries})"
                            )
                        else:
                            logger.warning(
                                f"[FSM-RETRY] Part {part_idx} grasp FAILED again, "
                                f"already in retry queue (attempt {current_retries + 1}/{self._max_retries})"
                            )
                    else:
                        # Max retries exceeded, skip this part
                        self._skipped_parts.append(part_idx)
                        logger.error(
                            f"[FSM-RETRY] Part {part_idx} FAILED after {self._max_retries} retries, skipping"
                        )
                    
                    # Skip TRANSPORT/LOWER/RELEASE - directly retreat since gripper is empty
                    self._grasp_failed_in_verify = True
                    self._transition_to(FSMState.RETREAT)

        elif self._state == FSMState.TRANSPORT:
            # TRANSPORT state: move to box with much higher tolerance
            # The robot just needs to get close to the box, exact position
            # is refined in LOWER state. 2.0x tolerance helps IK converge.
            transport_tol = self._pos_tol * 2.0  # 100% more lenient
            if self._is_converged_custom(target, transport_tol) or timed_out:
                if timed_out:
                    logger.warning(
                        f"[FSM] TRANSPORT timed out after {self._state_frame_counter} frames — forcing transition. "
                        f"This usually means the IK solver cannot reach the target. "
                        f"Target: {np.round(target[:3], 3) if target is not None else 'None'}"
                    )
                self._transition_to(FSMState.LOWER)

        elif self._state == FSMState.LOWER:
            # LOWER state: needs relaxed tolerance like TRANSPORT
            # The precision is less critical since we're just approaching release height
            lower_tol = self._pos_tol * 2.0  # Same as TRANSPORT: 0.10m
            if self._is_converged_custom(target, lower_tol) or timed_out:
                if timed_out:
                    logger.warning(f"[FSM] LOWER timed out after {self._state_frame_counter} frames — forcing transition")
                self._transition_to(FSMState.RELEASE)
                self._frame_counter = 0

        elif self._state == FSMState.RELEASE:
            self._frame_counter += 1
            if self._frame_counter >= self._release_frames:
                self._transition_to(FSMState.RETREAT)

        elif self._state == FSMState.RETREAT:
            # RETREAT state: also needs relaxed tolerance for moving away
            retreat_tol = self._pos_tol * 2.0  # Same as TRANSPORT/LOWER
            if self._is_converged_custom(target, retreat_tol) or timed_out:
                if timed_out:
                    logger.warning(f"[FSM] RETREAT timed out after {self._state_frame_counter} frames — forcing transition")
                
                # CRITICAL FIX: Handle part index based on grasp result
                if self._grasp_failed_in_verify:
                    # Grasp failed - DO NOT advance index, will retry same part via RETRY_APPROACH
                    # The retry logic below will handle whether to retry or skip
                    logger.info(
                        f"[FSM-RETREAT] Grasp failed for part {self._current_part_index}, "
                        f"checking retry queue"
                    )
                    # Don't increment - keep current_part_index for retry
                else:
                    # Grasp succeeded: advance to next part
                    self._current_part_index += 1
                    logger.info(f"[FSM-RETREAT] Grasp succeeded, advancing to part {self._current_part_index}")
                
                logger.info(
                    f"[FSM] RETREAT done: part_index={self._current_part_index}, "
                    f"num_parts={self._num_parts}, "
                    f"part_positions_count={len(self._part_positions_world)}, "
                    f"retry_queue={self._retry_queue}, "
                    f"grasp_failed={self._grasp_failed_in_verify}"
                )
                
                if self._current_part_index >= self._num_parts:
                    # All primary parts processed, check retry queue
                    logger.info(
                        f"[FSM] All {self._num_parts} parts processed, "
                        f"retry_queue={self._retry_queue}, "
                        f"current_part_index={self._current_part_index}"
                    )
                    if self._retry_queue:
                        # Pop first failed part for retry
                        retry_idx = self._retry_queue.pop(0)
                        
                        # CRITICAL: Check if part is still in failed_parts
                        # It might have succeeded on a previous retry but not been removed from queue
                        if retry_idx not in self._failed_parts:
                            logger.warning(
                                f"[FSM-RETRY] Part {retry_idx} in retry_queue but not in failed_parts, "
                                f"skipping (already succeeded or invalid)"
                            )
                            # Continue to next retry or finish
                            if self._retry_queue:
                                # Try next part in queue - need to stay in RETREAT to process it
                                # Reset to process next retry immediately
                                retry_idx = self._retry_queue.pop(0)
                                if retry_idx not in self._failed_parts:
                                    logger.error(f"[FSM-RETRY] Multiple invalid entries in retry_queue, transitioning to DONE")
                                    self._transition_to(FSMState.DONE)
                                    return
                            else:
                                self._transition_to(FSMState.DONE)
                                return
                        
                        self._current_part_index = retry_idx
                        logger.info(
                            f"[FSM-RETRY] Retrying part {retry_idx} "
                            f"(attempt {self._failed_parts[retry_idx]}/{self._max_retries})"
                        )
                        self._select_arm_for_current_part()
                        self._transition_to(FSMState.RETRY_APPROACH)
                    else:
                        # No more retries, truly done
                        self._transition_to(FSMState.DONE)
                        if self._skipped_parts:
                            logger.warning(
                                f"[FSM] All parts processed — DONE (skipped {len(self._skipped_parts)} parts: {self._skipped_parts})"
                            )
                        else:
                            logger.info("[FSM] All parts sorted — DONE")
                else:
                    # More parts to process OR retry current part
                    if self._grasp_failed_in_verify:
                        # Grasp failed - check if we should retry or skip
                        part_idx = self._current_part_index
                        current_retries = self._failed_parts.get(part_idx, 0)
                        
                        if current_retries < self._max_retries:
                            # Retry this part immediately via RETRY_APPROACH
                            logger.info(
                                f"[FSM-RETREAT] Part {part_idx} failed, retrying immediately "
                                f"(attempt {current_retries}/{self._max_retries})"
                            )
                            # Remove from retry queue since we're retrying now
                            if part_idx in self._retry_queue:
                                self._retry_queue.remove(part_idx)
                            
                            self._select_arm_for_current_part()
                            self._transition_to(FSMState.RETRY_APPROACH)
                        else:
                            # Max retries exceeded, skip this part
                            logger.warning(
                                f"[FSM-RETREAT] Part {part_idx} failed after {current_retries} retries, skipping"
                            )
                            # Advance to next part
                            self._current_part_index += 1
                            self._grasp_failed_in_verify = False
                            
                            if self._current_part_index >= self._num_parts:
                                # All parts done
                                if self._retry_queue:
                                    retry_idx = self._retry_queue.pop(0)
                                    if retry_idx in self._failed_parts:
                                        self._current_part_index = retry_idx
                                        self._select_arm_for_current_part()
                                        self._transition_to(FSMState.RETRY_APPROACH)
                                    else:
                                        self._transition_to(FSMState.DONE)
                                else:
                                    self._transition_to(FSMState.DONE)
                            else:
                                self._select_arm_for_current_part()
                                self._transition_to(FSMState.READY)
                    else:
                        # Grasp succeeded - normal flow to next part
                        logger.info(
                            f"[FSM] Transitioning from RETREAT to READY for part {self._current_part_index}/{self._num_parts}"
                        )
                        # Reset grasp failure flag for next part
                        self._grasp_failed_in_verify = False
                        self._select_arm_for_current_part()
                        logger.info(
                            f"[FSM] Selected arm={self._current_arm} for part {self._current_part_index}, "
                            f"part_position={self._part_positions_world[self._current_part_index] if self._current_part_index < len(self._part_positions_world) else 'N/A'}"
                        )
                        self._transition_to(FSMState.READY)

        elif self._state == FSMState.RETRY_APPROACH:
            # RETRY_APPROACH: Same as APPROACH but will use adjusted params in _state_position_and_grip
            if self._is_converged(target) or timed_out:
                if timed_out:
                    logger.warning(f"[FSM] RETRY_APPROACH timed out after {self._state_frame_counter} frames — forcing transition")
                self._transition_to(FSMState.DESCEND)

    def _transition_to(self, new_state: FSMState) -> None:
        """Transition to a new state with logging."""
        old = self._state
        self._state = new_state
        self._frame_counter = 0
        self._state_frame_counter = 0  # reset state timeout counter

        if new_state != old:
            logger.info(f"[FSM] {old.value} -> {new_state.value}")

        # Compute and cache the target for the new state (once)
        if new_state not in (FSMState.IDLE, FSMState.DONE):
            self._compute_and_cache_target()
        else:
            self._cached_active_target = None
            self._cached_grip_cmd = 0.0

    # ------------------------------------------------------------------
    # Convergence check
    # ------------------------------------------------------------------

    def _is_converged(self, target: Optional[np.ndarray]) -> bool:
        """Check if the active arm's EE has converged to *target* (position only)."""
        return self._is_converged_custom(target, self._pos_tol)
    
    def _is_converged_custom(self, target: Optional[np.ndarray], tolerance: float) -> bool:
        """Check convergence with custom tolerance.
        
        Args:
            target: Target position [x, y, z, roll, pitch, yaw]
            tolerance: Position tolerance in meters
            
        Returns:
            True if position error < tolerance
        """
        if target is None or self._current_ee is None:
            return False
        current = self._current_ee.get(self._current_arm)
        if current is None:
            return False
        pos_err = np.linalg.norm(current[:3] - target[:3])
        converged = pos_err < tolerance
        # Log every ~0.5s (15 frames) for convergence-critical states
        self._log_counter += 1
        if self._log_counter % 15 == 0:
            logger.info(
                f"[FSM-CONV] {self._state.value} arm={self._current_arm}: "
                f"ee={np.round(current[:3], 4)}, target={np.round(target[:3], 4)}, "
                f"err={pos_err:.4f}m, tol={tolerance}, "
                f"{'CONVERGED' if converged else 'NOT converged'}"
            )
        return converged

    # ------------------------------------------------------------------
    # Arm selection
    # ------------------------------------------------------------------

    def _select_arm_for_current_part(self) -> None:
        """Select arm for the current part.

        Uses the configured preferred arm (default: right) because the left
        arm IK solver requires separate tuning.  Can be overridden via
        fsm_preferred_arm config to "auto" for X-based selection.
        """
        preferred = getattr(self._config, "fsm_preferred_arm", "right")
        if preferred == "auto":
            part_world = self._get_current_part_world()
            if part_world is None:
                self._current_arm = "right"
                return
            if part_world[0] > self._robot_position_world[0]:
                self._current_arm = "right"
            else:
                self._current_arm = "left"
        else:
            self._current_arm = preferred

    # ------------------------------------------------------------------
    # Helper: cache the non-active arm's current position
    # ------------------------------------------------------------------

    def _cache_other_arm_target(self) -> None:
        """Store the idle arm's current EE pose so it holds position."""
        if self._current_ee is None:
            return
        other = "right" if self._current_arm == "left" else "left"
        other_pose = self._current_ee.get(other)
        if other_pose is not None:
            self._other_arm_target = other_pose.copy()

    # ------------------------------------------------------------------
    # Helper: get current part world position
    # ------------------------------------------------------------------

    def _get_current_part_world(self) -> Optional[np.ndarray]:
        """Return world position of the current part, or None."""
        if self._current_part_index < len(self._part_positions_world):
            return self._part_positions_world[self._current_part_index]
        return None

    def _verify_grasp_success(self) -> bool:
        """Verify if part was successfully grasped using dual methods.
        
        Returns:
            True if grasp appears successful, False if part likely still on table
        """
        # Method 1: Check gripper position (if available from EE data)
        gripper_ok = self._check_gripper_grasp_state()
        
        # Method 2: Check if part is still on table
        part_on_table = self._check_part_still_on_table()
        
        # If either method detects failure, mark as failed
        grasp_success = gripper_ok and not part_on_table
        
        logger.info(
            f"[FSM-VERIFY] Grasp verification: "
            f"gripper_ok={gripper_ok}, part_on_table={part_on_table}, "
            f"result={'PASS' if grasp_success else 'FAIL'}"
        )
        
        return grasp_success

    def _check_gripper_grasp_state(self) -> bool:
        """Check if gripper is in closed position (part grasped).
        
        Returns:
            True if gripper appears closed, False if open/part fell
        """
        if self._current_ee is None:
            return True  # Can't verify, assume OK
        
        # Get gripper finger positions from robot interface (passed via FSMAgent)
        gripper_finger_width = self._gripper_finger_width
        if gripper_finger_width is None:
            return True  # No data available, assume OK
        
        # Walker S2: gripper close width ~0.01m, open width ~-0.0215m
        # Total range: 0.0315m
        # When grasping a part, gripper will be somewhere in the middle.
        # Check if gripper has moved at least 50% from open position toward closed.
        # Open = -0.0215, 50% closed = -0.0215 + 0.5*0.0315 = -0.00575
        open_width = getattr(self, 'gripper_open_width', -0.0215)
        closed_width = getattr(self, 'gripper_close_width', 0.01)
        gripper_range = closed_width - open_width  # 0.0315
        
        # If gripper has moved 40%+ from open position, consider it grasping
        grasp_threshold = open_width + 0.4 * gripper_range  # -0.0215 + 0.4*0.0315 = -0.0089
        is_grasping = gripper_finger_width >= grasp_threshold
        
        if not is_grasping:
            logger.warning(
                f"[FSM-VERIFY] Gripper check FAILED: width={gripper_finger_width:.4f}m, "
                f"threshold={grasp_threshold:.4f}m (open={open_width:.4f}, closed={closed_width:.4f})"
            )
        else:
            logger.info(
                f"[FSM-VERIFY] Gripper check PASSED: width={gripper_finger_width:.4f}m >= {grasp_threshold:.4f}m"
            )
        
        return is_grasping

    def _check_part_still_on_table(self) -> bool:
        """Check if part is still on the table (not picked up).
        
        Returns:
            True if part appears to still be on table, False if picked up
        """
        part_world = self._get_current_part_world()
        if part_world is None:
            return False  # Can't verify, assume OK
        
        # Table height is ~1.04m, part height ~0.05m
        # If part Z is within 2cm of table surface, it's still on table
        table_surface_z = self._table_height
        part_bottom_z = part_world[2]
        still_on_table = (part_bottom_z - table_surface_z) < 0.02
        
        if still_on_table:
            logger.warning(
                f"[FSM-VERIFY] Part position check FAILED: "
                f"part_z={part_bottom_z:.4f}m, table_z={table_surface_z:.4f}m"
            )
        
        return still_on_table

    # ------------------------------------------------------------------
    # Coordinate transforms (inline, no external dependency)
    # ------------------------------------------------------------------

    def _world_to_base(self, world_xyz: np.ndarray) -> np.ndarray:
        """Transform a position from world frame to robot base frame."""
        d = np.asarray(world_xyz, dtype=float) - self._robot_position_world
        base_xyz = self._R_world_to_base @ d
        
        # Log transformation for debugging box placement
        if np.linalg.norm(d) > 0.1:  # Only log for significant distances
            logger.debug(
                f"[FSM-TRANSFORM] world_to_base: "
                f"world={world_xyz}, robot_pos={self._robot_position_world}, "
                f"delta={np.round(d, 3)}, base={np.round(base_xyz, 3)}"
            )
        
        return base_xyz

    @staticmethod
    def _euler_zyx_to_rotation_matrix(roll_deg: float, pitch_deg: float, yaw_deg: float) -> np.ndarray:
        """Convert Euler ZYX angles (degrees) to a 3x3 rotation matrix.

        Convention: R = Rz(yaw) @ Ry(pitch) @ Rx(roll), applied as ZYX intrinsic.
        """
        r = math.radians(roll_deg)
        p = math.radians(pitch_deg)
        y = math.radians(yaw_deg)

        cr, sr = math.cos(r), math.sin(r)
        cp, sp = math.cos(p), math.sin(p)
        cy, sy = math.cos(y), math.sin(y)

        Rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
        Ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
        Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])

        return Rz @ Ry @ Rx

    @staticmethod
    def _rotation_matrix_to_rpy(R: np.ndarray) -> np.ndarray:
        """Convert a 3x3 rotation matrix to [roll, pitch, yaw] (ZYX intrinsic).

        Handles gimbal lock gracefully.
        """
        sy = -R[2, 0]
        sy = np.clip(sy, -1.0, 1.0)
        pitch = math.asin(sy)

        if abs(sy) > 0.99999:
            # Gimbal lock
            roll = math.atan2(-R[0, 1], R[1, 1])
            yaw = 0.0
        else:
            roll = math.atan2(R[2, 1], R[2, 2])
            yaw = math.atan2(R[1, 0], R[0, 0])

        return np.array([roll, pitch, yaw], dtype=float)