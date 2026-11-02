# Alhamdulillah A4 Vector Recreation — V2 Fidelity Plan

## Priority status — deferred by the user on 2026-11-02

The user reviewed the current result and moved custom calligraphy and
other-language reconstruction into the future backlog. Preserve the V1/V2
artifacts, measurements, code, and validation reports. The automated Phase 3
result remains a checkpoint requiring visual review, not final approval.

Further tracing, English matching, lighting, and fidelity correction for this
artwork are outside the active queue. Resume this plan only when the user
requests it. Common-work priorities are maintained in
[`CURRENT_IMPLEMENTATION_PRIORITIES.md`](CURRENT_IMPLEMENTATION_PRIORITIES.md).

## Goal

Rebuild the supplied photographed design as a clean A4 landscape CorelDRAW
document whose visible geometry closely follows the reference while remaining
fully vector. The photograph is analysis material only and must not be embedded
in the deliverable artwork.

The V1 file is retained as evidence and must not be overwritten. V2 will be
created as a new document and output folder.

## Why V1 failed visually

V1 proved only that CorelDRAW could create an A4 document with vector objects,
layers, gradients, groups, and editable text. Its PASS result did not measure
similarity to the supplied design. That was the wrong completion criterion.

### 1. Arabic calligraphy — critical failure

- The reference contains a custom composed calligraphic treatment, not ordinary
  typeset Arabic.
- V1 substituted the Aldhabi font and stretched its text bounds. This changed
  the glyph construction, joins, stroke order, word spacing, terminals, and
  diacritic positions.
- The V1 calligraphy separates into visually unrelated left and right clusters,
  whereas the reference is a broad, integrated central composition.
- The large V1 underline and rising stroke were invented approximations rather
  than traced parts of the reference lettering.
- The gold highlight and shadow follow generic object gradients instead of the
  actual light/dark regions of the reference strokes.

**V2 decision:** do not use a font for the visible Arabic. Trace the exact
silhouette into editable Bezier curves, keeping principal strokes and diacritics
as named child objects. A hidden nonprinting Unicode text object may be retained
only for semantic/editing reference.

### 2. Trellis outside the page — critical production failure

- V1 generated repeat cells beyond the art and page boundaries.
- Four white rectangles were used as visual masks, but they are not a true clip.
- The PDF hid the problem because PDF export clips to the page. CorelDRAW's
  editing view correctly reveals the out-of-page curves around all four sides.
- The audit checked bitmap count and PDF size but never checked printable object
  bounds against the page.

**V2 decision:** build one accurate pattern tile and PowerClip the repeat field
into the inner art rectangle. If X7 PowerClip automation is unreliable, trim or
intersect the repeated curves geometrically. No printable child may remain on
the pasteboard.

### 3. Trellis design — major mismatch

- The reference uses a slim interlocking Moroccan ogee/quatrefoil network with
  pronounced necks and pointed transitions.
- V1 uses a generic rounded clover cell. Its lobes, corner transitions, pitch,
  row offset, and density are visibly different.
- The V1 top and bottom crops do not match which portions of the source repeat
  are visible at the edges.

**V2 decision:** trace one clean repeat directly from a perspective-corrected
reference, determine exact horizontal/vertical pitch, and duplicate that module.

### 4. Plaque silhouette — major mismatch

- V1 uses a symmetrical hand-guessed cloud shape.
- The reference plaque has its own asymmetric shoulder locations, scallop radii,
  transition points, and clipped central plateau.
- V1's side boundaries and shoulder heights create rectangular-looking dark
  regions that are not positioned like the photographed design.
- The dark gradient is too uniform and too black in the lower half.

**V2 decision:** trace the plaque boundary from the rectified reference as one
closed Bezier curve. Do not generate it from mirrored numeric guesses.

### 5. English lettering — substantial mismatch

- Bookman Old Style Bold is too heavy and too slab-like for the reference.
- Width, cap height, baseline, tracking, serif shape, and word position differ.
- The V1 brown offset shadow is stronger than the reference and reads as an
  added 3D effect.

**V2 decision:** compare installed serif candidates by rendered silhouette and
measured word bounds. Preserve editable text only if a close match is found;
otherwise use a curve copy for the visible word plus hidden editable source text.

### 6. Light effects — substantial mismatch

- V1 light positions were estimated before a reliable photo-to-page transform.
- Several glows are missing, displaced, or have the wrong size.
- Some reference glows terminate Arabic strokes; V1 treats them as unrelated
  floating dots.
- Concentric opaque circles still create harder halos than the soft reference.
- The principal starburst has incorrect ray lengths, brightness falloff, and
  relationship to the nearby orb.

**V2 decision:** catalogue every light from the rectified reference with center,
radius, ray angle, ray length, and attachment relationship. Use native fountain
transparency where X7 preserves vector output; otherwise use a denser bounded
vector blend with no visible outer ring.

### 7. Margin, color, and gradient inaccuracies

