# CorelDRAW AI Operator — Prototype v0.6 (CorelDRAW X7)

A local MCP bridge that lets compatible AI clients operate CorelDRAW X7 through Windows COM automation.

## Roadmap and capability status

- `PLAN.md` is the staged implementation plan.
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
- Fifty default tests, one guarded live-status test, and a catalog consistency validator.

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

Requirements pin MCP SDK v1 because the server uses `mcp.server.fastmcp`:

```text
mcp>=1.28,<2
pywin32>=306; platform_system == "Windows"
```

## Safety / limitations

- The bridge intentionally does not expose object deletion or arbitrary macro execution.
- `use_active_document(confirm_existing_document=True)` is required before editing an already-open document.
- `resize_object` can stretch text glyphs; for typography, change font size instead when possible.
- Imported art can need repositioning and sizing; inspect `list_objects` after import.
- Print readiness is not inferred from export success. Check page size, bleed, resolution, fonts, color profiles, and printer requirements.
- The model/client must call tools correctly. An MCP connection does not guarantee good visual design; iterate and inspect the document.
