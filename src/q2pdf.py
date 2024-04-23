from typing import Any
import fitz

from q2gui.q2app import Q2App
from q2gui.q2app import load_q2engine
from q2gui.q2form import Q2Form
from PyQt6.QtWidgets import (
    QTableView,
    QAbstractItemView,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsLineItem,
)
from PyQt6.QtGui import QMouseEvent, QPixmap, QImage, QPen, QTransform
from PyQt6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    Qt,
    QSize,
    QVariant,
    pyqtSignal,
)

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


class PageView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.item = QGraphicsPixmapItem()
        self.scene.addItem(self.item)
        self.lines = []

    def set_image(self, pixmap):
        self.item.setPixmap(pixmap)
        # self.scene.setSceneRect(0, 0, pixmap.width(), pixmap.height())
        # print(self.rect(), self.sceneRect())
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def mousePressEvent(self, event: QMouseEvent):
        pos = self.mapToScene(event.pos())
        # item_at = self.scene.itemAt(pos, QTransform())
        # print(item_at, pos.x(), [x.sceneBoundingRect().x() for x in self.lines])
        if len(self.items(event.pos())) <= 1:
            line: QGraphicsLineItem = self.scene.addLine(
                pos.x(), 0, pos.x(), self.sceneRect().height(), QPen(Qt.GlobalColor.darkBlue, 8)
            )
            line.setFlags(
                QGraphicsLineItem.GraphicsItemFlag.ItemIsMovable
                | QGraphicsLineItem.GraphicsItemFlag.ItemIsSelectable
            )
            self.lines.append(line)
            event.ignore()
        else:
            return super().mousePressEvent(event)

    def resizeEvent(self, event):
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        return super().resizeEvent(event)


class Q2PdfComposer(Q2Form):
    def __init__(self, title="", pdf_file=None):
        self.pdf = None
        self.pdf_file = pdf_file
        self.pdf_pages = {}
        self.preview_dpi = 10
        self.image_dpi = 300
        super().__init__(title)

    def on_init(self):
        self.read_pdf()

        self.pages_model = PagesModel(self.pdf_pages)
        self.pages_preview = PdfPagesPreview(self.pdf_pages)
        self.page_image = PageView()
        self.pages_preview.row_selected.connect(self.preview_changed)
        self.pages_preview.setModel(self.pages_model)

        self.add_control("/")
        self.add_control("/vs")
        self.add_control("/h")
        self.add_control(
            "preview_dpi", "Preview DPI", control="spin", data=self.preview_dpi, valid=self.preview_dpi_valid
        )
        self.add_control(
            "image_dpi", "Image DPI", control="spin", data=self.image_dpi, valid=self.image_dpi_valid
        )
        self.add_control("/")
        self.add_control("/h")
        self.add_control("pages", widget=self.pages_preview)
        self.add_control("page_image", widget=self.page_image, stretch=99)
        self.add_control("/")
        self.maximized = True
        return super().on_init()

    def preview_changed(self, row):
        if row < 0:
            return
        self.page_image.set_image(self.get_page_image(row, dpi=self.image_dpi))

    def image_dpi_valid(self):
        _dpi = int(self.s.image_dpi)
        if _dpi < 3 or _dpi > 50:
            self.s.image_dpi = self.image_dpi
            return

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
        return super().after_form_show()

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
        form = Q2PdfComposer("Compose PDF", "data/test1.pdf")
        form.run()
        self.close()


def demo():
    app = DemoApp("Q2Pdf")
    app.run()


if __name__ == "__main__":
    demo()
