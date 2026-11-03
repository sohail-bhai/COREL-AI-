# Contour-offset offline verification — 2026-11-03

Status: `implemented_unverified`. No live CorelDRAW connection or mutation ran.

- Focused suite: `python -m unittest discover -s tests -p test_contour_offsets.py -q`;
  37 passed.
- Full suite: `python -m unittest discover -s tests -q`; 675 tests,
  650 passed, 25 guarded live tests skipped.
- Catalog: 77 registered tools, 79 records/matrix rows, 295 native members,
  209 checked schemas, 237 examples, 28 enum groups and 62 adapter capabilities.
- Deferred coverage: 77 tools, zero missing explicit native gates.
- Installed X7 inspection: 47 descriptors and five enum groups,
  `connection_attempted: false`.

Checks cover inside/outside bounds and native controls; RGB/CMYK output;
primitive copy conversion; source line/cubic/compound geometry, gradient and
transparency; nested groups and verified replacement containers; signed editable
outputs; explicit fully/partially collapsed inside results; and redacted errors.
Controller effect bounds can change temporarily while its underlying geometry
remains unchanged. All generated curve identities/nodes/handles survive
separation and ungrouping.

Native mismatches, mutable aliases, foreign descendants, unknown roots,
stray page/layer objects, source changes and failed cleanup prevent success.
Known effects created before a throw can be recovered from owned-controller
metadata and safely discarded. Unknown ownership remains quarantined; geometry
inspection survives. No automatic undo or production readiness is claimed.

Readable X7 contour help establishes the workflow requirement. Three SDK pages
returned HTTP 200 without readable API content; the alternate help path was
unavailable. See [../CONTOUR_OFFSETS.md](../CONTOUR_OFFSETS.md).

Prepared gate: `CorelDisposableDocumentLiveTests.test_contour_offsets_live`.
Disposable rectangle, ellipse, cubic and compound fixtures save native readback,
CDR and PDF artifacts. Exact native lifecycle/distance, hole winding, miter
semantics, rendered appearance and cutting/print approval remain deferred.
