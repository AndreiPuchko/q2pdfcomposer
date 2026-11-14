import sys
import os
import subprocess
import fitz

from PyQt6.QtWidgets import (
    QTableView,
    QAbstractItemView,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsLineItem,
    QGraphicsDropShadowEffect,
    QSpinBox,
    QDoubleSpinBox,
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
from PyQt6.QtGui import (
    QFocusEvent,
    QKeyEvent,
    QMouseEvent,
    QPixmap,
    QImage,
    QPen,
    QCursor,
    QShowEvent,
    QWheelEvent,
    QPainter,
    QColor,
    QFont,
)
from PyQt6.QtCore import (
    Qt,
    QAbstractTableModel,
    QEvent,
    QMimeData,
    QModelIndex,
    QVariant,
    QRectF,
    QSize,
    pyqtSignal,
)


class PagesModel(QAbstractTableModel):
    rows_reordered = pyqtSignal(int, int)
    PAGE_ROW_MIME_TYPE = "application/x-pdf-composer-page-row"
    THUMBNAIL_SPACING = 5

    def __init__(self, preview_pages, allow_reordering=False):
        super().__init__()
        self.preview_pages = preview_pages
        self.allow_reordering = allow_reordering

    def rowCount(self, parent=None):
        return len(self.preview_pages)

    def columnCount(self, parent=None):
        return 1

    def data(self, index: QModelIndex, role):
        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == 0:
                return f"{index.row()+1}"
        elif role == Qt.ItemDataRole.BackgroundRole:
            return QColor("lightgrey")
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom
        if role == Qt.ItemDataRole.DecorationRole:
            if index.column() == 0:
                return self.preview_pages[index.row()]
        elif role == Qt.ItemDataRole.SizeHintRole and index.column() == 0:
            size = self.preview_pages[index.row()].size()
            return QSize(
                size.width() + int(self.THUMBNAIL_SPACING * 1.5), size.height() + self.THUMBNAIL_SPACING
            )
        return QVariant()

    def refresh(self):
        self.beginResetModel()
        self.endResetModel()

    def flags(self, index):
        flags = super().flags(index)
        if self.allow_reordering:
            flags |= Qt.ItemFlag.ItemIsDropEnabled
            if index.isValid():
                flags |= Qt.ItemFlag.ItemIsDragEnabled
        return flags

    def mimeTypes(self):
        return [self.PAGE_ROW_MIME_TYPE]

    def mimeData(self, indexes):
        mime_data = QMimeData()
        rows = {index.row() for index in indexes if index.isValid()}
        if self.allow_reordering and len(rows) == 1:
            mime_data.setData(self.PAGE_ROW_MIME_TYPE, str(rows.pop()).encode("ascii"))
        return mime_data

    def supportedDropActions(self):
        return Qt.DropAction.MoveAction

    def dropMimeData(self, mime_data, action, row, column, parent):
        if action == Qt.DropAction.IgnoreAction:
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
    row_selected = pyqtSignal(int)
    preview_dpi_changed = pyqtSignal(int)
    content_width_changed = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.minimum_content_width = 0
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
        w = self.columnWidth(0) + (
            self.verticalScrollBar().width() if self.verticalScrollBar().isVisible() else 0
        )
        self.setFixedWidth(max(w, self.minimum_content_width))
        self.content_width_changed.emit(self.width())

    def resizeEvent(self, e):
        self.resize_to_content()
        return super().resizeEvent(e)

    def currentChanged(self, current: QModelIndex, previous: QModelIndex):
        self.row_selected.emit(current.row())
        return super().currentChanged(current, previous)

    def get_selected_rows(self):
        return [x.row() for x in self.selectionModel().selectedRows() if not self.isRowHidden(x.row())]

    def wheelEvent(self, event: QWheelEvent):
        if QApplication.keyboardModifiers() == Qt.KeyboardModifier.ControlModifier:
            self.preview_dpi_changed.emit(1 if event.angleDelta().y() > 0 else -1)
            event.ignore()
        else:
            return super().wheelEvent(event)


class PageView(QGraphicsView):
    next_page = pyqtSignal(int)
    add_current_page = pyqtSignal()

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

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.fit_page()

    def fit_page(self):
        if self.pdf_image.pixmap().isNull():
            return
        self.resetTransform()
        self.fitInView(self.pdf_image, Qt.AspectRatioMode.KeepAspectRatio)

    def ensure_minimal_zoom(self):
        tlp = self.mapFromScene(0, 0)
        brp = self.mapFromScene(self.sceneRect().size().width(), self.sceneRect().size().height())

        scene_width = brp.x() - tlp.x()
        scene_height = brp.y() - tlp.y()

        view_width = self.rect().width()
        view_height = self.rect().height()
        if scene_height < view_height and scene_width < view_width:
            self.fitInView(self.pdf_image, Qt.AspectRatioMode.KeepAspectRatio)

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


class Q2PdfWidget(QWidget):

    def __init__(self, source_file="", dpi=300):
        super().__init__()

        self._preview_dpi = 15
        self._pdf_file = None
        self.pdf = None
        self.aec = 0
        self.dpi = dpi

        self.preview_pages = {}
        self.composed_preview_pages = []
        self.composed_pdf = fitz.open()
        self._previewing_result = False
        self._preview_row = None
        self.debug_data = None
        self.result_data = None
        self.layoutMargins = [3, 3, 3, 3]

        self.toolbar_frame = self.get_toolbar()
        self.doc_frame = QWidget()
        doc_layout = QHBoxLayout(self.doc_frame)
        doc_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignCenter)
        doc_layout.setContentsMargins(*self.layoutMargins)

        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(*self.layoutMargins)
        self.setLayout(self.main_layout)

        self.pages_view = PdfPagesPreview()
        self.pages_view.row_selected.connect(self.preview_page_changed)
        self.pages_model = PagesModel(self.preview_pages)
        self.pages_view.setModel(self.pages_model)
        self.pages_view.clicked.connect(lambda index: self.preview_page_changed(index.row()))
        self.pages_view.doubleClicked.connect(lambda index: self.add_source_page(index.row()))
        self.pages_view.setToolTip("Double-click a page to add it to the result")

        self.composed_pages_view = PdfPagesPreview()
        self.composed_pages_view.row_selected.connect(self.preview_composed_page_changed)
        self.composed_pages_model = PagesModel(self.composed_preview_pages, allow_reordering=True)
        self.composed_pages_model.rows_reordered.connect(self.reorder_composed_pages)
        self.composed_pages_view.setModel(self.composed_pages_model)
        self.composed_pages_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.composed_pages_view.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.composed_pages_view.setDragEnabled(True)
        self.composed_pages_view.setAcceptDrops(True)
        self.composed_pages_view.setDropIndicatorShown(True)
        self.composed_pages_view.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.composed_pages_view.setDragDropOverwriteMode(False)
        self.pages_view.content_width_changed.connect(self.resize_composed_pages_view)
        self.composed_pages_view.clicked.connect(
            lambda index: self.preview_composed_page_changed(index.row())
        )
        self.composed_page_count_label = QLabel("Result PDF")

        self.page_view = PageView(self.dpi)
        self.page_view.next_page.connect(self.next_preview_page)
        self.page_view.add_current_page.connect(self.add_current_page)

        self.preview_source_label = QLabel("Preview")

        self.first_page_button = QToolButton()
        self.first_page_button.setText("|◀")
        self.first_page_button.setToolTip("First page")
        self.first_page_button.clicked.connect(lambda: self.go_to_preview_page(0))

        self.previous_page_button = QToolButton()
        self.previous_page_button.setText("◀")
        self.previous_page_button.setToolTip("Previous page")
        self.previous_page_button.clicked.connect(lambda: self.next_preview_page(-1))

        self.page_number_input = QSpinBox()
        self.page_number_input.setKeyboardTracking(False)
        self.page_number_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_number_input.setMinimumWidth(75)
        self.page_number_input.valueChanged.connect(self.go_to_page_number)

        self.next_page_button = QToolButton()
        self.next_page_button.setText("▶")
        self.next_page_button.setToolTip("Next page")
        self.next_page_button.clicked.connect(lambda: self.next_preview_page(1))

        self.last_page_button = QToolButton()
        self.last_page_button.setText("▶|")
        self.last_page_button.setToolTip("Last page")
        self.last_page_button.clicked.connect(self.go_to_last_preview_page)

        self.add_page_button = QToolButton()
        self.add_page_button.setText("Add page")
        self.add_page_button.setEnabled(False)
        self.add_page_button.clicked.connect(self.add_current_page)

        self.remove_page_button = QToolButton()
        self.remove_page_button.setText("Remove page")
        self.remove_page_button.setEnabled(False)
        self.remove_page_button.clicked.connect(self.remove_current_page)

        self.save_result_button = QToolButton()
        self.save_result_button.setText("Save result")
        self.save_result_button.setEnabled(False)
        self.save_result_button.clicked.connect(self.save_result)

        work_frame = QWidget()
        work_layout = QHBoxLayout(work_frame)
        work_layout.setContentsMargins(*self.layoutMargins)
        work_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        composed_frame = QWidget()
        composed_layout = QVBoxLayout(composed_frame)
        composed_layout.setContentsMargins(0, 0, 0, 0)
        composed_layout.addWidget(self.composed_page_count_label)
        composed_layout.addWidget(self.composed_pages_view, stretch=1)
        work_layout.addWidget(composed_frame, stretch=1)

        source_frame = QWidget()
        source_layout = QVBoxLayout(source_frame)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.addWidget(QLabel("Source PDF"))
        source_layout.addWidget(self.pages_view, stretch=2)
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
        buttons_layout.addWidget(self.save_result_button)

        page_navigation_frame = QWidget()
        page_navigation_layout = QHBoxLayout(page_navigation_frame)
        page_navigation_layout.setContentsMargins(*self.layoutMargins)
        page_navigation_layout.setSpacing(2)
        page_navigation_layout.addStretch(1)
        page_navigation_layout.addWidget(self.first_page_button)
        page_navigation_layout.addWidget(self.previous_page_button)
        page_navigation_layout.addWidget(self.page_number_input)
        page_navigation_layout.addWidget(self.next_page_button)
        page_navigation_layout.addWidget(self.last_page_button)
        page_navigation_layout.addStretch(1)

        preview_layout.addWidget(buttons_frame, stretch=0)
        preview_layout.addWidget(self.preview_source_label)
        preview_layout.addWidget(page_navigation_frame, stretch=0)
        preview_layout.addWidget(self.page_view, stretch=1)

        doc_layout.addWidget(work_frame, stretch=0)
        doc_layout.addWidget(preview_frame, stretch=1)

        self.main_layout.addWidget(self.toolbar_frame)
        self.main_layout.addWidget(self.doc_frame)
        self.setAcceptDrops(True)
        for child in self.findChildren(QWidget):
            child.setAcceptDrops(True)
            child.installEventFilter(self)
        self.pages_view.preview_dpi_changed.connect(self.preview_dpi_changed)
        self.update_page_navigation()
        if source_file:
            self.pdf_file = source_file
        else:
            self.open_file()

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

    def get_toolbar(self):
        toolbar_frame = self.get_frame()

        self.open_file_button = QToolButton()
        self.open_file_button.setText("Open")
        self.open_file_button.clicked.connect(self.open_file)
        self.open_file_button.setToolTip("Open source PDF")

        self.file_name_label = QLabel()

        toolbar_frame.layout().addWidget(self.open_file_button)
        toolbar_frame.layout().addWidget(QLabel("Source file:"))
        toolbar_frame.layout().addWidget(self.file_name_label)
        return toolbar_frame

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

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
            if self.dropped_pdf_path(event.mimeData()):
                QToolTip.showText(QCursor.pos(), "Open", self)
                event.acceptProposedAction()
                return True
        elif event.type() == QEvent.Type.Drop:
            file_name = self.dropped_pdf_path(event.mimeData())
            if file_name:
                try:
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
        self.refresh_pages_view()

    def preview_dpi_changed(self, value):
        self.preview_dpi += value

    @property
    def pdf_file(self):
        return self._pdf_file

    @pdf_file.setter
    def pdf_file(self, value):
        new_pdf = fitz.open(value) if value else None
        old_pdf = self.pdf
        self.pdf = new_pdf
        self._pdf_file = value or None
        self._previewing_result = False
        self._preview_row = None
        self.result_data = None
        if self.pdf is None:
            self.preview_pages.clear()
            self.pages_model.refresh()
            self.pages_view.resize_to_content()
            self.resize_composed_pages_view()
            self.pages_view.clearSelection()
            self.pages_view.setCurrentIndex(QModelIndex())
            self.add_page_button.setEnabled(False)
            self.remove_page_button.setEnabled(False)
            self.preview_source_label.setText("Preview")
            self.page_view.set_image(QPixmap())
            self.update_page_navigation()
            self.file_name_label.clear()
        else:
            self.refresh_pages_view()
            self.pages_view.set_page(0)
            if self.pdf.page_count:
                self.preview_page_changed(0)
                self.page_view.fit_page()
            self.add_page_button.setEnabled(self.pdf.page_count > 0)
            self.file_name_label.setText(os.path.abspath(value))
        if old_pdf is not None:
            old_pdf.close()

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
                pixmap.samples_ptr,
                pixmap.width,
                pixmap.height,
                pixmap.stride,
                QImage.Format.Format_RGB888,
            )
            return QPixmap.fromImage(image)
        return pixmap.tobytes("png")

    def get_preview_pages(self, preview_dpi):
        if self.pdf is None:
            return {}
        return {page.number: self.get_page_image(page.number, preview_dpi) for page in self.pdf.pages()}

    def refresh_pages_view(self):
        self.preview_pages.clear()
        if self.pdf is None:
            self.pages_model.refresh()
            self.pages_view.resize_to_content()
            self.resize_composed_pages_view()
            self.update_page_navigation()
            return
        for key, value in self.get_preview_pages(self.preview_dpi).items():
            image = QImage()
            image.loadFromData(value)
            pix = QPixmap.fromImage(image)
            painter = QPainter(pix)
            font = painter.font()
            font.setPointSize(self.preview_dpi)
            painter.setFont(font)
            painter.drawText(QRectF(pix.rect()), Qt.AlignmentFlag.AlignCenter, f"{key + 1}")
            self.preview_pages[key] = pix

        self.preview_pages.update()
        previous_row = self.pages_view.currentIndex().row()
        self.pages_model.refresh()
        self.pages_view.resize_to_content()
        self.resize_composed_pages_view()
        if previous_row >= 0 and previous_row < self.pages_model.rowCount() - 1:
            self.pages_view.set_page(previous_row)
        else:
            self.pages_view.set_page(0)

    def preview_page_changed(self, row):
        if row < 0 or self.pdf is None or row >= self.pdf.page_count:
            return
        if not self._previewing_result and self._preview_row == row:
            return
        self._previewing_result = False
        self._preview_row = row
        self.add_page_button.setEnabled(True)
        self.remove_page_button.setEnabled(False)
        self.composed_pages_view.clearSelection()
        self.preview_source_label.setText(f"Source PDF — page {row + 1} of {self.pdf.page_count}")
        self.page_view.set_image(self.get_page_image(row, QImage=QImage, QPixmap=QPixmap))
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
        self.pages_view.clearSelection()
        self.preview_source_label.setText(f"Result PDF — page {row + 1} of {self.composed_pdf.page_count}")
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
            self.pages_view.set_page(row)
            self.preview_page_changed(row)

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

    def remove_current_page(self):
        row = self._preview_row
        if not self._previewing_result or row is None or row < 0 or row >= self.composed_pdf.page_count:
            return

        self.composed_pdf.delete_page(row)
        self.save_result_button.setEnabled(self.composed_pdf.page_count > 0)
        self.composed_preview_pages[:] = [
            self.create_composed_preview(page_number) for page_number in range(self.composed_pdf.page_count)
        ]
        self.composed_pages_model.refresh()
        self.resize_composed_pages_view()

        self._preview_row = None
        if self.composed_pdf.page_count:
            self.composed_pages_view.set_page(min(row, self.composed_pdf.page_count - 1))
        else:
            source_row = self.pages_view.currentIndex().row()
            if self.pdf is not None and 0 <= source_row < self.pdf.page_count:
                self.preview_page_changed(source_row)
            else:
                self._previewing_result = False
                self.remove_page_button.setEnabled(False)
                self.preview_source_label.setText("Preview")
                self.page_view.set_image(QPixmap())
                self.update_page_navigation()

    def add_current_page(self):
        if self._previewing_result:
            return
        row = self.pages_view.currentIndex().row()
        if self.pdf is None or row < 0 or row >= self.pdf.page_count:
            return

        self.composed_pdf.insert_pdf(self.pdf, from_page=row, to_page=row)
        self.save_result_button.setEnabled(True)
        preview = self.create_composed_preview(self.composed_pdf.page_count - 1)
        self.composed_preview_pages.append(preview)
        self.composed_pages_model.refresh()
        self.resize_composed_pages_view()

    def add_source_page(self, row):
        if self.pdf is None or row < 0 or row >= self.pdf.page_count:
            return
        self.pages_view.set_page(row)
        self.preview_page_changed(row)
        self.add_current_page()

    def create_composed_preview(self, page_number):
        image = QImage()
        if not image.loadFromData(
            self.get_page_image(page_number, self.preview_dpi, document=self.composed_pdf)
        ):
            raise RuntimeError(f"Unable to render result page {page_number + 1}")
        preview = QPixmap.fromImage(image)
        painter = QPainter(preview)
        font = painter.font()
        font.setPointSize(self.preview_dpi)
        painter.setFont(font)
        painter.drawText(QRectF(preview.rect()), Qt.AlignmentFlag.AlignCenter, f"{page_number + 1}")
        painter.end()
        return preview

    def resize_composed_pages_view(self, minimum_width=None):
        if minimum_width is None:
            minimum_width = self.pages_view.width()
        self.composed_pages_view.resize_to_content(minimum_width)

    def get_page_count(self):
        return self.pages_view.model().rowCount()

    def get_selected_pages(self):
        return self.pages_view.get_selected_rows()


if __name__ == "__main__":
    app = QApplication([])
    pdf_widget = Q2PdfWidget(source_file="data/Scannen0003.pdf", dpi=600)
    pdf_widget.preview_dpi = 10
    pdf_widget.resize(1000, 1000)
    pdf_widget.move(100, 100)
    pdf_widget.show()
    app.exec()
    sys.exit(0)
