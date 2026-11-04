# Changelog

All notable changes to the CorelDRAW AI Operator will be documented in this file.

The project follows Semantic Versioning while experimental and keeps tool-schema compatibility separate from package versions. Dates use `YYYY-MM-DD`.

## [Unreleased]

### Added

- Two local raster tools for immutable source inspection and fingerprint-guarded
  source-preserving PNG/TIFF crop/quarter rotation/flips/fitting. Forty-nine checks
  cover decoded pixels, all EXIF orientations, grayscale/palette transparency,
  mode/ICC/DPI preservation, stale sources, publication races, owned-output cleanup,
  strict schemas and redacted records. Primary Pillow evidence is retained;
  Corel import and visual review remain deferred. The surface has 87 tools;
  775 automated checks pass and 27 guarded live gates are skipped.
- Native bitmap metadata and placed affine resolution inspection, including
  rotation, mirrors, skew and worst directional DPI. Thirty-eight focused checks
  cover pixel-grid/crop geometry, two-read consistency, nested effect scope,
  missing metadata, context restoration and strict schemas. X7 evidence is
  retained and the disposable native gate remains deferred. The surface has 85
  tools; 726 automated checks pass and 27 guarded live gates are skipped.
- Seven guarded page/layer tools for structure fingerprints, exact activation,
  naming, explicit-size page append, ordinary local layer creation and native
  visibility/editability/printing flags. Thirty-eight focused checks cover stale
  state, ownership, unit restoration, verified empty-container cleanup and worker
  quarantine. X7 type-library and readable primary help evidence are retained;
  native lifecycle and CDR/PDF review remain deferred. The surface has 84 tools;
  688 automated checks pass and 26 guarded live gates are skipped.
- Source-preserving editable contour derivatives for closed vectors, with native
  inside/outside distance, step and corner controls. Thirty-seven focused checks
  cover controller/leaf geometry, compound/nested ownership, verified cleanup of
  known partial native effects and quarantine of foreign/stray outputs. Installed
  X7 evidence and readable contour help are retained. Exact offsets/winding,
  miter/cutting behavior and native CDR/PDF review remain deferred. The surface
  has 77 registered tools; 650 automated checks pass and 25 live gates are skipped.
- Two gradient tools for native inspection and guarded opaque direct RGB/CMYK
  multicolor fills. Thirty checks cover stop/component/parameter reconciliation,
  editable text/vector preservation, stale fingerprints, incomplete metadata and
  partial-write quarantine. Installed X7 descriptors/enums and readable X7 help
  support the requirement; native interpolation/coordinates and artifact review
  remain deferred. The surface has 76 registered tools; 613 automated checks pass
  and 24 live gates are skipped.
- Source-preserving PowerClip inspection, copied frame/content fitting and
  extraction into editable component roots for revisions/rebuilds. Thirty-four
  focused checks cover mixed content, nested locks, complete source geometry,
  ownership/alias rejection and verified cleanup/quarantine. Installed X7
  descriptors are retained without application access; online pages returned no
  readable API content. The surface has 74 registered tools; 583 checks pass and
  23 live gates remain deferred. Native clipping/extraction, pixel/visual evidence
  and in-place edit mode remain pending.
- Transparency inspection and controlled normal-mode uniform fill/outline/both
  application/removal. Eighteen checks cover exact percentage/scope/merge,
  non-uniform replacement intent, ignored/partial writes, preservation and
  quarantine with continued inspection. Installed X7 applied-to/merge constants
  are catalogued and validated. The surface has 71 registered tools; 549 checks
  pass and 22 live gates remain deferred. Rendered blending/pixel/print behavior
  remains unverified.
- Controlled native RGB/CMYK process fills and existing ordinary-outline colors.
  Native factory/final components, measured vector/text geometry and the other
  appearance channel gate success; non-uniform fill replacement is explicit.
  Eighteen checks cover failures, unsupported targets, source preservation and
  worker quarantine. Installed X7 appearance/clipping signatures are retained
  without application access. The surface has 69 registered tools; 531 checks
  pass and 21 live gates remain deferred. Native color/print verification, ICC/
  spot workflows and outline-width units remain pending.
