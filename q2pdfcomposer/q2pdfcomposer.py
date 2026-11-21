import hashlib
import math
import os
from typing import Any

try:
    import qtpy
except ModuleNotFoundError as error:
    if error.name != "qtpy":
        raise
    raise ImportError(
        "QtPy is required to run PDF Composer. Install it with 'python -m pip install QtPy'."
    ) from error
if not qtpy.API_NAME:
    raise ImportError(
        "QtPy is installed, but no supported Qt binding is available. Install PyQt6 or PySide6."
    )

import qtpy.QtCore as QtCore
from qtpy.QtWidgets import (
    QTableView,
    QAbstractItemView,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QSpinBox,
    QFileDialog,
    QMessageBox,
    QToolButton,
    QApplication,
    QToolTip,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
    QLabel,
)
from qtpy.QtGui import (
    QKeyEvent,
    QPixmap,
    QImage,
    QCursor,
    QShowEvent,
    QWheelEvent,
    QPainter,
    QColor,
    QIcon,
)
from qtpy.QtSvg import QSvgRenderer

from qtpy.QtCore import (
    Qt,
    QAbstractTableModel,
    QByteArray,
    QEvent,
    QMimeData,
    QModelIndex,
    QRectF,
    QSize,
)

import pymupdf as fitz

Signal = QtCore.Signal
fitz.TOOLS.mupdf_display_errors(False)


class SourcePages(dict):
    def __init__(self, composer, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.composer = composer
        self._size_hints = {}

    def clear(self):
        super().clear()
        self._size_hints.clear()

    def __getitem__(self, key: Any) -> Any:
        if super().__getitem__(key) is None:
            self.__setitem__(key, self.composer.create_source_preview_page(key))
        return super().__getitem__(key)

    def size_hint(self, key: int) -> QSize:
        if key not in self._size_hints:
            page = self.composer.pdf[key]
            scale = self.composer.preview_dpi / 72
            self._size_hints[key] = QSize(
                math.ceil(page.rect.width * scale),
                math.ceil(page.rect.height * scale),
            )
        return self._size_hints[key]


class ComposerToolButton(QToolButton):
    def __init__(self, text, icon_name, parent=None, primary=False):
        super().__init__(parent)
        icon_color = "#ffffff" if primary else "#2E39B3"
        self.SVG_ICONS = {
            "first": '<path d="M5 4v16M19 5l-8 7 8 7"/>',
            "previous": '<path d="M17 5l-8 7 8 7"/>',
            "next": '<path d="M7 5l8 7-8 7"/>',
            "last": '<path d="M19 4v16M6 5l8 7-8 7"/>',
            "rotate": '<path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8" /><path d="M21 3v5h-5" />',
            "add": '<path d="M12 5v14M5 12h14"/>',
            "remove": '<path d="M5 12h14"/>',
            "save": '<path d="M12 3v12m0 0 5-5m-5 5-5-5M5 19v2h14v-2"/>',
            "open": '<path d="m6 14 1.45-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.55 6a2 2 0 0 1-1.94'
            " 1.5H4a2 2 0 0 1-2-2V5c0-1.1.9-2 2-2h3.93a2 2 0 0 1 1.66.9l.82"
            ' 1.2a2 2 0 0 0 1.66.9H18a2 2 0 0 1 2 2v2" />',
        }
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">'
            f'<g fill="none" stroke="{icon_color}" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round">{self.SVG_ICONS[icon_name]}</g></svg>'
        )
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        icon_pixmap = QPixmap(24, 24)
        icon_pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(icon_pixmap)
        renderer.render(painter)
        painter.end()

        if text:
            self.setText(text)
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            self.setFixedHeight(32)
        else:
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            self.setFixedSize(32, 32)
        self.setIcon(QIcon(icon_pixmap))
        self.setIconSize(QSize(18, 18))
        if primary:
            self.setStyleSheet(
                "QToolButton { color: white; background-color: #0d6efd; border: 1px solid #0d6efd; "
                "border-radius: 4px; padding: 4px 10px; font-weight: 600; }"
                "QToolButton:hover { background-color: #0b5ed7; border-color: #0b5ed7; }"
                "QToolButton:pressed { background-color: #0a58ca; border-color: #0a58ca; }"
                "QToolButton:disabled { background-color: #6c9bd2; border-color: #6c9bd2; }"
            )


