# CorelDRAW X7 Disposable-Document Regression

- **UTC run time:** 2026-10-31T173920767391Z
- **Result:** PASS
- **CorelDRAW version:** Version 17.0.0.491
- **ProgID:** CorelDRAW.Application.17
- **Connection mode:** Dispatch
- **Output directory:** `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T173917430222Z-7h_5dv73`
- **Failure:** None

The run created a new synthetic document and did not bind a document that predated the test.
Passing this regression is evidence for the tested environment only; it does not prove visual or print readiness.

| Step | Status | Duration (ms) | Detail |
|---|---|---:|---|
| connect / corel_status | passed | 6.66 | target_document_name=None |
| create_document | passed | 172.81 | target_document_name='Untitled-1', created=True |
| use_active_document | passed | 4.36 | target_document_name='Untitled-1' |
| draw_rectangle | passed | 100.32 | object_name='Live_Rectangle', created=True |
| draw_ellipse | passed | 112.62 | object_name='Live_Ellipse', created=True |
| add_text | passed | 106.7 | object_name='Live_Text', created=True |
| set_fill_color | passed | 120.46 | object_name='Live_Rectangle', updated=True |
| set_outline | passed | 92.59 | object_name='Live_Rectangle', updated=True |
| move_object | passed | 49.29 | object_name='Live_Ellipse', moved=True |
| resize_object | passed | 63.28 | object_name='Live_Ellipse', resized=True |
| set_text_content | passed | 74.51 | object_name='Live_Text', updated=True |
| rename_object | passed | 82.75 | object_name='Live_Ellipse_Renamed', renamed=True |
| duplicate_object | passed | 158.56 | object_name='Live_Rectangle_Copy', duplicated=True |
| create synthetic import fixture | passed | 0.45 | NoneType |
| import_artwork | passed | 202.77 | object_count=1, imported=True |
| list_objects | passed | 150.49 | object_count=5 |
| export_pdf | passed | 1202.7 | path='C:\\Users\\ADMIN\\AppData\\Local\\Temp\\opencode\\corel-live\\run-20261031T173917430222Z-7h_5dv73\\disposable-regression.pdf', bytes=391476 |
| save_document | passed | 131.29 | path='C:\\Users\\ADMIN\\AppData\\Local\\Temp\\opencode\\corel-live\\run-20261031T173917430222Z-7h_5dv73\\disposable-regression.cdr', bytes=1104009 |

## Artifacts

- CDR: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T173917430222Z-7h_5dv73\disposable-regression.cdr` (1104009 bytes)
- PDF: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T173917430222Z-7h_5dv73\disposable-regression.pdf` (391476 bytes)
- Synthetic SVG fixture: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T173917430222Z-7h_5dv73\synthetic-import.svg`

## Cleanup

- Closed the saved disposable document.

## Manual review still required

- Open each generated CDR and confirm objects remain editable.
- Inspect each generated PDF for page size, fonts, colors, and rendering.
- Do not mark tools live-verified until this report and the artifacts have been reviewed.
