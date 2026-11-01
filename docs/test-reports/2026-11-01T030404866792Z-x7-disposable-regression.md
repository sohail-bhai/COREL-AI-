# CorelDRAW X7 Disposable-Document Regression

- **UTC run time:** 2026-11-01T030404866792Z
- **Result:** PASS
- **CorelDRAW version:** Version 17.0.0.491
- **ProgID:** CorelDRAW.Application.17
- **Connection mode:** Dispatch
- **Output directory:** `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261101T030401745319Z-dt53u68p`
- **Failure:** None

The run created a new synthetic document and did not bind a document that predated the test.
Passing this regression is evidence for the tested environment only; it does not prove visual or print readiness.

| Step | Status | Duration (ms) | Detail |
|---|---|---:|---|
| connect / corel_status | passed | 1623.03 | target_document_name=None |
| create_document | passed | 301.1 | target_document_name='Untitled-1', created=True |
| draw_box_1 | passed | 152.65 | object_name='Align_Box1', created=True |
| draw_box_2 | passed | 62.31 | object_name='Align_Box2', created=True |
| align_objects | passed | 65.0 | object_count=2 |
| align_to_page | passed | 43.29 | object_count=1 |
| group_shapes | passed | 123.47 | completed |
| list_objects_after_group | passed | 30.05 | object_count=1 |
| ungroup_shapes | passed | 27.56 | object_name='Live_Group' |
| list_objects_after_ungroup | passed | 117.23 | object_count=2 |
| save_document | passed | 68.9 | path='C:\\Users\\ADMIN\\AppData\\Local\\Temp\\opencode\\corel-live\\run-20261101T030401745319Z-dt53u68p\\disposable-align-group.cdr', bytes=10002 |

## Artifacts

- CDR: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261101T030401745319Z-dt53u68p\disposable-align-group.cdr` (10002 bytes)
- PDF: not generated
- Synthetic SVG fixture: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261101T030401745319Z-dt53u68p\synthetic-import.svg`

## Cleanup

- Closed the saved disposable document.

## Manual review still required

- Open each generated CDR and confirm objects remain editable.
- No PDF was generated; PDF review is not applicable.
- Do not mark tools live-verified until this report and the artifacts have been reviewed.
