# CorelDRAW X7 Disposable-Document Regression

- **UTC run time:** 2026-11-01T030409181735Z
- **Result:** PASS
- **CorelDRAW version:** Version 17.0.0.491
- **ProgID:** CorelDRAW.Application.17
- **Connection mode:** Dispatch
- **Output directory:** `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261101T030407548448Z-yz8n1yq_`
- **Failure:** None

The run created a new synthetic document and did not bind a document that predated the test.
Passing this regression is evidence for the tested environment only; it does not prove visual or print readiness.

| Step | Status | Duration (ms) | Detail |
|---|---|---:|---|
| connect / corel_status | passed | 8.03 | target_document_name=None |
| create_document | passed | 182.17 | target_document_name='Untitled-1', created=True |
| execute_design_plan | passed | 438.25 | completed |
| list_objects | passed | 109.6 | object_count=3 |
| execute_failing_plan_rollback | failed | 175.21 | CorelBridgeError: Plan execution failed on element 'rollback_artwork_fail'. Changes were rolled back and the prior page state was verified. |
| list_objects_after_rollback | passed | 94.98 | object_count=3 |
| save_document | passed | 112.98 | path='C:\\Users\\ADMIN\\AppData\\Local\\Temp\\opencode\\corel-live\\run-20261101T030407548448Z-yz8n1yq_\\disposable-design-plan.cdr', bytes=1102788 |

## Artifacts

- CDR: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261101T030407548448Z-yz8n1yq_\disposable-design-plan.cdr` (1102788 bytes)
- PDF: not generated
- Synthetic SVG fixture: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261101T030407548448Z-yz8n1yq_\synthetic-import.svg`

## Cleanup

- Closed the saved disposable document.

## Manual review still required

- Open each generated CDR and confirm objects remain editable.
- No PDF was generated; PDF review is not applicable.
- Do not mark tools live-verified until this report and the artifacts have been reviewed.
