"""
Universal 3D Model Loader for Luma Tools.

Provides a unified interface for loading 3D models from various formats
including GLB, GLTF, FBX, OBJ, and USD using Assimp.

Supports:
- Meshes with vertices, normals, UVs, and vertex colors
- Materials with diffuse color and texture paths
- Embedded textures (GLB/FBX)
- Skeleton/bone hierarchies
- Animations with keyframe data
"""

import os
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple, Any
from enum import Enum

import numpy as np

# Check for Open3D availability (preferred - bundles Assimp)
try:
    import open3d as o3d
    OPEN3D_AVAILABLE = True
except ImportError:
    OPEN3D_AVAILABLE = False
    o3d = None

# Check for Assimp availability (fallback)
# Note: pyassimp raises AssimpError at import if native library not found
ASSIMP_AVAILABLE = False
pyassimp = None
postprocess = None

# Add libs folder to PATH so pyassimp can find the native Assimp DLL
# libs is at python/libs, we are at python/models/loader.py
_LIBS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "libs")
if os.path.isdir(_LIBS_DIR):
    os.environ['PATH'] = _LIBS_DIR + os.pathsep + os.environ.get('PATH', '')

try:
    import pyassimp as _pyassimp
    from pyassimp import postprocess as _postprocess
    pyassimp = _pyassimp
    postprocess = _postprocess
    ASSIMP_AVAILABLE = True
except Exception:
    pass

# Check for trimesh availability (fallback for GLB/GLTF/OBJ)
try:
    import trimesh
    TRIMESH_AVAILABLE = True
except ImportError:
    TRIMESH_AVAILABLE = False
    trimesh = None

# Check for USD availability (for USD files)
try:
    from pxr import Usd, UsdGeom, UsdSkel
    USD_AVAILABLE = True
except ImportError:
    USD_AVAILABLE = False


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

    def get_bone(self, name: str) -> Optional[Bone]:
        """Get bone by name."""
        idx = self.bone_name_to_index.get(name)
        if idx is not None and idx < len(self.bones):
            return self.bones[idx]
        return None

    def get_root_bones(self) -> List[Bone]:
        """Get all root bones (bones with no parent)."""
        return [b for b in self.bones if b.parent_index < 0]


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
# SUPPORTED FORMATS
# ============================================================================

SUPPORTED_EXTENSIONS = {
    '.glb', '.gltf',  # glTF
    '.fbx',           # Autodesk FBX
    '.obj',           # Wavefront OBJ
    '.usd', '.usda', '.usdc', '.usdz',  # USD
    '.dae',           # Collada
    '.3ds',           # 3D Studio Max
    '.blend',         # Blender (limited support)
    '.stl',           # STL (mesh only)
    '.ply',           # PLY (mesh only)
    '.npz',           # NumPy archive (SMPL skeleton data from HyMotion)
}


def is_supported_format(path: str) -> bool:
    """Check if the file format is supported."""
    ext = os.path.splitext(path)[1].lower()
    return ext in SUPPORTED_EXTENSIONS


def get_format_type(path: str) -> str:
    """Get the format type for a file path."""
    ext = os.path.splitext(path)[1].lower()
    if ext in {'.glb', '.gltf'}:
        return 'gltf'
    elif ext == '.fbx':
        return 'fbx'
    elif ext == '.obj':
        return 'obj'
    elif ext in {'.usd', '.usda', '.usdc', '.usdz'}:
        return 'usd'
    elif ext == '.dae':
        return 'collada'
    else:
        return 'other'


# ============================================================================
# OPEN3D LOADER (Preferred - bundles Assimp)
# ============================================================================

