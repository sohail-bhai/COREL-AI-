# CorelDRAW X7 Disposable-Document Regression

- **UTC run time:** 2026-10-31T061235709267Z
- **Result:** FAIL
- **CorelDRAW version:** Version 17.0.0.491
- **ProgID:** CorelDRAW.Application.17
- **Connection mode:** Dispatch
- **Output directory:** `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T061229767441Z-fph6d151`
- **Failure:** CorelBridgeError: Plan execution failed on element 'badge_card': Could not read shapes from the target document's active page.. Changes were rolled back.

The run created a new synthetic document and did not bind a document that predated the test.
Passing this regression is evidence for the tested environment only; it does not prove visual or print readiness.

| Step | Status | Duration (ms) | Detail |
|---|---|---:|---|
| connect / corel_status | passed | 63.58 | target_document_name=None |
| create_document | passed | 177.84 | target_document_name='Untitled-1', created=True |
| execute_design_plan | failed | 5699.21 | CorelBridgeError: Plan execution failed on element 'badge_card': Could not read shapes from the target document's active page.. Changes were rolled back. |

## Artifacts

- CDR: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T061229767441Z-fph6d151\disposable-regression.cdr` (missing bytes)
- PDF: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T061229767441Z-fph6d151\disposable-regression.pdf` (missing bytes)
- Synthetic SVG fixture: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T061229767441Z-fph6d151\synthetic-import.svg`

## Cleanup

- Document left open because cleanup save failed: CorelBridgeError: CorelDRAW X7 could not save the target document. Full COM error: (-2147023174, 'The RPC server is unavailable.', None, None)

## Manual review still required

- Open the CDR and confirm objects remain editable.
- Inspect the PDF page size, fonts, colors, and rendering.
- Do not mark tools live-verified until this report and the artifacts have been reviewed.
