"""
USD-based model loader.

Uses OpenUSD (pxr) library for loading USD files.
Supports USD, USDA, USDC, and USDZ formats.
"""

import os
from typing import Set

import numpy as np

from .base import BaseModelLoader
from geo.loader import ModelData, MeshData, Bone, Skeleton
from core.import_utils import safe_import_multiple

(Usd, UsdGeom, UsdSkel), USD_AVAILABLE = safe_import_multiple("pxr", "Usd", "UsdGeom", "UsdSkel")


class USDModelLoader(BaseModelLoader):
    """Model loader using OpenUSD (pxr) library."""

    @property
    def name(self) -> str:
        return "USD"

    @property
    def supported_extensions(self) -> Set[str]:
        return {'.usd', '.usda', '.usdc', '.usdz'}

    @property
    def is_available(self) -> bool:
        return USD_AVAILABLE

    def load(self, path: str) -> ModelData:
        """Load a USD file using OpenUSD."""
        self._validate_load_preconditions(path, "pxr (usd-core)")
        model = ModelData(path=path)
        stage = Usd.Stage.Open(path)

        if not stage:
            raise ValueError(f"Failed to open USD file: {path}")

        # Extract meshes
        self._extract_meshes(stage, model)

        # Extract skeleton if available
        self._extract_skeleton(stage, model)

        # Calculate bounds
        self._calculate_bounds(model)

        return model

    def _extract_meshes(self, stage, model: ModelData) -> None:
        """Extract mesh geometry from USD stage."""
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
                faces = self._triangulate_faces(face_counts, face_indices)

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

    def _triangulate_faces(self, face_counts, face_indices) -> list:
        """Convert polygon faces to triangles."""
        faces = []
        idx = 0
        for count in face_counts:
            if count == 3:
                faces.append([face_indices[idx], face_indices[idx + 1], face_indices[idx + 2]])
            elif count == 4:
                # Triangulate quad
                faces.append([face_indices[idx], face_indices[idx + 1], face_indices[idx + 2]])
                faces.append([face_indices[idx], face_indices[idx + 2], face_indices[idx + 3]])
            # Skip n-gons with more than 4 vertices for now
            idx += count
        return faces

    def _extract_skeleton(self, stage, model: ModelData) -> None:
        """Extract skeleton from USD stage."""
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
                    break  # Only process first skeleton
