"""
Model loader package for Luma Tools.

Provides a unified interface for loading 3D models using a strategy pattern.
Each loader handles specific formats with appropriate libraries.

Usage:
    from models.loaders import load_model, get_loader_availability

    # Load any supported format
    model = load_model("path/to/model.glb")

    # Check available loaders
    availability = get_loader_availability()
"""

from .base import BaseModelLoader
from .factory import load_model, get_loader_availability, get_format_type

__all__ = [
    'BaseModelLoader',
    'load_model',
    'get_loader_availability',
    'get_format_type',
]
