# INS-002 focused inspection — automated verification

- **Date:** 2026-11-03
- **Bridge/schema:** 0.6.0 / tool-schema v1
- **Profile:** CorelDRAW X7 17
- **Result:** Automated gates pass; live X7 verification pending.

## Implemented behavior

- `get_object_bounds`: finite inch bounds with ruler-origin disclosure and
  unit/reference restoration; restoration failures return an error.
- `get_text_properties`: bounded story content and actual aggregate formatting,
  with unavailable, indeterminate and truncated properties explicitly reported.
- `get_fill`: actual fill type and native uniform RGB/CMYK/gray/spot values,
  with missing channels and capped summaries explicitly reported.
- All three require a unique top-level active-page name or explicit index on
  the bound document, return actual identity, refuse ambiguous names, and
  sanitize failed COM reads.
- Shared text readback preserves undefined bold values as null.

## Verification

| Gate | Result |
|---|---|
| Default unittest discovery | PASS — 256 tests; 8 live tests skipped |
| Focused inspection coverage | PASS — 34 tests |
| Catalog validation | PASS — 44 registered tools; 46 records; 138 examples |
| Adapter metadata | PASS — 32 capabilities; 31 available; 0 verified |
| Static diagnostics | PASS — X7 registration present; no connection attempted |
| Diff whitespace check | PASS |

Focused tests cover validation before document access, duplicate and missing
targets, nested/page boundaries, bounded enumeration, no active-document
fallback, Unicode/capped/empty content, undefined style codes, partial reads,
native color models, bounded summaries, geometry/context failures, arithmetic
overflow, artwork preservation, and strict request/actual-result schemas.
Server tests verify the serialized dispatcher arguments for the new wrappers.

## Remaining evidence

`test_focused_object_inspection_live` is prepared and skipped by default. It
creates a disposable synthetic CDR, verifies known geometry/text/RGB and
duplicate-name refusals, checks saved-document dirty state and selection,
page/layer, units/reference preservation, and retains JSON readback and a report.
See [../TESTING.md](../TESTING.md) for the explicit opt-in command.

No X7 runtime, visual-editability, print-ready, persistent-ID, text-run,
overflow, complex-fill or outline-unit verification is claimed by this batch.
ID-001 stale document/object-reference handling remains the next ticket.
