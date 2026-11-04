# Print run offline verification — 2026-11-04

Scope: general native-artwork repeat inspection, complete sheet planning and
source-preserving creation of independently owned editable sheet documents.
No live CorelDRAW or browser/preview operation was performed.

Results:

- Focused repeat-run suite: 23 tests pass.
- Default suite: 874 tests, 845 pass, 29 guarded native tests skipped.
- Catalog: 91 registered tools, 93 records/matrix rows, 313 native members,
  264 checked schemas, 279 checked examples, 28 enum groups, 72 capabilities.
- Consolidated inventory: 91 tools, zero missing explicit native gates.

The independent scene model tests complete vector coordinates/transforms and
deep native copies across output pages. Five copies with capacity two produce
2/2/1 sheets; orientation and quarter-turn placement preserve physical size.
Checks cover nested groups/locked clips, bitmap/text metadata, exact quantities,
production allowances, stale/tampered manifests/plans, source dirty/selection
changes, reused/foreign receipts, wrong placement, late copy/sheet corruption,
stray artwork, bounded item references, strict nested output schemas and cleanup.

Failures discard only proven owned outputs. Pre-existing/foreign documents are
never discarded. Source changes and failed output closure leave cleanup
unverified instead of claiming a safe recovery. Inspection is classified as
read-only in the worker registry; execution remains tracked as mutating.

API dependencies reuse existing primary/type-library evidence for native
copy/paste/duplicate, pages/layers, transforms, vector/PowerClip and gradient
inspection. No additional provider, browser or cross-session resource was used.

All three tools stay `implemented_unverified` and production readiness stays
false. The guarded native gate is prepared for the later consolidated campaign;
it must establish real clipboard/copy/coordinate/context behavior and save
independent editable CDR/PDF evidence. Expanded bitmap/text/gradient/PowerClip
fixtures, visual fidelity, source pixels/glyphs and production acceptance remain
pending. See [PRINT_RUNS.md](../PRINT_RUNS.md).
