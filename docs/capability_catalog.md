# CorelDRAW X7 Automation Capability Catalog

**Catalog revision:** 2026-10-30

**Profile:** `coreldraw-x7-17`

**Target:** CorelDRAW X7 / major version 17 / reported build 17.0.0.491

**Completeness:** Partial, focused on the current v0.6 bridge

**Machine-readable registry:** `catalog/mcp_tool_registry.json`

## Purpose

This catalog is the source of truth for what the CorelDRAW AI Operator currently exposes, what CorelDRAW X7 evidence supports each operation, what has actually been tested, and what remains planned or uncertain.

It deliberately does **not** equate CorelDRAW UI commands with automation APIs. It also does not treat a documented COM member, successful Python import, or compiling method call as proof that a complete model-facing workflow is safe or verified.

## Catalog layers

### Layer A — Raw X7 API inventory

`catalog/coreldraw_x7_api_inventory.json` records the COM registrations and X7 object-model members used by the current bridge. The initial revision is intentionally partial. It includes direct dependencies of the existing tools, their signatures from the installed type library, official X7 class references, and live-test status.

### Layer B — Approved atomic MCP tools

`catalog/mcp_tool_registry.json` records the current model-facing tool surface and the next inspection tools. Each record contains:

- stable tool name and category;
- input and current output schemas;
- permission, risk, and confirmation class;
- supported capability profile;
- required X7 API members;
- implementation and verification status;
- test evidence and known limitations.

### Layer C — High-level workflows

Workflow records orchestrate atomic tools deterministically. The initial registry contains draft records for sheet-layout calculation, chest-number generation, and N-up arrangement. They are not MCP tools yet.

## Evidence hierarchy

Evidence is evaluated in this order:

1. Official CorelDRAW X7 object-model reference under `/sdk/api/draw/17/`.
2. Installed X7 COM type library, inspected without invoking methods.
3. Windows COM registration for ProgIDs and type-library paths.
4. Current bridge source code.
5. Reproducible live integration test against a disposable X7 document.
6. Historical user reports, which are useful but must be reproduced before the new registry marks a tool `verified`.

### Local evidence inspected in this revision

- `CorelDRAW.Application.17` is registered.
- Generic `CorelDRAW.Application` currently resolves through `CurVer` to `CorelDRAW.Application.17`.
- Both ProgIDs map to CLSID `{2FBA0002-B5E2-C3B0-412E-C843C16BAFDB}`.
- The installed 64-bit type library is `CorelDRAW.tlb` with library ID `{FBF4300F-D921-11D1-B806-00A0C90646A9}`.
- Its registered type-library major version is `11` hexadecimal, corresponding to product major version 17 decimal.
- Type-library inspection confirmed the current method signatures and enum constants without opening or modifying a document.

## Status meanings

| Status | Meaning |
|---|---|
| `planned` | Approved direction, but no implementation exists. |
| `research_required` | A schema or implementation decision lacks sufficient X7 evidence. |
| `implemented_unverified` | Code is exposed, but the required reproducible live test is absent or incomplete. |
| `verified` | Documentation/type-library evidence and the required recorded live test both pass. |
| `unsupported` | Deliberately unavailable or shown not to work for the profile. |
| `deprecated` | Retained temporarily for compatibility but scheduled for removal. |

## Current status summary

| Registry layer/status | Count |
|---|---:|
| Registered atomic tools — `implemented_unverified` | 17 |
| Planned atomic/workflow tools — `planned` | 12 |
| Planned tools blocked by research | 1 |
| Tools marked `verified` | 0 |

The zero verified count is intentional. The repository reports historical successes, but it does not yet contain the reproducible dated test report required by the current product contract.

## Existing MCP tools

