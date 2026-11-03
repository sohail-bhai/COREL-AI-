# Future Implementation Plan — CorelDRAW AI Operator

- **Plan date:** 2026-10-31
- **Target:** CorelDRAW X7 17.0.0.491 on Windows 11
- **Runtime:** Python 3.11, MCP SDK v1, pywin32
- **Planning horizon:** prototype stabilization through production-ready local operator
- **Strategic reference:** `PLAN.md`
- **Product contract:** `ANTIGRAVITY_MASTER_SPEC.md`

**Priority update — 2026-11-02:** Follow
[`CURRENT_IMPLEMENTATION_PRIORITIES.md`](CURRENT_IMPLEMENTATION_PRIORITIES.md)
for the active delivery order: inspection and common-operation verification,
recovery, everyday text/layout, templates/batches, then print production.
Custom calligraphy and other-language reconstruction are deferred by the user;
the milestones below remain technical references and safety gates.

## 1. Purpose

This is the operational plan for the next implementation stages. `PLAN.md` remains the
long-range product roadmap; this document defines the order of work, how each milestone
should be implemented, and the evidence required before moving forward.

The next releases should prioritize reliability over tool count. New tools are useful only
when the bridge can identify the correct document and object, validate the full operation,
recover safely from failure, read back the actual result, and report limitations honestly.

## 2. Current baseline

As of this plan date:

- The bridge connects to CorelDRAW X7 through one serialized COM STA worker.
- Document targeting, stable result envelopes, error codes, an X7 adapter, diagnostics,
  catalog validation, inspection tools, sheet-layout planning, and chest-number generation
  are present.
- The registry contains 38 records: 33 `implemented_unverified`, four `planned`, and one
  `research_required`.
- A disposable X7 regression has exercised `create_chest_number_batch`, but manual CDR/PDF
  review and complete evidence updates are still required.
- The design-plan vertical slice (`validate_design_plan`, `preview_design_plan`, and
  `execute_design_plan`) has schema/runtime parity coverage, blocking preflight, asset-path
  preflight, actual-state readback, sanitized errors, and verified fake-COM rollback behavior.
- The current working tree passes 140 default tests with five live tests skipped, and the
  standalone catalog validator passes. A disposable X7 design-plan run has passed; manual CDR
  artifact review is still required before the tools can be marked `verified`.
- All implemented tools remain conservatively unverified until their applicable live and
  manual checks are recorded.

## 3. Required architecture boundary

Keep the existing flow and make each boundary explicit:

```text
Antigravity / OpenCode
        |
        v
MCP wrappers (`corel_operator/server.py`)
        |
        v
Pure validation and workflow planning
        |
        v
Serialized dispatcher / one COM STA thread
        |
        v
Corel bridge + X7 adapter
        |
        v
Explicitly bound CorelDRAW document
```

Rules for future work:

1. MCP wrappers stay thin; they validate transport-level inputs and dispatch named methods.
2. Pure calculations and schema validation must not connect to CorelDRAW.
3. Every COM object is created, resolved, and used on the dispatcher thread.
4. Version-specific members and enum values belong in `corel_operator/adapters/x7.py`.
5. Mutations use an explicitly bound document; window focus is never authorization.
6. Every mutation reads back actual state and reports discrepancies.
7. The registry, capability matrix, tests, and docs change in the same implementation batch.

## 4. Delivery roadmap

### Milestone 0 — Finish and stabilize the current design-plan slice

- **Priority:** P0 — do this before adding more capabilities
- **Estimated effort:** 2–4 development days plus a disposable X7 review

#### Implementation

1. Preserve the current in-progress files as one focused change set; do not mix unrelated
   editing tools into it.
2. Keep the design-plan registry examples conformant with the shared target-document schema
   and keep the standalone catalog validator passing throughout the slice.
