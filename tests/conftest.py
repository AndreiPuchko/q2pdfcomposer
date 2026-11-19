import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import pymupdf as fitz
from qtpy.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def sample_pdf(tmp_path):
    path = tmp_path / "sample.pdf"
    document = fitz.open()
    for number in range(3):
        page = document.new_page(width=200 + number * 10, height=300)
        page.insert_text((20, 40), f"Page {number + 1}")
    document.save(path)
    document.close()
    return path
