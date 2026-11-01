# CorelDRAW X7 Disposable-Document Regression

- **UTC run time:** 2026-11-01T030412340149Z
- **Result:** PASS
- **CorelDRAW version:** Version 17.0.0.491
- **ProgID:** CorelDRAW.Application.17
- **Connection mode:** Dispatch
- **Output directory:** `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261101T030409182743Z-v1btp_g4`
- **Failure:** None

The run created a new synthetic document and did not bind a document that predated the test.
Passing this regression is evidence for the tested environment only; it does not prove visual or print readiness.

| Step | Status | Duration (ms) | Detail |
|---|---|---:|---|
| connect / corel_status | passed | 6.81 | target_document_name=None |
| create_document | passed | 150.8 | target_document_name='Untitled-1', created=True |
| use_active_document | passed | 4.42 | target_document_name='Untitled-1' |
| draw_rectangle | passed | 89.83 | object_name='Live_Rectangle', created=True |
| draw_ellipse | passed | 101.63 | object_name='Live_Ellipse', created=True |
| add_text | passed | 100.63 | object_name='Live_Text', created=True |
| set_fill_color | passed | 111.69 | object_name='Live_Rectangle', updated=True |
| set_outline | passed | 89.16 | object_name='Live_Rectangle', updated=True |
| move_object | passed | 49.4 | object_name='Live_Ellipse', moved=True |
| resize_object | passed | 63.32 | object_name='Live_Ellipse', resized=True |
| set_text_content | passed | 71.78 | object_name='Live_Text', updated=True |
| rename_object | passed | 83.25 | object_name='Live_Ellipse_Renamed', renamed=True |
| duplicate_object | passed | 135.62 | object_name='Live_Rectangle_Copy', duplicated=True |
| create synthetic import fixture | passed | 0.38 | NoneType |
| import_artwork | passed | 159.45 | object_count=1, imported=True |
| list_objects | passed | 157.12 | object_count=5 |
| export_pdf | passed | 1153.44 | path='C:\\Users\\ADMIN\\AppData\\Local\\Temp\\opencode\\corel-live\\run-20261101T030409182743Z-v1btp_g4\\disposable-regression.pdf', bytes=391479 |
| save_document | passed | 123.09 | path='C:\\Users\\ADMIN\\AppData\\Local\\Temp\\opencode\\corel-live\\run-20261101T030409182743Z-v1btp_g4\\disposable-regression.cdr', bytes=1104049 |

## Artifacts

- CDR: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261101T030409182743Z-v1btp_g4\disposable-regression.cdr` (1104049 bytes)
- PDF: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261101T030409182743Z-v1btp_g4\disposable-regression.pdf` (391479 bytes)
- Synthetic SVG fixture: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261101T030409182743Z-v1btp_g4\synthetic-import.svg`

## Cleanup

- Closed the saved disposable document.

## Manual review still required

- Open each generated CDR and confirm objects remain editable.
- Inspect each generated PDF for page size, fonts, colors, and rendering.
- Do not mark tools live-verified until this report and the artifacts have been reviewed.
