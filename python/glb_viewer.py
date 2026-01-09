"""
GLB 3D Viewer for Luma Tools.

Provides an interactive 3D viewer dialog for GLB/GLTF models with PBR material support.
Uses QOpenGLWidget for rendering with mouse controls for rotation, pan, and zoom.
"""

import os
import math
from typing import Optional, Dict, List, Tuple

import numpy as np

from PySide2.QtCore import Qt, Signal, QPoint, QSize, QRunnable, QObject, QThreadPool
from PySide2.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QWidget,
    QLabel, QFrame, QSizePolicy, QMessageBox, QStackedWidget
)
from PySide2.QtGui import QColor, QMouseEvent, QWheelEvent, QKeyEvent

try:
    from PySide2.QtWidgets import QOpenGLWidget
    from PySide2.QtGui import QOpenGLContext, QSurfaceFormat
    OPENGL_AVAILABLE = True
except ImportError:
    OPENGL_AVAILABLE = False

try:
    from OpenGL.GL import *
    from OpenGL.GLU import *
    PYOPENGL_AVAILABLE = True
except ImportError:
    PYOPENGL_AVAILABLE = False


# ============================================================================
# MODEL LOADER (Background Thread)
# ============================================================================

class ModelLoaderSignals(QObject):
    """Signals for the model loader worker."""
    finished = Signal(object)  # Emits dict with mesh data
    error = Signal(str)        # Emits error message
    progress = Signal(str)     # Emits status message


class ModelLoaderWorker(QRunnable):
    """
    Background worker to load GLB/GLTF models without blocking the UI.
    """

    def __init__(self, glb_path: str):
        super().__init__()
        self.glb_path = glb_path
        self.signals = ModelLoaderSignals()

    def run(self):
        """Load the model in background thread."""
        try:
            import trimesh

            if not os.path.exists(self.glb_path):
                self.signals.error.emit(f"File not found: {self.glb_path}")
                return

            self.signals.progress.emit("Loading model file...")

            # Load the model
            scene_or_mesh = trimesh.load(self.glb_path)

            self.signals.progress.emit("Processing meshes...")

            meshes = []
            # Extract meshes
            if isinstance(scene_or_mesh, trimesh.Scene):
                for name, geometry in scene_or_mesh.geometry.items():
                    if isinstance(geometry, trimesh.Trimesh):
                        mesh_data = self._extract_mesh_data(geometry, name)
                        if mesh_data:
                            meshes.append(mesh_data)
            elif isinstance(scene_or_mesh, trimesh.Trimesh):
                mesh_data = self._extract_mesh_data(scene_or_mesh, "mesh")
                if mesh_data:
                    meshes.append(mesh_data)

            if not meshes:
                self.signals.error.emit("No valid meshes found in file")
                return

            # Calculate scene bounds
            scene_center, scene_radius = self._calculate_scene_bounds(scene_or_mesh)

            self.signals.progress.emit("Finalizing...")

            result = {
                'meshes': meshes,
                'scene_center': scene_center,
                'scene_radius': scene_radius,
                'path': self.glb_path
            }

            self.signals.finished.emit(result)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.signals.error.emit(f"Error loading model: {e}")

    def _extract_mesh_data(self, mesh, name: str) -> Optional[Dict]:
        """Extract renderable data from a trimesh mesh."""
        try:
            vertices = np.array(mesh.vertices, dtype=np.float32)
            faces = np.array(mesh.faces, dtype=np.uint32)

            # Get or compute normals
            if mesh.vertex_normals is not None:
                normals = np.array(mesh.vertex_normals, dtype=np.float32)
            else:
                normals = np.zeros_like(vertices)

            # Get color if available
            if hasattr(mesh.visual, 'vertex_colors') and mesh.visual.vertex_colors is not None:
                colors = np.array(mesh.visual.vertex_colors, dtype=np.float32) / 255.0
            elif hasattr(mesh.visual, 'main_color') and mesh.visual.main_color is not None:
                color = np.array(mesh.visual.main_color[:3], dtype=np.float32) / 255.0
                colors = np.tile(color, (len(vertices), 1))
            else:
                # Default gray color
                colors = np.full((len(vertices), 3), 0.7, dtype=np.float32)

            return {
                'name': name,
                'vertices': vertices,
                'normals': normals,
                'faces': faces,
                'colors': colors,
                'vao': None,
                'vbo_vertices': None,
                'vbo_normals': None,
                'vbo_colors': None,
                'ebo': None
            }

        except Exception as e:
            print(f"Error extracting mesh data: {e}")
            return None

    def _calculate_scene_bounds(self, scene_or_mesh) -> Tuple[np.ndarray, float]:
        """Calculate scene center and radius for camera positioning."""
        import trimesh

        try:
            if isinstance(scene_or_mesh, trimesh.Scene):
                bounds = scene_or_mesh.bounds
            else:
                bounds = scene_or_mesh.bounds

            if bounds is not None and len(bounds) == 2:
                scene_center = (bounds[0] + bounds[1]) / 2
                scene_radius = np.linalg.norm(bounds[1] - bounds[0]) / 2
            else:
                scene_center = np.array([0.0, 0.0, 0.0])
                scene_radius = 1.0

            return scene_center, scene_radius

        except Exception:
            return np.array([0.0, 0.0, 0.0]), 1.0


