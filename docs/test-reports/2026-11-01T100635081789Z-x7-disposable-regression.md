# CorelDRAW X7 Disposable-Document Regression

- **UTC run time:** 2026-11-01T100635081789Z
- **Result:** FAIL
- **CorelDRAW version:** Version 17.0.0.491
- **ProgID:** CorelDRAW.Application.17
- **Connection mode:** Dispatch
- **Output directory:** `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261101T100632924557Z-g69dgcjm`
- **Failure:** CorelBridgeError: Imposition execution failed. The new output page was removed and the source was preserved.

The run created a new synthetic document and did not bind a document that predated the test.
Passing this regression is evidence for the tested environment only; it does not prove visual or print readiness.

| Step | Status | Duration (ms) | Detail |
|---|---|---:|---|
| connect / corel_status | passed | 135.96 | target_document_name=None |
| create disposable imposition document | passed | 259.74 | target_document_name='Untitled-1', created=True |
| create asymmetric vector repeat | passed | 502.21 | completed |
| inspect_repeat_unit | passed | 86.62 | completed |
| prepare_imposition_job plan | passed | 127.54 | completed |
| prepare_imposition_job execute | failed | 484.48 | CorelBridgeError: Imposition execution failed. The new output page was removed and the source was preserved. |

## Artifacts

- CDR: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261101T100632924557Z-g69dgcjm\disposable-regression.cdr` (10371 bytes)
- PDF: not generated
- Synthetic SVG fixture: `C:\Users\ADMIN\AppData\Local\Temp\opencode\corel-live\run-20261101T100632924557Z-g69dgcjm\synthetic-import.svg`

## Cleanup

- Saved the disposable document during cleanup before closing it.
- Closed the saved disposable document.

## Manual review still required

- Open each generated CDR and confirm objects remain editable.
- No PDF was generated; PDF review is not applicable.
- Do not mark tools live-verified until this report and the artifacts have been reviewed.

## Failure diagnosis

- `Shape.CopyToLayer(output_layer)` raised COM error `-2147352567` with inner HRESULT `-2147467259` for the synthetic repeat group and a layer on the newly added page.
- The operation removed its new output page, verified the approved source was unchanged, saved the disposable source document during cleanup, and closed it.
- The succeeding run uses the type-library-confirmed and separately probed `Shape.Copy()` / `Layer.Paste()` equivalent.