3. Extend `tests/test_design_plans.py` to cover:
   - valid rectangle, ellipse, text, and artwork plans;
   - unknown and missing properties;
   - Boolean-as-number rejection, NaN/infinity, size limits, and element-count limits;
   - duplicate IDs and unsafe/invalid artwork paths;
   - canvas-bound warnings versus blocking errors;
   - deterministic preview output and z-order;
   - expected-element-count validation.
4. Add fake-COM execution tests for success, object styling, actual-state readback, failure at
   each element type, command-group cleanup, rollback success, and rollback failure.
5. Make `ready_for_execution` false when a blocking preflight condition exists. Warnings must
   not be silently treated as approval.
6. Ensure the design-plan schema and runtime validator enforce the same rules. Prefer one
   canonical Draft 2020-12 schema and test runtime behavior against it.
7. Return safe structured error details. Do not include raw COM exception strings in the MCP
   response or report rollback when rollback was not verified.
8. Execute the existing guarded live test that creates its own document, runs a small synthetic
   plan, inspects resulting objects, saves to a unique temporary path, and closes only that
   document.
9. Update the registry, matrix, capability catalog, changelog, test count, and dated report.

#### Exit gate

- Default tests and `scripts/validate_catalog.py` pass.
- No default test starts CorelDRAW.
- A failed plan cannot be reported as rolled back without a post-rollback state check.
- A disposable live plan produces editable objects with the expected IDs and bounds.
- The status remains `implemented_unverified` until manual artifact review is recorded.

### Milestone 1 — Complete inspection and reliable identity

- **Priority:** P0
- **Estimated effort:** 1–2 weeks

#### Capabilities

- `find_objects`
- `get_object_bounds`
- `get_text_properties`
- `get_fill`
- `get_outline` after outline-unit research
- `get_layer_info`
- intentional top-level or recursive group traversal

#### Implementation

1. Add a pure object-reference model containing bridge/document session, page/layer
   identity, ancestor-group and native shape identity, StaticID, full object name,
   type, and diagnostic indices. Emit null when complete metadata is unavailable.
2. Resolve references inside `CorelBridge` on the COM worker. Never persist COM proxies or
   silently fall back to the active document.
3. Authenticate issued references, require exact bridge/document session, and resolve
   exact page/layer/group/native shape identity with matching StaticID, name, and type.
   Never fall back from stale references to names/indices. Legacy names and indexes
   remain separate explicit active-page selectors.
4. Return `AMBIGUOUS_SELECTOR` for duplicate matches and `OBJECT_NOT_FOUND` for stale IDs.
5. Add bounded traversal options (`recursive`, `max_depth`, `max_results`) so groups cannot
   create unbounded enumeration.
6. Detect a user-closed target document and clear the stale binding instead of acting on a
   newly active document.
7. Test duplicate names, reordered shapes, nested groups, multiple pages, master layers,
   closed documents, and process restart semantics with fake COM objects.
8. Live-test StaticID behavior across reorder, save/reopen, and a bridge restart. Record what
   is and is not persistent; do not assume persistence from one run.

#### Exit gate

Before mutation, the bridge can explain exactly which document and object will be changed.
Duplicate names, stale targets, groups, and page boundaries have deterministic behavior.

### Milestone 2 — Transaction safety, recovery, and operation records

- **Priority:** P0
- **Estimated effort:** 1–2 weeks

#### Implementation

1. Add a redacted JSON Lines operation logger, disabled or minimally configured by default.
   Store logs outside the repository and never write to MCP stdout.
2. Record operation ID, timestamp, tool, profile, target IDs, non-confidential input summary,
   result code, created object IDs, duration, and rollback outcome.
3. Add explicit dispatcher state: `idle`, `running`, `timed_out_but_running`, and `unavailable`.
   If an MCP timeout occurs while COM continues, reject subsequent mutations until the worker
   reaches a known state.
4. Validate X7 command-group/Undo semantics on a disposable document. A successful method
   call is insufficient; compare object identity/count and relevant properties after Undo.
