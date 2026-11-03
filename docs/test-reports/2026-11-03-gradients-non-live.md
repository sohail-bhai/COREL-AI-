# Gradient offline verification — 2026-11-03

Status: `implemented_unverified`. No live CorelDRAW connection or mutation ran.

- Focused suite: `python -m unittest discover -s tests -p test_gradients.py -q`;
  30 passed.
- Full default suite: `python -m unittest discover -s tests -q`; 637 tests,
  613 passed, 24 guarded live tests skipped.
- Catalog: 76 registered tools, 78 records/matrix rows, 274 native members,
  206 checked schemas, 234 examples, 24 enum groups and 61 adapter capabilities.
- Deferred coverage: 76 tools, zero missing explicit native gates.
- Installed X7 inspection: 103 descriptors, three enums,
  `connection_attempted: false`.

Offline checks cover RGB/CMYK components and ordered interior stops; native
type/angle/center/padding/steps; direct/opaque/smoothing controls; guarded revisions;
whole-story/unlinked text and complete vector/outline/transparency preservation.
Oversized collections, missing components/getters, ignored controls/additions,
shared color factories, late stop loss, source changes and partial native errors
cannot report success. Failed assignments quarantine writes while inspection
remains available; no automatic undo is claimed.

X7's fountain-fill help returned readable workflow descriptions. Three SDK pages
returned HTTP 200 without readable API content, so they do not establish COM
semantics. See [../GRADIENTS.md](../GRADIENTS.md) and its retained evidence.

Prepared gate: `CorelDisposableDocumentLiveTests.test_gradient_fills_live`.
It creates four type fixtures, RGB/CMYK stops, artistic/paragraph text, guarded
revisions and CDR/PDF/readback artifacts. Native stop/endpoints and coordinates,
rendered interpolation, ICC/separation accuracy and MCP-client/manual review
remain deferred.
