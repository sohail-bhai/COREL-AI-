# CorelDRAW X7 Disposable-Document Regression

- **UTC run time:** 2026-10-31T173913010244Z
- **Result:** PASS
- **CorelDRAW version:** Version 17.0.0.491
- **ProgID:** CorelDRAW.Application.17
- **Connection mode:** Dispatch
- **Output directory:** `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T173909081936Z-xddu0ugz`
- **Failure:** None

The run created a new synthetic document and did not bind a document that predated the test.
Passing this regression is evidence for the tested environment only; it does not prove visual or print readiness.

| Step | Status | Duration (ms) | Detail |
|---|---|---:|---|
| connect / corel_status | passed | 2329.42 | target_document_name=None |
| create_document | passed | 335.51 | target_document_name='Untitled-1', created=True |
| draw_box_1 | passed | 161.6 | object_name='Align_Box1', created=True |
| draw_box_2 | passed | 74.09 | object_name='Align_Box2', created=True |
| align_objects | passed | 72.75 | object_count=2 |
| align_to_page | passed | 44.77 | object_count=1 |
| group_shapes | passed | 146.5 | completed |
| list_objects_after_group | passed | 28.93 | object_count=1 |
| ungroup_shapes | passed | 72.97 | object_name='Live_Group' |
| list_objects_after_ungroup | passed | 74.66 | object_count=2 |
| save_document | passed | 80.96 | path='C:\\Users\\ADMIN\\AppData\\Local\\Temp\\opencode\\corel-live\\run-20261031T173909081936Z-xddu0ugz\\disposable-align-group.cdr', bytes=9996 |

## Artifacts

- CDR: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T173909081936Z-xddu0ugz\disposable-align-group.cdr` (9996 bytes)
- PDF: not generated
- Synthetic SVG fixture: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T173909081936Z-xddu0ugz\synthetic-import.svg`

## Cleanup

- Closed the saved disposable document.

## Manual review still required

- Open each generated CDR and confirm objects remain editable.
- No PDF was generated; PDF review is not applicable.
- Do not mark tools live-verified until this report and the artifacts have been reviewed.
