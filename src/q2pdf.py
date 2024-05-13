import json
import os
import q2pdfwidget

from q2gui.q2app import Q2App
from q2gui.q2app import load_q2engine
from q2gui.q2dialogs import q2wait
from q2gui.q2form import Q2Form
from q2rad.q2utils import open_document
from q2gui.q2app import q2app

load_q2engine(globals(), "PyQt6")


class Q2PdfComposer(Q2Form):
    def __init__(self, pdf_file=None):
        self.pdf = None
        self.pdf_file = pdf_file
        self.preview_dpi = 10
        self.image_dpi = 300
        self.ocr_widget = q2pdfwidget.Q2PdfWidget(
            self.progress_callback, result_mode=q2pdfwidget.Q2PdfWidget.CSV_FILE
        )
        self.ocr_widget.set_tesseract_cmd("C:\\Users\\andre\\Desktop\\pdflabels\\Tesseract-OCR\\tesseract.exe")
        self.ocr_widget.pdf_file = pdf_file
        self.ocr_widget.base_column = int(q2app.q2_app.settings.get("pdf_composer", "base_column", "1"))
        self.ocr_widget.row_margin = float(q2app.q2_app.settings.get("pdf_composer", "row_margin", "0.5"))
        self.ocr_widget.restore_lines(
            json.loads(q2app.q2_app.settings.get("pdf_composer", "lines", "[2, 4]"))
        )

        self.progress_bar = None
        super().__init__("Compose PDF")

    def on_init(self):
        self.add_control("pages", widget=self.ocr_widget)
        self.maximized = True
        return super().on_init()

    def progress_callback(self, arg1, arg2):
        if arg1 == "start":
            self.progress_bar = q2wait(arg2)
        elif arg1 == "finish":
            self.progress_bar.close()
            if os.path.isfile(arg2):
                open_document(arg2)
        else:
            self.progress_bar.step(arg1)

    def after_form_closed(self):
        self.q2_app.settings.set("pdf_composer", "lines", f"{self.ocr_widget.get_lines()}")
        self.q2_app.settings.set("pdf_composer", "base_column", f"{self.ocr_widget.base_column}")
        self.q2_app.settings.set("pdf_composer", "row_margin", f"{self.ocr_widget.row_margin}")
        return super().after_form_closed()


class DemoApp(Q2App):

    def on_init(self):
        # self.hide_menubar()
        # self.hide_tabbar()
        return super().on_init()

    def on_new_tab(self):
        # form = Q2PdfComposer("data/test1.pdf")
        form = Q2PdfComposer("data/Scannen0003.pdf")
        form.run()
        self.close()


def demo():
    app = DemoApp("Q2Pdf")
    app.run()


if __name__ == "__main__":
    demo()
