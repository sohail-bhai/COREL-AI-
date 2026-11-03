# Controlled PDF and coverage non-live verification

Date: 2026-11-03. No live CorelDRAW tests were run.

- 22 focused PDF tests pass.
- Default suite: 476 tests, 458 pass and 18 guarded native gates skip.
- Catalog: 61 registered tools, 63 records/matrix rows, 179 API members,
  161 schemas, 189 examples and 46 adapter capabilities.
- Complete verification inventory: 61 tools, no missing native gate candidates.
  Candidate presence still requires assertion review, execution and artifact review.

Coverage includes strict local PDF parsing, every page/box despite summary
truncation, rotated dimensions, direct/composite/Form font program presence,
input/resource limits, zero-bleed native controls, verified settings restoration,
failed/mismatched native output, existing/concurrent output preservation, staged
byte changes and worker quarantine on uncertain restoration.

The template suite now has 25 passing checks, including nested group bounds
changing after text personalization while static leaf geometry remains intact.

Prepared native gates cover controlled PDF, basic document/page/layer/object
inspection, raster placement and standalone contour nesting. They remain pending
with all earlier native/client/manual checks. See [PDF_PRODUCTION.md](../PDF_PRODUCTION.md)
and [CONSOLIDATED_LIVE_VERIFICATION.md](../CONSOLIDATED_LIVE_VERIFICATION.md).
