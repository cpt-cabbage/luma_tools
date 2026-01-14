"""
Validate that product names follow naming conventions.

Ensures product names are valid identifiers that work well with
AYON's database and file system requirements.
"""

import re
from .base import BaseValidator, InstanceData, ValidationResult


# Valid product name pattern: starts with letter, alphanumeric + underscores
# This is the AYON standard naming convention
PRODUCT_NAME_PATTERN = re.compile(r'^[a-zA-Z][a-zA-Z0-9_]*$')

# Reserved names that shouldn't be used
RESERVED_NAMES = {
    'main', 'master', 'default', 'none', 'null', 'undefined',
    'test', 'temp', 'tmp', 'new', 'copy',
}

# Maximum name length (practical limit for file systems and databases)
MAX_NAME_LENGTH = 64


class ValidateNamingConvention(BaseValidator):
    """
    Validate that product name follows AYON naming conventions.

    Rules:
    - Must start with a letter (a-z, A-Z)
    - Can contain letters, numbers, and underscores
    - Cannot contain spaces or special characters
    - Cannot be a reserved name
    - Must be under 64 characters
    """

    name = "ValidateNamingConvention"
    label = "Naming Convention"
    description = "Validate that product name follows AYON conventions"
    enabled = True
    optional = False  # This is a blocking validator

    def validate(self, instance: InstanceData) -> ValidationResult:
        """
        Check that product_name follows naming conventions.

        Args:
            instance: InstanceData with product_name set

        Returns:
            ValidationResult with pass/fail status
        """
        product_name = instance.product_name

        if not product_name:
            return ValidationResult(
                validator=self.name,
                passed=False,
                message="Product name is required",
                details="Please provide a product name for publishing."
            )

        # Check length
        if len(product_name) > MAX_NAME_LENGTH:
            return ValidationResult(
                validator=self.name,
                passed=False,
                message=f"Product name too long ({len(product_name)} characters)",
                details=f"Product name must be {MAX_NAME_LENGTH} characters or less. "
                        f"Current name is {len(product_name)} characters."
            )

        # Check for invalid characters
        if not PRODUCT_NAME_PATTERN.match(product_name):
            # Provide specific feedback on what's wrong
            issues = []

            if not product_name[0].isalpha():
                issues.append("must start with a letter (a-z, A-Z)")

            if ' ' in product_name:
                issues.append("cannot contain spaces (use underscores instead)")

            invalid_chars = set(re.findall(r'[^a-zA-Z0-9_]', product_name))
            if invalid_chars:
                chars_str = ', '.join(f"'{c}'" for c in sorted(invalid_chars))
                issues.append(f"contains invalid characters: {chars_str}")

            issues_str = '\n- '.join(issues)

            return ValidationResult(
                validator=self.name,
                passed=False,
                message=f"Invalid product name: '{product_name}'",
                details=f"Product name '{product_name}' has the following issues:\n- {issues_str}\n\n"
                        "Valid names: start with a letter, contain only letters, numbers, and underscores.\n"
                        "Examples: myModel, character_v01, prop_table_highres"
            )

        # Check reserved names
        if product_name.lower() in RESERVED_NAMES:
            return ValidationResult(
                validator=self.name,
                passed=False,
                message=f"'{product_name}' is a reserved name",
                details=f"The name '{product_name}' is reserved and cannot be used.\n"
                        "Please choose a more descriptive name for your product."
            )

        # Also validate variant if present
        variant = instance.variant
        if variant:
            if not PRODUCT_NAME_PATTERN.match(variant):
                return ValidationResult(
                    validator=self.name,
                    passed=False,
                    message=f"Invalid variant name: '{variant}'",
                    details="Variant names follow the same rules as product names:\n"
                            "- Start with a letter\n"
                            "- Only letters, numbers, and underscores\n"
                            "Examples: highres, lowres, v2, final"
                )

        return ValidationResult(
            validator=self.name,
            passed=True,
            message=f"Product name '{product_name}' is valid"
        )
