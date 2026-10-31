# CorelDRAW X7 Disposable-Document Regression

- **UTC run time:** 2026-10-31T061326057885Z
- **Result:** PASS
- **CorelDRAW version:** Version 17.0.0.491
- **ProgID:** CorelDRAW.Application.17
- **Connection mode:** Dispatch
- **Output directory:** `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T061324492167Z-y_svr7j5`
- **Failure:** None

The run created a new synthetic document and did not bind a document that predated the test.
Passing this regression is evidence for the tested environment only; it does not prove visual or print readiness.

| Step | Status | Duration (ms) | Detail |
|---|---|---:|---|
| connect / corel_status | passed | 10.41 | target_document_name=None |
| create_document | passed | 196.21 | target_document_name='Untitled-1', created=True |
| execute_design_plan | passed | 426.53 | completed |
| list_objects | passed | 107.98 | object_count=3 |
| execute_failing_plan_rollback | failed | 79.21 | CorelBridgeError: Plan execution failed on element 'rollback_artwork_fail': Artwork file does not exist: C:\nonexistent_artwork_12345.svg. Changes were rolled back. |
| list_objects_after_rollback | passed | 129.76 | object_count=3 |
| save_document | passed | 103.21 | path='C:\\Users\\ADMIN\\AppData\\Local\\Temp\\opencode\\corel-live\\run-20261031T061324492167Z-y_svr7j5\\disposable-design-plan.cdr', bytes=1102275 |

## Artifacts

- CDR: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T061324492167Z-y_svr7j5\disposable-regression.cdr` (missing bytes)
- PDF: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T061324492167Z-y_svr7j5\disposable-regression.pdf` (missing bytes)
- Synthetic SVG fixture: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T061324492167Z-y_svr7j5\synthetic-import.svg`

## Cleanup

- Closed the saved disposable document.

## Manual review still required

- Open the CDR and confirm objects remain editable.
- Inspect the PDF page size, fonts, colors, and rendering.
- Do not mark tools live-verified until this report and the artifacts have been reviewed.
