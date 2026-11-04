# Native bitmap properties and placed resolution

Status: `implemented_unverified`. Live CorelDRAW verification remains deferred.

`get_bitmap_properties` selects an exact bitmap by signed object reference or a
strict legacy name/index. It reports pixel dimensions, native X/Y resolution,
color mode code, embedded/linked flags, crop capability and crop-envelope state.
Missing or malformed properties remain explicit; the tool does not read pixels.

`minimum_dpi` ranges from 1 to 2400, defaulting to 150. The tool reads the native
uncropped `BoundingBoxPath` and the shape's affine matrix in document inches.
Exactly one closed four-line parallelogram is required for calculation, with
complete node/segment ownership and connectivity. Matrix column directions map
the two measured edges to pixel X/Y; matrix scale is not applied a second time
to already placed geometry. Rotation, reflection and nonuniform scale therefore
retain the correct pixel-axis extents instead of using axis-aligned bounds.

Pixel X/Y DPI is pixels divided by the corresponding placed edge length. The
minimum directional DPI is the reciprocal of the largest singular value of
the pixel-to-inch affine mapping. With skew, the worst directional value can
be lower than either axis DPI. For example, a 1200-by-600 image placed at 4-by-2
inches is 300 DPI; a unit horizontal shear produces about 185.41 DPI in its worst
direction even though its two pixel-axis DPI values exceed 200.

Native resolution metadata is returned separately and is not substituted for
placed-resolution calculation. For an unmodified crop envelope, the uncropped
box must reconcile with actual shape bounds. Modified crop bounds must remain
inside the uncropped grid. Cropping does not create new detail or reinterpret
the entire pixel count as belonging to the smaller visible region. Native
`Cropped` means crop capability; `CropEnvelopeModified` identifies a changed
envelope. Cropping, resampling and linked files still need native/manual review.

Pixel counts, crop state, placed bounds/matrix, uncropped corners and bitmap/group
effect scope must reconcile across two reads. Changed or unavailable readback
prevents a passing resolution result. Signed group ancestors are checked for
effects/clipping too. These checks detect observed state changes but are not an
atomic document lock or proof of unchanged pixel content.

Missing metadata, unclear axis mapping, unsupported native path topology,
degenerate/non-affine geometry, insufficient coordinate precision,
effect/clipping scope, crop/bounds discrepancies
and readback changes return `indeterminate`/`not_checked`, with explicit reasons.
Metadata axes are bounded to one million pixels each and 500 million total
pixels. Box coordinates are bounded to plus/minus one million inches. Four box
nodes/segments are read; source pixel memory is not allocated.
Temporary inch/reference changes must enter the requested context and restore
the original values exactly. Unverified context restoration raises a redacted
error. Inspection remains available when the worker quarantines later writes.

The returned current-session fingerprint includes recorded identity, native
metadata, geometry, resolution request/result and consistency state. It changes
after observed pixel counts, placement, metadata or thresholds change. It is
not a pixel-content hash or persistent/reopened document identity.

Installed evidence: [x7_bitmap_api_evidence.json](x7_bitmap_api_evidence.json)
contains 32 descriptors with `connection_attempted:false`. Readable X7
[bitmap dimension/resolution help](https://product.corel.com/help/CorelDRAW/540229932/Main/EN/Documentation/CorelDRAW-Changing-the-dimensions-and-resolution-of-bitmaps.html)
supports the workflow requirement. Three SDK requests returned HTTP 200 without
readable API documentation; access outcomes are retained in
[bitmap_online_evidence.json](bitmap_online_evidence.json).

Thirty-eight focused non-live tests cover analytic resolution, rotation, mirrors,
skew, crop handling, nested effect scope, unavailable metadata, stale identities,
readback changes, strict schemas, context restoration and worker classification.
The prepared `CorelDisposableDocumentLiveTests.test_bitmap_properties_live` gate
imports a synthetic image, measures size/rotation/mirror/scale and a transformed
group, and prepares JSON/CDR/PDF artifacts. Native crop/skew paths, nested/global
coordinate semantics and manual artifact review remain consolidated dependencies.

No source-detail, pixel-fidelity, visual-quality, ICC/spot/separation or printer
approval is inferred. General image preparation, document-wide raster preflight,
background cleanup, tracing and selective regeneration remain broader work.
