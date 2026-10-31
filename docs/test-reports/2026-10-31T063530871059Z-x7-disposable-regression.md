# CorelDRAW X7 Disposable-Document Regression

- **UTC run time:** 2026-10-31T063530871059Z
- **Result:** PASS
- **CorelDRAW version:** Version 17.0.0.491
- **ProgID:** CorelDRAW.Application.17
- **Connection mode:** Dispatch
- **Output directory:** `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T063527498476Z-d6ruy1d_`
- **Failure:** None

The run created a new synthetic document and did not bind a document that predated the test.
Passing this regression is evidence for the tested environment only; it does not prove visual or print readiness.

| Step | Status | Duration (ms) | Detail |
|---|---|---:|---|
| connect / corel_status | passed | 1745.59 | target_document_name=None |
| create_document | passed | 338.49 | target_document_name='Untitled-1', created=True |
| draw_box_1 | passed | 188.23 | object_name='Align_Box1', created=True |
| draw_box_2 | passed | 73.9 | object_name='Align_Box2', created=True |
| align_objects | passed | 71.65 | object_count=2 |
| align_to_page | passed | 47.83 | object_count=1 |
| group_shapes | passed | 151.33 | completed |
| list_objects_after_group | passed | 29.32 | object_count=1 |
| ungroup_shapes | passed | 77.29 | object_name='Live_Group' |
| list_objects_after_ungroup | passed | 79.52 | object_count=2 |
| save_document | passed | 63.21 | path='C:\\Users\\ADMIN\\AppData\\Local\\Temp\\opencode\\corel-live\\run-20261031T063527498476Z-d6ruy1d_\\disposable-align-group.cdr', bytes=9998 |

## Artifacts

- CDR: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T063527498476Z-d6ruy1d_\disposable-regression.cdr` (missing bytes)
- PDF: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T063527498476Z-d6ruy1d_\disposable-regression.pdf` (missing bytes)
- Synthetic SVG fixture: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T063527498476Z-d6ruy1d_\synthetic-import.svg`

## Cleanup

- Closed the saved disposable document.

## Manual review still required

- Open the CDR and confirm objects remain editable.
- Inspect the PDF page size, fonts, colors, and rendering.
- Do not mark tools live-verified until this report and the artifacts have been reviewed.
