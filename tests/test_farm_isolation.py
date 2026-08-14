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
import json
import os
import shutil
import subprocess
import sys

import pytest

_PYTHON_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "python",
)
# Source directories of the farm-copied packages
_COMFYUI_PKG = os.path.join(_PYTHON_ROOT, "comfyui")
_CORE_PKG = os.path.join(_PYTHON_ROOT, "core")

# Files copied to the farm, mapping (source dir, source basename) -> farm basename
# Must stay in sync with deadline/submitter.py and deadline/path_check.py
FARM_COPIES = {
    (_COMFYUI_PKG, "runner.py"): "comfyui_runner.py",
    (_COMFYUI_PKG, "utils.py"): "comfyui_utils.py",
    (_COMFYUI_PKG, "analytics.py"): "comfyui_analytics.py",
    (_COMFYUI_PKG, "node_configs.py"): "comfyui_node_configs.py",
    (_COMFYUI_PKG, "metadata.py"): "comfyui_metadata.py",
    (_COMFYUI_PKG, "path_check.py"): "comfyui_path_check.py",
    (_CORE_PKG, "metadata_file.py"): "comfyui_metadata_file.py",
}

# Package prefixes that do NOT exist on farm workers. The fixture must purge
# these from sys.modules AND keep their paths off sys.path, otherwise a
# workstation-only import (e.g. `from core.metadata_file import ...`) would
# silently succeed in the test and mask a real farm failure.
_WORKSTATION_ONLY_PACKAGES = ("comfyui", "core")


@pytest.fixture()
def farm_env(tmp_path):
    """Create an isolated directory mimicking the farm _job_data/ folder.

    Copies the farm scripts, puts *only* that directory on sys.path, and
    removes any path entries that would let ``import comfyui`` or
    ``import core`` succeed.
    """
    # Copy files
    for (src_dir, src_name), dst_name in FARM_COPIES.items():
        src = os.path.join(src_dir, src_name)
        dst = os.path.join(tmp_path, dst_name)
        shutil.copy2(src, dst)

    def _is_workstation_module(name):
        return any(name == pkg or name.startswith(pkg + ".") or name.startswith("comfyui_")
                   for pkg in _WORKSTATION_ONLY_PACKAGES)

    # Snapshot original state
    original_path = sys.path[:]
    original_modules = {k: v for k, v in sys.modules.items()
                        if _is_workstation_module(k)}

    # Purge workstation packages from sys.modules so re-imports hit our copies
    for key in list(sys.modules):
        if _is_workstation_module(key):
            del sys.modules[key]

    # Build a clean sys.path: only the temp dir + stdlib/site-packages
    # (no entry that contains a comfyui/ or core/ package directory)
    clean_path = [str(tmp_path)]
    for p in original_path:
        if any(os.path.isdir(os.path.join(p, pkg))
               for pkg in _WORKSTATION_ONLY_PACKAGES):
            continue  # skip — would let workstation packages import
        clean_path.append(p)
    sys.path[:] = clean_path

    yield tmp_path

    # Restore
    sys.path[:] = original_path
    # Remove modules we loaded from the temp dir
    for key in list(sys.modules):
        if _is_workstation_module(key):
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

    def test_metadata_imports(self, farm_env):
        """metadata.py provides add_per_file_metadata used by the runner."""
        mod = importlib.import_module("comfyui_metadata")
        assert hasattr(mod, "add_per_file_metadata")

    def test_metadata_file_imports(self, farm_env):
        """core/metadata_file.py is farm-copied as comfyui_metadata_file."""
        mod = importlib.import_module("comfyui_metadata_file")
        assert hasattr(mod, "get_metadata_file")


