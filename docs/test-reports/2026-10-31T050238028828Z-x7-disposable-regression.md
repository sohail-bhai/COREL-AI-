# CorelDRAW X7 Disposable-Document Regression

- **UTC run time:** 2026-10-31T050238028828Z
- **Result:** PASS
- **CorelDRAW version:** Version 17.0.0.491
- **ProgID:** CorelDRAW.Application.17
- **Connection mode:** Dispatch
- **Output directory:** `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T050233759156Z-c18wypy3`
- **Failure:** None

The run created a new synthetic document and did not bind a document that predated the test.
Passing this regression is evidence for the tested environment only; it does not prove visual or print readiness.

| Step | Status | Duration (ms) | Detail |
|---|---|---:|---|
| connect / corel_status | passed | 1665.61 | target_document_name=None |
| create_document | passed | 316.19 | target_document_name='Untitled-1', created=True |
| create_chest_number_batch | passed | 1489.57 | created=True |
| list_objects | passed | 435.14 | object_count=12 |
| save_document | passed | 188.91 | path='C:\\Users\\ADMIN\\AppData\\Local\\Temp\\opencode\\corel-live\\run-20261031T050233759156Z-c18wypy3\\disposable-chest-numbers.cdr', bytes=1704107 |

## Artifacts

- CDR: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T050233759156Z-c18wypy3\disposable-regression.cdr` (1704191 bytes)
- PDF: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T050233759156Z-c18wypy3\disposable-regression.pdf` (missing bytes)
- Synthetic SVG fixture: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261031T050233759156Z-c18wypy3\synthetic-import.svg`

## Cleanup

- Saved the disposable document during cleanup before closing it.
- Closed the saved disposable document.

## Manual review still required

- Open the CDR and confirm objects remain editable.
- Inspect the PDF page size, fonts, colors, and rendering.
- Do not mark tools live-verified until this report and the artifacts have been reviewed.
