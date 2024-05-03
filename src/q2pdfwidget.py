import sys
import fitz
import pytesseract
from PIL import Image as im
import io
import ocr_json


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
    QResizeEvent,
    QWheelEvent,
    QPainter,
)
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QVariant, pyqtSignal, QRectF

pytesseract.pytesseract.tesseract_cmd = "C:\\Users\\andre\\Desktop\\pdflabels\\Tesseract-OCR\\tesseract.exe"


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

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
        return super().hoverEnterEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Left:
            self.moveBy(-1, 0)
        elif event.key() == Qt.Key.Key_Right:
            self.moveBy(1, 0)
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

    def set_image(self, pixmap):
        self.pdf_image.setPixmap(pixmap)
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def mouseReleaseEvent(self, event: QMouseEvent):
        x_pos = self.mapToScene(event.pos()).x()
        width = self.sceneRect().width()
        focus_item = self.scene.focusItem()
        if focus_item is None:
            if x_pos > 0 and x_pos < width:
                self.add_line(x_pos)
        else:
            if x_pos < 0 or x_pos > width:
                self.scene.removeItem(focus_item)
                self.lines.pop(self.lines.index(focus_item))
            else:
                focus_item.setPos(focus_item.pos().x(), 0)
        return super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        self.next_page.emit(-1 if event.angleDelta().y() > 0 else 1)
        return super().wheelEvent(event)

    def restore_lines(self, lines):
        for x in lines:
            self.add_line(x)

    def add_line(self, pos_x):
        self.lines.append(VerticalLine(self.pdf_image, pos_x))
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.setSceneRect(self.pdf_image.boundingRect())
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

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

        self._preview_dpi = 10
        self.image_dpi = 300
        self.base_column = 1
        self.string_delta = 58
        self.pdf_pages = {}
        self.pages_view = PdfPagesPreview()
        self.pages_view.row_selected.connect(self.preview_page_changed)
        self.pages_model = PagesModel(self.pdf_pages)
        self.pages_view.setModel(self.pages_model)

        self.page_view = PageView()
        self.page_view.next_page.connect(self.pages_view.next_page)
        self._pdf_file = None
        self.main_layout.addWidget(self.pages_view, stretch=0)
        self.main_layout.addWidget(self.page_view, stretch=99)

    @property
    def preview_dpi(self):
        return self._preview_dpi

    @preview_dpi.setter
    def preview_dpi(self, value):
        self._preview_dpi = value
        self.refresh_pages_view()

    @property
    def pdf_file(self):
        return self._pdf_file

    @pdf_file.setter
    def pdf_file(self, value):
        self._pdf_file = value
        self.pdf = fitz.open(self._pdf_file)
        self.refresh_pages_view()

    def refresh_pages_view(self):
        for page in self.pdf.pages():
            pix = self.get_page_image(page.number, self.preview_dpi)
            painter = QPainter(pix)
            font = painter.font()
            font.setPointSize(self.preview_dpi)
            painter.setFont(font)
            painter.drawText(QRectF(pix.rect()), Qt.AlignmentFlag.AlignCenter, f"{page.number + 1}")
            self.pdf_pages[page.number] = {"number": page.number, "preview": pix, "page": page}
        self.pages_model.refresh()
        self.pages_view.resize_to_content()
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

    def get_ocr_steps(self):
        return len(self.pages_view.get_selected_rows()) * len(self.page_view.get_boxes())

    def ocr(self, page_numbers=None, debug=False, progress_callback=None):
        boxes = self.page_view.get_boxes()
        k = self.image_dpi / 72

        if page_numbers is None:
            page_numbers = self.pages_view.get_selected_rows()
            print(page_numbers)
        if not isinstance(page_numbers, list):
            page_numbers = [int(page_numbers)]

        result = []

        for page in self.pdf.pages():
            if page.number not in page_numbers:
                continue

            print(page.number)

            for index, x in enumerate(boxes):
                if callable(progress_callback):
                    progress_callback()
                chunk = {}
                result.append(chunk)
                print("\tchunk", index)
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
                chunk["data"] = chunk_data

                if debug:
                    ocr_csv_text = str(pytesseract.image_to_data(im.open(io.BytesIO(bytes_pixmap))))
                    chunk["csv"] = ocr_csv_text

        table = ocr_json.json_ocr(
            [[x["data"] for x in result]], base_column=self.base_column, string_delta=self.string_delta
        )

        return table, result


if __name__ == "__main__":
    app = QApplication([])
    widget = Q2PdfWidget()
    widget.pdf_file = "data/Scannen0001.pdf"
    widget.restore_lines([364, 1416, 1602, 1808, 2117])
    widget.show()
    widget.preview_dpi = 10
    widget.resize(1000, 1000)
    widget.move(100, 100)
    app.exec()
    # print(widget.get_lines())
    print(widget.ocr(debug=False)[0])
    # print(widget.get_ocr_steps())
    sys.exit(0)
