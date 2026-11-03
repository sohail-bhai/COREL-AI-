# CorelDRAW AI Operator — Prototype v0.6 (CorelDRAW X7)

A local MCP bridge that lets compatible AI clients operate CorelDRAW X7 through Windows COM automation.

## Roadmap and capability status

- `PLAN.md` is the strategic staged roadmap.
- `docs/IMPLEMENTATION_PLAN.md` is the prioritized future implementation plan with concrete
  implementation steps, milestone gates, and the immediate execution queue.
- `docs/CAPABILITY_GAP_RESEARCH.md` compares online workflow research with the
  current bridge and defines the broader autonomous delivery sequence.
- `catalog/workflow_gaps.json` maps all registered tools into a source-backed
  workflow gap backlog; it does not expose additional MCP tools.
- `docs/capability_catalog.md` is the readable capability/status reference.
- `catalog/mcp_tool_registry.json` is the machine-readable model-facing tool registry.
- `catalog/coreldraw_x7_api_inventory.json` contains the current evidence-backed X7 API subset.
- `docs/TESTING.md` explains default and explicitly enabled live tests.

Historical successes listed below are retained as evidence, but the new registry conservatively marks current tools `implemented_unverified` until they pass a reproducible, dated test against a disposable X7 document.

Validate the catalog without starting CorelDRAW:

```powershell
.\.venv\Scripts\python.exe scripts\validate_catalog.py
```

## New in v0.6

- One authoritative bridge version, tool-schema version, and X7 capability-profile ID.
- A stable result envelope for every MCP tool.
- Stable error codes for expected validation, targeting, path, overwrite, COM, worker, and timeout failures.
- Runtime metadata from `corel_status`, including Python, MCP SDK, pywin32, ProgID, and CorelDRAW version/build fields.
- 281 default tests (nine guarded live gates skipped), disposable-document regressions, and a catalog consistency validator. Live verification is deferred to a consolidated campaign across implemented features.
- An explicit CorelDRAW X7 adapter that prefers `CorelDRAW.Application.17`, rejects unexpected major versions, and centralizes verified constants/capability status.
- Native appearance readback and richer object identity using X7 `StaticID`, layer, page, and type metadata where available.
- Bound-document liveness checks that clear closed/replaced targets and prevent
  editing another active document; see [`docs/DOCUMENT_TARGETING.md`](docs/DOCUMENT_TARGETING.md).
- Six implemented-unverified read-only inspection tools for open documents, target-document details, pages, page bounds, layers, and single objects.
- Bounded `find_objects` inspection across pages, layers, and nested groups, with
  literal filters, duplicate-name retention, and explicit completeness limits;
  see [`docs/OBJECT_SEARCH.md`](docs/OBJECT_SEARCH.md).
- Focused `get_object_bounds`, `get_text_properties`, and `get_fill` inspection
  with strict selectors, bounded output, native color-model preservation, and
  explicit unavailable/indeterminate properties; see
  [`docs/OBJECT_INSPECTION.md`](docs/OBJECT_INSPECTION.md).
- `calculate_sheet_layout`, a read-only N-up optimizer for upright, rotated, mixed-row, mixed-column, and sheet-orientation candidates, including per-edge/gripper allowances, waste, alternatives, and production-quantity math.
- `plan_chest_number_batch`, a read-only preflight that validates ranges, preserves zero-padding, and optionally returns a complete sheet-fit and placement plan.
- `plan_print_job`, a no-Corel preflight for one raster artwork: exact finished/sheet sizes, bleed and safe boxes, contain/cover/stretch geometry, effective DPI, best-fit imposition, sheet counts, waste, and per-copy rotation coordinates.
- `prepare_print_job`, a new-document-only workflow that imports the validated artwork, applies planned fit/crop and per-copy rotation, creates named copies, and reads back their actual bounds. It deliberately does not claim print-ready output.
- `classify_imposition_job`, which routes obvious rectangles directly to N-up and asks cutter/rotation questions only for non-rectangular contour work.
- `inspect_repeat_unit`, which requires one independent vector repeat group and one named closed dieline, then uses CorelDRAW X7 `SubPath.GetPolyline` to produce deterministic contour geometry.
- `plan_contour_nesting`, a pure collision-checked 0°/180° paired-row optimizer for interlocking dielines.
- `prepare_contour_nesting`, which copies the pristine repeat to a new output page, preserves one top-level group per copy, verifies contour clearance, and leaves the source group/page unchanged. X7 cross-page transfer uses the live-tested `Shape.Copy`/`Layer.Paste` fallback and reports that it replaces clipboard contents.
- `prepare_imposition_job`, the preferred model-facing classify/plan/approve/execute workflow. It asks rotation questions only when capacity improves, fingerprints the complete plan and source identity, requires the matching fingerprint for mutation, and rolls back by deleting only its new output page. The guarded X7 execution/rollback run passes; manual CDR review remains pending.