5. Define rollback policy by target type:
   - new bridge-created document: command-group rollback and verified cleanup;
   - existing authorized document: require a tested checkpoint strategy before multi-step
     execution, otherwise reject the plan with a clear unsupported/safety error;
   - export: unique output paths and cleanup only for files created by the failed operation.
6. Research an X7-safe copy/checkpoint API before relying on it. Do not use `SaveAs` as a
   checkpoint if it changes the user's document identity or path.
7. Add bounded operation counts, elapsed-time budgets, and asset-size limits to plans and
   batches.

#### Exit gate

A forced failure leaves a disposable document in the verified pre-operation state, or the
result explicitly reports that recovery is incomplete and blocks further mutation.

### Milestone 3 — Core editing, typography, and layout vocabulary

- **Priority:** P1
- **Estimated effort:** 2–4 weeks

Implement in small vertical slices, in this order:

1. **Arrange:** align to page, align selected objects, distribute, group, ungroup, and z-order.
2. **Transform:** rotation and proportional scaling with explicit anchor semantics.
3. **Appearance:** no fill, no outline, verified outline units, and CMYK without silent RGB
   conversion.
4. **Typography:** font family/size/style, text color, alignment, paragraph text, and spacing.
5. **Page/layer:** page size/orientation, create/activate page, create/activate layer, and move
   object to layer.
6. **Destructive editing:** deletion or convert-to-curves only after checkpoint and explicit
   confirmation policies pass live tests.

#### How to implement each slice

1. Add X7 documentation/type-library evidence to the raw inventory.
2. Record exact signatures and enum values in the X7 adapter.
3. Add validation and fake-COM tests before registering the MCP tool.
4. Implement one bridge method using the bound document and identity resolver.
5. Read back bounds, appearance, text, layer, and identity as applicable.
6. Add a thin server wrapper and complete registry schemas/examples.
7. Run a disposable X7 test and manually inspect operations whose appearance cannot be proven
   from properties alone.

#### Exit gate

A simple letterhead, badge, or card can be created and revised while keeping text and shapes
editable, preserving exact dimensions, and reporting actual final properties.

### Milestone 4 — Production design-plan engine v1

- **Priority:** P1
- **Estimated effort:** 1–2 weeks after Milestones 1–3

#### Implementation

1. Publish one immutable `design-plan/1.0` schema. Future incompatible formats get a new
   version rather than changing v1 semantics in place.
2. Keep the v1 allowlist intentionally small: document setup, supported primitives, artistic
   text, approved artwork import, verified styling, transforms, grouping, and z-order.
3. Split execution into four explicit stages:
   - parse and schema validation;
   - capability/safety preflight with no side effects;
   - transactional execution;
   - post-execution inspection and discrepancy report.
4. Preflight every asset path, object ID, canvas bound, capability, expected object count,
   confirmation requirement, and maximum operation count before the first mutation.
5. Produce a deterministic plan hash. Execute the exact validated plan/hash so validation and
   execution cannot accidentally use different content.
6. Return per-operation requested values, actual values, warnings, object references, and
   rollback state. Do not reduce the result to a single `executed: true` flag.
7. Add a process-local execution ID/retry policy so a client retry cannot silently duplicate a
   completed plan. Document that process-local protection does not survive restart.

#### Exit gate

The client can validate, preview, execute, inspect, and revise a small design without bypassing
the safeguards of its atomic tools.

### Milestone 5 — Deterministic batch production

- **Priority:** P1
- **Estimated effort:** 2–3 weeks

#### Implementation order

1. Complete `create_chest_number_batch` readback, text-fit behavior, overflow reporting, and
   verified rollback.
