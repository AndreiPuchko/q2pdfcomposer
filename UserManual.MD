# PDF Composer User Manual

PDF Composer lets you build a new PDF by selecting pages from a source document, arranging them, rotating them, and exporting the result.

## Main Window

The window contains three main areas:

- **Result PDF** — pages currently included in the output document.
- **Source PDF** — pages from the currently open source file.
- **Preview** — a larger view of the selected source or result page.

/Main window: source pages, result pages, and page preview/

## Open a Source PDF

- Click **Open** and choose a PDF file.
- You can also drag a PDF file into the application.
- Dropping a PDF on the **Result PDF** list opens it as the source and adds all of its pages to the result.
- Dropping a PDF elsewhere in the window opens it as the source without adding its pages.

Opening another source replaces the current source document. Pages already added to the result remain there.
Source thumbnails already included from the same PDF are highlighted, even if you reopen that file during the current session.
When an included source page is shown in the preview while the source list has focus, its matching result thumbnails are highlighted too.
When a result thumbnail has focus and its page is shown in the preview, the matching source thumbnail is outlined in pink.

/Open button and source file/

## Add Pages to the Result

Select one or more pages in the **Source PDF** list, then use **Add**. Pages are added in source-document order.

You can also:

- Double-click a source thumbnail to add that page.
- Drag selected source thumbnails to the desired position in the **Result PDF** list. Multiple selected pages are inserted in source order.
- Use **Space**, **Enter**, **Return**, or **+** while the source page list is focused.
- Use **Enter**, **Return**, or **+** while the page preview is focused.

Use the platform's standard extended-selection gestures (such as **Ctrl-click** or **Shift-click**) to select multiple thumbnails.

/Selecting and adding source pages/

## Arrange and Remove Result Pages

- Drag a result thumbnail to change the page order.
- Select one or more result pages and click **Remove**.
- You can also press **Delete** or **-** while the result list is focused.
- Double-click a result thumbnail to remove it.

The preview shows the selected result page. Removing pages updates the result immediately.

/Reordering and removing result pages/

## Preview, Navigate, and Rotate

Select a thumbnail to show its page in the preview. The navigation controls above the preview let you go to the first, previous, next, or last page, or enter a page number.
The current thumbnail is outlined to distinguish it from other selected pages.

Keyboard and mouse navigation:

- **Page Up** / **Page Down** or **Up** / **Down** move between pages while the preview is focused.
- The mouse wheel over the preview also changes pages.
- **Ctrl + mouse wheel** over the preview zooms in or out.
- When a scrollbar is visible, drag the page to pan around it.

Click the rotate button to rotate the currently previewed page 90 degrees clockwise. A source page's rotation is kept in memory and is carried into the result when that page is added. Rotations made to result pages are included in the exported PDF. The original source file on disk is not modified.

/Page navigation, preview, and rotate control/

## Adjust Rendering DPI

The controls to the right of **Add**, **Remove**, and **Save** change rendering quality:

- **Thumbnails DPI** adjusts the source and result thumbnails. Supported values are 6–49.
- **Preview DPI** adjusts the larger page preview. Supported values are 100–1200, in steps of 50.

Higher DPI can make pages sharper but take longer to render and use more memory.

/Thumbnail and preview DPI controls/

## Export the Result

Click **Save** to choose where to write the result PDF. The button is enabled when the result contains at least one page. If the file name does not end in `.pdf`, the extension is added automatically.

/Save result dialog/

## Requirements

PDF Composer requires QtPy, a supported Qt binding (such as PyQt6 or PySide6), and PyMuPDF. If QtPy is unavailable, the application reports an import error with installation guidance.