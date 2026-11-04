# Document raster preflight offline verification — 2026-11-04

Status: `implemented_unverified`. The autonomous goal is active; live CorelDRAW
verification remains deferred to the consolidated campaign.

- Focused suite: `python -m unittest discover -s tests -p test_raster_preflight.py -q`;
  47 passed, zero skips.
- Existing bitmap suite after private-reader reuse: 38 passed, zero skips.
- Full suite: `python -m unittest discover -s tests -q`; 850 tests,
  822 passed, 28 guarded live tests skipped.
- Catalog: 88 tools, 90 records/matrix rows, 313 native members,
  252 checked schemas, 270 examples, 28 enum groups, 69 adapter capabilities.
- Deferred campaign: 88 tools, zero missing explicit native gates.
- Installed evidence: 24 descriptors, `connection_attempted:false`;
  `Shape.PowerClipParent` return interface resolves to `IVGShape`.
- Static diagnostics, catalog/campaign checks, compileall and Git whitespace
  checks passed. Existing tool/schema/example and native-member semantics are
  unchanged; native usage mappings and the shape-enum usage list were extended.

Tests cover inactive-page low DPI, nested groups/effects, PowerClip/group contents,
master deduplication/applied-page reporting, explicitly excluded nonprinting and
included hidden printable layers. Empty scopes are not applicable. Unreadable
bitmap or ancestor geometry, EPS/unknown linking state and relative/OPI semantics
remain indeterminate. Missing/empty/non-file absolute local sources fail; source
files are never decoded and a nondecodable file proves only presence.

Two graph/three structure observations reconcile geometry, metadata, nested
membership/order, native link paths and local file-state fingerprints. Changed
evidence invalidates current statuses and retains observed statuses. Shape/depth
budgets, cycles/aliases, foreign/wrong parent ownership and unreadable child
getters prevent full coverage. Opaque symbol/OLE/EPS/custom/unknown containers
also prevent clean coverage; special effect groups enumerate readable children
while preserving unresolved rendering evidence. Strict schemas reject false
passes, invalid source presence, coercion and any production-ready claim.

Units/reference/dirty/selection/page/layer preservation, unreadable context,
ignored entry/restoration and late target closure are checked. Recorded wrappers
dispatch exact arguments. Preflight remains read-only during mutation quarantine;
failed context verification blocks later writes through existing recovery state.
No native pixel, artwork, clipboard, selection, layer or link write was performed.

Readable primary Corel PDF preflight and X7 resolution help returned HTTP 200.
The SDK `LinkFileName` request returned HTTP 200 without readable API text. Actual
access dates and bounded excerpts are retained in
[../raster_preflight_online_evidence.json](../raster_preflight_online_evidence.json).
The installed getter/ownership evidence is in
[../x7_raster_preflight_api_evidence.json](../x7_raster_preflight_api_evidence.json).

Prepared gate: `CorelDisposableDocumentLiveTests.test_document_raster_preflight_live`.
It checks two owned pages and an inactive nested low-DPI bitmap, prepared PNG
handoff, preserved native context, and retained CDR/PDF/readback artifacts.
Native links/relative/OPI/EPS/master/clip/nonprinting and unusual coordinates need
later native/manual expansion. Source detail/cache freshness, ICC/spot/overprint,
export-generated rasterization, visual fidelity and prepress approval remain
unchecked. Next implementation work is multi-sheet production.
