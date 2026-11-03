# Current Implementation Priorities

**Updated:** 2026-11-03
**Decision:** Prioritize common editing, layout, templates, and print production;
then extend into component-based AI design and smart redesign.

The user reviewed the current Alhamdulillah result and deferred further custom
calligraphy and other-language reference reconstruction. These remain future
capabilities. The retained V2 files, measurements, scripts, and gate reports are
research checkpoints; they are not final visual approval.

This document defines the active delivery order. The older milestone plans
remain technical references, but their reconstruction sequence does not block
common-work implementation. No further Alhamdulillah tracing, typography,
lighting, or fidelity correction is in the active queue.

## Verification timing — user decision 2026-11-03

Defer live CorelDRAW verification until a later consolidated pass covering all
implemented features. Continue implementation and the required non-live tests
for each batch; pending live-only acceptance checks do not block that work.
Keep feature-specific disposable test gates and an explicit coverage inventory
so the combined run can account for every implemented feature and its failures.

API research, preflight, fake-COM recovery/rollback, and product safety remain
required. Features stay `implemented_unverified` until their applicable live
checks and required manual artifact review pass. The timing decision does not
authorize running live tests now or using existing client artwork as fixtures.

## Active delivery order

**Autonomous delivery update — 2026-11-03:** The user authorized continued
implementation and online capability research. Follow the immediate safety
tickets below, then the evidence-backed workflow gaps in
[CAPABILITY_GAP_RESEARCH.md](CAPABILITY_GAP_RESEARCH.md). Broader coverage includes
typography/layout, reusable data-driven jobs, vectors/clipping/effects, production
output, and component AI design/revisions. Continue independent work when an
API/provider/output dependency is unresolved, retain bounded tests and honest
capability status, and keep live verification deferred.

### 1. Reliable inspection and common-operation verification

- INS-001 is implemented: bounded `find_objects` has explicit bound-document,
  page/layer scope, nested group traversal, and deterministic duplicate-name
  retention. Default tests and catalog validation pass; the prepared disposable
  X7 search gate remains pending. See [OBJECT_SEARCH.md](OBJECT_SEARCH.md).
- INS-002 is implemented: focused `get_object_bounds`, `get_text_properties`,
  and `get_fill` provide bounded actual-state readback, strict selectors, and
  explicit unavailable/indeterminate properties. Fake-COM/catalog gates pass;
  the disposable X7 gate remains pending. See [OBJECT_INSPECTION.md](OBJECT_INSPECTION.md).
- Standalone outline inspection remains pending X7 outline-unit research.
- Review the retained common-work CDR evidence and live-verify the applicable
  text replacement, move/resize, duplicate, align, group, save, and PDF tools.
- ID-001 document liveness is implemented: targeted operations check bounded
  open-document membership and invalidate closed/replaced bindings without
  active-document fallback. See [DOCUMENT_TARGETING.md](DOCUMENT_TARGETING.md).
- ID-001 object references are implemented: eleven inspection/editing tools
  accept signed bridge/document/page/layer/group references, reject stale or
  ambiguous identities, and preserve targeting after reorder. Fake-COM and
  dispatcher gates pass; native lifecycle verification is deferred. See
  [OBJECT_REFERENCES.md](OBJECT_REFERENCES.md).
- SAFE-001 is implemented: opt-in bounded external JSONL events cover all 74
  MCP tools, with input type counts, worker target IDs, result/created IDs,
  duration, rollback flags and separate caller/worker completion. Redaction,
  filesystem failure, capacity, concurrency and timeout event tests pass. See
  [OPERATION_RECORDS.md](OPERATION_RECORDS.md).
- SAFE-002 is implemented: one admitted native call, pending cancellation,
  explicit worker state, bounded outcome history, native edit-stage tracking,
  partial-failure quarantine and exact-ID reconciliation. Forty-one focused tests
  pass; the synthetic native gate and real modal/busy checks remain deferred.
  See [WORKER_RECOVERY.md](WORKER_RECOVERY.md).
- Typography is implemented: paragraph frames, font catalog, reference-aware
  whole-story styles and native overflow/spacing readback pass automated gates.
  Native behavior, spacing writes and auto-fit remain deferred. See
  [TYPOGRAPHY.md](TYPOGRAPHY.md).
- Layout transforms are implemented: finite matrix inspection, explicit-pivot
  rotation, mirroring, native sibling order and measured distribution pass
  automated gates. See [LAYOUT_TRANSFORMS.md](LAYOUT_TRANSFORMS.md).
- Templates are implemented: named text-field snapshots, literal CSV, full-data
  validation and full/partial output sheets pass 25 focused non-live checks.
  Owned-output cleanup, final row readback and measured source preservation are
  covered. See [TEMPLATE_BATCHES.md](TEMPLATE_BATCHES.md).
- Controlled zero-bleed PDF export and local page/font inspection are implemented
  with 22 focused checks and a deferred native gate. All 74 tools are included in
  the consolidated coverage inventory. See [PDF_PRODUCTION.md](PDF_PRODUCTION.md)
  and [CONSOLIDATED_LIVE_VERIFICATION.md](CONSOLIDATED_LIVE_VERIFICATION.md).
- General vectors are implemented: line/cubic creation, full geometry inspection,
  fingerprint-guarded node/handle edits, weld/trim/intersect, combine and break-apart
  pass 33 focused checks. Source geometry/appearance and owned-output cleanup are
  verified in non-live tests. Native closure, shaping and winding remain deferred.
  See [VECTOR_EDITING.md](VECTOR_EDITING.md).
