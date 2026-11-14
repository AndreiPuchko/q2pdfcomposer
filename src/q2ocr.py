import fitz
from PIL import Image as im
import io
import csv
import pytesseract

INCH = 2.54


class Q2OCR:

    def __init__(self, dpi=300):
        self._pdf_file = None
        self.pdf = None
        self.dpi = dpi
        self.result_data = None
        self.psm = 6
        self.row_top_margin = 3
        self.row_bottom_margin = 3

    @property
    def pdf_file(self):
        return self._pdf_file

    @pdf_file.setter
    def pdf_file(self, value):
        self._pdf_file = value
        self.pdf = fitz.open(value)
        self.result_data = None

    def get_page_image(self, page_number, dpi=None, QImage=None, QPixmap=None, document=None):
        if dpi is None:
            dpi = self.dpi
        if document is None:
            document = self.pdf
        pixmap = document[page_number].get_pixmap(dpi=dpi, alpha=False)
        if QImage and QPixmap:
            image = QImage(
                pixmap.samples_ptr, pixmap.width, pixmap.height, pixmap.stride, QImage.Format.Format_RGB888
            )
            return QPixmap.fromImage(image)
        else:
            return pixmap.tobytes("png")

    def validate_page_numbers(self, page_numbers=None):
        if page_numbers is None:
            page_numbers = [p for p in range(self.pdf.page_count)]
        if not isinstance(page_numbers, list):
            page_numbers = [int(page_numbers)]
        page_numbers = [p for p in page_numbers if p >= 0 and p < self.pdf.page_count]
        return page_numbers

    def get_preview_pages(self, preview_dpi):
        preview_pages = {}
        for page in self.pdf.pages():
            pix = self.get_page_image(page.number, preview_dpi)
            preview_pages[page.number] = pix
        return preview_pages
