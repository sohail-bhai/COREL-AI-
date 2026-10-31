# CorelDRAW X7 Disposable-Document Regression

- **UTC run time:** 2026-10-31T063538591277Z
- **Result:** PASS
- **CorelDRAW version:** Version 17.0.0.491
- **ProgID:** CorelDRAW.Application.17
- **Connection mode:** Dispatch
- **Output directory:** `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T063535307684Z-bulf0osy`
- **Failure:** None

The run created a new synthetic document and did not bind a document that predated the test.
Passing this regression is evidence for the tested environment only; it does not prove visual or print readiness.

| Step | Status | Duration (ms) | Detail |
|---|---|---:|---|
| connect / corel_status | passed | 8.5 | target_document_name=None |
| create_document | passed | 170.74 | target_document_name='Untitled-1', created=True |
| use_active_document | passed | 0.28 | target_document_name='Untitled-1' |
| draw_rectangle | passed | 111.58 | object_name='Live_Rectangle', created=True |
| draw_ellipse | passed | 122.32 | object_name='Live_Ellipse', created=True |
| add_text | passed | 118.12 | object_name='Live_Text', created=True |
| set_fill_color | passed | 117.4 | object_name='Live_Rectangle', updated=True |
| set_outline | passed | 91.63 | object_name='Live_Rectangle', updated=True |
| move_object | passed | 50.96 | object_name='Live_Ellipse', moved=True |
| resize_object | passed | 61.78 | object_name='Live_Ellipse', resized=True |
| set_text_content | passed | 71.67 | object_name='Live_Text', updated=True |
| rename_object | passed | 78.18 | object_name='Live_Ellipse_Renamed', renamed=True |
| duplicate_object | passed | 154.11 | object_name='Live_Rectangle_Copy', duplicated=True |
| create synthetic import fixture | passed | 0.38 | NoneType |
| import_artwork | passed | 162.58 | object_count=1, imported=True |
| list_objects | passed | 156.67 | object_count=5 |
| export_pdf | passed | 1186.36 | path='C:\\Users\\ADMIN\\AppData\\Local\\Temp\\opencode\\corel-live\\run-20261031T063535307684Z-bulf0osy\\disposable-regression.pdf', bytes=391476 |
| save_document | passed | 114.64 | path='C:\\Users\\ADMIN\\AppData\\Local\\Temp\\opencode\\corel-live\\run-20261031T063535307684Z-bulf0osy\\disposable-regression.cdr', bytes=1104026 |

## Artifacts

- CDR: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T063535307684Z-bulf0osy\disposable-regression.cdr` (1104026 bytes)
- PDF: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T063535307684Z-bulf0osy\disposable-regression.pdf` (391476 bytes)
- Synthetic SVG fixture: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T063535307684Z-bulf0osy\synthetic-import.svg`

## Cleanup

- Closed the saved disposable document.

## Manual review still required

- Open the CDR and confirm objects remain editable.
- Inspect the PDF page size, fonts, colors, and rendering.
- Do not mark tools live-verified until this report and the artifacts have been reviewed.
