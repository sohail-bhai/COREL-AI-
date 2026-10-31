# CorelDRAW X7 Disposable-Document Regression

- **UTC run time:** 2026-10-31T044736397749Z
- **Result:** FAIL
- **CorelDRAW version:** Version 17.0.0.491
- **ProgID:** CorelDRAW.Application.17
- **Connection mode:** Dispatch
- **Output directory:** `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T044733035675Z-tt22sqe6`
- **Failure:** CorelBridgeError: CorelDRAW X7 artwork import failed. Full COM error: The Python instance can not be converted to a COM object

The run created a new synthetic document and did not bind a document that predated the test.
Passing this regression is evidence for the tested environment only; it does not prove visual or print readiness.

| Step | Status | Duration (ms) | Detail |
|---|---|---:|---|
| connect / corel_status | passed | 1610.92 | target_document_name=None |
| create_document | passed | 391.41 | target_document_name='Untitled-1', created=True |
| use_active_document | passed | 2.53 | target_document_name='Untitled-1' |
| draw_rectangle | passed | 172.27 | object_name='Live_Rectangle', created=True |
| draw_ellipse | passed | 101.64 | object_name='Live_Ellipse', created=True |
| add_text | passed | 214.91 | object_name='Live_Text', created=True |
| set_fill_color | passed | 115.23 | object_name='Live_Rectangle', updated=True |
| set_outline | passed | 88.66 | object_name='Live_Rectangle', updated=True |
| move_object | passed | 54.93 | object_name='Live_Ellipse', moved=True |
| resize_object | passed | 65.63 | object_name='Live_Ellipse', resized=True |
| set_text_content | passed | 74.22 | object_name='Live_Text', updated=True |
| rename_object | passed | 90.06 | object_name='Live_Ellipse_Renamed', renamed=True |
| duplicate_object | passed | 146.29 | object_name='Live_Rectangle_Copy', duplicated=True |
| create synthetic import fixture | passed | 0.46 | NoneType |
| import_artwork | failed | 34.92 | CorelBridgeError: CorelDRAW X7 artwork import failed. Full COM error: The Python instance can not be converted to a COM object |

## Artifacts

- CDR: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T044733035675Z-tt22sqe6\disposable-regression.cdr` (1698766 bytes)
- PDF: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T044733035675Z-tt22sqe6\disposable-regression.pdf` (missing bytes)
- Synthetic SVG fixture: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T044733035675Z-tt22sqe6\synthetic-import.svg`

## Cleanup

- Saved the disposable document during cleanup before closing it.
- Closed the saved disposable document.

## Manual review still required

- Open the CDR and confirm objects remain editable.
- Inspect the PDF page size, fonts, colors, and rendering.
- Do not mark tools live-verified until this report and the artifacts have been reviewed.
