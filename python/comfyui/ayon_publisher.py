"""
ComfyUI AYON Publisher for Luma Tools.

Handles publishing ComfyUI-generated images and 3D models to AYON.
Includes Phase 2 AYON integration with validators.
"""

import os
import logging
from typing import Optional, List, Tuple
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QCheckBox
)
from PySide6.QtCore import QThreadPool
from dialog_helpers import show_warning, show_error, show_info

logger = logging.getLogger(__name__)

# Module-level anchor for in-flight publish workers — keeps them alive even
# if the calling progress dialog is dropped early. Workers self-remove from
# this list when their result/error callback fires.
_active_publish_workers: List["object"] = []


# AYON product types offered for ComfyUI assets, in the order the dialog lists
# them. Shared so the batch publisher infers exactly what the dialog defaults to.
AYON_PRODUCT_TYPES = (
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
)

AYON_TASKS = ("lighting", "compositing", "fx", "lookdev", "animation")

# Suffixes stripped when deriving a product name from a filename
_PRODUCT_NAME_SUFFIXES = ('_000', '_001', '_002', '_view', '_export')


def infer_product_type(file_path: str) -> str:
    """Guess the AYON product type from a file extension."""
    from core.config import (
        IMAGE_EXTENSIONS,
        VIDEO_EXTENSIONS,
        AUDIO_EXTENSIONS,
        MODEL_EXTENSIONS,
    )
    ext = os.path.splitext(file_path)[1].lower()
    if ext in MODEL_EXTENSIONS:
        return "model"
    if ext in {'.abc', '.npz'}:
        return "pointcache"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "review"
    if ext in AUDIO_EXTENSIONS or ext == '.aiff':
        return "audio"
    return "image"


def infer_product_name(file_path: str) -> str:
    """Derive a product name from a filename, dropping generated suffixes."""
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    for suffix in _PRODUCT_NAME_SUFFIXES:
        if base_name.endswith(suffix):
            base_name = base_name[:-len(suffix)]
            break
    return base_name


def publish_asset_headless(
    file_path: str,
    app_state,
    product_type: str = None,
    product_name: str = None,
    variant: str = "",
    task: str = None,
    comment: str = "",
    use_farm: bool = False,
) -> Tuple[bool, str]:
    """Publish one asset to AYON with no UI at all.

    Safe to call from a worker thread — it creates no Qt widgets and shows no
    dialogs, which is what a batch publish needs. The interactive
    publish_comfyui_asset_to_ayon() collects the same values from a dialog and
    then does the same work.

    Returns:
        Tuple of (success, message). ``message`` explains the failure, or names
        what was published on success.
    """
    from ayon.service import (
        AYON_AVAILABLE,
        create_ayon_metadata_single_file,
        write_metadata_file,
        publish_to_ayon_local,
        convert_to_ayon_folder_path,
        build_ayon_metadata_filename,
    )

    if not AYON_AVAILABLE:
        return False, "AYON is not available or not configured"
    if getattr(app_state, 'standalone_mode', False):
        return False, "Publishing is not available in standalone mode"
    if not file_path or not os.path.isfile(file_path):
        return False, f"File not found: {file_path}"

    product_type = product_type or infer_product_type(file_path)
    product_name = product_name or infer_product_name(file_path)
    task = task or AYON_TASKS[0]

    if not product_name:
        return False, "Product name is empty"

    passed, validator_error = _run_publish_validators(
        file_path, product_type, product_name, variant, parent_widget=None
    )
    if not passed:
        return False, f"Validation failed: {validator_error}"

    full_product_name = f"{product_name}_{variant}" if variant else product_name
    folder_path = convert_to_ayon_folder_path(app_state.shotpath, app_state.jobname)
    render_dir = os.path.dirname(file_path)

    metadata = create_ayon_metadata_single_file(
        project_name=app_state.jobname,
        file_path=file_path,
        product_name=full_product_name,
        product_type=product_type,
        folder_path=folder_path,
        task=task,
        user=app_state.user,
        variant=variant or "",
        comment=comment or "",
    )

    metadata_filename = build_ayon_metadata_filename(full_product_name, prefix="comfyui")
    metadata_path = write_metadata_file(
        metadata, os.path.join(render_dir, metadata_filename)
    )
    if not metadata_path:
        return False, f"Could not write metadata next to {os.path.basename(file_path)}"

    if use_farm:
        from ayon.service import submit_ayon_publish_to_deadline
        job_id = submit_ayon_publish_to_deadline(
            project_name=app_state.jobname,
            render_name=full_product_name,
            render_file=os.path.basename(file_path),
            metadata_path=metadata_path,
            folder_path=folder_path,
            task=task,
            user=app_state.user,
            build_job_id=None,
        )
        if job_id:
            return True, f"Submitted to Deadline ({job_id})"
        return False, "Failed to submit publish job to Deadline"

    ok = publish_to_ayon_local(
        metadata_path=metadata_path,
        project_name=app_state.jobname,
        folder_path=folder_path,
        task=task,
        user=app_state.user,
    )
    if ok:
        return True, f"Published {full_product_name}"
    return False, "AYON publish command failed (see log)"


