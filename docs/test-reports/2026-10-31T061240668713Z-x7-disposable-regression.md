# CorelDRAW X7 Disposable-Document Regression

- **UTC run time:** 2026-10-31T061240668713Z
- **Result:** PASS
- **CorelDRAW version:** Version 17.0.0.491
- **ProgID:** CorelDRAW.Application.17
- **Connection mode:** Dispatch
- **Output directory:** `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T061235733739Z-vcz23ero`
- **Failure:** None

The run created a new synthetic document and did not bind a document that predated the test.
Passing this regression is evidence for the tested environment only; it does not prove visual or print readiness.

| Step | Status | Duration (ms) | Detail |
|---|---|---:|---|
| connect / corel_status | passed | 1748.78 | target_document_name=None |
| create_document | passed | 318.72 | target_document_name='Untitled-1', created=True |
| use_active_document | passed | 10.27 | target_document_name='Untitled-1' |
| draw_rectangle | passed | 175.82 | object_name='Live_Rectangle', created=True |
| draw_ellipse | passed | 113.19 | object_name='Live_Ellipse', created=True |
| add_text | passed | 197.32 | object_name='Live_Text', created=True |
| set_fill_color | passed | 116.49 | object_name='Live_Rectangle', updated=True |
| set_outline | passed | 210.43 | object_name='Live_Rectangle', updated=True |
| move_object | passed | 48.7 | object_name='Live_Ellipse', moved=True |
| resize_object | passed | 61.45 | object_name='Live_Ellipse', resized=True |
| set_text_content | passed | 57.64 | object_name='Live_Text', updated=True |
| rename_object | passed | 97.93 | object_name='Live_Ellipse_Renamed', renamed=True |
| duplicate_object | passed | 140.98 | object_name='Live_Rectangle_Copy', duplicated=True |
| create synthetic import fixture | passed | 0.43 | NoneType |
| import_artwork | passed | 150.55 | object_count=1, imported=True |
| list_objects | passed | 164.83 | object_count=5 |
| export_pdf | passed | 1172.31 | path='C:\\Users\\ADMIN\\AppData\\Local\\Temp\\opencode\\corel-live\\run-20261031T061235733739Z-vcz23ero\\disposable-regression.pdf', bytes=391476 |
| save_document | passed | 143.49 | path='C:\\Users\\ADMIN\\AppData\\Local\\Temp\\opencode\\corel-live\\run-20261031T061235733739Z-vcz23ero\\disposable-regression.cdr', bytes=1103999 |

## Artifacts

- CDR: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T061235733739Z-vcz23ero\disposable-regression.cdr` (1103999 bytes)
- PDF: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T061235733739Z-vcz23ero\disposable-regression.pdf` (391476 bytes)
- Synthetic SVG fixture: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T061235733739Z-vcz23ero\synthetic-import.svg`

## Cleanup

- Closed the saved disposable document.

## Manual review still required

- Open the CDR and confirm objects remain editable.
- Inspect the PDF page size, fonts, colors, and rendering.
- Do not mark tools live-verified until this report and the artifacts have been reviewed.
