# CorelDRAW AI Operator — Product Brief and Engineering Specification
**Audience:** Antigravity coding agent  
**Project status:** Working proof of concept; expand the existing project, do not restart it  
**Document revision:** 1.0  
**Date:** 2026-10-29

---

## 0. Executive instruction to the coding agent

You are working on an existing Windows/Python/MCP project called **CorelDRAW AI Operator**. Your task is to turn it into a reliable natural-language design operator for **CorelDRAW Graphics Suite X7, version 17.0.0.491**, and later support other compatible CorelDRAW releases through an explicit compatibility layer.

The user wants to type ordinary instructions such as:
- “Create a professional A4 letterhead for this company.”
- “Recreate this reference as closely as possible, keeping text editable and using generated/imported artwork for complex parts.”
- “Create chest numbers 001–200, each 8 × 6 inches, with consistent typography.”
- “Generate ID cards from this spreadsheet and arrange them efficiently on A3 sheets.”
- “Move the heading, change the fill color, resize the logo, replace the phone number, and export a new PDF.”

The agent must translate intent into a plan, execute operations through the CorelDRAW automation API, inspect the results, correct errors where possible, and clearly report what was or was not completed.

**Do not claim every CorelDRAW UI feature can be automated merely because a similarly named UI button exists.** Build an evidence-backed capability inventory from the CorelDRAW X7 object model, local macro/API documentation and live tests. Implement only calls that have verified method signatures, argument semantics, expected behavior, and tests. Mark uncertain capabilities as `research_required` or `unsupported`, never silently fake them.

## 1. Confirmed environment and working proof

### User environment
- OS: Windows 11 (a diagnostic reported platform string `Windows-10-10.0.26200-SP0`; the build number is consistent with a newer Windows 11 build despite the platform string).
- Python: 3.11.9, 64-bit.
- CorelDRAW: X7, version/build `17.0.0.491`, released in 2014.
- CorelDRAW COM connection: confirmed.
- MCP connection from Antigravity: confirmed.
- First natural-language design: confirmed; Antigravity created a new page, rectangular outline, and two editable artistic-text objects.
- CDR saving: confirmed after fixing the SaveAs call to pass CorelDRAW X7 save options.
- MCP SDK: use the v1 FastMCP API. Current `requirements.txt` should pin `mcp>=1.28,<2` because the current server imports `mcp.server.fastmcp.FastMCP`. Do not upgrade to MCP SDK v2 without consciously migrating imports and APIs.
- pywin32: required on Windows; current requirements use `pywin32>=306`.

### Current project folder reported by the user
`G:\sohail\COREL AI\CorelDRAW_AI_Operator_Prototype\CorelDRAW_AI_Operator_Prototype`

Existing configured MCP server name:
`coreldraw-ai-operator`

The current prototype archive reported in the chat is `CorelDRAW_AI_Operator_Prototype_v0.5_X7.zip`. Inspect the actual files in the user's existing project before modifying anything. Do not assume the archive is already installed; the active Antigravity server was previously configured against the user's project folder and has successfully executed `corel_status`.

### Existing proof-of-concept tool set (from v0.5 package)
- `corel_status`
- `create_document`
- `use_active_document`
- `add_text`
- `draw_rectangle`
- `draw_ellipse`
- `list_objects`
- `set_fill_color`
- `set_outline`
- `move_object`
- `resize_object`
- `set_text_content`
- `rename_object`
- `duplicate_object`
- `import_artwork`
- `save_document`
- `export_pdf`

Treat the above as the currently intended API surface; re-open the installed server code to confirm exact implementations before relying on it. Some newer functions were packaged but not all received live tests.

## 2. Product vision and scope

### Core product
An AI-operated bridge into the real CorelDRAW document, not an image-only generator and not a macro that only does one fixed task.

The system combines:
1. **Intent interpretation:** AI understands the user's natural-language goal and constraints.
2. **Planning:** creates a structured sequence of operations and identifies missing information.
3. **Execution:** calls small, typed MCP tools that perform defined CorelDRAW actions.
4. **Inspection:** queries the document and object properties after changes.
5. **Visual feedback:** exports a preview when supported and analyzes the rendered result.
6. **Correction:** makes targeted changes instead of rebuilding everything.
7. **Batch workflows:** creates variations from data or numbering rules.
8. **Production checks:** validates physical dimensions, bleed, content bounds, font assumptions, image resolution and export settings.
9. **Artwork integration:** imports user-provided images, SVGs and other supported artwork; later optionally calls a provider adapter for AI image generation.
10. **Multi-client access:** Antigravity and OpenCode should call the same local MCP bridge. A supported ChatGPT route may be added later; do not promise direct custom-MCP write access inside every ChatGPT plan.

