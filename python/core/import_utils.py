"""
Safe import utilities for optional dependencies.

Provides a consistent pattern for importing optional modules with availability flags.
"""

from typing import Tuple, Any, Optional
import importlib


def safe_import(module_path: str, attr: Optional[str] = None) -> Tuple[Optional[Any], bool]:
    """
    Safely import a module or attribute with availability flag.

    Args:
        module_path: Full module path (e.g., "pxr.Usd", "open3d")
        attr: Optional attribute name to import from module

    Returns:
        Tuple of (module_or_attr, is_available)

    Examples:
        >>> Usd, USD_AVAILABLE = safe_import("pxr", "Usd")
        >>> o3d, OPEN3D_AVAILABLE = safe_import("open3d")
        >>> QOpenGLWidget, GL_AVAILABLE = safe_import("PySide2.QtWidgets", "QOpenGLWidget")
    """
    try:
        module = importlib.import_module(module_path)
        if attr:
            return getattr(module, attr), True
        return module, True
    except (ImportError, AttributeError, ModuleNotFoundError):
        return None, False


def safe_import_multiple(module_path: str, *attrs: str) -> Tuple[Tuple[Optional[Any], ...], bool]:
    """
    Safely import multiple attributes from a module.

    Args:
        module_path: Full module path
        *attrs: Attribute names to import

    Returns:
        Tuple of ((attr1, attr2, ...), is_available)

    Example:
        >>> (Usd, Sdf, UsdGeom), USD_AVAILABLE = safe_import_multiple("pxr", "Usd", "Sdf", "UsdGeom")
    """
    try:
        module = importlib.import_module(module_path)
        values = tuple(getattr(module, attr) for attr in attrs)
        return values, True
    except (ImportError, AttributeError, ModuleNotFoundError):
        return tuple(None for _ in attrs), False
