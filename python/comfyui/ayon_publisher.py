"""
ComfyUI AYON Publisher for Luma Tools.

Handles publishing ComfyUI-generated images and 3D models to AYON.
Includes Phase 2 AYON integration with validators.
"""

import os
from typing import Optional, List, Tuple
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QCheckBox, QMessageBox
)
from PySide6.QtCore import QThreadPool

from resources.ui.workers import Worker


def _run_publish_validators(
    file_path: str,
    product_type: str,
    product_name: str,
    variant: str,
    parent_widget=None
) -> Tuple[bool, str]:
    """
    Run AYON validators before publishing.

    Args:
        file_path: Path to file being published
        product_type: AYON product type (model, image, etc.)
        product_name: Product name
        variant: Optional variant
        parent_widget: Parent widget for error dialogs

    Returns:
        Tuple of (passed, error_message)
    """
    try:
        from ayon.validators import run_validators, InstanceData

        instance = InstanceData(
            source_file=file_path,
            product_type=product_type,
            product_name=product_name,
            variant=variant,
        )

        all_passed, results = run_validators(instance)

        if not all_passed:
            # Collect failure messages
            failures = [r for r in results if not r.passed]
            error_lines = []
            for failure in failures:
                error_lines.append(f"• {failure.validator}: {failure.message}")
                if failure.details:
                    # Indent details
                    error_lines.append(f"  {failure.details[:200]}")

            error_msg = "\n".join(error_lines)
            return False, error_msg

        return True, ""

    except ImportError as e:
        # Validators not available - log but continue (graceful degradation)
        print(f"[AYON Publish] Validators not available: {e}")
        return True, ""


