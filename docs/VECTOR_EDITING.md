# General editable vectors and shaping

Implemented on 2026-11-03. Native execution, visual/winding review and MCP-client
verification remain deferred to the consolidated campaign.

Six tools add general graphics to the common editing and production foundations:

- `create_vector_path`: editable open/closed subpaths with straight lines and
  Cartesian cubic controls. A missing closing line is normalized into the plan.
  All supported native points/handles/counts are read back before acceptance.
- `get_curve_geometry`: complete native topology, positions, cusp/smooth/
  symmetrical types, controls, bounds and a source-bound geometry fingerprint.
  Rectangles, ellipses and polygons use their read-only `DisplayCurve` geometry;
  this inspection does not convert original primitives.
- `edit_curve_geometry`: complete preflight for node positions and cubic handles.
  It requires the current fingerprint and exact target. Moving a node can
  translate attached handles or retain their absolute positions. Incompatible
  smooth/symmetrical constraints fail before editing; cusp conversion is explicit.
- `boolean_shapes`: weld, source-from-target trim and intersection through owned
  copies. Empty trim/intersection is explicit. Originals retain their native types.
- `combine_vector_shapes`: compound curves from 2-64 copied exact inputs, with
  complete subpath geometry reconciliation.
- `break_apart_curve`: independent copied subpaths matched to original geometry
  and named deterministically despite native output-order differences.

## Contracts and safeguards

All coordinates are document inches. Paths require `start`, `segments`, `closed`;
segments require `type`, `end`, and cubic `control1`/`control2`. Native data is
ordinary JSON, with signed object references and a whole-geometry SHA-256.
Native node indices are temporary locators protected by that current fingerprint.

Limits: 64 subpaths, 1000 total segments including closing lines, 2000 nodes,
200 node/handle edit entries, 64 derivative outputs and 10000 root objects during
ownership inspection. Unknown/mixed individual node/segment types, inconsistent
ownership/connectivity/counts and unavailable required APIs fail explicitly.

Shaping requires distinct exact root objects on one page/layer. It reads native
display geometry before copying, converts only owned copies, rejects shared
curve data and checks copied geometry/appearance. Source and original root
membership/order are rechecked after work. Cleanup deletes only established
owned outputs; unknown outputs or failed cleanup leave recovery required.

The preservation scope is explicit: original root membership/relative order,
measured input geometry and basic appearance. This is not a complete native file
or complex-effect diff. Compound/split geometry may have native traversal/order
differences. Equivalent segment geometry does not prove fill winding, output
appearance or visual fidelity. The output inherits native defaults/first input
appearance; inspect and style it using appearance tools.

Node edits intentionally modify their exact target. Required APIs and the full
target geometry are checked before writes; the whole curve and basic appearance
are checked afterwards. There is no automatic undo for these existing-object
edits. Any unverified partial mutation quarantines further writes through the
exact-operation recovery protocol. Source-preserving derivatives have verified
owned-output cleanup instead.

Native closure behavior, closed cubic endpoints, primitive display-curve owner
identity and shaping semantics are included in the prepared native gate. They
remain unverified rather than being inferred from mock COM behavior.

## Evidence and remaining work

Installed X7 evidence: `x7_vector_api_evidence.json` records 226 descriptors and
three enum groups without connecting to CorelDRAW. Thirty-three focused non-live
checks cover topology, exact handles/bounds, fingerprints, smooth constraints,
primitive preservation, native copy aliases, cleanup, source corruption, unknown
outputs, relative order, combined/split geometry and strict result schemas.

The disposable gate is
`CorelDisposableDocumentLiveTests.test_vector_editing_and_shaping_live`. It creates
its own CDR/PDF fixtures and is not run during implementation.

Source-preserving node insertion/explicit deletion is implemented separately in
[VECTOR_TOPOLOGY.md](VECTOR_TOPOLOGY.md). Adjacent deletion/fitting, open endpoint
cropping, generic conversion/nested shaping, offsets and broader appearance/clipping
remain in the backlog.

Primary references:

- [X7 read-only display curves](https://community.coreldraw.com/sdk/api/draw/17/p/shape.displaycurve?lang=cli)
- [X7.4 weld flags](https://community.coreldraw.com/sdk/api/draw/17.4/m/shape.weld?lang=vb)
- [Corel trim behavior](https://community.coreldraw.com/sdk/api/draw/25/m/shape.trim?lang=cli)
- [Corel intersection behavior](https://community.coreldraw.com/sdk/api/draw/26/m/shape.intersect?lang=cli)
- [Corel closure semantics](https://community.coreldraw.com/sdk/api/draw/27/p/subpath.closed?lang=vba)

Newer pages establish behavior expectations. The retained installed X7 signatures
establish version compatibility. The base X7 `AppendCurveSegment2` page was
inaccessible through the search tool; its Cartesian argument ordering is confirmed
by the local X7 descriptor, not by a retrieved web page.