def _load_with_open3d(path: str) -> ModelData:
    """Load a 3D model using Open3D (which bundles Assimp)."""
    if not OPEN3D_AVAILABLE:
        raise ImportError("open3d is not available. Install with: pip install open3d")

    model = ModelData(path=path)

    # Read the mesh
    mesh = o3d.io.read_triangle_mesh(path, enable_post_processing=True)

    if mesh.is_empty():
        ext = os.path.splitext(path)[1].lower()
        if ext == '.fbx':
            # FBX file with no mesh data - likely skeleton/animation only
            # Open3D can't read skeleton data, needs pyassimp
            raise ValueError(
                f"FBX file has no mesh data (skeleton-only?). "
                f"Open3D cannot read skeleton/animation data from FBX. "
                f"Install pyassimp for skeleton-only FBX support."
            )
        raise ValueError(f"Failed to load mesh from: {path}")

    # Convert to numpy arrays
    vertices = np.asarray(mesh.vertices, dtype=np.float32)
    faces = np.asarray(mesh.triangles, dtype=np.uint32)

    # Get or compute normals
    if mesh.has_vertex_normals():
        normals = np.asarray(mesh.vertex_normals, dtype=np.float32)
    else:
        mesh.compute_vertex_normals()
        normals = np.asarray(mesh.vertex_normals, dtype=np.float32)

    # Get UVs if available
    uvs = None
    if mesh.has_triangle_uvs():
        # Open3D stores UVs per triangle vertex, need to reorganize
        triangle_uvs = np.asarray(mesh.triangle_uvs, dtype=np.float32)
        # This is triangle-based, we need vertex-based
        # For now, skip complex UV reorganization
        pass

    # Get vertex colors if available
    colors = None
    if mesh.has_vertex_colors():
        colors = np.asarray(mesh.vertex_colors, dtype=np.float32)
        # Convert RGB to RGBA
        if colors.shape[1] == 3:
            alpha = np.ones((colors.shape[0], 1), dtype=np.float32)
            colors = np.hstack([colors, alpha])

    mesh_data = MeshData(
        name=os.path.basename(path),
        vertices=vertices,
        normals=normals,
        faces=faces,
        uvs=uvs,
        colors=colors
    )
    model.meshes.append(mesh_data)

    # Calculate bounds
    if len(vertices) > 0:
        model.bounds_min = np.min(vertices, axis=0).astype(np.float32)
        model.bounds_max = np.max(vertices, axis=0).astype(np.float32)

    return model


# ============================================================================
# TRIMESH LOADER (Best for GLB/GLTF - properly extracts textures)
# ============================================================================