- Source-preserving node topology revisions: exact line/cubic subdivision,
  explicit nonadjacent-node reconnection and source-to-output node mapping.
  Owned CopyAssign outputs retain basic fill/outline with verified cusp types;
  assignment/copy/cleanup failures and source corruption have recovery coverage.
  Twenty-two focused checks pass, including independent curve-polynomial samples.
  The surface has 68 registered tools; 513 checks pass and 20 live gates are
  deferred. Native CopyAssign coordinates/closure and visual review remain pending.
- Six general vector tools: editable line/cubic paths, complete geometry and
  fingerprint-guarded nodes/handles, source-preserving weld/trim/intersect,
  combine and break-apart. Thirty-three focused checks cover topology, handle
  constraints, identities, source corruption and owned-output cleanup. Installed
  X7 signatures are retained without connecting to the app. Native closure,
  shaping appearance and winding remain deferred. The surface has 67 registered
  tools; 491 automated checks pass and 19 live gates remain skipped.
- Controlled zero-bleed PDF export with explicit font/range/color/version and
  bitmap controls, verified native setting restoration, full page/font structure
  checks and exclusive output publication. Twenty-two focused tests cover native
  failures, composite/Form fonts, races and staging changes. The catalog now has
  61 registered tools and a complete deferred verification inventory; missing
  document-inspection, raster-placement and low-level contour gates were prepared.
- Four reusable template tools: bounded source snapshots, literal UTF-8 CSV,
  deterministic record/copy planning and independent full/partial sheet outputs.
  Final row/formatting/static geometry and native ownership checks cover shared
  copies, source preservation, overflow and verified cleanup. Twenty-four focused
  tests pass; the disposable native gate and visual review remain deferred.
- Retained installed X7 PDF signatures/enums for controlled export research;
  no application connection was used.
- Worker recovery (SAFE-002): immediate operator/outcome metadata tools and
  exact-ID native reconciliation, one admitted COM call, pending-timeout
  cancellation, no automatic replay of running work, bounded pinned history,
  and mutation quarantine after late completion or uncertain partial failure.
  Native edit stages distinguish true preflight refusals from validation
  errors after changes; nested calls preserve that distinction. Restore failures
  now fail edits. Forty-one focused tests and a deferred synthetic native gate
  cover deadline races, cancellation, busy HRESULTs, partial acknowledgement,
  strict probes, and shutdown. The surface now has 47 registered tools.
- Opt-in redacted operation records (SAFE-001) covering all 44 MCP tools,
  with exclusive bounded JSONL files outside the repository, input type counts,
  target/created IDs when available, durations, result codes, rollback flags,
  and correlated caller/worker events. Text, paths, names and raw errors are
  excluded at extraction and disk boundaries. Twenty logging/dispatcher tests
  cover storage failures, concurrency, late completion after caller timeout,
  and envelope/schema compatibility. Creation primitives return object IDs.
  Busy/timeout mutation gating remains the separate SAFE-002 ticket.
- Session object references (ID-001) accepted by eleven common inspection/edit
  tools, with signed bridge/document/page/layer/group/native shape identity,
  full name/type/StaticID checks, complete bounded scope resolution, stale and
  ambiguity refusals, fresh rename/duplicate references, and reference-safe
  nested targeting after reorder. Thirty-one fake-COM/dispatcher safety tests
  and a deferred synthetic save/reopen/restart X7 gate are included. Active-page
  index readback now compares native identity instead of duplicate names.
- Bound-document liveness for ID-001: targeted operations verify bounded open
  document membership and application identity, clear closed/replaced bindings,
  retire stale sessions, and refuse unreadable/oversized collections before
  editing. Twenty-four fake-COM tests and a deferred two-document X7 gate are
  included. Native identity now uses the installed pywin32 IUnknown representation
  and equality rather than an unavailable getter; a generic COM smoke check
  confirms proxy stability without starting Corel. Session object references
  complete the implemented identity portion; native lifecycle gates remain pending.
- Focused read-only object inspection (INS-002): `get_object_bounds`,
  `get_text_properties`, and `get_fill` with strict active-page selectors,
  bounded story/identity/color output, explicit unavailable/indeterminate
  formatting, native color-model preservation, finite bounds, and verified
  fake-COM context restoration. Strict catalog schemas, 34 focused tests,
  dispatcher coverage, and a guarded disposable X7 gate are included; live
  verification remains pending. Shared bold readback now preserves undefined
  tri-state values as null. Live cleanup saves dirty disposable fixtures to a
  unique checkpoint before closing.