def publish_comfyui_asset_to_ayon(
    file_path: str,
    parent_widget=None,
    output_dir: Optional[str] = None
) -> bool:
    """
    Publish a ComfyUI-generated asset (image or 3D model) to AYON.

    Shows a dialog to collect publishing metadata from the user.
    Runs validators before publishing to catch errors early.

    Args:
        file_path: Path to the file to publish
        parent_widget: Parent widget for the dialog
        output_dir: Optional output directory (for metadata lookup)

    Returns:
        bool: True if successfully published, False otherwise
    """
    try:
        from ayon.service import (
            AYON_AVAILABLE,
            create_ayon_metadata_single_file,
            write_metadata_file,
            publish_to_ayon_local,
            convert_to_ayon_folder_path
        )
        from core.state_manager import get_app_state

        if not AYON_AVAILABLE:
            QMessageBox.warning(
                parent_widget,
                "AYON Not Available",
                "AYON publishing requires AYON to be properly configured."
            )
            return False

        app_state = get_app_state()

        if app_state.standalone_mode:
            QMessageBox.warning(
                parent_widget,
                "Standalone Mode",
                "Publishing to AYON is not available in standalone mode.\n\n"
                "Please run the tool from within AYON context."
            )
            return False

        # Show publish dialog to get metadata
        dialog = ComfyUIPublishDialog(file_path, app_state, parent_widget)
        if dialog.exec() != QDialog.Accepted:
            return False  # User cancelled

        # Get publish options from dialog
        product_type = dialog.get_product_type()
        product_name = dialog.get_product_name()
        variant = dialog.get_variant()
        task = dialog.get_task()
        use_farm = dialog.get_use_farm()
        comment = dialog.get_comment()

        # Run validators before proceeding (Phase 2 AYON integration)
        print("[AYON Publish] Running validators...")
        validators_passed, validator_error = _run_publish_validators(
            file_path, product_type, product_name, variant, parent_widget
        )

        if not validators_passed:
            QMessageBox.warning(
                parent_widget,
                "Validation Failed",
                f"Publishing cannot proceed due to validation errors:\n\n{validator_error}"
            )
            return False

        # Build full product name with variant (AYON standard)
        if variant:
            full_product_name = f"{product_name}_{variant}"
        else:
            full_product_name = product_name

        print(f"[AYON Publish] Product Type: {product_type}, Product Name: {full_product_name}, Task: {task}")

        # Get folder path
        print("[AYON Publish] Building AYON paths...")
        folder_path = convert_to_ayon_folder_path(app_state.shotpath, app_state.jobname)

        # Get render directory for metadata output
        render_dir = os.path.dirname(file_path)

        # Use the single-file metadata function (handles FBX, GLB, images, etc.)
        print("[AYON Publish] Creating metadata...")
        metadata = create_ayon_metadata_single_file(
            project_name=app_state.jobname,
            file_path=file_path,
            product_name=full_product_name,
            product_type=product_type,
            folder_path=folder_path,
            task=task,
            user=app_state.user,
            variant=variant if variant else "",
            comment=comment if comment else ""
        )

        # Write metadata file next to the source file
        print("[AYON Publish] Writing metadata file...")
        metadata_filename = f"ayon_comfyui_{full_product_name}.json"
        metadata_path = os.path.join(render_dir, metadata_filename)

        print(f"[AYON Publish] Writing metadata to: {metadata_path}")
        metadata_path = write_metadata_file(metadata, metadata_path)

        if not metadata_path:
            QMessageBox.critical(
                parent_widget,
                "Metadata Error",
                "Failed to write AYON metadata file."
            )
            return False

        # Publish
        success = False
        if use_farm:
            # Submit to Deadline
            print("[AYON Publish] Submitting to Deadline farm...")
            from ayon.service import submit_ayon_publish_to_deadline

            filename = os.path.basename(file_path)
            job_id = submit_ayon_publish_to_deadline(
                project_name=app_state.jobname,
                render_name=full_product_name,
                render_file=filename,
                metadata_path=metadata_path,
                folder_path=folder_path,
                task=task,
                user=app_state.user,
                build_job_id=None
            )

            if job_id:
                print(f"[AYON Publish] Successfully submitted to Deadline: {job_id}")
                QMessageBox.information(
                    parent_widget,
                    "Published to Farm",
                    f"Successfully submitted to Deadline.\n\n"
                    f"Job ID: {job_id}\n"
                    f"Product Type: {product_type}\n"
                    f"Product: {full_product_name}\n"
                    f"Task: {task}"
                )
                success = True
            else:
                print("[AYON Publish] Failed to submit to Deadline")
                QMessageBox.critical(
                    parent_widget,
                    "Publish Failed",
                    "Failed to submit job to Deadline."
                )
        else:
            # Publish locally using Worker thread to avoid freezing UI
            print("[AYON Publish] Publishing to AYON locally...")

            # Create a progress dialog to show while publishing
            from PySide6.QtWidgets import QProgressDialog
            from PySide6.QtCore import Qt

            progress_dialog = QProgressDialog(
                "Publishing to AYON...\n\nThis may take a moment.",
                None,  # No cancel button
                0, 0,  # Indeterminate progress
                parent_widget
            )
            progress_dialog.setWindowTitle("Publishing")
            progress_dialog.setWindowModality(Qt.WindowModal)
            progress_dialog.setMinimumDuration(0)
            progress_dialog.setValue(0)
            progress_dialog.show()

            # Variables to capture result
            publish_result = {"success": False, "error": None}

            def publish_worker():
                """Worker function to publish to AYON."""
                try:
                    result = publish_to_ayon_local(
                        metadata_path=metadata_path,
                        project_name=app_state.jobname,
                        folder_path=folder_path,
                        task=task,
                        user=app_state.user
                    )
                    publish_result["success"] = result
                    return result
                except Exception as e:
                    publish_result["error"] = str(e)
                    raise

            def on_publish_complete(result):
                """Handle successful publish completion."""
                progress_dialog.close()

                if result:
                    print("[AYON Publish] Successfully published to AYON")
                    QMessageBox.information(
                        parent_widget,
                        "Published Successfully",
                        f"Successfully published to AYON.\n\n"
                        f"Product Type: {product_type}\n"
                        f"Product: {full_product_name}\n"
                        f"Task: {task}"
                    )
                else:
                    print("[AYON Publish] Failed to publish to AYON")
                    QMessageBox.critical(
                        parent_widget,
                        "Publish Failed",
                        "AYON publish command failed. Check logs for details."
                    )

            def on_publish_error(error_tuple):
                """Handle publish error."""
                progress_dialog.close()
                error_msg = str(error_tuple[1]) if len(error_tuple) > 1 else "Unknown error"
                print(f"[AYON Publish] Error: {error_msg}")
                QMessageBox.critical(
                    parent_widget,
                    "Publish Error",
                    f"Failed to publish to AYON:\n\n{error_msg}"
                )

            # Create and start worker
            worker = Worker(publish_worker)
            worker.signals.result.connect(on_publish_complete)
            worker.signals.error.connect(on_publish_error)
            QThreadPool.globalInstance().start(worker)

            # Return True to indicate publish was initiated
            # (actual result will be shown in callbacks)
            success = True

        return success

    except Exception as e:
        import traceback
        traceback.print_exc()
        QMessageBox.critical(
            parent_widget,
            "Publish Error",
            f"Failed to publish to AYON:\n\n{str(e)}"
        )
        return False


