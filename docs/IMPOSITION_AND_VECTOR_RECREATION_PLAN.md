# Imposition Orchestration and Reference-to-Vector Reconstruction Plan

**Plan revision:** 2026-11-01  
**Target:** CorelDRAW Graphics Suite X7, build 17.0.0.491  
**Clients:** Antigravity, OpenCode, and other approved MCP clients  
**Status:** Approved roadmap; A1/A2 implemented-unverified on 2026-11-01, disposable X7 verification pending

### Implementation checkpoint — 2026-11-01

- `prepare_imposition_job` now owns classify/plan/approve/execute routing for selected vector repeats.
- The first call is non-mutating; execution requires `confirm_execution=true` plus the exact SHA-256 fingerprint recomputed from source identity, production inputs, output policy, and deterministic geometry.
- Obvious rectangles bypass cutter questions. Contour jobs ask about 180° rotation only when the rotated candidate improves sheet capacity.
- Execution creates one new page and explicit output layer, copies the source with the installed X7 type-library-confirmed `Shape.CopyToLayer` signature, keeps every repeat as an independent group, and verifies actual contours.
- Failure cleanup deletes only the newly added output page and verifies that the approved source signature is unchanged.
- These behaviors have fake-COM/unit evidence only. `AddPagesEx`, `CopyToLayer`, page deletion, curve flattening, group rotation, and coordinate readback remain `implemented_unverified` until an explicitly authorized disposable X7 run.
- Multi-sheet materialization and production layers/marks/controlled exports remain A5/A6 work.

## 1. Outcomes

This roadmap delivers two related production workflows:

1. **Reliable print imposition:** the user supplies one repeat unit and production constraints; the system asks only relevant questions, computes geometry in Python, preserves the source, creates independent copies, and verifies the actual CorelDRAW result.
2. **Reference-to-vector reconstruction:** the user supplies a design image, screenshot, scan, PDF preview, or photograph; the system analyzes it into a structured plan and recreates supported content as an editable vector CDR rather than flattening the complete design into one image.

The model interprets intent and ambiguity. Deterministic code owns dimensions, transformations, collision detection, object creation, validation, and readback.

## 2. Non-negotiable product rules

1. Do not ask cutter questions for obvious rectangular work.
2. Ask cutter, grain, or rotation questions only when they can change a non-rectangular production plan.
3. Never treat an already imposed multi-copy image or group as one repeat unit.
4. Keep every imposed repeat as a separately named top-level group.
5. Preserve the original source page/document; production output belongs on a new page or document.
6. Never infer contour clearance, font identity, dimensions, or text content from appearance when exact source data is available.
7. Do not call a raster import a vector recreation.
8. Keep all supported text editable unless the user explicitly authorizes conversion to curves.
9. Report every raster fallback, substituted font, approximate color, unsupported effect, and low-confidence observation.
10. No workflow may claim `print_ready: true` until all job-specific production checks are implemented and passed.
11. No private reference may be uploaded to an external vision or generation provider without explicit approval.
12. Every mutation must support preflight, actual-state readback, discrepancy reporting, and rollback.

## 3. Shared workflow architecture

Both workstreams use the same bounded state model:

```text
inspect
  -> classify
  -> needs_input (only if required facts are missing)
  -> plan
  -> validate
  -> await_approval
  -> execute
  -> read_back
  -> verify
  -> completed | rolled_back | failed
```

Every high-level planner returns:

```json
{
  "status": "needs_input | planned | completed | failed",
  "questions": [],
  "blocking_issues": [],
  "warnings": [],
  "plan_fingerprint": "deterministic-hash",
  "ready_for_execution": false
}
```

Execution must recompute and match the approved plan fingerprint. This prevents a model from approving one plan and executing changed geometry.

## 4. Workstream A — Reliable imposition orchestration

### A0. Live-verify the existing contour vertical slice

The pure planner and fake-COM execution are implemented. Before expanding them, run guarded tests against a disposable X7 document.

Verify:

- `SubPath.GetPolyline` availability and precision on build 17.0.0.491.
- Straight, rounded, and Bézier dielines.
- Closed-subpath detection.
- Child object names after group duplication.
- `Shape.Rotate(180)` and `RotationAngle` readback.
- Child contour coordinates after parent-group rotation.
- Group movement based on contour rather than group bounding box.
- Independent top-level groups after execution.
- Command-group rollback after a forced discrepancy.
- Shared-cut-line behavior at zero clearance.
- Positive bleed/gutter clearance after Corel coordinate rounding.

