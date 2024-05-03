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
        self.ocr_widget = q2pdfwidget.Q2PdfWidget()
        self.ocr_widget.pdf_file = pdf_file
        self.lines = json.loads(q2app.q2_app.settings.get("pdf_composer", "lines", "[100]"))
        self.base_column = int(q2app.q2_app.settings.get("pdf_composer", "base_column", "1"))
        self.string_delta = int(q2app.q2_app.settings.get("pdf_composer", "string_delta", "59"))
        self.ocr_widget.restore_lines(self.lines)
        self.save_debug_data = False
        super().__init__("Compose PDF")

    def open_pdf(self):
        pdf_file = q2app.q2_app.get_open_file_dialoq("Select PDF document", ".", "PDF (*.pdf)")[0]
        if pdf_file:
            self.ocr_widget.pdf_file = pdf_file

    def on_init(self):
        self.add_control("/")
        self.add_control("/v")
        self.add_control("/h", tag="toolbox")
        self.add_control("select_pdf", "Select PDF file", control="toolbutton", valid=self.open_pdf)
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
        self.add_control("pages", widget=self.ocr_widget)
        self.add_control("/")
        self.maximized = True
        return super().on_init()

    def ocr_settings_valid(self):
        self.base_column = int(self.s.base_column)
        self.string_delta = int(self.s.string_delta)
        self.save_debug_data = self.s.save_debug_data

    def preview_dpi_valid(self):
        _dpi = int(self.s.preview_dpi)
        if _dpi < 8 or _dpi > 50:
            self.s.preview_dpi = self.preview_dpi
            return
        self.preview_dpi = _dpi
        self.ocr_widget.preview_dpi = _dpi

    def ocr(self):
        self.ocr_widget.base_column = self.base_column
        self.ocr_widget.string_delta = self.string_delta
        if int(self.s.radio_page) <= 1:
            pages = [x for x in range(self.ocr_widget.get_page_count())]
        else:
            pages = self.ocr_widget.get_selected_pages()

        w = q2wait(self.ocr_widget.get_ocr_steps(pages))
        csv_file = self.ocr_widget.ocr(pages, progress_callback=lambda: w.step())
        w.close()

        if os.path.isfile(csv_file):
            open_document(csv_file)

    def after_form_closed(self):
        self.q2_app.settings.set("pdf_composer", "lines", f"{self.ocr_widget.get_lines()}")
        self.q2_app.settings.set("pdf_composer", "base_column", f"{self.base_column}")
        self.q2_app.settings.set("pdf_composer", "string_delta", f"{self.string_delta}")
        return super().after_form_closed()


class DemoApp(Q2App):

    def on_init(self):
        # self.hide_menubar()
        # self.hide_tabbar()
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