class ComfyUIPublishDialog(QDialog):
    """Dialog for collecting AYON publish metadata for ComfyUI assets."""

    def __init__(self, file_path: str, app_state, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.app_state = app_state
        self._setup_ui()

    def _setup_ui(self):
        """Set up the dialog UI."""
        filename = os.path.basename(self.file_path)
        self.setWindowTitle(f"Publish to AYON - {filename}")
        self.setMinimumWidth(450)
        self.setModal(True)

        # Apply dark theme
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e22;
            }
            QLabel {
                color: #e0e0e0;
                font-size: 12px;
            }
            QLineEdit, QComboBox {
                background-color: #2c313a;
                color: #e0e0e0;
                border: 1px solid #3c414b;
                border-radius: 4px;
                padding: 6px;
                font-size: 12px;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #4a9eff;
            }
            QCheckBox {
                color: #e0e0e0;
                font-size: 12px;
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
            QPushButton#publishButton {
                background-color: #10b981;
                color: white;
            }
            QPushButton#publishButton:hover {
                background-color: #14ce94;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # File info
        info_label = QLabel(f"<b>File:</b> {filename}")
        layout.addWidget(info_label)

        # Product Type selector (AYON standard)
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Product Type:"))
        self.product_type_combo = QComboBox()

        # Standard AYON product types (same as Houdini/Blender)
        product_types = [
            "model",        # 3D models/geometry
            "rig",          # Character rigs
            "look",         # Materials/shading
            "animation",    # Animation caches
            "pointcache",   # Alembic/USD caches
            "camera",       # Camera exports
            "image",        # Still images
            "render",       # Rendered images/sequences
            "plate",        # Input plates
            "review",       # Preview videos/turntables
            "audio",        # Audio files
        ]
        self.product_type_combo.addItems(product_types)

        # Auto-detect type from file extension
        ext = os.path.splitext(filename)[1].lower()
        default_type = "image"  # Default
        if ext in ['.glb', '.gltf', '.obj', '.fbx', '.usd', '.usda', '.usdc', '.usdz']:
            default_type = "model"
        elif ext in ['.abc', '.npz']:
            default_type = "pointcache"
        elif ext in ['.png', '.jpg', '.jpeg', '.tif', '.tiff', '.exr']:
            default_type = "image"
        elif ext in ['.mp4', '.mov', '.avi']:
            default_type = "review"
        elif ext in ['.wav', '.mp3', '.aiff']:
            default_type = "audio"

        idx = self.product_type_combo.findText(default_type)
        if idx >= 0:
            self.product_type_combo.setCurrentIndex(idx)

        type_layout.addWidget(self.product_type_combo)
        layout.addLayout(type_layout)

        # Product name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Product Name:"))
        self.product_name_edit = QLineEdit()
        # Auto-populate from filename
        base_name = os.path.splitext(filename)[0]
        # Remove common suffixes
        for suffix in ['_000', '_001', '_002', '_view', '_export']:
            if base_name.endswith(suffix):
                base_name = base_name[:-len(suffix)]
        self.product_name_edit.setText(base_name)
        name_layout.addWidget(self.product_name_edit)
        layout.addLayout(name_layout)

        # Variant (optional)
        variant_layout = QHBoxLayout()
        variant_layout.addWidget(QLabel("Variant:"))
        self.variant_edit = QLineEdit()
        self.variant_edit.setPlaceholderText("Optional (e.g., highres, lowres)")
        variant_layout.addWidget(self.variant_edit)
        layout.addLayout(variant_layout)

        # Task selector
        task_layout = QHBoxLayout()
        task_layout.addWidget(QLabel("Task:"))
        self.task_combo = QComboBox()
        self.task_combo.addItems(["lighting", "compositing", "fx", "lookdev", "animation"])
        # Try to default to current task if available
        if hasattr(self.app_state, 'task') and self.app_state.task:
            idx = self.task_combo.findText(self.app_state.task.lower())
            if idx >= 0:
                self.task_combo.setCurrentIndex(idx)
        task_layout.addWidget(self.task_combo)
        layout.addLayout(task_layout)

        # Comment
        comment_layout = QHBoxLayout()
        comment_layout.addWidget(QLabel("Comment:"))
        self.comment_edit = QLineEdit()
        self.comment_edit.setPlaceholderText("Optional comment...")
        comment_layout.addWidget(self.comment_edit)
        layout.addLayout(comment_layout)

        # Use farm checkbox
        self.use_farm_check = QCheckBox("Publish on Deadline farm")
        self.use_farm_check.setChecked(False)  # Default to local
        layout.addWidget(self.use_farm_check)

        # Shot/project info
        info_text = f"<i>Project: {self.app_state.jobname}<br>"
        if hasattr(self.app_state, 'shot') and self.app_state.shot:
            info_text += f"Shot: {self.app_state.shot}<br>"
        info_text += f"User: {self.app_state.user}<br><br>"
        info_text += "Product types follow AYON standards (Houdini/Blender/etc.)</i>"
        info_label2 = QLabel(info_text)
        layout.addWidget(info_label2)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        self.publish_btn = QPushButton("Publish")
        self.publish_btn.setObjectName("publishButton")
        self.publish_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.publish_btn)

        layout.addLayout(button_layout)

    def get_product_type(self) -> str:
        """Get the selected product type."""
        return self.product_type_combo.currentText()

    def get_product_name(self) -> str:
        """Get the product name entered by the user."""
        return self.product_name_edit.text().strip()

    def get_variant(self) -> str:
        """Get the optional variant."""
        return self.variant_edit.text().strip()

    def get_task(self) -> str:
        """Get the selected task."""
        return self.task_combo.currentText()

    def get_use_farm(self) -> bool:
        """Get whether to use farm publishing."""
        return self.use_farm_check.isChecked()

    def get_comment(self) -> str:
        """Get the optional comment."""
        return self.comment_edit.text().strip()
