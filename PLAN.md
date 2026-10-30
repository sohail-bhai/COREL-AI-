# CorelDRAW AI Operator — Implementation Plan

**Plan date:** 2026-10-30  
**Target application:** CorelDRAW Graphics Suite X7, version 17.0.0.491  
**Primary runtime:** Windows 11, Python 3.11, MCP SDK v1  
**Product stage:** Working proof of concept entering stabilization  
**Product contract:** `ANTIGRAVITY_MASTER_SPEC.md`

## 1. Objective

Build a reliable, local, natural-language operator for real CorelDRAW documents. The AI client should be able to plan a design, call safe typed MCP tools, inspect the actual document state, correct problems, produce deterministic batches, and save editable CDR files or validated exports.

The implementation must remain evidence-based. A CorelDRAW operation is not considered supported merely because a similar UI command exists or because code compiles. Every capability must be tied to CorelDRAW X7 documentation or type-library evidence and, where practical, a passing test on a disposable X7 document.

## 2. Current baseline

| Area | Current state |
|---|---|
| CorelDRAW connection | COM connection to X7 17.0.0.491 is reported as successful |
| MCP connection | Antigravity reportedly called `corel_status` successfully |
| COM threading | One dedicated serialized COM worker thread is implemented |
| Document safety | New bridge-created documents are the default target; existing documents require explicit binding |
| Existing MCP surface | 17 tools are registered |
| Historically demonstrated operations | Status, document creation, rectangle, editable text, and CDR save |
| Remaining v0.5 operations | Implemented but mostly not verified live |
| Automated tests | None; `tests/` is currently empty |
| Capability inventory | A small seed CSV exists, but the required evidence-backed catalog does not |
| Advanced workflows | Design plans, batches, previews, correction, and preflight are not implemented |

This baseline is provisional until it is reproduced and recorded. Conflicting or stale documentation must be corrected as part of stabilization.

## 3. Non-negotiable engineering rules

1. Never modify an existing user document without explicit authorization and an unambiguous target.
2. Run live integration tests only against a new disposable document or an approved throwaway copy.
3. Never silently overwrite CDR, PDF, image, or batch output files.
4. Keep all COM objects and calls on one initialized STA worker thread.
5. Do not expose arbitrary Python, shell, VBA, macros, or unrestricted COM dispatch to the model.
6. Verify X7 signatures and enum values; do not copy modern CorelDRAW APIs without independent X7 evidence.
7. Return structured results and stable error codes, then read back actual state after mutations.
8. Keep raw API inventory separate from approved MCP tools and high-level workflows.
9. Mark tools `verified` only after a recorded passing live test on the target X7 installation.
10. Work in small reviewable releases and keep `main` in a usable state.

## 4. Delivery strategy

Development will proceed through vertical, testable milestones rather than a large tool dump:

1. Stabilize and truthfully catalog the existing prototype.
2. Add reliable inspection and object identity.
3. Complete the core editing and layout vocabulary.
4. Add preview and controlled design-plan execution.
5. Implement deterministic batch workflows.
6. Add production preflight and visual correction.
7. Add reference recreation, external imagery, and additional compatibility only after the core is reliable.

## 5. Phase 0 — Repository and safety baseline

### Tasks

- [x] Confirm the actual project root.
- [x] Inspect source, documentation, configuration, dependencies, and current tools.
- [x] Create a Git repository using `main`.
- [x] Connect `origin` to `https://github.com/sohail-bhai/COREL-AI-.git`.
- [x] Exclude `.venv`, caches, generated output, logs, backups, and CDR working files.
- [x] Add this implementation plan.
- [x] Create and push the baseline commits.

### Exit condition

The current proof of concept and this plan are safely stored on GitHub without committing the local virtual environment or user artwork.

## 6. Phase 1 — Stabilize v0.5 and establish evidence

This is the **next implementation milestone**. No broad feature expansion should happen before this phase passes.

### 1.1 Create the truthful capability catalog — completed 2026-10-30

Create the required deliverables:

