"""
Animation utilities for 3D model handling.

Provides interpolation functions and data structures for skeletal animation.
"""

# Defer all annotation evaluation so the module can still be imported when
# numpy isn't installed — dataclass field annotations would otherwise be
# evaluated at class-definition time and raise NameError on `np.ndarray`.
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple

# numpy is optional. Importing geo.loader transitively pulls this module in,
# so a broken numpy install would otherwise crash the whole geo subsystem
# at import time even for code paths that never touch animation.
try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore
    _HAS_NUMPY = False


# ============================================================================
# DATA CLASSES
# ============================================================================

class InterpolationType(Enum):
    """Animation interpolation types."""
    LINEAR = "linear"
    STEP = "step"
    CUBIC = "cubic"


@dataclass
class VectorKeyframe:
    """Keyframe for position or scale (vec3)."""
    time: float
    value: np.ndarray  # Shape: (3,) float32
    interpolation: InterpolationType = InterpolationType.LINEAR


@dataclass
class QuaternionKeyframe:
    """Keyframe for rotation (quaternion)."""
    time: float
    value: np.ndarray  # Shape: (4,) float32 - (x, y, z, w)
    interpolation: InterpolationType = InterpolationType.LINEAR


@dataclass
class BoneAnimation:
    """Animation data for a single bone."""
    bone_name: str
    position_keys: List[VectorKeyframe] = field(default_factory=list)
    rotation_keys: List[QuaternionKeyframe] = field(default_factory=list)
    scale_keys: List[VectorKeyframe] = field(default_factory=list)


# ============================================================================
# INTERPOLATION FUNCTIONS
# ============================================================================

def lerp(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    """Linear interpolation between two vectors."""
    return a + (b - a) * t


def slerp(q1: np.ndarray, q2: np.ndarray, t: float) -> np.ndarray:
    """Spherical linear interpolation between two quaternions."""
    q1 = q1 / np.linalg.norm(q1)
    q2 = q2 / np.linalg.norm(q2)

    dot = np.dot(q1, q2)
    if dot < 0:
        q2 = -q2
        dot = -dot

    if dot > 0.9995:
        result = q1 + t * (q2 - q1)
        return result / np.linalg.norm(result)

    theta_0 = np.arccos(dot)
    theta = theta_0 * t

    q_perp = q2 - q1 * dot
    perp_norm = np.linalg.norm(q_perp)
    if perp_norm < 1e-10:
        return q1.copy()
    q_perp = q_perp / perp_norm

    return q1 * np.cos(theta) + q_perp * np.sin(theta)


def quaternion_to_matrix(q: np.ndarray) -> np.ndarray:
    """Convert quaternion (x, y, z, w) to 4x4 rotation matrix."""
    x, y, z, w = q

    n = np.sqrt(x*x + y*y + z*z + w*w)
    if n > 0:
        x, y, z, w = x/n, y/n, z/n, w/n

    return np.array([
        [1 - 2*y*y - 2*z*z, 2*x*y - 2*z*w, 2*x*z + 2*y*w, 0],
        [2*x*y + 2*z*w, 1 - 2*x*x - 2*z*z, 2*y*z - 2*x*w, 0],
        [2*x*z - 2*y*w, 2*y*z + 2*x*w, 1 - 2*x*x - 2*y*y, 0],
        [0, 0, 0, 1]
    ], dtype=np.float32)


def compose_transform(position: np.ndarray, rotation: np.ndarray, scale: np.ndarray) -> np.ndarray:
    """Compose a 4x4 transform matrix from position, rotation (quaternion), and scale."""
    rot_mat = quaternion_to_matrix(rotation)
    rot_mat[0, :3] *= scale[0]
    rot_mat[1, :3] *= scale[1]
    rot_mat[2, :3] *= scale[2]
    rot_mat[0, 3] = position[0]
    rot_mat[1, 3] = position[1]
    rot_mat[2, 3] = position[2]
    return rot_mat


def interpolate_bone_animation(bone_anim: BoneAnimation, time: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Interpolate bone animation at a given time.

    Returns:
        Tuple of (position, rotation_quaternion, scale)
    """
    position = np.array([0, 0, 0], dtype=np.float32)
    rotation = np.array([0, 0, 0, 1], dtype=np.float32)
    scale = np.array([1, 1, 1], dtype=np.float32)

    if bone_anim.position_keys:
        position = _interpolate_vector_keys(bone_anim.position_keys, time)
    if bone_anim.rotation_keys:
        rotation = _interpolate_quaternion_keys(bone_anim.rotation_keys, time)
    if bone_anim.scale_keys:
        scale = _interpolate_vector_keys(bone_anim.scale_keys, time)

    return position, rotation, scale


def _interpolate_vector_keys(keys: List[VectorKeyframe], time: float) -> np.ndarray:
    """Interpolate vector keyframes at a given time."""
    if not keys:
        return np.array([0, 0, 0], dtype=np.float32)

    if len(keys) == 1:
        return keys[0].value.copy()

    for i in range(len(keys) - 1):
        if keys[i].time <= time <= keys[i + 1].time:
            dt = keys[i + 1].time - keys[i].time
            if dt <= 0:
                return keys[i].value.copy()
            t = (time - keys[i].time) / dt
            return lerp(keys[i].value, keys[i + 1].value, t)

    if time < keys[0].time:
        return keys[0].value.copy()
    return keys[-1].value.copy()


def _interpolate_quaternion_keys(keys: List[QuaternionKeyframe], time: float) -> np.ndarray:
    """Interpolate quaternion keyframes at a given time."""
    if not keys:
        return np.array([0, 0, 0, 1], dtype=np.float32)

    if len(keys) == 1:
        return keys[0].value.copy()

    for i in range(len(keys) - 1):
        if keys[i].time <= time <= keys[i + 1].time:
            dt = keys[i + 1].time - keys[i].time
            if dt <= 0:
                return keys[i].value.copy()
            t = (time - keys[i].time) / dt
            return slerp(keys[i].value, keys[i + 1].value, t)

    if time < keys[0].time:
        return keys[0].value.copy()
    return keys[-1].value.copy()
