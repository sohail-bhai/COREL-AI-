# Raster preparation offline verification — 2026-11-04

Status: `implemented_unverified`. No live CorelDRAW connection or mutation ran.
The user requested stopping after this iteration and continuing later.

- Focused suite: `python -m unittest discover -s tests -p test_raster_assets.py -q`;
  49 passed, zero skips.
- Full suite: `python -m unittest discover -s tests -q`; 802 tests,
  775 passed, 27 guarded live tests skipped.
- Catalog: 87 tools, 89 records/matrix rows, 309 native members,
  245 checked schemas, 267 examples, 28 enum groups, 68 adapter capabilities.
- Deferred campaign: 87 tools, zero missing explicit native gates; the two raster
  tools are `local_only` with MCP client verification still pending.
- Static diagnostics: bridge 0.6.0, schema 1, `connection_attempted:false`.
- Compileall and Git whitespace checks passed. Existing tool records, schema
  definitions and examples compare equal to the preceding committed registry.

Synthetic known-pixel tests cover the crop/rotation/flip order, all quarter
rotations and all eight EXIF orientations, contain/cover/stretch fitting,
explicit upscale refusal and reporting, PNG/TIFF RGB/RGBA/L/LA/CMYK round trips,
palette/bitonal/grayscale transparency and JPEG/BMP/GIF sources. ICC bytes and
recognized DPI remain preserved; axis swaps, quantization, absent TIFF resolution
tags and EXIF/text stripping are checked. Precision and multi-frame preparation,
implicit CMYK-to-PNG conversion and disguised unsupported decoders are refused.

Failure tests cover malformed requests, stale fingerprints, source changes,
missing sources and simulated alias retargeting with identical source bytes.
Destinations are never overwritten. Tests exercise hard-link and exclusive-copy
publication, racing destinations, staged pixel/DPI mismatches, replaced outputs
including identical bytes, unknown ownership receipts, failed stat/deletion and
temporary cleanup. A source deleted after publication is reported unverified;
only known owned output is removed. External source edits and unowned output
replacements remain preserved. These observations do not provide atomic locks.

Direct recorded MCP wrappers validate against strict output schemas and bypass
the native dispatcher. Local errors do not enter native recovery. Recorded events
contain operation IDs and outcome metadata without source paths, pixel hashes or
asset fingerprints. Strict schemas reject unexpected nested keys and false
source-preservation success fields.

Three primary Pillow references returned readable HTTP 200 content on
2026-11-04: EXIF transforms, resize/resampling and image-format metadata. The
bounded excerpts and actual access dates are retained in
[../raster_preparation_online_evidence.json](../raster_preparation_online_evidence.json).
See [../RASTER_PREPARATION.md](../RASTER_PREPARATION.md) for contracts and limits.

MCP client, prepared-image X7 import, transparency/color/placement and CDR/PDF
visual handoff remain deferred. No ICC conversion, added source detail, visual
fidelity, native crop/coordinate semantics or print readiness is established by
these offline checks. Document-wide raster preflight is the next implementation
iteration; broader background/cleanup, tracing and component AI work remain open.
