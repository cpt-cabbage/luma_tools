"""Tests for ComfyUIWidgetManager value collection.

These run without a QApplication: collect_editable_values only touches plain
attributes on the container/widget objects, so simple stubs stand in for the
real Qt widgets.
"""

import json

import pytest


class _FileSelectorStub:
    """Stands in for BatchImageSelector: has selected_files and nothing else."""

    def __init__(self, files):
        self.selected_files = files


class _Container:
    def __init__(self, input_widget):
        self.input_widget = input_widget


class _AppStateStub:
    def __init__(self, workflow_path):
        self.comfyui_workflow_path = workflow_path


def _make_manager(workflow_path, dynamic_widgets):
    from ui.tabs.comfyui.ui_manager import ComfyUIWidgetManager

    mgr = object.__new__(ComfyUIWidgetManager)
    mgr.app_state = _AppStateStub(workflow_path)
    mgr.dynamic_widgets = dynamic_widgets
    mgr.collect_settings_values = lambda: {}
    return mgr


def _write_workflow(tmp_path, nodes):
    path = tmp_path / "workflow.json"
    path.write_text(json.dumps(nodes))
    return str(path)


class TestCollectEditableValues:
    def test_audio_selection_is_collected(self, tmp_path):
        """A LoadAudio_editable slot must submit the user's file, not the
        workflow's baked-in default."""
        workflow_path = _write_workflow(tmp_path, {
            "7": {"class_type": "LoadAudio",
                  "_meta": {"title": "Voice_editable"},
                  "inputs": {"audio": "default.wav"}},
        })
        selector = _FileSelectorStub(["C:/refs/voice.wav"])
        mgr = _make_manager(workflow_path, {("7", "audio"): _Container(selector)})

        values, _count = mgr.collect_editable_values()

        assert values["7"][0]["value"] == ["C:/refs/voice.wav"]

    def test_image_selection_is_collected(self, tmp_path):
        workflow_path = _write_workflow(tmp_path, {
            "3": {"class_type": "LoadImage",
                  "_meta": {"title": "Input_editable"},
                  "inputs": {"image": "default.png"}},
        })
        selector = _FileSelectorStub(["C:/refs/a.png", "C:/refs/b.png"])
        mgr = _make_manager(workflow_path, {("3", "image"): _Container(selector)})

        values, count = mgr.collect_editable_values()

        assert values["3"][0]["value"] == ["C:/refs/a.png", "C:/refs/b.png"]
        assert count == 2
