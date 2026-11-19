from qtpy.QtCore import QMimeData, QModelIndex, Qt
from qtpy.QtGui import QColor, QPixmap

from q2pdfcomposer.q2pdfcomposer import PagesModel, PdfPagesPreview


def test_pages_model_basic_data_and_flags(qapp):
    pages = [QPixmap(40, 60), QPixmap(50, 70)]
    model = PagesModel(pages)

    assert model.rowCount() == 2
    assert model.columnCount() == 1
    assert model.data(model.index(0, 0), Qt.ItemDataRole.DecorationRole) is pages[0]
    assert isinstance(model.data(model.index(0, 0), Qt.ItemDataRole.BackgroundRole), QColor)
    assert model.flags(model.index(0, 0)) & Qt.ItemFlag.ItemIsSelectable


def test_source_mime_data_and_drag_actions(qapp):
    model = PagesModel([QPixmap(10, 10), QPixmap(10, 10)], allow_dragging=True)
    indexes = [model.index(1, 0), model.index(0, 0)]
    mime = model.mimeData(indexes)

    assert mime.hasFormat(model.SOURCE_PAGES_MIME_TYPE)
    assert bytes(mime.data(model.SOURCE_PAGES_MIME_TYPE)) == b"0,1"
    assert model.supportedDragActions() == Qt.DropAction.CopyAction


def test_reorder_mime_data_and_move_rows(qapp):
    pages = [QPixmap(10, 10), QPixmap(20, 20), QPixmap(30, 30)]
    original_pages = list(pages)
    model = PagesModel(pages, allow_reordering=True)
    model.index(1, 0)

    mime = model.mimeData([model.index(1, 0)])
    assert mime.hasFormat(model.PAGE_ROW_MIME_TYPE)
    assert bytes(mime.data(model.PAGE_ROW_MIME_TYPE)) == b"1"

    reordered = []
    model.rows_reordered.connect(lambda source, destination: reordered.append((source, destination)))
    assert model.moveRows(QModelIndex(), 0, 1, QModelIndex(), 3)
    assert pages == [original_pages[1], original_pages[2], original_pages[0]]
    assert reordered == [(0, 2)]
    assert not model.moveRows(QModelIndex(), -1, 1, QModelIndex(), 1)
    assert not model.moveRows(QModelIndex(), 0, 2, QModelIndex(), 1)


def test_drop_source_pages_emits_destination(qapp):
    model = PagesModel([], allow_reordering=True)
    emitted = []
    model.source_pages_dropped.connect(lambda rows, destination: emitted.append((rows, destination)))
    mime = QMimeData()
    mime.setData(model.SOURCE_PAGES_MIME_TYPE, b"2,0")

    assert model.dropMimeData(mime, Qt.DropAction.CopyAction, 1, 0, QModelIndex())
    assert emitted == [([2, 0], 1)]

    mime.setData(model.SOURCE_PAGES_MIME_TYPE, b"not-a-row")
    assert not model.dropMimeData(mime, Qt.DropAction.CopyAction, 0, 0, QModelIndex())


def test_preview_navigation_and_selection(qapp):
    model = PagesModel([QPixmap(10, 10), QPixmap(20, 20), QPixmap(30, 30)])
    view = PdfPagesPreview()
    view.setModel(model)

    view.set_page(-1)
    assert not view.currentIndex().isValid()
    view.set_page(1)
    assert view.currentIndex().row() == 1
    view.set_page(99)
    assert view.currentIndex().row() == 1

    assert view.get_selected_rows() == [1]
    view.close()
