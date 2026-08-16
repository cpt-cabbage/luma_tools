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
