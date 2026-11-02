# Future Forms Poster — Design Quality Benchmark

**Date:** 2026-11-01  
**Benchmark:** `future-forms-poster-v1`  
**CorelDRAW:** Version 17.0.0.491 (`CorelDRAW.Application.17`)  
**Final result:** **PASS — 96/100**

## Test setup

The task, desired composition, hard gates, and scoring weights were fixed before the live run in
[`benchmarks/future_forms_poster.json`](../../benchmarks/future_forms_poster.json). The accepted run
created a new disposable A4 document and did not bind to pre-existing artwork.

The brief requested an original, vector-only A4 conference poster with editable typography, a
four-color identity, strong typographic hierarchy, an asymmetric orbital composition, systematic
spacing, named production groups, and CDR/PDF deliverables.

## Desired output versus obtained output

| Criterion | Desired | Obtained | Result |
|---|---:|---:|:---:|
| Canvas | 8.27 × 11.69 in | 8.27 × 11.69 in | Pass |
| Construction | Native vectors and editable text | 58 native planned elements plus direct vector/text operations; no artwork import | Pass |
| Required copy | 15 exact strings | 15/15 exact strings confirmed by object readback | Pass |
| Palette samples | Midnight, cream, coral, aqua | 4/4 exact RGB samples confirmed | Pass |
| Named groups | 5 required | 5/5 present | Pass |
| Plan complexity | At least 50 elements | 58 elements | Pass |
| Tool breadth | At least 15 operation types | 24 operation types | Pass |
| Failed calls in accepted run | 0 | 0 across 52 recorded calls | Pass |
| CDR output | Present and non-empty | 2,286,942 bytes | Pass |
| PDF output | Present and non-empty | 17,511 bytes | Pass |

The accepted run recorded approximately 57.1 seconds of cumulative tool execution. It exercised
connection/status, document creation and targeting, plan validation/preview/execution, primitive
creation, styling, text editing, renaming, moving, resizing, duplication, object/page alignment,
grouping, inspection/readback, CDR save, and PDF export.

## Scoring

| Category | Score | Notes |
|---|---:|---|
| Document and artifacts | 15/15 | Correct page and both deliverables were verified. |
| Content fidelity | 20/20 | Copy, palette samples, groups, and element-count target matched. |
| Tool execution and readback | 25/25 | Broad operation use, no accepted-run failures, and post-operation readback. |
| Visual hierarchy | 9/10 | `FORMS` is dominant, `FUTURE` is secondary, and the orbit is a clear visual anchor. |
| Layout and balance | 9/10 | Strong asymmetry and negative space; the orbital rule finishes very close to the coral rail. |
| System consistency | 8/8 | Palette, dots, rings, rails, rules, and spacing form one coherent visual system. |
| Legibility | 6/7 | Required copy is readable, but `EDITION` is cramped and micro-copy needs a print-size proof. |
| Originality and polish | 4/5 | Convincing contemporary identity with minor opportunities for bespoke typography/refinement. |
| **Total** | **96/100** | **Pass (threshold: 80)** |

## Visual comparison

The PDF matches the intended composition: metadata at the top, oversized title at upper-left,
edition badge at upper-right, an orbital focal system in the lower-right, a dot matrix and event
information balancing the lower-left, and a restrained footer. There is no accidental clipping,
missing text, default black outline, or major collision.

Three non-blocking refinements remain:

1. Give the `EDITION` caption more breathing room beneath `26`.
2. Print-proof the 7–8.5 pt metadata and coordinate labels at actual A4 size.
3. Add a slightly larger gap between the long cream orbital rule and the coral right rail.

## Defect discovered during the first attempt

Before the accepted run, a valid design plan failed in `preview_design_plan` with
`KeyError: 'red'`. The design-plan schema permits an outline containing only `width_points` and
declares default RGB values, but preview accesses `red`, `green`, and `blue` directly before those
defaults are materialized. The benchmark runner now supplies explicit zero RGB values as a local
compatibility workaround. Production bridge code was not changed, so this remains a separate tool
contract defect to fix and regression-test.

## Artifacts and reproduction

- Editable CDR: `output/future_forms_benchmark_20261101_200848/future_forms_2026.cdr`
- Review PDF: `output/future_forms_benchmark_20261101_200848/future_forms_2026.pdf`
- Full checks and tool trace: `output/future_forms_benchmark_20261101_200848/benchmark_result.json`
- Initial preview failure: `output/future_forms_benchmark_20261101_200827/benchmark_result.json`
- Benchmark runner: [`scripts/run_design_quality_benchmark.py`](../../scripts/run_design_quality_benchmark.py)

Run again with:

```powershell
.\.venv\Scripts\python.exe scripts\run_design_quality_benchmark.py
```

This score establishes successful tool use and a strong PDF design result. It does not establish
press readiness; fonts, color management, output intent, and physical print quality were not tested.
