# CorelDRAW X7 Disposable-Document Regression

- **UTC run time:** 2026-10-31T173917429103Z
- **Result:** PASS
- **CorelDRAW version:** Version 17.0.0.491
- **ProgID:** CorelDRAW.Application.17
- **Connection mode:** Dispatch
- **Output directory:** `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T173915747575Z-owtnq182`
- **Failure:** None

The run created a new synthetic document and did not bind a document that predated the test.
Passing this regression is evidence for the tested environment only; it does not prove visual or print readiness.

| Step | Status | Duration (ms) | Detail |
|---|---|---:|---|
| connect / corel_status | passed | 8.26 | target_document_name=None |
| create_document | passed | 201.64 | target_document_name='Untitled-1', created=True |
| execute_design_plan | passed | 465.78 | completed |
| list_objects | passed | 110.12 | object_count=3 |
| execute_failing_plan_rollback | failed | 173.81 | CorelBridgeError: Plan execution failed on element 'rollback_artwork_fail'. Changes were rolled back and the prior page state was verified. |
| list_objects_after_rollback | passed | 100.31 | object_count=3 |
| save_document | passed | 109.52 | path='C:\\Users\\ADMIN\\AppData\\Local\\Temp\\opencode\\corel-live\\run-20261031T173915747575Z-owtnq182\\disposable-design-plan.cdr', bytes=1102232 |

## Artifacts

- CDR: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T173915747575Z-owtnq182\disposable-design-plan.cdr` (1102232 bytes)
- PDF: not generated
- Synthetic SVG fixture: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T173915747575Z-owtnq182\synthetic-import.svg`

## Cleanup

- Closed the saved disposable document.

## Manual review still required

- Open each generated CDR and confirm objects remain editable.
- No PDF was generated; PDF review is not applicable.
- Do not mark tools live-verified until this report and the artifacts have been reviewed.