### Non-goals for the first milestone
- Do not build a replacement for CorelDRAW.
- Do not create a separate vector renderer if CorelDRAW's object model can do the job.
- Do not send arbitrary generated Python, shell commands, or VBA macros to execution.
- Do not guarantee pixel-perfect replication of every flattened image.
- Do not call a PDF “print-ready” merely because export succeeded.
- Do not expose all raw API methods directly as AI tools with no schema or safeguards.
- Do not automatically modify whatever document happens to be active.

### User outcomes
The user should be able to create new designs, edit existing designs with explicit authorization, batch-produce personalized designs, import/generated images, and save/export editable files using language rather than manual repetitive actions.

## 3. Architecture

Recommended architecture:

`Antigravity / OpenCode / other supported clients`
→ `MCP stdio server`
→ `Tool registry and validation layer`
→ `CorelDRAW service/dispatcher`
→ `single COM STA worker thread`
→ `CorelDRAW X7 COM object model`
→ `CDR / PDF / raster previews / imported artwork`

### Requirements
- The COM automation objects must be owned and used on one dedicated COM-initialized STA thread. Do not pass COM proxy objects across arbitrary MCP worker threads.
- MCP stdio is a protocol channel. Never print logs/debug messages to stdout; use stderr or structured logging to a file.
- One shared bridge should support clients launching separate server processes. Each client process may own its own bridge instance; ensure target-document/session state is explicit and never assume an in-memory target object is shared between two independently launched MCP processes.
- Discover or attach to CorelDRAW intentionally. Prefer the version-aware programmatic identifier `CorelDRAW.Application.17` when explicitly targeting X7; test whether the generic `CorelDRAW.Application` attaches to the expected installed application. If multiple versions are installed, report the detected version and ask/require explicit selection instead of guessing.
- Keep the CorelDRAW bridge independent from a given AI vendor. Provider-specific image generation and model API calls belong in separate adapters.
- Return structured, deterministic outputs and errors from tools.

## 4. Versions and exact settings

Keep these version concepts separate. They are not interchangeable.

### A. CorelDRAW application version
- Installed product: CorelDRAW X7.
- Detected build: `17.0.0.491`.
- The CorelDRAW developer reference for X7 is the API under `/sdk/api/draw/17/`.
- Corel's external-process example uses `CorelDRAW.Application.17` for X7 and explains that the COM type library version may use a hexadecimal major version. See source links at end.

Runtime discovery should record at minimum:
- `application_version_string`
- `application_version_major` (17 for X7)
- `application_build` if discoverable
- `prog_id_used`
- `python_version`
- `python_bitness`
- `mcp_sdk_version`
- `pywin32_version`
- supported capability profile ID, e.g. `coreldraw-x7-17`
- connection result and timestamp

Do not infer the exact build solely from `ProgID`; query the live application where possible. Do not treat CDR save-format version as the running CorelDRAW application version.

### B. Python runtime
- Target current user environment: Python 3.11.9, 64-bit.
- Avoid upgrading Python without need.
- Keep the project in a virtual environment at `.venv`.
- Dependencies:
  - `mcp>=1.28,<2`
  - `pywin32>=306; platform_system == "Windows"`
- Pin upper/lower boundaries intentionally. Add a lock file or pinned tested set later.
- The actual COM connection and draw/save behavior must be smoke-tested under the installed interpreter.

### C. Internal software version
Use Semantic Versioning for the bridge package:
- `0.x.y` while the tool schemas and behavior are experimental.
- increment patch for fixes without intentional interface changes.
- increment minor for backward-compatible tool additions/optional arguments.
- increment major for incompatible tool/schema changes.
Store it in one place, e.g. `corel_operator/version.py` and `pyproject.toml`, and expose it from `corel_status`.

### D. MCP protocol/tool schema version
Expose a separate `tool_schema_version`, initially `1`. Increment only when request/response semantics change incompatibly. Tool names should stay stable once a public release has been used by client configs/prompts.

### E. API capability profile
Create a capability profile such as:
```json
{
  "profile_id": "coreldraw-x7-17",
  "product_major": 17,
  "verified_builds": ["17.0.0.491"],
  "api_reference_root": "https://community.coreldraw.com/sdk/api/draw/17/",
  "status": "partial",
  "last_verified_utc": null
}
```
This is an example schema, not permission to claim every capability is verified. Record each capability's own evidence/status.

### F. Document units and numeric parameters
Use stable, user-friendly units at the MCP boundary:
- x/y/width/height: inches by default for print design.
- font size: points.
- outline width: points.
- RGB: integer values 0–255.
- hex colors: accept `#RRGGBB`; convert to/from RGB in validation layer.
- angles: degrees.
- percentages: explicit `0–100` or scale factor `0–1`; never mix them.
- DPI: pixels per inch.
- physical size and units must be explicit in outputs.
- for CMYK/spot colors, use separate arguments and report actual supported color mode. Do not silently convert user-specified print colors to RGB.
- convert to CorelDRAW's document units in a context manager and restore the previous unit after each operation.
- CorelDRAW X7's `cdrUnit` enum value for inches is `1`; do not use `2` for inches (2 is feet in the known enum). Still verify via the installed type library/docs.
- coordinates and reference points must be defined consistently. Report whether x/y means top-left, bottom-left, center, or another explicit anchor.

