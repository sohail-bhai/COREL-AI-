# CorelDRAW X7 Disposable-Document Regression

- **UTC run time:** 2026-10-31T063533667033Z
- **Result:** PASS
- **CorelDRAW version:** Version 17.0.0.491
- **ProgID:** CorelDRAW.Application.17
- **Connection mode:** Dispatch
- **Output directory:** `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T063530874333Z-9wrcbpo7`
- **Failure:** None

The run created a new synthetic document and did not bind a document that predated the test.
Passing this regression is evidence for the tested environment only; it does not prove visual or print readiness.

| Step | Status | Duration (ms) | Detail |
|---|---|---:|---|
| connect / corel_status | passed | 10.29 | target_document_name=None |
| create_document | passed | 162.62 | target_document_name='Untitled-1', created=True |
| create_chest_number_batch | passed | 1517.53 | created=True |
| list_objects | passed | 418.99 | object_count=12 |
| save_document | passed | 171.96 | path='C:\\Users\\ADMIN\\AppData\\Local\\Temp\\opencode\\corel-live\\run-20261031T063530874333Z-9wrcbpo7\\disposable-chest-numbers.cdr', bytes=1704198 |

## Artifacts

- CDR: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T063530874333Z-9wrcbpo7\disposable-regression.cdr` (missing bytes)
- PDF: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T063530874333Z-9wrcbpo7\disposable-regression.pdf` (missing bytes)
- Synthetic SVG fixture: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T063530874333Z-9wrcbpo7\synthetic-import.svg`

## Cleanup

- Closed the saved disposable document.

## Manual review still required

- Open the CDR and confirm objects remain editable.
- Inspect the PDF page size, fonts, colors, and rendering.
- Do not mark tools live-verified until this report and the artifacts have been reviewed.
