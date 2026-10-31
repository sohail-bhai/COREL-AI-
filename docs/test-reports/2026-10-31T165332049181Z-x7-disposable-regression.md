# CorelDRAW X7 Disposable-Document Regression

- **UTC run time:** 2026-10-31T165332049181Z
- **Result:** PASS
- **CorelDRAW version:** Version 17.0.0.491
- **ProgID:** CorelDRAW.Application.17
- **Connection mode:** Dispatch
- **Output directory:** `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T165330430080Z-5ib18w6q`
- **Failure:** None

The run created a new synthetic document and did not bind a document that predated the test.
Passing this regression is evidence for the tested environment only; it does not prove visual or print readiness.

| Step | Status | Duration (ms) | Detail |
|---|---|---:|---|
| connect / corel_status | passed | 78.2 | target_document_name=None |
| create_document | passed | 190.29 | target_document_name='Untitled-1', created=True |
| execute_design_plan | passed | 325.43 | completed |
| list_objects | passed | 129.27 | object_count=3 |
| execute_failing_plan_rollback | failed | 167.14 | CorelBridgeError: Plan execution failed on element 'rollback_artwork_fail'. Changes were rolled back and the prior page state was verified. |
| list_objects_after_rollback | passed | 112.1 | object_count=3 |
| save_document | passed | 112.58 | path='C:\\Users\\ADMIN\\AppData\\Local\\Temp\\opencode\\corel-live\\run-20261031T165330430080Z-5ib18w6q\\disposable-design-plan.cdr', bytes=1102226 |

## Artifacts

- CDR: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T165330430080Z-5ib18w6q\disposable-design-plan.cdr` (1102226 bytes)
- PDF: not generated
- Synthetic SVG fixture: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T165330430080Z-5ib18w6q\synthetic-import.svg`

## Cleanup

- Closed the saved disposable document.

## Manual review still required

- Open each generated CDR and confirm objects remain editable.
- No PDF was generated; PDF review is not applicable.
- Do not mark tools live-verified until this report and the artifacts have been reviewed.