def _load_with_trimesh(path: str) -> ModelData:
    """Load a 3D model using trimesh. Best for GLB/GLTF with embedded textures."""
    if not TRIMESH_AVAILABLE:
        raise ImportError("trimesh is not available. Install with: pip install trimesh")

    model = ModelData(path=path)

    # Load the model
    scene_or_mesh = trimesh.load(path)

    # Handle scene vs single mesh
    if isinstance(scene_or_mesh, trimesh.Scene):
        geometries = list(scene_or_mesh.geometry.items())
    elif isinstance(scene_or_mesh, trimesh.Trimesh):
        geometries = [('mesh_0', scene_or_mesh)]
    else:
        geometries = []

    texture_counter = 0

    for name, geom in geometries:
        if not isinstance(geom, trimesh.Trimesh):
            continue

        vertices = np.array(geom.vertices, dtype=np.float32)
        faces = np.array(geom.faces, dtype=np.uint32)

        # Normals
        if geom.vertex_normals is not None:
            normals = np.array(geom.vertex_normals, dtype=np.float32)
        else:
            normals = np.zeros_like(vertices)

        # UVs and textures from visual
        uvs = None
        colors = None
        material_index = -1

        if hasattr(geom, 'visual') and geom.visual is not None:
            vis = geom.visual

            # Check for TextureVisuals (has UVs and material with textures)
            if hasattr(vis, 'uv') and vis.uv is not None:
                uvs = np.array(vis.uv, dtype=np.float32)

            # Extract material and texture
            if hasattr(vis, 'material') and vis.material is not None:
                mat = vis.material
                material = Material(name=name or f'material_{len(model.materials)}')

                # Get diffuse color
                if hasattr(mat, 'baseColorFactor') and mat.baseColorFactor is not None:
                    bc = mat.baseColorFactor
                    material.diffuse_color = tuple(bc[:4]) if len(bc) >= 4 else (bc[0], bc[1], bc[2], 1.0)
                elif hasattr(mat, 'diffuse') and mat.diffuse is not None:
                    d = mat.diffuse
                    if hasattr(d, '__len__') and len(d) >= 3:
                        material.diffuse_color = (d[0], d[1], d[2], d[3] if len(d) > 3 else 1.0)

                # Get PBR properties
                if hasattr(mat, 'metallicFactor'):
                    material.metallic = float(mat.metallicFactor) if mat.metallicFactor is not None else 0.0
                if hasattr(mat, 'roughnessFactor'):
                    material.roughness = float(mat.roughnessFactor) if mat.roughnessFactor is not None else 0.5

                # Extract texture image (PBRMaterial uses baseColorTexture, SimpleMaterial uses image)
                texture_image = None
                if hasattr(mat, 'baseColorTexture') and mat.baseColorTexture is not None:
                    texture_image = mat.baseColorTexture
                elif hasattr(mat, 'image') and mat.image is not None:
                    texture_image = mat.image

                if texture_image is not None:
                    # Convert PIL image to bytes for storage
                    import io
                    texture_name = f'texture_{texture_counter}'
                    texture_counter += 1

                    try:
                        buf = io.BytesIO()
                        # Ensure RGBA mode
                        if texture_image.mode != 'RGBA':
                            texture_image = texture_image.convert('RGBA')
                        texture_image.save(buf, format='PNG')
                        model.textures[texture_name] = buf.getvalue()
                        material.diffuse_texture = texture_name
                    except Exception as e:
                        print(f"Error saving texture: {e}")

                material_index = len(model.materials)
                model.materials.append(material)

            # Fallback: vertex colors
            elif hasattr(vis, 'vertex_colors') and vis.vertex_colors is not None:
                colors = np.array(vis.vertex_colors, dtype=np.float32) / 255.0

        mesh_data = MeshData(
            name=name or f'mesh_{len(model.meshes)}',
            vertices=vertices,
            normals=normals,
            faces=faces,
            uvs=uvs,
            colors=colors,
            material_index=material_index
        )
        model.meshes.append(mesh_data)

    # Calculate bounds
    _calculate_bounds(model)

    return model


# ============================================================================
# ASSIMP LOADER (Fallback when Open3D not available)
# ============================================================================

def _is_ascii_fbx(path: str) -> bool:
    """Check if an FBX file is ASCII format (vs binary)."""
    try:
        with open(path, 'rb') as f:
            header = f.read(23)
            # ASCII FBX starts with "; FBX" or "Kaydara FBX Binary"
            # Binary FBX starts with "Kaydara FBX Binary  \x00"
            if header.startswith(b'Kaydara FBX Binary'):
                return False
            # Check for ASCII indicators
            if header.startswith(b'; FBX') or b'FBXHeaderExtension' in f.read(1000):
                return True
    except Exception:
        pass
    return False