- Bounded read-only `find_objects` (INS-001) with literal name/text/type filters,
  explicit page/layer scope, deterministic nested-group paths, duplicate-name
  retention, scan/depth/result completeness reporting, bounded summaries, and
  stable validation/COM errors. Registry schemas, adapter metadata, 20 focused
  fake-COM tests, dispatcher coverage, and a guarded disposable X7 gate are
  included; live search verification remains pending.
- Alhamdulillah vector-recreation V2 reference foundation with bounded image
  preflight, source hashing, exact-A4 perspective rectification, reversible
  pixel-to-Corel transforms, measured inner-field margins, non-overwriting
  reference-only workspaces, a dedicated preparation CLI, and unit coverage.
- Independent Alhamdulillah Phase 2 visual gate for retained field, plaque, and
  trellis geometry, with exact-input fingerprints, fail-closed dimension and
  artifact checks, a dedicated validation CLI, and synthetic pass/fail tests.
- Reproducible Alhamdulillah Phase 3 calligraphy extraction and tracing with a
  plaque-bounded analysis mask, connected-component and counterform retention,
  low-node native CorelDRAW curves, non-overwriting CDR/PDF runs, source-hash
  preservation, full-render silhouette differencing, and an explicit manual
  reading/overlay review gate.
- Implementation-ready roadmap for unified imposition orchestration, source-preserving output, conditional production Q&A, and reference-image-to-editable-vector CDR reconstruction in `docs/IMPOSITION_AND_VECTOR_RECREATION_PLAN.md`.
- Unified vector-imposition orchestration:
  - `prepare_imposition_job` provides one non-mutating plan call followed by explicit `confirm_execution` and exact SHA-256 plan-fingerprint approval.
  - Fingerprints bind source document/page/group identity, normalized contour geometry, production inputs, output policy, and deterministic placements; changed source state invalidates approval.
  - Obvious rectangles bypass cutter questions, while contour jobs ask about 180° rotation only when it improves copies per sheet.
  - Execution creates an explicit layer on a new page, copies rather than transforms the source, keeps repeats independent, verifies readback/collisions, and rolls back by deleting only its new page.
  - The guarded X7 run verified straight-contour flattening, 0°/180° groups, contour placement, collision readback, distinct identities, unchanged source state, and forced output-page-only rollback; manual CDR review remains pending.
  - X7 `Shape.CopyToLayer` failed for the cross-page group despite its type-library signature. The bridge now uses the live-tested `Shape.Copy` / `Layer.Paste` equivalent and discloses that this replaces current system clipboard contents.
  - Both the failed `CopyToLayer` report and passing fallback report are retained under `docs/test-reports/` so capability evidence remains honest.
- Shape-aware packaging imposition:
  - `classify_imposition_job` sends obvious rectangles directly to N-up without asking irrelevant cutter questions; non-rectangular work receives conditional cutter/dieline/rotation Q&A.
  - `inspect_repeat_unit` requires one independently grouped vector repeat and one uniquely named closed dieline, rejects likely combined multi-copy sources, and flattens X7 curves through `SubPath.GetPolyline`.
  - `plan_contour_nesting` performs deterministic polygon validation, bleed/gutter clearance checks, and production-friendly complete-row 0°/180° interlocking rather than visual placement guesses.
  - `prepare_contour_nesting` copies the pristine source to a new page first, keeps every output copy as a separate named top-level group, applies planned rotations/positions, verifies actual contours, and preserves the original source page/group.
- Deterministic best-fit print imposition:
  - `calculate_sheet_layout` can explicitly evaluate upright grids, fully rotated grids, mixed rotated rows, mixed rotated columns, and portrait/landscape sheet candidates.
  - The optimizer returns ranked alternatives, per-copy rotation and coordinates, usable/paper waste, guillotine-cutting complexity, and quantity/sheet/overage calculations without scaling artwork.
  - Per-edge printer margins, gripper/feed allowance, mark clearance, gutters, and bleed-inclusive placement sizes participate in the exact geometry.
  - `plan_print_job` exposes the production math and centers incomplete best-fit strips; `prepare_print_job` now executes and verifies planned 90-degree rotations.
