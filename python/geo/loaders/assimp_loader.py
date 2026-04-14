"""
Assimp-based model loader.

Uses PyAssimp library for loading 3D models.
Best for FBX files with skeleton/animation support.
"""

import os
import logging
from typing import Set, List, Dict, Optional

logger = logging.getLogger(__name__)

import numpy as np

from .base import BaseModelLoader
from geo.loader import (
    ModelData, MeshData, Material, Bone, Skeleton, Animation,
    BoneAnimation, VectorKeyframe, QuaternionKeyframe
)

# Add libs folder to PATH for native Assimp DLL.
# Guarded so re-imports don't keep prepending the same directory — without
# this, hot-reload during dev or test isolation grows PATH without bound and
# the modified env is inherited by every child process (FFmpeg/OIIO/Deadline).
_LIBS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "libs")
if os.path.isdir(_LIBS_DIR):
    _existing_path = os.environ.get('PATH', '')
    if _LIBS_DIR not in _existing_path.split(os.pathsep):
        os.environ['PATH'] = _LIBS_DIR + os.pathsep + _existing_path

from core.import_utils import safe_import

pyassimp, ASSIMP_AVAILABLE = safe_import("pyassimp")
postprocess = None
if ASSIMP_AVAILABLE:
    from pyassimp import postprocess


