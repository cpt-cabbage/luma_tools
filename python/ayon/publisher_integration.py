"""
AYON Publisher Integration for Luma Tools.

Provides proper AYON publisher integration following the same patterns as
Houdini, Blender, and other DCCs. Uses AYON's standardized publishing API.
"""

# Check if AYON is available
try:
    from ayon_core.tools.publisher import show as show_publisher
    AYON_PUBLISHER_AVAILABLE = True
except ImportError:
    AYON_PUBLISHER_AVAILABLE = False
    print("Warning: AYON publisher tools not available")


def open_ayon_publisher():
    """
    Open the standard AYON Publisher UI.

    This is the same publisher UI used by Houdini, Blender, etc.
    It provides:
    - Instance management
    - Validation
    - Product type selection
    - Version control
    - Comment/notes

    Returns:
        bool: True if publisher was opened successfully
    """
    if not AYON_PUBLISHER_AVAILABLE:
        return False

    try:
        # Open AYON's standard publisher window
        # This is the same UI you see in Houdini/Blender
        show_publisher()
        return True
    except Exception as e:
        print(f"Failed to open AYON Publisher: {e}")
        import traceback
        traceback.print_exc()
        return False