- Print-production foundation for generated raster artwork:
  - Pure `plan_print_job` MCP tool for bounded raster inspection, exact finished/sheet sizes, bleed and safe-area geometry, contain/cover/stretch fit modes, effective-DPI checks, deterministic one-sheet N-up placement, and structured blocking/warning checks.
  - Mutating `prepare_print_job` MCP tool that creates only a new sheet, imports one validated artwork object, creates deterministic named copies, reads back actual bounds, and rolls back placement failures.
  - Cover mode uses a temporary lossless center-cropped TIFF derivative so the imported object preserves aspect ratio without depending on an unverified X7 clipping API.
  - The report always returns `print_ready: false` until marks, output profiles, and controlled export checks are implemented and verified.
- Native Alignment & Grouping Tools (Option C):
  - Mutating `align_objects` MCP tool aligning two or more shapes horizontally (left, center, right) and/or vertically (top, center, bottom) relative to a reference target (`last_selected` or `first_selected`).
  - Mutating `align_to_page` MCP tool snapping shapes to page edges or centering on page axes, individually or collectively as a group (`align_as_group`).
  - Mutating `group_shapes` MCP tool grouping two or more shapes on the active page into a single named composite shape (`Type == 7`).
  - Mutating `ungroup_shapes` MCP tool releasing child shapes from groups with support for top-level or recursive (`ungroup_all`) ungrouping.
  - Live integration test `test_align_and_group_live` executed against CorelDRAW X7 build 17.0.0.491 verifying alignment to reference shapes, centering to page, grouping into composite shape, and ungrouping back to original shapes.
- Structured Design Plan Engine (Option B):
  - Pure `validate_design_plan` MCP tool enforcing design plan schema v1.0, checking element bounds, required fields, styling consistency, and max element limit (200).
  - Pure `preview_design_plan` MCP tool computing composite bounds, an RGB color palette, typography summary, warnings, blocking issues, and execution readiness.
  - Mutating `execute_design_plan` MCP tool transactionally executing multi-element plans in CorelDRAW X7 using `doc.BeginCommandGroup()`, `doc.EndCommandGroup()`, and atomic `doc.Undo()` rollback on element failure, followed by automated post-execution discrepancy verification.
  - Live integration test `test_execute_design_plan_live` executed against CorelDRAW X7 build 17.0.0.491 verifying successful execution and rollback behavior.
- `create_chest_number_batch` MCP mutating tool: generates bounded sequential chest numbers, bounding boxes, and optional header/footer text directly in the bound CorelDRAW document using calculated N-up sheet placement coordinates.
- A pure `calculate_sheet_layout` MCP tool that compares rotated and unrotated rectangular grids, returns deterministic placement coordinates, and caps coordinate output at 2000 placements.
- A pure `plan_chest_number_batch` MCP tool that validates a bounded numeric range and optionally assigns each zero-padded item a sheet placement before any document edit.
- A separately authorized CorelDRAW X7 regression that creates only a new disposable document, exercises the existing editing operations with synthetic content, uses unique CDR/PDF paths, and writes a dated review report.
- Live-test report guidance under `docs/test-reports/`, including explicit manual editability and PDF-review requirements.
- Six read-only inspection tools: `list_open_documents`, `get_document_info`, `list_pages`, `get_page_bounds`, `list_layers`, and `get_object_info`.
- Process-local document session IDs and StaticID-derived object IDs, both conservatively documented as requiring live persistence tests.
- Fake-COM coverage for multi-document identity, bound-target inspection, multi-page dimensions, page-local bounds, page/master-layer state, and combined object readback.

### Changed

- Design-plan runtime validation now uses its Draft 2020-12 schema as the first validation boundary, rejects unknown properties and non-finite/out-of-policy values, and enforces type-specific required fields.
- Canvas overflow is now a blocking preflight issue by default. A plan may explicitly set `bounding_box_within_canvas` to `false` to retain overflow as a non-blocking warning.
- `execute_design_plan` rejects blocking issues before creating a document or opening a CorelDRAW command group.
- `execute_design_plan` preflights every artwork path before document creation, returns per-element actual object readback, and treats command-group close failures as rollback-triggering execution failures.
- Disposable live-test reports now enumerate the CDR/PDF artifacts actually generated by each specialized regression.
- Declared `jsonschema` as a direct runtime dependency instead of relying on a transitive installation.

### Fixed

