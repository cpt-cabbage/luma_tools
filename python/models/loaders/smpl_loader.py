"""
SMPL NPZ model loader.

Loads SMPL skeleton data from HyMotion NPZ files.
These files contain motion capture data in SMPL format.
"""

import os
from typing import Set

import numpy as np

from .base import BaseModelLoader
from models.loader import ModelData, Bone, Skeleton, Animation


class SMPLModelLoader(BaseModelLoader):
    """Model loader for SMPL NPZ files (HyMotion skeleton data)."""

    # SMPL joint names (standard SMPL-H hierarchy)
    JOINT_NAMES = [
        "pelvis",           # 0 (root)
        "left_hip",         # 1
        "right_hip",        # 2
        "spine1",           # 3
        "left_knee",        # 4
        "right_knee",       # 5
        "spine2",           # 6
        "left_ankle",       # 7
        "right_ankle",      # 8
        "spine3",           # 9
        "left_foot",        # 10
        "right_foot",       # 11
        "neck",             # 12
        "left_collar",      # 13
        "right_collar",     # 14
        "head",             # 15
        "left_shoulder",    # 16
        "right_shoulder",   # 17
        "left_elbow",       # 18
        "right_elbow",      # 19
        "left_wrist",       # 20
        "right_wrist",      # 21
    ]

    # SMPL parent indices (standard hierarchy)
    PARENT_INDICES = [
        -1,  # pelvis (root, no parent)
        0,   # left_hip -> pelvis
        0,   # right_hip -> pelvis
        0,   # spine1 -> pelvis
        1,   # left_knee -> left_hip
        2,   # right_knee -> right_hip
        3,   # spine2 -> spine1
        4,   # left_ankle -> left_knee
        5,   # right_ankle -> right_knee
        6,   # spine3 -> spine2
        7,   # left_foot -> left_ankle
        8,   # right_foot -> right_ankle
        9,   # neck -> spine3
        9,   # left_collar -> spine3
        9,   # right_collar -> spine3
        12,  # head -> neck
        13,  # left_shoulder -> left_collar
        14,  # right_shoulder -> right_collar
        16,  # left_elbow -> left_shoulder
        17,  # right_elbow -> right_shoulder
        18,  # left_wrist -> left_elbow
        19,  # right_wrist -> right_elbow
    ]

    @property
    def name(self) -> str:
        return "SMPL"

    @property
    def supported_extensions(self) -> Set[str]:
        return {'.npz'}

    @property
    def is_available(self) -> bool:
        # NumPy is always available
        return True

    def load(self, path: str) -> ModelData:
        """Load SMPL skeleton data from HyMotion NPZ files."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"Model file not found: {path}")

        model = ModelData(path=path)

        # Load NPZ file
        with np.load(path, allow_pickle=False) as data:
            # SMPL data contains:
            # - Rh: root rotation (num_frames, 3) in axis-angle
            # - trans/Th: translation (num_frames, 3)
            # - poses: joint rotations (num_frames, 66) - 22 joints x 3 axis-angle
            # - betas: shape parameters (10,)
            # - gender: string

            Rh = data.get("Rh", data.get("root_orient"))
            trans = data.get("trans", data.get("Th"))
            poses = data.get("poses", data.get("body_pose"))

            if poses is None or trans is None:
                raise ValueError("NPZ file doesn't contain required SMPL data (poses, trans)")

            num_frames = len(poses)

            # Build skeleton from SMPL joint hierarchy
            skeleton = self._build_skeleton()
            model.skeleton = skeleton

            # Create animation from the data
            if num_frames > 1:
                animation = Animation(
                    name="SMPL Motion",
                    duration=num_frames / 30.0,  # Assume 30 FPS
                    ticks_per_second=30.0
                )
                model.animations.append(animation)

            # Calculate bounds from first frame translation
            if len(trans) > 0:
                root_pos = trans[0].astype(np.float32)
                # SMPL body is roughly 1.7m tall
                model.bounds_min = root_pos - np.array([0.5, 0.0, 0.5], dtype=np.float32)
                model.bounds_max = root_pos + np.array([0.5, 1.7, 0.5], dtype=np.float32)

        return model

    def _build_skeleton(self) -> Skeleton:
        """Build skeleton from SMPL joint hierarchy."""
        skeleton = Skeleton()

        for i, (name, parent_idx) in enumerate(zip(self.JOINT_NAMES, self.PARENT_INDICES)):
            bone = Bone(
                name=name,
                index=i,
                parent_index=parent_idx,
                offset_matrix=np.eye(4, dtype=np.float32),
                local_transform=np.eye(4, dtype=np.float32)
            )
            skeleton.bones.append(bone)
            skeleton.bone_name_to_index[name] = i

        return skeleton
