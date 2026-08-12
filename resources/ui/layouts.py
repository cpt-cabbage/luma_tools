"""
Custom layout classes.

Provides specialized layouts like FlowLayout for flexible widget arrangement.
"""
from PySide6.QtCore import Qt, QRect, QSize, QPoint
from PySide6.QtWidgets import QLayout, QStyle, QSizePolicy


class FlowLayout(QLayout):
    """
    A flow layout that arranges widgets in a row, wrapping to the next row when space runs out.
    Similar to CSS flexbox with flex-wrap: wrap.
    """

    def __init__(self, parent=None, margin=0, spacing=-1):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self._item_list = []
        self._h_spacing = spacing
        self._v_spacing = spacing
        self._animation_active = False
        self._pending_rect = None
        # minimumSize() is an O(N) sweep that Qt calls several times per layout
        # pass (sizeHint() delegates to it). Items here are fixed-size
        # thumbnails, so the result only changes when the item list changes or
        # Qt invalidates the layout — both of which clear this.
        self._min_size_cache = None

    def __del__(self):
        # Check if _item_list exists (may not if initialization failed or GC order issues)
        if not hasattr(self, '_item_list'):
            return
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def invalidate(self):
        self._min_size_cache = None
        super().invalidate()

    def addItem(self, item):
        self._item_list.append(item)
        self._min_size_cache = None

    def insertItem(self, index, item):
        """Insert a layout item at the specified index."""
        if index < 0:
            index = 0
        elif index > len(self._item_list):
            index = len(self._item_list)
        self._item_list.insert(index, item)
        self._min_size_cache = None

    def insertWidget(self, index, widget):
        """Insert a widget at the specified index in the layout."""
        from PySide6.QtWidgets import QWidgetItem
        self.addChildWidget(widget)
        item = QWidgetItem(widget)
        self.insertItem(index, item)

    def horizontalSpacing(self):
        if self._h_spacing >= 0:
            return self._h_spacing
        return self._smart_spacing(QStyle.PM_LayoutHorizontalSpacing)

    def verticalSpacing(self):
        if self._v_spacing >= 0:
            return self._v_spacing
        return self._smart_spacing(QStyle.PM_LayoutVerticalSpacing)

    def _smart_spacing(self, pm):
        parent = self.parent()
        if parent is None:
            return -1
        elif parent.isWidgetType():
            return parent.style().pixelMetric(pm, None, parent)
        else:
            return parent.spacing()

    def count(self):
        return len(self._item_list)

    def itemAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._item_list):
            self._min_size_cache = None
            return self._item_list.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self._do_layout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super().setGeometry(rect)
        if self._animation_active:
            self._pending_rect = rect
            return
        self._do_layout(rect, False)

    def begin_animation(self):
        """Block layout repositioning during widget animations."""
        self._animation_active = True
        self._pending_rect = None

    def end_animation(self):
        """Resume layout and replay any missed layout pass."""
        self._animation_active = False
        if self._pending_rect is not None:
            rect = self._pending_rect
            self._pending_rect = None
            self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        if self._min_size_cache is not None:
            return self._min_size_cache
        size = QSize()
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        self._min_size_cache = size
        return size

    def _do_layout(self, rect, test_only):
        """Position (or measure) every item.

        This is the layout hot path — a gallery rebuild runs it once per item
        batch and every resize/heightForWidth query runs it again, so per-item
        work here is multiplied by the item count. Spacing is resolved once up
        front and each item's sizeHint is fetched once instead of three times
        (that alone was ~48 M cross-language calls on a 2500-item gallery).
        """
        left, top, right, bottom = self.getContentsMargins()
        effective_rect = rect.adjusted(+left, +top, -right, -bottom)
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0

        # Explicit spacing (the gallery always sets one) resolves to a constant;
        # only the style-derived fallback has to be asked per widget.
        space_x = self.horizontalSpacing()
        space_y = self.verticalSpacing()
        dynamic_x = space_x == -1
        dynamic_y = space_y == -1

        left_edge = effective_rect.x()
        right_edge = effective_rect.right()

        for item in self._item_list:
            if dynamic_x or dynamic_y:
                style = item.widget().style()
                if dynamic_x:
                    space_x = style.layoutSpacing(
                        QSizePolicy.PushButton, QSizePolicy.PushButton, Qt.Horizontal
                    )
                if dynamic_y:
                    space_y = style.layoutSpacing(
                        QSizePolicy.PushButton, QSizePolicy.PushButton, Qt.Vertical
                    )

            hint = item.sizeHint()
            hint_width = hint.width()

            next_x = x + hint_width + space_x
            if next_x - space_x > right_edge and line_height > 0:
                x = left_edge
                y = y + line_height + space_y
                next_x = x + hint_width + space_x
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))

            x = next_x
            hint_height = hint.height()
            if hint_height > line_height:
                line_height = hint_height

        return y + line_height - rect.y() + bottom
