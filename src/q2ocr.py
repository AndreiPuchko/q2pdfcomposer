import fitz
from PIL import Image as im
import io
import csv
import pytesseract


INCH = 2.54


class Q2OCR:
    CSV_FILE = 1
    JSON_DATA = 2

    def __init__(self, dpi=300, progress_callback=None, result_mode=CSV_FILE):
        self._pdf_file = None
        self.pdf = None
        self.dpi = dpi
        self.result_data = None
        self.progress_callback = progress_callback
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

    def set_tesseract_cmd(self, cmd):
        pytesseract.pytesseract.tesseract_cmd = cmd

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

    def ocr_progress_tick(self, arg1=None, arg2=None):
        if self.progress_callback is not None:
            self.progress_callback(arg1, arg2)
        else:
            print(arg1, arg2)

    def extract_rows_from_chunk_data(self, data, row_margin):
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
            if data["top"][row] - _last_top > row_margin:
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
        return res

    def json_ocr(self, data, base_column=1, row_margin=0.5, aec=0):
        grand_result = []
        for page in data:
            page_result = []
            for chunk in page:
                page_result.append(self.extract_rows_from_chunk_data(chunk, row_margin))
            for main_column_row in page_result[base_column - 1]:
                for index, other_column in enumerate(page_result):
                    if index == base_column - 1:
                        continue
                    for other_column_row in other_column:
                        if (
                            other_column_row["top"] >= main_column_row["top"] - self.row_top_margin
                            and other_column_row["top"] <= main_column_row["bottom"] + self.row_bottom_margin
                        ):
                            main_column_row[f"column_{index:04}"] = other_column_row["text"]
                        if f"column_{index:04}" not in main_column_row:
                            main_column_row[f"column_{index:04}"] = ""

                main_column_row[f"column_{base_column-1:04}"] = main_column_row["text"]
                del main_column_row["text"]
                del main_column_row["bottom"]
                del main_column_row["top"]
            for row in page_result[base_column - 1]:
                if len([1 for x in row.values() if len(x.strip()) == 0]) > aec:
                    continue
                grand_result.append(row)
        return grand_result

    def ocr(self, page_numbers=None, lines=[], base_column=1, row_margin=0.5, aec=0, debug=True):
        stripes = [(x, lines[index + 1]) for index, x in enumerate(lines[:-1])]

        page_numbers = self.validate_page_numbers(page_numbers)
        steps_count = len(page_numbers) * len(stripes)
        result = []
        debug_data = []
        count = 0
        self.ocr_progress_tick("start", steps_count)
        for page in self.pdf.pages():
            if page.number not in page_numbers:
                continue
            result.append([])
            for index, stripe_x0_x1 in enumerate(stripes):
                count += 1
                self.ocr_progress_tick(count, steps_count)
                debug_data.append([])
                chunk = {}

                # print("\tchunk", index)
                debug_file_name = f"temp\\chunk-{index}-page-{page.number}"
                chunk["debug_file_name"] = debug_file_name

                clip = (stripe_x0_x1[0] / INCH * 72, 0, stripe_x0_x1[1] / INCH * 72, page.rect.height)
                pixmap = page.get_pixmap(
                    dpi=self.dpi, alpha=False, colorspace=fitz.Colorspace(fitz.CS_GRAY), clip=clip
                )
                if debug:
                    pixmap.save(f"{debug_file_name}.png")
                bytes_pixmap = pixmap.tobytes(output="png")
                chunk["pixmap"] = bytes_pixmap

                chunk_data = pytesseract.image_to_data(
                    im.open(io.BytesIO(bytes_pixmap)),
                    output_type=pytesseract.Output.DICT,
                    config=f"--psm {self.psm}",
                )
                result[-1].append(chunk_data)
                chunk["data"] = chunk_data
                # print(
                #     pytesseract.image_to_string(
                #         im.open(io.BytesIO(bytes_pixmap)),
                #         config=f"--psm {self.psm}",
                #     )
                # )
                debug_data[-1].append(chunk)

                if debug:
                    ocr_csv_text = str(
                        pytesseract.image_to_data(
                            im.open(io.BytesIO(bytes_pixmap)),
                            config=f"--psm {self.psm}",
                        )
                    )
                    chunk["csv"] = ocr_csv_text
                    open(f"{debug_file_name}.csv", "w").write(ocr_csv_text)

        table = self.json_ocr(
            result, base_column=base_column, row_margin=row_margin / INCH * self.dpi, aec=aec
        )
        self.debug_data = debug_data

        if self.result_mode == self.CSV_FILE:
            self.result_data = self.save_csv(table)
        else:
            self.result_data = table

        self.ocr_progress_tick("finish", self.result_data)

        return self.result_data

    def save_csv(self, table):
        result_csv_file_name = "temp\\data.csv"
        csv_writer = csv.DictWriter(
            open(result_csv_file_name, "w", encoding="utf-8"),
            sorted([x for x in table[0]]),
            dialect="excel",
            lineterminator="\n",
            delimiter=";",
        )
        csv_writer.writeheader()
        for x in table:
            csv_writer.writerow(x)
        csv_writer = None
        return result_csv_file_name


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