- [x] `docs/capability_catalog.md`
- [x] `catalog/coreldraw_x7_api_inventory.json`
- [x] `catalog/mcp_tool_registry.json`
- [x] `catalog/capability_matrix.csv`
- [x] `catalog/enum_reference.json`
- [x] `docs/UNSUPPORTED_AND_RESEARCH_REQUIRED.md`
- [x] `docs/TOOL_VERSIONING.md`
- [x] `CHANGELOG.md`
- [x] `scripts/validate_catalog.py`

Catalog rules:

- Begin with the 17 existing tools and the highest-priority planned capabilities.
- Every record must include source, X7 profile, permission/risk class, schema, status, test evidence, and limitations.
- Use statuses consistently: `planned`, `research_required`, `implemented_unverified`, `verified`, `unsupported`, or `deprecated`.
- A missing source or untested signature must remain `research_required` or `implemented_unverified`.
- Do not attempt to expose the entire raw inventory as MCP tools.

### 1.2 Add project and protocol versioning — completed 2026-10-30

- [x] Add one authoritative package version, initially the next development release after prototype v0.5.
- [x] Add a separate `tool_schema_version`.
- [x] Add the X7 capability profile ID `coreldraw-x7-17`.
- [x] Report bridge, Python, MCP, pywin32, CorelDRAW, profile, and ProgID information from `corel_status`.
- [x] Document semantic-version and schema-version rules.

### 1.3 Establish automated tests — foundation completed 2026-10-30

Initial Batch 2 contract tests completed:

- [x] `tests/test_version.py`
- [x] `tests/test_results.py`
- [x] `tests/test_bridge_errors.py`
- [x] `tests/test_status_metadata.py`
- [x] `tests/test_server_contract.py`

Required foundation:

- [x] `tests/test_tool_schemas.py`
- [x] `tests/test_validation.py`
- [x] `tests/test_corel_unit_conversion.py`
- [x] `tests/test_document_targeting.py`
- [x] `tests/test_path_safety.py`
- [x] `tests/test_dispatcher.py`
- [x] `tests/integration/` for explicitly enabled CorelDRAW tests

Testing requirements:

- Unit tests must not launch or mutate CorelDRAW.
- Mock/fake COM objects should cover dispatch, target binding, validation, and readback behavior.
- Live tests must be disabled by default and require an explicit environment flag.
- Each live run must use a newly created disposable document and unique output directory.
- Store a dated, non-confidential test report under `docs/test-reports/`.

### 1.4 Introduce the X7 compatibility boundary

- Prefer the explicit `CorelDRAW.Application.17` ProgID for X7 and report the ProgID actually used.
- Detect and reject or clearly report an unexpected running major version.
- Centralize verified X7 enum values and method differences.
- Add a capability check such as `supports(capability_name)` with evidence/status.
- Keep version checks out of individual tools wherever possible.

### 1.5 Standardize results, errors, and operation records — result/error contract completed; persistent operation logging remains

The v0.6 result contract now contains:

- [x] `ok`
- [x] `tool`
- [x] `bridge_version`
- [x] `tool_schema_version`
- [x] `profile_id`
- [x] `target_document`
- [x] `data`
- [x] `warnings`
- [x] `error.code`
- [x] `error.message`
- [x] `error.details`
- [x] `duration_ms`

Stable error categories now include:

- [x] `NO_TARGET_DOCUMENT`
- [x] `CONFIRMATION_REQUIRED`
- [x] `INVALID_ARGUMENT`
- [x] `OBJECT_NOT_FOUND`
- [x] `AMBIGUOUS_SELECTOR`
- [x] `UNSUPPORTED_IN_PROFILE`
- [x] `UNSAFE_PATH`
- [x] `OUTPUT_EXISTS`
- [x] `COREL_COM_ERROR`
- [x] `OPERATION_TIMEOUT`
- [x] `WORKER_UNAVAILABLE`
- [x] `INTERNAL_ERROR`

- [ ] Add persistent operation logs that avoid document contents, credentials, and confidential artwork.

### 1.6 Harden and verify the existing 17 tools

For every existing tool:

1. Confirm the exact X7 API member and argument semantics.
2. Add schema and validation tests.
3. Run it against a disposable document when mutation is involved.
4. Read back actual properties rather than returning only requested values.
5. Record evidence and limitations in the registry.
6. Update status only after the applicable tests pass.

