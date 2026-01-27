"""
Base classes and utilities for AYON validators.

Provides a validation framework similar to AYON's Pyblish plugins
but simplified for Luma Tools' use case.
"""

import logging
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """
    Raised when validation fails.

    Similar to AYON's PublishValidationError but standalone.
    """

    def __init__(self, message: str, validator_name: str = "", details: str = ""):
        super().__init__(message)
        self.validator_name = validator_name
        self.details = details


@dataclass
class ValidationResult:
    """Result of a single validator."""
    validator: str
    passed: bool
    message: str = ""
    details: str = ""


@dataclass
class InstanceData:
    """
    Data about the item being published.

    Mirrors AYON's instance.data convention but as a simple dataclass.
    """
    source_file: str = ""
    product_type: str = ""
    product_name: str = ""
    variant: str = ""
    task: str = ""
    project_name: str = ""
    folder_path: str = ""
    user: str = ""
    comment: str = ""
    # Additional context
    extra: Dict[str, Any] = field(default_factory=dict)


class BaseValidator:
    """
    Base class for validators.

    Subclass and implement validate() to create new validators.
    Follows AYON/Pyblish conventions for consistency.

    Example:
        class ValidateMyThing(BaseValidator):
            name = "Validate My Thing"

            def validate(self, instance: InstanceData) -> ValidationResult:
                if not instance.source_file:
                    return ValidationResult(
                        validator=self.name,
                        passed=False,
                        message="No source file specified"
                    )
                return ValidationResult(validator=self.name, passed=True)
    """

    name: str = "Base Validator"
    label: str = ""  # Optional human-readable label
    description: str = ""
    enabled: bool = True
    optional: bool = False  # If True, failures don't block publish

    def validate(self, instance: InstanceData) -> ValidationResult:
        """
        Run validation on the instance data.

        Args:
            instance: InstanceData containing publish information

        Returns:
            ValidationResult indicating pass/fail and any messages
        """
        raise NotImplementedError("Subclass must implement validate()")


def run_validators(
    instance: InstanceData,
    validators: Optional[List[BaseValidator]] = None
) -> Tuple[bool, List[ValidationResult]]:
    """
    Run all validators against an instance.

    Args:
        instance: InstanceData to validate
        validators: Optional list of validators (uses defaults if not provided)

    Returns:
        Tuple of (all_passed, list of ValidationResult)
    """
    from .validate_file_exists import ValidateFileExists
    from .validate_file_format import ValidateFileFormat
    from .validate_naming_convention import ValidateNamingConvention

    if validators is None:
        validators = [
            ValidateFileExists(),
            ValidateFileFormat(),
            ValidateNamingConvention(),
        ]

    results: List[ValidationResult] = []
    all_passed = True

    for validator in validators:
        if not validator.enabled:
            continue

        result = validator.validate(instance)
        results.append(result)

        if not result.passed:
            if not validator.optional:
                all_passed = False
            logger.warning(f"[Validator] {validator.name}: FAILED - {result.message}")
        else:
            logger.info(f"[Validator] {validator.name}: PASSED")

    return all_passed, results
