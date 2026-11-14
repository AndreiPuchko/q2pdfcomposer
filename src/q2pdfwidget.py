import sys
import os
import subprocess
import fitz
import q2ocr

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
    QToolButton,
    QApplication,
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
)
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QVariant, QRectF, pyqtSignal

INCH = 2.54


def open_document(folder):
    if "win32" in sys.platform:
        os.startfile(folder)
    elif "darwin" in sys.platform:
        subprocess.Popen(["open", folder])
    else:
        subprocess.Popen(["xdg-open", folder])


class PagesModel(QAbstractTableModel):
    def __init__(self, preview_pages):
        super().__init__()
        self.preview_pages = preview_pages

    def rowCount(self, parent=None):
        return len(self.preview_pages)

    def columnCount(self, parent=None):
        return 1

    def data(self, index: QModelIndex, role):
        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == 0:
                return f"{index.row()+1}"
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom
        if role == Qt.ItemDataRole.DecorationRole:
            if index.column() == 0:
                return self.preview_pages[index.row()]
        elif role == Qt.ItemDataRole.SizeHintRole:
            if index.column() == 0:
                return self.preview_pages[index.row()].size()
        return QVariant()

    def refresh(self):
        self.beginResetModel()
        self.endResetModel()


class PdfPagesPreview(QTableView):
    row_selected = pyqtSignal(int)
    preview_dpi_changed = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
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

    def resize_to_content(self):
        self.resizeColumnsToContents()
        self.resizeRowsToContents()
        w = self.columnWidth(0) + (
            self.verticalScrollBar().width() if self.verticalScrollBar().isVisible() else 0
        )
        self.setFixedWidth(w)

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


class VerticalLine(QGraphicsLineItem):
    def __init__(self, parent_item, pos_x) -> None:
        super().__init__(0, 0, 0, parent_item.boundingRect().height())
        self.moveBy(pos_x, 0)
        # self.setZValue(2)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
            | QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges
        )

        self.setPen(QPen(Qt.GlobalColor.darkBlue, 8))
        self.setParentItem(parent_item)
        ef = QGraphicsDropShadowEffect()
        ef.setColor(Qt.GlobalColor.green)
        ef.setOffset(0)
        ef.setBlurRadius(20)
        self.setGraphicsEffect(ef)
        self.graphicsEffect().setEnabled(False)
        self.setAcceptHoverEvents(True)

    def focusInEvent(self, event: QFocusEvent | None) -> None:
        self.graphicsEffect().setEnabled(True)
        return super().focusInEvent(event)

    def focusOutEvent(self, event: QFocusEvent | None) -> None:
        self.graphicsEffect().setEnabled(False)
        return super().focusOutEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Left:
            self.moveBy(-1, 0)
        elif event.key() == Qt.Key.Key_Right:
            self.moveBy(1, 0)
        elif event.key() == Qt.Key.Key_Delete:
            self.scene().removeItem(self)
        return super().keyPressEvent(event)


class PageView(QGraphicsView):
    next_page = pyqtSignal(int)

    def __init__(self, dpi):
        super().__init__()
        self.scene: QGraphicsScene = QGraphicsScene()
        self.setScene(self.scene)
        self.pdf_image = QGraphicsPixmapItem()
        self.scene.addItem(self.pdf_image)
        self.setBackgroundBrush(Qt.GlobalColor.lightGray)
        self.dpi = dpi
        self.lines = []
        self.mouse_click_pos = None
        self.drag_mode = False

    def set_image(self, pixmap):
        self.pdf_image.setPixmap(pixmap)
        self.setSceneRect(self.pdf_image.boundingRect())

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
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


