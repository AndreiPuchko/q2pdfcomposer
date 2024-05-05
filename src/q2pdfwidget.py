import sys
import fitz
import pytesseract
from PIL import Image as im
import io
import csv


from PyQt6.QtWidgets import (
    QGraphicsSceneHoverEvent,
    QTableView,
    QAbstractItemView,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsLineItem,
    QApplication,
    QHBoxLayout,
    QWidget,
)
from PyQt6.QtGui import (
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
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QVariant, pyqtSignal, QRectF, QPoint

pytesseract.pytesseract.tesseract_cmd = "C:\\Users\\andre\\Desktop\\pdflabels\\Tesseract-OCR\\tesseract.exe"


def extract_rows_from_chunk_data(data, string_delta):
    res = []

    row_count = len(data["level"])

    # for key, value in data.items():
    _text = ""
    _top = 999999999999
    _bottom = 0
    _last_top = 0
    for row in range(row_count):
        if data["level"][row] != 5:
            continue
        if data["top"][row] < _last_top:
            continue
        if data["top"][row] - _last_top > string_delta:
            res.append({"text": _text.strip(), "top": _top, "bottom": _bottom})
            _text = ""
            _top = 999999999999
            _bottom = 0
        if len(data["text"][row]) > 1:
            _text += " " + data["text"][row]
            _top = min(data["top"][row], _top)
            _bottom = max(data["top"][row] + data["height"][row], _bottom)
            _last_top = data["top"][row]
    res.append({"text": _text.strip(), "top": _top, "bottom": _bottom})
    # for x in res:
    #     print(x['top'], x["text"][:100])
    return res


def json_ocr(data, base_column=1, string_delta=59):
    grand_result = []
    for page in data:
        page_result = []
        for chunk in page:
            page_result.append(extract_rows_from_chunk_data(chunk, string_delta))
        for main_column_row in page_result[base_column - 1]:
            for index, other_column in enumerate(page_result):
                if index == base_column - 1:
                    continue
                for other_column_row in other_column:
                    if (
                        other_column_row["top"] >= main_column_row["top"]
                        and other_column_row["top"] <= main_column_row["bottom"]
                    ):
                        main_column_row[f"other_column_{index}"] = other_column_row["text"]
                    if f"other_column_{index}" not in main_column_row:
                        main_column_row[f"other_column_{index}"] = ""
            del main_column_row["bottom"]
            del main_column_row["top"]
        for row in page_result[base_column - 1]:
            # if len([1 for x in row.values() if len(x.strip())==0]) <= 1:
            grand_result.append(row)
    return grand_result


# if __name__ == "__main__":
#     data = json.load(open("temp/raw_ocr_data.json"))
#     rez = json_ocr(data)
#     print(rez[2])


class PagesModel(QAbstractTableModel):
    def __init__(self, pdf_pages):
        super().__init__()
        self.pdf_pages = pdf_pages

    def rowCount(self, parent=None):
        return len(self.pdf_pages)

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
                return self.pdf_pages[index.row()]["preview"]
        elif role == Qt.ItemDataRole.SizeHintRole:
            if index.column() == 0:
                return self.pdf_pages[index.row()]["preview"].size()
        return QVariant()

    def headerData(self, section: int, orientation: Qt.Orientation, role):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if section == 0:
                return "#"
            elif section == 1:
                return "Thumbnail"
        elif orientation == Qt.Orientation.Vertical:
            if role == Qt.ItemDataRole.DisplayRole:
                return QVariant(section + 1)
            elif role == Qt.ItemDataRole.TextAlignmentRole:
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
        else:
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
        self.setZValue(2)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
            | QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges
        )
        self.setPen(QPen(Qt.GlobalColor.darkBlue, 8))
        self.setParentItem(parent_item)
        self.setAcceptHoverEvents(True)

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

    def __init__(self):
        super().__init__()
        self.scene: QGraphicsScene = QGraphicsScene()
        self.setScene(self.scene)
        self.pdf_image = QGraphicsPixmapItem()
        self.scene.addItem(self.pdf_image)
        self.setBackgroundBrush(Qt.GlobalColor.lightGray)
        self.lines = []
        self.mouse_click_pos = None
        self.drag_mode = False

    def set_image(self, pixmap):
        self.pdf_image.setPixmap(pixmap)
        self.setSceneRect(self.pdf_image.boundingRect())

    def showEvent(self, event: QShowEvent | None) -> None:
        super().showEvent(event)
        self.fitInView(self.pdf_image, Qt.AspectRatioMode.KeepAspectRatio)

    def mousePressEvent(self, event: QMouseEvent):
        self.mouse_click_pos = event.pos()
        return super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

        x_pos = self.mapToScene(event.pos()).x()
        width = self.sceneRect().width()
        focus_item = self.scene.focusItem()
        if focus_item is None:
            if self.drag_mode:
                self.drag_mode = False
                self.mouse_click_pos = None
                return
            if x_pos > 0 and x_pos < width:
                self.add_line(x_pos)
        else:
            if x_pos < 0 or x_pos > width:
                self.scene.removeItem(focus_item)
                self.lines.pop(self.lines.index(focus_item))
            else:
                focus_item.setPos(focus_item.pos().x(), 0)
        self.mouse_click_pos = None
        return super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if self.drag_mode:
            self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        if isinstance(self.itemAt(event.pos()), VerticalLine):
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
            super().mouseMoveEvent(event)
        elif self.scene.focusItem() is None:
            if self.mouse_click_pos is not None:
                self.drag_mode = True
                delta = self.mouse_click_pos - event.pos()
                if self.horizontalScrollBar().isVisible():
                    self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + delta.x())
                if self.verticalScrollBar().isVisible():
                    self.verticalScrollBar().setValue(self.verticalScrollBar().value() + delta.y())
                self.mouse_click_pos = event.pos()
                self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
            else:
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        else:
            super().mouseMoveEvent(event)

    def ensure_fit_in(self):
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
            self.ensure_fit_in()
        # return super().wheelEvent(event)

    def restore_lines(self, lines):
        for x in lines:
            self.add_line(x)

    def add_line(self, pos_x):
        self.lines.append(VerticalLine(self.pdf_image, pos_x))
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.ensure_fit_in()

    def get_lines(self):
        return sorted([x.pos().toPoint().x() for x in self.lines])

    def get_boxes(self):
        lines = self.get_lines()
        boxes = []
        for x in range(len(lines) - 1):
            boxes.append([lines[x], 0, lines[x + 1], int(self.pdf_image.boundingRect().height())])
        return boxes