| Tool | Permission | Priority | Current status | Evidence summary | Primary next check |
|---|---|---:|---|---|---|
| `corel_status` | read-only | P0 | implemented_unverified | Version/build/active-document members confirmed; v0.6 runtime metadata has non-COM tests | Reproduce the complete v0.6 envelope through an MCP client |
| `create_document` | mutating | P0 | implemented_unverified | `CreateDocument`/`SetSize` confirmed; page size/unit/reference readback has fake-COM tests | Reproduce actual readback on a disposable X7 document |
| `use_active_document` | mutating | P0 | implemented_unverified | `ActiveDocument` confirmed | Test only with approved throwaway document; add checkpoint policy |
| `add_text` | mutating | P0 | implemented_unverified | `CreateArtisticText` confirmed; content/format/bounds readback has fake-COM tests | Verify coordinates, charset, substitution, bounds, and editability live |
| `draw_rectangle` | mutating | P0 | implemented_unverified | `CreateRectangle2` confirmed; actual-bounds readback has fake-COM tests | Reproduce exact bounds on X7 |
| `draw_ellipse` | mutating | P1 | implemented_unverified | `CreateEllipse2` confirmed; center conversion/bounds readback has fake-COM tests | Reproduce exact bounds on X7 |
| `list_objects` | read-only | P0 | implemented_unverified | StaticID/layer/page and native appearance readback have fake-COM tests | Test mixed objects, groups, bounds, text, and outline units live |
| `set_fill_color` | mutating | P1 | implemented_unverified | RGB factory/uniform fill confirmed; native readback has fake tests | Reproduce actual RGB and fill type on X7 |
| `set_outline` | mutating | P1 | implemented_unverified | Outline type/color/raw width readback has fake tests | Establish width units with a controlled X7 test |
| `move_object` | mutating | P1 | implemented_unverified | Reference point and `SetPosition` confirmed | Verify drawing origin and resulting absolute bounds |
| `resize_object` | mutating | P1 | implemented_unverified | Shape size properties confirmed | Control anchor and test primitives versus text |
| `set_text_content` | mutating | P1 | implemented_unverified | Text story property chain confirmed | Verify content and formatting preservation |
| `rename_object` | mutating | P1 | implemented_unverified | Name plus StaticID/layer/page identity readback has fake tests | Verify identity persistence and duplicate-name behavior |
| `duplicate_object` | mutating | P1 | implemented_unverified | `Duplicate` plus copy identity readback has fake tests | Verify offset, actual bounds, and identity on X7 |
| `import_artwork` | external I/O | P1 | implemented_unverified | `Layer.Import` plus imported identity has fake tests | Test safe fixtures per format and selection/fallback detection live |
| `save_document` | external I/O | P0 | implemented_unverified | Save options, enums, and `SaveAs` confirmed; historical save reported | Reproduce unique CDR save and inspect resulting file/options |
| `export_pdf` | export | P1 | implemented_unverified | `PublishToPDF` confirmed; nonempty-file verification has fake tests | Parse/verify page size and report inherited settings in a live run |

## Next approved tools and workflows

The registry contains draft records for:

- `list_open_documents`
- `get_document_info`
- `list_pages`
- `get_page_bounds`
- `list_layers`
- `get_object_info`
- `find_objects`
- `get_text_properties`
- `get_fill`
- `get_outline`
- `calculate_sheet_layout`
- `create_chest_number_batch`
- `arrange_n_up_print_sheet`

These entries are catalog records only. They do not become available to an AI client until implemented in the bridge/server, tested, and documented.

## Important findings from this catalog pass

### Version-aware connection is feasible

The X7 adapter now prefers `CorelDRAW.Application.17`, validates that the connected application reports major version 17, and reports the ProgID/mode used. Generic `CorelDRAW.Application` remains a validated fallback because another installed CorelDRAW version could change `CurVer`.

The adapter exposes evidence/status for 18 approved capabilities. Seventeen are available but still `implemented_unverified`; the claimed point semantics for outline width remain unavailable and `research_required`. No capability is reported as live verified yet.

### The unconfirmed `Application.Caption` read was removed

`Application.Caption` was not found in the official X7 Application class list or installed type-library property map. Bridge 0.6.0 no longer reads it. The raw inventory retains the record as historical `research_required` evidence so it is not accidentally reintroduced.

### Tool-schema v1 is a stable envelope

Every current and planned registry output uses the same success/error envelope. Operation-specific v0.5 fields remain under `data`; errors carry a stable code, safe message, and details object. The registry includes validated success and error examples for every tool record.

### Outline-width units are unresolved

The official class summary and installed type library confirm `Outline.Width` as a writable `Double`, but the inspected evidence does not establish the MCP boundary's claimed point conversion. `set_outline` and the outline field in `list_objects` therefore cannot be marked verified yet.

### Existing enum magic numbers are real X7 constants

Read-only type-library inspection confirmed:

- `cdrInch = 1`
- `cdrFoot = 2`
- `cdrBottomLeft = 5`
- `cdrAutoSense = 0`
- `cdrCDR = 1795`
- `cdrCurrentVersion = 0`
- `cdrAllPages = 0`
- `cdrTrue = -1`, `cdrFalse = 0`, `cdrUndefined = -2`

They still need to be centralized in the future X7 adapter instead of remaining as scattered numeric literals.

## Machine-readable files

| File | Purpose |
|---|---|
| `catalog/coreldraw_x7_api_inventory.json` | Current-use raw X7 COM/API evidence |
| `catalog/mcp_tool_registry.json` | Atomic/workflow tools, schemas, risk, and status |
| `catalog/capability_matrix.csv` | Reviewable status and next-test matrix |
| `catalog/enum_reference.json` | Type-library-derived enum values used by the bridge |
| `docs/UNSUPPORTED_AND_RESEARCH_REQUIRED.md` | Explicit uncertainty and unsupported boundaries |
| `docs/TOOL_VERSIONING.md` | Product, schema, profile, catalog, and status rules |

## Updating the catalog

For any capability change:

1. Add or update raw API evidence.
2. Update the MCP registry schema and risk classification.
3. Update the capability matrix.
4. Add tests or a live-test plan.
5. Record the change in `CHANGELOG.md`.
6. Change to `verified` only after a dated passing test report exists.

The catalog is expected to grow incrementally. A partial truthful inventory is preferred over a large guessed inventory.