## 5. Standards for every new MCP tool

Every new MCP tool must have all of the following before it is considered complete.

### Tool definition metadata
- Stable `snake_case` tool name.
- One-sentence description describing exactly what it does.
- Category.
- Input schema with types, units, ranges, required/optional fields, enums and defaults.
- Output schema and one or more realistic examples.
- Required capability/API call(s).
- Supported CorelDRAW versions/profile IDs.
- Permission class: `read_only`, `mutating`, `destructive`, `export`, or `external_io`.
- Risk and confirmation requirement.
- Error cases and stable error codes.
- Unit tests for validation and dispatch.
- Live integration test against CorelDRAW X7 when the operation can be safely tested.
- API documentation URL or local reference file/page that supports the implementation.
- Known limitations.
- Status: `planned`, `research_required`, `implemented_unverified`, `verified`, `unsupported`, or `deprecated`.
- Changelog/schema version.

### Suggested tool-registry record
```json
{
  "name": "set_fill_color",
  "category": "appearance",
  "description": "Set a solid fill on a named shape in the target document.",
  "input_schema": {
    "object_name": "string",
    "rgb": {"type": "array", "items": "integer 0..255", "length": 3}
  },
  "output_schema": {
    "ok": "boolean",
    "object_name": "string",
    "actual_rgb": "array[integer,integer,integer]"
  },
  "permission": "mutating",
  "confirmation": "not_required_for_bridge_created_target",
  "coreldraw_profiles": ["coreldraw-x7-17"],
  "api_calls": ["Shape.Fill", "Fill.ApplyUniformFill", "Application.CreateRGBColor"],
  "status": "implemented_unverified",
  "docs": ["https://community.coreldraw.com/sdk/api/draw/17/c/shape",
           "https://community.coreldraw.com/sdk/api/draw/17/p/fill.uniformcolor"],
  "tests": ["unit:rgb_validation", "integration:x7_fill_color"]
}
```
Do not copy this record's claimed API call list without validating against the code/docs; it illustrates the metadata format.

### New-tool implementation procedure
1. Search the official CorelDRAW X7 API docs and local macro editor reference for the required capability.
2. Identify the object/class hierarchy and exact method/property signatures, including optional arguments and enumerations.
3. Record which release supports the method. Do not use API signatures copied from a newer CorelDRAW release unless the X7 reference independently confirms them.
4. Write a small isolated diagnostic or test macro/COM script against a blank disposable document.
5. Confirm argument ordering, coordinate units, coordinate origin, returned COM object, enum values, and error behavior.
6. Implement the operation in `corel_bridge.py` or a focused module, using existing validation and unit-conversion helpers.
7. Add a thin MCP wrapper in `server.py` or register through a central tool registry.
8. Add input validation, object/document targeting, timeouts, useful error messages, structured results and operation logging.
9. Add unit tests plus a guarded integration test. Do not test destructive operations on user documents.
10. Add the registry entry, docs, example prompt and changelog entry.
11. Mark `verified` only after a live integration test passes on the user's CorelDRAW version and the visible result is inspected.
12. Restart the MCP server and confirm the tool appears in Antigravity/OpenCode's available tool list.
13. Run a regression test for existing tools.
14. If the method is missing or behaves differently in X7, mark unsupported/research_required, then evaluate a macro fallback or UI-automation fallback separately.

### What not to do when adding tools
- Do not invent method names.
- Do not use an API from CorelDRAW 2025/2026 merely because the method page exists for a recent version.
- Do not expose one generic `run_any_macro(code)` or `execute_python(code)` tool.
- Do not create dozens of separate tools for trivial aliases that should be one parameterized operation.
- Do not claim a method works because Python syntax compiles.
- Do not trust a return value alone; inspect document/object state after mutation.
- Do not expose raw COM interfaces directly to the model.
- Do not allow filenames/paths to overwrite existing files silently.
- Do not hide exceptions; return a stable error code plus a concise diagnostic.

## 6. How to inventory “all CorelDRAW tools”

The phrase “all tools in CorelDRAW” can mean UI buttons, keyboard shortcuts, dialogs, automation APIs, or complete design workflows. They are not equivalent.

The deliverable should be a **CorelDRAW X7 Automation Capability Catalog**, not one MCP command per visible UI button.

### Discovery sources in order
1. Official CorelDRAW X7 object-model reference under `https://community.coreldraw.com/sdk/api/draw/17/`.
2. Official CorelDRAW Macro Programming Guide and local Macro Editor/Help object model reference.
3. Official CorelDRAW X7 Object Model Diagram.
4. Installed VGCore COM type library: inspect the registered type library/interfaces through safe Python/COM introspection where possible.
5. CorelDRAW X7 live tests against a disposable document.
6. User-interface automation only as a last resort when no reliable API exists.