2. Implement `arrange_n_up_print_sheet` using the existing pure sheet-layout calculator.
3. Add multi-page placement only after create/activate-page APIs are verified on X7.
4. Add pure sequence validation for gaps, duplicates, leading zeros, and requested count.
5. Add CSV ingestion using Python's CSV parser with explicit encoding, required headers,
   record limits, duplicate-row policy, and a preview-only field mapping.
6. Implement one template workflow (ID cards or labels) before generalizing to certificates,
   tickets, cards, and tags.
7. Pre-calculate all placements and output paths before editing CorelDRAW.
8. Produce a machine-readable manifest containing source-row ID, generated object IDs, page,
   placement, status, and output path.

#### Required regression

- Generate labels `001` through `200` with exact ordering and no gaps or duplicates.
- Verify page capacity, overflow behavior, leading zeros, object count, and saved editability.
- Test malformed, duplicate, empty, oversized, and non-ASCII CSV values without mutation.

#### Exit gate

A 001–200 job can be validated before mutation, generated deterministically across the required
pages, inspected, saved to unique outputs, and reconciled against its manifest.

### Milestone 6 — Preview and production preflight

- **Priority:** P1
- **Estimated effort:** 2–3 weeks

#### Implementation

1. Add deterministic page and selected-object preview export with explicit dimensions,
   resolution, page, background, and output path.
2. Add property-based checks first:
   - page size/orientation;
   - objects outside page, bleed, or safe bounds;
   - font availability and editable/curve state;
   - bitmap effective resolution and missing/linked assets;
   - declared RGB/CMYK/spot-color intent;
   - duplicate IDs and incomplete batch data.
3. Add overlap checks with clear exclusions; intentional overlap must not be treated as an
   automatic failure.
4. Verify exported PDF existence and page boxes with a deliberately selected PDF library.
   Pin it as a direct dependency and add fixture-based tests before using it in live preflight.
5. Report each check as `passed`, `failed`, `warning`, or `not_checked`, including evidence.
6. Never emit an unconditional `print_ready` result. Report readiness only against explicitly
   supplied job requirements and list every unchecked requirement.

#### Exit gate

The bridge can export a reproducible preview and provide an honest, machine-readable preflight
report that distinguishes verified facts from warnings and unperformed checks.

### Milestone 7 — Visual comparison and reference recreation

- **Priority:** P2 — begin only after deterministic preflight works
- **Estimated effort:** 3–5 weeks plus provider evaluation

#### Implementation

1. Export a local preview and divide a reference into editable text, simple native shapes, and
   complex artwork regions.
2. Rebuild simple regions through the design-plan engine; import complex approved assets.
3. Put vision/image providers behind an interface separate from the Corel bridge.
4. Require explicit consent before any user image, preview, or prompt leaves the machine.
5. Store credentials only in environment/OS secret facilities and redact provider payloads
   from operation logs.
6. Return measurable differences (bounds, scale, alignment, color samples where meaningful)
   and request approval for subjective corrections.

#### Exit gate

The system can iteratively improve a reference-based layout while keeping supported elements
editable and clearly reporting visual differences it cannot resolve.

### Milestone 8 — Client compatibility, version expansion, and packaging

- **Priority:** P2
- **Estimated effort:** 1–2 weeks per tested client/version target

1. Run the same discovery and representative tool calls from Antigravity and OpenCode.
2. Keep client configuration in docs/config fragments; do not add vendor logic to the bridge.
3. Add another CorelDRAW release only through a new adapter and a machine/profile-specific
   regression suite.
4. Add a lock file and reproducible environment setup after direct dependencies are settled.
5. Evaluate an installer or managed local service only after startup, logs, upgrades, and
   multi-client ownership behavior are defined.

## 5. Standard implementation workflow for every capability

Each new capability follows this sequence:

