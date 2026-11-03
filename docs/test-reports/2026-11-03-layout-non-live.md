# Layout transforms: automated implementation evidence

Date: 2026-11-03. Target: CorelDRAW X7 17.0.0.491.
Status: `implemented_unverified`; all live verification remains deferred.

Implemented five MCP tools: `get_object_transform`, `rotate_object`,
`flip_object`, `order_object`, and `distribute_objects`.

Validation:

- Default suite: 424 tests run; 411 automated checks passed, 13 live gates skipped.
- Focused layout: 24 tests passed.
- Catalog: 55 registered tools, 57 records, 149 API inventory members,
  171 examples, 40 adapter capabilities, 16 enum groups; strict schemas pass.
- Static diagnostics passed with `connection_attempted: false`.
- Git whitespace checks passed.

Checks cover finite native transform metadata, measured/external pivots, absolute
and wrapped angles, actual bounds after rotation, mirror axes/round trips and
small-matrix parity, native sibling relations with deliberately opaque ZOrder,
nested group scope, ambiguous/incomplete stacking, actual equal-gap/explicit-gap
and vertical equal-center distribution, rotated bounds, protruding middle objects,
projected overlap, unchanged orthogonal geometry, independent target preflight,
duplicate/ancestor targets, stale/reordered/foreign-page references, partial
worker quarantine, strict result/request schemas, and invalid options.

The installed library was read through a foreground inspector without connecting
to CorelDRAW. X7 RotateEx and AbsoluteHScale documentation and X7.4 Flip
documentation informed the contracts. Exact X7 matrix/order pages were partly
inaccessible; their signatures are type-library confirmed, not runtime verified.

The prepared `test_layout_transforms_live` has not run. Native matrix conventions,
mirror axes/rendering, explicit pivots, nested stacking and distribution bounds
must pass that gate and artifact review before a verified status is justified.
Layer/page organization, guides and outline-aware/safe-area reflow remain gaps.
