# CorelDRAW X7 Disposable-Document Regression

- **UTC run time:** 2026-10-31T063405656860Z
- **Result:** FAIL
- **CorelDRAW version:** Version 17.0.0.491
- **ProgID:** CorelDRAW.Application.17
- **Connection mode:** Dispatch
- **Output directory:** `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T063402390847Z-v147b3db`
- **Failure:** AssertionError: 1.0 != 4.0 within 0.02 delta (3.0 difference)

The run created a new synthetic document and did not bind a document that predated the test.
Passing this regression is evidence for the tested environment only; it does not prove visual or print readiness.

| Step | Status | Duration (ms) | Detail |
|---|---|---:|---|
| connect / corel_status | passed | 2005.89 | target_document_name=None |
| create_document | passed | 346.15 | target_document_name='Untitled-1', created=True |
| draw_box_1 | passed | 190.75 | object_name='Align_Box1', created=True |
| draw_box_2 | passed | 69.67 | object_name='Align_Box2', created=True |
| align_objects | passed | 73.56 | object_count=2 |

## Artifacts

- CDR: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T063402390847Z-v147b3db\disposable-regression.cdr` (9820 bytes)
- PDF: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T063402390847Z-v147b3db\disposable-regression.pdf` (missing bytes)
- Synthetic SVG fixture: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T063402390847Z-v147b3db\synthetic-import.svg`

## Cleanup

- Saved the disposable document during cleanup before closing it.
- Closed the saved disposable document.

## Manual review still required

- Open the CDR and confirm objects remain editable.
- Inspect the PDF page size, fonts, colors, and rendering.
- Do not mark tools live-verified until this report and the artifacts have been reviewed.