class Q2PdfWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.main_layout = QHBoxLayout()
        self.setLayout(self.main_layout)
        self.main_layout.setContentsMargins(1, 1, 1, 1)
        self.meta = {}

        self._preview_dpi = 10
        self.image_dpi = 300
        self.base_column = 1
        self.string_delta = 58
        self.pdf_pages = {}
        self.debug_data = None
        self.pages_view = PdfPagesPreview()
        self.pages_view.row_selected.connect(self.preview_page_changed)
        self.pages_model = PagesModel(self.pdf_pages)
        self.pages_view.setModel(self.pages_model)

        self.page_view = PageView()
        self.page_view.next_page.connect(self.pages_view.next_page)
        self._pdf_file = None
        self.main_layout.addWidget(self.pages_view, stretch=0)
        self.main_layout.addWidget(self.page_view, stretch=99)
        self.pages_view.preview_dpi_changed.connect(self.preview_dpi_changed)

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
        self.pdf = fitz.open(self._pdf_file)
        self.refresh_pages_view()
        self.pages_view.set_page(0)

    def refresh_pages_view(self):
        for page in self.pdf.pages():
            pix = self.get_page_image(page.number, self.preview_dpi)
            painter = QPainter(pix)
            font = painter.font()
            font.setPointSize(self.preview_dpi)
            painter.setFont(font)
            painter.drawText(QRectF(pix.rect()), Qt.AlignmentFlag.AlignCenter, f"{page.number + 1}")
            self.pdf_pages[page.number] = {"number": page.number, "preview": pix, "page": page}
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
        self.page_view.set_image(self.get_page_image(row, dpi=self.image_dpi))

    def get_page_image(self, page_number, dpi):
        pixmap = self.pdf[page_number].get_pixmap(dpi=dpi, alpha=False)
        image = QImage(
            pixmap.samples_ptr, pixmap.width, pixmap.height, pixmap.stride, QImage.Format.Format_RGB888
        )
        return QPixmap.fromImage(image)

    def restore_lines(self, lines_list=[100, 200]):
        self.page_view.restore_lines(lines_list)

    def get_lines(self):
        return self.page_view.get_lines()

    def get_ocr_steps(self, page_numbers=None):
        if page_numbers is None:
            page_numbers = self.pages_view.get_selected_rows()
        if not isinstance(page_numbers, list):
            page_numbers = [int(page_numbers)]
        return len(page_numbers) * len(self.page_view.get_boxes())

    def get_page_count(self):
        return self.pages_view.model().rowCount()

    def get_selected_pages(self):
        return self.pages_view.get_selected_rows()

    def ocr(self, page_numbers=None, debug=False, progress_callback=None, save_csv_file=True):
        boxes = self.page_view.get_boxes()
        k = self.image_dpi / 72

        if page_numbers is None:
            page_numbers = self.pages_view.get_selected_rows()
        if not isinstance(page_numbers, list):
            page_numbers = [int(page_numbers)]

        result = []
        debug_data = []

        for page in self.pdf.pages():
            if page.number not in page_numbers:
                continue

            result.append([])

            for index, x in enumerate(boxes):
                if callable(progress_callback):
                    progress_callback()
                debug_data.append([])
                chunk = {}

                # print("\tchunk", index)
                debug_file_name = f"temp\\chunk-{index}-page-{page.number}"
                chunk["debug_file_name"] = debug_file_name

                clip = (x[0] / k, x[1] / k, x[2] / k, x[3] / k)
                pixmap = page.get_pixmap(
                    dpi=self.image_dpi, alpha=False, colorspace=fitz.Colorspace(fitz.CS_GRAY), clip=clip
                )
                # if debug:
                #     pixmap.save(f"{debug_file_name}.png")

                bytes_pixmap = pixmap.tobytes(output="png")
                chunk["pixmap"] = bytes_pixmap

                chunk_data = pytesseract.image_to_data(
                    im.open(io.BytesIO(bytes_pixmap)), output_type=pytesseract.Output.DICT
                )
                result[-1].append(chunk_data)
                chunk["data"] = chunk_data
                debug_data[-1].append(chunk)

                if debug:
                    ocr_csv_text = str(pytesseract.image_to_data(im.open(io.BytesIO(bytes_pixmap))))
                    chunk["csv"] = ocr_csv_text

        table = json_ocr(result, base_column=self.base_column, string_delta=self.string_delta)
        self.debug_data = debug_data
        if save_csv_file:
            return self.save_csv(table)
        else:
            return table

    def save_csv(self, table):
        result_csv_file_name = "temp\\data.csv"
        csv_writer = csv.DictWriter(
            open(result_csv_file_name, "w", encoding="utf-8"),
            [x for x in table[0]],
            dialect="excel",
            lineterminator="\n",
            delimiter=";",
        )
        csv_writer.writeheader()
        for x in table:
            csv_writer.writerow(x)
        csv_writer = None
        return result_csv_file_name

        # open_document(result_csv_file_name)


if __name__ == "__main__":
    app = QApplication([])
    widget = Q2PdfWidget()
    widget.pdf_file = "data/Scannen0001.pdf"
    widget.restore_lines([364, 1416, 1602, 1808, 2117])
    widget.preview_dpi = 10
    widget.resize(1000, 1000)
    widget.move(100, 100)
    widget.show()
    app.exec()
    # print(widget.get_lines())
    # print(widget.ocr())

    # print(widget.get_ocr_steps())
    sys.exit(0)
