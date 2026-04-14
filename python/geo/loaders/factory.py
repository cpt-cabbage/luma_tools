"""
Model loader factory.

Provides a unified interface for loading 3D models using the best available loader.
Implements priority-based loader selection based on format and library availability.
"""

import os
import threading
from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    # Avoid circular import: geo.loader re-exports symbols from this module.
    from geo.loader import ModelData

# Import loaders
from .open3d_loader import Open3DModelLoader
from .trimesh_loader import TrimeshModelLoader
from .assimp_loader import AssimpModelLoader, ASSIMP_AVAILABLE
from .usd_loader import USDModelLoader
from .smpl_loader import SMPLModelLoader

# All supported extensions
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

# Singleton loader instances
_loaders_lock = threading.RLock()
_loaders = None


def _get_loaders() -> List:
    """Get all loader instances (lazy initialization)."""
    global _loaders
    if _loaders is not None:
        return _loaders
    with _loaders_lock:
        if _loaders is not None:
            return _loaders
        _loaders = [
            USDModelLoader(),
            TrimeshModelLoader(),
            AssimpModelLoader(),
            Open3DModelLoader(),
            SMPLModelLoader(),
        ]
        return _loaders


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
    elif ext == '.npz':
        return 'npz'
    else:
        return 'other'


def is_supported_format(path: str) -> bool:
    """Check if the file format is supported."""
    ext = os.path.splitext(path)[1].lower()
    return ext in SUPPORTED_EXTENSIONS


def load_model(path: str) -> "ModelData":
    """
    Load a 3D model from file.

    Uses the best available loader in this priority order:
    1. USD (pxr) for USD files
    2. Trimesh for GLB/GLTF (best embedded texture extraction)
    3. PyAssimp for FBX (skeleton/animation support)
    4. Open3D for simple formats (OBJ, STL, PLY)
    5. SMPL loader for NPZ files (HyMotion data)

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
    loaders = _get_loaders()

    # Build priority order based on format
    priority_order = _get_loader_priority(format_type, loaders)

    # Try loaders in priority order
    for loader in priority_order:
        if not loader.is_available:
            errors.append(f"{loader.name} loader: not available")
            continue

        if ext not in loader.supported_extensions:
            continue

        try:
            return loader.load(path)
        except Exception as e:
            errors.append(f"{loader.name} loader: {e}")

    # No loader succeeded
    if not any(loader.is_available for loader in loaders):
        raise ImportError(
            "No 3D model loaders available. Install one of:\n"
            "  pip install open3d  (recommended - supports FBX, GLB, OBJ, etc.)\n"
            "  pip install trimesh  (for GLB, GLTF, OBJ)\n"
            "  pip install pyassimp  (requires Assimp native library)"
        )

    raise ValueError(f"Failed to load model '{path}':\n" + "\n".join(f"  - {e}" for e in errors))


def _get_loader_priority(format_type: str, loaders: List) -> List:
    """Get loaders in priority order based on format type."""
    # Find loaders by name for ordering
    loader_map = {loader.name: loader for loader in loaders}

    # Define priority by format
    priority_names = {
        'usd': ['USD', 'Trimesh', 'Assimp', 'Open3D'],
        'gltf': ['Trimesh', 'Open3D', 'Assimp'],
        'fbx': ['Assimp', 'Open3D', 'Trimesh'],
        'obj': ['Open3D', 'Trimesh', 'Assimp'],
        'collada': ['Assimp', 'Trimesh', 'Open3D'],
        'npz': ['SMPL'],
        'other': ['Open3D', 'Trimesh', 'Assimp'],
    }

    names = priority_names.get(format_type, priority_names['other'])
    return [loader_map[name] for name in names if name in loader_map]


def get_loader_availability() -> Dict[str, bool]:
    """Check which loaders are available."""
    loaders = _get_loaders()
    return {loader.name.lower(): loader.is_available for loader in loaders}