def _load_with_assimp(path: str) -> ModelData:
    """Load a 3D model using Assimp."""
    if not ASSIMP_AVAILABLE:
        raise ImportError("pyassimp is not available. Install with: pip install pyassimp")

    # Check for ASCII FBX which can be problematic
    ext = os.path.splitext(path)[1].lower()
    if ext == '.fbx' and _is_ascii_fbx(path):
        # ASCII FBX files can cause issues with some Assimp versions
        # Try loading anyway but be prepared for failures
        pass

    # Assimp post-processing flags
    flags = (
        postprocess.aiProcess_Triangulate |
        postprocess.aiProcess_GenNormals |
        postprocess.aiProcess_CalcTangentSpace |
        postprocess.aiProcess_JoinIdenticalVertices |
        postprocess.aiProcess_SortByPType |
        postprocess.aiProcess_FlipUVs
    )

    # Try loading with pyassimp - catch NULL pointer and other errors
    context = None
    try:
        context = pyassimp.load(path, processing=flags)
    except Exception as e:
        error_msg = str(e)
        # If full processing fails, try with minimal flags
        if "NULL" in error_msg.upper() or "null" in error_msg.lower():
            try:
                # Try with just triangulation - fewer flags = fewer potential issues
                minimal_flags = postprocess.aiProcess_Triangulate
                context = pyassimp.load(path, processing=minimal_flags)
            except Exception as e2:
                # Last resort: try with NO post-processing flags
                try:
                    context = pyassimp.load(path, processing=0)
                except Exception as e3:
                    raise ValueError(
                        f"Assimp failed to parse FBX (NULL pointer error). "
                        f"The file may use an unsupported FBX format or be corrupted."
                    )
        else:
            raise

    if context is None:
        raise ValueError("Failed to load model with Assimp")

    # Use context manager (required for newer pyassimp versions)
    with context as scene:
        # Validate scene
        if scene is None:
            raise ValueError("Assimp returned NULL scene - file may be corrupted or unsupported")

        model = ModelData(path=path)
        base_dir = os.path.dirname(path)

        # Debug: Print what we found
        num_meshes = len(scene.meshes) if scene.meshes else 0
        num_anims = len(scene.animations) if hasattr(scene, 'animations') and scene.animations else 0
        print(f"Assimp loaded: {num_meshes} meshes, {num_anims} animations")

        # Load materials
        model.materials = _extract_materials(scene, base_dir)

        # Load embedded textures
        model.textures = _extract_embedded_textures(scene)

        # Load meshes
        model.meshes = _extract_meshes(scene)

        # Load skeleton
        model.skeleton = _extract_skeleton(scene)

        # Load animations
        model.animations = _extract_animations(scene)

        # Calculate bounds
        _calculate_bounds(model)

        return model


def _extract_materials(scene, base_dir: str) -> List[Material]:
    """Extract materials from Assimp scene."""
    materials = []

    for mat in scene.materials:
        material = Material(name=mat.properties.get('name', f'Material_{len(materials)}'))

        # Diffuse color
        if 'diffuse' in mat.properties:
            diffuse = mat.properties['diffuse']
            if len(diffuse) >= 3:
                material.diffuse_color = (diffuse[0], diffuse[1], diffuse[2],
                                         diffuse[3] if len(diffuse) > 3 else 1.0)

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
            # Handle relative paths
            if not os.path.isabs(tex_path):
                tex_path = os.path.join(base_dir, tex_path)
            material.diffuse_texture = tex_path

        materials.append(material)

    return materials


def _extract_embedded_textures(scene) -> Dict[str, bytes]:
    """Extract embedded textures from Assimp scene."""
    textures = {}

    if hasattr(scene, 'textures') and scene.textures:
        for i, tex in enumerate(scene.textures):
            if tex.data:
                # Create a name for the embedded texture
                name = f"*{i}"  # Assimp convention for embedded textures
                textures[name] = bytes(tex.data)

    return textures


def _extract_meshes(scene) -> List[MeshData]:
    """Extract meshes from Assimp scene."""
    meshes = []

    for mesh in scene.meshes:
        mesh_data = MeshData(
            name=mesh.name or f"Mesh_{len(meshes)}",
            vertices=np.array(mesh.vertices, dtype=np.float32),
            normals=np.array(mesh.normals, dtype=np.float32) if mesh.normals.size > 0 else np.zeros_like(mesh.vertices, dtype=np.float32),
            faces=np.array([face.indices for face in mesh.faces], dtype=np.uint32),
            material_index=mesh.materialindex
        )

        # UV coordinates (first set)
        if mesh.texturecoords.size > 0 and len(mesh.texturecoords) > 0:
            uvs = mesh.texturecoords[0]
            if uvs is not None and len(uvs) > 0:
                # Only take first 2 components (U, V)
                mesh_data.uvs = np.array(uvs[:, :2], dtype=np.float32)

        # Vertex colors (first set)
        if hasattr(mesh, 'colors') and mesh.colors.size > 0:
            colors = mesh.colors[0]
            if colors is not None and len(colors) > 0:
                mesh_data.colors = np.array(colors, dtype=np.float32)

        # Bone weights
        if mesh.bones:
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

        meshes.append(mesh_data)

    return meshes


