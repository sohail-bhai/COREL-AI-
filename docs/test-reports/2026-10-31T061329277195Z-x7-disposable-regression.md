# CorelDRAW X7 Disposable-Document Regression

- **UTC run time:** 2026-10-31T061329277195Z
- **Result:** PASS
- **CorelDRAW version:** Version 17.0.0.491
- **ProgID:** CorelDRAW.Application.17
- **Connection mode:** Dispatch
- **Output directory:** `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T061326059546Z-4_gaeoed`
- **Failure:** None

The run created a new synthetic document and did not bind a document that predated the test.
Passing this regression is evidence for the tested environment only; it does not prove visual or print readiness.

| Step | Status | Duration (ms) | Detail |
|---|---|---:|---|
| connect / corel_status | passed | 8.22 | target_document_name=None |
| create_document | passed | 164.25 | target_document_name='Untitled-1', created=True |
| use_active_document | passed | 5.07 | target_document_name='Untitled-1' |
| draw_rectangle | passed | 88.92 | object_name='Live_Rectangle', created=True |
| draw_ellipse | passed | 108.5 | object_name='Live_Ellipse', created=True |
| add_text | passed | 100.77 | object_name='Live_Text', created=True |
| set_fill_color | passed | 118.46 | object_name='Live_Rectangle', updated=True |
| set_outline | passed | 97.89 | object_name='Live_Rectangle', updated=True |
| move_object | passed | 51.13 | object_name='Live_Ellipse', moved=True |
| resize_object | passed | 63.56 | object_name='Live_Ellipse', resized=True |
| set_text_content | passed | 76.4 | object_name='Live_Text', updated=True |
| rename_object | passed | 83.03 | object_name='Live_Ellipse_Renamed', renamed=True |
| duplicate_object | passed | 154.38 | object_name='Live_Rectangle_Copy', duplicated=True |
| create synthetic import fixture | passed | 0.42 | NoneType |
| import_artwork | passed | 161.38 | object_count=1, imported=True |
| list_objects | passed | 147.35 | object_count=5 |
| export_pdf | passed | 1152.61 | path='C:\\Users\\ADMIN\\AppData\\Local\\Temp\\opencode\\corel-live\\run-20261031T061326059546Z-4_gaeoed\\disposable-regression.pdf', bytes=391476 |
| save_document | passed | 125.2 | path='C:\\Users\\ADMIN\\AppData\\Local\\Temp\\opencode\\corel-live\\run-20261031T061326059546Z-4_gaeoed\\disposable-regression.cdr', bytes=1104058 |

## Artifacts

- CDR: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T061326059546Z-4_gaeoed\disposable-regression.cdr` (1104058 bytes)
- PDF: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T061326059546Z-4_gaeoed\disposable-regression.pdf` (391476 bytes)
- Synthetic SVG fixture: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T061326059546Z-4_gaeoed\synthetic-import.svg`

## Cleanup

- Closed the saved disposable document.

## Manual review still required

- Open the CDR and confirm objects remain editable.
- Inspect the PDF page size, fonts, colors, and rendering.
- Do not mark tools live-verified until this report and the artifacts have been reviewed.