- Source-preserving node insertion/deletion revisions are implemented with
  exact line/cubic subdivision, explicit reconnection and full node mapping.
  Twenty-two focused checks and the full non-live suite pass. CopyAssign native
  coordinates/closure and visual review remain deferred. See [VECTOR_TOPOLOGY.md](VECTOR_TOPOLOGY.md).
- Controlled RGB/CMYK process colors are implemented: exact native components,
  vector/text geometry and other-channel preservation pass 18 focused checks.
  Replacing non-uniform fills is explicit; outline colors preserve raw widths.
  Native color/print verification and outline-width units remain deferred/unresolved.
  See [PROCESS_COLORS.md](PROCESS_COLORS.md).
- Transparency inspection and normal-mode uniform fill/outline/both application/
  removal are implemented with 18 focused checks. Native percentage/scope/merge
  readback and measured/base-appearance preservation gate success; partial failures
  quarantine while inspection remains available. See [TRANSPARENCY.md](TRANSPARENCY.md).
- PowerClip inspection, copied frame/content creation and extraction/rebuild
  workflows are implemented with 34 focused checks. Mixed editable content,
  contain/cover fitting, nested clip locks and owned-output recovery are covered.
  Native clipping/extraction and manual artifact review remain deferred; in-place
  clip editing is future work. See [POWERCLIP.md](POWERCLIP.md).
- Next: gradients, contour offsets and broader prepress;
  spacing/fitting, layer organization and existing-document checkpoints remain gaps.

**Gate:** The intended object can be found and inspected without mutation;
common edits report actual state on an explicitly authorized disposable target.

### 2. Recovery and operation records

- Redacted operation records and busy/timeout reconciliation are implemented.
  Continue tested existing-document checkpoint and specialized rollback policies
  alongside the relevant workflow slices; native verification remains deferred.
- Preserve preflight, explicit document binding, overwrite protection,
  discrepancy reporting, and verified rollback for each common workflow.

**Gate:** A forced failure leaves known state and blocks unsafe continuation.
This safety foundation remains required before broader editing and batch work.

### 3. Everyday text and layout controls

- Paragraph creation, font/size/style/alignment revisions, font catalog and
  chain-overflow/native-spacing inspection are implemented. Continue spacing
  writes, glyph coverage, safe fitting and the deferred native typography gate.
- Proportional resizing, rotation, mirroring, distribution and native sibling
  order are implemented. Continue editable/visible layers, page organization,
  guides and outline-aware/safe-area reflow using confirmed X7 APIs.

**Gate:** Create and revise a simple card, label, or flyer while preserving
editable text, exact dimensions, object identity, and recovery behavior.

### 4. Reusable templates and deterministic batches

- Named text fields, literal CSV, complete preflight, duplicate policy and
  independent full/partial output sheets are implemented. Final native readback
  checks every record, field/item bounds, overflow and measured source state.
- Image personalization, mixed/linked text, safe automatic fitting and additional
  numbering variants remain gaps. Native and manual verification stay deferred.

**Gate:** A small approved batch has correct content/counts, editable objects,
unchanged source artwork, and no silent output overwrite.

### 5. Complete print-production workflows

- Finish curved-contour X7 verification and automatic repeat-unit inspection.
- Extend existing imposition to verified multi-sheet and partial-sheet output.
- Controlled zero-bleed PDF export and parsed all-page/font checks are implemented.
  Continue job-specific nonzero bleed, marks, ICC/PDF-X, spot/overprint checks
  and general multisheet imposition after the required API/output research.

**Gate:** Quantity, spacing, source preservation, page count, and export checks
pass; `print_ready` is reported only when all applicable checks pass.

## Future backlog

### Accepted design expansion — 2026-11-03

The user approved these additions to the implementation plan. They are planned
capabilities, not claims of implemented tools. The five active priorities above
remain the initial delivery order; these additions depend on their inspection,
editing, recovery, and preflight gates.

- **Component-based AI design generation:** Generate artwork components
  separately, combine them with native editable text and vector objects, and
  allow an individual component to be removed, regenerated, and replaced while
  preserving approved parts. Generated images remain raster unless actually
  reconstructed or traced into verified editable vectors.
- **Smart redesign:** Adapt an approved design to the requested physical size,
  aspect ratio, bleed, safe area, and raster resolution. Reflow the layout and
  regenerate only components that need new geometry or sufficient pixels;
  preserve the approved source and review replacements before finalizing.
- **Reference-to-vector recreation:** Rebuild simpler logos and reference
  artwork as editable objects, with explicit raster/vector status and fidelity
  limits. Custom calligraphy and complex-script reconstruction remain deferred.
- **Image preparation:** Background removal, cropping, cleanup, and effective
  resolution checks using versioned copies of the source images.
- **Design quality checks:** Combine measured layout, font, safe-area, and
  resolution checks with clearly identified visual-review warnings.
- **Product mockups:** Preview approved artwork on products such as shirts,
  mugs, boxes, and signs, separately from production artwork.
- **Revision history:** Keep local design/component versions, compare changes,
  and restore a prior revision with verified document state.

Company-specific brand kits, a job manager, additional business integrations,
and general export-preset expansion are excluded from this scope. Existing CDR
saving and controlled PDF output remain part of the print-production workflow;
the image-generation provider interface is needed for the accepted design work.

Implementation steps, dependencies, and acceptance gates are in
[Implementation Plan, section 10](IMPLEMENTATION_PLAN.md#10-approved-design-expansion--2026-11-03).

### Deferred reconstruction research

Custom Arabic/calligraphy tracing, other complex-script reconstruction, and
advanced reference fidelity remain in the existing V2 and reconstruction plans.
Resume them only when the user brings that work back into scope. Existing text
capabilities do not need to be removed to implement this priority change.
