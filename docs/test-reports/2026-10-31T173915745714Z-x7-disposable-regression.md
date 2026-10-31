# CorelDRAW X7 Disposable-Document Regression

- **UTC run time:** 2026-10-31T173915745714Z
- **Result:** PASS
- **CorelDRAW version:** Version 17.0.0.491
- **ProgID:** CorelDRAW.Application.17
- **Connection mode:** Dispatch
- **Output directory:** `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T173913013328Z-0rx14not`
- **Failure:** None

The run created a new synthetic document and did not bind a document that predated the test.
Passing this regression is evidence for the tested environment only; it does not prove visual or print readiness.

| Step | Status | Duration (ms) | Detail |
|---|---|---:|---|
| connect / corel_status | passed | 10.22 | target_document_name=None |
| create_document | passed | 161.11 | target_document_name='Untitled-1', created=True |
| create_chest_number_batch | passed | 1449.16 | created=True |
| list_objects | passed | 425.11 | object_count=12 |
| save_document | passed | 181.03 | path='C:\\Users\\ADMIN\\AppData\\Local\\Temp\\opencode\\corel-live\\run-20261031T173913013328Z-0rx14not\\disposable-chest-numbers.cdr', bytes=1704147 |

## Artifacts

- CDR: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T173913013328Z-0rx14not\disposable-chest-numbers.cdr` (1704147 bytes)
- PDF: not generated
- Synthetic SVG fixture: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T173913013328Z-0rx14not\synthetic-import.svg`

## Cleanup

- Closed the saved disposable document.

## Manual review still required

- Open each generated CDR and confirm objects remain editable.
- No PDF was generated; PDF review is not applicable.
- Do not mark tools live-verified until this report and the artifacts have been reviewed.
