"""
Feature Request Dialog for Admin Users.

Displays all feature requests with filtering, sorting, and completion tracking.
Allows administrators to mark requests as completed.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QDialogButtonBox, QLabel, QCheckBox, QHBoxLayout, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt

from core.feature_requests import get_feature_requests, mark_feature_requests_as_read, mark_request_completed


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
        self.info_label.setStyleSheet("font-weight: bold; padding: 5px;")
        self.layout.addWidget(self.info_label)

        # Filter buttons
        filter_layout = QHBoxLayout()
        self.show_all_btn = QPushButton("Show All")
        self.show_pending_btn = QPushButton("Show Pending")
        self.show_completed_btn = QPushButton("Show Completed")
        filter_layout.addWidget(self.show_all_btn)
        filter_layout.addWidget(self.show_pending_btn)
        filter_layout.addWidget(self.show_completed_btn)
        filter_layout.addStretch()
        self.layout.addLayout(filter_layout)

        # Table widget
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Done", "Date", "User", "Category", "Description", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)  # Description column stretches
        self.table.setColumnWidth(0, 60)   # Done checkbox
        self.table.setColumnWidth(1, 140)  # Date
        self.table.setColumnWidth(2, 120)  # User
        self.table.setColumnWidth(3, 100)  # Category
        self.table.setColumnWidth(5, 180)  # Status
        self.layout.addWidget(self.table)

        # Buttons
        button_layout = QHBoxLayout()
        self.mark_completed_btn = QPushButton("Mark Selected as Completed")
        button_layout.addWidget(self.mark_completed_btn)
        button_layout.addStretch()

        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(self.accept)
        button_layout.addWidget(button_box)

        self.layout.addLayout(button_layout)

    def _connect_signals(self):
        """Connect signals to slots."""
        self.show_all_btn.clicked.connect(lambda: self._populate_table("all"))
        self.show_pending_btn.clicked.connect(lambda: self._populate_table("pending"))
        self.show_completed_btn.clicked.connect(lambda: self._populate_table("completed"))
        self.mark_completed_btn.clicked.connect(self._on_mark_completed)

    def _load_data(self):
        """Load feature requests and mark as read."""
        # Mark as read
        mark_feature_requests_as_read(self.user)

        # Get requests
        self.requests = get_feature_requests()

        # Update info label
        self._update_info_label()

        # Populate table
        self._populate_table("all")

    def _update_info_label(self):
        """Update the info label with request counts."""
        completed_count = sum(1 for req in self.requests if req.get('completed', False))
        pending_count = len(self.requests) - completed_count
        self.info_label.setText(
            f"Total Requests: {len(self.requests)} | Pending: {pending_count} | Completed: {completed_count}"
        )

    def _populate_table(self, filter_type: str = "all"):
        """
        Populate table based on filter.

        Args:
            filter_type: One of "all", "pending", or "completed"
        """
        self.table.setRowCount(0)
        self.checkbox_map.clear()

        # Filter requests
        filtered_requests = self.requests
        if filter_type == "pending":
            filtered_requests = [r for r in self.requests if not r.get('completed', False)]
        elif filter_type == "completed":
            filtered_requests = [r for r in self.requests if r.get('completed', False)]

        self.table.setRowCount(len(filtered_requests))

        for i, req in enumerate(filtered_requests):
            # Checkbox
            checkbox = QCheckBox()
            checkbox.setChecked(req.get('completed', False))
            checkbox.setEnabled(not req.get('completed', False))  # Disable if already completed
            checkbox_widget = QTableWidgetItem()
            self.table.setItem(i, 0, checkbox_widget)
            self.table.setCellWidget(i, 0, checkbox)
            self.checkbox_map[checkbox] = req.get('id')

            # Date
            self.table.setItem(i, 1, QTableWidgetItem(req['timestamp']))

            # User
            self.table.setItem(i, 2, QTableWidgetItem(req['username']))

            # Category
            self.table.setItem(i, 3, QTableWidgetItem(req['category']))

            # Description
            desc_item = QTableWidgetItem(req['description'])
            desc_item.setToolTip(req['description'])  # Full text on hover
            self.table.setItem(i, 4, desc_item)

            # Status
            if req.get('completed', False):
                status_text = f"✓ Done by {req.get('completed_by', 'Unknown')} on {req.get('completed_at', 'Unknown')}"
            else:
                status_text = "Pending"
            self.table.setItem(i, 5, QTableWidgetItem(status_text))

    def _on_mark_completed(self):
        """Mark selected requests as completed."""
        selected_ids = []
        for checkbox, req_id in self.checkbox_map.items():
            if checkbox.isChecked() and checkbox.isEnabled():
                selected_ids.append(req_id)

        if not selected_ids:
            QMessageBox.information(self, "No Selection", "Please select pending requests to mark as completed.")
            return

        # Confirm
        reply = QMessageBox.question(
            self,
            "Confirm Completion",
            f"Mark {len(selected_ids)} request(s) as completed?\n\nUsers will be notified.",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            success_count = 0
            for req_id in selected_ids:
                if mark_request_completed(req_id, self.user):
                    success_count += 1

            QMessageBox.information(
                self,
                "Completed",
                f"Marked {success_count} request(s) as completed.\nUsers will be notified when they open the app."
            )

            # Refresh the dialog
            self.accept()
            # Parent will handle reopening if needed