Imposition routing is deliberate: ordinary rectangular artwork uses rectangular N-up without cutter questions. Packaging/dieline work uses explicit repeat and contour inspection; the orchestrator asks unresolved cutting-method questions and asks about 180° rotation only when it improves capacity. An already combined multi-copy image/group is rejected because copies cannot be transformed and verified independently.

The approved roadmap—including the implemented-unverified orchestration/source-preservation slice and the following reference-image-to-editable-vector CDR work—is documented in [`docs/IMPOSITION_AND_VECTOR_RECREATION_PLAN.md`](docs/IMPOSITION_AND_VECTOR_RECREATION_PLAN.md).

Run static diagnostics without connecting to CorelDRAW:

```powershell
.\.venv\Scripts\python.exe -m corel_operator.diagnostics --static-only
```

Tool results now use this shape:

```json
{
  "ok": true,
  "tool": "list_objects",
  "bridge_version": "0.6.0",
  "tool_schema_version": 1,
  "profile_id": "coreldraw-x7-17",
  "target_document": {"name": "Graphic1"},
  "data": {},
  "warnings": [],
  "error": null,
  "duration_ms": 4.2
}
```

The operation-specific fields returned by v0.5 are preserved inside `data`.

## Confirmed in the user's environment

- CorelDRAW X7 version 17.0.0.491 was detected through COM.
- A new document, rectangle and editable text were created through Antigravity prompts.
- A CDR save operation succeeded after using explicit X7 save options.
- Antigravity successfully called the `corel_status` MCP tool.

Those checks confirm the basic pipeline works. The new v0.5 tools below need a live test in the user's CorelDRAW X7 installation before being considered validated.

## New in v0.5

- Safe target-document binding: mutations target a document created by the bridge; editing an already-open document requires explicit confirmation.
- Object listing and inspection.
- Stable object names on newly created shapes.
- RGB fill and outline controls.
- Absolute object positioning and resizing.
- Text content editing and object renaming.
- Object duplication.
- Local raster/vector artwork import.
- Existing overwrite protection for CDR/PDF saves.
- One dedicated COM worker thread for serialized automation calls.

## Upgrade existing installation

Your existing project is already connected to Antigravity. Do not replace its MCP configuration. Follow `docs/UPGRADE_TO_V0.6.md`; v0.6 adds package modules and a new response contract, so copying only `corel_bridge.py` and `server.py` is no longer sufficient. `docs/UPGRADE_FROM_V0.4.md` is retained as historical v0.5 guidance.

Requirements pin MCP SDK v1 because the server uses `mcp.server.fastmcp`; JSON Schema is a
direct runtime dependency for design-plan validation:

```text
mcp>=1.28,<2
jsonschema>=4.21,<5
pywin32>=306; platform_system == "Windows"
```

## Safety / limitations

- The bridge intentionally does not expose object deletion or arbitrary macro execution.
- `use_active_document(confirm_existing_document=True)` is required before editing an already-open document.
- `resize_object` can stretch text glyphs; for typography, change font size instead when possible.
- Imported art can need repositioning and sizing; inspect `list_objects` after import.
- Print readiness is not inferred from export success. Check page size, bleed, resolution, fonts, color profiles, and printer requirements.
- The model/client must call tools correctly. An MCP connection does not guarantee good visual design; iterate and inspect the document.