class PagesModel(QAbstractTableModel):
    rows_reordered = Signal(int, int)
    source_pages_dropped = Signal(list, int)
    PAGE_ROW_MIME_TYPE = "application/x-pdf-composer-page-row"
    SOURCE_PAGES_MIME_TYPE = "application/x-pdf-composer-source-pages"
    THUMBNAIL_SPACING = 6

    def __init__(self, preview_pages, allow_reordering=False, allow_dragging=False):
        super().__init__()
        self.preview_pages = preview_pages
        self.allow_reordering = allow_reordering
        self.allow_dragging = allow_dragging
        self.included_rows = set()
        self.previewed_rows = set()

    def rowCount(self, parent=None):
        return len(self.preview_pages)

    def columnCount(self, parent=None):
        return 1

    def data(self, index: QModelIndex, role):
        if role == Qt.ItemDataRole.BackgroundRole:
            return (
                QColor("#45ef07")
                if index.row() in self.included_rows or index.row() in self.previewed_rows
                else QColor("lightgrey")
            )
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom
        if role == Qt.ItemDataRole.DecorationRole:
            if index.column() == 0:
                return self.preview_pages[index.row()]
        elif role == Qt.ItemDataRole.SizeHintRole and index.column() == 0:
            if isinstance(self.preview_pages, SourcePages):
                size = self.preview_pages.size_hint(index.row())
            else:
                size = self.preview_pages[index.row()].size()
            return QSize(size.width() + int(self.THUMBNAIL_SPACING), size.height() + self.THUMBNAIL_SPACING)
        return None

    def set_included_rows(self, rows):
        rows = set(rows)
        if rows == self.included_rows:
            return
        self.included_rows = rows
        self._emit_background_changed()

    def set_previewed_rows(self, rows):
        rows = set(rows)
        if rows == self.previewed_rows:
            return
        self.previewed_rows = rows
        self._emit_background_changed()

    def _emit_background_changed(self):
        if self.rowCount():
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self.rowCount() - 1, 0),
                [Qt.ItemDataRole.BackgroundRole],
            )

    def refresh(self):
        self.beginResetModel()
        self.endResetModel()

    def flags(self, index):
        flags = super().flags(index)
        if self.allow_reordering:
            flags |= Qt.ItemFlag.ItemIsDropEnabled
            if index.isValid():
                flags |= Qt.ItemFlag.ItemIsDragEnabled
        elif self.allow_dragging and index.isValid():
            flags |= Qt.ItemFlag.ItemIsDragEnabled
        return flags

    def mimeTypes(self):
        return [self.PAGE_ROW_MIME_TYPE, self.SOURCE_PAGES_MIME_TYPE]

    def mimeData(self, indexes):
        mime_data = QMimeData()
        rows = {index.row() for index in indexes if index.isValid()}
        if self.allow_reordering and len(rows) == 1:
            mime_data.setData(self.PAGE_ROW_MIME_TYPE, str(rows.pop()).encode("ascii"))
        elif self.allow_dragging and rows:
            encoded_rows = ",".join(str(row) for row in sorted(rows))
            mime_data.setData(self.SOURCE_PAGES_MIME_TYPE, encoded_rows.encode("ascii"))
        return mime_data

    def supportedDropActions(self):
        actions = Qt.DropAction.IgnoreAction
        if self.allow_reordering:
            actions |= Qt.DropAction.MoveAction | Qt.DropAction.CopyAction
        if self.allow_dragging:
            actions |= Qt.DropAction.CopyAction
        return actions

    def supportedDragActions(self):
        if self.allow_reordering:
            return Qt.DropAction.MoveAction
        if self.allow_dragging:
            return Qt.DropAction.CopyAction
        return Qt.DropAction.IgnoreAction

    def dropMimeData(self, mime_data, action, row, column, parent):
        if action == Qt.DropAction.IgnoreAction:
            return True
        if self.allow_reordering and mime_data.hasFormat(self.SOURCE_PAGES_MIME_TYPE):
            if action != Qt.DropAction.CopyAction:
                return False
            try:
                source_rows = [
                    int(encoded_row)
                    for encoded_row in bytes(mime_data.data(self.SOURCE_PAGES_MIME_TYPE))
                    .decode("ascii")
                    .split(",")
                ]
            except ValueError:
                return False
            destination_row = self.rowCount() if row < 0 else row
            if row < 0 and parent.isValid():
                destination_row = parent.row()
            self.source_pages_dropped.emit(source_rows, destination_row)
            return True
        if (
            not self.allow_reordering
            or action != Qt.DropAction.MoveAction
            or not mime_data.hasFormat(self.PAGE_ROW_MIME_TYPE)
        ):
            return False

        try:
            source_row = int(bytes(mime_data.data(self.PAGE_ROW_MIME_TYPE)).decode("ascii"))
        except ValueError:
            return False
        if row >= 0:
            destination_child = row
        elif parent.isValid():
            destination_child = parent.row()
            if source_row < destination_child:
                destination_child += 1
        else:
            destination_child = self.rowCount()
        return self.moveRows(QModelIndex(), source_row, 1, QModelIndex(), destination_child)

    def moveRows(self, source_parent, source_row, count, destination_parent, destination_child):
        if (
            not self.allow_reordering
            or source_parent.isValid()
            or destination_parent.isValid()
            or count != 1
            or source_row < 0
            or source_row >= self.rowCount()
            or destination_child < 0
            or destination_child > self.rowCount()
            or source_row <= destination_child <= source_row + count
        ):
            return False

        if not self.beginMoveRows(
            source_parent,
            source_row,
            source_row + count - 1,
            destination_parent,
            destination_child,
        ):
            return False
        moved_page = self.preview_pages.pop(source_row)
        destination_row = destination_child - count if destination_child > source_row else destination_child
        self.preview_pages.insert(destination_row, moved_page)
        self.endMoveRows()
        self.rows_reordered.emit(source_row, destination_row)
        return True