| Step | Deliverable | Required result |
|---:|---|---|
| 1 | X7 research | Exact class/member/signature, enum values, and side effects recorded |
| 2 | Catalog proposal | Status, risk class, confirmation, profile, limitations, and test plan |
| 3 | Pure validation | Units, ranges, defaults, limits, path rules, and deterministic errors |
| 4 | Adapter update | Version-specific constants/capability evidence centralized |
| 5 | Bridge method | Bound target, STA-only COM use, no active-document fallback |
| 6 | Readback | Actual object/document properties and discrepancy reporting |
| 7 | MCP wrapper | Thin wrapper with stable tool name and result envelope |
| 8 | Non-live tests | Schema, pure logic, fake COM, errors, timeout/recovery behavior |
| 9 | Live test | Explicitly enabled disposable document and unique output paths |
| 10 | Release evidence | Registry, matrix, docs, changelog, report, and status update |

If X7 evidence is missing at Step 1, stop and mark the capability `research_required`. If a
safe implementation is not possible, mark it `unsupported` rather than adding a raw COM or
macro escape hatch.

## 6. Immediate execution queue

**Autonomous delivery update — 2026-11-03:** Continue these safety tickets and
then the expanded workflow backlog in [CAPABILITY_GAP_RESEARCH.md](CAPABILITY_GAP_RESEARCH.md).
That research maps all 44 registered tools into 15 workflow families against
12 official sources; it does not imply complete X7 support for modern features.
Keep research dependencies explicit and implement evidenced batches autonomously.

These are the next reviewable tickets:

| Order | Ticket | Work | Acceptance |
|---:|---|---|---|
| 1 | DP-001 | Complete schema/runtime edge-case parity tests | Unknown fields, limits, NaN, and unsafe inputs fail before COM |
| 2 | DP-002 | Separate blocking preflight failures from warnings | `ready_for_execution` reflects actual safety state |
| 3 | DP-003 | Extend fake-COM execution/readback tests | All element types, styling, and discrepancies covered |
| 4 | DP-004 | Prove and report rollback behavior | Forced failure has verified post-state |
| 5 | DP-005 | Run guarded disposable design-plan test | Dated report and editable CDR produced |
| 6 | INS-001 | Bounded `find_objects` implemented; disposable X7 gate prepared | Duplicate/nested results deterministic in fake-COM tests; live gate pending |
| 7 | INS-002 | Focused text, bounds, and native fill inspection implemented; disposable X7 gate prepared | Strict selectors and bounded actual readback pass fake-COM/schema gates; live gate pending |
| 8 | ID-001 | Document-liveness guard and signed object references implemented; lifecycle X7 gate prepared | Closed/replaced/stale/ambiguous targets are refused; nested edits and reorder pass fake-COM/dispatcher tests; live gate pending |
| 9 | SAFE-001 | Opt-in bounded external operation records implemented | All 47 MCP tools have caller/worker events; redaction/storage/timeout event tests pass; no content on stdout |
| 10 | SAFE-002 | Explicit worker state and guarded reconciliation implemented; native gate prepared | Pending cancellation, late-result quarantine, native-stage tracking, partial-failure acknowledgement and exact-ID reconciliation pass automated gates; live verification deferred |

DP-001 through DP-005 now pass their automated and disposable-X7 gates. Manual review of the
dated design-plan CDR remains pending, so the tools retain `implemented_unverified` status.
`INS-001` now passes its default tests and catalog/schema gates; the prepared
disposable-X7 search gate remains pending. Its IDs/paths remain inspection-only;
separate signed object references are accepted by the common selector tools.
`INS-002` now passes fake-COM, strict request/result schema, and catalog gates;
its disposable-X7 geometry/text/fill and unchanged-state gate is prepared.
See [OBJECT_INSPECTION.md](OBJECT_INSPECTION.md). `ID-001` implements the
[document guard](DOCUMENT_TARGETING.md) and [object references](OBJECT_REFERENCES.md).
Scope/lifecycle/limits and reference-aware edits pass fake-COM/dispatcher gates;
native save/reopen/restart verification remains deferred. SAFE-001 now implements
[redacted operation records](OPERATION_RECORDS.md); SAFE-002 implements
[worker state/reconciliation](WORKER_RECOVERY.md). The immediate safety tickets
pass their non-live gates; native verification remains deferred. Editable
typography/layout is next, with existing-document checkpoints retained as a
separate recovery requirement. See
[OBJECT_SEARCH.md](OBJECT_SEARCH.md) for the separate search contract/live gate.

