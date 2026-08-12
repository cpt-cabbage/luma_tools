"""
Feature Request Dialog for Admin Users.

Displays all feature requests with pending items at top and completed items
in a collapsible section at the bottom.
Allows administrators to mark requests as completed.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QDialogButtonBox, QLabel, QCheckBox, QHBoxLayout, QPushButton,
    QFrame, QWidget, QToolButton
)
from PySide6.QtCore import Qt

from core.feature_requests import get_feature_requests, mark_feature_requests_as_read, mark_request_completed, reject_request
from dialog_helpers import confirm_action, show_info


class CollapsibleSection(QWidget):
    """A collapsible section widget with a header button and content area."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._is_collapsed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header with toggle button
        self.toggle_button = QToolButton()
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.DownArrow)
        self.toggle_button.setText(title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(False)
        self.toggle_button.clicked.connect(self._toggle)
        layout.addWidget(self.toggle_button)

        # Separator line
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        # Content area
        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(0, 5, 0, 0)
        layout.addWidget(self.content_area)

    def _toggle(self):
        """Toggle the collapsed state."""
        self._is_collapsed = self.toggle_button.isChecked()
        self.toggle_button.setArrowType(Qt.RightArrow if self._is_collapsed else Qt.DownArrow)
        self.content_area.setVisible(not self._is_collapsed)

    def set_collapsed(self, collapsed: bool):
        """Set the collapsed state."""
        self.toggle_button.setChecked(collapsed)
        self._toggle()

    def add_widget(self, widget):
        """Add a widget to the content area."""
        self.content_layout.addWidget(widget)

    def update_title(self, title: str):
        """Update the section title."""
        self.toggle_button.setText(title)


class FeatureRequestDialog(QDialog):
    """Dialog for viewing and managing feature requests (admin only)."""

    def __init__(self, parent, user: str, is_admin: bool):
        """
        Initialize the feature request dialog.

        Args:
            parent: Parent widget (main window)
            user: Current username
            is_admin: Whether the user has admin privileges
        """
        super().__init__(parent)
        self.user = user
        self.is_admin = is_admin
        self.requests = []
        self.checkbox_map = {}

        self._setup_ui()
        self._load_data()
        self._connect_signals()

    def _setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle("Luma Tools - Feature Requests")
        self.setMinimumSize(900, 600)

        self.layout = QVBoxLayout(self)

        # Info label with counts
        self.info_label = QLabel()
        self.info_label.setProperty("textRole", "title")
        self.layout.addWidget(self.info_label)

        # Pending requests section (main area)
        pending_label = QLabel("Pending Requests")
        pending_label.setProperty("textRole", "title")
        self.layout.addWidget(pending_label)

        self.pending_table = self._create_table()
        self.layout.addWidget(self.pending_table, stretch=2)

        # Action buttons for pending requests
        button_layout = QHBoxLayout()
        self.mark_completed_btn = QPushButton("Mark Selected as Completed")
        button_layout.addWidget(self.mark_completed_btn)
        self.reject_btn = QPushButton("Reject Selected")
        button_layout.addWidget(self.reject_btn)
        button_layout.addStretch()
        self.layout.addLayout(button_layout)

        # Rejected requests section (collapsible)
        self.rejected_section = CollapsibleSection("Rejected Requests (0)")
        self.rejected_table = self._create_table(show_checkbox=False, table_type="rejected")
        self.rejected_section.add_widget(self.rejected_table)
        self.rejected_section.set_collapsed(True)
        self.layout.addWidget(self.rejected_section, stretch=1)

        # Completed requests section (collapsible)
        self.completed_section = CollapsibleSection("Completed Requests (0)")
        self.completed_table = self._create_table(show_checkbox=False)
        self.completed_section.add_widget(self.completed_table)
        self.completed_section.set_collapsed(True)  # Start collapsed
        self.layout.addWidget(self.completed_section, stretch=1)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(self.accept)
        self.layout.addWidget(button_box)

    def _create_table(self, show_checkbox: bool = True, table_type: str = "completed") -> QTableWidget:
        """Create a table widget with appropriate columns.

        Args:
            show_checkbox: Whether to show the checkbox column
            table_type: Type of non-checkbox table ("completed" or "rejected")

        Returns:
            Configured QTableWidget
        """
        table = QTableWidget()

        if show_checkbox:
            table.setColumnCount(5)
            table.setHorizontalHeaderLabels(["Select", "Date", "User", "Category", "Description"])
            table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
            table.setColumnWidth(0, 50)   # Select checkbox
            table.setColumnWidth(1, 140)  # Date
            table.setColumnWidth(2, 120)  # User
            table.setColumnWidth(3, 100)  # Category
        elif table_type == "rejected":
            table.setColumnCount(6)
            table.setHorizontalHeaderLabels(["Date", "User", "Category", "Description", "Rejected By", "Reason"])
            table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
            table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
            table.setColumnWidth(0, 140)  # Date
            table.setColumnWidth(1, 120)  # User
            table.setColumnWidth(2, 100)  # Category
            table.setColumnWidth(4, 120)  # Rejected By
        else:
            table.setColumnCount(5)
            table.setHorizontalHeaderLabels(["Date", "User", "Category", "Description", "Completed By"])
            table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
            table.setColumnWidth(0, 140)  # Date
            table.setColumnWidth(1, 120)  # User
            table.setColumnWidth(2, 100)  # Category
            table.setColumnWidth(4, 180)  # Completed By

        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)

        return table

    def _connect_signals(self):
        """Connect signals to slots."""
        self.mark_completed_btn.clicked.connect(self._on_mark_completed)
        self.reject_btn.clicked.connect(self._on_reject)

    def _load_data(self):
        """Load feature requests and mark as read."""
        # Mark as read
        mark_feature_requests_as_read(self.user)

        # Get requests
        self.requests = get_feature_requests()

        # Update info label
        self._update_info_label()

        # Populate tables
        self._populate_tables()

    def _update_info_label(self):
        """Update the info label with request counts."""
        completed_count = sum(1 for req in self.requests if req.get('completed', False))
        rejected_count = sum(1 for req in self.requests if req.get('rejected', False))
        pending_count = len(self.requests) - completed_count - rejected_count
        self.info_label.setText(
            f"Total Requests: {len(self.requests)} | Pending: {pending_count} | "
            f"Rejected: {rejected_count} | Completed: {completed_count}"
        )

    def _populate_tables(self):
        """Populate pending, rejected, and completed tables."""
        # Clear existing data
        self.pending_table.setRowCount(0)
        self.rejected_table.setRowCount(0)
        self.completed_table.setRowCount(0)
        self.checkbox_map.clear()

        # Separate pending, rejected, and completed
        pending_requests = [
            r for r in self.requests
            if not r.get('completed', False) and not r.get('rejected', False)
        ]
        rejected_requests = [r for r in self.requests if r.get('rejected', False)]
        completed_requests = [r for r in self.requests if r.get('completed', False)]

        # Populate pending table
        self.pending_table.setRowCount(len(pending_requests))
        for i, req in enumerate(pending_requests):
            req_id = req.get('id')

            # Checkbox for selection
            checkbox = QCheckBox()
            checkbox.setChecked(False)
            checkbox_widget = QTableWidgetItem()
            self.pending_table.setItem(i, 0, checkbox_widget)
            self.pending_table.setCellWidget(i, 0, checkbox)
            self.checkbox_map[checkbox] = req_id

            # Date
            self.pending_table.setItem(i, 1, QTableWidgetItem(req['timestamp']))
            # User
            self.pending_table.setItem(i, 2, QTableWidgetItem(req['username']))
            # Category
            self.pending_table.setItem(i, 3, QTableWidgetItem(req['category']))
            # Description
            desc_item = QTableWidgetItem(req['description'])
            desc_item.setToolTip(req['description'])
            self.pending_table.setItem(i, 4, desc_item)

        # Populate rejected table (sorted by rejection date, newest first)
        rejected_requests.sort(key=lambda x: x.get('rejected_at', ''), reverse=True)
        self.rejected_table.setRowCount(len(rejected_requests))
        for i, req in enumerate(rejected_requests):
            # Date
            self.rejected_table.setItem(i, 0, QTableWidgetItem(req['timestamp']))
            # User
            self.rejected_table.setItem(i, 1, QTableWidgetItem(req['username']))
            # Category
            self.rejected_table.setItem(i, 2, QTableWidgetItem(req['category']))
            # Description
            desc_item = QTableWidgetItem(req['description'])
            desc_item.setToolTip(req['description'])
            self.rejected_table.setItem(i, 3, desc_item)
            # Rejected by
            self.rejected_table.setItem(i, 4, QTableWidgetItem(req.get('rejected_by', 'Unknown')))
            # Reason
            reason = req.get('reject_reason', '')
            reason_item = QTableWidgetItem(reason)
            reason_item.setToolTip(reason)
            self.rejected_table.setItem(i, 5, reason_item)

        # Update rejected section title
        self.rejected_section.update_title(f"Rejected Requests ({len(rejected_requests)})")

        # Populate completed table (sorted by completion date, newest first)
        completed_requests.sort(key=lambda x: x.get('completed_at', ''), reverse=True)
        self.completed_table.setRowCount(len(completed_requests))
        for i, req in enumerate(completed_requests):
            # Date
            self.completed_table.setItem(i, 0, QTableWidgetItem(req['timestamp']))
            # User
            self.completed_table.setItem(i, 1, QTableWidgetItem(req['username']))
            # Category
            self.completed_table.setItem(i, 2, QTableWidgetItem(req['category']))
            # Description
            desc_item = QTableWidgetItem(req['description'])
            desc_item.setToolTip(req['description'])
            self.completed_table.setItem(i, 3, desc_item)
            # Completed by
            completed_text = f"{req.get('completed_by', 'Unknown')} on {req.get('completed_at', 'Unknown')}"
            self.completed_table.setItem(i, 4, QTableWidgetItem(completed_text))

        # Update completed section title
        self.completed_section.update_title(f"Completed Requests ({len(completed_requests)})")

    def _on_mark_completed(self):
        """Mark selected requests as completed."""
        selected_ids = []
        for checkbox, req_id in self.checkbox_map.items():
            if checkbox.isChecked():
                selected_ids.append(req_id)

        if not selected_ids:
            show_info("No Selection", "Please select pending requests to mark as completed.", self)
            return

        # Confirm
        if not confirm_action(
            "Confirm Completion",
            f"Mark {len(selected_ids)} request(s) as completed?\n\nUsers will be notified.",
            self
        ):
            return

        success_count = 0
        for req_id in selected_ids:
            if mark_request_completed(req_id, self.user):
                success_count += 1

        if success_count > 0:
            show_info(
                "Completed",
                f"Marked {success_count} request(s) as completed.\nUsers will be notified when they open the app.",
                self
            )
            # Refresh the data to show updated state
            self._load_data()
        else:
            show_info(
                "Error",
                "Failed to mark requests as completed. Check the logs for details.",
                self
            )

    def _on_reject(self):
        """Reject selected requests with a reason."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextEdit, QDialogButtonBox

        selected_ids = []
        for checkbox, req_id in self.checkbox_map.items():
            if checkbox.isChecked():
                selected_ids.append(req_id)

        if not selected_ids:
            show_info("No Selection", "Please select pending requests to reject.", self)
            return

        # Ask for rejection reason
        reason_dialog = QDialog(self)
        reason_dialog.setWindowTitle("Rejection Reason")
        reason_dialog.setMinimumSize(400, 200)

        layout = QVBoxLayout(reason_dialog)
        layout.addWidget(QLabel(f"Rejecting {len(selected_ids)} request(s).\nPlease provide a reason:"))

        reason_edit = QTextEdit()
        reason_edit.setPlaceholderText("Enter the reason for rejection...")
        layout.addWidget(reason_edit)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(reason_dialog.accept)
        button_box.rejected.connect(reason_dialog.reject)
        layout.addWidget(button_box)

        if reason_dialog.exec() != QDialog.Accepted:
            return

        reason = reason_edit.toPlainText().strip()
        if not reason:
            show_info("No Reason", "Please provide a reason for rejection.", self)
            return

        success_count = 0
        for req_id in selected_ids:
            if reject_request(req_id, self.user, reason):
                success_count += 1

        if success_count > 0:
            show_info(
                "Rejected",
                f"Rejected {success_count} request(s).\nUsers will be notified when they open the app.",
                self
            )
            self._load_data()
        else:
            show_info(
                "Error",
                "Failed to reject requests. Check the logs for details.",
                self
            )