class PdfPagesPreview(QTableView):
    row_selected = Signal(int)
    focus_changed = Signal()
    preview_dpi_changed = Signal(int)
    content_width_changed = Signal(int)
    add_page_requested = Signal()
    remove_page_requested = Signal()

    def __init__(self):
        super().__init__()
        self.minimum_content_width = 10
        self.add_page_on_keypress = False
        self.remove_page_on_keypress = False
        self.alternative_frame_rows = set()
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        # self.setShowGrid(False)
        self.horizontalHeader().hide()
        self.verticalHeader().hide()

    def setModel(self, model):
        super().setModel(model)
        self.resize_to_content()

    def next_page(self, page):
        self.set_page(self.currentIndex().row() + page)

    def set_page(self, new_row):
        if new_row < 0 or new_row > (self.model().rowCount() - 1):
            return
        index = self.model().index(new_row, 0)
        self.setCurrentIndex(index)

    def resize_to_content(self, minimum_width=None):
        if minimum_width is not None:
            self.minimum_content_width = minimum_width
        self.resizeColumnsToContents()
        self.resizeRowsToContents()
        self._update_width()

    def _update_width(self):
        scrollbar = self.verticalScrollBar()
        scrollbar_width = (
            scrollbar.sizeHint().width()
            if scrollbar.isVisible() or scrollbar.maximum() > scrollbar.minimum()
            else 0
        )
        width = self.columnWidth(0) + scrollbar_width
        width = max(width, self.minimum_content_width)
        if width != self.width():
            self.setFixedWidth(width)
            self.content_width_changed.emit(width)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_width()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.focus_changed.emit()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.focus_changed.emit()

    def set_alternative_frame_rows(self, rows):
        rows = set(rows)
        if rows == self.alternative_frame_rows:
            return
        self.alternative_frame_rows = rows
        self.viewport().update()

    def paintEvent(self, event):
        super().paintEvent(event)
        index = self.currentIndex()
        if not index.isValid() and not self.alternative_frame_rows:
            return
        painter = QPainter(self.viewport())
        if index.isValid():
            self._draw_page_frame(painter, index.row(), self.palette().highlight().color(), 2)
        for row in sorted(self.alternative_frame_rows):
            self._draw_page_frame(painter, row, QColor("#ff4da6"), 3)
        painter.end()

    def _draw_page_frame(self, painter, row, color, width):
        index = self.model().index(row, 0)
        rect = self.visualRect(index)
        if rect.isEmpty():
            return
        rect.setSize(self.model().data(index, Qt.ItemDataRole.SizeHintRole))
        pen = painter.pen()
        pen.setWidth(width)
        pen.setColor(color)
        painter.setPen(pen)
        painter.drawRect(rect.adjusted(width, width, -width, -width))

    def currentChanged(self, current: QModelIndex, previous: QModelIndex):
        self.row_selected.emit(current.row())
        return super().currentChanged(current, previous)

    def keyPressEvent(self, event: QKeyEvent):
        if self.add_page_on_keypress and event.key() in (
            Qt.Key.Key_Space,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Return,
            Qt.Key.Key_Plus,
        ):
            self.add_page_requested.emit()
            event.accept()
            return
        if self.remove_page_on_keypress and event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Minus):
            self.remove_page_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def get_selected_rows(self):
        return [x.row() for x in self.selectionModel().selectedRows() if not self.isRowHidden(x.row())]

    def wheelEvent(self, event: QWheelEvent):
        if QApplication.keyboardModifiers() == Qt.KeyboardModifier.ControlModifier:
            self.preview_dpi_changed.emit(1 if event.angleDelta().y() > 0 else -1)
            event.ignore()
        else:
            return super().wheelEvent(event)


