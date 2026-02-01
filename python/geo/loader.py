"""
Universal 3D Model Loader for Luma Tools.

Provides a unified interface for loading 3D models from various formats
including GLB, GLTF, FBX, OBJ, and USD.

Supports:
- Meshes with vertices, normals, UVs, and vertex colors
- Materials with diffuse color and texture paths
- Embedded textures (GLB/FBX)
- Skeleton/bone hierarchies
- Animations with keyframe data

Architecture:
- This module contains data classes and re-exports the factory API
- Individual loaders are in geo/loaders/ package:
  - open3d_loader.py: Open3D-based loader (OBJ, STL, PLY)
  - trimesh_loader.py: Trimesh-based loader (GLB, GLTF with textures)
  - assimp_loader.py: PyAssimp-based loader (FBX with skeleton/animation)
  - usd_loader.py: OpenUSD-based loader (USD, USDA, USDC, USDZ)
  - smpl_loader.py: SMPL NPZ loader (HyMotion skeleton data)
"""

import os
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple

import numpy as np


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class MeshData:
    """Represents a single mesh with geometry and material reference."""
    name: str
    vertices: np.ndarray  # Shape: (N, 3) float32
    normals: np.ndarray   # Shape: (N, 3) float32
    uvs: Optional[np.ndarray] = None  # Shape: (N, 2) float32
    colors: Optional[np.ndarray] = None  # Shape: (N, 4) float32 RGBA
    faces: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.uint32))  # Shape: (M, 3) uint32
    material_index: int = -1
    # Bone weights for skeletal animation
    bone_ids: Optional[np.ndarray] = None  # Shape: (N, 4) int32 - up to 4 bones per vertex
    bone_weights: Optional[np.ndarray] = None  # Shape: (N, 4) float32


@dataclass
class Material:
    """Represents a material with color and texture information."""
    name: str
    diffuse_color: Tuple[float, float, float, float] = (0.8, 0.8, 0.8, 1.0)
    specular_color: Tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    ambient_color: Tuple[float, float, float, float] = (0.2, 0.2, 0.2, 1.0)
    emissive_color: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    shininess: float = 32.0
    opacity: float = 1.0
    # Texture paths (relative or absolute)
    diffuse_texture: Optional[str] = None
    normal_texture: Optional[str] = None
    specular_texture: Optional[str] = None
    # PBR properties
    metallic: float = 0.0
    roughness: float = 0.5


@dataclass
class Bone:
    """Represents a bone in the skeleton hierarchy."""
    name: str
    index: int
    parent_index: int  # -1 for root bones
    # Bind pose transform (bone space to model space)
    offset_matrix: np.ndarray  # Shape: (4, 4) float32
    # Local transform relative to parent
    local_transform: np.ndarray = field(default_factory=lambda: np.eye(4, dtype=np.float32))


@dataclass
class Skeleton:
    """Represents a skeleton with bone hierarchy."""
    bones: List[Bone] = field(default_factory=list)
    bone_name_to_index: Dict[str, int] = field(default_factory=dict)


# Import animation types from animation_utils
from .animation_utils import (
    InterpolationType,
    VectorKeyframe,
    QuaternionKeyframe,
    BoneAnimation,
    lerp,
    slerp,
    quaternion_to_matrix,
    compose_transform,
    interpolate_bone_animation,
)


@dataclass
class Animation:
    """Represents an animation clip."""
    name: str
    duration: float  # Duration in seconds
    ticks_per_second: float = 25.0
    bone_animations: Dict[str, BoneAnimation] = field(default_factory=dict)

    @property
    def fps(self) -> float:
        return self.ticks_per_second

    @property
    def frame_count(self) -> int:
        return int(self.duration * self.ticks_per_second)


@dataclass
class ModelData:
    """Complete loaded model data."""
    path: str
    meshes: List[MeshData] = field(default_factory=list)
    materials: List[Material] = field(default_factory=list)
    textures: Dict[str, bytes] = field(default_factory=dict)  # Embedded textures
    skeleton: Optional[Skeleton] = None
    animations: List[Animation] = field(default_factory=list)

    # Computed bounds
    bounds_min: np.ndarray = field(default_factory=lambda: np.array([0, 0, 0], dtype=np.float32))
    bounds_max: np.ndarray = field(default_factory=lambda: np.array([0, 0, 0], dtype=np.float32))

    @property
    def has_skeleton(self) -> bool:
        return self.skeleton is not None and len(self.skeleton.bones) > 0

    @property
    def has_animations(self) -> bool:
        return len(self.animations) > 0

    @property
    def has_meshes(self) -> bool:
        return len(self.meshes) > 0

    @property
    def is_skeleton_only(self) -> bool:
        """Returns True if model has skeleton but no visible meshes."""
        return self.has_skeleton and not self.has_meshes

    @property
    def center(self) -> np.ndarray:
        return (self.bounds_min + self.bounds_max) / 2

    @property
    def radius(self) -> float:
        return float(np.linalg.norm(self.bounds_max - self.bounds_min) / 2)


# ============================================================================
# RE-EXPORT FACTORY API (for backwards compatibility)
# ============================================================================

from .loaders.factory import (
    load_model,
    get_loader_availability,
    get_format_type,
    is_supported_format,
    SUPPORTED_EXTENSIONS,
    ASSIMP_AVAILABLE,
)

__all__ = [
    # Data classes
    'MeshData',
    'Material',
    'Bone',
    'Skeleton',
    'Animation',
    'ModelData',
    # Animation utilities (re-exported)
    'InterpolationType',
    'VectorKeyframe',
    'QuaternionKeyframe',
    'BoneAnimation',
    'lerp',
    'slerp',
    'quaternion_to_matrix',
    'compose_transform',
    'interpolate_bone_animation',
    # Factory API
    'load_model',
    'get_loader_availability',
    'get_format_type',
    'is_supported_format',
    'SUPPORTED_EXTENSIONS',
    'ASSIMP_AVAILABLE',
]
