import os
from unittest.mock import patch

import pymupdf as fitz
import pytest
from qtpy.QtCore import QMimeData, QModelIndex, Qt, QUrl
from qtpy.QtCore import QItemSelectionModel
from qtpy.QtGui import QColor, QPixmap

from q2pdfcomposer.q2pdfcomposer import (
    PagesModel,
    PdfPagesPreview,
    Q2PdfComposer,
    SourcePages,
)


def test_source_pages_lazy_preview(qapp):
    composer = Q2PdfComposer()
    composer.pdf = fitz.open()
    composer.pdf.new_page(width=200, height=300)

    created = []
    composer.create_source_preview_page = lambda row: created.append(row) or QPixmap(10, 10)
    pages = SourcePages(composer)
    pages.update({0: None})

    assert pages[0] is pages[0]
    assert created == [0]
    assert pages.size_hint(0).width() > 0
    assert pages.size_hint(0).height() > 0

    pages.clear()
    assert len(pages) == 0
    assert pages._size_hints == {}
    composer.pdf.close()
    composer.close()


@pytest.fixture
def composer(qapp, sample_pdf):
    widget = Q2PdfComposer(str(sample_pdf), dpi=100)
    yield widget
    if widget.pdf is not None:
        widget.pdf.close()
    widget.composed_pdf.close()
    widget.close()


def test_load_pdf_and_page_navigation(composer):
    assert composer.pdf.page_count == 3
    assert composer.pdf_file.endswith("sample.pdf")
    assert composer._preview_row == 0
    assert composer.add_page_button.isEnabled()

    composer.go_to_preview_page(2)
    assert composer._preview_row == 2
    composer.go_to_last_preview_page()
    assert composer._preview_row == 2
    composer.next_preview_page(-1)
    assert composer._preview_row == 1


def test_add_rotate_remove_and_save_result(composer, tmp_path):
    selection = composer.source_pages_view.selectionModel()
    selection.select(composer.source_pages_model.index(0, 0), QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    selection.select(composer.source_pages_model.index(2, 0), QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    composer.add_selected_pages()

    assert composer.composed_pdf.page_count == 2
    assert composer.save_result_button.isEnabled()

    composer.preview_composed_page_changed(0)
    original_rotation = composer.composed_pdf[0].rotation
    composer.rotate_preview_page()
    assert composer.composed_pdf[0].rotation == (original_rotation + 90) % 360

    composer.composed_pages_view.selectRow(0)
    composer.remove_selected_pages()
    assert composer.composed_pdf.page_count == 1

    output = tmp_path / "result.pdf"
    with patch(
        "q2pdfcomposer.q2pdfcomposer.QFileDialog.getSaveFileName",
        return_value=(str(output), "PDF files (*.pdf)"),
    ):
        composer.save_result()

    assert output.exists()
    saved = fitz.open(output)
    assert saved.page_count == 1
    saved.close()


def test_remove_last_composed_page_resets_preview(composer):
    composer.add_source_page(0)
    assert composer.composed_pdf.page_count == 1
    composer.preview_composed_page_changed(0)

    composer.remove_selected_pages()

    assert composer.composed_pdf.page_count == 0
    assert not composer.save_result_button.isEnabled()
    assert not composer.remove_page_button.isEnabled()


def test_insert_and_reorder_composed_pages(composer):
    composer.insert_source_pages_at([1, 0], 0)
    assert composer.composed_pdf.page_count == 2

    composer.preview_composed_page_changed(0)
    composer.reorder_composed_pages(0, 1)

    assert composer.composed_pdf.page_count == 2
    assert len(composer.composed_preview_pages) == 2


def test_preview_dpi_bounds(composer):
    assert composer.preview_dpi == 10
    composer.preview_dpi = 5
    assert composer.preview_dpi == 10
    composer.preview_dpi = 50
    assert composer.preview_dpi == 10
    composer.preview_dpi = 20
    assert composer.preview_dpi == 20


def test_get_page_image_requires_document(composer):
    with pytest.raises(RuntimeError, match="No PDF document"):
        composer.pdf = None
        composer.get_page_image(0)


def test_dropped_pdf_path_accepts_only_single_local_pdf(tmp_path):
    mime = QMimeData()
    pdf = tmp_path / "drop.pdf"
    pdf.write_bytes(b"%PDF")
    mime.setUrls([QUrl.fromLocalFile(str(pdf))])
    assert os.path.normpath(Q2PdfComposer.dropped_pdf_path(mime)) == os.path.normpath(str(pdf))

    mime.setUrls([QUrl("https://example.com/file.pdf")])
    assert Q2PdfComposer.dropped_pdf_path(mime) is None
