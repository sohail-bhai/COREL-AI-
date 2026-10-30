# Implementation Plan — CorelDRAW AI Operator

## Current status
- Confirmed COM connection to CorelDRAW X7, version 17.0.0.491.
- Python 3.11.9 64-bit was reported.
- Next validation: create and save a separate test document with editable text and shapes.

## Phase 1 — Working CorelDRAW bridge
- Validate new document creation and page sizing.
- Validate inches conversion.
- Validate editable artistic text, rectangles and ellipses.
- Validate safe save with an explicit `StructSaveAsOptions` object and then PDF publishing.
- Test through smoke test before connecting an AI client.

## Phase 2 — Connect Antigravity and OpenCode
- Register the same MCP stdio server in each client.
- Test `corel_status`, `create_document`, `add_text`, and `draw_rectangle`.
- Add a clear confirmation/backup policy for destructive operations.

## Phase 3 — Natural-language design
- Add a structured design plan schema.
- Add document inspection, object listing, colors, outlines, grouping, move/resize and text editing.
- Use exported previews for visual correction.
- Keep exact dimensions as deterministic values.

## Phase 4 — Batch production
- Sequential chest numbers and leading-zero preservation.
- CSV/XLSX-driven IDs, labels, certificates and product tags.
- Template cloning and print-sheet placement.
- Verification of missing/duplicate rows.

## Phase 5 — Reference recreation and generated artwork
- Analyze reference layouts.
- Rebuild text and simple graphics as editable objects.
- Import SVG and raster images for complex art/backgrounds.
- Preview and compare iteratively.

## Phase 6 — Preflight and production
- Checks for page size, bleed, font presence, image resolution, color setup and export dimensions.
- Printer-specific test exports.
- Do not label a file print-ready until its actual requirements have been checked.

## Phase 7 — Multi-client support
- Confirm OpenCode MCP setup.
- Confirm Antigravity MCP setup.
- Add ChatGPT only through a supported custom MCP route for the user's account, or a separately built model-API client.