Corel says the local Macros Help contains every feature/function that can be automated in the application, and its X7 guide explains VBA/VSTA and the object model. Verify whether VBA/VSTA features are installed; do not assume every install has the same components.

### Inventory process
- Enumerate documented classes, properties, methods, enums and events for the X7 object model.
- Enumerate the available COM type library/interfaces from the installed environment where tools allow.
- Normalize method names and attach source/version evidence.
- Group capabilities by domain.
- Map low-level API methods into user-facing tool workflows.
- For every candidate, record API name, class, signature, docs URL, minimum/maximum known version, parameter types, enum values, known quirks, mutating/destructive status, feasible MCP schema, test harness and status.
- Dedupe overloaded methods, aliases and duplicate inheritance entries.
- Mark undocumented dynamic-dispatch members as `research_required`.
- Cross-check the API inventory with the X7 object model diagram and local Macro Editor Help.
- Add the inventory to version control as machine-readable JSON plus a readable Markdown/CSV report.
- Build a discrepancy report for methods listed in docs but missing from type library, and methods in type library but not documented.
- Do not equate “method exists” with “AI should call it directly.” Some operations are too low-level, unsafe, or require UI context.

### Three layers of inventory
**Layer A: Raw API capability inventory.** Exhaustive list of documented/discoverable X7 classes, methods, properties, enums, events.

**Layer B: Approved MCP atomic tools.** A curated subset of reusable, typed, safe actions, such as `add_text`, `move_object`, `set_fill_color`, `align_objects`, `import_artwork`.

**Layer C: High-level workflow tools.** Task-specific orchestration such as `create_chest_number_batch`, `populate_id_cards_from_csv`, `arrange_n_up_print_sheet`, `recreate_reference_layout`, `preflight_print_document`. These orchestrate atomic tools deterministically.

Do not expose the complete raw API inventory as hundreds of MCP tools by default. Too many overlapping tools increase model confusion and make schemas hard to maintain. Keep raw API metadata searchable and expose the stable atomic and workflow tools as the model-facing surface. If future models can reliably search tool catalogs, use a capability-search tool or grouped tool loading.

## 7. Proposed automation catalogue / tool map

The following is the required capability roadmap, not a claim that all methods are already implemented or verified.

### A. Connection, diagnostics and capability discovery
- `corel_status`
- `list_open_documents`
- `get_active_document_info`
- `get_corel_version`
- `get_runtime_versions`
- `get_capabilities`
- `search_capability_catalog`
- `get_capability_details`
- `run_safe_diagnostics`
- `test_api_method` (diagnostic-only, allowlisted method and disposable document; never arbitrary calls)

### B. Document and file lifecycle
- `create_document`
- `open_document` (must report active file and ask before opening if it might affect current workflow)
- `activate_document`
- `get_document_info`
- `save_document` (new path by default; never overwrite silently)
- `save_document_as`
- `save_with_options` (explicit CDR save-format version, ICC embed, VBA project, range, overwrite flag)
- `close_document` (confirmation; block if unsaved changes unless explicit)
- `duplicate_document` where X7 supports a safe approach
- `export_pdf`
- `export_document` by explicit format
- `export_page_preview`
- `export_object_preview`
- `get_export_capabilities`

### C. Pages, units, layout and guides
- `list_pages`
- `create_page`
- `duplicate_page`
- `delete_page` (destructive confirmation)
- `activate_page`
- `set_page_size`
- `set_page_orientation`
- `set_page_background`
- `set_page_bleed`
- `get_page_bounds`
- `set_document_units`
- `get_document_units`
- `add_guideline`
- `list_guidelines`
- `remove_guideline`
- `set_grid_options`
- `get_print_bounds`
- `set_reference_point`
- `set_page_margins` (may be a bridge-level concept, not a native page property)

### D. Layers
- `list_layers`
- `create_layer`
- `rename_layer`
- `activate_layer`
- `set_layer_visibility`
- `set_layer_editable`
- `set_layer_printable` (only if supported by X7)
- `move_object_to_layer`
- `get_layer_info`

### E. Object inventory, selection and identity
- `list_objects`
- `get_object_info`
- `find_objects`
- `select_objects`
- `clear_selection`
- `get_selection`
- `name_object`
- `get_object_bounds`
- `get_object_text`
- `get_object_type`
- Use stable object names/metadata generated by this bridge. Shape index is a fallback only because indexes can change.

### F. Primitive drawing
- `add_text` / `create_artistic_text`
- `create_paragraph_text`
- `draw_rectangle`
- `draw_rounded_rectangle`
- `draw_ellipse`
- `draw_line`
- `draw_polyline`
- `draw_polygon`
- `draw_star`
- `draw_spiral`
- `draw_polygon_from_points`
- `draw_curve_from_points`
- `create_dimension_line` (confirm X7 API support)
- `draw_barcode` (check whether barcode capability exists in installed edition; otherwise external generator/import)
- `create_qr_code` (use a tested QR generator and import SVG if Corel API lacks native capability)

