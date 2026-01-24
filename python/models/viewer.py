"""
Enhanced 3D Model Viewer for Luma Tools.

Provides an interactive 3D viewer with support for:
- Textured meshes (GLB, FBX, OBJ, USD, GLTF)
- Skeleton/bone visualization
- Animation playback with full transport controls
- Cross-platform (Windows/Mac) support

Uses QOpenGLWidget for rendering with mouse controls for rotation, pan, and zoom.
"""

import os
import sys
import math
from typing import Optional, Dict, List, Tuple
from enum import Enum

import numpy as np

from PySide6.QtCore import Qt, Signal, QPoint, QTimer, QRunnable, QObject, QThreadPool
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QWidget,
    QLabel, QFrame, QSizePolicy, QMessageBox, QStackedWidget,
    QSlider, QComboBox, QCheckBox
)
from PySide6.QtGui import QColor, QMouseEvent, QWheelEvent, QKeyEvent, QImage, QPixmap

try:
    from PySide6.QtOpenGLWidgets import QOpenGLWidget
    from PySide6.QtGui import QSurfaceFormat, QOpenGLContext
    OPENGL_AVAILABLE = True
except ImportError:
    OPENGL_AVAILABLE = False

try:
    from OpenGL.GL import *
    from OpenGL.GLU import *
    PYOPENGL_AVAILABLE = True
except ImportError:
    PYOPENGL_AVAILABLE = False

# Import model loader
try:
    from models.loader import (
        ModelData, MeshData, Skeleton, Bone, Animation,
        load_model, interpolate_bone_animation, compose_transform,
        quaternion_to_matrix, ASSIMP_AVAILABLE
    )
    MODEL_LOADER_AVAILABLE = True
except ImportError:
    MODEL_LOADER_AVAILABLE = False
    ASSIMP_AVAILABLE = False

# Import animation controller (extracted for better organization)
from models.animation_controller import AnimationController, AnimationTransportBar


# ============================================================================
# VIEW MODE
# ============================================================================

class ViewMode(Enum):
    """Viewer display modes."""
    TEXTURED = "textured"
    SKELETON = "skeleton"
    WIREFRAME = "wireframe"


class ModelLoaderSignals(QObject):
    """Signals for the model loader worker."""
    finished = Signal(object)  # Emits ModelData
    error = Signal(str)
    progress = Signal(str)


class ModelLoaderWorker(QRunnable):
    """Background worker to load 3D models."""

    def __init__(self, model_path: str):
        super().__init__()
        self.model_path = model_path
        self.signals = ModelLoaderSignals()

    def run(self):
        """Load the model in background thread."""
        try:
            if not os.path.exists(self.model_path):
                self.signals.error.emit(f"File not found: {self.model_path}")
                return

            self.signals.progress.emit("Loading model file...")

            model_data = load_model(self.model_path)

            self.signals.progress.emit("Processing complete")
            self.signals.finished.emit(model_data)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.signals.error.emit(f"Error loading model: {e}")


# ============================================================================
# MODEL VIEWER WIDGET (OpenGL)
# ============================================================================