class PageView(QGraphicsView):
    next_page = Signal(int)
    add_current_page = Signal()

    def __init__(self, dpi):
        super().__init__()
        self.scene: QGraphicsScene = QGraphicsScene()
        self.setScene(self.scene)
        self.pdf_image = QGraphicsPixmapItem()
        self.scene.addItem(self.pdf_image)
        self.setBackgroundBrush(Qt.GlobalColor.lightGray)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.lines = []
        self.mouse_click_pos = None
        self.drag_mode = False

    def set_image(self, pixmap):
        self.pdf_image.setPixmap(pixmap)
        self.setSceneRect(self.pdf_image.boundingRect())
        self.update_drag_mode()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.fit_page()

    def fit_page(self):
        if self.pdf_image.pixmap().isNull():
            return
        self.resetTransform()
        self.fitInView(self.pdf_image, Qt.AspectRatioMode.KeepAspectRatio)
        self.update_drag_mode()

    def update_drag_mode(self):
        has_scrollbar = self.horizontalScrollBar().isVisible() or self.verticalScrollBar().isVisible()
        if has_scrollbar != self.drag_mode:
            self.setDragMode(
                QGraphicsView.DragMode.ScrollHandDrag if has_scrollbar else QGraphicsView.DragMode.NoDrag
            )
            self.drag_mode = has_scrollbar

    def ensure_minimal_zoom(self):
        tlp = self.mapFromScene(0, 0)
        brp = self.mapFromScene(self.sceneRect().size().width(), self.sceneRect().size().height())

        scene_width = brp.x() - tlp.x()
        scene_height = brp.y() - tlp.y()

        view_width = self.rect().width()
        view_height = self.rect().height()
        if scene_height < view_height and scene_width < view_width:
            self.fitInView(self.pdf_image, Qt.AspectRatioMode.KeepAspectRatio)
        self.update_drag_mode()

    def wheelEvent(self, event: QWheelEvent):
        if QApplication.keyboardModifiers() == Qt.KeyboardModifier.NoModifier:
            self.next_page.emit(-1 if event.angleDelta().y() > 0 else 1)
        elif QApplication.keyboardModifiers() == Qt.KeyboardModifier.ControlModifier:
            factor = 1.1
            if event.angleDelta().y() < 0:
                factor = 0.9

            self.scale(factor, factor)
            self.ensure_minimal_zoom()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.ensure_minimal_zoom()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_PageUp, Qt.Key.Key_PageDown, Qt.Key.Key_Down, Qt.Key.Key_Up):
            self.next_page.emit(
                -1
                if event.key()
                in [
                    Qt.Key.Key_PageUp,
                    Qt.Key.Key_Up,
                ]
                else 1
            )
            event.accept()
            return
        elif event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Plus):
            self.add_current_page.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class Q2PdfComposer(QWidget):

    def __init__(self, source_file="", dpi=150):
        super().__init__()

        self._preview_dpi = 10
        self._pdf_file = None
        self.pdf = None
        self.dpi = dpi

        self.source_preview_pages = SourcePages(self)
        self.composed_preview_pages = []
        self.composed_page_sources = []
        self.source_pdf_hash = None
        self.composed_pdf = fitz.open()
        self._previewing_result = False
        self._preview_row = None
        self.debug_data = None
        self.result_data = None
        self.layoutMargins = [3, 3, 3, 3]

        self.source_file_name = ""
        self.doc_frame = QWidget()
        doc_layout = QHBoxLayout(self.doc_frame)
        doc_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignCenter)
        doc_layout.setContentsMargins(*self.layoutMargins)

        self.main_layout = QHBoxLayout()
        self.main_layout.setContentsMargins(*self.layoutMargins)
        self.setLayout(self.main_layout)

        self.source_pages_view = PdfPagesPreview()
        self.source_pages_view.add_page_on_keypress = True
        self.source_pages_view.add_page_requested.connect(self.add_selected_pages)
        self.source_pages_view.row_selected.connect(self.preview_page_changed)
        self.source_pages_model = PagesModel(self.source_preview_pages, allow_dragging=True)
        self.source_pages_view.setModel(self.source_pages_model)
        self.source_pages_view.setDragEnabled(True)
        self.source_pages_view.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.source_pages_view.clicked.connect(lambda index: self.preview_page_changed(index.row()))
        self.source_pages_view.doubleClicked.connect(lambda index: self.add_source_page(index.row()))
        self.source_pages_view.setToolTip(
            "Double-click a page or press Space, Enter, or + to add it to the result"
        )
        self.source_pages_view.focus_changed.connect(self.update_composed_page_highlights)

        self.composed_pages_view = PdfPagesPreview()
        self.composed_pages_view.remove_page_on_keypress = True
        self.composed_pages_view.remove_page_requested.connect(self.remove_selected_pages)
        self.composed_pages_view.row_selected.connect(self.preview_composed_page_changed)
        self.composed_pages_model = PagesModel(self.composed_preview_pages, allow_reordering=True)
        self.composed_pages_model.rows_reordered.connect(self.reorder_composed_pages)
        self.composed_pages_model.source_pages_dropped.connect(self.insert_source_pages_at)
        self.composed_pages_view.setModel(self.composed_pages_model)
        self.composed_pages_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.composed_pages_view.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.composed_pages_view.setDragEnabled(True)
        self.composed_pages_view.setAcceptDrops(True)
        self.composed_pages_view.setDropIndicatorShown(True)
        self.composed_pages_view.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.composed_pages_view.setDragDropOverwriteMode(False)
        self.composed_pages_view.focus_changed.connect(self.update_source_page_frames)
        self.source_pages_view.content_width_changed.connect(self.resize_composed_pages_view)
        self.composed_pages_view.clicked.connect(
            lambda index: self.preview_composed_page_changed(index.row())
        )
        self.composed_pages_view.doubleClicked.connect(self.remove_selected_pages)
        self.composed_page_count_label = QLabel("Result PDF")

        self.page_view = PageView(self.dpi)
        self.page_view.next_page.connect(self.next_preview_page)
        self.page_view.add_current_page.connect(self.add_selected_pages)

        self.preview_source_label = QLabel("Preview")

        self.first_page_button = ComposerToolButton("", "first")
        self.first_page_button.setToolTip("First page")
        self.first_page_button.clicked.connect(lambda: self.go_to_preview_page(0))

        self.previous_page_button = ComposerToolButton("", "previous")
        self.previous_page_button.setToolTip("Previous page")
        self.previous_page_button.clicked.connect(lambda: self.next_preview_page(-1))

        self.page_number_input = QSpinBox()
        self.page_number_input.setKeyboardTracking(False)
        self.page_number_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_number_input.setMinimumWidth(75)
        self.page_number_input.valueChanged.connect(self.go_to_page_number)

        self.next_page_button = ComposerToolButton("", "next")
        self.next_page_button.setToolTip("Next page")
        self.next_page_button.clicked.connect(lambda: self.next_preview_page(1))

        self.last_page_button = ComposerToolButton("", "last")
        self.last_page_button.setToolTip("Last page")
        self.last_page_button.clicked.connect(self.go_to_last_preview_page)

        self.rotate_page_button = ComposerToolButton("", "rotate")
        self.rotate_page_button.setToolTip("Rotate page clockwise")
        self.rotate_page_button.clicked.connect(self.rotate_preview_page)

        # navigation_font = self.first_page_button.font()
        # navigation_font.setPointSize(navigation_font.pointSize() + 6)
        # for button in (
        #     self.first_page_button,
        #     self.previous_page_button,
        #     self.next_page_button,
        #     self.last_page_button,
        #     self.rotate_page_button,
        # ):
        #     button.setFont(navigation_font)

        self.add_page_button = ComposerToolButton("Add", "add")
        self.add_page_button.setEnabled(False)
        self.add_page_button.setToolTip("Add selected source pages to the result")
        self.add_page_button.clicked.connect(self.add_selected_pages)

        self.remove_page_button = ComposerToolButton("Remove", "remove")
        self.remove_page_button.setEnabled(False)
        self.remove_page_button.setToolTip("Remove selected result pages")
        self.remove_page_button.clicked.connect(self.remove_selected_pages)

        self.save_result_button = ComposerToolButton("Savе", "save")
        self.save_result_button.setEnabled(False)
        self.save_result_button.clicked.connect(self.save_result)

        self.thumbnail_dpi_spinbox = QSpinBox()
        self.thumbnail_dpi_spinbox.setRange(6, 49)
        self.thumbnail_dpi_spinbox.setValue(self.preview_dpi)
        self.thumbnail_dpi_spinbox.setToolTip("Thumbnail rendering DPI")
        self.thumbnail_dpi_spinbox.valueChanged.connect(self.set_preview_dpi)

        self.preview_dpi_spinbox = QSpinBox()
        self.preview_dpi_spinbox.setRange(100, 1200)
        self.preview_dpi_spinbox.setValue(self.dpi)
        self.preview_dpi_spinbox.setSingleStep(50)
        self.preview_dpi_spinbox.setToolTip("Full-page preview rendering DPI")
        self.preview_dpi_spinbox.valueChanged.connect(self.preview_render_dpi_changed)

        work_frame = QWidget()
        work_layout = QHBoxLayout(work_frame)
        work_layout.setContentsMargins(*self.layoutMargins)
        work_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        composed_frame = QWidget()
        composed_layout = QVBoxLayout(composed_frame)
        composed_layout.setContentsMargins(0, 0, 0, 0)
        composed_layout.addWidget(self.composed_page_count_label)
        composed_layout.addWidget(self.save_result_button)
        composed_layout.addWidget(self.composed_pages_view, stretch=1)
        work_layout.addWidget(composed_frame, stretch=1)

        source_frame = QWidget()
        source_layout = QVBoxLayout(source_frame)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.addWidget(QLabel("Source PDF"))

        self.open_file_button = ComposerToolButton("Open", "open", primary=True)
        self.open_file_button.clicked.connect(self.open_file)
        self.open_file_button.setToolTip("Open source PDF")
        source_layout.addWidget(self.open_file_button)

        source_layout.addWidget(self.source_pages_view, stretch=2)
        work_layout.addWidget(source_frame, stretch=2)

        preview_frame = QWidget()
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(*self.layoutMargins)
        preview_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        buttons_frame = QWidget()
        buttons_layout = QHBoxLayout(buttons_frame)
        buttons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        buttons_layout.setContentsMargins(*self.layoutMargins)
        buttons_layout.addWidget(self.add_page_button)
        buttons_layout.addWidget(self.remove_page_button)
        # buttons_layout.addWidget(self.save_result_button)
        buttons_layout.addStretch(1)
        buttons_layout.addWidget(QLabel("Thumbnails DPI:"))
        buttons_layout.addWidget(self.thumbnail_dpi_spinbox)
        buttons_layout.addWidget(QLabel("Preview DPI:"))
        buttons_layout.addWidget(self.preview_dpi_spinbox)

        page_navigation_frame = QWidget()
        page_navigation_layout = QHBoxLayout(page_navigation_frame)
        page_navigation_layout.setContentsMargins(0, 0, 0, 0)
        page_navigation_layout.setSpacing(2)

        page_navigation_layout.addStretch(1)
        page_navigation_layout.addWidget(self.first_page_button)
        page_navigation_layout.addWidget(self.previous_page_button)
        page_navigation_layout.addWidget(self.page_number_input)
        page_navigation_layout.addWidget(self.next_page_button)
        page_navigation_layout.addWidget(self.last_page_button)
        page_navigation_layout.addWidget(self.rotate_page_button)
        page_navigation_layout.addStretch(1)

        preview_layout.addWidget(buttons_frame, stretch=0)
        preview_layout.addWidget(self.preview_source_label)
        preview_layout.addWidget(page_navigation_frame, stretch=0)
        preview_layout.addWidget(self.page_view, stretch=1)

        doc_layout.addWidget(work_frame, stretch=0)
        doc_layout.addWidget(preview_frame, stretch=1)

        # self.main_layout.addWidget(self.toolbar_frame)
        self.main_layout.addWidget(self.doc_frame)
        self.setAcceptDrops(True)
        for child in self.findChildren(QWidget):
            child.setAcceptDrops(True)
            child.installEventFilter(self)
        self.composed_pages_view.preview_dpi_changed.connect(self.preview_dpi_changed)
        self.source_pages_view.preview_dpi_changed.connect(self.preview_dpi_changed)
        self.update_page_navigation()
        if source_file:
            self.pdf_file = source_file
        else:
            self.resize_source_pages_view()
            self.resize_composed_pages_view()
            # self.open_file()

    def get_frame(self, orientation=Qt.Orientation.Horizontal):
        frame = QWidget()
        if orientation == Qt.Orientation.Horizontal:
            frame.setLayout(QHBoxLayout())
            frame.layout().setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignCenter)
        else:
            frame.setLayout(QVBoxLayout())
            frame.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        frame.layout().setContentsMargins(*self.layoutMargins)
        return frame

    def open_file(self):
        file_name = QFileDialog.getOpenFileName(caption="Open PDF file", filter="PDF (*.PDF)")[0]
        if file_name:
            self.pdf_file = file_name

    @staticmethod
    def dropped_pdf_path(mime_data):
        if not mime_data.hasUrls():
            return None
        urls = mime_data.urls()
        if len(urls) != 1 or not urls[0].isLocalFile():
            return None
        file_name = urls[0].toLocalFile()
        if os.path.splitext(file_name)[1].lower() != ".pdf":
            return None
        return file_name

    def is_composed_pages_drop_target(self, watched):
        return isinstance(watched, QWidget) and (
            watched is self.composed_pages_view or self.composed_pages_view.isAncestorOf(watched)
        )

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            event.ignore()
            return
        super().keyPressEvent(event)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
            if self.dropped_pdf_path(event.mimeData()):
                tooltip = "Open and add all pages" if self.is_composed_pages_drop_target(watched) else "Open"
                QToolTip.showText(QCursor.pos(), tooltip, self)
                event.acceptProposedAction()
                return True
        elif event.type() == QEvent.Type.Drop:
            file_name = self.dropped_pdf_path(event.mimeData())
            if file_name:
                try:
                    if self.is_composed_pages_drop_target(watched):
                        if self._load_pdf_file(file_name, reopen_on_error=False):
                            self.source_pages_view.selectAll()
                            self.add_selected_pages()
                    else:
                        self.pdf_file = file_name
                except (fitz.mupdf.FzErrorBase, OSError, RuntimeError, ValueError) as error:
                    QMessageBox.critical(self, "Open failed", f"Could not open PDF:\n{error}")
                finally:
                    QToolTip.hideText()
                event.acceptProposedAction()
                return True
        elif event.type() == QEvent.Type.DragLeave:
            QToolTip.hideText()
        return super().eventFilter(watched, event)

    @property
    def preview_dpi(self):
        return self._preview_dpi

    @preview_dpi.setter
    def preview_dpi(self, value):
        if value <= 5 or value >= 50:
            return
        self._preview_dpi = value
        if hasattr(self, "thumbnail_dpi_spinbox") and self.thumbnail_dpi_spinbox.value() != value:
            previous_blocked = self.thumbnail_dpi_spinbox.blockSignals(True)
            self.thumbnail_dpi_spinbox.setValue(value)
            self.thumbnail_dpi_spinbox.blockSignals(previous_blocked)
        self.refresh_source_pages_view()
        self.composed_preview_pages[:] = [
            self.create_composed_preview(page_number) for page_number in range(self.composed_pdf.page_count)
        ]
        self.composed_pages_model.refresh()
        self.resize_composed_pages_view()

    def set_preview_dpi(self, value):
        self.preview_dpi = value

    def preview_dpi_changed(self, value):
        self.preview_dpi += value

    def preview_render_dpi_changed(self, value):
        if value == self.dpi:
            return
        self.dpi = value
        if self._preview_row is None:
            return

        row = self._preview_row
        self._preview_row = None
        if self._previewing_result:
            self.preview_composed_page_changed(row)
        else:
            self.preview_page_changed(row)
        self.page_view.fit_page()

    @property
    def pdf_file(self):
        return self._pdf_file

    @pdf_file.setter
    def pdf_file(self, value):
        self._load_pdf_file(value, reopen_on_error=True)

    def _load_pdf_file(self, value, reopen_on_error):
        try:
            new_source_hash = self._hash_pdf_file(value) if value else None
            new_pdf = fitz.open(value) if value else None
        except (fitz.mupdf.FzErrorBase, OSError, RuntimeError, ValueError) as error:
            QMessageBox.critical(self, "Open failed", f"Could not open PDF:\n{error}")
            if reopen_on_error:
                self.open_file()
            return False
        old_pdf = self.pdf
        self.pdf = new_pdf
        self._pdf_file = value or None
        self.source_pdf_hash = new_source_hash
        self._previewing_result = False
        self._preview_row = None
        self.result_data = None
        self.update_composed_page_highlights()
        self.update_source_page_frames()
        if self.pdf is None:
            self.source_preview_pages.clear()
            self.source_pages_model.refresh()
            self.resize_source_pages_view()
            self.resize_composed_pages_view()
            self.source_pages_view.clearSelection()
            self.source_pages_view.setCurrentIndex(QModelIndex())
            self.source_pages_model.set_included_rows(set())
            self.add_page_button.setEnabled(False)
            self.remove_page_button.setEnabled(False)
            self.preview_source_label.setText("Preview")
            self.page_view.set_image(QPixmap())
            self.update_page_navigation()
            self.source_file_name = ""
        else:
            self.refresh_source_pages_view()
            self.source_pages_view.set_page(0)
            self.source_file_name = os.path.abspath(value)
            if self.pdf.page_count:
                self.preview_page_changed(0)
                self.page_view.fit_page()
            self.add_page_button.setEnabled(self.pdf.page_count > 0)
        if old_pdf is not None:
            old_pdf.close()
        return True

    @staticmethod
    def _hash_pdf_file(file_name):
        digest = hashlib.sha256()
        with open(file_name, "rb") as pdf_file:
            for chunk in iter(lambda: pdf_file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def get_page_image(self, page_number, dpi=None, QImage=None, QPixmap=None, document=None):
        if dpi is None:
            dpi = self.dpi
        if document is None:
            document = self.pdf
        if document is None:
            raise RuntimeError("No PDF document is loaded")

        pixmap = document[page_number].get_pixmap(dpi=dpi, alpha=False)
        if QImage and QPixmap:
            image = QImage(
                pixmap.samples_mv,
                pixmap.width,
                pixmap.height,
                pixmap.stride,
                QImage.Format.Format_RGB888,
            ).copy()
            return QPixmap.fromImage(image)
        return pixmap.tobytes("png")

    def draw_page_number(self, page_number: int, page):
        image = QImage()
        image.loadFromData(page)
        pix = QPixmap.fromImage(image)
        painter = QPainter(pix)
        font = painter.font()
        font.setPointSize(self.preview_dpi)
        painter.setFont(font)
        painter.setPen(QColor("blue"))
        painter.drawText(QRectF(pix.rect()), Qt.AlignmentFlag.AlignCenter, f"{page_number + 1}")
        return pix

    def create_source_preview_page(self, page_number: int):
        page = self.get_page_image(page_number, self.preview_dpi)
        return self.draw_page_number(page_number, page)

    def refresh_source_pages_view(self):
        self.source_preview_pages.clear()
        if self.pdf is None:
            self.source_pages_model.refresh()
            self.resize_source_pages_view()
            self.resize_composed_pages_view()
            self.update_page_navigation()
            return
        self.source_preview_pages.update({x: None for x in range(self.pdf.page_count)})
        self.source_pages_model.refresh()
        self.update_source_page_highlights()
        previous_row = self.source_pages_view.currentIndex().row()
        self.resize_source_pages_view()
        self.resize_composed_pages_view()
        if previous_row >= 0 and previous_row < self.source_pages_model.rowCount() - 1:
            self.source_pages_view.set_page(previous_row)
        else:
            self.source_pages_view.set_page(0)

    def update_source_page_highlights(self):
        included_rows = set()
        if self.source_pdf_hash is not None:
            included_rows = {
                source_row
                for source_hash, source_row in self.composed_page_sources
                if source_hash == self.source_pdf_hash
            }
        self.source_pages_model.set_included_rows(included_rows)

    def update_composed_page_highlights(self):
        previewed_rows = set()
        focus_widget = QApplication.focusWidget()
        source_view_has_focus = focus_widget is not None and (
            focus_widget is self.source_pages_view or self.source_pages_view.isAncestorOf(focus_widget)
        )
        if (
            source_view_has_focus
            and not self._previewing_result
            and self.source_pdf_hash is not None
            and self._preview_row is not None
        ):
            previewed_rows = {
                result_row
                for result_row, (source_hash, source_row) in enumerate(self.composed_page_sources)
                if source_hash == self.source_pdf_hash and source_row == self._preview_row
            }
        self.composed_pages_model.set_previewed_rows(previewed_rows)

    def update_source_page_frames(self):
        framed_rows = set()
        focus_widget = QApplication.focusWidget()
        result_view_has_focus = focus_widget is not None and (
            focus_widget is self.composed_pages_view or self.composed_pages_view.isAncestorOf(focus_widget)
        )
        if (
            result_view_has_focus
            and self._previewing_result
            and self.source_pdf_hash is not None
            and self._preview_row is not None
            and 0 <= self._preview_row < len(self.composed_page_sources)
        ):
            source_hash, source_row = self.composed_page_sources[self._preview_row]
            if (
                source_hash == self.source_pdf_hash
                and self.pdf is not None
                and 0 <= source_row < self.pdf.page_count
            ):
                framed_rows.add(source_row)
        self.source_pages_view.set_alternative_frame_rows(framed_rows)

    def preview_page_changed(self, row):
        if row < 0 or self.pdf is None or row >= self.pdf.page_count:
            return
        if not self._previewing_result and self._preview_row == row and row != 0:
            return
        self._previewing_result = False
        self._preview_row = row
        self.add_page_button.setEnabled(True)
        self.remove_page_button.setEnabled(False)
        self.preview_source_label.setText(f"Source PDF: {self.source_file_name}")
        self.composed_pages_view.clearSelection()
        self.page_view.set_image(self.get_page_image(row, QImage=QImage, QPixmap=QPixmap))
        self.update_composed_page_highlights()
        self.update_source_page_frames()
        self.update_page_navigation()

    def preview_composed_page_changed(self, row):
        if row < 0 or row >= self.composed_pdf.page_count:
            return
        if self._previewing_result and self._preview_row == row:
            return
        self._previewing_result = True
        self._preview_row = row
        self.add_page_button.setEnabled(False)
        self.remove_page_button.setEnabled(True)
        self.source_pages_view.clearSelection()
        self.preview_source_label.setText(f"Result PDF")
        self.update_composed_page_highlights()
        self.update_source_page_frames()
        self.page_view.set_image(
            self.get_page_image(
                row,
                dpi=self.dpi,
                QImage=QImage,
                QPixmap=QPixmap,
                document=self.composed_pdf,
            )
        )
        self.update_page_navigation()

    def update_page_navigation(self):
        if self._previewing_result:
            page_count = self.composed_pdf.page_count
        else:
            page_count = self.pdf.page_count if self.pdf is not None else 0

        row = self._preview_row if self._preview_row is not None else 0
        row = row if 0 <= row < page_count else -1
        was_blocked = self.page_number_input.blockSignals(True)
        if page_count:
            self.page_number_input.setRange(1, page_count)
        else:
            self.page_number_input.setRange(0, 0)
        self.page_number_input.setSuffix(f" / {page_count}")
        self.page_number_input.setValue(row + 1 if row >= 0 else 0)
        self.page_number_input.blockSignals(was_blocked)
        self.page_number_input.setEnabled(page_count > 0)
        self.rotate_page_button.setEnabled(row >= 0)
        self.first_page_button.setEnabled(row > 0)
        self.previous_page_button.setEnabled(row > 0)
        self.next_page_button.setEnabled(0 <= row < page_count - 1)
        self.last_page_button.setEnabled(0 <= row < page_count - 1)

    def go_to_page_number(self, page_number):
        self.go_to_preview_page(page_number - 1)

    def go_to_preview_page(self, row):
        if self._previewing_result:
            if 0 <= row < self.composed_pdf.page_count:
                self.composed_pages_view.set_page(row)
                self.preview_composed_page_changed(row)
        elif self.pdf is not None and 0 <= row < self.pdf.page_count:
            self.source_pages_view.set_page(row)
            self.preview_page_changed(row)

    def rotate_preview_page(self):
        row = self._preview_row
        if row is None:
            return

        if self._previewing_result:
            document = self.composed_pdf
            if row < 0 or row >= document.page_count:
                return
            page = document.load_page(row)
            page.set_rotation((page.rotation + 90) % 360)
            self.composed_preview_pages[:] = [
                self.create_composed_preview(page_number) for page_number in range(document.page_count)
            ]
            self.composed_pages_model.refresh()
            self.resize_composed_pages_view()
            self._preview_row = None
            self.composed_pages_view.set_page(row)
            self.preview_composed_page_changed(row)
        else:
            if self.pdf is None or row < 0 or row >= self.pdf.page_count:
                return
            page = self.pdf.load_page(row)
            page.set_rotation((page.rotation + 90) % 360)
            self._preview_row = None
            self.refresh_source_pages_view()
            self.source_pages_view.set_page(row)
            self.preview_page_changed(row)
        self.page_view.fit_page()

    def go_to_last_preview_page(self):
        if self._previewing_result:
            page_count = self.composed_pdf.page_count
        else:
            page_count = self.pdf.page_count if self.pdf is not None else 0
        self.go_to_preview_page(page_count - 1)

    def next_preview_page(self, page):
        if self._preview_row is not None:
            self.go_to_preview_page(self._preview_row + page)

    def reorder_composed_pages(self, source_row, destination_row):
        document_destination = destination_row
        if destination_row > source_row:
            document_destination += 1
            if document_destination == self.composed_pdf.page_count:
                document_destination = -1
        self.composed_pdf.move_page(source_row, document_destination)
        source_reference = self.composed_page_sources.pop(source_row)
        self.composed_page_sources.insert(destination_row, source_reference)
        self.update_composed_page_highlights()

        preview_row = None
        if self._previewing_result and self._preview_row is not None:
            preview_row = self._preview_row
            if preview_row == source_row:
                preview_row = destination_row
            elif source_row < destination_row and source_row < preview_row <= destination_row:
                preview_row -= 1
            elif destination_row < source_row and destination_row <= preview_row < source_row:
                preview_row += 1

        self.composed_preview_pages[:] = [
            self.create_composed_preview(page_number) for page_number in range(self.composed_pdf.page_count)
        ]
        self.composed_pages_model.refresh()
        self.resize_composed_pages_view()

        if preview_row is not None:
            self._preview_row = None
            self.composed_pages_view.set_page(preview_row)
        self.update_source_page_frames()
        self.update_page_navigation()

    def save_result(self):
        if self.composed_pdf.page_count == 0:
            return

        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Save result PDF",
            "result.pdf",
            "PDF files (*.pdf)",
        )
        if not file_name:
            return

        root, extension = os.path.splitext(file_name)
        if extension.lower() != ".pdf":
            file_name = f"{root}.pdf" if extension else f"{file_name}.pdf"
        try:
            self.composed_pdf.save(file_name)
        except (fitz.mupdf.FzErrorBase, OSError, RuntimeError, ValueError) as error:
            QMessageBox.critical(self, "Save failed", f"Could not save PDF:\n{error}")

    def remove_selected_pages(self):
        if not self._previewing_result:
            return

        selected_rows = sorted(set(self.composed_pages_view.get_selected_rows()))
        if not selected_rows and self._preview_row is not None:
            selected_rows = [self._preview_row]
        selected_rows = [row for row in selected_rows if 0 <= row < self.composed_pdf.page_count]
        if not selected_rows:
            return

        preview_row = self._preview_row
        for row in reversed(selected_rows):
            self.composed_pdf.delete_page(row)
            del self.composed_page_sources[row]
        self.update_source_page_highlights()
        self.update_composed_page_highlights()

        self.save_result_button.setEnabled(self.composed_pdf.page_count > 0)
        self.composed_preview_pages[:] = [
            self.create_composed_preview(page_number) for page_number in range(self.composed_pdf.page_count)
        ]
        self.composed_pages_model.refresh()
        self.resize_composed_pages_view()

        self._preview_row = None
        if self.composed_pdf.page_count:
            if preview_row in selected_rows:
                next_row = min(selected_rows[0], self.composed_pdf.page_count - 1)
            elif preview_row is None:
                next_row = min(selected_rows[0], self.composed_pdf.page_count - 1)
            else:
                next_row = preview_row - sum(row < preview_row for row in selected_rows)
            self.composed_pages_view.clearSelection()
            self.composed_pages_view.set_page(next_row)
            self.preview_composed_page_changed(next_row)
        else:
            source_row = self.source_pages_view.currentIndex().row()
            if self.pdf is not None and 0 <= source_row < self.pdf.page_count:
                self.preview_page_changed(source_row)
            else:
                self._previewing_result = False
                self.remove_page_button.setEnabled(False)
                self.preview_source_label.setText("Preview")
                self.page_view.set_image(QPixmap())
                self.update_source_page_frames()
                self.update_page_navigation()

    def add_selected_pages(self):
        if self._previewing_result:
            return
        if self.pdf is None:
            return

        selected_rows = sorted(set(self.source_pages_view.get_selected_rows()))
        if not selected_rows:
            current_row = self.source_pages_view.currentIndex().row()
            if 0 <= current_row < self.pdf.page_count:
                selected_rows = [current_row]
        selected_rows = [row for row in selected_rows if 0 <= row < self.pdf.page_count]
        if not selected_rows:
            return

        self.insert_source_pages_at(selected_rows, self.composed_pdf.page_count)

    def insert_source_pages_at(self, source_rows, destination_row):
        if self.pdf is None:
            return
        source_rows = sorted(
            {row for row in source_rows if isinstance(row, int) and 0 <= row < self.pdf.page_count}
        )
        if not source_rows:
            return

        destination_row = max(0, min(destination_row, self.composed_pdf.page_count))
        insert_count = len(source_rows)
        preview_row = self._preview_row if self._previewing_result else None
        for offset, source_row in enumerate(source_rows):
            self.composed_pdf.insert_pdf(
                self.pdf,
                from_page=source_row,
                to_page=source_row,
                start_at=destination_row + offset,
            )
            self.composed_page_sources.insert(
                destination_row + offset,
                (self.source_pdf_hash, source_row),
            )
        self.update_source_page_highlights()
        self.update_composed_page_highlights()
        self.save_result_button.setEnabled(True)
        self.composed_preview_pages[:] = [
            self.create_composed_preview(page_number) for page_number in range(self.composed_pdf.page_count)
        ]
        self.composed_pages_model.refresh()
        self.resize_composed_pages_view()
        if preview_row is not None:
            if destination_row <= preview_row:
                preview_row += insert_count
            self._preview_row = None
            self.composed_pages_view.set_page(preview_row)
            self.preview_composed_page_changed(preview_row)

    def add_source_page(self, row):
        if self.pdf is None or row < 0 or row >= self.pdf.page_count:
            return
        self.source_pages_view.clearSelection()
        self.source_pages_view.selectRow(row)
        self.source_pages_view.set_page(row)
        self.preview_page_changed(row)
        self.add_selected_pages()

    def create_composed_preview(self, page_number):
        image = self.get_page_image(page_number, self.preview_dpi, document=self.composed_pdf)
        return self.draw_page_number(page_number, image)

    def resize_composed_pages_view(self, minimum_width=None):
        if minimum_width is None:
            minimum_width = self.source_pages_view.width()
        self.composed_pages_view.resize_to_content(minimum_width)

    def resize_source_pages_view(self):
        if self.pdf is None:
            a4_width_points, _ = fitz.paper_size("a4")
            a4_width = math.ceil(a4_width_points * self.preview_dpi / 72)
            minimum_width = (
                a4_width + int(PagesModel.THUMBNAIL_SPACING * 1.5) + self.source_pages_view.frameWidth()
            )
        else:
            minimum_width = 0
        self.source_pages_view.resize_to_content(minimum_width)

    def get_selected_pages(self):
        return self.source_pages_view.get_selected_rows()