### G. Text editing and typography
- `set_text_content`
- `set_font_family`
- `set_font_size`
- `set_font_style`
- `set_text_alignment`
- `set_character_spacing`
- `set_line_spacing`
- `set_paragraph_spacing`
- `set_text_color`
- `fit_text_to_box` (bridge algorithm with bounds verification)
- `create_text_on_path` (only if verified)
- `convert_text_to_curves` (destructive confirmation; retain editable original/duplicate)
- `list_fonts_or_check_font_availability` (system-level check, disclose limitations)
- `get_text_properties`
- `replace_text_in_document` (preview matches first; then confirm/apply)
- `create_numbered_text_sequence`

### H. Fill, outline, transparency and appearance
- `set_fill_color_rgb`
- `set_fill_color_cmyk`
- `set_no_fill`
- `get_fill`
- `set_gradient_fill`
- `set_pattern_fill`
- `set_texture_fill` (verify X7 API/licensing/library)
- `set_transparency`
- `set_outline_color`
- `set_outline_width`
- `set_outline_style`
- `set_outline_caps_and_joins`
- `set_outline_arrowheads`
- `remove_outline`
- `get_outline`
- `apply_style`
- `copy_style`
- `sample_color_from_object` (only if API can reliably report it)

### I. Transform, arrange and duplicate
- `move_object`
- `resize_object`
- `scale_object`
- `rotate_object`
- `skew_object`
- `flip_object_horizontal`
- `flip_object_vertical`
- `align_objects`
- `distribute_objects`
- `align_to_page`
- `center_object_on_page`
- `set_z_order_front`
- `set_z_order_back`
- `move_forward_one_level`
- `move_backward_one_level`
- `duplicate_object`
- `duplicate_in_grid`
- `clone_object`
- `group_objects`
- `ungroup_objects`
- `lock_object`
- `unlock_object`
- `hide_object`
- `show_object`
- `delete_object` (destructive, confirmation, target must be unambiguous)
- `clear_transformations`
- `snap_to_guides` (may require geometry calculations rather than an API setting)

### J. Vector paths and boolean operations
- `convert_to_curves`
- `get_curve_nodes`
- `set_curve_nodes` (high risk, only if stable in X7)
- `close_curve`
- `reverse_curve_direction`
- `combine_shapes`
- `break_apart`
- `weld_shapes`
- `trim_shapes`
- `intersect_shapes`
- `simplify_curve`
- `smooth_nodes`
- `join_curves`
- `create_contour`
- `create_blend`
- `create_envelope`
- `create_distortion`
- `create_powerclip`
Each must be version-gated and implemented only after signatures and side effects are verified.

### K. Images and artwork
- `import_artwork`
- `import_bitmap`
- `import_svg`
- `import_pdf`
- `get_bitmap_info`
- `set_bitmap_size`
- `crop_bitmap` (use API or controlled geometry)
- `set_bitmap_transparency`
- `export_selected_object`
- `extract_or_link_embedded_asset` (only if safely supported)
- `replace_image_object`
- `place_image_inside_frame`
- `trace_bitmap` (may need UI or an X7-specific trace feature; do not assert API support until verified)
- `generate_artwork_via_provider` (external provider adapter, not a CorelDRAW API call)
- `place_generated_artwork`
- `vectorize_generated_artwork` (optional; trace fidelity is variable)

### L. Color systems and palette
- `create_rgb_color`
- `create_cmyk_color`
- `get_color_value`
- `set_color_profile` (verify X7 API support)
- `list_palettes`
- `create_palette`
- `import_palette`
- `add_swatch`
- `set_spot_color` (verify behavior and color management)
Do not treat RGB preview values as a substitute for print-specific CMYK/spot-color requirements.

### M. Grouping, effects, and object operations
- `apply_shadow` (verify X7 signature)
- `apply_transparency`
- `apply_contour`
- `apply_blend`
- `apply_distortion`
- `apply_envelope`
- `clear_effect`
- `break_effect_apart`
- `powerclip_add`
- `powerclip_extract`
- `set_object_rotation_center`
- `apply_color_effect` only after exact X7 API verification
- `copy_properties`
- `paste_properties`
This area needs a slower verification-first approach because many methods have complex arguments and irreversible consequences.

### N. Batch production and data merge
These are workflow tools over the atomic drawing tools:
- `create_chest_number_batch`
- `create_ticket_sequence`
- `create_id_cards_from_csv`
- `create_labels_from_csv`
- `create_certificates_from_csv`
- `create_business_cards_from_csv`
- `create_price_tags_from_csv`
- `duplicate_template_for_rows`
- `arrange_n_up_print_sheet`
- `calculate_sheet_layout`
- `prepare_imposition_job`
- `validate_sequence_no_gaps_or_duplicates`
- `report_missing_fields`
- `export_batch_to_individual_files`
- `export_batch_to_combined_pdf`
- `create_spreadsheet_field_mapping`
Batch generation should be deterministic: Python generates exact values and loops; the LLM should not manually invent 200 number objects one by one.