class Q2PdfWidget(QWidget):

    def __init__(self, ocr_progress_callback=None, dpi=300):
        super().__init__()

        self._preview_dpi = 15
        self._pdf_file = None
        self.aec = 0
        self.dpi = dpi

        self._base_column = 1
        self._row_margin = 0.5

        self._ocr_progress_callback = ocr_progress_callback

        self.preview_pages = {}
        self.composed_preview_pages = []
        self.composed_pdf = fitz.open()
        self._previewing_result = False
        self._preview_row = None
        self.debug_data = None
        self.result_data = None

        self.toolbar_frame = self.get_toolbar()
        self.doc_frame = QWidget()
        doc_layout = QHBoxLayout(self.doc_frame)
        doc_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignCenter)
        doc_layout.setContentsMargins(1, 1, 1, 1)

        self.q2ocr = q2ocr.Q2OCR(dpi=self.dpi)

        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.main_layout)

        self.pages_view = PdfPagesPreview()
        self.pages_view.row_selected.connect(self.preview_page_changed)
        self.pages_model = PagesModel(self.preview_pages)
        self.pages_view.setModel(self.pages_model)
        self.pages_view.clicked.connect(lambda index: self.preview_page_changed(index.row()))

        self.composed_pages_view = PdfPagesPreview()
        self.composed_pages_view.row_selected.connect(self.preview_composed_page_changed)
        self.composed_pages_model = PagesModel(self.composed_preview_pages)
        self.composed_pages_view.setModel(self.composed_pages_model)
        self.composed_pages_view.clicked.connect(
            lambda index: self.preview_composed_page_changed(index.row())
        )
        self.composed_page_count_label = QLabel("Result PDF")

        self.page_view = PageView(self.q2ocr.dpi)
        self.page_view.next_page.connect(self.next_preview_page)

        self.preview_source_label = QLabel("Preview")

        self.add_page_button = QToolButton()
        self.add_page_button.setText("Add page")
        self.add_page_button.setEnabled(False)
        self.add_page_button.clicked.connect(self.add_current_page)

        self.remove_page_button = QToolButton()
        self.remove_page_button.setText("Remove page")
        self.remove_page_button.setEnabled(False)
        self.remove_page_button.clicked.connect(self.remove_current_page)

        work_frame = QWidget()
        work_layout = QHBoxLayout(work_frame)
        work_layout.setContentsMargins(1, 1, 1, 1)
        work_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        composed_frame = QWidget()
        composed_layout = QVBoxLayout(composed_frame)
        composed_layout.addWidget(self.composed_page_count_label)
        composed_layout.addWidget(self.composed_pages_view, stretch=1)
        work_layout.addWidget(composed_frame, stretch=1)

        source_frame = QWidget()
        source_layout = QVBoxLayout(source_frame)
        source_layout.addWidget(QLabel("Source PDF"))
        source_layout.addWidget(self.pages_view, stretch=2)
        work_layout.addWidget(source_frame, stretch=2)

        preview_frame = QWidget()
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(1, 1, 1, 1)
        preview_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        preview_layout.addWidget(self.preview_source_label)

        buttons_frame = QWidget()
        buttons_layout = QHBoxLayout(buttons_frame)
        buttons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        buttons_layout.setContentsMargins(1, 1, 1, 1)
        buttons_layout.addWidget(self.add_page_button)
        buttons_layout.addWidget(self.remove_page_button)

        preview_layout.addWidget(buttons_frame, stretch=0)
        preview_layout.addWidget(self.page_view, stretch=1)

        doc_layout.addWidget(work_frame, stretch=0)
        doc_layout.addWidget(preview_frame, stretch=1)

        self.main_layout.addWidget(self.toolbar_frame)
        self.main_layout.addWidget(self.doc_frame)
        self.pages_view.preview_dpi_changed.connect(self.preview_dpi_changed)

    def get_frame(self, orientation=Qt.Orientation.Horizontal):
        frame = QWidget()
        if orientation == Qt.Orientation.Horizontal:
            frame.setLayout(QHBoxLayout())
            frame.layout().setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignCenter)
        else:
            frame.setLayout(QVBoxLayout())
            frame.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        frame.layout().setContentsMargins(1, 1, 1, 1)
        return frame

    def get_toolbar(self):
        button_style_sheet = "* {background:silver} *:hover {background:green; color:white}"
        toolbar_frame = self.get_frame()
        self.open_file_button = QToolButton()
        self.open_file_button.setText("🗁")
        self.open_file_button.clicked.connect(self.open_file)
        self.open_file_button.setToolTip("Open another ")
        self.open_file_button.setStyleSheet(button_style_sheet)

        self.base_column_spin = QSpinBox()
        self.base_column_spin.setValue(self.base_column)

        def base_column_changed(value):
            self.base_column = value

        self.base_column_spin.valueChanged.connect(base_column_changed)

        self.row_margin_spin = QDoubleSpinBox()
        self.row_margin_spin.setSingleStep(0.01)
        self.row_margin_spin.setValue(self.row_margin)

        def row_margin_changed(value):
            self.row_margin = value

        self.row_margin_spin.valueChanged.connect(row_margin_changed)

        self.empty_cells_spin = QSpinBox()
        self.empty_cells_spin.setValue(self.aec)

        def empty_cells_changed(value):
            self.aec = value

        self.empty_cells_spin.valueChanged.connect(empty_cells_changed)
        self.empty_cells_spin.setToolTip("Allowed number of empty cells in row")
        self.file_name_label = QLabel()

        toolbar_frame.layout().addWidget(self.open_file_button)
        toolbar_frame.layout().addWidget(QLabel("Source file:"))
        toolbar_frame.layout().addWidget(self.file_name_label)
        return toolbar_frame

    def open_file(self):
        file_name = QFileDialog.getOpenFileName(caption="Open PDF file", filter="PDF (*.PDF)")[0]
        if file_name:
            self.pdf_file = file_name

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
        self._pdf_file = value
        self._previewing_result = False
        self._preview_row = None
        self.q2ocr.pdf_file = value
        self.refresh_pages_view()
        self.pages_view.set_page(0)
        self.add_page_button.setEnabled(True)
        self.file_name_label.setText(os.path.abspath(value))
        self.result_data = None

    @property
    def base_column(self):
        return self._base_column

    @base_column.setter
    def base_column(self, value):
        self._base_column = value
        self.base_column_spin.setValue(value)

    @property
    def row_margin(self):
        return self._row_margin

    @row_margin.setter
    def row_margin(self, value):
        self._row_margin = value
        self.row_margin_spin.setValue(value)

    def refresh_pages_view(self):
        self.preview_pages.clear()
        for key, value in self.q2ocr.get_preview_pages(self.preview_dpi).items():
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
        if previous_row >= 0 and previous_row < self.pages_model.rowCount() - 1:
            self.pages_view.set_page(previous_row)
        else:
            self.pages_view.set_page(0)

    def preview_page_changed(self, row):
        if row < 0 or self.q2ocr.pdf is None or row >= self.q2ocr.pdf.page_count:
            return
        if not self._previewing_result and self._preview_row == row:
            return
        self._previewing_result = False
        self._preview_row = row
        self.add_page_button.setEnabled(True)
        self.remove_page_button.setEnabled(False)
        self.composed_pages_view.clearSelection()
        self.preview_source_label.setText(f"Source PDF — page {row + 1} of {self.q2ocr.pdf.page_count}")
        self.page_view.set_image(self.q2ocr.get_page_image(row, QImage=QImage, QPixmap=QPixmap))
        # image = QImage()
        # image.loadFromData(self.q2ocr.get_page_image(row))
        # self.page_view.set_image(QPixmap.fromImage(image))

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
            self.q2ocr.get_page_image(
                row,
                dpi=self.dpi,
                QImage=QImage,
                QPixmap=QPixmap,
                document=self.composed_pdf,
            )
        )

    def next_preview_page(self, page):
        if self._previewing_result:
            self.composed_pages_view.next_page(page)
        else:
            self.pages_view.next_page(page)

    def remove_current_page(self):
        row = self._preview_row
        if not self._previewing_result or row is None or row < 0 or row >= self.composed_pdf.page_count:
            return

        self.composed_pdf.delete_page(row)
        self.composed_preview_pages[:] = [
            self.create_composed_preview(page_number)
            for page_number in range(self.composed_pdf.page_count)
        ]
        self.composed_pages_model.refresh()
        self.composed_pages_view.resize_to_content()
        self.composed_page_count_label.setText(f"Result PDF ({self.composed_pdf.page_count} pages)")

        self._preview_row = None
        if self.composed_pdf.page_count:
            self.composed_pages_view.set_page(min(row, self.composed_pdf.page_count - 1))
        else:
            source_row = self.pages_view.currentIndex().row()
            if self.q2ocr.pdf is not None and 0 <= source_row < self.q2ocr.pdf.page_count:
                self.preview_page_changed(source_row)
            else:
                self._previewing_result = False
                self.remove_page_button.setEnabled(False)
                self.preview_source_label.setText("Preview")
                self.page_view.set_image(QPixmap())

    def add_current_page(self):
        if self._previewing_result:
            return
        row = self.pages_view.currentIndex().row()
        if self.q2ocr.pdf is None or row < 0 or row >= self.q2ocr.pdf.page_count:
            return

        self.composed_pdf.insert_pdf(self.q2ocr.pdf, from_page=row, to_page=row)
        preview = self.create_composed_preview(self.composed_pdf.page_count - 1)
        self.composed_preview_pages.append(preview)
        self.composed_pages_model.refresh()
        self.composed_pages_view.resize_to_content()
        self.composed_page_count_label.setText(f"Result PDF ({self.composed_pdf.page_count} pages)")

    def create_composed_preview(self, page_number):
        image = QImage()
        if not image.loadFromData(
            self.q2ocr.get_page_image(page_number, self.preview_dpi, document=self.composed_pdf)
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

    def get_page_count(self):
        return self.pages_view.model().rowCount()

    def get_selected_pages(self):
        return self.pages_view.get_selected_rows()


if __name__ == "__main__":
    app = QApplication([])
    ocr_widget = Q2PdfWidget(dpi=600)
    ocr_widget.pdf_file = "data/Scannen0003.pdf"
    ocr_widget.preview_dpi = 10
    ocr_widget.resize(1000, 1000)
    ocr_widget.move(100, 100)
    ocr_widget.show()
    app.exec()
    sys.exit(0)