**Acceptance fixture:** one asymmetric carton contour where two upright rows fit fewer copies than alternating 0°/180° rows. The upper row must rotate, move closer, remain collision-free, and stay independently grouped.

### A1. Add one model-facing imposition orchestrator — implemented-unverified

Implement `prepare_imposition_job` as the preferred model-facing entry point. Low-level planners remain available for testing and expert use, but Antigravity should not manually combine duplicate, rotate, group, and move calls.

Proposed input:

```json
{
  "source_selector": {"object_name": "Repeat_Unit"},
  "dieline_name": "CutContour",
  "sheet_width_inches": 19,
  "sheet_height_inches": 13,
  "quantity": 100,
  "bleed_inches": 0.125,
  "gutter_inches": 0.125,
  "margin_inches": 0.25,
  "cutting_method": "unknown",
  "allowed_rotations": [0, 180],
  "confirm_execution": false,
  "approved_plan_fingerprint": ""
}
```

Internal routing:

```text
obvious rectangle
  -> rectangular best-fit N-up
  -> no cutter question

explicit non-rectangular contour
  -> unknown cutter: ask
  -> guillotine only: rectangular separation bounds
  -> die/digital cutter: contour nesting
  -> unknown grain/direction: ask only if rotation would improve the result
```

The first call plans only. Mutation requires `confirm_execution=true` and a matching plan fingerprint.

### A2. Preserve the source automatically — implemented-unverified

The initial contour executor required a clean page and transformed the source group. The implemented-unverified A2 slice replaces that limitation with this source-preserving workflow:

```text
Source page/document
└── Repeat_Unit

New output page/document
├── Nested_Copy_001
├── Nested_Copy_002
├── Nested_Copy_003
└── Nested_Copy_004
```

Tasks:

- Research and live-verify X7 `CopyToLayer` or the safest equivalent cross-page/cross-document operation.
- Never move or rename the approved source group.
- Record source document/page/object identity in the plan.
- Reject execution if source identity changes after approval.
- Put print artwork, dielines, fold lines, and marks on explicit output layers.
- Roll back and remove only the newly created output page/document on failure.

### A3. Inspect a selected repeat automatically

Implement `inspect_selection_as_repeat`.

It should:

- Determine whether the selection represents one repeat, several repeats, or one flattened multi-copy image.
- Reject combined four-up artwork as a source repeat.
- Report top-level and child object counts and types.
- Offer to create one repeat group only after confirmation.
- Find cut-contour candidates using, in priority order:
  1. Explicit object name (`CutContour`, `Dieline`, `Cut`).
  2. Explicit dieline layer.
  3. Verified spot-color name.
  4. Closed outer-curve geometry.
- Ask the user to choose only when multiple credible contours remain.
- Never group every page object merely because they are selected.

### A4. Expand deterministic contour optimization

Implement in this order:

1. **Horizontal row offsets:** evaluate zero offset and geometry-derived contact offsets for opposing rows.
2. **Rotation policies:** support `[0]`, `[0, 180]`, and explicitly approved `[0, 90, 180, 270]`.
3. **Grain and direction constraints:** exclude illegal candidates before optimization.
4. **No-fit-polygon contact candidates:** derive useful translations from contour vertices/edges rather than visual guessing.
5. **Common-line policy:** allow shared cut lines only when explicitly authorized.
6. **Alternative scoring:** capacity, sheets, waste, overage, cutting complexity, and production risk.

Remain bounded and production-friendly. Unrestricted free-form/Tetris nesting is not the default.

### A5. Execute complete multi-sheet jobs

Planning already reports sheets and overage. Execution should create every required output page:

- Full-sheet master placement.
- Required number of pages/sheets.
- Optional reduced final sheet to avoid unnecessary overage.
- Stable copy numbers across pages.
- Per-page verification and a whole-job manifest.
- Rollback policy that identifies exactly which pages were created.

### A6. Add production output controls

After geometry is live-verified:

