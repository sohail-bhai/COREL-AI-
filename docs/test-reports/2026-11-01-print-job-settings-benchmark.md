# Print Job Settings Benchmark

**Date:** 2026-11-01  
**Benchmark:** `print-job-settings-v1`  
**CorelDRAW:** Version 17.0.0.491  
**Verdict:** **CONDITIONAL — live workflow passed; poster PDF is not press-ready**  
**Combined score:** **85/100**

## Scope

The requirements were fixed before execution in
[`benchmarks/print_job_settings.json`](../../benchmarks/print_job_settings.json). The test had two
independent parts:

1. Audit the generated Future Forms poster PDF for basic commercial-print metadata.
2. Exercise the live print-job planner and CorelDRAW placement workflow with a disposable 300-DPI
   CMYK, bleed-inclusive raster fixture.

The PDF inspection is a bounded token and page-box audit, not a standards-complete PDF/X preflight.

## Poster PDF production audit — 15/30

| Requirement | Actual | Result |
|---|---|:---:|
| A4 trim dimensions | 8.27 × 11.69 in | Pass |
| Explicit TrimBox | 8.27 × 11.69 in | Pass |
| BleedBox | Not present | **Fail** |
| Managed/CMYK output | `/DeviceRGB` present; no `/DeviceCMYK` | **Fail** |
| Output intent | Not present | **Fail** |
| Embedded-font evidence | Two `/FontFile` tokens | Pass* |

\*Token evidence does not prove that every used glyph and font is correctly embedded.

The poster is suitable as a correctly sized RGB review PDF or for a non-bleed office print. It must
not be sent to a commercial press as a certified full-bleed file without additional production work.

## Live print-job settings

| Setting | Expected | Actual | Result |
|---|---:|---:|:---:|
| Artwork | CMYK TIFF, 1125 × 675 px | CMYK TIFF, 1125 × 675 px | Pass |
| Effective resolution | At least 300 DPI | 300 DPI | Pass |
| Finished size | 3.5 × 2.0 in | 3.5 × 2.0 in | Pass |
| Bleed | 0.125 in per edge | 0.125 in | Pass |
| Placed size | 3.75 × 2.25 in | 3.75 × 2.25 in | Pass |
| Safe margin | 0.125 in | 0.125 in | Pass |
| Safe size | 3.25 × 1.75 in | 3.25 × 1.75 in, rotated as needed | Pass |
| Sheet | 12 × 18 in portrait | 12 × 18 in portrait | Pass |
| Base margin | 0.25 in | 0.25 in | Pass |
| Mark clearance | 0.125 in | 0.125 in | Pass |
| Bottom gripper | 0.375 in | 0.375 in | Pass |
| Effective L/T/R/B margins | 0.375 / 0.375 / 0.375 / 0.750 in | Exact match | Pass |
| Gutter | 0.125 in | 0.125 in | Pass |
| Layout | Best-fit mixed rotation | Mixed rotated columns | Pass |
| Capacity | 19 per sheet | 19 per sheet | Pass |
| Live placements | 19 | 19, all bounds verified | Pass |
| Exported PDF page | 12 × 18 in | 12 × 18 in | Pass |

The visual sheet contains one seven-item upright column and three four-item rotated columns, for 19
copies total. The layout is guillotine-friendly but has moderate cutting complexity.

### Quantity result

- Requested production quantity: **250**
- Capacity: **19 per sheet**
- Sheets required: **14**
- Total produced: **266**
- Overage: **16**
- Usable-area waste: **15.556%**
- Whole-sheet paper waste: **25.781%**

The planner correctly rejected 250 as a one-sheet execution request while still returning complete
multi-sheet production math. A separate 19-copy plan was then executed for one verified sheet.

### Efficiency versus finishing tradeoff

The selected 19-up mixed layout is more material-efficient. The planner also reported a 16-up
all-rotated grid with simpler cutting but higher whole-sheet paper waste (**37.5%**). A production
operator should choose between these based on finishing cost, not capacity alone.

## Honest limitations detected

The live workflow scored **70/70** because it both executed correctly and reported its limitations:

- The CMYK fixture has no embedded ICC profile.
- Mark clearance is reserved, but crop and registration marks are not drawn.
- No output profile or conversion policy is applied.
- The PDF export preset is not controlled or certified.
- `prepare_print_job` correctly returned `print_ready: false`.

The imposed PDF is CMYK and exactly 12 × 18 inches, but it still has no output intent or generated
print marks. Successful placement/export therefore does not make it a press-certified PDF.

## Recommended production settings for the poster

1. Add the printer's requested bleed—commonly 3 mm or 0.125 in—and extend the navy background and
   right coral rail fully through that bleed.
2. Convert using the printer's specified CMYK ICC profile; do not use an arbitrary generic CMYK
   conversion when accurate coral/aqua reproduction matters.
3. Export with an agreed PDF/X preset, normally PDF/X-4 unless the printer requests another
   standard, with an OutputIntent.
4. Include bleed and printer-requested crop/registration marks.
5. Run an external PDF preflight for page boxes, font embedding, image resolution, transparency,
   overprint, rich-black limits, and total ink coverage.
6. Obtain a contract or calibrated proof because the design relies on saturated coral and aqua.

## Artifacts

- Settings specification: [`benchmarks/print_job_settings.json`](../../benchmarks/print_job_settings.json)
- Reusable runner: [`scripts/run_print_job_settings_benchmark.py`](../../scripts/run_print_job_settings_benchmark.py)
- CMYK fixture: `output/print_settings_benchmark_20261101_203433/cmyk_bleed_fixture_300dpi.tif`
- Editable imposed CDR: `output/print_settings_benchmark_20261101_203433/imposed_12x18.cdr`
- Imposed PDF: `output/print_settings_benchmark_20261101_203433/imposed_12x18.pdf`
- Complete checks and trace: `output/print_settings_benchmark_20261101_203433/benchmark_result.json`

Reproduce with:

```powershell
.\.venv\Scripts\python.exe scripts\run_print_job_settings_benchmark.py
```
