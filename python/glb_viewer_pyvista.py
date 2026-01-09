"""
PyVista-based GLB 3D Viewer for Luma Tools.

Provides an interactive 3D viewer widget for GLB/GLTF models with full PBR material support.
Uses PyVista with VTK for rendering and pyvistaqt for Qt integration.
"""

import os
from typing import Optional, Dict

# Set Qt API before importing Qt modules
os.environ.setdefault("QT_API", "pyside2")

from PySide2.QtCore import Qt, Signal, QRunnable, QObject, QThreadPool
from PySide2.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFrame, QSizePolicy, QStackedWidget
)

# Check for pyvista availability
try:
    import pyvista as pv
    pv.global_theme.allow_empty_mesh = True
    PYVISTA_AVAILABLE = True
except ImportError:
    PYVISTA_AVAILABLE = False

# Check for pyvistaqt availability
try:
    from pyvistaqt import QtInteractor
    PYVISTAQT_AVAILABLE = True
except ImportError:
    PYVISTAQT_AVAILABLE = False


# ============================================================================
# MODEL LOADER (Background Thread)
# ============================================================================

class PyVistaModelLoaderSignals(QObject):
    """Signals for the model loader worker."""
    finished = Signal(object)  # Emits dict with mesh data
    error = Signal(str)        # Emits error message
    progress = Signal(str)     # Emits status message


class PyVistaModelLoaderWorker(QRunnable):
    """
    Background worker to load GLB/GLTF models without blocking the UI.
    """

    def __init__(self, glb_path: str):
        super().__init__()
        self.glb_path = glb_path
        self.signals = PyVistaModelLoaderSignals()

    def run(self):
        """Load the model in background thread."""
        try:
            if not os.path.exists(self.glb_path):
                self.signals.error.emit(f"File not found: {self.glb_path}")
                return

            self.signals.progress.emit("Loading model file...")

            # Read the glTF/GLB file
            block = pv.read(self.glb_path)

            self.signals.progress.emit("Processing meshes...")

            # Extract meshes from the multiblock dataset
            meshes = []
            self._extract_meshes(block, meshes)

            if not meshes:
                self.signals.error.emit("No valid meshes found in file")
                return

            self.signals.progress.emit("Finalizing...")

            result = {
                'meshes': meshes,
                'path': self.glb_path,
                'block': block  # Keep original block for import_gltf
            }

            self.signals.finished.emit(result)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.signals.error.emit(f"Error loading model: {e}")

    def _extract_meshes(self, block, meshes, depth=0):
        """Recursively extract meshes from multiblock dataset."""
        if depth > 10:  # Prevent infinite recursion
            return

        if isinstance(block, pv.MultiBlock):
            for i in range(block.n_blocks):
                sub_block = block[i]
                if sub_block is not None:
                    self._extract_meshes(sub_block, meshes, depth + 1)
        elif isinstance(block, pv.PolyData):
            if block.n_points > 0:
                meshes.append(block)
        elif hasattr(block, 'extract_surface'):
            try:
                surface = block.extract_surface()
                if surface.n_points > 0:
                    meshes.append(surface)
            except Exception:
                pass


# ============================================================================
# PYVISTA GLB VIEWER WIDGET
# ============================================================================

