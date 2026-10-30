# Testing

## Default test run

The default suite must not connect to, launch, or mutate CorelDRAW:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Current expected result:

```text
Ran 83 tests
OK (skipped=2)
```

Coverage includes:

- authoritative bridge/schema/profile versions;
- tool-schema v1 success and error envelopes;
- all catalog JSON Schemas and 90 request/success/error examples;
- bridge argument validation and stable error codes;
- inch-unit and reference-point context restoration;
- protected target-document behavior using fake COM objects;
- import extension/size checks and output overwrite refusal;
- dedicated dispatcher-thread execution, exception propagation, and shutdown;
- explicit X7 ProgID preference, generic fallback, and wrong-major rejection;
- adapter constants/capability status and connection-free static diagnostics;
- document/page, primitive/text bounds, text-format, and PDF-file readback using fake COM objects;
- native RGB/fill/outline readback plus StaticID/layer/page identity for list, rename, duplicate, and import operations;
- read-only document, page, layer, and single-object inspection using fake multi-document COM collections;
- `corel_status` runtime metadata using a fake Application object.

Temporary path-safety fixtures are created under the operating system's `opencode` temporary directory and removed by the tests.

## Catalog validation

Run independently with:

```powershell
.\.venv\Scripts\python.exe scripts\validate_catalog.py
```

The validator checks server/registry tool parity, API/evidence references, enum/registry versions, error-code parity, CSV consistency, JSON Schemas, and every catalog example.

## Guarded live test

`tests/integration/test_corel_live.py` is skipped by default. Its read-only gate checks status/profile metadata and enumerates open documents without binding a target.

Run it only when the user explicitly wants to attach to or launch CorelDRAW X7:

```powershell
$env:COREL_LIVE_TESTS = "1"
.\.venv\Scripts\python.exe -m unittest tests.integration.test_corel_live -v
```

Enabling the flag permits `CorelBridge.connect()` to attach through COM or launch the registered application. It does not authorize mutation of an existing document.

## Guarded mutating regression

The disposable-document regression is also skipped by default. It requires both the general live-test flag and a separate mutation authorization:

```powershell
$env:COREL_LIVE_TESTS = "1"
$env:COREL_LIVE_MUTATION_TESTS = "1"
.\.venv\Scripts\python.exe -m unittest tests.integration.test_corel_live.CorelDisposableDocumentLiveTests -v
```

This test creates and binds its own new document before exercising the existing editing operations. It uses a unique directory beneath the operating system's `opencode` temporary directory, refuses output overwrites through the bridge, and writes a dated report under `docs/test-reports/`. Generated CDR, PDF, and SVG artifacts remain outside the repository for manual review.

Do not set either flag in shared automation. A passing run is not enough to claim visual quality or print readiness, and catalog records must remain `implemented_unverified` until the dated report and artifacts are reviewed.
