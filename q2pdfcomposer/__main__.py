import sys

from q2pdfcomposer import Q2PdfComposer

try:
    import qtpy
except ModuleNotFoundError as error:
    if error.name != "qtpy":
        raise
    raise ImportError(
        "QtPy is required to run PDF Composer. Install it with 'python -m pip install QtPy'."
    ) from error
if not qtpy.API_NAME:
    raise ImportError(
        "QtPy is installed, but no supported Qt binding is available. Install PyQt6 or PySide6."
    )

from qtpy.QtWidgets import QApplication

if __name__ == "__main__":
    app = QApplication([])
    pdf_widget = Q2PdfComposer(dpi=150)
    pdf_widget.resize(1000, 1000)
    pdf_widget.move(100, 100)
    pdf_widget.show()
    app.exec()
    sys.exit(0)