def _extract_skeleton(scene) -> Optional[Skeleton]:
    """Extract skeleton from Assimp scene."""
    # Collect all bones from meshes (if any)
    bone_names = set()
    bone_offsets = {}

    for mesh in scene.meshes:
        if mesh.bones:
            for bone in mesh.bones:
                bone_names.add(bone.name)
                bone_offsets[bone.name] = np.array(bone.offsetmatrix, dtype=np.float32).reshape(4, 4).T

    # Build skeleton from node hierarchy
    skeleton = Skeleton()

    # For skeleton-only files (mocap, HyMotion), we need to look at ALL nodes
    # Not just bones referenced by meshes
    skeleton_only_mode = len(bone_names) == 0

    def process_node(node, parent_index=-1):
        """Recursively process nodes to build bone hierarchy."""
        is_bone = False

        if skeleton_only_mode:
            # In skeleton-only mode, consider any node that's not the root or a camera/light as a bone
            # Skip nodes with "Root", "Scene", "Camera", "Light" in name
            node_name_lower = node.name.lower()
            skip_keywords = ['camera', 'light', 'ambientlight']

            # Include if it's not a skip keyword and has children or transformations
            if not any(kw in node_name_lower for kw in skip_keywords):
                is_bone = True
        else:
            # Normal mode: only process nodes that are referenced as bones in meshes
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


def _extract_animations(scene) -> List[Animation]:
    """Extract animations from Assimp scene."""
    animations = []

    if not hasattr(scene, 'animations') or not scene.animations:
        return animations

    for anim in scene.animations:
        animation = Animation(
            name=anim.name or f"Animation_{len(animations)}",
            duration=float(anim.duration),
            ticks_per_second=float(anim.tickspersecond) if anim.tickspersecond > 0 else 25.0
        )

        # Convert duration from ticks to seconds
        animation.duration = animation.duration / animation.ticks_per_second

        # Extract bone animations
        for channel in anim.channels:
            bone_anim = BoneAnimation(bone_name=channel.nodename)

            # Position keyframes
            for key in channel.positionkeys:
                bone_anim.position_keys.append(VectorKeyframe(
                    time=float(key.time) / animation.ticks_per_second,
                    value=np.array([key.value.x, key.value.y, key.value.z], dtype=np.float32)
                ))

            # Rotation keyframes
            for key in channel.rotationkeys:
                bone_anim.rotation_keys.append(QuaternionKeyframe(
                    time=float(key.time) / animation.ticks_per_second,
                    value=np.array([key.value.x, key.value.y, key.value.z, key.value.w], dtype=np.float32)
                ))

            # Scale keyframes
            for key in channel.scalingkeys:
                bone_anim.scale_keys.append(VectorKeyframe(
                    time=float(key.time) / animation.ticks_per_second,
                    value=np.array([key.value.x, key.value.y, key.value.z], dtype=np.float32)
                ))

            animation.bone_animations[channel.nodename] = bone_anim

        animations.append(animation)

    return animations


def _calculate_bounds(model: ModelData):
    """Calculate bounding box for the model."""
    if not model.meshes:
        return

    all_vertices = []
    for mesh in model.meshes:
        if mesh.vertices is not None and len(mesh.vertices) > 0:
            all_vertices.append(mesh.vertices)

    if all_vertices:
        combined = np.vstack(all_vertices)
        model.bounds_min = np.min(combined, axis=0).astype(np.float32)
        model.bounds_max = np.max(combined, axis=0).astype(np.float32)


# ============================================================================
# USD LOADER (Fallback)
# ============================================================================

