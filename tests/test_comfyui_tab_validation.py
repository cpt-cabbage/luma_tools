"""Submit validation for cardinality-marked file slots.

_validate_dynamic_inputs runs on plain attributes of the container/widget
objects, so stubs stand in for Qt widgets — no QApplication needed.
"""


class _SelectorStub:
    def __init__(self, files):
        self.selected_files = files


class _ContainerStub:
    def __init__(self, node, files):
        self.editable_node = node
        self.input_widget = _SelectorStub(files)

    def isHidden(self):
        return False


class _WidgetManagerStub:
    def __init__(self, dynamic_widgets):
        self.dynamic_widgets = dynamic_widgets


class _AppStateStub:
    comfyui_workflow_path = None


def _make_tab(dynamic_widgets):
    from ui.tabs.comfyui.tab import ComfyUITab

    tab = object.__new__(ComfyUITab)
    tab.widget_manager = _WidgetManagerStub(dynamic_widgets)
    tab.app_state = _AppStateStub()
    tab.show_status = lambda *a, **k: None
    return tab


def _node(cardinality):
    from comfyui.editable import EditableNode

    return EditableNode(node_id="41", node_type="LoadImage",
                        title="Refs_editable", display_name="Refs",
                        widget_type="image", widget_name="image",
                        cardinality=cardinality)


class _TextWidgetStub:
    def __init__(self, text):
        self._text = text

    def toPlainText(self):
        return self._text


class _TextContainerStub:
    def __init__(self, node, text):
        self.editable_node = node
        self.input_widget = _TextWidgetStub(text)

    def isHidden(self):
        return False


def _text_node(node_id="9"):
    from comfyui.editable import EditableNode

    return EditableNode(node_id=node_id, node_type="MiniMaxH3Easy",
                        title="Prompt_editable", display_name="Prompt",
                        widget_type="text", widget_name="prompt",
                        current_value="workflow default")


class TestMissingNodeCheckIsCached:
    """_validate_dynamic_inputs runs on every generation-count slider tick —
    it must read the cached result, never re-read the workflow JSON from the
    network share."""

    def test_validation_does_not_load_workflow(self, monkeypatch, tmp_path):
        import comfyui.workflow as wf_mod

        reads = []
        monkeypatch.setattr(wf_mod, "load_workflow",
                            lambda path: reads.append(path) or {})
        tab = _make_tab({})
        tab.app_state.comfyui_workflow_path = str(tmp_path / "preset.json")
        tab._validate_dynamic_inputs()
        assert reads == []

    def test_cached_message_blocks(self):
        tab = _make_tab({})
        tab._missing_nodes_error = "Cannot submit — missing: MiniMaxH3Easy"
        assert tab._validate_dynamic_inputs() == (
            "Cannot submit — missing: MiniMaxH3Easy")

    def test_recheck_populates_cache(self, monkeypatch, tmp_path):
        import json
        import comfyui.node_info as ni

        preset = tmp_path / "preset.json"
        preset.write_text(json.dumps(
            {"1": {"class_type": "MiniMaxH3Easy", "inputs": {}}}))
        monkeypatch.setattr(ni, "get_known_class_types",
                            lambda: {"LoadImage"})
        tab = _make_tab({})
        tab.app_state.comfyui_workflow_path = str(preset)
        tab._recheck_missing_nodes()
        assert "MiniMaxH3Easy" in tab._missing_nodes_error

    def test_recheck_clears_stale_error(self, monkeypatch, tmp_path):
        import json
        import comfyui.node_info as ni

        preset = tmp_path / "preset.json"
        preset.write_text(json.dumps(
            {"1": {"class_type": "LoadImage", "inputs": {}}}))
        monkeypatch.setattr(ni, "get_known_class_types",
                            lambda: {"LoadImage"})
        tab = _make_tab({})
        tab.app_state.comfyui_workflow_path = str(preset)
        tab._missing_nodes_error = "Cannot submit — stale"
        tab._recheck_missing_nodes()
        assert tab._missing_nodes_error is None


class TestStaleTagWarningDedupe:
    """The status bar warning must fire when the stale tags change, not on
    every validation tick — validation runs per slider tick and would
    clobber the status bar."""

    def _tab_with_stale_tag(self):
        from comfyui.editable import CARDINALITY_MANY
        widgets = {
            ("41", "image"): _ContainerStub(_node(CARDINALITY_MANY),
                                            ["C:/r/one.png"]),
            ("9", "prompt"): _TextContainerStub(_text_node(),
                                                "use <Picture 2> here"),
        }
        tab = _make_tab(widgets)
        calls = []
        tab.show_status = lambda msg, level="info": calls.append(msg)
        return tab, calls

    def test_same_tags_warn_once(self):
        tab, calls = self._tab_with_stale_tag()
        tab._validate_dynamic_inputs()
        tab._validate_dynamic_inputs()
        assert len(calls) == 1
        assert "<Picture 2>" in calls[0]


class TestBrowseDirectoryMemory:
    """Each selector type saves under its own context key — audio and video
    selectors read comfyui_audio/comfyui_videos, so saving everything under
    comfyui_images left their browse memory permanently stale."""

    def test_context_key_is_saved(self, monkeypatch):
        import core.user_preferences as up

        saved = {}
        monkeypatch.setattr(up, "set_last_browse_directory",
                            lambda ctx, d: saved.update({ctx: d}))
        tab = _make_tab({})
        tab._on_images_changed(["C:/refs/voice.wav"], "comfyui_audio")
        assert saved == {"comfyui_audio": "C:/refs"}

    def test_context_covers_every_selector_type(self):
        from ui.tabs.comfyui.ui_manager import BROWSE_CONTEXTS
        assert BROWSE_CONTEXTS == {"image": "comfyui_images",
                                   "video": "comfyui_videos",
                                   "audio": "comfyui_audio"}


class TestValidateEmptyFileSlots:
    def test_single_slot_with_no_files_blocks(self):
        from comfyui.editable import CARDINALITY_SINGLE
        tab = _make_tab({("41", "image"):
                         _ContainerStub(_node(CARDINALITY_SINGLE), [])})
        error = tab._validate_dynamic_inputs()
        assert error is not None
        assert "no image selected" in error

    def test_optional_slot_with_no_files_is_allowed(self):
        """'Name_editable?' means the node is removed when empty — an empty
        selection is a valid choice, not a blocker."""
        from comfyui.editable import CARDINALITY_OPTIONAL
        tab = _make_tab({("41", "image"):
                         _ContainerStub(_node(CARDINALITY_OPTIONAL), [])})
        assert tab._validate_dynamic_inputs() is None

    def test_fanout_slot_with_no_files_is_allowed(self):
        """'Name_editable*' with zero references generates without them —
        the expansion removes the loader node."""
        from comfyui.editable import CARDINALITY_MANY
        tab = _make_tab({("41", "image"):
                         _ContainerStub(_node(CARDINALITY_MANY), [])})
        assert tab._validate_dynamic_inputs() is None
