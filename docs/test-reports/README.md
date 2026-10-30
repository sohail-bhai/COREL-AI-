# Live Test Reports

This directory stores dated, non-confidential reports from explicitly authorized CorelDRAW X7 integration runs.

## Disposable-document regression gate

The mutating regression in `tests/integration/test_corel_live.py` is disabled unless both environment flags are set:

```powershell
$env:COREL_LIVE_TESTS = "1"
$env:COREL_LIVE_MUTATION_TESTS = "1"
.\.venv\Scripts\python.exe -m unittest tests.integration.test_corel_live.CorelDisposableDocumentLiveTests -v
```

The test creates a new document, synthetic vector artwork, and a unique output directory beneath the operating system's `opencode` temporary directory. It never calls `use_active_document` until after the test itself has created and bound the active document. Existing output files are not overwritten.

Each enabled run writes a dated Markdown report here and leaves its CDR, PDF, and SVG artifacts in the unique temporary output directory for manual review. Reports must not contain client artwork, credentials, prompts, or document contents from pre-existing files.

A passing automated report does **not** establish visual quality or print readiness. Review the generated CDR for editability and the PDF for dimensions and rendering before changing catalog records from `implemented_unverified` to `verified`.
