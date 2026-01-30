"""
Trimesh-based model loader.

Uses Trimesh library for loading 3D models.
Best for GLB/GLTF with embedded textures - properly extracts texture data.
"""

import os
import logging
from typing import Set

logger = logging.getLogger(__name__)

import numpy as np

from .base import BaseModelLoader
from geo.loader import ModelData, MeshData, Material
from core.import_utils import safe_import

trimesh, TRIMESH_AVAILABLE = safe_import("trimesh")


class TrimeshModelLoader(BaseModelLoader):
    """Model loader using Trimesh library. Best for GLB/GLTF with textures."""

    @property
    def name(self) -> str:
        return "Trimesh"

    @property
    def supported_extensions(self) -> Set[str]:
        return {'.glb', '.gltf', '.obj', '.dae', '.stl', '.ply'}

    @property
    def is_available(self) -> bool:
        return TRIMESH_AVAILABLE

    def load(self, path: str) -> ModelData:
        """Load a 3D model using Trimesh."""
        self._validate_load_preconditions(path, "trimesh")
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
                        texture_counter = self._extract_texture(
                            model, material, texture_image, texture_counter
                        )

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
        self._calculate_bounds(model)

        return model

    def _extract_texture(self, model: ModelData, material: Material,
                         texture_image, texture_counter: int) -> int:
        """Extract texture from PIL image and store in model."""
        import io

        texture_name = f'texture_{texture_counter}'

        try:
            buf = io.BytesIO()
            # Ensure RGBA mode
            if texture_image.mode != 'RGBA':
                texture_image = texture_image.convert('RGBA')
            texture_image.save(buf, format='PNG')
            model.textures[texture_name] = buf.getvalue()
            material.diffuse_texture = texture_name
            return texture_counter + 1
        except Exception as e:
            logger.error(f"Error saving texture: {e}")
            return texture_counter