- V1 assumed a 5.6 mm margin instead of measuring the rectified print area.
- Background colors were sampled conceptually rather than from controlled parts
  of the image.
- Camera glare, perspective, and print lighting were not separated from intended
  artwork gradients.
- Metallic gold in V1 is a generic fountain fill and does not match the source's
  highlight bands.

**V2 decision:** derive geometry from the rectified page, then sample multiple
low-glare regions. Treat color as approximate where the photograph cannot prove
the original print value, but match relative warm/cool and light/dark structure.

### 8. Validation design — process failure

- V1 declared PASS for exact page size, zero bitmaps, and editable text.
- It did not compare the rendered result to the reference.
- It did not detect out-of-page geometry.
- It did not measure plaque, Arabic, pattern, text, or flare alignment.

**V2 decision:** separate `vector_integrity` from `visual_fidelity`. Both must
pass before V2 is called complete.

## V2 implementation sequence

### Implementation status — 2026-11-02

The non-guessing Phase 0/1 foundation is now implemented:

- `corel_operator/reference_recreation.py` performs bounded image preflight,
  SHA-256 source identity, EXIF normalization, explicit rotation, corner
  validation, perspective rectification, and physical A4 calibration.
- The measurement record contains reversible transforms between rotated source
  pixels, rectified pixels, Corel millimetres, and Corel inches. Rectified output
  uses an exact integer `99:70` A4 ratio.
- Optional measured inner-field corners produce per-edge white-margin widths in
  millimetres. Uncertain regions remain explicit data rather than guessed art.
- `scripts/prepare_alhamdulillah_v2_reference.py` creates a unique reference-only
  workspace, copies rather than moves the source, and refuses existing output
  directories. It never opens or modifies a V1 CDR.
- `tests/test_reference_recreation.py` covers transform accuracy, invalid corner
  rejection, A4 ratio, inner-margin measurement, rotation/rectification, source
  preservation, staged workspace output, and overwrite refusal.

The supplied photograph has since been materialized locally and retained by
SHA-256 identity in a calibrated V2 workspace. Structural artifacts now exist,
but they remain intermediate Phase 2 work and are not a visually approved V2
recreation.

First create the corner-marking workspace:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_alhamdulillah_v2_reference.py `
  --source "C:\path\to\original-photo.jpg"
```

Measure the paper and inner-field corners in the generated
`reference_rotated_for_corner_marking.png`, fill
`corner_measurements.template.json`, and rerun into another new workspace:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_alhamdulillah_v2_reference.py `
  --source "C:\path\to\original-photo.jpg" `
  --corner-measurements "C:\path\to\completed-corners.json"
```

Only after `status` is `PHASE_1_RECTIFIED_AND_CALIBRATED` may structural tracing
begin. The rectified PNG remains analysis-only and must never be placed on a
printable layer.

### Phase 2 gate status — 2026-11-02

`PASS_PHASE2_STRUCTURE` proves clipping, printable-bitmap exclusion, PDF vector
integrity, reference-layer isolation, and top-level page containment only. The
independent validator is:

```powershell
.\.venv\Scripts\python.exe scripts\validate_alhamdulillah_v2_phase2.py `
  --workspace output\alhamdulillah_a4_vector_v2_recovered_20261102
```

It compares the retained preview directly with the rectified reference and
binds its report to the exact input bytes with SHA-256 fingerprints. The current
recovered run is `PASS_PHASE2_GATE`: field error is 0.1902 mm, plaque IoU is
0.986893, and tolerant trellis F1 is 0.904986. Its rectified-reference SHA-256
is the same `5c7bbccf...a9884` used by the earlier passing run. The calibrated
corner record is now durable in
`config/alhamdulillah-v2-corner-measurements.json`, so ignored output cleanup no
longer destroys the measurements needed to reproduce this gate.

### Phase 3 automated status — 2026-11-02

`scripts/prepare_alhamdulillah_v2_arabic_mask.py` reproducibly extracts the
warm/bright calligraphy candidate only inside the passing plaque geometry. The
analysis mask is never imported as printable artwork. The retained trace run
`phase3_arabic_recovered_trace02` contains 22 native CorelDRAW curve components,
zero visible text objects, zero printable bitmaps, and a vector PDF with no image
objects. Full-render differencing against the retained Phase 2 preview gives a
strict silhouette IoU of 0.960760, and the Phase 2 source CDR hash is unchanged.

The result is `PASS_PHASE3_AUTOMATED_GATE_REVIEW_REQUIRED`, not final Phase 3
approval. A person must still review the full overlay, confirm the visible
reading `الحمد لله`, and reject any retained glare or detached pattern fragment
before Phase 4 typography is authorized.

### Phase 0 — preserve and prepare

1. Keep V1 unchanged.
2. Create a unique V2 output directory and CDR.
3. Save the supplied photo locally as a reference-only asset if the client can
   materialize it; never embed it in final printable layers.
4. Add a hidden, locked, nonprinting `00 - Reference` layer only during tracing.

**Exit gate:** V1 is untouched and the reference layer cannot print/export.

