# CorelDRAW X7 Disposable-Document Regression

- **UTC run time:** 2026-10-31T061214364715Z
- **Result:** PASS
- **CorelDRAW version:** Version 17.0.0.491
- **ProgID:** CorelDRAW.Application.17
- **Connection mode:** Dispatch
- **Output directory:** `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T061211118129Z-142uf2m2`
- **Failure:** None

The run created a new synthetic document and did not bind a document that predated the test.
Passing this regression is evidence for the tested environment only; it does not prove visual or print readiness.

| Step | Status | Duration (ms) | Detail |
|---|---|---:|---|
| connect / corel_status | passed | 1674.19 | target_document_name=None |
| create_document | passed | 337.82 | target_document_name='Untitled-1', created=True |
| execute_design_plan | passed | 573.93 | completed |
| list_objects | passed | 114.09 | object_count=3 |
| execute_failing_plan_rollback | failed | 125.85 | CorelBridgeError: Plan execution failed on element 'rollback_artwork_fail': Artwork file does not exist: C:\nonexistent_artwork_12345.svg. Changes were rolled back. |
| list_objects_after_rollback | passed | 139.22 | object_count=3 |
| save_document | passed | 138.02 | path='C:\\Users\\ADMIN\\AppData\\Local\\Temp\\opencode\\corel-live\\run-20261031T061211118129Z-142uf2m2\\disposable-design-plan.cdr', bytes=1102251 |

## Artifacts

- CDR: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T061211118129Z-142uf2m2\disposable-regression.cdr` (1102238 bytes)
- PDF: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T061211118129Z-142uf2m2\disposable-regression.pdf` (missing bytes)
- Synthetic SVG fixture: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T061211118129Z-142uf2m2\synthetic-import.svg`

## Cleanup

- Saved the disposable document during cleanup before closing it.
- Closed the saved disposable document.

## Manual review still required

- Open the CDR and confirm objects remain editable.
- Inspect the PDF page size, fonts, colors, and rendering.
- Do not mark tools live-verified until this report and the artifacts have been reviewed.
