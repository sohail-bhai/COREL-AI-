# Bitmap inspection offline verification — 2026-11-04

Status: `implemented_unverified`. No live CorelDRAW connection or mutation ran.

- Focused suite: `python -m unittest discover -s tests -p test_bitmap_properties.py -q`;
  38 passed.
- Full suite: `python -m unittest discover -s tests -q`; 753 tests,
  726 passed, 27 guarded live tests skipped.
- Catalog: 85 tools, 87 records/matrix rows, 309 native members,
  232 schemas, 261 examples, 28 enum groups and 66 adapter capabilities.
- Deferred campaign: 85 tools, zero missing explicit native gates.
- Installed inspection: 32 descriptors, `connection_attempted:false`.

Analytic tests establish correct axis and minimum directional DPI for physical
size, arbitrary rotation, reflection, nonuniform scale, cyclic/reversed box
winding and skew. Already placed geometry is not scaled twice. A unit shear
shows both axis DPI values above 200 while worst directional DPI is 185.41.
Small non-affine boxes and insufficient coordinate precision are refused.

Native fakes cover independent metadata, cropped/uncropped bounds, four-line
box topology/ownership, nested effect/clipping scope, unknown properties, missing
or malformed pixel counts, degenerate geometry and redacted readback failures.
Two reads reconcile pixel counts/crop state/bounds/matrix/box/scope. Observed
changes prevent a resolution pass. Late document closure invalidates the target.
Unit/reference entry and exact restoration are checked; read-only inspection
remains available while later mutations are quarantined.

Source pixel content is not read, hashed or modified. Metadata/current-grid DPI
does not prove image detail, visual quality, ICC/spot/separation or printer
approval. Native crop/skew/group/global coordinate behavior remains unverified.

Readable X7 bitmap size/resolution help supports the requirement. Three SDK
requests returned HTTP 200 without readable API content. Their actual November 3
access dates are retained; this report records the November 4 implementation.
See [../BITMAP_INSPECTION.md](../BITMAP_INSPECTION.md).

Prepared gate: `CorelDisposableDocumentLiveTests.test_bitmap_properties_live`.
Synthetic PNG fixtures prepare scale/rotate/mirror/transformed-group native
readback plus CDR/PDF artifacts. Native and manual review remain deferred.
