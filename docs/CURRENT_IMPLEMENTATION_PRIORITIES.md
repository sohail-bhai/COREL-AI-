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

## Active delivery order

### 1. Reliable inspection and common-operation verification

- Implement INS-001: bounded `find_objects` with explicit document/page/layer
  scope, nested group traversal, and deterministic duplicate-name handling.
- Add focused text, bounds, fill, and outline inspection for safe revisions.
- Review the retained common-work CDR evidence and live-verify the applicable
  text replacement, move/resize, duplicate, align, group, save, and PDF tools.
- Detect stale references and refuse ambiguous targets.

**Gate:** The intended object can be found and inspected without mutation;
common edits report actual state on an explicitly authorized disposable target.

### 2. Recovery and operation records

- Complete redacted operation records and busy/timeout recovery behavior.
- Preserve preflight, explicit document binding, overwrite protection,
  discrepancy reporting, and verified rollback for each common workflow.

**Gate:** A forced failure leaves known state and blocks unsafe continuation.
This safety foundation remains required before broader editing and batch work.

### 3. Everyday text and layout controls

- Implement and verify missing paragraph-text and font/size/style/alignment
  controls, text overflow checks, spacing, and color inspection/readback.
- Complete useful gaps in distribution, proportional scaling, rotation,
  z-order, and layer organization using confirmed X7 APIs.

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
