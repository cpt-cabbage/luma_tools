"""Tests that farm-deployed scripts can be imported without the comfyui package.

The Deadline runner copies a handful of scripts from python/comfyui/ into a
flat _job_data/ directory with a 'comfyui_' prefix (e.g. utils.py becomes
comfyui_utils.py).  These scripts must be importable WITHOUT the comfyui
package on sys.path — otherwise every farm job fails with ModuleNotFoundError.

The test simulates that environment:
1. Copy the same files that submitter.py copies into a temp directory.
2. Remove any comfyui package paths from sys.path.
3. Try to import each copied module.
"""
import importlib
import os
import shutil
import sys
import tempfile

import pytest

# Source directory of the comfyui package
_COMFYUI_PKG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "python", "comfyui",
)

# Files copied to the farm, mapping source basename -> farm basename
# Must stay in sync with deadline/submitter.py
FARM_COPIES = {
    "runner.py": "comfyui_runner.py",
    "utils.py": "comfyui_utils.py",
    "analytics.py": "comfyui_analytics.py",
    "node_configs.py": "comfyui_node_configs.py",
}


@pytest.fixture()
def farm_env(tmp_path):
    """Create an isolated directory mimicking the farm _job_data/ folder.

    Copies the farm scripts, puts *only* that directory on sys.path, and
    removes any path entries that would let ``import comfyui`` succeed.
    """
    # Copy files
    for src_name, dst_name in FARM_COPIES.items():
        src = os.path.join(_COMFYUI_PKG, src_name)
        dst = os.path.join(tmp_path, dst_name)
        shutil.copy2(src, dst)

    # Snapshot original state
    original_path = sys.path[:]
    original_modules = {k: v for k, v in sys.modules.items()
                        if k.startswith("comfyui")}

    # Purge comfyui from sys.modules so re-imports hit our copies
    for key in list(sys.modules):
        if key.startswith("comfyui"):
            del sys.modules[key]

    # Build a clean sys.path: only the temp dir + stdlib/site-packages
    # (no entry that contains a comfyui/ package directory)
    clean_path = [str(tmp_path)]
    for p in original_path:
        if os.path.isdir(os.path.join(p, "comfyui")):
            continue  # skip — would let `import comfyui` succeed
        clean_path.append(p)
    sys.path[:] = clean_path

    yield tmp_path

    # Restore
    sys.path[:] = original_path
    # Remove modules we loaded from the temp dir
    for key in list(sys.modules):
        if key.startswith("comfyui"):
            del sys.modules[key]
    # Put back the originals
    sys.modules.update(original_modules)


class TestFarmImportIsolation:
    """Each farm-copied module must import cleanly without the comfyui package."""

    def test_node_configs_imports(self, farm_env):
        mod = importlib.import_module("comfyui_node_configs")
        assert hasattr(mod, "EXPORT_NODE_TYPES")
        assert hasattr(mod, "OUTPUT_SUFFIX")

    def test_analytics_imports(self, farm_env):
        importlib.import_module("comfyui_analytics")

    def test_utils_imports(self, farm_env):
        mod = importlib.import_module("comfyui_utils")
        # Verify the key symbols that runner.py needs are present
        assert hasattr(mod, "modify_workflow_seed")
        assert hasattr(mod, "has_output_suffix_nodes")
        assert hasattr(mod, "EXPORT_NODE_TYPES")

    def test_runner_imports(self, farm_env):
        """runner.py is the actual entry-point Deadline executes."""
        importlib.import_module("comfyui_runner")


class TestSubmitterCopyListComplete:
    """Verify every comfyui.* import in the farm scripts has a matching copy."""

    @staticmethod
    def _collect_comfyui_fallback_imports(filepath):
        """Return set of module basenames imported via comfyui_<name> pattern."""
        imports = set()
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                # Match "from comfyui_<name> import" or "import comfyui_<name>"
                if stripped.startswith("from comfyui_"):
                    module = stripped.split()[1].split(".")[0]
                    imports.add(module)
                elif stripped.startswith("import comfyui_"):
                    module = stripped.split()[1].split(".")[0]
                    imports.add(module)
        return imports

    def test_all_fallback_imports_have_source_copy(self):
        """Every comfyui_<x> import in farm scripts must have a matching entry
        in the submitter copy list so the file actually exists on the farm."""
        farm_basenames = set(FARM_COPIES.values())
        # Strip .py to get module names
        farm_modules = {os.path.splitext(b)[0] for b in farm_basenames}

        missing = set()
        for src_name in FARM_COPIES:
            src_path = os.path.join(_COMFYUI_PKG, src_name)
            needed = self._collect_comfyui_fallback_imports(src_path)
            for mod in needed:
                if mod not in farm_modules:
                    missing.add((src_name, mod))

        assert not missing, (
            f"Farm scripts import modules that are NOT copied by submitter.py: "
            f"{missing}. Add them to FARM_COPIES in submitter.py."
        )