def _load_with_usd(path: str) -> ModelData:
    """Load a USD file using OpenUSD (pxr)."""
    if not USD_AVAILABLE:
        raise ImportError("USD support requires pxr. Install with: pip install usd-core")

    model = ModelData(path=path)
    stage = Usd.Stage.Open(path)

    if not stage:
        raise ValueError(f"Failed to open USD file: {path}")

    # Traverse the stage and extract geometry
    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.Mesh):
            mesh_prim = UsdGeom.Mesh(prim)

            # Get vertices
            points = mesh_prim.GetPointsAttr().Get()
            if not points:
                continue

            vertices = np.array(points, dtype=np.float32)

            # Get face vertex indices
            face_counts = mesh_prim.GetFaceVertexCountsAttr().Get()
            face_indices = mesh_prim.GetFaceVertexIndicesAttr().Get()

            if not face_counts or not face_indices:
                continue

            # Convert to triangles
            faces = []
            idx = 0
            for count in face_counts:
                if count == 3:
                    faces.append([face_indices[idx], face_indices[idx+1], face_indices[idx+2]])
                elif count == 4:
                    # Triangulate quad
                    faces.append([face_indices[idx], face_indices[idx+1], face_indices[idx+2]])
                    faces.append([face_indices[idx], face_indices[idx+2], face_indices[idx+3]])
                idx += count

            # Get normals
            normals_attr = mesh_prim.GetNormalsAttr().Get()
            if normals_attr:
                normals = np.array(normals_attr, dtype=np.float32)
            else:
                normals = np.zeros_like(vertices)

            mesh_data = MeshData(
                name=prim.GetName(),
                vertices=vertices,
                normals=normals,
                faces=np.array(faces, dtype=np.uint32) if faces else np.array([], dtype=np.uint32)
            )

            # Get UVs if available
            uv_attr = mesh_prim.GetPrimvar("st")
            if uv_attr:
                uvs = uv_attr.Get()
                if uvs:
                    mesh_data.uvs = np.array(uvs, dtype=np.float32)

            model.meshes.append(mesh_data)

    # Extract skeleton if available
    for prim in stage.Traverse():
        if prim.IsA(UsdSkel.Skeleton):
            skel = UsdSkel.Skeleton(prim)
            joints = skel.GetJointsAttr().Get()

            if joints:
                skeleton = Skeleton()
                for i, joint in enumerate(joints):
                    # Parse joint path to get parent
                    parts = joint.split('/')
                    parent_index = -1
                    if len(parts) > 1:
                        parent_path = '/'.join(parts[:-1])
                        parent_index = skeleton.bone_name_to_index.get(parent_path, -1)

                    bone = Bone(
                        name=joint,
                        index=i,
                        parent_index=parent_index,
                        offset_matrix=np.eye(4, dtype=np.float32)
                    )
                    skeleton.bones.append(bone)
                    skeleton.bone_name_to_index[joint] = i

                model.skeleton = skeleton
                break

    _calculate_bounds(model)
    return model


# ============================================================================
# SMPL NPZ LOADER (For HyMotion skeleton data)
# ============================================================================

