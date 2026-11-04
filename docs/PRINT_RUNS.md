# General artwork print runs

`inspect_print_repeat`, `plan_print_run` and `execute_print_run` create complete
full/partial-sheet runs for an existing native artwork repeat. Template CSV
batches remain available when each copy needs personalized text.

Inspect a named/indexed/session-referenced source, plan its requested quantity
and sheet geometry, review the entire plan, then execute with the returned
`fingerprint` as `approved_fingerprint`. Execution binds a separately owned
editable output document on success. Save/export that output through existing
CDR/PDF tools. No automatic save, export or printing takes place.

The local plan preserves physical repeat size and materializes every used slot
across every sheet. The final sheet contains only the remaining copies: five
copies at two per sheet produce sheets with 2, 2 and 1 copies. Rotation policies
are `never`, `all` and `best_fit`; rotations are 0/90 degrees. Sheet orientation,
per-edge margins, gripper and mark clearance reuse the researched imposition
planner. Clearance reserves space without drawing marks. Bleed is zero.

Two native source scans reconcile measured paths, transforms, names, supported
fill/outline/transparency metadata, text hashes/basic aggregate metadata, bitmap
dimensions/resolution, groups and locked PowerClips. Source context includes
units, reference point, dirty state, selection identities, page/layer membership
and active page/layer. Supported primitives, unlinked text and native bitmaps
must have readable evidence. Live effects, opaque/unknown containers, complex
paint and unlocked PowerClip contents are refused.

Limits: 1000 source shapes, 32 nesting levels, 10000 measured curve segments,
8 MiB manifest, 500 requested copies and 50000 output descendant shapes. Source
document structure uses the existing bounded organization limits. Returned item
references are capped at 100, while all copies receive final verification.

Execution reinspects the source before mutation, makes pristine copies before
placement, verifies original-size transforms and payload, then checks all copies
again after all edits. It checks page order/dimensions, complete root membership,
independent descendant identities and total quantity. Success requires preserved
measured source context. A failure closes only a document proven newly owned;
it restores source context/focus where possible and reports verified or uncertain
cleanup. Pre-existing documents are never discarded. The system clipboard is
replaced and cannot be restored by this contract.

These observations do not establish bitmap pixels/link freshness, complete text
run formatting/glyphs, rendered clipping/visual fidelity, outline-aware trim or
bleed, color/overprint or printer approval. Nested native coordinates can be local
or transformed; comparisons allow supported observations without claiming visual
equivalence. No atomic native lock is available. Results remain
`implemented_unverified` and `production_ready: false`.

Offline tests: `tests/test_print_runs.py`, using independently modeled copies,
curves and transforms. The guarded `test_print_run_live` prepares full/partial
and rotated disposable runs with editable CDR/PDF artifacts for the consolidated
campaign. Native/manual verification has not run. Expanded text/bitmap/gradient/
PowerClip native fixtures and production review remain part of that later work.
