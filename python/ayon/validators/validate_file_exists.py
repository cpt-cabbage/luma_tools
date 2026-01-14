"""
Validate that source file exists.

This is a critical validator - publishing cannot proceed if the file doesn't exist.
"""

import os
from .base import BaseValidator, InstanceData, ValidationResult


class ValidateFileExists(BaseValidator):
    """
    Validate that the source file to be published exists on disk.

    This is a mandatory validator - files must exist to be published.
    """

    name = "ValidateFileExists"
    label = "File Exists"
    description = "Validate that the source file exists on disk"
    enabled = True
    optional = False  # This is a blocking validator

    def validate(self, instance: InstanceData) -> ValidationResult:
        """
        Check that source_file exists.

        Args:
            instance: InstanceData with source_file set

        Returns:
            ValidationResult with pass/fail status
        """
        source_file = instance.source_file

        if not source_file:
            return ValidationResult(
                validator=self.name,
                passed=False,
                message="No source file specified",
                details="The source_file field in instance data is empty. "
                        "Please provide a file path to publish."
            )

        if not os.path.exists(source_file):
            return ValidationResult(
                validator=self.name,
                passed=False,
                message=f"Source file does not exist: {source_file}",
                details=f"The file at path '{source_file}' could not be found. "
                        "Please verify the file path is correct."
            )

        if not os.path.isfile(source_file):
            return ValidationResult(
                validator=self.name,
                passed=False,
                message=f"Source path is not a file: {source_file}",
                details=f"The path '{source_file}' exists but is not a file "
                        "(it may be a directory). Please provide a file path."
            )

        # Get file size for informational purposes
        file_size = os.path.getsize(source_file)
        file_size_mb = file_size / (1024 * 1024)

        return ValidationResult(
            validator=self.name,
            passed=True,
            message=f"File exists: {os.path.basename(source_file)} ({file_size_mb:.2f} MB)"
        )