### Phase 1 — rectify and calibrate the photograph

1. Rotate the photo 90 degrees counter-clockwise into readable landscape form.
2. Detect the four paper corners and apply a perspective transform.
3. Normalize the transformed canvas to the exact A4 ratio, 297:210.
4. Separately record page edge, inner printed-field edge, and white-margin width.
5. Store a pixel-to-Corel coordinate transform in a V2 measurement JSON file.
6. Mark uncertain areas caused by glare, blur, or occlusion rather than guessing.

**Exit gate:** all later object coordinates come from one documented transform,
not visual estimates.

### Phase 2 — trace structural geometry

1. Create the exact A4 page and measured white margin.
2. Trace the plaque perimeter from the rectified silhouette.
3. Trace one exact trellis repeat from the clearest available region.
4. Duplicate at measured pitch and offset.
5. PowerClip or geometrically intersect the trellis with the printed field.
6. Add an explicit bounds check for every top-level printable object and every
   un-clipped child object.

**Exit gate:** no visible curve exists outside the page; plaque and pattern edge
overlays align with the reference before typography is added.

### Phase 3 — rebuild the Arabic faithfully

1. Isolate the reference calligraphy silhouette after perspective correction.
2. Trace the main connected strokes manually with a low-node Bezier strategy.
3. Trace each detached mark and diacritic as its own named curve.
4. Verify the visible reading and placement of `الحمد لله` against the source.
5. Group objects by main word, secondary word, diacritics, shadows, and highlights.
6. Apply gold fills and shadows using duplicates or clipped highlight curves,
   without changing the traced outer silhouette.
7. Keep optional hidden Unicode text on the nonprinting reference layer.

**Exit gate:** the calligraphy silhouette, major negative spaces, diacritics, and
stroke terminals align in a 50% opacity overlay. Font substitution is not used
for visible Arabic.

### Phase 4 — match English typography

1. Measure target word bounds, baseline, cap height, and average stroke weight.
2. Render likely installed serif candidates at the target size.
3. Compare outlines for the distinctive `A`, `h`, `m`, `u`, and final `h`.
4. Adjust tracking only after the glyph style is selected.
5. If no font is close enough, convert a traced visible copy to curves while
   retaining hidden editable source text.
6. Rebuild the metallic fill and restrained shadow from measured source offsets.

**Exit gate:** word silhouette and baseline match the rectified reference; the
shadow cannot extend beyond its measured offset.

### Phase 5 — rebuild all light effects

1. Create a manifest for each orb and starburst with normalized coordinates.
2. Distinguish background orbs, stroke-tip glows, and independent star flares.
3. Use radial fountain transparency or a validated vector blend for soft halos.
4. Build rays as tapered Bezier shapes with measured angles and lengths.
5. Match z-order so attached glows sit on their corresponding calligraphic tips.

**Exit gate:** light centers are within 1.5 mm of measured positions and no
concentric band edge is visible at normal print zoom.

### Phase 6 — measured correction loop

1. Export a fixed-size local preview of the CDR.
2. Align it with the perspective-corrected reference.
3. Produce local-only overlay, edge-difference, and region-mask comparisons.
4. Correct only the failing objects; do not rebuild successful layers.
5. Run at most three measured correction passes, retaining each report.

Suggested measurements:

- Page and inner-field bounds: within 0.5 mm.
- Plaque silhouette intersection-over-union: at least 0.97.
- Arabic silhouette intersection-over-union: at least 0.93, plus manual review.
- English bounds and baseline: within 1 mm.
- Pattern pitch and row offset: within 0.5 mm.
- Principal flare centers: within 1.5 mm.
- No printable object bounds outside the page.

### Phase 7 — final production audit

1. Confirm 297 x 210 mm landscape.
2. Confirm semantic layer order and named object groups.
3. Confirm zero embedded bitmap artwork.
4. Confirm no printable reference layer.
5. Confirm no off-page printable objects.
6. Confirm Arabic visible artwork is editable curves and grouped logically.
7. Confirm PDF contains no unexpected raster image objects.
8. Save CDR, vector PDF, preview, measurement JSON, and fidelity report.

## Planned V2 layer structure

1. `00 - Reference - NONPRINTING` (hidden/locked before final save)
2. `01 - Background and Margin`
3. `02 - Trellis PowerClip`
4. `03 - Traced Plaque`
5. `04 - Arabic Calligraphy Curves`
6. `05 - English Typography`
7. `06 - Vector Light Effects`

## Definition of V2 completion

V2 is complete only when:

- The visible Arabic is traced from the supplied composition rather than
  substituted with a font.
- The trellis is truly clipped and no outlines appear outside the page.
- Structural overlays show the plaque, pattern, typography, and flare positions
  align with the rectified reference within the stated tolerances.
- The CDR remains a layered, editable vector document with no imported bitmap
  used as printable artwork.
- The final report distinguishes measured matches from color/font details that
  remain uncertain because the source is a perspective photograph.
