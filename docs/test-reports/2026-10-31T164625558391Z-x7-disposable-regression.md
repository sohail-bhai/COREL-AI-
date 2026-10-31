# CorelDRAW X7 Disposable-Document Regression

- **UTC run time:** 2026-10-31T164625558391Z
- **Result:** PASS
- **CorelDRAW version:** Version 17.0.0.491
- **ProgID:** CorelDRAW.Application.17
- **Connection mode:** Dispatch
- **Output directory:** `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T164623541517Z-t_cprii4`
- **Failure:** None

The run created a new synthetic document and did not bind a document that predated the test.
Passing this regression is evidence for the tested environment only; it does not prove visual or print readiness.

| Step | Status | Duration (ms) | Detail |
|---|---|---:|---|
| connect / corel_status | passed | 162.21 | target_document_name=None |
| create_document | passed | 271.2 | target_document_name='Untitled-1', created=True |
| execute_design_plan | passed | 496.15 | completed |
| list_objects | passed | 129.04 | object_count=3 |
| execute_failing_plan_rollback | failed | 167.49 | CorelBridgeError: Plan execution failed on element 'rollback_artwork_fail'. Changes were rolled back and the prior page state was verified. |
| list_objects_after_rollback | passed | 109.7 | object_count=3 |
| save_document | passed | 176.08 | path='C:\\Users\\ADMIN\\AppData\\Local\\Temp\\opencode\\corel-live\\run-20261031T164623541517Z-t_cprii4\\disposable-design-plan.cdr', bytes=1102235 |

## Artifacts

- CDR: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T164623541517Z-t_cprii4\disposable-design-plan.cdr` (1102235 bytes)
- PDF: not generated
- Synthetic SVG fixture: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T164623541517Z-t_cprii4\synthetic-import.svg`

## Cleanup

- Closed the saved disposable document.

## Manual review still required

- Open each generated CDR and confirm objects remain editable.
- No PDF was generated; PDF review is not applicable.
- Do not mark tools live-verified until this report and the artifacts have been reviewed.
