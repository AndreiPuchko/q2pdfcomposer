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
        self.ocr_widget = q2pdfwidget.Q2PdfWidget(result_mode=q2pdfwidget.Q2PdfWidget.CSV_FILE)
        self.ocr_widget.pdf_file = pdf_file
        self.progress_bar = None
        super().__init__("Compose PDF")

    def on_init(self):
        self.add_control("pages", widget=self.ocr_widget)
        self.maximized = True
        return super().on_init()


class DemoApp(Q2App):

    def on_init(self):
        return super().on_init()

    def on_new_tab(self):
        form = Q2PdfComposer("data/Scannen0003.pdf")
        form.run()
        self.close()


def demo():
    app = DemoApp("Q2Pdf")
    app.run()


if __name__ == "__main__":
    demo()
