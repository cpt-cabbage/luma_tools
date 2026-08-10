"""
USD-based model loader.

Uses OpenUSD (pxr) library for loading USD files.
Supports USD, USDA, USDC, and USDZ formats.
"""

import os
from typing import Set

# numpy is optional (mirrors base.py) — a broken venv must not make the
# whole geo.loaders import graph blow up; this loader just reports
# unavailable instead.
try:
    import numpy as np
except Exception:
    np = None

from .base import BaseModelLoader
from geo.loader import ModelData, MeshData, Bone, Skeleton

# pxr is imported lazily on first availability check — importing every 3D
# library eagerly cost ~11.5 s at `import geo.loaders` time, before any
# file was ever opened.
Usd = UsdGeom = UsdSkel = None
USD_AVAILABLE = False
_pxr_checked = False


def _ensure_pxr() -> bool:
    """Import pxr on first use and report availability."""
    global Usd, UsdGeom, UsdSkel, USD_AVAILABLE, _pxr_checked
    if not _pxr_checked:
        from core.import_utils import safe_import_multiple
        (Usd, UsdGeom, UsdSkel), USD_AVAILABLE = safe_import_multiple(
            "pxr", "Usd", "UsdGeom", "UsdSkel"
        )
        _pxr_checked = True
    return USD_AVAILABLE and np is not None


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
        return _ensure_pxr()

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
                if normals_attr is not None:
                    interp = mesh_prim.GetNormalsInterpolation()
                    if interp == 'vertex' or interp == 'varying':
                        normals = np.array(normals_attr, dtype=np.float32)
                    elif interp == 'faceVarying' and face_counts is not None:
                        normals = None
                    else:
                        normals = np.array(normals_attr, dtype=np.float32)
                else:
                    normals = None

                if normals is None:
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
