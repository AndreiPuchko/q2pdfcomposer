import fitz
import json
import csv
import ocr_json
import io
from PIL import Image as im
from q2gui.q2app import Q2App
from q2gui.q2app import load_q2engine
from q2gui.q2dialogs import q2wait
from q2gui.q2form import Q2Form
from q2rad.q2utils import open_document
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
)
from PyQt6.QtGui import QKeyEvent, QMouseEvent, QPixmap, QImage, QPen, QCursor
from PyQt6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    Qt,
    QVariant,
    pyqtSignal,
)
import pytesseract

pytesseract.pytesseract.tesseract_cmd = "C:\\Users\\andre\\Desktop\\pdflabels\\Tesseract-OCR\\tesseract.exe"

load_q2engine(globals(), "PyQt6")


class PagesModel(QAbstractTableModel):
    def __init__(self, pdf_pages):
        super().__init__()
        self.pdf_pages = pdf_pages

    def rowCount(self, parent=None):
        return len(self.pdf_pages)

    def columnCount(self, parent=None):
        return 2

    def data(self, index: QModelIndex, role):
        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == 0:
                return self.pdf_pages[index.row()]["number"] + 1
            elif index.column() == 1:
                return ""
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
        elif role == Qt.ItemDataRole.DecorationRole:
            if index.column() == 1:
                return self.pdf_pages[index.row()]["preview"]
        elif role == Qt.ItemDataRole.SizeHintRole:
            if index.column() == 1:
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

    def __init__(self, pdf_pages):
        super().__init__()
        self.pdf_pages = pdf_pages
        # self.horizontalHeader().hide()
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self.verticalHeader().hide()
        # self.setStyleSheet("background:red")

    def setModel(self, model):
        super().setModel(model)
        self.resize_to_content()

    def resize_to_content(self):
        self.resizeColumnsToContents()
        self.resizeRowsToContents()
        w = self.columnWidth(0) + self.columnWidth(1) + self.verticalHeader().width()
        self.setFixedWidth(w)
        # print(self.horizontalHeader().width(), self.width())

    def currentChanged(self, current: QModelIndex, previous: QModelIndex):
        self.row_selected.emit(current.row())
        return super().currentChanged(current, previous)

    def set_current_row(self, row):
        self.setCurrentIndex(self.model().index(row, 0))

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