Imposition routing must also be deterministic:
- Obvious rectangular artwork uses `calculate_sheet_layout` / `plan_print_job`; do not ask which cutter will be used.
- Non-rectangular packaging or dieline work first uses `inspect_repeat_unit` and asks only its returned unresolved questions.
- Use `plan_contour_nesting` / `prepare_contour_nesting` only with one independently grouped repeat and one explicit closed vector dieline.
- Prefer `prepare_imposition_job` for model-facing vector imposition. Its first call plans only; mutation requires explicit confirmation plus the matching source-and-geometry plan fingerprint.
- Preserve the approved source page/group unchanged. Imposed repeats belong on a new output page, and rollback may remove only output created by that operation.
- On X7 build 17.0.0.491, cross-page group transfer uses the live-tested `Shape.Copy` / `Layer.Paste` fallback because `Shape.CopyToLayer` failed. The plan must warn before approval that execution replaces current system clipboard contents.
- Never flatten or group all imposed copies into one image. Each executed repeat remains a separately named top-level group.
- GPT interprets production intent; Python computes rotations, contour clearance, positions, capacity, and collision verification.

### O. Preview, validation and print preflight
- `export_preview`
- `inspect_page_bounds`
- `check_objects_outside_page`
- `check_overlaps`
- `check_missing_assets`
- `check_font_availability`
- `check_image_resolution`
- `check_bleed_and_safe_margin`
- `check_color_mode`
- `check_page_dimensions`
- `check_duplicate_ids`
- `create_preflight_report`
- `compare_reference_preview` (computer-vision or image-model adapter)
- `apply_safe_corrections`
- `request_approval_for_unresolved_issues`
No tool may claim “print-ready” until checks required for the specific print job pass or are explicitly marked as not checked.

### P. AI planning and generated imagery
- `build_design_plan` (prefer local structured plan JSON before execution)
- `validate_design_plan`
- `execute_design_plan` (only allowlisted operations; validate before execution)
- `preview_design_plan`
- `compare_design_to_reference`
- `generate_background_image` (provider adapter; API credentials from environment; never expose secrets)
- `generate_illustration`
- `remove_background` (provider/external package; availability check)
- `place_image_in_document`
- `revise_design_from_feedback`
Do not couple the MCP bridge to a single model provider or assume the ChatGPT web UI can be called as an API.

This catalogue is a roadmap. The agent must merge it with API evidence and the installed project code, then assign statuses to every candidate. Do not claim that every item is supported by CorelDRAW X7.

## 8. Tool catalog deliverables (machine-readable)

Create these project files:
- `docs/capability_catalog.md` — readable reference.
- `catalog/coreldraw_x7_api_inventory.json` — raw API inventory discovered from docs/type library.
- `catalog/mcp_tool_registry.json` — approved model-facing tools and schemas.
- `catalog/capability_matrix.csv` — capability, API evidence, X7 support status, test status, priority, limitations.
- `catalog/enum_reference.json` — CorelDRAW X7 enum names and numeric values derived from trusted X7 docs/type library.
- `docs/UNSUPPORTED_AND_RESEARCH_REQUIRED.md` — unsupported or uncertain operations plus what evidence is needed.
- `docs/TOOL_VERSIONING.md` — product, schema, and CorelDRAW version rules.
- `CHANGELOG.md` — dated change log.
- `tests/test_tool_schemas.py` — schema validation tests.
- `tests/test_corel_unit_conversion.py` — inches/points/angle conversion tests.
- `tests/integration/` — guarded tests requiring CorelDRAW X7.

Do not fill the catalog with guessed method names. Each raw inventory record should indicate its source and confidence.

## 9. Document targeting and safety

This software may manipulate valuable client artwork. Safety is a hard product requirement.

- Default target: a document explicitly created by this bridge.
- An existing/active document can be targeted only after the user explicitly authorizes the operation, with a clear confirmation that editing the existing document is intended.
- Before a major edit, save a checkpoint copy or use a tested undo/rollback strategy.
- Never overwrite CDR/PDF/image output silently. Generate unique filenames or require explicit confirmation.
- Destructive operations (`delete`, convert text to curves, flattening, weld/trim, overwrite, close unsaved document) need unambiguous target identification and confirmation.
- For batch operations, validate the complete job and output filenames before making changes.
- Keep a structured operation log: timestamp, tool, target doc, input summary, success/failure, output object IDs, duration. Avoid logging confidential artwork or secrets.
- No arbitrary macro execution, shell access, general file deletion, arbitrary Python execution, or unrestricted COM member invocation exposed to the model.
- Allow file imports only from local paths the user specified; enforce allowed extensions and size limits.
- Avoid path traversal; use normalized absolute paths and reject device paths/unsafe locations.
- Don't share private user document content with image-generation APIs unless explicitly requested and understood.
- Ask before external uploads or provider calls that send user artwork off-device.
- Maintain a backup of the current working project before major refactors.