Specific issues to verify or improve:

- Coordinate origin and anchor semantics for all creation and movement operations.
- Inches/points conversion, especially outline width.
- Page size readback after document creation.
- Stable target-document identity if focus changes or a document closes.
- Stable object identity beyond mutable shape indexes.
- Fill, outline, position, size, and text readback.
- Import selection and multi-object identification.
- Path normalization, device/UNC path policy, allowed extensions, and file-size limits.
- Save options and the meaning of hard-coded X7 enum values.
- PDF existence, size, page dimensions, and inherited export-setting warnings.
- Timeout behavior when a COM call remains blocked after the MCP request times out.

### Phase 1 acceptance gate

- The server starts cleanly under Python 3.11 and MCP SDK v1.
- Every registered tool has a valid input schema, output contract, catalog record, and explicit status.
- Unit tests pass without opening CorelDRAW.
- A guarded live regression creates only a disposable document.
- Historically working operations are reproduced and recorded.
- No existing client document is changed.
- CDR and PDF tests use unique paths and verify that outputs exist.
- Documentation reflects actual results with no contradictory status claims.

## 7. Phase 2 — Inspection and stable document/object identity

Implement the read layer needed for reliable planning and correction:

- `list_open_documents`
- `get_active_document_info`
- `get_document_info`
- `list_pages`
- `get_page_bounds`
- `list_layers`
- `get_layer_info`
- `get_object_info`
- `find_objects`
- `get_object_bounds`
- `get_text_properties`
- `get_fill`
- `get_outline`

Identity requirements:

- Maintain explicit document session identity.
- Prefer stable bridge-generated object IDs/names over shape indexes.
- Detect duplicate names and stale references.
- Define behavior after MCP process restart or document closure.
- Inspect pages, layers, groups, and nested objects intentionally rather than assuming only the active page matters.

### Exit condition

The agent can unambiguously identify the intended document and object, inspect its actual properties, and explain why a selector is safe before mutation.

## 8. Phase 3 — Core editing, typography, and layout

Add only capabilities confirmed by X7 evidence and tests.

### Priority capabilities

- Page size and orientation
- Paragraph text
- Font family, size, style, alignment, spacing, and text color
- RGB and verified CMYK fills/outlines
- No-fill and no-outline operations
- Rotation and proportional scaling
- Align and distribute
- Z-order operations
- Group and ungroup
- Duplicate in a deterministic grid
- Layers and moving objects between layers
- Safe object deletion with confirmation and checkpoint policy

### Exit condition

A prompt can create and revise a professional simple layout while preserving editability, dimensions, object identity, and rollback safety.

## 9. Phase 4 — Preview and controlled design plans

### Deliverables

- A versioned design-plan JSON schema.
- `validate_design_plan` with no side effects.
- `preview_design_plan` describing expected operations and risks.
- `execute_design_plan` limited to an allowlist of registered tools.
- Page and selected-object preview export.
- Post-operation inspection and discrepancy reporting.

The executor must reject duplicate IDs, invalid bounds, unsupported capabilities, unsafe paths, unconfirmed destructive actions, and plans that target an ambiguous document.

### Exit condition

The AI can plan, validate, execute, inspect, and revise a small design without bypassing individual tool safeguards.

## 10. Phase 5 — Deterministic batch production

Implement workflows in this order:

1. `create_chest_number_batch`
2. `calculate_sheet_layout`
3. `arrange_n_up_print_sheet`
4. Sequence validation for gaps and duplicates
5. CSV-driven ID cards
6. Labels, tickets, certificates, cards, and tags
7. Individual and combined batch export

Rules:

- Python—not the language model—generates sequences and performs geometry loops.
- Preserve leading zeros and validate the full data set before document mutation.
- Calculate fit, margins, gutters, orientation, and overflow before placement.
- Validate output filenames before starting a batch.
- Produce a machine-readable completion report.

### Exit condition

A 001–200 chest-number job can be generated with no missing or duplicate values, arranged predictably, and verified before export.

## 11. Phase 6 — Production preflight

Add checks for:

