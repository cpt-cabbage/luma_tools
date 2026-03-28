"""
Option Button Manager for popup menu selection.

Provides a reusable abstraction for buttons that show a popup menu
with selectable options, replacing the repeated pattern across tabs.

Usage:
    # In initialize():
    self._source_manager = OptionButtonManager(
        button=self.ui.SourceButton,
        options=[("For Comp", "for_comp"), ("Raw", "raw"), ("Custom", "custom")],
        initial_value="for_comp",
        on_changed=self._on_source_changed,
        label_prefix="Source: "
    )

    # Access current value:
    current_source = self._source_manager.value

    # Set value programmatically:
    self._source_manager.set_value("raw")
"""

from typing import List, Tuple, Any, Callable, Optional, Union


class OptionButtonManager:
    """
    Manages a button with popup menu selection.

    Attributes:
        button: The QPushButton to manage
        options: List of (label, value) tuples
        value: Current selected value
        label_prefix: Optional prefix for button text
    """

    def __init__(
        self,
        button,
        options: List[Tuple[str, Any]],
        initial_value: Any,
        on_changed: Callable[[Any], None],
        label_prefix: str = "",
        parent_window=None,
        label_func: Optional[Callable[[Any], str]] = None
    ):
        """
        Initialize the option button manager.

        Args:
            button: QPushButton to manage
            options: List of (label, value) tuples for menu options
            initial_value: Initial selected value
            on_changed: Callback when selection changes (receives new value)
            label_prefix: Text to prepend to button label (e.g. "Source: ")
            parent_window: Parent window for popup menu positioning
            label_func: Optional function to get display label for a value.
                       If provided, overrides the label from options for button text.
        """
        self.button = button
        self.options = options
        self.value = initial_value
        self.on_changed = on_changed
        self.label_prefix = label_prefix
        self.parent_window = parent_window
        self.label_func = label_func

        # Connect button click
        button.clicked.connect(self._show_menu)

        # Set initial text
        self._update_text()

    def _get_label_for_value(self, value: Any) -> str:
        """Get the display label for a value."""
        if self.label_func:
            return self.label_func(value)
        return next((label for label, val in self.options if val == value), str(value))

    def _update_text(self):
        """Update button text to reflect current selection."""
        label = self._get_label_for_value(self.value)
        if self.label_prefix:
            self.button.setText(f"{self.label_prefix}{label}")
        else:
            self.button.setText(label)

    def _show_menu(self):
        """Show popup menu with options."""
        from small_widgets import show_popup_menu

        parent = self.parent_window or self.button.window()

        # Build display options (may use label_func for customization)
        display_options = []
        for label, value in self.options:
            if self.label_func:
                display_label = self.label_func(value)
            else:
                display_label = label
            display_options.append((display_label, value))

        result = show_popup_menu(
            parent,
            self.button,
            display_options,
            current=self.value
        )

        if result is not None:
            self.value = result
            self._update_text()
            self.on_changed(result)

    def set_value(self, value: Any, trigger_callback: bool = False):
        """
        Set the current value programmatically.

        Args:
            value: New value to set
            trigger_callback: If True, call on_changed callback
        """
        self.value = value
        self._update_text()
        if trigger_callback:
            self.on_changed(value)

    def update_options(self, options: List[Tuple[str, Any]]):
        """
        Update the available options.

        Args:
            options: New list of (label, value) tuples
        """
        self.options = options
        self._update_text()

    def refresh_text(self):
        """Refresh button text (useful when label_func results may have changed)."""
        self._update_text()


class IndexedOptionButtonManager:
    """
    Manages a button with index-based popup menu selection.

    Use this for options where the value is an index into a list,
    and you need separate display labels for menu vs button.

    Example options format:
        [(0, "High Quality (CRF 18)", "Quality: High"),
         (1, "Medium Quality (CRF 23)", "Quality: Medium")]
    """

    def __init__(
        self,
        button,
        options: List[Tuple[int, str, str]],
        initial_index: int,
        on_changed: Callable[[int], None],
        parent_window=None
    ):
        """
        Initialize the indexed option button manager.

        Args:
            button: QPushButton to manage
            options: List of (index, menu_label, button_label) tuples
            initial_index: Initial selected index
            on_changed: Callback when selection changes (receives new index)
            parent_window: Parent window for popup menu positioning
        """
        self.button = button
        self.options = options
        self.index = initial_index
        self.on_changed = on_changed
        self.parent_window = parent_window

        # Connect button click
        button.clicked.connect(self._show_menu)

        # Set initial text
        self._update_text()

    def _update_text(self):
        """Update button text to reflect current selection."""
        for idx, menu_label, button_label in self.options:
            if idx == self.index:
                self.button.setText(button_label)
                return

    def _show_menu(self):
        """Show popup menu with options."""
        from small_widgets import show_popup_menu

        parent = self.parent_window or self.button.window()

        # Convert to (label, value) format
        menu_options = [(menu_label, idx) for idx, menu_label, button_label in self.options]

        result = show_popup_menu(
            parent,
            self.button,
            menu_options,
            current=self.index
        )

        if result is not None:
            self.index = result
            self._update_text()
            self.on_changed(result)

    def set_index(self, index: int, trigger_callback: bool = False):
        """
        Set the current index programmatically.

        Args:
            index: New index to set
            trigger_callback: If True, call on_changed callback
        """
        self.index = index
        self._update_text()
        if trigger_callback:
            self.on_changed(index)

    @property
    def value(self) -> int:
        """Get current index (alias for index)."""
        return self.index