- Print and cut layers.
- Crop/registration marks where applicable.
- Cutter registration marks and barcodes where supported.
- Output color-profile checks.
- Controlled PDF preset.
- Separate cut-file export where required.
- Job ticket containing source identity, quantity, sheet, rotations, cutter method, grain rule, warnings, and plan fingerprint.

## 5. Workstream B — Reference design to editable vector CDR

### B0. Define supported reconstruction tiers

The system must classify the reference before promising fidelity.

| Tier | Reference type | Expected output |
|---|---|---|
| V1 | Flat layouts with text, solid shapes, lines, simple icons, and placed assets | Mostly or fully editable vector CDR |
| V2 | Logos, curved paths, gradients, clipping, moderate illustration | Editable vector/hybrid CDR with disclosed approximations |
| V3 | Photographs, painterly artwork, complex textures, 3D renders | Vector layout plus approved raster regions; never described as fully vector |
| Unsupported/blocked | Unreadable text, unknown dimensions, protected/private upload without approval, missing critical assets | Structured questions or honest refusal for affected regions |

Pixel-perfect recreation from every flattened screenshot is not guaranteed. Physical geometry, editability, text accuracy, and disclosed differences are the primary contract.

### B1. Materialize and preflight the reference

Chat attachments are not automatically local MCP files. The client must materialize the reference to an approved local path or pass an approved provider result.

Implement `inspect_reference_design`:

- Validate local path, extension, byte size, dimensions, frame count, orientation, alpha, color mode, and profile.
- Detect screenshot, clean export, scan, camera photograph, or PDF preview.
- Detect likely perspective distortion and crop.
- Ask for target physical width/height when it cannot be inferred reliably.
- Ask for a cleaner/original asset when the supplied reference is too small.
- Record privacy classification and whether cloud processing is authorized.
- Generate a local analysis preview without modifying CorelDRAW.

Required initial facts:

- Target page dimensions or one known physical measurement.
- Whether exact text must remain editable.
- Whether supplied logos/assets must be reused rather than traced.
- Whether raster fallback is allowed for complex regions.

### B2. Introduce a provider-neutral reference-analysis schema

The MCP bridge must not depend on one vision model. Define `reference-analysis-v1` so analysis may come from:

- A local CV/OCR adapter.
- An explicitly approved external vision provider.
- A client vision model that returns schema-valid observations.
- A combination of deterministic detection and model interpretation.

Proposed structure:

```json
{
  "reference": {
    "pixel_width": 1600,
    "pixel_height": 1000,
    "target_width_inches": 8.5,
    "target_height_inches": 5.5,
    "perspective_corrected": false
  },
  "elements": [
    {
      "id": "headline",
      "kind": "text",
      "bounds_normalized": {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.12},
      "rotation_degrees": 0,
      "z_index": 20,
      "text": "Example",
      "text_confidence": 0.98,
      "font_candidates": ["Montserrat Bold"],
      "style": {},
      "uncertainties": []
    }
  ],
  "relationships": [
    {"type": "centered_on", "subject": "headline", "target": "page"}
  ],
  "palette": [],
  "questions": [],
  "unsupported_regions": []
}
```

All pixel coordinates are normalized before conversion to inches. Python—not the model—performs the pixel-to-page transform.

### B3. Extend the design-plan schema without breaking v1

Create `design-plan-v2`; keep v1 readable.

Add evidence-backed element types and properties incrementally:

- Line and polyline.
- Rounded rectangle.
- Polygon.
- Bézier path.
- Artistic and paragraph text.
- Rotation and proportional scaling.
- Layer and z-order.
- Group relationships.
- Opacity/transparency.
- Verified RGB/CMYK/spot colors.
- Linear/radial gradients after X7 verification.
- Clipping/PowerClip after X7 verification.
- Placed raster/SVG assets with explicit fallback status.

Before mutation, `validate_design_plan` must reject unsupported element kinds, invalid paths, duplicate IDs, ambiguous layers, missing assets, text overflow, and out-of-canvas geometry.

### B4. Build the simple editable-vector vertical slice

Implement `plan_reference_recreation` and `execute_reference_recreation` for V1 references first.

Supported first slice:

- Exact page size.
- Solid background.
- Rectangles, rounded rectangles, ellipses, lines, and simple polygons.
- Editable artistic/paragraph text.
- RGB fills and outlines.
- Basic alignment, rotation, grouping, layers, and z-order.
- Approved placed image assets for explicitly non-vector regions.