- Page dimensions and orientation
- Objects outside page bounds
- Bleed and safe margins
- Unexpected overlaps
- Font availability and editable/converted text state
- Bitmap effective resolution
- Missing or linked assets
- RGB/CMYK/spot-color intent
- Duplicate IDs and incomplete data
- Export existence and page dimensions

The report must distinguish `passed`, `failed`, `warning`, and `not_checked`. The system must never label an output print-ready when required checks were not performed.

## 12. Phase 7 — Reference recreation and generated artwork

- Analyze a reference into editable text, primitive vector elements, and complex artwork regions.
- Rebuild simple elements natively in CorelDRAW.
- Import approved raster/SVG artwork for complex areas.
- Export previews and compare layout, typography, color, and bounds.
- Apply targeted revisions rather than blindly rebuilding everything.
- Add image-generation providers behind a separate adapter.
- Require explicit approval before uploading private artwork or prompts to an external service.

Pixel-perfect recreation of every flattened reference remains a non-goal; discrepancies must be reported truthfully.

## 13. Phase 8 — Client and version expansion

- Verify the same bridge from Antigravity and OpenCode.
- Document client-specific configuration without coupling bridge logic to a vendor.
- Add other CorelDRAW versions only through tested compatibility profiles/adapters.
- Add a ChatGPT route only through an officially supported MCP or model-API integration available to the user.

## 14. Immediate execution queue

Work should begin with these small batches:

| Order | Batch | Status | Result |
|---:|---|---|---|
| 1 | Catalog foundation | Complete | Required catalog files containing truthful records for current tools |
| 2 | Version and result contract | Complete | Bridge/schema/profile versions plus stable structured errors |
| 3 | Unit-test foundation | Complete | Schema, validation, units, targeting, paths, and dispatcher tests |
| 4 | X7 adapter and diagnostics | Next | Version-specific connection, runtime details, centralized verified constants |
| 5 | Existing-tool hardening | Queued | Actual-state readback and fixes identified by unit tests |
| 6 | Guarded live regression | Queued | Recorded disposable-document test of the existing tool set |
| 7 | Inspection vertical slice | Queued | Document, page, layer, and single-object inspection tools |
| 8 | First workflow vertical slice | Queued | Chest-number sequence plus sheet-layout calculation |

Each batch should end with tests, documentation updates, a catalog status update, and a focused commit.

## 15. Test and release policy

### Test layers

1. **Static/unit:** schemas, validation, conversions, path rules, registry consistency.
2. **Mock COM:** dispatch, targeting, readback, failures, and timeout behavior.
3. **Live integration:** explicit opt-in against CorelDRAW X7 and disposable documents.
4. **Visual/manual:** inspect CDR editability and rendered preview where automation cannot prove appearance.
5. **Client regression:** verify tool discovery and calls from Antigravity and OpenCode.

### Release rules

- Use semantic versions while the project remains experimental.
- Use feature branches or focused commits for each execution batch.
- Update `CHANGELOG.md`, catalog statuses, and test reports with every release.
- Never merge a claimed `verified` status without linked evidence.
- Keep output artifacts and confidential documents out of Git.

## 16. Deferred decisions

These choices are intentionally deferred until the foundation is stable:

- Image-generation provider and credential model
- Vision model/provider for reference comparison
- XLSX library and spreadsheet mapping UI
- UI automation fallbacks for capabilities absent from the X7 object model
- Support policy for newer CorelDRAW releases
- Packaging as an installer or background Windows service

## 17. Definition of product success

The product reaches its intended outcome when a user can safely say:

> Create or edit this CorelDRAW design, keep important elements editable, use exact physical dimensions, inspect what you changed, correct visible problems, produce all required personalized variations, and save/export without damaging my existing work.

The operator must then complete that workflow with deterministic tool calls, evidence-backed X7 capabilities, explicit safety decisions, actual-state verification, and an honest report of anything unsupported or unchecked.

## 18. Next action

Start **Immediate Execution Queue — Batch 4: X7 adapter and diagnostics**. Prefer and verify the explicit X7 ProgID, reject unexpected major versions, centralize verified constants, and expose capability support without changing the default no-live-test policy.
