# Common layout transforms

Status: `implemented_unverified`. All X7 runtime/visual checks are deferred.
The installed type library confirms the transform/order signatures and mirror
axes. [Inspector](../scripts/inspect_x7_layout_api.py) and
[recorded evidence](x7_layout_api_evidence.json) use no application connection.

- `get_object_transform` reads a finite six-value native affine matrix, rotation
  normalized to 0-360 degrees, bounds in document ruler inches and an opaque
  native ZOrder value. Units and bottom-left reference point are restored.
- `rotate_object(angle_degrees, relative=True, center_x_inches=None,
  center_y_inches=None, ...)` uses X7 RotateEx. The default pivot is the measured
  bounds center. Both explicit coordinates are required together. Absolute mode
  computes a delta from native RotationAngle; relative mode applies the supplied
  delta. Requested angles are bounded to +/-36000 degrees. Actual angle and
  finite matrix/bounds are returned; angle discrepancies fail.
- `flip_object(axis, ...)` uses the installed horizontal/vertical/both enum values
  (1/2/3). Readback checks native matrix determinant magnitude and sign; both axes
  also require the linear coefficients to reverse. Zero/numerically unstable
  transforms are refused. This parity check supports native transformation
  evidence; native axis conventions and rendering still need the prepared gate.
- `order_object(position, ...)` supports front/back/forward_one/back_one. Its scope
  is the immediate sibling layer or parent group, bounded to 10000 entries.
  Complete native OrderIsInFrontOf relations establish the rank from front;
  raw ZOrder direction is not assumed. After editing, sibling membership, scope
  and the expected rank must match. Nested group semantics remain unverified.
- `distribute_objects(axis, object_names=None, object_references=None,
  mode="equal_gaps", spacing_inches=None, allow_overlap=False)` handles 3-100
  independent objects. Supply exactly one list of unique names or signed
  references. Targets sort by current position. Equal gaps preserve the outer
  extent; a supplied gap anchors at the minimum coordinate. Equal centers
  preserve the first/last centers. Explicit gaps are -200 to 200 inches and
  apply to equal_gaps mode. Orthogonal coordinates and sizes stay fixed.

Distribution checks every exact session identity before moving anything and
immediately before each SetPosition. Duplicate identities and a selected group
alongside its descendant are refused. Every actual result must match planned
bounds within 0.001 inch. The `has_axis_overlap` flag describes projected intervals
on the chosen axis; it does not incorporate orthogonal separation. Projected
overlap requires explicit `allow_overlap=True`. These are geometric bounds;
outline expansion, guides and print collision policy remain separate work.

All tools accept the existing strict selectors; mutation with a signed reference
requires its page explicitly active. Inspection may read other pages without
activation. Reordering preserves native identity, so signed references remain
valid when names/group membership/document lifetime remain valid.

Mutations use [worker recovery](WORKER_RECOVERY.md). Late outcomes, uncertain
native readback, or partial multi-object edits block follow-up mutations until
exact-ID reconciliation. There is no automatic replay or generic rollback.
Temporary measurement context writes also count as native edit stages; a later
preflight failure can conservatively require reconciliation even when geometry
was not edited. Failed unit/reference restoration is never hidden.

## Evidence and deferred verification

[X7 RotateEx documentation](https://community.coreldraw.com/sdk/api/draw/17/m/shape.rotateex)
confirms explicit pivot coordinates and degree angles. The X7
[AbsoluteHScale page](https://community.coreldraw.com/sdk/api/draw/17/p/shape.absolutehscale)
describes accumulated stretching; it is not used as a mirror verdict.
[X7.4 Flip documentation](https://community.coreldraw.com/sdk/api/draw/17.4/m/shape.flip?lang=cli)
corroborates the mirror behavior. Build-17 signatures and constants come from
the installed library. Some exact X7 order/matrix pages were inaccessible;
member existence alone does not prove their runtime semantics.

`test_layout_transforms_live` creates its own asymmetric rectangles, measures
rotation/pivots and native mirror axes, checks mirror round trips and stacking,
distributes on both axes, checks nested sibling order and ancestor refusal,
records readback and saves only owned artwork. Cleanup errors fail the gate.
It remains skipped until both existing live-test environment gates are enabled.

Remaining layout work: editable/visible layers and page organization, guides,
shape/skew/path-specific transforms, outline-aware layouts, safe-area fitting,
and template/job reflow. The next coherent workflow is reusable fields and
deterministic data batches using the typography and geometry foundations.
