"""Conveyor belt part spawner for Task 2: Dynamic part spawning.

Dynamically spawns parts on the moving conveyor belt at random intervals.
Supports episode reset and part tracking.
"""

import logging
import random
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class ConveyorPartSpawner:
    """Dynamically spawn parts on conveyor belt at random intervals.
    
    Manages part spawning lifecycle:
    - Track spawned parts count (4A + 4B = 8 total)
    - Random interval spawning (5-10s between parts)
    - Alternate or randomize part type (A/B)
    - Spawn at conveyor start position with random rotation
    - Track active parts on conveyor
    - Support episode reset
    """
    
    def __init__(self, cfg, scene_builder, world):
        """Initialize conveyor part spawner.
        
        Args:
            cfg: Task configuration dict (from Conveyor_Sorting.yaml)
            scene_builder: SceneBuilder instance for spawning parts
            world: Isaac Sim World instance for timing
        """
        self.cfg = cfg
        self.scene_builder = scene_builder
        self.world = world
        
        grasp_cfg = cfg.get('grasp', {})
        
        # Spawning state
        self.total_spawned = 0
        self.total_to_spawn = grasp_cfg.get('total_parts_to_sort', 8)
        self.parts_per_type = grasp_cfg.get('parts_per_type', 4)
        self.spawned_type_a = 0
        self.spawned_type_b = 0
        
        # Timing
        self.next_spawn_time = 0.0
        self.spawn_interval_min = grasp_cfg.get('conveyor_spawn_interval_min', 5.0)
        self.spawn_interval_max = grasp_cfg.get('conveyor_spawn_interval_max', 10.0)
        self.conveyor_speed = float(grasp_cfg.get('conveyor_speed', 0.1))
        self._last_update_time: Optional[float] = None
        
        # Spawn position
        self.spawn_position = np.array(
            grasp_cfg.get('conveyor_spawn_position', [0.12, 0.26859, 0.98])
        )
        
        # Part tracking
        self.active_parts = []  # List of spawned part prim paths
        
        logger.info(
            f"[ConveyorSpawner] Initialized: {self.total_to_spawn} parts to spawn, "
            f"interval [{self.spawn_interval_min:.1f}s, {self.spawn_interval_max:.1f}s]"
        )
    
    def schedule_next_spawn(self):
        """Schedule next part spawn with random interval."""
        interval = random.uniform(self.spawn_interval_min, self.spawn_interval_max)
        current_time = self._get_current_time()
        self.next_spawn_time = current_time + interval
        logger.info(
            f"[ConveyorSpawner] Next spawn scheduled in {interval:.2f}s "
            f"(at t={self.next_spawn_time:.2f}s)"
        )
    
    def spawn_next_part(self):
        """Spawn next part (A or B) on conveyor.
        
        Determines part type, creates part with random rotation,
        and tracks the spawned part.
        """
        if self.total_spawned >= self.total_to_spawn:
            logger.warning("[ConveyorSpawner] All parts already spawned")
            return
        
        # Determine part type (alternate to ensure balance)
        if self.spawned_type_a < self.parts_per_type and self.spawned_type_b < self.parts_per_type:
            # Both types still need parts, alternate
            part_type = 'A' if self.spawned_type_a <= self.spawned_type_b else 'B'
        elif self.spawned_type_a < self.parts_per_type:
            part_type = 'A'
        elif self.spawned_type_b < self.parts_per_type:
            part_type = 'B'
        else:
            logger.error("[ConveyorSpawner] No more parts should be spawned")
            return
        
        # Keep spawned parts flat on the conveyor. Randomizing roll/pitch makes
        # some assets appear to hover or stand on an edge at the fixed spawn Z.
        rotation = [0.0, 0.0, random.uniform(-90, 90)]
        
        # Spawn part via SceneBuilder
        try:
            part_path = self.scene_builder.spawn_conveyor_part(
                part_type=part_type,
                position=self.spawn_position.tolist(),
                rotation=rotation
            )
            
            if part_path:
                self.active_parts.append(part_path)
                self.total_spawned += 1
                
                if part_type == 'A':
                    self.spawned_type_a += 1
                else:
                    self.spawned_type_b += 1
                
                logger.info(
                    f"[ConveyorSpawner] Spawned Part {part_type} #{self.total_spawned} "
                    f"(A:{self.spawned_type_a}, B:{self.spawned_type_b}) at "
                    f"pos={self.spawn_position}"
                )
                
                # Schedule next spawn if more parts needed
                if self.total_spawned < self.total_to_spawn:
                    self.schedule_next_spawn()
                else:
                    logger.info("[ConveyorSpawner] All parts spawned")
            else:
                logger.error(f"[ConveyorSpawner] Failed to spawn part {part_type}")
                
        except Exception as e:
            logger.error(f"[ConveyorSpawner] Error spawning part: {e}")
    
    def update(self):
        """Called each physics step to check if should spawn.
        
        Checks if current time has reached next_spawn_time and spawns
        the next part if so.
        """
        if self.total_spawned >= self.total_to_spawn:
            self._advance_active_parts()
            return

        self._advance_active_parts()
        current_time = self._get_current_time()
        if current_time >= self.next_spawn_time:
            self.spawn_next_part()

    def _advance_active_parts(self) -> None:
        """Move spawned parts along the conveyor direction.

        The visual conveyor surface velocity is not enough for dynamically
        cloned USD parts in this integration, so keep the FSM's spawned parts
        moving explicitly using simulation time.
        """
        current_time = self._get_current_time()
        if self._last_update_time is None:
            self._last_update_time = current_time
            return

        dt = max(0.0, min(current_time - self._last_update_time, 0.25))
        self._last_update_time = current_time
        if dt <= 0.0 or not self.active_parts:
            return

        try:
            self.scene_builder.move_conveyor_parts(self.active_parts, self.conveyor_speed * dt)
        except Exception as e:
            logger.error(f"[ConveyorSpawner] Error moving conveyor parts: {e}")
    
    def reset(self):
        """Reset spawner for new episode.
        
        Deletes all spawned parts, resets counters, and schedules first spawn.
        """
        logger.info("[ConveyorSpawner] Resetting for new episode")
        
        # Delete spawned parts via SceneBuilder
        try:
            self.scene_builder.delete_spawned_conveyor_parts()
        except Exception as e:
            logger.error(f"[ConveyorSpawner] Error deleting parts: {e}")
        
        # Reset counters
        self.total_spawned = 0
        self.spawned_type_a = 0
        self.spawned_type_b = 0
        self.active_parts = []
        self._last_update_time = self._get_current_time()
        
        # Schedule first spawn (immediate or after short delay)
        self.next_spawn_time = self._get_current_time() + 2.0  # 2s initial delay
        logger.info("[ConveyorSpawner] First part scheduled in 2.0s")
    
    def get_spawn_progress(self) -> dict:
        """Get current spawning progress.
        
        Returns:
            Dict with spawning statistics
        """
        return {
            'total_spawned': self.total_spawned,
            'total_to_spawn': self.total_to_spawn,
            'spawned_type_a': self.spawned_type_a,
            'spawned_type_b': self.spawned_type_b,
            'remaining': self.total_to_spawn - self.total_spawned,
            'next_spawn_time': self.next_spawn_time,
            'current_time': self._get_current_time(),
        }
    
    def is_complete(self) -> bool:
        """Check if all parts have been spawned."""
        return self.total_spawned >= self.total_to_spawn
    
    def _get_current_time(self) -> float:
        """Get current simulation time.
        
        Returns:
            Current time in seconds
        """
        try:
            return self.world.current_time
        except Exception:
            # Fallback if world not available
            return 0.0