class Q2PdfComposer(Q2Form):
    def __init__(self, pdf_file=None):
        self.pdf = None
        self.pdf_file = pdf_file
        self.pdf_pages = {}
        self.preview_dpi = 10
        self.image_dpi = 300
        super().__init__("Compose PDF")
        self.lines = json.loads(self.q2_app.settings.get("pdf_composer", "lines", "[100]"))
        self.save_debug_data = False

    def on_init(self):
        self.read_pdf()
        self.base_column = self.q2_app.settings.get("pdf_composer", "base_column", "1")
        self.string_delta = self.q2_app.settings.get("pdf_composer", "string_delta", "59")

        self.pages_model = PagesModel(self.pdf_pages)
        self.pages_preview = PdfPagesPreview(self.pdf_pages)
        self.page_view = PageView()
        self.pages_preview.row_selected.connect(self.preview_changed)
        self.pages_preview.setModel(self.pages_model)

        self.add_control("/")
        self.add_control("/vs")
        self.add_control("/h")
        self.add_control(
            "preview_dpi", "Preview DPI", control="spin", data=self.preview_dpi, valid=self.preview_dpi_valid
        )
        self.add_control(
            "base_column",
            "Base column",
            control="spin",
            datatype="int",
            data=self.base_column,
            valid=self.ocr_settings_valid,
        )
        self.add_control(
            "string_delta",
            "String delta",
            control="spin",
            datatype="int",
            data=self.string_delta,
            valid=self.ocr_settings_valid,
        )
        self.add_control("radio_page", "Pages", control="radio", pic="All;Selected", datatype="int")
        self.add_control(
            "ocr",
            "GO!",
            control="button",
            datalen=5,
            style=" *{background:lime;color:black} *:hover{background:chartreuse}",
            valid=self.ocr,
        )
        self.add_control(
            "save_debug_data",
            control="check",
            pic="Save debug data",
            data="",
            valid=self.ocr_settings_valid,
        )
        self.add_control("/s")
        self.add_control("/")
        self.add_control("/h")
        self.add_control("pages", widget=self.pages_preview)
        self.add_control("page_image", widget=self.page_view, stretch=99)
        self.add_control("/")
        self.maximized = True
        return super().on_init()

    def ocr_settings_valid(self):
        self.base_column = int(self.s.base_column)
        self.string_delta = int(self.s.string_delta)

    def get_lines(self):
        return self.page_view.get_lines()

    def ocr(self):
        selected_rows = self.pages_preview.get_selected_rows()
        boxes = self.page_view.get_boxes()
        k = self.image_dpi / 72
        result = []
        w = q2wait(self.pdf.page_count)
        for page in self.pdf.pages():
            w.step()
            if int(self.s.radio_page) == 2 and page.number not in selected_rows:
                continue
            result.append([])
            print(page.number)
            for index, x in enumerate(boxes):
                print("\tchunk", index)
                clip = (x[0] / k, x[1] / k, x[2] / k, x[3] / k)
                pixmap = page.get_pixmap(
                    dpi=self.image_dpi, alpha=False, colorspace=fitz.Colorspace(fitz.CS_GRAY), clip=clip
                )
                fname = f"temp\\chunk-{index}-page-{page.number}.png"
                # pixmap.save(fname)

                bytes_pixmap = pixmap.tobytes(output="png")

                chunk_data = pytesseract.image_to_data(
                    im.open(io.BytesIO(bytes_pixmap)), output_type=pytesseract.Output.DICT
                )
                result[-1].append(chunk_data)

                if self.save_debug_data:
                    ocr_csv_text = str(pytesseract.image_to_data(im.open(io.BytesIO(bytes_pixmap))))
                    open(f"{fname}.csv", "w").write(ocr_csv_text)
                # txt = str(pytesseract.image_to_string(fname))
                # open(f"{fname}.txt", "w").write(txt)
        w.close()
        print("done")
        if self.save_debug_data:
            json.dump(result, open(f"temp/raw_ocr_data.json", "w"))

        grand_result = ocr_json.json_ocr(
            result, base_column=int(self.base_column), string_delta=int(self.string_delta)
        )
        if self.save_debug_data:
            json.dump(grand_result, open(f"temp\\data.json", "w"))

        result_csv_file_name = "temp\\data.csv"
        csv_writer = csv.DictWriter(
            open(result_csv_file_name, "w", encoding="utf-8"),
            [x for x in grand_result[0]],
            dialect="excel",
            lineterminator="\n",
            delimiter=";",
        )
        csv_writer.writeheader()
        for x in grand_result:
            csv_writer.writerow(x)
        csv_writer = None
        open_document(result_csv_file_name)

    def preview_changed(self, row):
        if row < 0:
            return
        self.page_view.set_image(self.get_page_image(row, dpi=self.image_dpi))

    def preview_dpi_valid(self):
        _dpi = int(self.s.preview_dpi)
        if _dpi < 3 or _dpi > 50:
            self.s.preview_dpi = self.preview_dpi
            return
        self.preview_dpi = _dpi
        self.read_pdf()
        self.pages_model.refresh()
        self.pages_preview.resize_to_content()

    def after_form_show(self):
        self.pages_preview.set_current_row(0)
        self.page_view.restore_lines(self.lines)
        return super().after_form_show()

    def after_form_closed(self):
        self.q2_app.settings.set("pdf_composer", "lines", f"{self.get_lines()}")
        self.q2_app.settings.set("pdf_composer", "base_column", f"{self.base_column}")
        self.q2_app.settings.set("pdf_composer", "string_delta", f"{self.string_delta}")
        return super().after_form_closed()

    def get_page_image(self, page_number, dpi):
        pixmap = self.pdf[page_number].get_pixmap(dpi=dpi, alpha=False)
        image = QImage(
            pixmap.samples_ptr, pixmap.width, pixmap.height, pixmap.stride, QImage.Format.Format_RGB888
        )
        return QPixmap.fromImage(image)

    def read_pdf(self):
        if self.pdf is None:
            self.pdf = fitz.open(self.pdf_file)

        for page in self.pdf.pages():
            # pixmap = page.get_pixmap(dpi=self.dpi, alpha=False)

            # im = QImage(
            #     pixmap.samples_ptr, pixmap.width, pixmap.height, pixmap.stride, QImage.Format.Format_RGB888
            # )
            # pixmap.save("page-%i.png" % page.number)
            # im.save("__page-%i.png" % page.number)
            pix = self.get_page_image(page.number, self.preview_dpi)
            self.pdf_pages[page.number] = {"number": page.number, "preview": pix, "page": page}


class DemoApp(Q2App):

    def on_init(self):
        # self.hide_menubar()
        self.hide_tabbar()
        return super().on_init()

    def on_new_tab(self):
        # form = Q2PdfComposer("data/test1.pdf")
        form = Q2PdfComposer("data/Scannen0001.pdf")
        form.run()
        self.close()


def demo():
    app = DemoApp("Q2Pdf")
    app.run()


if __name__ == "__main__":
    demo()
