# Testing

## Default test run

The default suite must not connect to, launch, or mutate CorelDRAW:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Current expected result:

```text
Ran 281 tests
OK (skipped=9)
```

Coverage includes:

- authoritative bridge/schema/profile versions;
- tool-schema v1 success and error envelopes;
- all catalog JSON Schemas and 138 request/success/error examples;
- bridge argument validation and stable error codes;
- inch-unit and reference-point context restoration;
- protected target-document behavior using fake COM objects;
- closed/replaced/lost-document and application detection using bounded open
  collections, COM proxy identity, retired sessions, and rejection before edits;
- import extension/size checks and output overwrite refusal;
- dedicated dispatcher-thread execution, exception propagation, and shutdown;
- explicit X7 ProgID preference, generic fallback, and wrong-major rejection;
- adapter constants/capability status and connection-free static diagnostics;
- document/page, primitive/text bounds, text-format, and PDF-file readback using fake COM objects;
- native RGB/fill/outline readback plus StaticID/layer/page identity for list, rename, duplicate, and import operations;
- read-only document, page, layer, and single-object inspection using fake multi-document COM collections;
- bounded literal object search across pages/layers/groups, duplicate names,
  master locations, Unicode filters, exact scan/result limits, cycle detection,
  non-mutating inspection, and strict actual-result schemas using fake COM;
- focused text/bounds/fill inspection with bounded identity and Unicode content,
  indeterminate tri-state formatting, native RGB/CMYK/gray/spot preservation,
  strict selectors, finite coordinates, and context-restoration failure checks;
- canonical design-plan schema/domain validation, asset preflight, preview readiness, actual-state readback, sanitized failures, command-group cleanup, and verified rollback;
- alignment and grouping validation/dispatch with guarded disposable-document live gates;
- contour routing/planning plus fingerprint-gated source-preserving imposition, new-page output, independent repeat groups, source-change rejection, and output-page-only rollback using fake COM objects;
- `corel_status` runtime metadata using a fake Application object.

Temporary path-safety fixtures are created under the operating system's `opencode` temporary directory and removed by the tests.

## Catalog validation

Run independently with:

```powershell
.\.venv\Scripts\python.exe scripts\validate_catalog.py
```

The validator checks server/registry tool parity, API/evidence references, enum/registry versions, error-code parity, CSV consistency, JSON Schemas, and every catalog example.

## Guarded live test

**User decision — 2026-11-03:** Defer live verification to one later consolidated
pass covering all implemented features. Keep running default tests, catalog
validation, and static diagnostics for each implementation batch. Retain the
feature-specific gates below, reconcile coverage before the combined run, and
keep per-feature evidence/status distinct. Pending live gates remain unverified;
the timing decision does not enable either live-test flag now.

`tests/integration/test_corel_live.py` is skipped by default. Its read-only gate checks status/profile metadata and enumerates open documents without binding a target.

The prepared ID-001 object-reference gate uses nested synthetic objects and
duplicate names, measures native identity through stacking reorder, edits the
exact child, tests rename/duplicate/delete, saves and reopens only its own CDR,
and refuses references from the retired document or a restarted bridge. It
retains JSON StaticID/reference readback without claiming persistence before
execution. Gate name: `test_object_references_live`. It remains deferred with
the other nine guarded live gates. See [OBJECT_REFERENCES.md](OBJECT_REFERENCES.md).

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

The prepared object-search gate creates a new two-page synthetic document with
duplicate text names and nested groups. It verifies page/layer/type/text scope,
depth/result/scan limits, stable repeated inspection, and unchanged active
page/layer, selection, units, reference point, and dirty state. It retains CDR
artwork, JSON readback, and a dated report. It remains skipped by default and
must be explicitly enabled with both flags:

```powershell
$env:COREL_LIVE_TESTS = "1"
$env:COREL_LIVE_MUTATION_TESTS = "1"
.\.venv\Scripts\python.exe -m unittest tests.integration.test_corel_live.CorelDisposableDocumentLiveTests.test_find_objects_live -v
```

The focused-inspection gate creates synthetic text and a known RGB rectangle,
including duplicate names. It checks actual text/bounds/fill, bounded previews,
strict selector refusals, and unchanged saved-document dirty state, selection,
page/layer, units, and reference point. It retains CDR and JSON readback without
using existing client artwork. Run it with the same explicit disposable-target
authorization:

```powershell
$env:COREL_LIVE_TESTS = "1"
$env:COREL_LIVE_MUTATION_TESTS = "1"
.\.venv\Scripts\python.exe -m unittest tests.integration.test_corel_live.CorelDisposableDocumentLiveTests.test_focused_object_inspection_live -v
```

The closed-document guard gate creates and saves two owned synthetic documents,
closes the bound one, and verifies edit refusal with the other unchanged:

```powershell
$env:COREL_LIVE_TESTS = "1"
$env:COREL_LIVE_MUTATION_TESTS = "1"
.\.venv\Scripts\python.exe -m unittest tests.integration.test_corel_live.CorelDisposableDocumentLiveTests.test_closed_document_guard_live -v
```

Run only the source-preserving imposition gate with:

```powershell
$env:COREL_LIVE_TESTS = "1"
$env:COREL_LIVE_MUTATION_TESTS = "1"
.\.venv\Scripts\python.exe -m unittest tests.integration.test_corel_live.CorelDisposableDocumentLiveTests.test_imposition_orchestration_live -v
```

This gate creates one synthetic asymmetric vector repeat, verifies fingerprint-gated 0°/180° output on a new page, confirms the source signature remains unchanged, then forces a collision discrepancy and verifies that only the new rollback page is deleted. CorelDRAW X7 cross-page transfer uses `Shape.Copy` plus `Layer.Paste`, which replaces the current system clipboard contents and is reported by the tool.

Do not set either flag in shared automation. A passing run is not enough to claim visual quality or print readiness, and catalog records must remain `implemented_unverified` until the dated report and artifacts are reviewed.