- Resolved a COM `VT_DISPATCH` marshaling error in `import_artwork` on CorelDRAW X7 by creating and passing an explicit `CreateStructImportOptions` object.
- Sanitized design-plan execution failures so raw COM exception text is not returned to MCP clients.
- Executed the full guarded live regression against CorelDRAW X7 17.0.0.491 on Windows 11 with all 17 operations passing and generating valid CDR and PDF files.

## [0.6.0] - 2026-10-30

### Added

- Evidence-backed initial capability catalog for the 17 registered v0.5 MCP tools.
- Partial current-use CorelDRAW X7 API inventory based on official X7 class references and read-only inspection of the installed X7 type library.
- MCP tool registry with request/response schemas, permissions, confirmation policy, API dependencies, test state, and limitations.
- Capability matrix covering registered tools and the next approved inspection/batch capabilities.
- X7 enum reference for units, reference points, save/export constants, tri-state values, text defaults, and shape type codes used by the bridge.
- Explicit unsupported/research-required register.
- Product/tool/profile/catalog versioning policy.
- Local catalog validator that checks JSON Schemas, server-tool parity, API references, evidence IDs, CSV/registry parity, and duplicate records without starting CorelDRAW.
- Authoritative bridge version, tool-schema version, and capability-profile constants in `corel_operator/version.py`.
- Tool-schema v1 success/error envelope with operation duration, warnings, target identity when known, and operation-specific `data`.
- Stable expected error codes and safe fallback handling for unexpected exceptions.
- `corel_status` runtime metadata for bridge, schema, profile, ProgID, connection mode, Python, MCP SDK, pywin32, and CorelDRAW version/build.
- Seventy-five default tests covering versions, result envelopes, schemas/examples, validation, units, targeting, paths, dispatcher behavior, X7 connection strategy, static diagnostics, appearance/identity readback, actual-state readback, and status metadata; the read-only and mutating live CorelDRAW tests are skipped unless explicitly enabled.
- v0.6 upgrade guide documenting the response migration and complete package-copy requirement.
- Persistent harness-incident log and future-agent safeguards for recurring Azure cross-resource item failures.
- CorelDRAW X7 compatibility adapter with explicit ProgID preference, major-version enforcement, centralized verified constants, and evidence-backed capability support.
- `--static-only` diagnostics for runtime, profile, dependency, and COM-registration checks without connecting to CorelDRAW.

### Changed

- Normalized all registered tools to `implemented_unverified` until historical successes are reproduced in a dated disposable-document test report.
- Wrapped prior v0.5 success dictionaries under `data`; all tools now use one deterministic top-level contract.
- Removed the unconfirmed dynamic `Application.Caption` read from `corel_status`.
- Added controlled `CorelDispatcher.close()` behavior for tests and future shutdown handling.
- Rejected Boolean RGB channel values instead of accepting them as Python integers.
- Changed connection discovery to prefer `CorelDRAW.Application.17`, with the generic ProgID retained only as a validated fallback.
- Added readback of actual page size/unit/reference point after document creation.
- Added actual bounds readback for rectangles, ellipses, and artistic text plus text content/font/size/bold readback.
- Required PDF export to produce a nonempty file and return its byte size.
- Added native fill/color and outline/type/color/width readback without silently converting color models or claiming outline-width units.
- Added StaticID, layer, page, and type identity to object listing, rename, duplication, and artwork import results.

### Security

- Documented the prohibition on arbitrary Python, shell, VBA, macro, and unrestricted COM execution.
- Documented confirmation, overwrite, active-document, local-file, and external-upload safety boundaries.
- Unexpected exception messages are no longer returned directly to MCP clients; only the exception type is included in safe details.

### Compatibility note

- v0.6 intentionally replaces the legacy direct success dictionary and `{error: string}` failure shape. Tool-specific success fields are now inside `data`; clients should first check `ok` and then inspect `data` or `error`.

## [0.5.0] - Historical prototype

### Added

- Explicit active-document binding confirmation.
- Object listing and bridge-generated object names.
- RGB fill and outline controls.
- Move, resize, text replacement, rename, and duplicate operations.
- Local artwork import.
- Single serialized COM worker thread.
- CDR/PDF overwrite protection.

### Known state

- Repository documentation reports successful CorelDRAW X7 connection, an Antigravity `corel_status` call, editable text/rectangle creation, and CDR save.
- Most v0.5 additions did not receive recorded live tests.
- No authoritative package version constant or automated test suite existed.
