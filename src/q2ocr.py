import fitz
from PIL import Image as im
import io
import csv
import pytesseract


INCH = 2.54


class Q2OCR:
    CSV_FILE = 1
    JSON_DATA = 2

    def __init__(self, dpi=300, result_mode=CSV_FILE):
        self._pdf_file = None
        self.pdf = None
        self.dpi = dpi
        self.result_data = None
        self.result_mode = result_mode
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

    def get_page_image(self, page_number, dpi=None, QImage=None, QPixmap=None):
        if dpi is None:
            dpi = self.dpi
        pixmap = self.pdf[page_number].get_pixmap(dpi=dpi, alpha=False)
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



if __name__ == "__main__":
    ocr = Q2OCR()
    # ocr.pdf_file = "data/Scannen0003.pdf"

    ocr.pdf_file = (
        "C:/Users/andre/Desktop/dev/exp/pdf/pdf_mupdf/data/MSA_MD- 11244 - ANAHEIM-SANTA ANA-IRVINE, CA.pdf"
    )
    ocr.set_tesseract_cmd("C:\\Users\\andre\\Desktop\\pdflabels\\Tesseract-OCR\\tesseract.exe")
    ocr.dpi = 300
    # ocr.ocr(0, lines=[3.1242, 12.2936, 13.656733, 15.206133, 17.873133], row_margin=0.5, aec=99)
    ocr.ocr(
        0,
        lines=[
            0.6858,
            1.913467,
            3.445933,
            5.1689,
            6.8707,
            9.381067,
            11.104033,
            13.6525,
            15.7607,
            17.8689,
            19.947467,
            22.064133,
            24.1681,
            26.1747,
            28.0035,
        ],
        row_margin=0.5,
        aec=99,
        base_column=5,
    )
