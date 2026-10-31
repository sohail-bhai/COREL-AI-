# CorelDRAW X7 Disposable-Document Regression

- **UTC run time:** 2026-10-31T061141198964Z
- **Result:** FAIL
- **CorelDRAW version:** Version 17.0.0.491
- **ProgID:** CorelDRAW.Application.17
- **Connection mode:** Dispatch
- **Output directory:** `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T061139100135Z-2rvg6n6j`
- **Failure:** CorelBridgeError: Unsupported plan version None; expected '1.0'.

The run created a new synthetic document and did not bind a document that predated the test.
Passing this regression is evidence for the tested environment only; it does not prove visual or print readiness.

| Step | Status | Duration (ms) | Detail |
|---|---|---:|---|
| connect / corel_status | passed | 1689.1 | target_document_name=None |
| create_document | passed | 315.38 | target_document_name='Untitled-1', created=True |
| execute_design_plan | failed | 0.02 | CorelBridgeError: Unsupported plan version None; expected '1.0'. |

## Artifacts

- CDR: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T061139100135Z-2rvg6n6j\disposable-regression.cdr` (8734 bytes)
- PDF: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T061139100135Z-2rvg6n6j\disposable-regression.pdf` (missing bytes)
- Synthetic SVG fixture: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T061139100135Z-2rvg6n6j\synthetic-import.svg`

## Cleanup

- Saved the disposable document during cleanup before closing it.
- Closed the saved disposable document.

## Manual review still required

- Open the CDR and confirm objects remain editable.
- Inspect the PDF page size, fonts, colors, and rendering.
- Do not mark tools live-verified until this report and the artifacts have been reviewed.