class ComfyUIAYONPublisher:
    """Headless batch publisher for gallery multi-select publishing.

    Deliberately UI-free so the gallery can run it on a worker thread. Options
    default to the same inference the interactive dialog uses, and may be
    overridden per batch.
    """

    def __init__(self, app_state, product_type: str = None, variant: str = "",
                 task: str = None, comment: str = "", use_farm: bool = False):
        self.app_state = app_state
        self.product_type = product_type
        self.variant = variant
        self.task = task
        self.comment = comment
        self.use_farm = use_farm
        self.last_message = ""

    def publish_single_file(self, file_path: str) -> bool:
        """Publish one file. Returns True on success; see last_message for detail."""
        success, message = publish_asset_headless(
            file_path,
            self.app_state,
            product_type=self.product_type,
            variant=self.variant,
            task=self.task,
            comment=self.comment,
            use_farm=self.use_farm,
        )
        self.last_message = message
        level = logger.info if success else logger.warning
        level(f"[AYON Batch] {os.path.basename(file_path)}: {message}")
        return success


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
        logger.info(f"[AYON Publish] Validators not available: {e}")
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
        from core.state_manager import app_state

        if not AYON_AVAILABLE:
            show_warning(
                "AYON Not Available",
                "AYON publishing requires AYON to be properly configured.",
                parent_widget
            )
            return False


        if app_state.standalone_mode:
            show_warning(
                "Standalone Mode",
                "Publishing to AYON is not available in standalone mode.\n\n"
                "Please run the tool from within AYON context.",
                parent_widget
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

        # A cleared product name would produce an unnamed product and a
        # metadata file like "ayon_comfyui_.json"
        if not product_name:
            logger.warning("[AYON Publish] Aborted: product name is empty")
            from dialog_helpers import show_warning
            show_warning(
                "Publish to AYON",
                "Product name cannot be empty.",
                parent=parent_widget,
            )
            return False

        # Run validators before proceeding (Phase 2 AYON integration)
        logger.info("[AYON Publish] Running validators...")
        validators_passed, validator_error = _run_publish_validators(
            file_path, product_type, product_name, variant, parent_widget
        )

        if not validators_passed:
            show_warning(
                "Validation Failed",
                f"Publishing cannot proceed due to validation errors:\n\n{validator_error}",
                parent_widget
            )
            return False

        # Build full product name with variant (AYON standard)
        if variant:
            full_product_name = f"{product_name}_{variant}"
        else:
            full_product_name = product_name

        logger.info(f"[AYON Publish] Product Type: {product_type}, Product Name: {full_product_name}, Task: {task}")

        # Get folder path
        logger.info("[AYON Publish] Building AYON paths...")
        folder_path = convert_to_ayon_folder_path(app_state.shotpath, app_state.jobname)

        # Get render directory for metadata output
        render_dir = os.path.dirname(file_path)

        # Use the single-file metadata function (handles FBX, GLB, images, etc.)
        logger.info("[AYON Publish] Creating metadata...")
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
        logger.info("[AYON Publish] Writing metadata file...")
        from ayon.service import build_ayon_metadata_filename
        metadata_filename = build_ayon_metadata_filename(full_product_name, prefix="comfyui")
        metadata_path = os.path.join(render_dir, metadata_filename)

        logger.info(f"[AYON Publish] Writing metadata to: {metadata_path}")
        metadata_path = write_metadata_file(metadata, metadata_path)

        if not metadata_path:
            show_error(
                "Metadata Error",
                "Could not write the AYON metadata file next to the item. "
                "The folder may be read-only, full, or temporarily unreachable "
                "on the network — check that you can write to it and try again.",
                parent_widget,
                detail=f"Target: {os.path.join(render_dir, metadata_filename)}",
            )
            return False

        # Publish
        success = False
        if use_farm:
            # Submit to Deadline
            logger.info("[AYON Publish] Submitting to Deadline farm...")
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
                logger.info(f"[AYON Publish] Successfully submitted to Deadline: {job_id}")
                show_info(
                    "Published to Farm",
                    f"Successfully submitted to Deadline.\n\n"
                    f"Job ID: {job_id}\n"
                    f"Product Type: {product_type}\n"
                    f"Product: {full_product_name}\n"
                    f"Task: {task}",
                    parent_widget
                )
                success = True
            else:
                logger.error("[AYON Publish] Failed to submit to Deadline")
                show_error("Publish Failed", "Failed to submit job to Deadline.", parent_widget)
        else:
            # Publish locally using Worker thread to avoid freezing UI
            logger.info("[AYON Publish] Publishing to AYON locally...")

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
                    logger.info("[AYON Publish] Successfully published to AYON")
                    show_info(
                        "Published Successfully",
                        f"Successfully published to AYON.\n\n"
                        f"Product Type: {product_type}\n"
                        f"Product: {full_product_name}\n"
                        f"Task: {task}",
                        parent_widget
                    )
                else:
                    logger.error("[AYON Publish] Failed to publish to AYON")
                    show_error(
                        "Publish Failed",
                        "AYON publish command failed. Check logs for details.",
                        parent_widget
                    )

            def on_publish_error(error_tuple):
                """Handle publish error."""
                progress_dialog.close()
                error_msg = str(error_tuple[1]) if len(error_tuple) > 1 else "Unknown error"
                logger.error(f"[AYON Publish] Error: {error_msg}")
                show_error(
                    "Publish Error",
                    "Could not publish to AYON. Check that the AYON server is "
                    "reachable and the folder/task still exists.",
                    parent_widget,
                    detail=error_msg,
                )

            # Create and start worker.
            # Anchor the worker on a module-level list (not just the dialog)
            # so it survives even if the caller drops its dialog reference.
            from ui_components import Worker
            worker = Worker(publish_worker)
            _active_publish_workers.append(worker)

            def _release_worker(*_args, **_kwargs):
                try:
                    _active_publish_workers.remove(worker)
                except ValueError:
                    pass

            worker.signals.result.connect(on_publish_complete)
            worker.signals.error.connect(on_publish_error)
            worker.signals.result.connect(_release_worker)
            worker.signals.error.connect(_release_worker)
            progress_dialog._worker = worker  # also anchor on the dialog for legacy callers
            QThreadPool.globalInstance().start(worker)

            # Return True to indicate publish was initiated
            # (actual result will be shown in callbacks)
            success = True

        return success

    except Exception as e:
        logger.error(f"[AYON Publish] Failed to publish to AYON: {e}", exc_info=True)
        show_error(
            "Publish Error",
            "Could not publish to AYON. Check that the AYON server is reachable "
            "and the folder/task still exists.",
            parent_widget,
            detail=f"{type(e).__name__}: {e}",
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

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # File info
        info_label = QLabel(f"<b>File:</b> {filename}")
        layout.addWidget(info_label)

        # Product Type selector (AYON standard)
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Product Type:"))
        self.product_type_combo = QComboBox()

        # Standard AYON product types (same as Houdini/Blender).
        # Shared with the headless batch publisher so both stay in step.
        self.product_type_combo.addItems(list(AYON_PRODUCT_TYPES))

        default_type = infer_product_type(self.file_path)
        idx = self.product_type_combo.findText(default_type)
        if idx >= 0:
            self.product_type_combo.setCurrentIndex(idx)

        type_layout.addWidget(self.product_type_combo)
        layout.addLayout(type_layout)

        # Product name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Product Name:"))
        self.product_name_edit = QLineEdit()
        # Auto-populate from filename (shared with the batch publisher)
        self.product_name_edit.setText(infer_product_name(self.file_path))
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
        self.task_combo.addItems(list(AYON_TASKS))
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

        self.publish_btn = QPushButton("Publish to AYON")
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
