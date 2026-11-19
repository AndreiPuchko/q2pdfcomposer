# PDF Composer

PDF Composer is a desktop application for assembling PDF documents from selected pages. Open a source PDF, choose pages, arrange and rotate the result, then save it as a new PDF.

![App Screenshot](assets/screenshot.png)

## Features

- Preview source and result pages.
- Add one or multiple selected source pages to the result.
- Drag source pages into the result and reorder result pages by dragging.
- Rotate pages clockwise.
- Remove selected result pages.
- Adjust thumbnail and preview rendering DPI.
- Save the composed document as a PDF.

## Installation

Install a Qt binding separately. Choose **one** of the following:

```bash
python -m pip install PyQt6
```

or

```bash
python -m pip install PySide6
```

Then install PDF Composer directly from GitHub:

```bash
python -m pip install "git+https://github.com/AndreiPuchko/q2pdfcomposer.git"

```

QtPy and PyMuPDF are installed as project dependencies; the Qt binding (PyQt6 or PySide6) must be installed manually as shown above.

## Run

After installation, launch the application with:

```bash
python -m q2pdfcomposer
```

To run from a source checkout instead:

```bash
python q2pdfcomposer/q2pdfcomposer.py
```

## Basic usage

1. Click **Open** or drag a PDF into the window.
2. Select pages in the source list. Use **Add** or drag the selection into the result list.
3. Rearrange result pages by dragging. Rotate or remove selected result pages as needed.
4. Click **Save** and choose an output file.

See [UserManual.MD](UserManual.MD) for detailed controls and keyboard shortcuts.

## Requirements

- Python
- QtPy
- PyMuPDF
- One Qt binding installed separately: PyQt6 or PySide6

## License

No license has been specified yet.