if PYVISTA_AVAILABLE and PYVISTAQT_AVAILABLE:
    class PyVistaGLBViewerWidget(QWidget):
        """
        Interactive 3D viewer widget for GLB/GLTF models using PyVista.

        Features:
        - Full PBR material support via VTK 9
        - Environment texture support for realistic lighting
        - Arcball rotation with left mouse button
        - Pan with middle mouse button or Shift+left
        - Zoom with scroll wheel or right mouse drag
        - Wireframe toggle
        """

        modelLoaded = Signal(str)  # Emits model path when loaded
        loadError = Signal(str)    # Emits error message

        def __init__(self, parent=None):
            super().__init__(parent)

            self._model_path = None
            self._meshes = []
            self._wireframe = False
            self._show_grid = True
            self._actors = []

            self._setup_ui()

        def _setup_ui(self):
            """Set up the widget UI with PyVista plotter."""
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            # Create a frame to hold the plotter
            self._frame = QFrame()
            self._frame.setStyleSheet("background-color: #26292e;")
            frame_layout = QVBoxLayout(self._frame)
            frame_layout.setContentsMargins(0, 0, 0, 0)

            # Create the PyVista QtInteractor
            self._plotter = QtInteractor(self._frame)
            self._plotter.set_background('#26292e')

            # Enable anti-aliasing for smoother rendering
            self._plotter.enable_anti_aliasing('ssaa')

            frame_layout.addWidget(self._plotter.interactor)
            layout.addWidget(self._frame)

            # Set minimum size
            self.setMinimumSize(400, 300)

            # Set focus policy for keyboard events
            self.setFocusPolicy(Qt.StrongFocus)

        def set_model_data(self, model_data: Dict):
            """
            Set pre-loaded model data (from async loader).

            Args:
                model_data: Dict containing meshes, path, and optionally block
            """
            self._model_path = model_data.get('path')
            self._meshes = model_data.get('meshes', [])

            # Clear existing actors
            self._plotter.clear()
            self._actors = []

            # Add meshes to the plotter
            for mesh in self._meshes:
                try:
                    # Check if mesh has texture coordinates and try to render with PBR
                    if mesh.active_texture_coordinates is not None:
                        actor = self._plotter.add_mesh(
                            mesh,
                            pbr=True,
                            metallic=0.2,
                            roughness=0.5,
                            style='surface' if not self._wireframe else 'wireframe'
                        )
                    else:
                        # Render with vertex colors if available, otherwise default
                        if 'RGB' in mesh.array_names or 'RGBA' in mesh.array_names:
                            actor = self._plotter.add_mesh(
                                mesh,
                                scalars='RGB' if 'RGB' in mesh.array_names else 'RGBA',
                                rgb=True,
                                style='surface' if not self._wireframe else 'wireframe'
                            )
                        else:
                            actor = self._plotter.add_mesh(
                                mesh,
                                color='#b0b0b0',
                                pbr=True,
                                metallic=0.1,
                                roughness=0.6,
                                style='surface' if not self._wireframe else 'wireframe'
                            )
                    self._actors.append(actor)
                except Exception as e:
                    print(f"Error adding mesh: {e}")
                    # Fallback to simple rendering
                    try:
                        actor = self._plotter.add_mesh(
                            mesh,
                            color='#b0b0b0',
                            style='surface' if not self._wireframe else 'wireframe'
                        )
                        self._actors.append(actor)
                    except Exception as e2:
                        print(f"Fallback rendering failed: {e2}")

            # Add a floor grid if enabled
            if self._show_grid and self._meshes:
                self._add_floor_grid()

            # Reset camera to fit the scene
            self._plotter.reset_camera()
            self._plotter.camera.zoom(0.8)

            if self._model_path:
                self.modelLoaded.emit(self._model_path)

        def import_gltf_direct(self, glb_path: str) -> bool:
            """
            Import a glTF file directly using PyVista's import_gltf method.
            This preserves PBR materials better than manual mesh extraction.

            Args:
                glb_path: Path to the GLB/GLTF file

            Returns:
                True if loading succeeded
            """
            try:
                self._model_path = glb_path
                self._plotter.clear()
                self._actors = []

                # Use import_gltf for best material preservation
                self._plotter.import_gltf(glb_path)

                # Add floor grid
                if self._show_grid:
                    self._add_floor_grid()

                # Reset camera
                self._plotter.reset_camera()
                self._plotter.camera.zoom(0.8)

                self.modelLoaded.emit(glb_path)
                return True

            except Exception as e:
                self.loadError.emit(f"Error loading model: {e}")
                import traceback
                traceback.print_exc()
                return False

        def _add_floor_grid(self):
            """Add a floor grid for reference."""
            try:
                # Calculate bounds from meshes
                if self._meshes:
                    all_bounds = [m.bounds for m in self._meshes if m.n_points > 0]
                    if all_bounds:
                        min_x = min(b[0] for b in all_bounds)
                        max_x = max(b[1] for b in all_bounds)
                        min_y = min(b[2] for b in all_bounds)
                        max_y = max(b[3] for b in all_bounds)
                        min_z = min(b[4] for b in all_bounds)

                        # Create grid at the bottom of the model
                        size = max(max_x - min_x, max_y - min_y) * 1.5
                        center_x = (min_x + max_x) / 2
                        center_y = (min_y + max_y) / 2

                        # Create a simple grid plane
                        grid = pv.Plane(
                            center=(center_x, center_y, min_z - 0.01),
                            direction=(0, 0, 1),
                            i_size=size,
                            j_size=size,
                            i_resolution=10,
                            j_resolution=10
                        )
                        self._plotter.add_mesh(
                            grid,
                            color='#404040',
                            style='wireframe',
                            line_width=1,
                            opacity=0.5
                        )
            except Exception as e:
                print(f"Error adding floor grid: {e}")

        def toggle_wireframe(self):
            """Toggle wireframe mode."""
            self._wireframe = not self._wireframe

            for actor in self._actors:
                try:
                    if self._wireframe:
                        actor.GetProperty().SetRepresentationToWireframe()
                    else:
                        actor.GetProperty().SetRepresentationToSurface()
                except Exception:
                    pass

            self._plotter.render()

        def toggle_grid(self):
            """Toggle grid visibility."""
            self._show_grid = not self._show_grid
            # Would need to re-render to add/remove grid
            # For now, just update the flag

        def reset_view(self):
            """Reset camera to default view."""
            self._plotter.reset_camera()
            self._plotter.camera.zoom(0.8)
            self._plotter.render()

        def get_camera_state(self) -> Optional[Dict]:
            """Get the current camera state for preservation."""
            try:
                camera = self._plotter.camera
                return {
                    'position': camera.position,
                    'focal_point': camera.focal_point,
                    'up': camera.up,
                    'clipping_range': camera.clipping_range,
                }
            except Exception as e:
                print(f"Error getting camera state: {e}")
                return None

        def set_camera_state(self, state: Dict):
            """Restore a previously saved camera state."""
            if not state:
                return
            try:
                camera = self._plotter.camera
                if 'position' in state:
                    camera.position = state['position']
                if 'focal_point' in state:
                    camera.focal_point = state['focal_point']
                if 'up' in state:
                    camera.up = state['up']
                if 'clipping_range' in state:
                    camera.clipping_range = state['clipping_range']
                self._plotter.render()
            except Exception as e:
                print(f"Error setting camera state: {e}")

        def set_environment_texture(self, texture_path: str):
            """Set environment texture for PBR lighting."""
            try:
                texture = pv.read_texture(texture_path)
                self._plotter.set_environment_texture(texture)
            except Exception as e:
                print(f"Error setting environment texture: {e}")

        def close(self):
            """Clean up resources."""
            try:
                self._plotter.close()
            except Exception:
                pass
            super().close()

