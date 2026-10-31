# CorelDRAW X7 Disposable-Document Regression

- **UTC run time:** 2026-10-31T044900929152Z
- **Result:** PASS
- **CorelDRAW version:** Version 17.0.0.491
- **ProgID:** CorelDRAW.Application.17
- **Connection mode:** Dispatch
- **Output directory:** `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T044856293939Z-6e0j198o`
- **Failure:** None

The run created a new synthetic document and did not bind a document that predated the test.
Passing this regression is evidence for the tested environment only; it does not prove visual or print readiness.

| Step | Status | Duration (ms) | Detail |
|---|---|---:|---|
| connect / corel_status | passed | 1617.93 | target_document_name=None |
| create_document | passed | 326.3 | target_document_name='Untitled-1', created=True |
| use_active_document | passed | 6.44 | target_document_name='Untitled-1' |
| draw_rectangle | passed | 143.99 | object_name='Live_Rectangle', created=True |
| draw_ellipse | passed | 108.8 | object_name='Live_Ellipse', created=True |
| add_text | passed | 181.56 | object_name='Live_Text', created=True |
| set_fill_color | passed | 121.76 | object_name='Live_Rectangle', updated=True |
| set_outline | passed | 86.84 | object_name='Live_Rectangle', updated=True |
| move_object | passed | 49.37 | object_name='Live_Ellipse', moved=True |
| resize_object | passed | 58.72 | object_name='Live_Ellipse', resized=True |
| set_text_content | passed | 68.98 | object_name='Live_Text', updated=True |
| rename_object | passed | 77.21 | object_name='Live_Ellipse_Renamed', renamed=True |
| duplicate_object | passed | 146.52 | object_name='Live_Rectangle_Copy', duplicated=True |
| create synthetic import fixture | passed | 0.42 | NoneType |
| import_artwork | passed | 156.43 | object_count=1, imported=True |
| list_objects | passed | 157.55 | object_count=5 |
| export_pdf | passed | 1168.77 | path='C:\\Users\\ADMIN\\AppData\\Local\\Temp\\opencode\\corel-live\\run-20261031T044856293939Z-6e0j198o\\disposable-regression.pdf', bytes=391476 |
| save_document | passed | 147.82 | path='C:\\Users\\ADMIN\\AppData\\Local\\Temp\\opencode\\corel-live\\run-20261031T044856293939Z-6e0j198o\\disposable-regression.cdr', bytes=1104027 |

## Artifacts

- CDR: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T044856293939Z-6e0j198o\disposable-regression.cdr` (1104027 bytes)
- PDF: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T044856293939Z-6e0j198o\disposable-regression.pdf` (391476 bytes)
- Synthetic SVG fixture: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T044856293939Z-6e0j198o\synthetic-import.svg`

## Cleanup

- Closed the saved disposable document.

## Manual review still required

- Open the CDR and confirm objects remain editable.
- Inspect the PDF page size, fonts, colors, and rendering.
- Do not mark tools live-verified until this report and the artifacts have been reviewed.