## 10. Target document identity and object identity

A bridge-created document should have a stable session identifier and be stored as the target document inside the COM worker. Do not silently act on `Application.ActiveDocument` each time because focus changes.

Important implementation requirement:
- Each tool must use the explicitly bound target document.
- `use_active_document` must be an explicit opt-in requiring a confirmation flag and should return document name/path plus warning.
- Where possible, assign stable object names to new shapes; use an internal ID stored in document custom properties or a bridge-owned map where safe. Names alone are not guaranteed unique.
- Shape indexes are fallback selectors only and can become invalid after objects are created/deleted/reordered.
- All mutations must return object ID/name and actual resulting properties after the call.
- When tool processes restart, explain that transient COM object pointers/session state are lost; recover document identity by path/session metadata instead of persisting COM pointers to disk.

## 11. MCP tool design and AI-facing usage

### Atomic tools
Keep tools small and typed: add text, draw rectangle, set fill, move shape, etc.

### Workflow tools
Add higher-level deterministic actions after the atomic layer is tested: batch numbers, merge CSV, fit N-up sheets.

### Design-plan schema
The model should first create a plan such as:
```json
{
  "document": {
    "width": 8.5,
    "height": 11.0,
    "unit": "inches",
    "color_intent": "screen_preview"
  },
  "elements": [
    {
      "id": "panel",
      "type": "rectangle",
      "bounds": {"x": 1, "y": 8.5, "width": 6.5, "height": 1.3},
      "fill": {"model": "rgb", "value": [20, 45, 90]},
      "outline": {"model": "rgb", "value": [220, 180, 75], "width_points": 2}
    },
    {
      "id": "title",
      "type": "artistic_text",
      "text": "AI DESIGN OPERATOR",
      "font": "Arial",
      "size_points": 24,
      "bold": true,
      "fill": {"model": "rgb", "value": [255, 255, 255]}
    }
  ]
}
```
This is an illustrative schema only. Validate bounds, required fields, units, duplicate IDs and target document before execution.

### Natural-language behavior
- Infer ordinary implementation decisions when safe.
- Ask one focused question if an essential output constraint is missing and cannot be reasonably defaulted.
- Summarize assumptions for dimensions, fonts, colors, background, file format, and print intent.
- Do not ask about every primitive operation. Plan then execute.
- Use exact deterministic code for numbering/layout calculations; use AI for interpretation and creative decisions.
- After execution, inspect actual document data, export a preview when available, and report discrepancies.
- If a tool is unavailable, say which capability is not implemented instead of pretending.

## 12. API discovery and runtime introspection plan

Implement a **safe discovery utility**, not an arbitrary method executor:
- connect to CorelDRAW X7 and read the app version/build;
- report `Application` properties that are intentionally allowlisted;
- where possible, inspect registered type-library metadata and class/interface member names;
- report Python and dependency versions;
- compare discovery output against the official X7 docs and local macro reference;
- generate a candidate API inventory report only;
- never call every discovered method automatically; many methods can mutate documents, open dialogs, or require special argument structures.

Prefer registered type-library information and official docs over `dir()` alone. Dynamic COM proxies may not enumerate all methods. A method absent from Python's `dir()` is not necessarily absent from COM.

Provide one dedicated validation harness that creates a disposable document, runs one capability test, inspects expected state, saves to a temporary output directory, and records result. For destructive tests, use throwaway copies only. Don't execute large unknown batches against the user's active document.

## 13. Compatibility layer

Use adapters rather than scattered checks:
- `CorelX7Adapter` for application major version 17.
- Add other adapters only after testing on those releases.
- Capability API such as `supports("shape.create_rectangle") -> true/false` with reason and tested status.
- Each tool checks that its required capability is available.
- If unsupported, return `UNSUPPORTED_IN_PROFILE`, profile ID and a helpful next step.
- Keep API method signatures/enums/constants in an X7 adapter or typed registry, not duplicated in every method.
- Do not rely on API docs for X7.4, 2024, 2025 or 2026 unless cross-version support is independently confirmed for X7.

## 14. Test plan and acceptance criteria

### Stage 1 — regression
- `corel_status` returns CorelDRAW X7 `17.0.0.491`.
- No exceptions from server startup; MCP v1 FastMCP import resolves.
- COM call dispatcher remains on the same initialized worker thread.
- Existing test document remains untouched.

### Stage 2 — atomic drawing
- Create new document at exact configured size.
- Add text, rectangle and ellipse as editable objects.
- Set fill, outline and text properties.
- Move/resize and read back actual bounds.
- Save CDR with correct X7 options and unique filename.
- Export PDF to unique filename and verify page dimensions. Do not assert print readiness without preflight.

### Stage 3 — tool list and schema
- All registered tools have valid JSON-compatible schemas.
- Tool descriptions explain units/selection semantics.
- Invalid RGB, empty text, invalid size, ambiguous selector, unsafe path and overwrites are rejected.
- Each tool reports structured errors.
- Antigravity lists the new tools after a restart and can call read-only `corel_status` and `list_objects`.

