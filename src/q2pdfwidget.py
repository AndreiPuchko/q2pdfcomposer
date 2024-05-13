import sys
import os
import subprocess
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

    def mousePressEvent(self, event: QMouseEvent):
        super().mousePressEvent(event)
        self.mouse_click_pos = event.pos()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        super().mouseReleaseEvent(event)

        x_pos = self.mapToScene(event.pos()).x()
        scene_width = self.sceneRect().width()
        focus_item = self.scene.focusItem()
        if focus_item is None:
            if self.drag_mode:
                self.drag_mode = False
                self.mouse_click_pos = None
                return
            if x_pos > 0 and x_pos < scene_width:
                self.add_line(x_pos)
        else:
            if x_pos < 0 or x_pos > scene_width:
                self.scene.removeItem(focus_item)
                self.lines.pop(self.lines.index(focus_item))
                self.clearFocus()
            else:
                focus_item.setPos(focus_item.pos().x(), 0)
        self.mouse_click_pos = None

    def mouseMoveEvent(self, event: QMouseEvent):
        super().mouseMoveEvent(event)
        item_at_pos = self.itemAt(event.pos())
        if isinstance(item_at_pos, VerticalLine):
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        if event.buttons() == Qt.MouseButton.LeftButton:
            if item_at_pos == self.pdf_image:
                if self.mouse_click_pos is not None:
                    self.drag_mode = True
                    delta = self.mouse_click_pos - event.pos()
                    if self.horizontalScrollBar().isVisible():
                        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + delta.x())
                    if self.verticalScrollBar().isVisible():
                        self.verticalScrollBar().setValue(self.verticalScrollBar().value() + delta.y())
                    self.mouse_click_pos = event.pos()
                    self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_PageDown:
            self.next_page.emit(1)
        elif event.key() == Qt.Key.Key_PageUp:
            self.next_page.emit(-1)
        else:
            if self.scene.focusItem() is not None:
                self.scene.focusItem().keyPressEvent(event)
            else:
                QGraphicsView.keyPressEvent(self, event)

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

    def add_line(self, pos_x):
        self.lines.append(VerticalLine(self.pdf_image, pos_x))

    def restore_lines(self, lines):
        self.lines.clear()
        scene_width = self.sceneRect().width()
        for x in lines:
            x_pos = int(self.dpi / INCH * x)
            if x_pos > 0 and x_pos < scene_width:
                self.add_line(x_pos)

    def get_lines(self):
        return sorted([round(x.pos().toPoint().x() * INCH / self.dpi, 6) for x in self.lines])