else:
    # Fallback widget when PyVista/pyvistaqt is not available
    class PyVistaGLBViewerWidget(QWidget):
        """Fallback widget when PyVista is not available."""
        modelLoaded = Signal(str)
        loadError = Signal(str)

        def __init__(self, parent=None):
            super().__init__(parent)
            layout = QVBoxLayout(self)

            msg = "PyVista 3D Viewer not available.\n\n"
            if not PYVISTA_AVAILABLE:
                msg += "Please install PyVista:\npip install pyvista\n\n"
            if not PYVISTAQT_AVAILABLE:
                msg += "Please install pyvistaqt:\npip install pyvistaqt"

            label = QLabel(msg)
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("color: #888; font-size: 14px;")
            layout.addWidget(label)
            self.setMinimumSize(400, 300)

        def set_model_data(self, model_data: Dict):
            self.loadError.emit("PyVista not available")

        def import_gltf_direct(self, glb_path: str) -> bool:
            self.loadError.emit("PyVista not available")
            return False

        def toggle_wireframe(self):
            pass

        def toggle_grid(self):
            pass

        def reset_view(self):
            pass

        def get_camera_state(self) -> Optional[Dict]:
            return None

        def set_camera_state(self, state: Dict):
            pass

        def set_environment_texture(self, texture_path: str):
            pass


# ============================================================================
# PYVISTA GLB VIEWER DIALOG
# ============================================================================

