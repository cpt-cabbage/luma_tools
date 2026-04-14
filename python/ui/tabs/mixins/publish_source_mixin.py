"""
Publish Source Mixin for tabs that can load renders from AYON published versions.

Provides programmatic creation of product/version combo boxes, AYON product
querying via background workers, and version-to-filesystem path resolution.

Usage:
    class MyTab(PublishSourceMixin, BaseTab):
        def initialize(self):
            self._init_publish_widgets(self.ui.MyVersionSpinBox)

        def _scan_publish_directory(self, staging_dir):
            from core.utils import scan_exr_sequences
            return scan_exr_sequences(staging_dir)
"""

import os
import logging

logger = logging.getLogger(__name__)


class PublishSourceMixin:
    """Mixin providing AYON publish source selection with product/version combos."""

    def _init_publish_widgets(self, anchor_widget):
        """Create AYON product/version combo boxes and insert into the layout.

        Finds the layout containing anchor_widget (typically the version spinbox)
        and inserts product label + combo, version label + combo after the
        source button.

        Args:
            anchor_widget: A widget in the target layout (e.g. the version spinbox).
        """
        from PySide6.QtWidgets import QComboBox, QLabel
        from PySide6.QtCore import QSize

        # Idempotency guard — if a future code path calls this twice, don't
        # duplicate the four widgets in the layout.
        if getattr(self, '_publish_product_combo', None) is not None:
            return

        self._publish_products = []
        self._publish_versions = []

        # Product combo
        self._publish_product_label = QLabel("Product:")
        self._publish_product_label.setVisible(False)

        self._publish_product_combo = QComboBox()
        self._publish_product_combo.setMinimumSize(QSize(200, 28))
        self._publish_product_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        self._publish_product_combo.setPlaceholderText("Select product...")
        self._publish_product_combo.setVisible(False)
        self._publish_product_combo.currentIndexChanged.connect(
            self._on_publish_product_changed
        )

        # Version combo
        self._publish_version_label = QLabel("Version:")
        self._publish_version_label.setVisible(False)

        self._publish_version_combo = QComboBox()
        self._publish_version_combo.setMinimumSize(QSize(80, 28))
        self._publish_version_combo.setPlaceholderText("Version...")
        self._publish_version_combo.setVisible(False)
        self._publish_version_combo.currentIndexChanged.connect(
            self._on_publish_version_changed
        )

        # Insert into layout containing the anchor widget
        layout = self._find_layout_containing(anchor_widget)
        if not layout:
            logger.warning("PublishSourceMixin: could not find layout for publish widgets")
            return

        # Find the anchor widget's position and insert after the source button
        # (which is typically the first widget in the layout)
        source_btn = getattr(self, '_source_button', None)
        if isinstance(source_btn, str):
            source_btn = self.get_widget(source_btn) if hasattr(self, 'get_widget') else None
        # Also check for programmatic source button
        if source_btn is None:
            source_btn = getattr(self, '_pb_source_button', None)

        insert_idx = 1  # Default: after first widget
        if source_btn:
            idx = layout.indexOf(source_btn)
            if idx >= 0:
                insert_idx = idx + 1

        # Insert in order: product_label, product_combo, version_label, version_combo
        layout.insertWidget(insert_idx, self._publish_product_label)
        layout.insertWidget(insert_idx + 1, self._publish_product_combo)
        layout.insertWidget(insert_idx + 2, self._publish_version_label)
        layout.insertWidget(insert_idx + 3, self._publish_version_combo)

    def _find_layout_containing(self, widget):
        """Find the QLayout that directly contains the given widget."""
        parent = widget.parentWidget()
        if parent is None:
            return None
        return self._search_layout_for_widget(parent.layout(), widget)

    def _search_layout_for_widget(self, layout, widget):
        """Recursively search for the layout containing widget."""
        if layout is None:
            return None
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item.widget() == widget:
                return layout
            if item.layout():
                found = self._search_layout_for_widget(item.layout(), widget)
                if found:
                    return found
        return None

    def _show_publish_widgets(self, visible):
        """Toggle visibility of the publish product/version combos."""
        if not hasattr(self, '_publish_product_combo'):
            return
        self._publish_product_label.setVisible(visible)
        self._publish_product_combo.setVisible(visible)
        self._publish_version_label.setVisible(visible)
        self._publish_version_combo.setVisible(visible)

    # ── AYON query flow ──────────────────────────────────────────────

    def _on_publish_source_selected(self):
        """Query AYON for render products when Publish source is selected."""
        render_list = self.get_widget(self._render_list_widget) if hasattr(self, '_render_list_widget') else None
        if render_list:
            render_list.clear()
            render_list.addItem("Loading products from AYON...")
            render_list.setEnabled(False)

        action_button = self.get_widget(self._action_button) if hasattr(self, '_action_button') else None
        if action_button:
            action_button.setEnabled(False)

        self.show_status("Querying AYON products...", "info")
        self.start_worker(
            self._fetch_ayon_products,
            on_result=self._on_ayon_products_fetched,
            on_error=self._on_publish_query_error,
        )

    def _fetch_ayon_products(self):
        """Worker: fetch render products from AYON for the current folder."""
        from ayon.service import AYON_AVAILABLE, convert_to_ayon_folder_path, get_folder_render_products

        if not AYON_AVAILABLE:
            return []

        project_name = self.app_state.jobname
        folder_path = convert_to_ayon_folder_path(
            self.app_state.shotpath, project_name
        )
        return get_folder_render_products(project_name, folder_path)

    def _on_ayon_products_fetched(self, products):
        """Populate product combo with fetched AYON products."""
        self._publish_products = products

        self._publish_product_combo.blockSignals(True)
        self._publish_product_combo.clear()
        for p in products:
            self._publish_product_combo.addItem(p["name"], p["id"])
        self._publish_product_combo.blockSignals(False)

        render_list = self.get_widget(self._render_list_widget) if hasattr(self, '_render_list_widget') else None

        if products:
            self.show_status(f"Found {len(products)} AYON product(s)", "info")
            # Trigger version fetch for the first product
            self._publish_product_combo.blockSignals(True)
            self._publish_product_combo.setCurrentIndex(0)
            self._publish_product_combo.blockSignals(False)
            self._on_publish_product_changed(0)
        else:
            if render_list:
                render_list.clear()
                render_list.addItem("No render products found in AYON")
                render_list.setEnabled(False)
            self.show_status("No render products found in AYON", "warning")

    def _on_publish_product_changed(self, index):
        """When product selection changes, fetch versions for that product."""
        if index < 0:
            return
        product_id = self._publish_product_combo.currentData()
        if not product_id:
            return

        self._publish_version_combo.blockSignals(True)
        self._publish_version_combo.clear()
        self._publish_version_combo.addItem("Loading...")
        self._publish_version_combo.blockSignals(False)

        self.start_worker(
            self._fetch_product_versions, product_id,
            on_result=self._on_publish_versions_fetched,
            on_error=self._on_publish_query_error,
        )

    def _fetch_product_versions(self, product_id):
        """Worker: fetch all versions for a product."""
        from ayon.service import get_product_version_list
        return get_product_version_list(self.app_state.jobname, product_id)

    def _on_publish_versions_fetched(self, versions):
        """Populate version combo with fetched versions."""
        self._publish_versions = versions

        self._publish_version_combo.blockSignals(True)
        self._publish_version_combo.clear()
        for v in versions:
            self._publish_version_combo.addItem(f"v{v['version']:03d}", v["id"])

        if versions:
            # Select latest (first in list, since sorted descending)
            self._publish_version_combo.setCurrentIndex(0)
        self._publish_version_combo.blockSignals(False)

        if versions:
            self._on_publish_version_changed(self._publish_version_combo.currentIndex())
        else:
            render_list = self.get_widget(self._render_list_widget) if hasattr(self, '_render_list_widget') else None
            if render_list:
                render_list.clear()
                render_list.addItem("No published versions with renders found")
                render_list.setEnabled(False)

            action_button = self.get_widget(self._action_button) if hasattr(self, '_action_button') else None
            if action_button:
                action_button.setEnabled(False)

            self.show_status("No published versions with renders found", "warning")

    def _on_publish_version_changed(self, index):
        """When version changes, resolve path and scan for renders."""
        if index < 0:
            return
        version_id = self._publish_version_combo.currentData()
        if not version_id:
            return

        render_list = self.get_widget(self._render_list_widget) if hasattr(self, '_render_list_widget') else None
        if render_list:
            render_list.clear()
            render_list.addItem("Resolving files...")
            render_list.setEnabled(False)

        self.show_status("Resolving AYON version to filesystem...", "info")
        self.start_worker(
            self._resolve_and_scan_publish, version_id,
            on_result=self._on_publish_scan_complete,
            on_error=self._on_publish_scan_error,
        )

    def _resolve_and_scan_publish(self, version_id):
        """Worker: resolve staging dir from AYON version and scan for sequences."""
        from ayon.service import resolve_version_render_path

        result = resolve_version_render_path(self.app_state.jobname, version_id)
        if not result:
            raise ValueError("Could not resolve filesystem path from AYON version")

        staging_dir = result["path"]
        if not os.path.exists(staging_dir):
            raise FileNotFoundError(f"Resolved path does not exist on disk: {staging_dir}")

        # Delegate to subclass scan function
        sequences = self._scan_publish_directory(staging_dir)
        return staging_dir, sequences

    def _scan_publish_directory(self, staging_dir):
        """Scan the resolved staging directory for render sequences.

        Subclasses MUST override this to provide the appropriate scan function.

        Args:
            staging_dir: Absolute filesystem path to the staging directory.

        Returns:
            list: List of fileseq.FileSequence objects (or equivalent).
        """
        raise NotImplementedError(
            "Subclasses must implement _scan_publish_directory()"
        )

    def _on_publish_scan_complete(self, result):
        """Handle successful publish path resolution and scan."""
        staging_dir, sequences = result

        render_list = self.get_widget(self._render_list_widget) if hasattr(self, '_render_list_widget') else None
        render_path = self.get_widget(self._render_path_widget) if hasattr(self, '_render_path_widget') else None
        action_button = self.get_widget(self._action_button) if hasattr(self, '_action_button') else None

        # Update render path display
        if render_path:
            render_path.setText(staging_dir)

        # Store in the same tuple format as filesystem scan: (subdir, FileSequence)
        renders = [("publish", seq) for seq in sequences]

        # Store renders using the standard attribute
        if hasattr(self, '_renders_attr'):
            setattr(self.app_state, self._renders_attr, renders)

        # Populate render list
        if render_list:
            render_list.clear()
            if renders:
                for _, render_seq in renders:
                    display_name = os.path.basename(str(render_seq))
                    render_list.addItem(display_name)
                render_list.setEnabled(True)
                self.show_status(f"Found {len(renders)} sequence(s)", "info")
            else:
                render_list.addItem("No EXR sequences found at resolved path")
                render_list.setEnabled(False)
                self.show_status("No sequences at resolved path", "warning")

        if action_button:
            action_button.setEnabled(False)

    def _on_publish_scan_error(self, error_msg, traceback_str=""):
        """Handle errors during publish path resolution."""
        render_list = self.get_widget(self._render_list_widget) if hasattr(self, '_render_list_widget') else None
        if render_list:
            render_list.clear()
            render_list.addItem(f"Error: {error_msg}")
            render_list.setEnabled(False)

        self.show_status(f"Publish source error: {error_msg}", "error")

    def _on_publish_query_error(self, error_msg, traceback_str=""):
        """Handle errors during AYON product/version queries."""
        logger.error(f"AYON query error: {error_msg}")
        self.show_status(f"AYON query failed: {error_msg}", "error")