class AssimpModelLoader(BaseModelLoader):
    """Model loader using PyAssimp. Best for FBX with skeleton/animation."""

    @property
    def name(self) -> str:
        return "Assimp"

    @property
    def supported_extensions(self) -> Set[str]:
        return {'.fbx', '.dae', '.3ds', '.blend', '.obj', '.glb', '.gltf'}

    @property
    def is_available(self) -> bool:
        return ASSIMP_AVAILABLE

    def load(self, path: str) -> ModelData:
        """Load a 3D model using Assimp."""
        self._validate_load_preconditions(path, "pyassimp")

        # Load with post-processing flags
        context = self._load_with_flags(path)

        if context is None:
            raise ValueError("Failed to load model with Assimp")

        # Process the scene
        with context as scene:
            if scene is None:
                raise ValueError("Assimp returned NULL scene - file may be corrupted")

            model = ModelData(path=path)
            base_dir = os.path.dirname(path)

            # Debug output
            num_meshes = len(scene.meshes) if scene.meshes else 0
            num_anims = len(scene.animations) if hasattr(scene, 'animations') and scene.animations else 0
            logger.info(f"Assimp loaded: {num_meshes} meshes, {num_anims} animations")

            # Extract all components
            model.materials = self._extract_materials(scene, base_dir)
            model.textures = self._extract_embedded_textures(scene)
            model.meshes = self._extract_meshes(scene)
            model.skeleton = self._extract_skeleton(scene)
            model.animations = self._extract_animations(scene)

            # Calculate bounds
            self._calculate_bounds(model)

            return model

    def _load_with_flags(self, path: str):
        """Load model with appropriate post-processing flags.

        Tries progressively simpler flag combinations if NULL errors occur.
        """
        # Flag priority: full processing -> minimal -> none
        flag_options = [
            (
                postprocess.aiProcess_Triangulate |
                postprocess.aiProcess_GenNormals |
                postprocess.aiProcess_CalcTangentSpace |
                postprocess.aiProcess_JoinIdenticalVertices |
                postprocess.aiProcess_SortByPType |
                postprocess.aiProcess_FlipUVs
            ),
            postprocess.aiProcess_Triangulate,
            0,  # No post-processing
        ]

        for flags in flag_options:
            try:
                return pyassimp.load(path, processing=flags)
            except Exception as e:
                error_msg = str(e)
                is_null_error = "NULL" in error_msg.upper() or "null" in error_msg.lower()
                if not is_null_error:
                    raise  # Non-NULL errors don't benefit from fallback
                logger.debug(f"Assimp NULL error with flags {flags}, trying fallback")

        raise ValueError(
            "Assimp failed to parse file (NULL pointer error). "
            "The file may use an unsupported format or be corrupted."
        )

    def _extract_materials(self, scene, base_dir: str) -> List[Material]:
        """Extract materials from Assimp scene."""
        materials = []

        for mat in scene.materials:
            material = Material(name=mat.properties.get('name', f'Material_{len(materials)}'))

            # Diffuse color
            if 'diffuse' in mat.properties:
                diffuse = mat.properties['diffuse']
                if len(diffuse) >= 3:
                    material.diffuse_color = (
                        diffuse[0], diffuse[1], diffuse[2],
                        diffuse[3] if len(diffuse) > 3 else 1.0
                    )

            # Specular color
            if 'specular' in mat.properties:
                specular = mat.properties['specular']
                if len(specular) >= 3:
                    material.specular_color = (specular[0], specular[1], specular[2], 1.0)

            # Ambient color
            if 'ambient' in mat.properties:
                ambient = mat.properties['ambient']
                if len(ambient) >= 3:
                    material.ambient_color = (ambient[0], ambient[1], ambient[2], 1.0)

            # Shininess
            if 'shininess' in mat.properties:
                material.shininess = float(mat.properties['shininess'])

            # Opacity
            if 'opacity' in mat.properties:
                material.opacity = float(mat.properties['opacity'])

            # Diffuse texture
            if 'file' in mat.properties:
                tex_path = mat.properties['file']
                if not os.path.isabs(tex_path):
                    tex_path = os.path.join(base_dir, tex_path)
                material.diffuse_texture = tex_path

            materials.append(material)

        return materials

    def _extract_embedded_textures(self, scene) -> Dict[str, bytes]:
        """Extract embedded textures from Assimp scene."""
        textures = {}

        if hasattr(scene, 'textures') and scene.textures:
            for i, tex in enumerate(scene.textures):
                if tex.data:
                    name = f"*{i}"  # Assimp convention for embedded textures
                    textures[name] = bytes(tex.data)

        return textures

    def _extract_meshes(self, scene) -> List[MeshData]:
        """Extract meshes from Assimp scene."""
        meshes = []

        for mesh in scene.meshes:
            mesh_data = MeshData(
                name=mesh.name or f"Mesh_{len(meshes)}",
                vertices=np.array(mesh.vertices, dtype=np.float32),
                normals=(
                    np.array(mesh.normals, dtype=np.float32)
                    if mesh.normals.size > 0
                    else np.zeros_like(mesh.vertices, dtype=np.float32)
                ),
                faces=np.array([face.indices for face in mesh.faces], dtype=np.uint32),
                material_index=mesh.materialindex
            )

            # UV coordinates (first set)
            if mesh.texturecoords.size > 0 and len(mesh.texturecoords) > 0:
                uvs = mesh.texturecoords[0]
                if uvs is not None and len(uvs) > 0:
                    mesh_data.uvs = np.array(uvs[:, :2], dtype=np.float32)

            # Vertex colors (first set)
            if hasattr(mesh, 'colors') and mesh.colors.size > 0:
                colors = mesh.colors[0]
                if colors is not None and len(colors) > 0:
                    mesh_data.colors = np.array(colors, dtype=np.float32)

            # Bone weights
            if mesh.bones:
                self._extract_bone_weights(mesh, mesh_data)

            meshes.append(mesh_data)

        return meshes

    def _extract_bone_weights(self, mesh, mesh_data: MeshData) -> None:
        """Extract bone weights for skeletal animation."""
        num_vertices = len(mesh.vertices)
        bone_ids = np.zeros((num_vertices, 4), dtype=np.int32)
        bone_weights = np.zeros((num_vertices, 4), dtype=np.float32)
        vertex_bone_count = np.zeros(num_vertices, dtype=np.int32)

        for bone_idx, bone in enumerate(mesh.bones):
            for weight in bone.weights:
                v_idx = weight.vertexid
                if vertex_bone_count[v_idx] < 4:
                    slot = vertex_bone_count[v_idx]
                    bone_ids[v_idx, slot] = bone_idx
                    bone_weights[v_idx, slot] = weight.weight
                    vertex_bone_count[v_idx] += 1

        mesh_data.bone_ids = bone_ids
        mesh_data.bone_weights = bone_weights

    def _extract_skeleton(self, scene) -> Optional[Skeleton]:
        """Extract skeleton from Assimp scene."""
        # Collect all bones from meshes
        bone_names = set()
        bone_offsets = {}

        for mesh in scene.meshes:
            if mesh.bones:
                for bone in mesh.bones:
                    bone_names.add(bone.name)
                    bone_offsets[bone.name] = np.array(
                        bone.offsetmatrix, dtype=np.float32
                    ).reshape(4, 4).T

        skeleton = Skeleton()
        skeleton_only_mode = len(bone_names) == 0

        def process_node(node, parent_index=-1):
            """Recursively process nodes to build bone hierarchy."""
            is_bone = False

            if skeleton_only_mode:
                # Include any node that's not a camera/light
                node_name_lower = node.name.lower()
                skip_keywords = ['camera', 'light', 'ambientlight']
                if not any(kw in node_name_lower for kw in skip_keywords):
                    is_bone = True
            else:
                is_bone = node.name in bone_names

            if is_bone:
                bone = Bone(
                    name=node.name,
                    index=len(skeleton.bones),
                    parent_index=parent_index,
                    offset_matrix=bone_offsets.get(node.name, np.eye(4, dtype=np.float32)),
                    local_transform=np.array(node.transformation, dtype=np.float32).reshape(4, 4).T
                )
                skeleton.bones.append(bone)
                skeleton.bone_name_to_index[node.name] = bone.index
                parent_index = bone.index

            for child in node.children:
                process_node(child, parent_index)

        if scene.rootnode:
            process_node(scene.rootnode)

        return skeleton if skeleton.bones else None

    def _extract_animations(self, scene) -> List[Animation]:
        """Extract animations from Assimp scene."""
        animations = []

        if not hasattr(scene, 'animations') or not scene.animations:
            return animations

        for anim in scene.animations:
            ticks_per_second = float(anim.tickspersecond) if anim.tickspersecond > 0 else 25.0
            duration_seconds = float(anim.duration) / ticks_per_second

            animation = Animation(
                name=anim.name or f"Animation_{len(animations)}",
                duration=duration_seconds,
                ticks_per_second=ticks_per_second
            )

            # Extract bone animations
            for channel in anim.channels:
                bone_anim = BoneAnimation(bone_name=channel.nodename)

                # Position keyframes
                for key in channel.positionkeys:
                    bone_anim.position_keys.append(VectorKeyframe(
                        time=float(key.time) / ticks_per_second,
                        value=np.array([key.value.x, key.value.y, key.value.z], dtype=np.float32)
                    ))

                # Rotation keyframes
                for key in channel.rotationkeys:
                    bone_anim.rotation_keys.append(QuaternionKeyframe(
                        time=float(key.time) / ticks_per_second,
                        value=np.array([key.value.x, key.value.y, key.value.z, key.value.w], dtype=np.float32)
                    ))

                # Scale keyframes
                for key in channel.scalingkeys:
                    bone_anim.scale_keys.append(VectorKeyframe(
                        time=float(key.time) / ticks_per_second,
                        value=np.array([key.value.x, key.value.y, key.value.z], dtype=np.float32)
                    ))

                animation.bone_animations[channel.nodename] = bone_anim

            animations.append(animation)

        return animations
