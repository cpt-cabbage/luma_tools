"""
Open3D-based model loader.

Uses Open3D library (which bundles Assimp) for loading 3D models.
Best for simple mesh formats like OBJ, STL, PLY.
"""

import os
from typing import Set

import numpy as np

from .base import BaseModelLoader
from geo.loader import ModelData, MeshData
from core.import_utils import safe_import

o3d, OPEN3D_AVAILABLE = safe_import("open3d")


class Open3DModelLoader(BaseModelLoader):
    """Model loader using Open3D library."""

    @property
    def name(self) -> str:
        return "Open3D"

    @property
    def supported_extensions(self) -> Set[str]:
        return {'.obj', '.stl', '.ply', '.fbx', '.glb', '.gltf'}

    @property
    def is_available(self) -> bool:
        return OPEN3D_AVAILABLE

    def load(self, path: str) -> ModelData:
        """Load a 3D model using Open3D."""
        self._validate_load_preconditions(path, "open3d")
        model = ModelData(path=path)

        # Read the mesh
        mesh = o3d.io.read_triangle_mesh(path, enable_post_processing=True)

        if mesh.is_empty():
            ext = os.path.splitext(path)[1].lower()
            if ext == '.fbx':
                # FBX file with no mesh data - likely skeleton/animation only
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

        # Get UVs if available (Open3D stores per-triangle, skip complex reorganization)
        uvs = None

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