# ============================================================================
# GLB VIEWER WIDGET (OpenGL)
# ============================================================================

if OPENGL_AVAILABLE and PYOPENGL_AVAILABLE:
    class GLBViewerWidget(QOpenGLWidget):
        """
        Interactive 3D viewer widget for GLB/GLTF models.

        Features:
        - Arcball rotation with left mouse button
        - Pan with middle mouse button
        - Zoom with scroll wheel or right mouse drag
        - Basic PBR-like shading
        - Wireframe toggle
        """

        modelLoaded = Signal(str)  # Emits model path when loaded
        loadError = Signal(str)    # Emits error message

        def __init__(self, parent=None):
            super().__init__(parent)

            # Model data
            self._model_path = None
            self._meshes: List[Dict] = []  # List of mesh data dicts
            self._scene_center = np.array([0.0, 0.0, 0.0])
            self._scene_radius = 1.0

            # Camera state
            self._rotation_x = 30.0  # Elevation
            self._rotation_y = 45.0  # Azimuth
            self._pan_x = 0.0
            self._pan_y = 0.0
            self._zoom = 1.0
            self._camera_distance = 3.0

            # Mouse tracking
            self._last_mouse_pos = QPoint()
            self._mouse_buttons = Qt.NoButton

            # Rendering options
            self._wireframe = False
            self._show_grid = True

            # OpenGL state
            self._initialized = False
            self._vao_list = []

            # Set minimum size
            self.setMinimumSize(400, 300)

            # Enable mouse tracking
            self.setMouseTracking(True)
            self.setFocusPolicy(Qt.StrongFocus)

        def set_model_data(self, model_data: Dict):
            """
            Set pre-loaded model data (from async loader).

            Args:
                model_data: Dict containing meshes, scene_center, scene_radius, path
            """
            self._model_path = model_data.get('path')
            self._meshes = model_data.get('meshes', [])
            self._scene_center = model_data.get('scene_center', np.array([0.0, 0.0, 0.0]))
            self._scene_radius = model_data.get('scene_radius', 1.0)

            # Reset camera
            self._reset_camera()

            # Trigger OpenGL update
            self.update()

            if self._model_path:
                self.modelLoaded.emit(self._model_path)

        def load_model(self, glb_path: str) -> bool:
            """
            Load a GLB/GLTF model synchronously (legacy method).

            Args:
                glb_path: Path to the GLB/GLTF file

            Returns:
                True if loading succeeded

            Note: Prefer using ModelLoaderWorker for async loading.
            """
            try:
                import trimesh

                if not os.path.exists(glb_path):
                    self.loadError.emit(f"File not found: {glb_path}")
                    return False

                self._model_path = glb_path
                self._meshes = []

                # Load the model
                scene_or_mesh = trimesh.load(glb_path)

                # Extract meshes
                if isinstance(scene_or_mesh, trimesh.Scene):
                    for name, geometry in scene_or_mesh.geometry.items():
                        if isinstance(geometry, trimesh.Trimesh):
                            mesh_data = self._extract_mesh_data(geometry, name)
                            if mesh_data:
                                self._meshes.append(mesh_data)
                elif isinstance(scene_or_mesh, trimesh.Trimesh):
                    mesh_data = self._extract_mesh_data(scene_or_mesh, "mesh")
                    if mesh_data:
                        self._meshes.append(mesh_data)

                if not self._meshes:
                    self.loadError.emit("No valid meshes found in file")
                    return False

                # Calculate scene bounds
                self._calculate_scene_bounds(scene_or_mesh)

                # Reset camera
                self._reset_camera()

                # Trigger OpenGL update
                self.update()

                self.modelLoaded.emit(glb_path)
                return True

            except Exception as e:
                self.loadError.emit(f"Error loading model: {e}")
                import traceback
                traceback.print_exc()
                return False

        def _extract_mesh_data(self, mesh, name: str) -> Optional[Dict]:
            """Extract renderable data from a trimesh mesh."""
            try:
                vertices = np.array(mesh.vertices, dtype=np.float32)
                faces = np.array(mesh.faces, dtype=np.uint32)

                # Get or compute normals
                if mesh.vertex_normals is not None:
                    normals = np.array(mesh.vertex_normals, dtype=np.float32)
                else:
                    normals = np.zeros_like(vertices)

                # Get color if available
                if hasattr(mesh.visual, 'vertex_colors') and mesh.visual.vertex_colors is not None:
                    colors = np.array(mesh.visual.vertex_colors, dtype=np.float32) / 255.0
                elif hasattr(mesh.visual, 'main_color') and mesh.visual.main_color is not None:
                    color = np.array(mesh.visual.main_color[:3], dtype=np.float32) / 255.0
                    colors = np.tile(color, (len(vertices), 1))
                else:
                    # Default gray color
                    colors = np.full((len(vertices), 3), 0.7, dtype=np.float32)

                return {
                    'name': name,
                    'vertices': vertices,
                    'normals': normals,
                    'faces': faces,
                    'colors': colors,
                    'vao': None,
                    'vbo_vertices': None,
                    'vbo_normals': None,
                    'vbo_colors': None,
                    'ebo': None
                }

            except Exception as e:
                print(f"Error extracting mesh data: {e}")
                return None

        def _calculate_scene_bounds(self, scene_or_mesh):
            """Calculate scene center and radius for camera positioning."""
            import trimesh

            try:
                if isinstance(scene_or_mesh, trimesh.Scene):
                    bounds = scene_or_mesh.bounds
                else:
                    bounds = scene_or_mesh.bounds

                if bounds is not None and len(bounds) == 2:
                    self._scene_center = (bounds[0] + bounds[1]) / 2
                    self._scene_radius = np.linalg.norm(bounds[1] - bounds[0]) / 2
                else:
                    self._scene_center = np.array([0.0, 0.0, 0.0])
                    self._scene_radius = 1.0

            except Exception:
                self._scene_center = np.array([0.0, 0.0, 0.0])
                self._scene_radius = 1.0

        def _reset_camera(self):
            """Reset camera to default view."""
            self._rotation_x = 30.0
            self._rotation_y = 45.0
            self._pan_x = 0.0
            self._pan_y = 0.0
            self._zoom = 1.0
            self._camera_distance = self._scene_radius * 3.0
            self.update()

        def initializeGL(self):
            """Initialize OpenGL resources."""
            glClearColor(0.15, 0.15, 0.18, 1.0)
            glEnable(GL_DEPTH_TEST)
            glEnable(GL_LIGHTING)
            glEnable(GL_LIGHT0)
            glEnable(GL_LIGHT1)
            glEnable(GL_COLOR_MATERIAL)
            glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
            glEnable(GL_NORMALIZE)

            # Smooth shading
            glShadeModel(GL_SMOOTH)

            # Set up lights
            # Key light (warm)
            glLightfv(GL_LIGHT0, GL_POSITION, [1.0, 1.0, 1.0, 0.0])
            glLightfv(GL_LIGHT0, GL_DIFFUSE, [0.9, 0.85, 0.8, 1.0])
            glLightfv(GL_LIGHT0, GL_SPECULAR, [1.0, 1.0, 1.0, 1.0])

            # Fill light (cool)
            glLightfv(GL_LIGHT1, GL_POSITION, [-0.5, 0.3, 1.0, 0.0])
            glLightfv(GL_LIGHT1, GL_DIFFUSE, [0.3, 0.35, 0.4, 1.0])
            glLightfv(GL_LIGHT1, GL_SPECULAR, [0.0, 0.0, 0.0, 1.0])

            # Ambient light
            glLightModelfv(GL_LIGHT_MODEL_AMBIENT, [0.2, 0.2, 0.22, 1.0])

            self._initialized = True

        def resizeGL(self, width, height):
            """Handle widget resize."""
            glViewport(0, 0, width, height)
            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()

            aspect = width / max(height, 1)
            gluPerspective(45.0, aspect, 0.01, 1000.0)

            glMatrixMode(GL_MODELVIEW)

        def paintGL(self):
            """Render the scene."""
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

            glMatrixMode(GL_MODELVIEW)
            glLoadIdentity()

            # Apply camera transform
            glTranslatef(-self._pan_x, -self._pan_y, -self._camera_distance * self._zoom)
            glRotatef(self._rotation_x, 1, 0, 0)
            glRotatef(self._rotation_y, 0, 1, 0)
            glTranslatef(-self._scene_center[0], -self._scene_center[1], -self._scene_center[2])

            # Draw grid
            if self._show_grid:
                self._draw_grid()

            # Set polygon mode
            if self._wireframe:
                glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
            else:
                glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

            # Draw meshes
            glEnable(GL_LIGHTING)
            for mesh in self._meshes:
                self._draw_mesh(mesh)

            # Reset polygon mode
            glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

        def _draw_grid(self):
            """Draw a reference grid."""
            glDisable(GL_LIGHTING)
            glColor3f(0.3, 0.3, 0.35)
            glLineWidth(1.0)

            grid_size = max(self._scene_radius * 2, 2.0)
            grid_divisions = 10
            step = grid_size / grid_divisions

            glBegin(GL_LINES)
            for i in range(-grid_divisions, grid_divisions + 1):
                # X lines
                glVertex3f(i * step, 0, -grid_size)
                glVertex3f(i * step, 0, grid_size)
                # Z lines
                glVertex3f(-grid_size, 0, i * step)
                glVertex3f(grid_size, 0, i * step)
            glEnd()

            glEnable(GL_LIGHTING)

        def _draw_mesh(self, mesh: Dict):
            """Draw a single mesh using vertex arrays (much faster than immediate mode)."""
            vertices = mesh['vertices']
            normals = mesh['normals']
            faces = mesh['faces']
            colors = mesh['colors']

            # Flatten faces for indexed drawing
            indices = faces.flatten().astype(np.uint32)

            # Enable vertex arrays
            glEnableClientState(GL_VERTEX_ARRAY)
            glEnableClientState(GL_NORMAL_ARRAY)
            glEnableClientState(GL_COLOR_ARRAY)

            # Set up pointers
            glVertexPointer(3, GL_FLOAT, 0, vertices)
            glNormalPointer(GL_FLOAT, 0, normals)

            # Handle colors (ensure 3 components)
            if colors.shape[1] >= 3:
                color_data = np.ascontiguousarray(colors[:, :3], dtype=np.float32)
            else:
                color_data = colors
            glColorPointer(3, GL_FLOAT, 0, color_data)

            # Draw with indices
            glDrawElements(GL_TRIANGLES, len(indices), GL_UNSIGNED_INT, indices)

            # Disable arrays
            glDisableClientState(GL_VERTEX_ARRAY)
            glDisableClientState(GL_NORMAL_ARRAY)
            glDisableClientState(GL_COLOR_ARRAY)

        def mousePressEvent(self, event: QMouseEvent):
            """Handle mouse press."""
            self._last_mouse_pos = event.pos()
            self._mouse_buttons = event.buttons()

        def mouseMoveEvent(self, event: QMouseEvent):
            """Handle mouse move for rotation/pan."""
            if self._mouse_buttons == Qt.NoButton:
                return

            dx = event.x() - self._last_mouse_pos.x()
            dy = event.y() - self._last_mouse_pos.y()

            if self._mouse_buttons & Qt.LeftButton:
                # Rotate
                sensitivity = 0.5
                self._rotation_y += dx * sensitivity
                self._rotation_x += dy * sensitivity
                self._rotation_x = max(-90, min(90, self._rotation_x))

            elif self._mouse_buttons & Qt.MiddleButton:
                # Pan
                sensitivity = self._scene_radius * 0.005
                self._pan_x -= dx * sensitivity
                self._pan_y += dy * sensitivity

            elif self._mouse_buttons & Qt.RightButton:
                # Zoom
                sensitivity = 0.01
                self._zoom *= 1.0 - dy * sensitivity
                self._zoom = max(0.1, min(10.0, self._zoom))

            self._last_mouse_pos = event.pos()
            self.update()

        def mouseReleaseEvent(self, event: QMouseEvent):
            """Handle mouse release."""
            self._mouse_buttons = event.buttons()

        def wheelEvent(self, event: QWheelEvent):
            """Handle scroll wheel for zoom."""
            delta = event.angleDelta().y()
            sensitivity = 0.001
            self._zoom *= 1.0 - delta * sensitivity
            self._zoom = max(0.1, min(10.0, self._zoom))
            self.update()

        def keyPressEvent(self, event: QKeyEvent):
            """Handle keyboard input."""
            if event.key() == Qt.Key_R:
                self._reset_camera()
            elif event.key() == Qt.Key_W:
                self._wireframe = not self._wireframe
                self.update()
            elif event.key() == Qt.Key_G:
                self._show_grid = not self._show_grid
                self.update()
            elif event.key() == Qt.Key_Escape:
                # Close parent dialog if any
                parent = self.parent()
                while parent:
                    if isinstance(parent, QDialog):
                        parent.close()
                        break
                    parent = parent.parent()
            else:
                super().keyPressEvent(event)

        def toggle_wireframe(self):
            """Toggle wireframe mode."""
            self._wireframe = not self._wireframe
            self.update()

        def reset_view(self):
            """Reset camera to default view."""
            self._reset_camera()

        def get_camera_state(self) -> Optional[Dict]:
            """Get the current camera state for preservation."""
            return {
                'rotation_x': self._rotation_x,
                'rotation_y': self._rotation_y,
                'pan_x': self._pan_x,
                'pan_y': self._pan_y,
                'zoom': self._zoom,
                'camera_distance': self._camera_distance,
            }

        def set_camera_state(self, state: Dict):
            """Restore a previously saved camera state."""
            if not state:
                return
            if 'rotation_x' in state:
                self._rotation_x = state['rotation_x']
            if 'rotation_y' in state:
                self._rotation_y = state['rotation_y']
            if 'pan_x' in state:
                self._pan_x = state['pan_x']
            if 'pan_y' in state:
                self._pan_y = state['pan_y']
            if 'zoom' in state:
                self._zoom = state['zoom']
            if 'camera_distance' in state:
                self._camera_distance = state['camera_distance']
            self.update()

