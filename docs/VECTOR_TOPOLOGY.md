# Source-preserving node topology revisions

`revise_curve_topology` inserts and deletes nodes on an independent editable
curve, preserving the fingerprinted source. Native verification remains deferred.
It accepts an exact signed root reference and the current `get_curve_geometry`
fingerprint, plus 1-200 total insertion/deletion entries.

Insertions require `subpath_index`, `segment_index`, and `t` in
`[0.000001, 0.999999]`. Indices and parameters always refer to the original
inspected geometry. Entries on one segment are sorted before subdivision.
Line interpolation and cubic de Casteljau subdivision retain the original
geometric locus. Parameter `t` is not a fraction of native arc length.

Deletions require `subpath_index`, `node_index`, and an explicit `replacement`:
`{"type":"line"}` or `{"type":"cubic","control1":{"x":1,"y":2},"control2":{"x":2,"y":3}}`.
The start/end are the retained neighbours. This explicitly changes geometry;
automatic curve fitting is separate work. Removing the first closed node rotates
the traversal start without reversing it. Adjacent removals, open endpoint
cropping, and insertion on either segment replaced by a deletion are refused.
Closed line-only outputs need three nodes; curved closed outputs need two.

The complete preflight enforces coordinate/topology budgets and rejects collapsed
line segments. Duplicate parameters, stale fingerprints and conflicting edits
fail before native copies. Returned topology includes every retained-node mapping,
every inserted node's result index and removed source indices. Result indices
belong to the returned curve fingerprint, not the source fingerprint.

The wrapper duplicates the exact source, converts only owned primitives and
uses installed X7 `Curve.CopyAssign(Source)` to assign a newly constructed curve.
Outputs retain copied basic fill/outline and have explicitly cusp node types;
their tangent coordinates are checked, but smooth/symmetrical editing constraints
are not retained. Complete geometry/count/type/appearance readback and original
membership/order/signatures gate success. Failed work deletes only owned output;
unverified cleanup or source corruption requires exact-operation recovery.

Limits: 64 subpaths, 1000 final segments, 2000 nodes, 200 edit entries and existing
bounded root membership inspection. Nested revision inputs and complex effect
preservation remain unsupported. The source file/artwork is preserved; this is
not a full native effect or rendered-appearance comparison.

Installed `docs/x7_vector_api_evidence.json` includes `Curve.CopyAssign`,
`Segment.AddNodeAt` and the required creation signatures, without connecting to
CorelDRAW. The current wrapper uses CopyAssign to avoid undocumented native
node-deletion reconnection semantics. Foreground primary-source requests to the
[CopyAssign](https://community.coreldraw.com/sdk/api/draw/17/m/curve.copyassign?lang=cli),
[AddNodeAt](https://community.coreldraw.com/sdk/api/draw/17/m/segment.addnodeat?lang=cli)
and [node deletion](https://community.coreldraw.com/sdk/api/draw/17/m/node.delete?lang=cli)
pages returned HTTP 200 without readable API content. These attempts are retained
in `vector_topology_online_evidence.json`; they are not documentation confirmation.

The non-live suite compares subdivided curves against independently evaluated
Bernstein polynomials across each interval, verifies exact midpoint controls,
source-index mappings, closed traversal, budgets, stale identity, primitive
preservation, native assignment failures, copied appearance, cleanup and worker
quarantine. The prepared disposable gate is
`CorelDisposableDocumentLiveTests.test_vector_topology_revision_live`. Native
CopyAssign coordinates for rotated shapes, closure/type behavior and complex
appearance remain unverified until that gate and manual CDR/PDF review pass.
