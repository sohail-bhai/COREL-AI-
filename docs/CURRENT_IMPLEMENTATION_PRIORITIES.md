# Current Implementation Priorities

**Updated:** 2026-11-02
**Decision:** Prioritize common editing, layout, templates, and print production.

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
- SAFE-001 is implemented: opt-in bounded external JSONL events cover all 55
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
- Next: reusable templates and batch production, then full print workflows;
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

- Add named-field template updates for cards, labels, tickets, and certificates.
- Add local CSV-driven personalization and numbering with missing-field,
  duplicate-record, sequence, overflow, and count checks before mutation.
- Keep reusable source templates unchanged and materialize distinct outputs.

**Gate:** A small approved batch has correct content/counts, editable objects,
unchanged source artwork, and no silent output overwrite.

### 5. Complete print-production workflows

- Finish curved-contour X7 verification and automatic repeat-unit inspection.
- Extend existing imposition to verified multi-sheet and partial-sheet output.
- Add job-specific bleed, margins, gutters, marks, output layers, controlled
  PDF export, and a production report backed by actual checks.

**Gate:** Quantity, spacing, source preservation, page count, and export checks
pass; `print_ready` is reported only when all applicable checks pass.

## Future backlog

Custom Arabic/calligraphy tracing, other complex-script reconstruction, and
advanced reference fidelity remain in the existing V2 and reconstruction plans.
Resume them only when the user brings that work back into scope. Existing text
capabilities do not need to be removed to implement this priority change.
