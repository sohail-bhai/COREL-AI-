# CorelDRAW X7 Disposable-Document Regression

- **UTC run time:** 2026-11-01T102314660325Z
- **Result:** PASS
- **CorelDRAW version:** Version 17.0.0.491
- **ProgID:** CorelDRAW.Application.17
- **Connection mode:** Dispatch
- **Output directory:** `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261101T102310723267Z-isivgrka`
- **Failure:** None

The run created a new synthetic document and did not bind a document that predated the test.
Passing this regression is evidence for the tested environment only; it does not prove visual or print readiness.

| Step | Status | Duration (ms) | Detail |
|---|---|---:|---|
| connect / corel_status | passed | 56.53 | target_document_name=None |
| create disposable imposition document | passed | 181.32 | target_document_name='Untitled-1', created=True |
| create asymmetric vector repeat | passed | 315.99 | completed |
| inspect_repeat_unit | passed | 79.29 | completed |
| prepare_imposition_job plan | passed | 127.05 | completed |
| prepare_imposition_job execute | passed | 1104.91 | completed |
| verify source after successful imposition | passed | 151.6 | completed |
| prepare forced-rollback plan | passed | 120.95 | completed |
| forced imposition collision rollback | failed | 1141.49 | CorelBridgeError: Imposition execution failed. The new output page was removed and the source was preserved. |
| verify source after imposition rollback | passed | 72.6 | completed |
| save imposition artifact | passed | 50.6 | path='C:\\Users\\ADMIN\\AppData\\Local\\Temp\\opencode\\corel-live\\run-20261101T102310723267Z-isivgrka\\disposable-imposition.cdr', bytes=13354 |

## Artifacts

- CDR: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261101T102310723267Z-isivgrka\disposable-imposition.cdr` (13354 bytes)
- PDF: not generated
- Synthetic SVG fixture: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261101T102310723267Z-isivgrka\synthetic-import.svg`

## Cleanup

- Closed the saved disposable document.

## Manual review still required

- Open each generated CDR and confirm objects remain editable.
- No PDF was generated; PDF review is not applicable.
- Do not mark tools live-verified until this report and the artifacts have been reviewed.
- Confirm page 1 contains the unchanged editable `Repeat_Unit` source group.
- Confirm page 2 contains four separately selectable `Imposed_Copy_###` groups on `Imposition_Repeats`.
- Confirm the upper-row copies are rotated 180° and visually interlock without overlap.
- Confirm no `Rollback_Copy_###` groups or extra rollback page remain.