Do not begin broad typography, visual AI, or additional batch types until tickets 1–10 pass
their applicable API-research and automated safety gates. Per the 2026-11-03 user decision,
live-only acceptance checks are deferred to the consolidated verification pass in section 7.

## 7. Test and release gates

### Commands that must pass for every non-live batch

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe scripts\validate_catalog.py
.\.venv\Scripts\python.exe -m corel_operator.diagnostics --static-only
```

### Evidence levels

1. **Planned:** schema/direction exists; no implementation claim.
2. **Research required:** X7 signature or behavior is unresolved.
3. **Implemented unverified:** code and non-live tests pass, but required X7/manual evidence is
   incomplete.
4. **Verified:** dated disposable X7 test passes, artifacts receive required manual review,
   limitations are recorded, and the catalog links the evidence.

### Consolidated live verification — user decision 2026-11-03

The user requested one later verification pass covering all implemented features.
Continue non-live implementation batches with the required automated gates;
defer live-only acceptance checks rather than running them after each feature.
Keep tools `implemented_unverified` while applicable X7/manual evidence is pending.

Before that combined pass, reconcile every registered feature with its test
coverage and required artifacts, retain feature-specific disposable gates, and
identify missing coverage. Run the suite sequentially against new synthetic
documents when the user initiates the live campaign, record per-feature results
and failures, and complete the required artifact review before status promotion.
No automatic live run is authorized by this timing decision. API research,
preflight, recovery/rollback testing, and production safety requirements continue
to apply throughout implementation.

### Release rules

- One focused feature or safety slice per commit/review.
- Never run live mutation tests against an existing user document.
- Never commit generated CDR/PDF files, private artwork, credentials, or local logs.
- Update `CHANGELOG.md`, catalog records, capability matrix, tests, and reports together.
- A new tool may increment the package minor version; increment the tool-schema version only
  for incompatible request/response semantics.
- Do not mark a milestone complete while default tests or catalog validation fail.

## 8. Main risks and mitigations

| Risk | Mitigation |
|---|---|
| X7 differs from modern API docs | Use X7 docs/type library and live disposable tests only |
| COM call outlives MCP timeout | Track worker busy state and block unsafe follow-up calls |
| Focus changes to another document | Resolve only the explicitly bound document/session |
| Names/indexes become stale | Composite references, ambiguity errors, and readback |
| Undo is not truly transactional | Live fault injection plus post-rollback state verification |
| Catalog drifts from server | Run parity/schema validation in every default test run |
| Batch partially mutates a job | Preflight complete input and use verified transactional boundaries |
| Export is mistaken for print readiness | Requirement-based preflight with `not_checked` states |
| Private artwork leaves the machine | Local-first processing and explicit external-upload consent |
| Too many model-facing tools cause confusion | Curated atomic tools plus deterministic workflow tools |

## 9. Definition of production-ready v1

The first production-ready release is reached when a user can safely:

1. create or explicitly bind a document;
2. inspect pages, layers, groups, objects, text, and appearance unambiguously;
3. validate and preview a bounded design or batch plan with no side effects;
4. execute it with verified rollback/recovery behavior;
5. inspect requested versus actual results and make targeted revisions;
6. generate a deterministic 001–200 batch with a reconciliation manifest;
7. save an editable CDR and export a unique PDF/preview;
8. receive a requirement-based preflight report with honest unchecked items; and
9. complete the workflow without modifying an unauthorized document or silently overwriting
   an output.

Capabilities outside this definition remain future work, not implied support.
