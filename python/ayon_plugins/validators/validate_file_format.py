"""
Validate that file format matches the selected product type.

Ensures consistency between what the user selects and what they're publishing.
"""

import os
from typing import Dict, Set
from .base import BaseValidator, InstanceData, ValidationResult


# Mapping of product types to allowed file extensions
# Based on AYON standards used in Houdini, Blender, Maya, etc.
PRODUCT_TYPE_EXTENSIONS: Dict[str, Set[str]] = {
    "model": {
        ".glb", ".gltf", ".obj", ".fbx",
        ".usd", ".usda", ".usdc", ".usdz",
        ".abc"  # Alembic can contain geometry
    },
    "pointcache": {
        ".abc", ".npz", ".bgeo", ".bgeo.sc",
        ".usd", ".usda", ".usdc"
    },
    "camera": {
        ".abc", ".usd", ".usda", ".usdc", ".fbx"
    },
    "animation": {
        ".abc", ".fbx", ".usd", ".usda", ".usdc",
        ".npz", ".json"  # Animation data
    },
    "rig": {
        ".fbx", ".glb", ".gltf",
        ".usd", ".usda", ".usdc"
    },
    "look": {
        ".json", ".mtlx",  # Material data
        ".usd", ".usda", ".usdc"  # USD can contain materials
    },
    "image": {
        ".png", ".jpg", ".jpeg", ".tif", ".tiff",
        ".exr", ".hdr", ".dpx", ".bmp", ".tga", ".webp"
    },
    "render": {
        ".png", ".jpg", ".jpeg", ".tif", ".tiff",
        ".exr", ".hdr", ".dpx"
    },
    "plate": {
        ".png", ".jpg", ".jpeg", ".tif", ".tiff",
        ".exr", ".dpx", ".mov", ".mp4"
    },
    "review": {
        ".mp4", ".mov", ".avi", ".mkv", ".webm",
        ".gif"  # Animated GIFs count as review
    },
    "audio": {
        ".wav", ".mp3", ".aiff", ".aif", ".flac", ".ogg"
    },
}


class ValidateFileFormat(BaseValidator):
    """
    Validate that the file extension matches the selected product type.

    Uses AYON-standard product type to extension mappings.
    This helps catch mismatches early (e.g., publishing a .png as "model").
    """

    name = "ValidateFileFormat"
    label = "File Format"
    description = "Validate that file extension matches product type"
    enabled = True
    optional = False  # This is a blocking validator

    def validate(self, instance: InstanceData) -> ValidationResult:
        """
        Check that file extension is valid for the product type.

        Args:
            instance: InstanceData with source_file and product_type set

        Returns:
            ValidationResult with pass/fail status
        """
        source_file = instance.source_file
        product_type = instance.product_type

        if not source_file:
            return ValidationResult(
                validator=self.name,
                passed=False,
                message="No source file specified"
            )

        if not product_type:
            return ValidationResult(
                validator=self.name,
                passed=False,
                message="No product type specified",
                details="Please select a product type (model, image, review, etc.)"
            )

        # Get file extension (lowercase)
        ext = os.path.splitext(source_file)[1].lower()

        if not ext:
            return ValidationResult(
                validator=self.name,
                passed=False,
                message="File has no extension",
                details=f"The file '{os.path.basename(source_file)}' has no extension. "
                        "Cannot determine file format."
            )

        # Get allowed extensions for product type
        allowed_extensions = PRODUCT_TYPE_EXTENSIONS.get(product_type)

        if allowed_extensions is None:
            # Unknown product type - pass but warn
            return ValidationResult(
                validator=self.name,
                passed=True,
                message=f"Unknown product type '{product_type}' - skipping format validation",
                details=f"The product type '{product_type}' is not in the known list. "
                        "Validation skipped."
            )

        if ext not in allowed_extensions:
            # Build list of allowed extensions for error message
            allowed_str = ", ".join(sorted(allowed_extensions))

            return ValidationResult(
                validator=self.name,
                passed=False,
                message=f"Extension '{ext}' is not valid for product type '{product_type}'",
                details=f"The file extension '{ext}' is not typically associated with "
                        f"the '{product_type}' product type.\n\n"
                        f"Allowed extensions for '{product_type}': {allowed_str}\n\n"
                        "Please select a different product type or use a different file."
            )

        return ValidationResult(
            validator=self.name,
            passed=True,
            message=f"Extension '{ext}' is valid for product type '{product_type}'"
        )