def _load_smpl_npz(path: str) -> ModelData:
    """Load SMPL skeleton data from HyMotion NPZ files."""
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

        # SMPL has 22 joints (not including root)
        # Total: 1 root + 22 body joints = 23 joints
        # But SMPL format typically stores 22 joints (root is separate as Rh)
        num_frames = len(poses)

        # Build skeleton from SMPL joint hierarchy
        # SMPL joint names (standard SMPL-H hierarchy)
        smpl_joint_names = [
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
        smpl_parents = [
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

        skeleton = Skeleton()

        # Create bones
        for i, (name, parent_idx) in enumerate(zip(smpl_joint_names, smpl_parents)):
            bone = Bone(
                name=name,
                index=i,
                parent_index=parent_idx,
                offset_matrix=np.eye(4, dtype=np.float32),
                local_transform=np.eye(4, dtype=np.float32)
            )
            skeleton.bones.append(bone)
            skeleton.bone_name_to_index[name] = i

        model.skeleton = skeleton

        # Create animation from the data
        if num_frames > 1:
            animation = Animation(
                name="SMPL Motion",
                duration=num_frames / 30.0,  # Assume 30 FPS
                ticks_per_second=30.0
            )

            # For each bone, create animation channels
            # We'll store the poses data for later use
            # (The actual animation playback would need to convert axis-angle to matrices)

            model.animations.append(animation)

        # Calculate simple bounds from first frame translation
        if len(trans) > 0:
            root_pos = trans[0].astype(np.float32)
            # SMPL body is roughly 1.7m tall, so use that as bounds
            model.bounds_min = root_pos - np.array([0.5, 0.0, 0.5], dtype=np.float32)
            model.bounds_max = root_pos + np.array([0.5, 1.7, 0.5], dtype=np.float32)

    return model


# ============================================================================
# PUBLIC API
# ============================================================================

def load_model(path: str) -> ModelData:
    """
    Load a 3D model from file.

    Uses the best available loader in this priority order:
    1. USD (pxr) for USD files
    2. Trimesh for GLB/GLTF (best embedded texture extraction)
    3. PyAssimp for FBX (skeleton/animation support)
    4. Open3D for simple formats (OBJ, STL, PLY)

    Args:
        path: Path to the 3D model file

    Returns:
        ModelData containing all loaded data

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If format is not supported
        ImportError: If required libraries are not available
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Model file not found: {path}")

    ext = os.path.splitext(path)[1].lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported format: {ext}")

    format_type = get_format_type(path)
    errors = []

    # For USD files, prefer the USD loader
    if format_type == 'usd':
        if USD_AVAILABLE:
            try:
                return _load_with_usd(path)
            except Exception as e:
                errors.append(f"USD loader: {e}")
        else:
            errors.append("USD support requires pxr. Install with: pip install usd-core")

    # For GLB/GLTF, prefer trimesh (best embedded texture extraction)
    # pyassimp doesn't properly extract compressed embedded textures from GLB
    if TRIMESH_AVAILABLE and format_type == 'gltf':
        try:
            return _load_with_trimesh(path)
        except Exception as e:
            errors.append(f"Trimesh loader: {e}")

    # For NPZ files (HyMotion SMPL data), load directly
    if format_type == 'other' and path.lower().endswith('.npz'):
        try:
            return _load_smpl_npz(path)
        except Exception as e:
            errors.append(f"NPZ loader: {e}")

    # For FBX, prefer pyassimp (skeleton/animation support)
    if ASSIMP_AVAILABLE and format_type == 'fbx':
        try:
            return _load_with_assimp(path)
        except Exception as e:
            errors.append(f"Assimp loader: {e}")

    # Try Open3D for OBJ and other simple formats
    if OPEN3D_AVAILABLE:
        try:
            return _load_with_open3d(path)
        except Exception as e:
            errors.append(f"Open3D loader: {e}")

    # Try trimesh for remaining formats (OBJ, Collada, etc.)
    if TRIMESH_AVAILABLE and format_type in ('obj', 'collada', 'other'):
        try:
            return _load_with_trimesh(path)
        except Exception as e:
            errors.append(f"Trimesh loader: {e}")

    # Try pyassimp as last resort
    if ASSIMP_AVAILABLE:
        try:
            return _load_with_assimp(path)
        except Exception as e:
            errors.append(f"Assimp loader: {e}")

    # No loader succeeded
    if not any([OPEN3D_AVAILABLE, TRIMESH_AVAILABLE, ASSIMP_AVAILABLE, USD_AVAILABLE]):
        raise ImportError(
            "No 3D model loaders available. Install one of:\n"
            "  pip install open3d  (recommended - supports FBX, GLB, OBJ, etc.)\n"
            "  pip install trimesh  (for GLB, GLTF, OBJ)\n"
            "  pip install pyassimp  (requires Assimp native library)"
        )

    raise ValueError(f"Failed to load model '{path}':\n" + "\n".join(f"  - {e}" for e in errors))


def get_loader_availability() -> Dict[str, bool]:
    """Check which loaders are available."""
    return {
        'open3d': OPEN3D_AVAILABLE,
        'trimesh': TRIMESH_AVAILABLE,
        'assimp': ASSIMP_AVAILABLE,
        'usd': USD_AVAILABLE,
    }