class Q2PdfWidget(QWidget):
    ocr_job_done = pyqtSignal(str)
    CSV_FILE = 1
    JSON_DATA = 2

    def __init__(self, ocr_progress_callback=None, result_mode=CSV_FILE):
        super().__init__()

        self._preview_dpi = 10
        self._pdf_file = None
        self.aec = 0

        self._base_column = 1
        self._string_delta = 58
        self.result_mode = result_mode

        self._ocr_progress_callback = ocr_progress_callback

        self.preview_pages = {}
        self.debug_data = None
        self.result_data = None

        self.toolbar_frame = self.get_toolbar()
        self.doc_frame = self.get_frame()

        self.q2ocr = q2ocr.Q2OCR(progress_callback=self.ocr_progress_tick)

        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.main_layout)

        self.pages_view = PdfPagesPreview()
        self.pages_view.row_selected.connect(self.preview_page_changed)
        self.pages_model = PagesModel(self.preview_pages)
        self.pages_view.setModel(self.pages_model)

        self.page_view = PageView(self.q2ocr.dpi)
        self.page_view.next_page.connect(self.pages_view.next_page)
        self.doc_frame.layout().addWidget(self.pages_view, stretch=0)
        self.doc_frame.layout().addWidget(self.page_view, stretch=99)

        self.main_layout.addWidget(self.toolbar_frame)
        self.main_layout.addWidget(self.doc_frame)
        self.pages_view.preview_dpi_changed.connect(self.preview_dpi_changed)

    def set_tesseract_cmd(self, cmd):
        self.q2ocr.set_tesseract_cmd(cmd)

    def set_result_mode(self, result_mode):
        self.result_mode = result_mode

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

        self.string_delta_spin = QSpinBox()
        self.string_delta_spin.setValue(self.string_delta)

        def string_delta_changed(value):
            self.string_delta = value

        self.string_delta_spin.valueChanged.connect(string_delta_changed)

        self.empty_cells_spin = QSpinBox()
        self.empty_cells_spin.setValue(self.aec)

        def empty_cells_changed(value):
            self.aec = value

        self.empty_cells_spin.valueChanged.connect(empty_cells_changed)
        self.empty_cells_spin.setToolTip("Allowed number of empty cells in row")

        self.ocr_all_button = QToolButton()
        self.ocr_all_button.setText("All")
        self.ocr_all_button.clicked.connect(self.ocr_all)
        self.ocr_all_button.setToolTip("Process all the pages ")
        self.ocr_all_button.setStyleSheet(button_style_sheet + "* {background:lightgreen} ")

        self.ocr_sel_button = QToolButton()
        self.ocr_sel_button.setText("Selected")
        self.ocr_sel_button.clicked.connect(self.ocr_selected)
        self.ocr_sel_button.setToolTip("Process only selected pages ")
        self.ocr_sel_button.setStyleSheet(button_style_sheet)

        self.file_name_label = QLabel()

        toolbar_frame.layout().addWidget(self.open_file_button)
        toolbar_frame.layout().addWidget(QLabel("Base column"))
        toolbar_frame.layout().addWidget(self.base_column_spin)
        toolbar_frame.layout().addWidget(QLabel("String delta"))
        toolbar_frame.layout().addWidget(self.string_delta_spin)
        toolbar_frame.layout().addWidget(QLabel("SEC:"))
        toolbar_frame.layout().addWidget(self.empty_cells_spin)
        toolbar_frame.layout().addWidget(QLabel("OCR:"))
        toolbar_frame.layout().addWidget(self.ocr_all_button)
        toolbar_frame.layout().addWidget(self.ocr_sel_button)

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
        self.q2ocr.pdf_file = value
        self.refresh_pages_view()
        self.pages_view.set_page(0)
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
    def string_delta(self):
        return self._string_delta

    @string_delta.setter
    def string_delta(self, value):
        self._string_delta = value
        self.string_delta_spin.setValue(value)

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
        if row < 0:
            return
        self.page_view.set_image(self.q2ocr.get_page_image(row, QImage=QImage, QPixmap=QPixmap))
        # image = QImage()
        # image.loadFromData(self.q2ocr.get_page_image(row))
        # self.page_view.set_image(QPixmap.fromImage(image))

    def restore_lines(self, lines_list=[2, 4]):
        self.page_view.restore_lines(lines_list)

    def get_lines(self):
        return self.page_view.get_lines()

    def get_ocr_steps(self, page_numbers=None):
        page_numbers = self.q2ocr.validate_page_numbers(page_numbers)
        return len(page_numbers) * len(self.get_lines())

    def get_page_count(self):
        return self.pages_view.model().rowCount()

    def get_selected_pages(self):
        return self.pages_view.get_selected_rows()

    def ocr_progress_tick(self, arg1=None, arg2=None):
        if self._ocr_progress_callback is not None:
            self._ocr_progress_callback(arg1, arg2)
        else:
            print(arg1, arg2)

    def ocr_all(self):
        return self.ocr([x for x in range(self.get_page_count())])

    def ocr_selected(self):
        return self.ocr(self.get_selected_pages())

    def ocr(self, page_numbers=None, debug=False):
        if len(self.get_lines()) < 2:
            return
        self.result_data = self.q2ocr.ocr(
            page_numbers,
            self.get_lines(),
            base_column=self.base_column,
            string_delta=self.string_delta,
            aec=self.aec,
            debug=debug,
        )
        self.ocr_job_done.emit(self.result_data)
        open_document(self.result_data)
        # self.ocr_job_done.emit("Done")


if __name__ == "__main__":
    app = QApplication([])
    ocr_widget = Q2PdfWidget()
    ocr_widget.pdf_file = "data/Scannen0003.pdf"
    ocr_widget.set_tesseract_cmd("C:\\Users\\andre\\Desktop\\pdflabels\\Tesseract-OCR\\tesseract.exe")
    ocr_widget.restore_lines([3.1242, 12.2936, 13.656733, 15.206133, 17.873133])
    ocr_widget.preview_dpi = 10
    ocr_widget.ocr_job_done.connect(lambda arg: print(arg, ocr_widget.result_data))
    ocr_widget.resize(1000, 1000)
    ocr_widget.move(100, 100)
    ocr_widget.show()
    app.exec()
    if ocr_widget.result_data:
        open_document(ocr_widget.result_data)
    sys.exit(0)