class PyVistaGLBViewerDialog(QWidget):
    """
    Dialog for viewing GLB/GLTF 3D models using PyVista.

    Features:
    - Full PBR material support
    - Async model loading with progress
    - Control buttons for reset, wireframe toggle
    - Keyboard shortcuts (R=reset, W=wireframe, Esc=close)
    """

    def __init__(self, glb_path: str, parent=None):
        super().__init__(parent, Qt.Window)

        self._glb_path = glb_path
        self._is_loading = False
        self._setup_ui()
        self._load_model_async()

    def _setup_ui(self):
        """Set up the dialog UI."""
        filename = os.path.basename(self._glb_path)
        self.setWindowTitle(f"3D Viewer - {filename}")
        self.setMinimumSize(800, 600)

        # Apply dark theme
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e22;
            }
            QPushButton {
                background-color: #3c414b;
                color: #e0e0e0;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #4a5160;
            }
            QPushButton:pressed {
                background-color: #2a2e36;
            }
            QPushButton:disabled {
                background-color: #2a2e36;
                color: #666;
            }
            QLabel {
                color: #a0a0a0;
                font-size: 11px;
            }
        """)

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Stacked widget for loading/viewer states
        self._stacked = QStackedWidget()
        self._stacked.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Loading page
        self._loading_page = QWidget()
        loading_layout = QVBoxLayout(self._loading_page)
        loading_layout.setAlignment(Qt.AlignCenter)

        self._loading_label = QLabel("Loading model...")
        self._loading_label.setAlignment(Qt.AlignCenter)
        self._loading_label.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                font-size: 16px;
                font-weight: bold;
            }
        """)
        loading_layout.addWidget(self._loading_label)

        self._loading_status = QLabel("")
        self._loading_status.setAlignment(Qt.AlignCenter)
        self._loading_status.setStyleSheet("color: #888; font-size: 12px;")
        loading_layout.addWidget(self._loading_status)

        self._stacked.addWidget(self._loading_page)

        # 3D Viewer page
        self._viewer = PyVistaGLBViewerWidget(self)
        self._viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._stacked.addWidget(self._viewer)

        layout.addWidget(self._stacked)

        # Control bar
        self._control_bar = QFrame()
        self._control_bar.setStyleSheet("background-color: #2a2e36; padding: 8px;")
        control_layout = QHBoxLayout(self._control_bar)
        control_layout.setContentsMargins(12, 8, 12, 8)

        # Controls label
        controls_label = QLabel("Controls: Left-drag=Rotate • Middle-drag=Pan • Scroll=Zoom • R=Reset • W=Wireframe")
        control_layout.addWidget(controls_label)

        control_layout.addStretch()

        # Reset button
        self._reset_btn = QPushButton("Reset View (R)")
        self._reset_btn.setMinimumWidth(100)
        self._reset_btn.setEnabled(False)
        self._reset_btn.clicked.connect(self._on_reset)
        control_layout.addWidget(self._reset_btn)

        # Wireframe button
        self._wireframe_btn = QPushButton("Wireframe (W)")
        self._wireframe_btn.setMinimumWidth(100)
        self._wireframe_btn.setCheckable(True)
        self._wireframe_btn.setEnabled(False)
        self._wireframe_btn.clicked.connect(self._on_wireframe)
        control_layout.addWidget(self._wireframe_btn)

        # Close button
        self._close_btn = QPushButton("Close")
        self._close_btn.setMinimumWidth(80)
        self._close_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a9eff;
                color: white;
            }
            QPushButton:hover {
                background-color: #6ab0ff;
            }
        """)
        self._close_btn.clicked.connect(self.close)
        control_layout.addWidget(self._close_btn)

        layout.addWidget(self._control_bar)

    def _load_model_async(self):
        """Load the model asynchronously."""
        if not is_pyvista_available():
            self._loading_label.setText("PyVista Not Available")
            self._loading_status.setText("Please install pyvista and pyvistaqt:\npip install pyvista pyvistaqt")
            return

        # Show loading state
        self._is_loading = True
        self._stacked.setCurrentIndex(0)
        self._loading_label.setText("Loading model...")
        self._loading_status.setText(os.path.basename(self._glb_path))

        # Create and start the worker
        self._loader = PyVistaModelLoaderWorker(self._glb_path)
        self._loader.signals.progress.connect(self._on_load_progress)
        self._loader.signals.finished.connect(self._on_load_finished)
        self._loader.signals.error.connect(self._on_load_error)

        QThreadPool.globalInstance().start(self._loader)

    def _on_load_progress(self, message: str):
        """Update loading status message."""
        self._loading_status.setText(message)

    def _on_load_finished(self, model_data: dict):
        """Handle successful async model loading."""
        self._is_loading = False
        self._viewer.set_model_data(model_data)

        # Switch to viewer page
        self._stacked.setCurrentIndex(1)

        # Enable controls
        self._reset_btn.setEnabled(True)
        self._wireframe_btn.setEnabled(True)

        print(f"Loaded 3D model: {model_data.get('path', 'unknown')}")

    def _on_load_error(self, error_msg: str):
        """Handle model loading error."""
        self._is_loading = False
        self._loading_label.setText("Error loading model")
        self._loading_status.setText(error_msg)
        self._loading_status.setStyleSheet("color: #ff6b6b; font-size: 12px;")

    def _on_reset(self):
        """Reset the view."""
        self._viewer.reset_view()

    def _on_wireframe(self):
        """Toggle wireframe mode."""
        self._viewer.toggle_wireframe()

    def keyPressEvent(self, event):
        """Handle keyboard events."""
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() == Qt.Key_R:
            self._on_reset()
        elif event.key() == Qt.Key_W:
            self._on_wireframe()
            self._wireframe_btn.setChecked(not self._wireframe_btn.isChecked())
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        """Clean up on close."""
        try:
            if hasattr(self, '_viewer') and self._viewer:
                self._viewer.close()
        except Exception:
            pass
        super().closeEvent(event)


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def is_pyvista_available() -> bool:
    """Check if PyVista and pyvistaqt are available."""
    return PYVISTA_AVAILABLE and PYVISTAQT_AVAILABLE


def create_viewer_widget(parent=None) -> QWidget:
    """
    Create the appropriate viewer widget based on available libraries.

    Returns PyVistaGLBViewerWidget if PyVista is available,
    otherwise returns a fallback widget.
    """
    return PyVistaGLBViewerWidget(parent)


def create_viewer_dialog(glb_path: str, parent=None) -> QWidget:
    """
    Create a viewer dialog for the given model path.

    Returns PyVistaGLBViewerDialog if PyVista is available.
    """
    return PyVistaGLBViewerDialog(glb_path, parent)