class TestFarmMetadataWorks:
    """The farm scripts must not just import — they must actually WORK.

    Regression test for the bug where comfyui/metadata.py imported
    core.metadata_file unguarded: the import error was swallowed and every
    farm job silently lost its per-file metadata (seeds, hashes, lineage).
    """

    def test_add_per_file_metadata_writes_in_farm_env(self, farm_env, tmp_path):
        mod = importlib.import_module("comfyui_metadata")
        output_dir = str(tmp_path / "outputs")
        os.makedirs(output_dir, exist_ok=True)

        result = mod.add_per_file_metadata(
            output_dir=output_dir,
            filename="test_output_00001.png",
            frame_index=1,
            actual_seed=12345,
            execution_time_ms=1000,
            content_hash="deadbeef",
        )
        assert result is True, "add_per_file_metadata must succeed on the farm"

        metadata_path = os.path.join(output_dir, mod.GALLERY_METADATA_FILE)
        assert os.path.isfile(metadata_path), "gallery metadata file must be written"
        with open(metadata_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        entry = data.get("_file_test_output_00001")
        assert entry is not None, "per-file entry must exist"
        assert entry["actual_seed"] == 12345
        assert entry["content_hash"] == "deadbeef"
        assert "_hash_deadbeef" in data, "hash index entry must exist"

    def test_lineage_works_in_farm_env(self, farm_env, tmp_path):
        mod = importlib.import_module("comfyui_metadata")
        output_dir = str(tmp_path / "outputs")
        os.makedirs(output_dir, exist_ok=True)

        assert mod.add_per_file_metadata(output_dir, "parent.png", file_id="p-1")
        assert mod.establish_lineage(output_dir, "child.png", "parent.png") is True
        child = mod.get_per_file_metadata(output_dir, "child.png")
        assert child is not None
        assert child["parent_id"] == "p-1"


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
        for src_dir, src_name in FARM_COPIES:
            src_path = os.path.join(src_dir, src_name)
            needed = self._collect_comfyui_fallback_imports(src_path)
            for mod in needed:
                if mod not in farm_modules:
                    missing.add((src_name, mod))

        assert not missing, (
            f"Farm scripts import modules that are NOT copied by submitter.py: "
            f"{missing}. Add them to FARM_COPIES in submitter.py."
        )


class TestFarmPathCheckWorks:
    """path_check.py is executed by Deadline's Python plugin on the worker.

    Importing is not enough: it reaches resolve_comfyui_paths through
    comfyui_utils, and that indirection is exactly what breaks in isolation.
    """

    def test_path_check_imports(self, farm_env):
        mod = importlib.import_module("comfyui_path_check")
        assert hasattr(mod, "run_checks")
        assert hasattr(mod, "main")

    def test_run_checks_works_in_farm_env(self, farm_env, tmp_path):
        mod = importlib.import_module("comfyui_path_check")

        result = mod.run_checks(str(tmp_path / "nope"), "embedded", "", str(tmp_path))

        assert result["ok"] is False
        assert any(c["id"] == "comfyui_dir" and not c["ok"] for c in result["checks"])
        # Proves resolve_comfyui_paths resolved via comfyui_utils, not the package
        assert any(c["id"] == "python_exe" for c in result["checks"])

    def test_runs_when_its_directory_is_not_on_sys_path(self, farm_env, tmp_path):
        """Regression: Deadline's Python plugin runs the script through a
        wrapper, so the script's directory is NOT on sys.path and the
        comfyui_utils copy beside it is invisible. That crashed the job with
        exit 1 and no result file, which the workstation could only report as
        a timeout. runpy.run_path reproduces the plugin's invocation.
        """
        script = os.path.join(str(farm_env), "comfyui_path_check.py")
        result_file = os.path.join(str(tmp_path), "out", "result.json")

        # Strip PYTHONPATH too - otherwise the subprocess could reach the real
        # comfyui package and the fallback import would mask the bug.
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)

        proc = subprocess.run(
            [sys.executable, "-c",
             "import runpy, sys; sys.argv = sys.argv[1:]; "
             "runpy.run_path(sys.argv[0], run_name='__main__')",
             script, "--comfyui-path", str(tmp_path), "--result-file", result_file],
            capture_output=True, text=True, cwd=str(tmp_path), env=env, timeout=120,
        )

        assert proc.returncode == 0, proc.stderr
        assert os.path.isfile(result_file), proc.stderr