### Stage 4 — workflow
- Create a business-card/letterhead/poster from a prompt.
- Recolor/move/edit an object by stable name.
- Create 200 numbered items with no missing or duplicate values; leading zeros preserved when specified.
- Arrange items on a print sheet and report if the requested layout does not fit.
- Generate a design from a reference by combining editable text/shapes with imported raster/vector assets.
- Compare exported preview to reference and report known mismatch areas.

### Stage 5 — regression and release
- Add reproducible test report, version update and change log.
- Mark each tool `verified` only with a recorded passing live test on CorelDRAW X7.
- Keep `implemented_unverified` distinct from `verified`.

## 15. Priority order: what to build next

1. **Audit and stabilize v0.5**: inspect real installed files, check `corel_bridge.py` and `server.py`, make a backup, run tests, and patch in place.
2. **Catalog/discovery system**: generate JSON/CSV inventory from X7 docs and available type-library metadata. This is the foundation for “all tools”.
3. **Document and object inspection**: reliable object identity, layer/page traversal, full object properties.
4. **Reliable styling**: fill, outline, text font/size/alignment and CMYK where supported.
5. **Transform and layout**: move, resize, align, distribute, z-order, groups, duplicate.
6. **Image import/export and previews**: test file filters, exact bounds, export resolution and page settings.
7. **Workflow planning**: design plan JSON and controlled execution.
8. **Batch production**: chest numbers, labels, cards, tickets, certificates, CSV/XLSX input and N-up.
9. **Visual feedback**: export preview, vision-based comparison, apply targeted corrections.
10. **AI image-generation adapter**: backgrounds and complex visual artwork, with user authorization before sending private assets to outside providers.
11. **Other AI clients**: validate OpenCode after Antigravity; only then document client-specific differences.
12. **ChatGPT route**: implement only through an officially supported connection for the user's account or a separate model-API interface; do not promise direct write access from every plan.

## 16. Required response from the coding agent

When you start:
1. Confirm the exact working project directory and list its files.
2. Make a backup or Git commit before editing.
3. Inspect and report current tool list, dependency versions and MCP config.
4. Identify which v0.5 tools are implemented, unverified, or broken.
5. Create the inventory/catalog files.
6. Propose the next small patch.
7. Implement the first verified batch of tools with tests.
8. Show exact file diffs, command lines, test outcomes, limitations and manual checks needed.
9. Never claim that every CorelDRAW capability is implemented if the catalog still contains `planned`, `research_required`, `unsupported` or `implemented_unverified` entries.
10. Continue in small releases rather than generating a huge untested code dump.

This is an engineering project, not a one-shot code-generation exercise. Favor accurate APIs, predictable changes, backups, and visible tests.

---

## 17. Official technical references

Use these as initial sources; the X7 section is the target, not current-version docs.

1. CorelDRAW Developer Area and API references: https://community.coreldraw.com/sdk
2. CorelDRAW X7 API, version 17 root: https://community.coreldraw.com/sdk/api/draw/17/
3. CorelDRAW X7 Programming Guide: https://community.coreldraw.com/sdk/w/guide
4. External process control for CorelDRAW X7: https://community.coreldraw.com/sdk/w/articles/217/controlling-coreldraw-or-corel-designer-applications-from-other-processes
5. X7 `Application` object: https://community.coreldraw.com/sdk/api/draw/17/c/application
6. X7 `Shape` object: https://community.coreldraw.com/sdk/api/draw/17/c/shape
7. X7 `Page` object: https://community.coreldraw.com/sdk/api/draw/17/c/page
8. X7 `Layer.CreateArtisticText`: https://community.coreldraw.com/sdk/api/draw/17/m/layer.createartistictext
9. X7 `Fill.UniformColor`: https://community.coreldraw.com/sdk/api/draw/17/p/fill.uniformcolor
10. X7 `Outline` object: https://community.coreldraw.com/sdk/api/draw/17/c/outline
11. X7 `StructSaveAsOptions`: https://community.coreldraw.com/sdk/api/draw/17/c/structsaveasoptions
12. X7 `Document.SaveAs` (X7.4 reference; verify X7 build before use): https://community.coreldraw.com/sdk/api/draw/17.4/m/document.saveas
13. CorelDRAW X7 Object Model Diagram PDF: https://community.coreldraw.com/sdk_files/CorelDRAW%20Object%20Model%20Diagram.pdf
14. CorelDRAW X7 User Guide: https://product.corel.com/help/CorelDRAW/540229932/Main/EN/User-Guide/CorelDRAW-X7.pdf

The official external-process tutorial explicitly discusses CorelDRAW X7, `CorelDRAW.Application.17`, COM/type-library access and creating artistic text from an external process. The X7 reference documents the Shape, Page, Layer, Fill and Outline object model. Verify any method, enum and signature against the X7 docs and live install before marking it supported.
