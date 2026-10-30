# Testing

## Default test run

The default suite must not connect to, launch, or mutate CorelDRAW:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Current expected result:

```text
Ran 62 tests
OK (skipped=1)
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
- `corel_status` runtime metadata using a fake Application object.

Temporary path-safety fixtures are created under the operating system's `opencode` temporary directory and removed by the tests.

## Catalog validation

Run independently with:

```powershell
.\.venv\Scripts\python.exe scripts\validate_catalog.py
```

The validator checks server/registry tool parity, API/evidence references, enum/registry versions, error-code parity, CSV consistency, JSON Schemas, and every catalog example.

## Guarded live test

`tests/integration/test_corel_live.py` is skipped by default. It currently contains only a read-only status/profile check.

Run it only when the user explicitly wants to attach to or launch CorelDRAW X7:

```powershell
$env:COREL_LIVE_TESTS = "1"
.\.venv\Scripts\python.exe -m unittest tests.integration.test_corel_live -v
```

Enabling the flag permits `CorelBridge.connect()` to attach through COM or launch the registered application. It does not authorize mutation of an existing document.

## Future mutating integration tests

Mutating tests must use a separate explicit authorization flag, create a new disposable document, use unique output paths, and never bind an existing active document. That suite is planned for the guarded live-regression batch and is not implemented yet.