Execution rules:

- Always create a new document.
- Use stable names derived from analysis IDs.
- Keep semantic layers (`Background`, `Artwork`, `Text`, `Cut`, `Reference`).
- Optionally keep the reference on a locked non-printing layer if X7 support is verified.
- Read back text, bounds, styles, layers, rotation, and object count.
- Never merge all reconstructed elements into one bitmap.

### B5. Typography reconstruction

Typography is a separate accuracy track, not a visual guess.

- OCR text with confidence per region.
- Require confirmation for low-confidence or tiny text.
- Check installed fonts before execution.
- Rank font candidates using measured glyph/layout similarity where possible.
- Never claim an exact font match without an installed matching font or source evidence.
- Fit text using deterministic width/height measurements and bounded font-size/spacing adjustments.
- Preserve paragraph alignment, line breaks, tracking, line spacing, and capitalization.
- Report substituted fonts and overflow.
- Permit conversion to curves only after explicit approval because editability is lost.

### B6. Vector paths, logos, and complex regions

Add only after V1 is stable:

- Edge/path extraction for high-contrast simple icons.
- Curve simplification with configurable tolerance.
- Closed-path validation and self-intersection checks.
- Native fills/outlines on traced paths.
- Optional Corel PowerTRACE only after X7 API evidence and live tests.
- Prefer original SVG/EPS/PDF/logo assets over tracing screenshots.
- Do not silently recreate protected marks inaccurately; record that the user supplied or authorized the asset.
- Keep photographs and complex textures as explicit raster regions unless a supported vectorization method succeeds.

### B7. Deterministic preview comparison and correction

Implement:

- `export_recreation_preview` at a fixed DPI and color mode.
- `compare_recreation_to_reference` after alignment to the same canvas.
- `plan_recreation_corrections` containing targeted edits only.

Comparison layers:

1. Canvas and major-region bounds.
2. Edge overlap and alignment.
3. Text content and line breaks.
4. Element count and hierarchy.
5. Palette/color differences.
6. Perceptual image difference for final review.
7. Optional vision critique for semantic mismatches.

The correction loop is bounded, for example three automatic iterations. Each iteration must improve measured criteria or stop and report unresolved differences. Do not repeatedly rebuild the entire document.

### B8. Add one high-level reconstruction orchestrator

Implement `recreate_reference_design` after the lower-level stages are verified.

It should:

```text
inspect reference
  -> ask only missing dimensions/privacy/text questions
  -> analyze into reference-analysis-v1
  -> classify V1/V2/V3 support tier
  -> build design-plan-v2
  -> validate and preview
  -> return planned result and fingerprint
  -> execute only after approval
  -> compare preview
  -> apply bounded targeted corrections
  -> save editable CDR to a unique path
  -> return fidelity/editability report
```

The final report must separate:

- Fully editable vector elements.
- Editable text.
- Traced/approximated paths.
- Imported vector assets.
- Raster fallback regions.
- Font substitutions.
- Unresolved visual differences.

## 6. Agent behavior and conditional questions

The high-level tools—not prompt cleverness—must determine required questions.

Examples:

| Situation | Required behavior |
|---|---|
| Rectangular business card | Plan N-up; do not ask cutter method |
| Irregular carton with unknown cutter | Ask cutter method |
| Carton where 180° does not improve capacity | Do not ask grain/rotation solely for optimization |
| Carton where 180° improves capacity | Ask whether grain/design direction permits it if unknown |
| Reference with known dimensions and clear text | Plan without unnecessary questions |
| Reference with no physical scale | Ask target dimensions |
| Tiny unreadable text | Ask for text or a better source |
| Photograph-heavy poster | Explain hybrid/raster regions; do not promise full vector output |
| Four-up flattened source | Reject as one repeat and request the original single design |

## 7. Unified implementation order