if OPENGL_AVAILABLE and PYOPENGL_AVAILABLE:
    class ModelViewerWidget(QOpenGLWidget):
        """
        Interactive 3D viewer widget for models.

        Features:
        - Textured mesh rendering
        - Skeleton/bone visualization
        - Animation playback
        - Arcball rotation, pan, and zoom
        """

        modelLoaded = Signal(str)
        loadError = Signal(str)

        # Colors for skeleton rendering
        JOINT_COLOR = (1.0, 0.6, 0.0, 1.0)  # Orange
        BONE_COLOR = (0.9, 0.9, 0.9, 1.0)   # White
        ROOT_JOINT_COLOR = (0.0, 1.0, 0.5, 1.0)  # Green

        def __init__(self, parent=None):
            super().__init__(parent)

            # Model data
            self._model_data: Optional[ModelData] = None
            self._textures: Dict[str, int] = {}  # texture_path -> OpenGL texture ID

            # View mode
            self._view_mode = ViewMode.TEXTURED

            # Camera state
            self._rotation_x = 30.0
            self._rotation_y = 45.0
            self._pan_x = 0.0
            self._pan_y = 0.0
            self._zoom = 1.0
            self._camera_distance = 3.0
            self._scene_center = np.array([0.0, 0.0, 0.0])
            self._scene_radius = 1.0

            # Mouse tracking
            self._last_mouse_pos = QPoint()
            self._mouse_buttons = Qt.NoButton

            # Rendering options
            self._show_grid = True

            # Animation
            self._bone_transforms: Dict[str, np.ndarray] = {}

            # OpenGL state
            self._initialized = False

            # Set minimum size
            self.setMinimumSize(400, 300)
            self.setMouseTracking(True)
            self.setFocusPolicy(Qt.StrongFocus)

        def set_model_data(self, model_data: ModelData):
            """Set loaded model data."""
            self._model_data = model_data

            if model_data:
                # Center horizontally but ground vertically
                # Use geometric center for X and Z, but use min Y (feet) for grounding
                center = model_data.center.copy()
                center[1] = model_data.bounds_min[1]  # Ground the model on Y=0

                self._scene_center = center
                self._scene_radius = max(model_data.radius, 0.1)
                self._reset_camera()

                # Load textures
                self._load_textures()

            self.update()

            if model_data:
                self.modelLoaded.emit(model_data.path)

        def set_view_mode(self, mode: ViewMode):
            """Set the view mode."""
            self._view_mode = mode
            self.update()

        def set_bone_transforms(self, transforms: Dict[str, np.ndarray]):
            """Set bone transforms for animation."""
            self._bone_transforms = transforms
            self.update()

        def _load_textures(self):
            """Load textures into OpenGL."""
            if not self._model_data or not self._initialized:
                return

            self.makeCurrent()

            # Clear old textures
            for tex_id in self._textures.values():
                glDeleteTextures([tex_id])
            self._textures.clear()

            # Load embedded textures
            for name, data in self._model_data.textures.items():
                try:
                    tex_id = self._create_texture_from_data(data)
                    if tex_id:
                        self._textures[name] = tex_id
                except Exception as e:
                    print(f"Error loading embedded texture {name}: {e}")

            # Load external textures from materials
            for mat in self._model_data.materials:
                if mat.diffuse_texture and mat.diffuse_texture not in self._textures:
                    try:
                        tex_id = self._create_texture_from_file(mat.diffuse_texture)
                        if tex_id:
                            self._textures[mat.diffuse_texture] = tex_id
                    except Exception as e:
                        print(f"Error loading texture {mat.diffuse_texture}: {e}")

        def _create_texture_from_data(self, data: bytes) -> Optional[int]:
            """Create OpenGL texture from image data."""
            try:
                from PIL import Image
                import io

                img = Image.open(io.BytesIO(data))
                img = img.convert('RGBA')
                img_data = np.array(img, dtype=np.uint8)

                return self._upload_texture(img_data, img.width, img.height)
            except Exception as e:
                print(f"Error creating texture from data: {e}")
                return None

        def _create_texture_from_file(self, path: str) -> Optional[int]:
            """Create OpenGL texture from file."""
            if not os.path.exists(path):
                return None

            try:
                from PIL import Image

                img = Image.open(path)
                img = img.convert('RGBA')
                img_data = np.array(img, dtype=np.uint8)

                return self._upload_texture(img_data, img.width, img.height)
            except Exception as e:
                print(f"Error loading texture file {path}: {e}")
                return None

        def _upload_texture(self, data: np.ndarray, width: int, height: int) -> int:
            """Upload texture data to OpenGL."""
            tex_id = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, tex_id)

            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0,
                        GL_RGBA, GL_UNSIGNED_BYTE, data)
            glGenerateMipmap(GL_TEXTURE_2D)

            return tex_id

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
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

            glShadeModel(GL_SMOOTH)

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

            # Load textures if model is already set
            if self._model_data:
                self._load_textures()

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

            if not self._model_data:
                return

            # Render based on view mode
            if self._view_mode == ViewMode.SKELETON:
                self._draw_skeleton()
            elif self._view_mode == ViewMode.WIREFRAME:
                glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
                glEnable(GL_LIGHTING)
                self._draw_meshes()
                glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
            else:  # TEXTURED
                glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
                glEnable(GL_LIGHTING)
                self._draw_meshes()

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
                glVertex3f(i * step, 0, -grid_size)
                glVertex3f(i * step, 0, grid_size)
                glVertex3f(-grid_size, 0, i * step)
                glVertex3f(grid_size, 0, i * step)
            glEnd()

            glEnable(GL_LIGHTING)

        def _draw_meshes(self):
            """Draw all meshes."""
            if not self._model_data:
                return

            for mesh in self._model_data.meshes:
                self._draw_mesh(mesh)

        def _draw_mesh(self, mesh: MeshData):
            """Draw a single mesh with materials and textures."""
            vertices = mesh.vertices
            normals = mesh.normals
            faces = mesh.faces
            uvs = mesh.uvs

            if len(vertices) == 0 or len(faces) == 0:
                return

            # Get material
            material = None
            if self._model_data and 0 <= mesh.material_index < len(self._model_data.materials):
                material = self._model_data.materials[mesh.material_index]

            # Bind texture if available
            has_texture = False
            if material and material.diffuse_texture:
                tex_id = self._textures.get(material.diffuse_texture)
                if tex_id:
                    glEnable(GL_TEXTURE_2D)
                    glBindTexture(GL_TEXTURE_2D, tex_id)
                    has_texture = True

            # Set material color
            if material:
                glColor4f(*material.diffuse_color)
            else:
                glColor4f(0.7, 0.7, 0.7, 1.0)

            # Draw with vertex arrays
            glEnableClientState(GL_VERTEX_ARRAY)
            glEnableClientState(GL_NORMAL_ARRAY)

            glVertexPointer(3, GL_FLOAT, 0, vertices)
            glNormalPointer(GL_FLOAT, 0, normals)

            if has_texture and uvs is not None and len(uvs) > 0:
                glEnableClientState(GL_TEXTURE_COORD_ARRAY)
                glTexCoordPointer(2, GL_FLOAT, 0, uvs)

            # Use vertex colors if available and no texture
            if not has_texture and mesh.colors is not None:
                glEnableClientState(GL_COLOR_ARRAY)
                color_data = np.ascontiguousarray(mesh.colors[:, :3], dtype=np.float32)
                glColorPointer(3, GL_FLOAT, 0, color_data)

            indices = faces.flatten().astype(np.uint32)
            glDrawElements(GL_TRIANGLES, len(indices), GL_UNSIGNED_INT, indices)

            # Cleanup
            glDisableClientState(GL_VERTEX_ARRAY)
            glDisableClientState(GL_NORMAL_ARRAY)
            glDisableClientState(GL_TEXTURE_COORD_ARRAY)
            glDisableClientState(GL_COLOR_ARRAY)

            if has_texture:
                glDisable(GL_TEXTURE_2D)

        def _draw_skeleton(self):
            """Draw the skeleton as joints and bones."""
            if not self._model_data or not self._model_data.skeleton:
                # If no skeleton, draw meshes in wireframe
                glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
                glColor4f(0.5, 0.5, 0.5, 0.5)
                self._draw_meshes()
                glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
                return

            skeleton = self._model_data.skeleton
            glDisable(GL_LIGHTING)

            # Calculate world positions for all bones
            bone_positions = {}
            for bone in skeleton.bones:
                # Get animated transform if available, otherwise use bind pose
                if bone.name in self._bone_transforms:
                    transform = self._bone_transforms[bone.name]
                else:
                    transform = bone.local_transform

                # Get world position (translation component)
                pos = np.array([transform[0, 3], transform[1, 3], transform[2, 3]])
                bone_positions[bone.name] = pos

            # Draw bones (lines connecting joints)
            glLineWidth(3.0)
            glBegin(GL_LINES)
            glColor4f(*self.BONE_COLOR)

            for bone in skeleton.bones:
                if bone.parent_index >= 0:
                    parent = skeleton.bones[bone.parent_index]
                    if bone.name in bone_positions and parent.name in bone_positions:
                        p1 = bone_positions[parent.name]
                        p2 = bone_positions[bone.name]
                        glVertex3f(*p1)
                        glVertex3f(*p2)
            glEnd()

            # Draw joints (spheres)
            joint_radius = self._scene_radius * 0.02

            for bone in skeleton.bones:
                if bone.name not in bone_positions:
                    continue

                pos = bone_positions[bone.name]

                # Root bones are green, others are orange
                if bone.parent_index < 0:
                    glColor4f(*self.ROOT_JOINT_COLOR)
                else:
                    glColor4f(*self.JOINT_COLOR)

                glPushMatrix()
                glTranslatef(*pos)
                self._draw_sphere(joint_radius, 8, 8)
                glPopMatrix()

            glLineWidth(1.0)
            glEnable(GL_LIGHTING)

        def _draw_sphere(self, radius: float, slices: int, stacks: int):
            """Draw a simple sphere using triangle strips."""
            for i in range(stacks):
                lat0 = math.pi * (-0.5 + float(i) / stacks)
                z0 = math.sin(lat0)
                zr0 = math.cos(lat0)

                lat1 = math.pi * (-0.5 + float(i + 1) / stacks)
                z1 = math.sin(lat1)
                zr1 = math.cos(lat1)

                glBegin(GL_QUAD_STRIP)
                for j in range(slices + 1):
                    lng = 2 * math.pi * float(j) / slices
                    x = math.cos(lng)
                    y = math.sin(lng)

                    glNormal3f(x * zr0, y * zr0, z0)
                    glVertex3f(x * zr0 * radius, y * zr0 * radius, z0 * radius)

                    glNormal3f(x * zr1, y * zr1, z1)
                    glVertex3f(x * zr1 * radius, y * zr1 * radius, z1 * radius)
                glEnd()

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
                sensitivity = 0.5
                self._rotation_y += dx * sensitivity
                self._rotation_x += dy * sensitivity
                self._rotation_x = max(-90, min(90, self._rotation_x))

            elif self._mouse_buttons & Qt.MiddleButton:
                sensitivity = self._scene_radius * 0.005
                self._pan_x -= dx * sensitivity
                self._pan_y += dy * sensitivity

            elif self._mouse_buttons & Qt.RightButton:
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
            elif event.key() == Qt.Key_G:
                self._show_grid = not self._show_grid
                self.update()
            elif event.key() == Qt.Key_Escape:
                parent = self.parent()
                while parent:
                    if isinstance(parent, QDialog):
                        parent.close()
                        break
                    parent = parent.parent()
            else:
                super().keyPressEvent(event)

        def toggle_grid(self):
            """Toggle grid visibility."""
            self._show_grid = not self._show_grid
            self.update()

        def reset_view(self):
            """Reset camera to default view."""
            self._reset_camera()

        def get_camera_state(self) -> Optional[Dict]:
            """Get the current camera state."""
            return {
                'rotation_x': self._rotation_x,
                'rotation_y': self._rotation_y,
                'pan_x': self._pan_x,
                'pan_y': self._pan_y,
                'zoom': self._zoom,
                'camera_distance': self._camera_distance,
            }

        def set_camera_state(self, state: Dict):
            """Restore a saved camera state."""
            if not state:
                return
            for key in ['rotation_x', 'rotation_y', 'pan_x', 'pan_y', 'zoom', 'camera_distance']:
                if key in state:
                    setattr(self, f'_{key}', state[key])
            self.update()

