"""
Base model loader abstract class.

Defines the interface that all model loaders must implement.
"""

from abc import ABC, abstractmethod
from typing import Set

import numpy as np

# Import data types from parent module
from geo.loader import ModelData


class BaseModelLoader(ABC):
    """Abstract base class for 3D model loaders."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the loader."""
        pass

    @property
    @abstractmethod
    def supported_extensions(self) -> Set[str]:
        """Set of file extensions this loader supports (lowercase with dot)."""
        pass

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the required libraries for this loader are available."""
        pass

    @abstractmethod
    def load(self, path: str) -> ModelData:
        """
        Load a 3D model from the given path.

        Args:
            path: Absolute path to the model file

        Returns:
            ModelData containing all loaded data

        Raises:
            ImportError: If required libraries are not available
            ValueError: If file cannot be loaded
            FileNotFoundError: If file doesn't exist
        """
        pass

    def can_load(self, path: str) -> bool:
        """
        Check if this loader can handle the given file.

        Args:
            path: Path to check

        Returns:
            True if this loader supports the file format and is available
        """
        import os
        ext = os.path.splitext(path)[1].lower()
        return self.is_available and ext in self.supported_extensions

    def _validate_load_preconditions(self, path: str, library_name: str = None) -> None:
        """
        Validate preconditions before loading a model.

        Call this at the start of load() to check availability and file existence.

        Args:
            path: Path to the model file
            library_name: Name of the library for error message (uses self.name if not provided)

        Raises:
            ImportError: If required library is not available
            FileNotFoundError: If file doesn't exist
        """
        import os
        lib_name = library_name or self.name
        if not self.is_available:
            raise ImportError(f"{lib_name} is not available. Install the required library.")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Model file not found: {path}")

    def _calculate_bounds(self, model: ModelData) -> None:
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
