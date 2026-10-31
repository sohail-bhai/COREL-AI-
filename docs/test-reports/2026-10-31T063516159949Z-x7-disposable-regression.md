# CorelDRAW X7 Disposable-Document Regression

- **UTC run time:** 2026-10-31T063516159949Z
- **Result:** PASS
- **CorelDRAW version:** Version 17.0.0.491
- **ProgID:** CorelDRAW.Application.17
- **Connection mode:** Dispatch
- **Output directory:** `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T063512721108Z-tggc2nya`
- **Failure:** None

The run created a new synthetic document and did not bind a document that predated the test.
Passing this regression is evidence for the tested environment only; it does not prove visual or print readiness.

| Step | Status | Duration (ms) | Detail |
|---|---|---:|---|
| connect / corel_status | passed | 1808.41 | target_document_name=None |
| create_document | passed | 338.34 | target_document_name='Untitled-1', created=True |
| draw_box_1 | passed | 179.82 | object_name='Align_Box1', created=True |
| draw_box_2 | passed | 78.56 | object_name='Align_Box2', created=True |
| align_objects | passed | 75.12 | object_count=2 |
| align_to_page | passed | 47.92 | object_count=1 |
| group_shapes | passed | 150.03 | completed |
| list_objects_after_group | passed | 29.83 | object_count=1 |
| ungroup_shapes | passed | 78.29 | object_name='Live_Group' |
| list_objects_after_ungroup | passed | 79.07 | object_count=2 |
| save_document | passed | 66.74 | path='C:\\Users\\ADMIN\\AppData\\Local\\Temp\\opencode\\corel-live\\run-20261031T063512721108Z-tggc2nya\\disposable-align-group.cdr', bytes=10005 |

## Artifacts

- CDR: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T063512721108Z-tggc2nya\disposable-regression.cdr` (missing bytes)
- PDF: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T063512721108Z-tggc2nya\disposable-regression.pdf` (missing bytes)
- Synthetic SVG fixture: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T063512721108Z-tggc2nya\synthetic-import.svg`

## Cleanup

- Closed the saved disposable document.

## Manual review still required

- Open the CDR and confirm objects remain editable.
- Inspect the PDF page size, fonts, colors, and rendering.
- Do not mark tools live-verified until this report and the artifacts have been reviewed.
