"""
Canvas tab module for Luma Tools.

Provides a collaborative infinite canvas workspace where generations live spatially,
synchronized across team members via the shared network drive.

Features:
- Infinite pan/zoom canvas with image nodes
- Bezier curve connections showing iteration lineage
- Sticky notes and group regions for organization
- Real-time collaboration via network file sync
- Minimap for navigation
- Collapsible toolbar
- Drawing tools with pen tablet support
- Grid and snapping
- Non-destructive image manipulation
- Undo/redo
- Export/import as .luma files
"""

import os
import logging
from pathlib import Path

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMenu

from .base_tab import BaseTab, TabConfig

logger = logging.getLogger(__name__)


class CanvasTab(BaseTab):
    """Tab for collaborative infinite canvas workspace."""

    TAB_CONFIG = TabConfig(ui_file="canvas.ui", tab_name="Canvas", tab_id="canvas")

    def connect_signals(self):
        """Connect canvas tab signals."""
        # Directory controls
        self.ui.CanvasOpenExplorer.clicked.connect(self._on_open_explorer)

        # Toolbar buttons - Basic tools
        self.ui.CanvasToolSelect.clicked.connect(lambda: self._set_tool("select"))
        # Pan button removed - use Space+drag instead (Photoshop-style)
        self.ui.CanvasToolPan.setVisible(False)
        self.ui.CanvasToolConnect.clicked.connect(lambda: self._set_tool("connect"))
        self.ui.CanvasToolAnnotate.clicked.connect(lambda: self._set_tool("annotate"))
        self.ui.CanvasToolGroup.clicked.connect(lambda: self._set_tool("group"))
        self.ui.CanvasToolCrop.clicked.connect(lambda: self._set_tool("crop"))

        # Drawing tools toggle (opens floating panel)
        self.ui.CanvasToolDraw.clicked.connect(self._on_draw_toggle)

        # Grid and snapping
        self.ui.CanvasToggleGrid.clicked.connect(self._on_toggle_grid)
        self.ui.CanvasToggleSnap.clicked.connect(self._on_toggle_snap)

        # Undo/Redo
        self.ui.CanvasUndo.clicked.connect(self._on_undo)
        self.ui.CanvasRedo.clicked.connect(self._on_redo)

        # View and File menus
        self.ui.CanvasViewMenu.clicked.connect(self._show_view_menu)
        self.ui.CanvasFileMenu.clicked.connect(self._show_file_menu)

        # View controls
        self.ui.CanvasFitAll.clicked.connect(self._on_fit_all)
        self.ui.CanvasFitSelection.clicked.connect(self._on_fit_selection)
        self.ui.CanvasZoomSlider.valueChanged.connect(self._on_zoom_changed)
        self.ui.CanvasResetZoom.clicked.connect(self._on_reset_zoom)
        self.ui.CanvasGoOrigin.clicked.connect(self._on_go_origin)

        # Color sampler
        self.ui.CanvasColorSampler.clicked.connect(self._on_color_sampler)

        # Toolbar collapse
        self.ui.CanvasToolbarToggle.clicked.connect(self._toggle_toolbar)

    def initialize(self):
        """Initialize the canvas tab."""
        from ui.canvas import (
            CollaborativeCanvas, CanvasSyncManager, CursorPresenceManager, UndoStack,
            CanvasMetadataManager, CanvasScope
        )

        # Path state
        self._current_path = ""

        # Multi-canvas state
        self._metadata_manager = None
        self._current_canvas_id = None
        self._current_canvas_name = None

        # Tool state
        self._current_tool = "select"
        self._toolbar_collapsed = False

        # Sync state
        self._sync_viewport = False  # Off by default - users keep their own view

        # Create the canvas widget
        self._canvas = CollaborativeCanvas()
        self._canvas.set_tab(self)  # Set tab reference for gallery integration

        # Setup undo stack
        self._undo_stack = UndoStack(self._canvas)
        self._canvas.set_undo_stack(self._undo_stack)
        self._undo_stack.can_undo_changed.connect(self._on_undo_state_changed)
        self._undo_stack.can_redo_changed.connect(self._on_redo_state_changed)

        # Insert canvas into the placeholder container
        canvas_layout = QtWidgets.QVBoxLayout(self.ui.CanvasContainer)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.addWidget(self._canvas)

        # Connect canvas signals
        self._canvas.canvas_modified.connect(self._on_canvas_modified)
        self._canvas.selection_changed.connect(self._on_selection_changed)
        self._canvas.item_added.connect(self._on_item_added)
        self._canvas.cursor_moved.connect(self._on_cursor_moved)
        self._canvas.cursor_moved.connect(self._update_coordinates)
        self._canvas.zoom_changed.connect(self._on_zoom_from_canvas)
        self._canvas.files_dropped_on_canvas.connect(self._on_files_dropped_to_canvas)
        self._canvas.tool_changed.connect(self._on_canvas_tool_changed)

        # Setup sync manager for collaboration (use canvas as parent since it's a QObject)
        self._sync_manager = CanvasSyncManager(self._canvas)
        self._sync_manager.state_changed.connect(self._on_remote_state_changed)
        self._sync_manager.sync_error.connect(self._on_sync_error)

        # Setup cursor presence manager
        self._presence_manager = CursorPresenceManager(self._canvas)
        self._presence_manager.cursors_updated.connect(self._on_cursors_updated)
        self._presence_manager.user_joined.connect(self._on_user_joined)
        self._presence_manager.user_left.connect(self._on_user_left)

        # Setup minimap
        self._setup_minimap()

        # Setup floating drawing tools panel
        self._setup_drawing_panel()

        # Setup canvas dropdown menu
        self._setup_canvas_dropdown()

        # Setup viewport sync toggle button
        self._setup_viewport_sync_toggle()

        # Load initial directory
        self._update_canvas_path()

        # Update toolbar button states
        self._update_tool_buttons()

        # Setup event bus subscriptions for cross-tab communication
        self._setup_event_bus_subscriptions()

        logger.info("Canvas tab initialized")

    def _setup_event_bus_subscriptions(self):
        """Subscribe to event bus signals for cross-tab awareness."""
        try:
            from core.event_bus import pipeline_events
            pipeline_events.add_to_canvas.connect(self._on_add_to_canvas_requested)
            logger.debug("Canvas tab subscribed to event bus")
        except ImportError:
            logger.debug("Event bus not available for canvas tab")

    def _on_add_to_canvas_requested(self, image_path: str):
        """Handle request to add an image to the canvas.

        Called when ComfyUI or Gallery wants to add an image to the canvas.

        Args:
            image_path: Path to the image to add
        """
        if hasattr(self, 'add_image_to_canvas'):
            self.add_image_to_canvas(image_path)

    def _setup_minimap(self):
        """Setup the floating canvas minimap widget."""
        from ui.canvas import CanvasMinimap

        # Create floating minimap widget (no parent for floating window)
        self._minimap = CanvasMinimap()
        self._minimap.set_canvas(self._canvas)

        # Connect minimap_trigger signal to show minimap on pan/zoom
        self._canvas.minimap_trigger.connect(self._on_minimap_trigger)

        # Hide CanvasMinimapContainer if it exists (no longer used)
        if hasattr(self.ui, 'CanvasMinimapContainer'):
            self.ui.CanvasMinimapContainer.setVisible(False)

    def _on_minimap_trigger(self):
        """Show the minimap when user pans or zooms."""
        if not hasattr(self, '_minimap') or not self._minimap:
            return
        # Position minimap in bottom-right corner of canvas
        self._position_minimap()
        self._minimap.show_temporarily()

    def _position_minimap(self):
        """Position the minimap in the bottom-right corner of the canvas."""
        if not hasattr(self, '_minimap') or not self._minimap:
            return

        # Get canvas global position and size
        canvas_rect = self._canvas.rect()
        canvas_global = self._canvas.mapToGlobal(canvas_rect.bottomRight())

        # Position minimap with margin from bottom-right corner
        margin = 15
        x = canvas_global.x() - self._minimap.width() - margin
        y = canvas_global.y() - self._minimap.height() - margin
        self._minimap.move(x, y)

    def _setup_drawing_panel(self):
        """Setup the floating drawing tools panel."""
        from ui.panels import DrawingToolsPanel

        # Create floating panel as child of the canvas container
        self._drawing_panel = DrawingToolsPanel(self.ui.CanvasContainer)

        # Connect panel signals
        self._drawing_panel.tool_changed.connect(self._on_drawing_tool_changed)
        self._drawing_panel.brush_size_changed.connect(self._on_brush_size_changed)
        self._drawing_panel.color_changed.connect(self._on_drawing_color_changed)
        self._drawing_panel.panel_closed.connect(self._on_drawing_panel_closed)

        # Initially hidden
        self._drawing_panel.hide()

    def _on_draw_toggle(self):
        """Handle Draw toggle button click."""
        is_checked = self.ui.CanvasToolDraw.isChecked()

        if is_checked:
            # Show the floating drawing tools panel
            self._show_drawing_panel()
            # Set to pen tool by default when entering drawing mode
            current_tool = self._drawing_panel.get_tool()
            self._set_tool(current_tool)
        else:
            # Hide the panel and switch back to select tool
            self._drawing_panel.hide()
            self._set_tool("select")

    def _show_drawing_panel(self):
        """Show the drawing tools panel at a good position."""
        if not hasattr(self, '_drawing_panel'):
            return

        # Sync panel state from canvas (in case color/size was changed elsewhere)
        canvas_color = self._canvas.get_drawing_color()
        canvas_width = self._canvas.get_drawing_width()
        self._drawing_panel.set_color(canvas_color)
        self._drawing_panel.set_brush_size(canvas_width)

        # Position panel in top-left of canvas area with some padding
        # Convert local coordinates to global since panel is a tool window
        from PySide6.QtCore import QPoint
        canvas_global_pos = self._canvas.mapToGlobal(QPoint(0, 0))
        panel_x = canvas_global_pos.x() + 10
        panel_y = canvas_global_pos.y() + 10
        self._drawing_panel.show_at(panel_x, panel_y)

    def _on_drawing_tool_changed(self, tool: str):
        """Handle tool change from drawing panel."""
        self._set_tool(tool)

    def _on_brush_size_changed(self, size: int):
        """Handle brush size change from drawing panel."""
        self._canvas.set_brush_size(size)
        logger.debug(f"Brush size set to: {size}")

    def _on_drawing_color_changed(self, color):
        """Handle drawing color change from drawing panel."""
        self._canvas.set_drawing_color(color)
        logger.debug(f"Drawing color set to: {color.name()}")

    def _on_drawing_panel_closed(self):
        """Handle drawing panel being closed."""
        # Uncheck the Draw button and switch to select tool
        self.ui.CanvasToolDraw.setChecked(False)
        self._set_tool("select")

    def _on_canvas_tool_changed(self, tool: str):
        """Handle tool change from canvas (e.g., keyboard shortcut).

        Shows/hides the drawing panel and updates the Draw button state.
        """
        # Drawing-related tools that should show the drawing panel
        is_drawing_tool = tool in ('pen', 'rect', 'ellipse', 'line', 'eraser', 'select_drawings')

        # Update Draw button state
        self.ui.CanvasToolDraw.setChecked(is_drawing_tool)

        # Show/hide drawing panel
        if is_drawing_tool:
            if not self._drawing_panel.isVisible():
                self._show_drawing_panel()
            # Sync the panel's tool selection (for actual drawing tools)
            if tool in ('pen', 'rect', 'ellipse', 'line', 'eraser', 'select_drawings'):
                self._drawing_panel.set_tool(tool)
        else:
            if self._drawing_panel.isVisible():
                self._drawing_panel.hide()

    def _configure_sync_managers(self):
        """Configure sync managers for the current canvas."""
        if not self._metadata_manager or not self._current_canvas_id:
            return

        username = self.app_state.user or "unknown"

        # Get paths from metadata manager
        canvas_file_path = self._metadata_manager.get_canvas_path(self._current_canvas_id)
        presence_dir = self._metadata_manager.get_presence_dir(self._current_canvas_id)

        if not canvas_file_path:
            logger.warning("No canvas file path for sync configuration")
            return

        # Configure both managers with direct paths
        self._sync_manager.configure(canvas_file_path, username)
        self._presence_manager.configure(presence_dir, username)

    def _start_sync(self):
        """Start synchronization polling."""
        if not self._current_canvas_id:
            return

        self._sync_manager.start()
        self._presence_manager.start()
        logger.info("Canvas sync started")

    def _stop_sync(self):
        """Stop synchronization polling."""
        self._sync_manager.stop()
        self._presence_manager.stop()
        logger.info("Canvas sync stopped")

    def _update_canvas_path(self):
        """Update the canvas to the current directory and handle canvas selection."""
        from core.settings_manager import safe_get_setting
        from ui.canvas import CanvasMetadataManager

        # Get network path (shared location, not per-user)
        network_path = safe_get_setting("network_output_path", "")
        if not network_path:
            logger.warning("No network output path configured for canvas")
            self._current_path = ""
            return

        self._current_path = network_path

        # Stop existing sync before path change
        if hasattr(self, '_sync_manager'):
            self._stop_sync()

        # Create metadata manager for current project/shot
        jobname = self.app_state.jobname or "default"
        shot = self.app_state.shot or ""
        username = self.app_state.user or "unknown"

        self._metadata_manager = CanvasMetadataManager(
            base_dir=network_path,
            jobname=jobname,
            shot=shot,
            username=username
        )

        # Open last canvas or show selector
        self._open_canvas_or_prompt_name()

    def _get_last_opened_key(self) -> str:
        """Get the key for last opened canvas in user settings."""
        jobname = self.app_state.jobname or "default"
        shot = self.app_state.shot or ""
        if shot:
            return f"{jobname}_{shot}"
        return jobname

    def _get_last_opened_canvas_id(self) -> str:
        """Get the last opened canvas ID for current project/shot."""
        from core.settings_manager import safe_get_setting
        last_opened_dict = safe_get_setting("canvas_last_opened", {})
        key = self._get_last_opened_key()
        return last_opened_dict.get(key, "")

    def _set_last_opened_canvas_id(self, canvas_id: str):
        """Set the last opened canvas ID for current project/shot."""
        from core.settings_manager import safe_get_setting, safe_set_setting
        last_opened_dict = safe_get_setting("canvas_last_opened", {})
        key = self._get_last_opened_key()
        last_opened_dict[key] = canvas_id
        safe_set_setting("canvas_last_opened", last_opened_dict)

    def _open_canvas_or_prompt_name(self):
        """Open last canvas or prompt user for new canvas name."""
        if not self._metadata_manager:
            return

        # Try to open last opened canvas
        last_id = self._get_last_opened_canvas_id()
        if last_id and self._metadata_manager.get_canvas(last_id):
            self._open_canvas(last_id)
            return

        # Check for existing canvases
        canvases = self._metadata_manager.list_canvases()
        if canvases:
            # Open the first/most recent canvas
            self._open_canvas(canvases[0].id)
        else:
            # No canvases yet - show empty canvas, user can create via menu
            logger.info("No canvases found - showing empty canvas")
            self._canvas.clear()
            self._on_canvas_loaded()

    def _prompt_new_canvas_name(self):
        """Prompt user to create a new canvas."""
        from ui.canvas import NewCanvasDialog, CanvasScope

        has_shot = bool(self.app_state.shot)
        dialog = NewCanvasDialog(
            has_shot_context=has_shot,
            default_name="Main",
            parent=self.main_window
        )

        if dialog.exec():
            name = dialog.canvas_name
            scope = dialog.canvas_scope

            canvas = self._metadata_manager.create_canvas(name, scope)
            if canvas:
                self._open_canvas(canvas.id)
            else:
                logger.error("Failed to create canvas")
                # Show empty canvas
                self._canvas.clear()
                self._on_canvas_loaded()
        else:
            # User cancelled - show empty canvas
            self._canvas.clear()
            self._on_canvas_loaded()

    def _open_canvas(self, canvas_id: str):
        """Open a specific canvas by ID."""
        if not self._metadata_manager:
            return

        canvas_def = self._metadata_manager.get_canvas(canvas_id)
        if not canvas_def:
            logger.error(f"Canvas not found: {canvas_id}")
            self._canvas.clear()
            self._on_canvas_loaded()
            return

        self._current_canvas_id = canvas_id
        self._current_canvas_name = canvas_def.name

        # Update dropdown text
        self._update_canvas_dropdown_text()

        # Get canvas file path
        canvas_file = self._metadata_manager.get_canvas_path(canvas_id)

        # Save as last opened
        self._set_last_opened_canvas_id(canvas_id)

        # Load the canvas
        self._load_canvas_state_async(canvas_file)

        logger.info(f"Opening canvas: {canvas_def.name} ({canvas_id})")

    def _setup_canvas_dropdown(self):
        """Setup the canvas dropdown menu."""
        if not hasattr(self.ui, 'CanvasDropdown'):
            return

        # Create menu for dropdown
        self._canvas_menu = QMenu(self.main_window)
        self._canvas_menu.setStyleSheet("""
            QMenu {
                background-color: #2c313a;
                color: #e0e0e0;
                border: 1px solid #3c414b;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
            }
            QMenu::item:selected {
                background-color: #4a9eff;
            }
            QMenu::item:disabled {
                color: #888;
                background-color: transparent;
            }
            QMenu::separator {
                height: 1px;
                background: #3c414b;
                margin: 4px 8px;
            }
        """)

        self.ui.CanvasDropdown.setMenu(self._canvas_menu)
        self._canvas_menu.aboutToShow.connect(self._populate_canvas_menu)

    def _setup_viewport_sync_toggle(self):
        """Setup the viewport sync toggle button in the toolbar."""
        # Create the toggle button
        self._viewport_sync_btn = QtWidgets.QPushButton("View Sync")
        self._viewport_sync_btn.setToolTip(
            "Sync viewport (pan/zoom) with other users.\n"
            "When ON, your view follows others' changes.\n"
            "When OFF, you control your own view."
        )
        self._viewport_sync_btn.setCheckable(True)
        self._viewport_sync_btn.setChecked(self._sync_viewport)
        self._viewport_sync_btn.setMinimumSize(70, 24)
        self._viewport_sync_btn.clicked.connect(self._on_toggle_viewport_sync)

        # Insert after the Snap button in the secondary toolbar
        layout = self.ui.CanvasToolbarContent.layout()
        if layout:
            # Find index of CanvasToggleSnap
            snap_index = -1
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item and item.widget() == self.ui.CanvasToggleSnap:
                    snap_index = i
                    break

            if snap_index >= 0:
                layout.insertWidget(snap_index + 1, self._viewport_sync_btn)
            else:
                # Fallback: add to end before stretch
                layout.addWidget(self._viewport_sync_btn)

    def _on_toggle_viewport_sync(self):
        """Toggle viewport sync on/off."""
        self._sync_viewport = self._viewport_sync_btn.isChecked()
        state = "ON" if self._sync_viewport else "OFF"
        logger.debug(f"Viewport sync toggled: {state}")
        self.show_status(f"View sync: {state}", "info")

    def _populate_canvas_menu(self):
        """Populate the canvas dropdown menu with available canvases."""
        from ui.canvas import CanvasScope

        self._canvas_menu.clear()

        if not self._metadata_manager:
            self._canvas_menu.addAction("No canvases available").setEnabled(False)
            return

        # Get canvases
        job_canvases = self._metadata_manager.list_canvases(CanvasScope.JOB)
        has_shot = bool(self.app_state.shot)
        shot_canvases = self._metadata_manager.list_canvases(CanvasScope.SHOT) if has_shot else []

        # Job canvases section
        if job_canvases:
            header = self._canvas_menu.addAction("── Job Canvases ──")
            header.setEnabled(False)

            for canvas in job_canvases:
                action = self._canvas_menu.addAction(f"  {canvas.name}")
                action.setData(canvas.id)
                action.setCheckable(True)
                action.setChecked(canvas.id == self._current_canvas_id)
                action.triggered.connect(lambda checked, cid=canvas.id: self._on_canvas_menu_item_clicked(cid))

        # Shot canvases section
        if shot_canvases:
            header = self._canvas_menu.addAction("── Shot Canvases ──")
            header.setEnabled(False)

            for canvas in shot_canvases:
                action = self._canvas_menu.addAction(f"  {canvas.name}")
                action.setData(canvas.id)
                action.setCheckable(True)
                action.setChecked(canvas.id == self._current_canvas_id)
                action.triggered.connect(lambda checked, cid=canvas.id: self._on_canvas_menu_item_clicked(cid))

        self._canvas_menu.addSeparator()

        # Management actions
        new_action = self._canvas_menu.addAction("New Canvas...")
        new_action.triggered.connect(self._on_new_canvas_action)

        manage_action = self._canvas_menu.addAction("Manage Canvases...")
        manage_action.triggered.connect(self._on_manage_canvases_action)

    def _on_canvas_menu_item_clicked(self, canvas_id: str):
        """Handle click on canvas menu item."""
        if canvas_id != self._current_canvas_id:
            self._open_canvas(canvas_id)

    def _on_new_canvas_action(self):
        """Handle New Canvas action from menu."""
        from ui.canvas import NewCanvasDialog, CanvasScope

        has_shot = bool(self.app_state.shot)
        dialog = NewCanvasDialog(
            has_shot_context=has_shot,
            parent=self.main_window
        )

        if dialog.exec():
            name = dialog.canvas_name
            scope = dialog.canvas_scope

            canvas = self._metadata_manager.create_canvas(name, scope)
            if canvas:
                self._open_canvas(canvas.id)

    def _on_manage_canvases_action(self):
        """Handle Manage Canvases action from menu."""
        from ui.canvas import CanvasSelectorDialog

        has_shot = bool(self.app_state.shot)
        dialog = CanvasSelectorDialog(
            metadata_manager=self._metadata_manager,
            has_shot_context=has_shot,
            parent=self.main_window
        )

        dialog.canvas_selected.connect(self._open_canvas)
        dialog.canvas_created.connect(self._open_canvas)
        dialog.exec()

    def _update_canvas_dropdown_text(self):
        """Update the dropdown button text with current canvas name."""
        if hasattr(self.ui, 'CanvasDropdown'):
            name = self._current_canvas_name or "(none)"
            self.ui.CanvasDropdown.setText(f"Canvas: {name}")

    def _load_canvas_state_async(self, canvas_file: str = None):
        """Load canvas state asynchronously to avoid blocking UI.

        Args:
            canvas_file: Full path to the canvas JSON file. If None, uses current canvas.
        """
        from ui_components import StatusColors

        # Use provided path or get from current canvas
        if not canvas_file and self._current_canvas_id and self._metadata_manager:
            canvas_file = self._metadata_manager.get_canvas_path(self._current_canvas_id)

        if not canvas_file:
            logger.warning("No canvas file specified for loading")
            self._canvas.clear()
            self._on_canvas_loaded()
            return

        if not os.path.exists(canvas_file):
            # No existing state - clear and proceed
            self._canvas.clear()
            self._on_canvas_loaded()
            logger.info("No existing canvas state, starting fresh")
            return

        # Show spinner in status bar
        self.update_status_with_spinner("Loading canvas...", StatusColors.INFO)

        # Start worker to load JSON and pre-load images
        self.start_worker(
            self._load_canvas_data_worker,
            canvas_file,
            on_result=self._on_canvas_data_loaded,
            on_error=self._on_canvas_load_error
        )

    @staticmethod
    def _load_canvas_data_worker(canvas_file: str) -> dict:
        """Worker thread: Load JSON and pre-load images as QImage.

        QImage is thread-safe, unlike QPixmap which must be created on main thread.

        Args:
            canvas_file: Path to the canvas state JSON file

        Returns:
            Dict with 'state' (canvas state) and 'preloaded_images' (node_id -> QImage)
        """
        from core.utils import load_json
        from PySide6.QtGui import QImage

        state = load_json(canvas_file, {})
        preloaded_images = {}

        # Pre-load images as QImage (thread-safe)
        for node_id, node_data in state.get('nodes', {}).items():
            image_path = node_data.get('path', '')
            if image_path and os.path.exists(image_path):
                qimage = QImage(image_path)
                if not qimage.isNull():
                    preloaded_images[node_id] = qimage

        return {'state': state, 'preloaded_images': preloaded_images}

    def _on_canvas_data_loaded(self, result: dict):
        """Main thread callback: Create QPixmaps and nodes."""
        from ui_components import StatusColors

        state = result.get('state', {})
        preloaded_images = result.get('preloaded_images', {})

        # Load state with pre-loaded images (creates QPixmaps on main thread)
        self._canvas.load_state_with_preloaded_images(state, preloaded_images)

        # Sync all nodes with gallery data (likes, groups, colors)
        self._canvas.sync_all_from_gallery()

        # Finalize loading
        self._on_canvas_loaded()

        # Update status bar
        count = len(state.get('nodes', {}))
        self.update_status_with_spinner(
            f"Canvas loaded ({count} images)",
            StatusColors.SUCCESS,
            start=False
        )
        logger.info(f"Loaded canvas state with {count} images")

    def _on_canvas_load_error(self, error_msg: str, traceback_str: str):
        """Handle canvas load error. Signature matches Signal(str, str)."""
        from ui_components import StatusColors

        logger.error(f"Failed to load canvas: {error_msg}")
        if traceback_str:
            logger.error(traceback_str)

        # Clear canvas and proceed
        self._canvas.clear()
        self._on_canvas_loaded()

        # Update status bar
        self.update_status_with_spinner(
            "Canvas load failed",
            StatusColors.ERROR,
            start=False
        )

    def _on_canvas_loaded(self):
        """Finalize after canvas loading completes (success or failure)."""
        # Configure and start sync for current canvas
        if hasattr(self, '_sync_manager') and self._current_canvas_id:
            self._configure_sync_managers()
            self._start_sync()

        canvas_name = self._current_canvas_name or "(none)"
        logger.info(f"Canvas loaded: {canvas_name}")

    def _save_canvas_state(self):
        """Save canvas state to the current canvas file."""
        if not self._current_canvas_id or not self._metadata_manager:
            return

        username = self.app_state.user or "unknown"
        state = self._canvas.get_state()
        state["modified_by"] = username

        # Count items for metadata
        item_count = len(state.get('nodes', {})) + len(state.get('annotations', []))

        # Use sync manager if available (updates its timestamp to prevent self-reload)
        if hasattr(self, '_sync_manager') and self._sync_manager:
            if self._sync_manager.save_state(state):
                logger.debug("Saved canvas state via sync manager")
                # Update metadata
                self._metadata_manager.update_canvas_metadata(
                    self._current_canvas_id,
                    modified=state.get("last_modified", ""),
                    modified_by=username,
                    item_count=item_count
                )
            return

        # Fallback: direct file save
        from core.utils import ensure_directory, save_json
        from datetime import datetime

        canvas_file = self._metadata_manager.get_canvas_path(self._current_canvas_id)
        if not canvas_file:
            logger.error("No canvas file path for save")
            return

        ensure_directory(os.path.dirname(canvas_file))

        try:
            now = datetime.now().isoformat()
            state["last_modified"] = now
            save_json(canvas_file, state)
            logger.info(f"Saved canvas state to {canvas_file}")

            # Update metadata
            self._metadata_manager.update_canvas_metadata(
                self._current_canvas_id,
                modified=now,
                modified_by=username,
                item_count=item_count
            )
        except Exception as e:
            logger.error(f"Failed to save canvas state: {e}")

    def _on_open_explorer(self):
        """Open current directory in file explorer."""
        if self._current_path and os.path.exists(self._current_path):
            import subprocess
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            subprocess.Popen(f'explorer "{self._current_path}"', creationflags=creationflags)

    def _set_tool(self, tool: str):
        """Set the current canvas tool."""
        self._current_tool = tool
        self._canvas.set_tool(tool)
        self._update_tool_buttons()
        self._update_tool_hint()
        logger.debug(f"Canvas tool set to: {tool}")

    def _update_tool_buttons(self):
        """Update toolbar button checked states."""
        # Main toolbar tools (pan removed - use Space+drag instead)
        tools = {
            "select": self.ui.CanvasToolSelect,
            "connect": self.ui.CanvasToolConnect,
            "annotate": self.ui.CanvasToolAnnotate,
            "group": self.ui.CanvasToolGroup,
            "crop": self.ui.CanvasToolCrop,
        }
        # Drawing tools are in the floating panel (includes eraser and select_drawings)
        drawing_tools = {"pen", "rect", "ellipse", "line", "eraser", "select_drawings"}
        is_drawing_tool = self._current_tool in drawing_tools

        for tool_name, button in tools.items():
            button.setChecked(tool_name == self._current_tool)

        # Update Draw toggle button state
        self.ui.CanvasToolDraw.setChecked(is_drawing_tool)

        # Update drawing panel tool if visible
        if hasattr(self, '_drawing_panel') and self._drawing_panel.isVisible():
            self._drawing_panel.set_tool(self._current_tool)

    # =========================================================================
    # Grid and Snapping
    # =========================================================================

    def _on_toggle_grid(self):
        """Toggle grid visibility."""
        is_checked = self.ui.CanvasToggleGrid.isChecked()
        self._canvas.toggle_grid(is_checked)
        logger.debug(f"Grid toggled: {is_checked}")

    def _on_toggle_snap(self):
        """Toggle snapping (both grid and neighbor)."""
        is_checked = self.ui.CanvasToggleSnap.isChecked()
        self._canvas.toggle_snap_to_grid(is_checked)
        self._canvas.toggle_snap_to_neighbors(is_checked)
        logger.debug(f"Snapping toggled: {is_checked}")

    # =========================================================================
    # Undo/Redo
    # =========================================================================

    def _on_undo(self):
        """Perform undo."""
        if hasattr(self, '_undo_stack'):
            self._undo_stack.undo()

    def _on_redo(self):
        """Perform redo."""
        if hasattr(self, '_undo_stack'):
            self._undo_stack.redo()

    def _on_undo_state_changed(self, can_undo: bool):
        """Update undo button state."""
        self.ui.CanvasUndo.setEnabled(can_undo)
        if can_undo and hasattr(self, '_undo_stack'):
            self.ui.CanvasUndo.setToolTip(self._undo_stack.get_undo_text())
        else:
            self.ui.CanvasUndo.setToolTip("Undo (Ctrl+Z)")

    def _on_redo_state_changed(self, can_redo: bool):
        """Update redo button state."""
        self.ui.CanvasRedo.setEnabled(can_redo)
        if can_redo and hasattr(self, '_undo_stack'):
            self.ui.CanvasRedo.setToolTip(self._undo_stack.get_redo_text())
        else:
            self.ui.CanvasRedo.setToolTip("Redo (Ctrl+Y)")

    # =========================================================================
    # View Menu (Alignment, Arrange, Z-Order)
    # =========================================================================

    def _show_view_menu(self):
        """Show the View dropdown menu."""
        menu = QMenu(self.main_window)

        # Alignment submenu
        align_menu = menu.addMenu("Align Selection")
        align_menu.addAction("Align Left", lambda: self._canvas.align_selection("left"))
        align_menu.addAction("Align Right", lambda: self._canvas.align_selection("right"))
        align_menu.addAction("Align Top", lambda: self._canvas.align_selection("top"))
        align_menu.addAction("Align Bottom", lambda: self._canvas.align_selection("bottom"))
        align_menu.addSeparator()
        align_menu.addAction("Center Horizontally", lambda: self._canvas.align_selection("center_h"))
        align_menu.addAction("Center Vertically", lambda: self._canvas.align_selection("center_v"))

        # Distribute submenu (requires 3+ items)
        selected_count = len(self._canvas._scene.selectedItems())
        dist_menu = menu.addMenu("Distribute Selection")
        dist_h = dist_menu.addAction("Distribute Horizontally", lambda: self._canvas.distribute_selection("horizontal"))
        dist_v = dist_menu.addAction("Distribute Vertically", lambda: self._canvas.distribute_selection("vertical"))
        # Disable if fewer than 3 items selected
        if selected_count < 3:
            dist_h.setEnabled(False)
            dist_v.setEnabled(False)
            dist_menu.setToolTip("Select at least 3 items to distribute")

        # Arrange submenu
        arrange_menu = menu.addMenu("Arrange Selection")
        arrange_menu.addAction("Grid", lambda: self._canvas.arrange_selection("grid"))
        arrange_menu.addAction("Horizontal Row", lambda: self._canvas.arrange_selection("horizontal"))
        arrange_menu.addAction("Vertical Column", lambda: self._canvas.arrange_selection("vertical"))
        arrange_menu.addAction("Bin Pack", lambda: self._canvas.arrange_selection("pack"))

        # Scale submenu
        scale_menu = menu.addMenu("Scale Selection")
        scale_menu.addAction("Match Width", lambda: self._show_scale_dialog("width"))
        scale_menu.addAction("Match Height", lambda: self._show_scale_dialog("height"))
        scale_menu.addAction("Match Area", lambda: self._show_scale_dialog("area"))

        menu.addSeparator()

        # Z-Order submenu
        zorder_menu = menu.addMenu("Z-Order")
        zorder_menu.addAction("Bring to Front (Ctrl+Shift+])", self._canvas.bring_to_front)
        zorder_menu.addAction("Bring Forward (Ctrl+])", self._canvas.bring_forward)
        zorder_menu.addAction("Send Backward (Ctrl+[)", self._canvas.send_backward)
        zorder_menu.addAction("Send to Back (Ctrl+Shift+[)", self._canvas.send_to_back)

        menu.addSeparator()

        # View options
        menu.addAction("Fit All (Ctrl+Space)", self._on_fit_all)
        menu.addAction("Fit Selection", self._on_fit_selection)
        menu.addAction("Reset Zoom (Ctrl+0)", lambda: self._canvas.set_zoom(1.0))
        menu.addAction("Go to Origin (Home)", self._canvas.center_on_origin)

        menu.addSeparator()

        # Color sampler
        menu.addAction("Show Color History", self._canvas.show_color_history_panel)

        # Show menu below the button
        button_pos = self.ui.CanvasViewMenu.mapToGlobal(
            self.ui.CanvasViewMenu.rect().bottomLeft()
        )
        menu.exec_(button_pos)

    def _show_scale_dialog(self, mode: str):
        """Show dialog for uniform scaling."""
        from PySide6.QtWidgets import QInputDialog

        label = {"width": "Target Width:", "height": "Target Height:", "area": "Target Area:"}[mode]
        default = {"width": 256, "height": 256, "area": 65536}[mode]

        value, ok = QInputDialog.getInt(
            self, f"Scale to {mode.title()}", label, default, 1, 10000
        )
        if ok:
            self._canvas.scale_selection_uniform(mode, value)

    # =========================================================================
    # File Menu (Export/Import)
    # =========================================================================

    def _show_file_menu(self):
        """Show the File dropdown menu."""
        menu = QMenu(self.main_window)

        menu.addAction("Export Canvas as .luma...", self._export_canvas)
        menu.addAction("Export Canvas (link images)...", lambda: self._export_canvas(embed=False))
        menu.addSeparator()
        menu.addAction("Import .luma File...", self._import_canvas)
        menu.addSeparator()
        menu.addAction("Clear Canvas", self._clear_canvas)

        # Show menu below the button
        button_pos = self.ui.CanvasFileMenu.mapToGlobal(
            self.ui.CanvasFileMenu.rect().bottomLeft()
        )
        menu.exec_(button_pos)

    def _export_canvas(self, embed: bool = True):
        """Export canvas to .luma file."""
        from file_dialogs import save_file_with_memory
        from ui.canvas import export_to_luma

        output_path = save_file_with_memory(
            parent=self.main_window,
            title="Export Canvas",
            filter="Luma Canvas Files (*.luma)",
            context="canvas_export"
        )

        if not output_path:
            return

        state = self._canvas.get_state()
        success = export_to_luma(state, output_path, embed_images=embed, base_path=self._current_path)

        if success:
            self.show_status(f"Exported canvas to {os.path.basename(output_path)}", "success")
        else:
            self.show_status("Failed to export canvas", "error")

    def _import_canvas(self):
        """Import canvas from .luma file."""
        from file_dialogs import browse_file_with_memory
        from ui.canvas import import_from_luma

        input_path = browse_file_with_memory(
            parent=self.main_window,
            title="Import Canvas",
            filter="Luma Canvas Files (*.luma);;All Files (*.*)",
            context="canvas_import"
        )

        if not input_path:
            return

        # Ask where to extract embedded images
        extract_path = self._current_path or os.path.dirname(input_path)

        state = import_from_luma(input_path, extract_path)
        if state:
            self._canvas.load_state(state)
            self.show_status(f"Imported canvas from {os.path.basename(input_path)}", "success")
        else:
            self.show_status("Failed to import canvas", "error")

    def _clear_canvas(self):
        """Clear the canvas after confirmation."""
        from dialog_helpers import confirm_action

        if confirm_action(
            "Clear Canvas",
            "Are you sure you want to clear all items from the canvas?",
            parent=self.main_window
        ):
            self._canvas.clear()
            if hasattr(self, '_undo_stack'):
                self._undo_stack.clear()
            self.show_status("Canvas cleared", "info")

    def _on_fit_all(self):
        """Fit all items in view."""
        self._canvas.fit_all()

    def _on_fit_selection(self):
        """Fit selected items in view."""
        self._canvas.fit_selection()

    def _on_zoom_changed(self, value: int):
        """Handle zoom slider change."""
        # Slider is 5-320, representing 5%-320% zoom
        zoom = value / 100.0
        # Block signals to prevent feedback loop
        self.ui.CanvasZoomSlider.blockSignals(True)
        self._canvas.set_zoom(zoom)
        self.ui.CanvasZoomSlider.blockSignals(False)
        # Update percent label
        self.ui.CanvasZoomPercent.setText(f"{value}%")

    def _sync_zoom_slider(self):
        """Sync the zoom slider with the current canvas zoom level."""
        zoom = self._canvas.get_zoom_level()
        zoom_percent = int(zoom * 100)
        # Clamp slider to its range (5-320), but show actual percent in label
        slider_value = max(5, min(320, zoom_percent))
        self.ui.CanvasZoomSlider.blockSignals(True)
        self.ui.CanvasZoomSlider.setValue(slider_value)
        self.ui.CanvasZoomSlider.blockSignals(False)
        # Update percent label with actual zoom value
        self.ui.CanvasZoomPercent.setText(f"{zoom_percent}%")

    def _on_zoom_from_canvas(self, zoom: float):
        """Handle zoom changes from the canvas (wheel, fit, etc.)."""
        self._sync_zoom_slider()

    def _toggle_toolbar(self):
        """Toggle secondary toolbar collapsed state."""
        self._toolbar_collapsed = not self._toolbar_collapsed
        self.ui.CanvasToolbarContent.setVisible(not self._toolbar_collapsed)

        # Update toggle button icon/text
        if self._toolbar_collapsed:
            self.ui.CanvasToolbarToggle.setText("+")
            self.ui.CanvasToolbarToggle.setToolTip("Expand secondary toolbar")
        else:
            self.ui.CanvasToolbarToggle.setText("-")
            self.ui.CanvasToolbarToggle.setToolTip("Collapse secondary toolbar")

    # =========================================================================
    # Zoom Controls
    # =========================================================================

    def _on_reset_zoom(self):
        """Reset zoom to 100%."""
        self._canvas.set_zoom(1.0)

    def _on_go_origin(self):
        """Center view on origin."""
        self._canvas.center_on_origin()

    def _on_color_sampler(self):
        """Show color history panel."""
        self._canvas.show_color_history_panel()

    # =========================================================================
    # Status Bar Updates
    # =========================================================================

    def _update_coordinates(self, x: float, y: float):
        """Update coordinate display in status bar."""
        self.ui.CanvasCoordinates.setText(f"X: {int(x)}  Y: {int(y)}")

    def _update_tool_hint(self):
        """Update tool hint in status bar based on current tool."""
        hints = {
            "select": "Select: Click items, Shift+click for multi-select, drag to move",
            "pan": "Pan: Drag to pan, or use Space+Drag in any tool",
            "connect": "Connect: Click source image, then click target to create connection",
            "annotate": "Note: Click to place a sticky note",
            "group": "Region: Drag to create a colored region",
            "crop": "Crop: Drag corners to crop, Esc to cancel. Non-destructive.",
            "pen": "Pen: Draw freehand strokes. Pressure-sensitive with tablet.",
            "rect": "Rectangle: Drag to draw. Hold Shift for square.",
            "ellipse": "Ellipse: Drag to draw. Hold Shift for circle.",
            "line": "Line: Click start, click end. Shift+L for arrow.",
        }
        hint = hints.get(self._current_tool, "")
        self.ui.CanvasToolHint.setText(hint)

    def _update_selection_info(self, selected_items: list):
        """Update selection info in status bar."""
        count = len(selected_items)
        if count == 0:
            self.ui.CanvasSelectionInfo.setText("")
        elif count == 1:
            self.ui.CanvasSelectionInfo.setText("1 item selected")
        else:
            self.ui.CanvasSelectionInfo.setText(f"{count} items selected")

    def _on_canvas_modified(self):
        """Handle canvas modification - debounced save state."""
        # Debounce saves to avoid excessive disk writes
        if not hasattr(self, '_save_timer'):
            self._save_timer = QTimer()
            self._save_timer.setSingleShot(True)
            self._save_timer.timeout.connect(self._do_save_canvas_state)

        # Reset timer on each modification (debounce 500ms)
        self._save_timer.start(500)

    def _do_save_canvas_state(self):
        """Actually perform the save (called after debounce)."""
        self._save_canvas_state()

    def _on_selection_changed(self, selected_items: list):
        """Handle selection change on canvas."""
        # Update fit selection button state
        self.ui.CanvasFitSelection.setEnabled(len(selected_items) > 0)
        # Update status bar
        self._update_selection_info(selected_items)

    def _on_item_added(self, item_id: str):
        """Handle new item added to canvas."""
        logger.debug(f"Item added to canvas: {item_id}")

    def _on_files_dropped_to_canvas(self, paths: list):
        """Handle files dropped to canvas - copy external files to gallery.

        Args:
            paths: List of file paths that were dropped onto the canvas
        """
        import shutil
        from core.settings_manager import get_setting

        try:
            gallery_path = get_setting("network_output_path")
            if not gallery_path:
                logger.warning("Cannot copy dropped files: no gallery path configured")
                return

            # Copy external files (ones not already in gallery) to gallery
            copied = 0
            for path in paths:
                # Skip files already in the gallery folder
                if path.startswith(gallery_path):
                    continue

                # Copy to gallery
                dest = os.path.join(gallery_path, os.path.basename(path))
                if not os.path.exists(dest):
                    shutil.copy2(path, dest)
                    copied += 1
                    logger.info(f"Copied dropped file to gallery: {os.path.basename(path)}")

            # Trigger gallery refresh if files were copied
            if copied > 0:
                try:
                    from core.event_bus import pipeline_events
                    pipeline_events.gallery_refresh_requested.emit(False)
                    self.show_status(f"Added {copied} file(s) to gallery", "success")
                except ImportError:
                    pass

        except Exception as e:
            logger.error(f"Error copying dropped files to gallery: {e}")

    def _on_remote_state_changed(self, state: dict):
        """Handle remote canvas state change from sync manager."""
        logger.info(f"Remote canvas state changed by {state.get('modified_by', 'unknown')}")

        # If viewport sync is off, remove viewport from state so user keeps their view
        if not self._sync_viewport and 'viewport' in state:
            state = dict(state)  # Copy to avoid modifying original
            del state['viewport']

        # Reload canvas state - last-write-wins
        self._canvas.load_state(state)

    def _on_sync_error(self, error_msg: str):
        """Handle sync error."""
        logger.warning(f"Canvas sync error: {error_msg}")
        self.show_status(f"Sync: {error_msg}", "warning")

    def _on_cursor_moved(self, x: float, y: float):
        """Handle local cursor movement - update presence."""
        if hasattr(self, '_presence_manager'):
            self._presence_manager.update_cursor(x, y)

    def _on_cursors_updated(self, cursors: dict):
        """Handle cursor updates from other users."""
        self._canvas.update_remote_cursors(cursors)

    def _on_user_joined(self, username: str):
        """Handle user joining the canvas."""
        logger.info(f"User joined canvas: {username}")
        self.show_status(f"{username} joined", "info")

    def _on_user_left(self, username: str):
        """Handle user leaving the canvas."""
        logger.info(f"User left canvas: {username}")
        self.show_status(f"{username} left", "info")

    def add_image_to_canvas(self, image_path: str, position: tuple = None):
        """
        Add an image to the canvas.

        Called from Gallery context menu or auto-add from ComfyUI.

        Args:
            image_path: Path to the image file
            position: Optional (x, y) position, or None for auto-placement
        """
        if position is None:
            # Auto-place near center of current view
            center = self._canvas.mapToScene(
                self._canvas.viewport().rect().center()
            )
            position = (center.x(), center.y())

        node = self._canvas.add_image(image_path, position[0], position[1])

        # Sync node with gallery data (likes, groups, colors)
        self._canvas.sync_node_from_gallery(image_path)

        # Check metadata for lineage and auto-connect
        self._auto_connect_from_metadata(node, image_path)

        return node

    def _auto_connect_from_metadata(self, node, image_path: str):
        """Auto-create connections from metadata lineage."""
        try:
            from comfyui.metadata import get_job_metadata

            # Get parent info from metadata
            metadata = get_job_metadata(os.path.dirname(image_path))
            if not metadata:
                return

            filename = os.path.basename(image_path)
            file_meta = metadata.get("files", {}).get(filename, {})
            parent_id = file_meta.get("parent_id")

            if parent_id:
                # Find parent node on canvas
                parent_node = self._canvas.find_node_by_file_id(parent_id)
                if parent_node:
                    self._canvas.add_connection(
                        parent_node.node_id,
                        node.node_id,
                        connection_type="auto"
                    )
                    logger.debug(f"Auto-connected {filename} to parent {parent_id}")
        except Exception as e:
            logger.debug(f"Could not auto-connect from metadata: {e}")

    def on_tab_activated(self):
        """Called when canvas tab becomes visible."""
        # Give canvas focus for keyboard shortcuts
        if hasattr(self, '_canvas'):
            self._canvas.setFocus()

        # Refresh sync if enabled
        if hasattr(self, '_sync_timer') and self._sync_timer.isActive():
            self._on_sync_poll()

        # Connect to gallery favorites signals if not already connected
        self._connect_gallery_signals()

        # Sync all nodes with current gallery state
        self._canvas.sync_all_from_gallery()

        logger.debug("Canvas tab activated")

    def _connect_gallery_signals(self):
        """Connect to gallery FavoritesManager signals for live updates."""
        if hasattr(self, '_gallery_signals_connected') and self._gallery_signals_connected:
            return  # Already connected

        favorites_manager = self._canvas._get_favorites_manager()
        if not favorites_manager:
            return

        try:
            # Connect to like changes
            favorites_manager.like_changed.connect(self._on_gallery_like_changed)
            # Connect to group changes
            favorites_manager.item_groups_changed.connect(self._on_gallery_groups_changed)
            favorites_manager.group_updated.connect(self._on_gallery_group_updated)

            self._gallery_signals_connected = True
            logger.debug("Connected to gallery favorites signals")
        except Exception as e:
            logger.warning(f"Could not connect to gallery signals: {e}")

    def _on_gallery_like_changed(self, path: str, is_liked: bool):
        """Handle like change from gallery."""
        self._canvas.sync_node_from_gallery(path)

    def _on_gallery_groups_changed(self, path: str):
        """Handle group membership change from gallery."""
        self._canvas.sync_node_from_gallery(path)

    def _on_gallery_group_updated(self, group_id: str):
        """Handle group property change from gallery (color change, etc.)."""
        # Need to refresh all nodes since group color may have changed
        self._canvas.sync_all_from_gallery()

    def on_tab_deactivated(self):
        """Called when switching away from canvas tab."""
        # Hide floating panels that shouldn't persist across tabs
        if hasattr(self, '_drawing_panel') and self._drawing_panel:
            self._drawing_panel.hide()

        # Hide color history panel
        if hasattr(self, '_canvas') and self._canvas:
            self._canvas.hide_color_history_panel()

        # Save state before leaving
        self._save_canvas_state()
        logger.debug("Canvas tab deactivated")
