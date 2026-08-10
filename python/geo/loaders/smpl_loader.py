"""
SMPL NPZ model loader.

Loads SMPL skeleton data from HyMotion NPZ files.
These files contain motion capture data in SMPL format.
"""

import os
from typing import Set

# numpy is optional (mirrors base.py) — a broken venv must not make the
# whole geo.loaders import graph blow up.
try:
    import numpy as np
except Exception:
    np = None

from .base import BaseModelLoader
from geo.loader import (
    ModelData, Bone, Skeleton, Animation,
    BoneAnimation, VectorKeyframe, QuaternionKeyframe,
)


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
        return np is not None

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

            # Frame rate: honour the NPZ metadata when present, else 30 FPS
            fps = 30.0
            for fps_key in ("mocap_framerate", "mocap_frame_rate", "fps", "framerate"):
                if fps_key in data:
                    try:
                        fps = float(np.asarray(data[fps_key]).flatten()[0])
                        break
                    except (TypeError, ValueError, IndexError):
                        continue

            # Build skeleton from SMPL joint hierarchy
            skeleton = self._build_skeleton()
            model.skeleton = skeleton

            # Create animation with actual per-bone keyframes. Previously the
            # pose/translation data was validated and then discarded, so
            # has_animations was True but playback showed a static bind pose.
            if num_frames > 1:
                animation = self._build_animation(poses, trans, Rh, fps)
                model.animations.append(animation)

            # Calculate bounds from first frame translation
            if len(trans) > 0:
                root_pos = trans[0].astype(np.float32)
                # SMPL body is roughly 1.7m tall
                model.bounds_min = root_pos - np.array([0.5, 0.0, 0.5], dtype=np.float32)
                model.bounds_max = root_pos + np.array([0.5, 1.7, 0.5], dtype=np.float32)

        return model

    def _build_animation(self, poses, trans, Rh, fps: float) -> Animation:
        """Build an Animation with per-bone keyframes from SMPL pose data.

        Args:
            poses: (num_frames, 22*3) axis-angle joint rotations
            trans: (num_frames, 3) root translation
            Rh: Optional (num_frames, 3) global root orientation — overrides
                the pelvis rotation from `poses` when present
            fps: Frames per second for keyframe timing
        """
        num_frames = len(poses)
        animation = Animation(
            name="SMPL Motion",
            duration=num_frames / fps,
            ticks_per_second=fps,
        )

        pose_array = np.asarray(poses, dtype=np.float64).reshape(num_frames, -1, 3)
        num_joints = min(pose_array.shape[1], len(self.JOINT_NAMES))

        trans_array = None
        if trans is not None and len(trans) == num_frames:
            trans_array = np.asarray(trans, dtype=np.float64)

        rh_array = None
        if Rh is not None and len(Rh) == num_frames:
            rh_array = np.asarray(Rh, dtype=np.float64).reshape(num_frames, -1)[:, :3]

        for joint_idx in range(num_joints):
            bone_name = self.JOINT_NAMES[joint_idx]
            bone_anim = BoneAnimation(bone_name=bone_name)

            for frame in range(num_frames):
                t = frame / fps
                if joint_idx == 0 and rh_array is not None:
                    axis_angle = rh_array[frame]
                else:
                    axis_angle = pose_array[frame, joint_idx]

                bone_anim.rotation_keys.append(QuaternionKeyframe(
                    time=t,
                    value=self._axis_angle_to_quaternion(axis_angle),
                ))

                # Root bone also carries the body translation
                if joint_idx == 0 and trans_array is not None:
                    bone_anim.position_keys.append(VectorKeyframe(
                        time=t,
                        value=trans_array[frame].astype(np.float32),
                    ))

            animation.bone_animations[bone_name] = bone_anim

        return animation

    @staticmethod
    def _axis_angle_to_quaternion(axis_angle) -> "np.ndarray":
        """Convert an axis-angle rotation vector to a quaternion [x, y, z, w]."""
        aa = np.asarray(axis_angle, dtype=np.float64)
        angle = float(np.linalg.norm(aa))
        if angle < 1e-8:
            return np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)
        axis = aa / angle
        half = angle / 2.0
        sin_half = np.sin(half)
        return np.array(
            [axis[0] * sin_half, axis[1] * sin_half, axis[2] * sin_half, np.cos(half)],
            dtype=np.float32,
        )

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