| Order | Batch | Deliverable | Exit gate |
|---:|---|---|---|
| 1 | A0 | Live X7 contour verification | Curved carton fixture passes rotation, placement, collision, and rollback |
| 2 | A1 | `prepare_imposition_job` planner/approval orchestrator | Antigravity uses one entry point and cannot skip classification |
| 3 | A2 | Source-preserving output page/document | Source identity and geometry remain unchanged after execution |
| 4 | A3 | Selection/repeat inspector | One repeat is detected; combined multi-copy sources are rejected |
| 5 | Client regression | Rectangle and carton prompt suite | Cutter questions appear only when relevant |
| 6 | B0–B1 | Reference tiers and file preflight | Local reference is safely classified and physically calibrated |
| 7 | B2 | `reference-analysis-v1` plus provider interface | Local/client/provider analyses validate through one schema |
| 8 | B3 | `design-plan-v2` and missing primitive tools | V1 plans validate without breaking v1 |
| 9 | B4 | Simple editable-vector recreation | Benchmark card/flyer recreates as named editable objects |
| 10 | B5 | Typography accuracy | Text content, font status, bounds, and overflow are verified |
| 11 | B7 | Preview comparison and bounded correction | Metrics improve or unresolved differences are reported |
| 12 | B8 | `recreate_reference_design` orchestrator | One approved workflow creates, compares, and saves an editable CDR |
| 13 | A4 | Horizontal offsets and expanded rotation candidates | Additional carton benchmarks improve without unsafe overlap |
| 14 | A5 | Multi-sheet execution | Quantity/pages/overage and final partial sheet are verified |
| 15 | B6 | Advanced paths and hybrid reconstruction | V2/V3 regions are reconstructed or disclosed correctly |
| 16 | A6 | Marks, profiles, controlled export, job ticket | Job-specific print checks support an honest production report |

Do not start B6 advanced tracing before the V1 editable layout and comparison loop pass.

## 8. Acceptance benchmark set

Maintain local, non-confidential fixtures with known dimensions and expected structure:

1. **Simple business card:** background, logo asset, two text styles, line, and contact icons.
2. **Promotional flyer:** paragraph text, hierarchy, colored panels, circles, and one photograph.
3. **Product label:** small text, barcode placeholder, border, and spot-color intent.
4. **Asymmetric carton dieline:** four copies where alternating 0°/180° rows outperform bounding-box placement.
5. **Curved package contour:** tests Corel curve flattening tolerance.
6. **Perspective photograph of a design:** must request/perform calibration before reconstruction.
7. **Low-resolution reference:** must ask for missing text/assets instead of hallucinating.
8. **Flattened four-up image:** must be rejected as a repeat source.

For supported vector benchmarks, require:

- Correct physical page dimensions within the established X7 tolerance.
- Separate named objects and expected layer/z-order structure.
- Exact confirmed text content.
- Editable text where promised.
- Geometry readback within configured tolerance.
- No undisclosed raster fallback.
- A preview comparison report.
- Unique non-overwriting CDR output.

## 9. Test strategy

Every batch requires:

1. Pure geometry/schema unit tests.
2. Invalid, boundary, ambiguity, and overflow tests.
3. Fake-COM success and rollback tests.
4. Guarded disposable X7 integration tests for every new COM member.
5. Retained machine-readable test report.
6. Manual CDR review for editability, layers, text, and visual fidelity.
7. Antigravity and OpenCode prompt regression.
8. Catalog, changelog, and capability-status updates.

Reference reconstruction also requires golden fixtures and versioned comparison thresholds. A changed vision provider must not silently change execution plans without a recorded analysis/schema version.

## 10. Decisions and open gates

The following are intentionally selected now:

- Local-file processing first.
- Provider-neutral vision schema.
- New-document reconstruction only.
- Vector-first with explicit hybrid fallback.
- Plan approval and fingerprint before mutation.
- Bounded correction loops.
- Source-preserving imposition.

The following must be decided only when their implementation batch starts:

- Local OCR engine versus approved external OCR adapter.
- Vision provider and credential model.
- Whether OpenCV or another local CV dependency is justified.
- X7 evidence for PowerTRACE automation.
- X7 evidence for cross-page/cross-document copying.
- Comparison metrics and benchmark-specific pass thresholds.
- Font-similarity implementation and font licensing policy.

## 11. Definition of completion

This roadmap is complete when both statements are true:

> Given one rectangular or non-rectangular repeat, the operator asks only relevant production questions, preserves the source, creates the best approved layout as independent groups, and proves the actual output is in bounds and collision-free.

> Given a supported reference design and physical dimensions, the operator creates a new editable vector-first CDR with verified text, named objects, layers, dimensions, preview comparison, disclosed approximations, and no flattened whole-design shortcut.