else:
    # Fallback widget when OpenGL is not available
    class GLBViewerWidget(QWidget):
        modelLoaded = Signal(str)
        loadError = Signal(str)

        def __init__(self, parent=None):
            super().__init__(parent)
            layout = QVBoxLayout(self)
            label = QLabel("OpenGL not available.\nCannot display 3D models.")
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("color: #888; font-size: 14px;")
            layout.addWidget(label)
            self.setMinimumSize(400, 300)

        def set_model_data(self, model_data: Dict):
            self.loadError.emit("OpenGL not available")

        def load_model(self, glb_path: str) -> bool:
            self.loadError.emit("OpenGL not available")
            return False

        def toggle_wireframe(self):
            pass

        def reset_view(self):
            pass

        def get_camera_state(self) -> Optional[Dict]:
            return None

        def set_camera_state(self, state: Dict):
            pass


# ============================================================================
# GLB VIEWER DIALOG
# ============================================================================

class GLBViewerDialog(QDialog):
    """
    Modal dialog for viewing GLB/GLTF 3D models.

    Features:
    - Async model loading with loading indicator
    - Fullscreen 3D viewport with mouse controls
    - Control buttons for reset, wireframe toggle
    - Keyboard shortcuts (R=reset, W=wireframe, F=fullscreen, Esc=close)
    """

    def __init__(self, glb_path: str, parent=None):
        super().__init__(parent)

        self._glb_path = glb_path
        self._is_loading = False
        self._setup_ui()
        self._connect_signals()
        self._load_model_async()

    def _setup_ui(self):
        """Set up the dialog UI."""
        filename = os.path.basename(self._glb_path)
        self.setWindowTitle(f"3D Viewer - {filename}")
        self.setMinimumSize(800, 600)

        # Start maximized to fill the window
        self.showMaximized()
        self.setModal(True)

        # Apply dark theme
        self.setStyleSheet("""
            QDialog {
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
        self._viewer = GLBViewerWidget(self)
        self._viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._stacked.addWidget(self._viewer)

        layout.addWidget(self._stacked)

        # Control bar
        self._control_bar = QFrame()
        self._control_bar.setStyleSheet("background-color: #2a2e36; padding: 8px;")
        control_layout = QHBoxLayout(self._control_bar)
        control_layout.setContentsMargins(12, 8, 12, 8)

        # Controls label
        controls_label = QLabel("Controls: Left-drag=Rotate • Middle-drag=Pan • Scroll=Zoom • R=Reset • W=Wireframe • F=Fullscreen")
        control_layout.addWidget(controls_label)

        control_layout.addStretch()

        # Reset button
        self._reset_btn = QPushButton("Reset View (R)")
        self._reset_btn.setMinimumWidth(100)
        self._reset_btn.setEnabled(False)
        control_layout.addWidget(self._reset_btn)

        # Wireframe button
        self._wireframe_btn = QPushButton("Wireframe (W)")
        self._wireframe_btn.setMinimumWidth(100)
        self._wireframe_btn.setCheckable(True)
        self._wireframe_btn.setEnabled(False)
        control_layout.addWidget(self._wireframe_btn)

        # Fullscreen button
        self._fullscreen_btn = QPushButton("Fullscreen (F)")
        self._fullscreen_btn.setMinimumWidth(100)
        self._fullscreen_btn.setCheckable(True)
        control_layout.addWidget(self._fullscreen_btn)

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
        control_layout.addWidget(self._close_btn)

        layout.addWidget(self._control_bar)

    def _connect_signals(self):
        """Connect signals to slots."""
        self._reset_btn.clicked.connect(self._viewer.reset_view)
        self._wireframe_btn.clicked.connect(self._viewer.toggle_wireframe)
        self._fullscreen_btn.clicked.connect(self._toggle_fullscreen)
        self._close_btn.clicked.connect(self.close)

        self._viewer.loadError.connect(self._on_load_error)
        self._viewer.modelLoaded.connect(self._on_model_loaded)

    def _toggle_fullscreen(self):
        """Toggle fullscreen mode."""
        if self.isFullScreen():
            self.showMaximized()
            self._fullscreen_btn.setChecked(False)
        else:
            self.showFullScreen()
            self._fullscreen_btn.setChecked(True)

    def _load_model_async(self):
        """Load the model asynchronously."""
        if not OPENGL_AVAILABLE or not PYOPENGL_AVAILABLE:
            QMessageBox.warning(
                self,
                "OpenGL Not Available",
                "OpenGL is required to view 3D models.\n\n"
                "Please ensure PyOpenGL is installed:\n"
                "pip install PyOpenGL PyOpenGL_accelerate"
            )
            return

        try:
            import trimesh
        except ImportError:
            QMessageBox.warning(
                self,
                "Trimesh Not Available",
                "Trimesh is required to load 3D models.\n\n"
                "Please ensure trimesh is installed:\n"
                "pip install trimesh"
            )
            return

        # Show loading state
        self._is_loading = True
        self._stacked.setCurrentIndex(0)  # Show loading page
        self._loading_label.setText("Loading model...")
        self._loading_status.setText(os.path.basename(self._glb_path))

        # Create and start the worker
        self._loader = ModelLoaderWorker(self._glb_path)
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

        QMessageBox.critical(
            self,
            "Error Loading Model",
            f"Failed to load 3D model:\n\n{error_msg}"
        )

    def _on_model_loaded(self, path: str):
        """Handle successful model loading (from viewer signal)."""
        pass  # Handled by _on_load_finished for async loading

    def keyPressEvent(self, event: QKeyEvent):
        """Handle dialog-level keyboard events."""
        if event.key() == Qt.Key_Escape:
            if self.isFullScreen():
                self.showMaximized()
                self._fullscreen_btn.setChecked(False)
            else:
                self.close()
        elif event.key() == Qt.Key_F:
            self._toggle_fullscreen()
        else:
            # Pass to viewer
            self._viewer.keyPressEvent(event)