else:
    # Fallback when OpenGL not available
    class ModelViewerWidget(QWidget):
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

        def set_model_data(self, model_data): pass
        def set_view_mode(self, mode): pass
        def set_bone_transforms(self, transforms): pass
        def toggle_grid(self): pass
        def reset_view(self): pass
        def get_camera_state(self): return None
        def set_camera_state(self, state): pass


# ============================================================================
# MODEL VIEWER DIALOG
# ============================================================================

class ModelViewerDialog(QDialog):
    """
    Modal dialog for viewing 3D models.

    Features:
    - Async model loading
    - View mode toggle (Textured/Skeleton/Wireframe)
    - Animation playback controls
    - Camera controls
    """

    def __init__(self, model_path: str, parent=None):
        super().__init__(parent)

        self._model_path = model_path
        self._model_data: Optional[ModelData] = None
        self._animation_controller = AnimationController(self)

        self._setup_ui()
        self._connect_signals()
        self._load_model_async()

    def _setup_ui(self):
        """Set up the dialog UI."""
        filename = os.path.basename(self._model_path)
        self.setWindowTitle(f"3D Viewer - {filename}")
        self.setMinimumSize(900, 700)
        self.showMaximized()
        self.setModal(True)

        # Dark theme
        self.setStyleSheet("""
            QDialog { background-color: #1e1e22; }
            QPushButton {
                background-color: #3c414b;
                color: #e0e0e0;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #4a5160; }
            QPushButton:pressed { background-color: #2a2e36; }
            QPushButton:checked { background-color: #4a9eff; }
            QPushButton:disabled { background-color: #2a2e36; color: #666; }
            QLabel { color: #a0a0a0; font-size: 11px; }
            QComboBox {
                background-color: #3c414b;
                color: #e0e0e0;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Stacked widget for loading/viewer
        self._stacked = QStackedWidget()
        self._stacked.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Loading page
        self._loading_page = QWidget()
        loading_layout = QVBoxLayout(self._loading_page)
        loading_layout.setAlignment(Qt.AlignCenter)

        self._loading_label = QLabel("Loading model...")
        self._loading_label.setAlignment(Qt.AlignCenter)
        self._loading_label.setStyleSheet("color: #e0e0e0; font-size: 16px; font-weight: bold;")
        loading_layout.addWidget(self._loading_label)

        self._loading_status = QLabel("")
        self._loading_status.setAlignment(Qt.AlignCenter)
        loading_layout.addWidget(self._loading_status)

        self._stacked.addWidget(self._loading_page)

        # Viewer page
        self._viewer = ModelViewerWidget(self)
        self._viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._stacked.addWidget(self._viewer)

        layout.addWidget(self._stacked)

        # Animation bar (hidden by default)
        self._animation_bar = AnimationTransportBar(self._animation_controller)
        self._animation_bar.setStyleSheet("background-color: #252830;")
        self._animation_bar.hide()
        layout.addWidget(self._animation_bar)

        # Control bar
        self._control_bar = QFrame()
        self._control_bar.setStyleSheet("background-color: #2a2e36; padding: 8px;")
        control_layout = QHBoxLayout(self._control_bar)
        control_layout.setContentsMargins(12, 8, 12, 8)

        # View mode selector
        control_layout.addWidget(QLabel("View:"))
        self._view_combo = QComboBox()
        self._view_combo.addItems(["Textured", "Skeleton", "Wireframe"])
        self._view_combo.setMinimumWidth(100)
        control_layout.addWidget(self._view_combo)

        # Animation selector (hidden by default)
        self._anim_label = QLabel("Animation:")
        self._anim_label.hide()
        control_layout.addWidget(self._anim_label)

        self._anim_combo = QComboBox()
        self._anim_combo.setMinimumWidth(150)
        self._anim_combo.hide()
        control_layout.addWidget(self._anim_combo)

        control_layout.addSpacing(16)

        # Controls help
        controls_label = QLabel("Left=Rotate | Middle=Pan | Scroll=Zoom | R=Reset | G=Grid")
        control_layout.addWidget(controls_label)

        control_layout.addStretch()

        # Reset button
        self._reset_btn = QPushButton("Reset View (R)")
        self._reset_btn.setEnabled(False)
        control_layout.addWidget(self._reset_btn)

        # Fullscreen button
        self._fullscreen_btn = QPushButton("Fullscreen (F)")
        self._fullscreen_btn.setCheckable(True)
        control_layout.addWidget(self._fullscreen_btn)

        # Publish to AYON button
        self._publish_btn = QPushButton("Publish to AYON")
        self._publish_btn.setStyleSheet("""
            QPushButton { background-color: #10b981; color: white; }
            QPushButton:hover { background-color: #14ce94; }
            QPushButton:disabled { background-color: #3c414b; color: #6b6f78; }
        """)
        # Check if AYON is available and not in standalone mode
        try:
            from core.state_manager import get_app_state
            from ayon.service import AYON_AVAILABLE
            app_state = get_app_state()
            is_standalone = app_state.standalone_mode

            # Debug logging
            print(f"[AYON Publish Button] AYON_AVAILABLE={AYON_AVAILABLE}, standalone_mode={is_standalone}")

            if is_standalone or not AYON_AVAILABLE:
                self._publish_btn.setEnabled(False)
                if is_standalone:
                    self._publish_btn.setToolTip("AYON publishing is not available in standalone mode")
                else:
                    self._publish_btn.setToolTip("AYON is not available")
            else:
                self._publish_btn.setToolTip("Publish this 3D model to AYON")
        except Exception as e:
            print(f"[AYON Publish Button] Error checking availability: {e}")
            import traceback
            traceback.print_exc()
            self._publish_btn.setEnabled(False)
            self._publish_btn.setToolTip("AYON is not available")
        control_layout.addWidget(self._publish_btn)

        # Close button
        self._close_btn = QPushButton("Close")
        self._close_btn.setStyleSheet("""
            QPushButton { background-color: #4a9eff; color: white; }
            QPushButton:hover { background-color: #6ab0ff; }
        """)
        control_layout.addWidget(self._close_btn)

        layout.addWidget(self._control_bar)

    def _connect_signals(self):
        """Connect signals."""
        self._reset_btn.clicked.connect(self._viewer.reset_view)
        self._fullscreen_btn.clicked.connect(self._toggle_fullscreen)
        self._publish_btn.clicked.connect(self._publish_to_ayon)
        self._close_btn.clicked.connect(self.close)

        self._view_combo.currentTextChanged.connect(self._on_view_mode_changed)
        self._anim_combo.currentTextChanged.connect(self._on_animation_changed)

        self._animation_controller.time_changed.connect(self._on_animation_time_changed)

    def _toggle_fullscreen(self):
        """Toggle fullscreen mode."""
        if self.isFullScreen():
            self.showMaximized()
            self._fullscreen_btn.setChecked(False)
        else:
            self.showFullScreen()
            self._fullscreen_btn.setChecked(True)

    def _load_model_async(self):
        """Load model asynchronously."""
        if not MODEL_LOADER_AVAILABLE:
            self._on_load_error("Model loader not available. Install pyassimp.")
            return

        self._stacked.setCurrentIndex(0)
        self._loading_label.setText("Loading model...")
        self._loading_status.setText(os.path.basename(self._model_path))

        worker = ModelLoaderWorker(self._model_path)
        worker.signals.progress.connect(self._on_load_progress)
        worker.signals.finished.connect(self._on_load_finished)
        worker.signals.error.connect(self._on_load_error)

        QThreadPool.globalInstance().start(worker)

    def _on_load_progress(self, message: str):
        self._loading_status.setText(message)

    def _on_load_finished(self, model_data: ModelData):
        self._model_data = model_data
        self._viewer.set_model_data(model_data)

        # Set up animations if available
        if model_data.has_animations:
            self._animation_controller.set_animations(model_data.animations)
            self._anim_combo.clear()
            self._anim_combo.addItems(self._animation_controller.animation_names)
            self._anim_label.show()
            self._anim_combo.show()
            self._animation_bar.show()

        # Switch to viewer
        self._stacked.setCurrentIndex(1)
        self._reset_btn.setEnabled(True)

        print(f"Loaded 3D model: {model_data.path}")
        print(f"  Meshes: {len(model_data.meshes)}, Materials: {len(model_data.materials)}")
        print(f"  Skeleton: {model_data.has_skeleton}, Animations: {len(model_data.animations)}")

    def _on_load_error(self, error_msg: str):
        self._loading_label.setText("Error loading model")

        # Provide more helpful messages for specific errors
        ext = os.path.splitext(self._model_path)[1].lower()
        if ext == '.fbx' and ('NULL' in error_msg.upper() or 'null' in error_msg.lower()):
            # HyMotion and other motion-capture FBX files often fail to load
            display_msg = (
                "This FBX file format is not supported.\n"
                "Motion capture FBX files (e.g., from HyMotion) may use\n"
                "a format that cannot be parsed by available libraries."
            )
        elif 'skeleton-only' in error_msg.lower():
            display_msg = (
                "This FBX contains only skeleton/animation data.\n"
                "No viewable mesh geometry found."
            )
        else:
            # Truncate long error messages
            display_msg = error_msg if len(error_msg) < 200 else error_msg[:200] + "..."

        self._loading_status.setText(display_msg)
        self._loading_status.setStyleSheet("color: #ff6b6b; font-size: 12px;")

    def _on_view_mode_changed(self, text: str):
        mode_map = {
            "Textured": ViewMode.TEXTURED,
            "Skeleton": ViewMode.SKELETON,
            "Wireframe": ViewMode.WIREFRAME,
        }
        self._viewer.set_view_mode(mode_map.get(text, ViewMode.TEXTURED))

    def _on_animation_changed(self, name: str):
        self._animation_controller.set_animation(name)

    def _on_animation_time_changed(self, time_sec: float, normalized: float):
        transforms = self._animation_controller.get_bone_transforms()
        self._viewer.set_bone_transforms(transforms)

    def _publish_to_ayon(self):
        """Publish this 3D model to AYON."""
        try:
            from comfyui.ayon_publisher import publish_comfyui_asset_to_ayon

            # Get output_dir from model path
            output_dir = os.path.dirname(self._model_path)

            # Call the publisher
            success = publish_comfyui_asset_to_ayon(
                file_path=self._model_path,
                parent_widget=self,
                output_dir=output_dir
            )

            if success:
                print(f"Successfully published model to AYON: {self._model_path}")

        except Exception as e:
            import traceback
            traceback.print_exc()
            from dialog_helpers import show_error
            show_error("Publish Error", f"Failed to publish model to AYON:\n\n{str(e)}", self)

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard events."""
        if event.key() == Qt.Key_Escape:
            if self.isFullScreen():
                self.showMaximized()
                self._fullscreen_btn.setChecked(False)
            else:
                self.close()
        elif event.key() == Qt.Key_F:
            self._toggle_fullscreen()
        elif event.key() == Qt.Key_Space:
            self._animation_controller.toggle_play()
        else:
            self._viewer.keyPressEvent(event)


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def is_viewer_available() -> bool:
    """Check if the model viewer is available."""
    return OPENGL_AVAILABLE and PYOPENGL_AVAILABLE and MODEL_LOADER_AVAILABLE


def get_supported_extensions() -> set:
    """Get set of supported file extensions."""
    if MODEL_LOADER_AVAILABLE:
        from models.loader import SUPPORTED_EXTENSIONS
        return SUPPORTED_EXTENSIONS
    return {'.glb', '.gltf'}


def create_viewer_dialog(model_path: str, parent=None) -> QDialog:
    """Create a viewer dialog for the given model path."""
    return ModelViewerDialog(model_path, parent)
