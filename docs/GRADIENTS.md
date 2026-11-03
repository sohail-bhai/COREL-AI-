# Bounded process-color gradients

`get_gradient_fill` and `set_gradient_fill` remain `implemented_unverified`.
All live verification is deferred to the consolidated campaign.

Inspection returns up to 32 ordered, endpoint-inclusive native color stops,
midpoints, blend codes and raw opacity metadata. Complete stop metadata requires
readable RGB/CMYK process components. It reads angle, steps, padding,
percent center offsets, spread, smoothing, anisotropy, transparency/merge,
acceleration and native coordinate/transform metadata. Missing or inconsistent
getters remain explicit and suppress the revision fingerprint. Opacity's native
byte units are not translated into a promised percentage. Native coordinate
interpretation still requires the later X7 gate.

Application accepts 2-32 strictly increasing integer-percent stops from 0 to 100,
all in one RGB or CMYK process model. It supports the installed linear, radial,
conical and square enum types, a finite angle, 0 automatic or 2-256 explicit
steps, 0-49 percent edge padding and center offsets within -50 to 50 percent.
Corel's X7 UI guide describes elliptical/rectangular fills; the native enum names
are radial/square. The wrapper requests symmetric fills with anisotropy disabled.

Native color factories must retain every exact process component before any
fill write. Creation supplies all ten parameters to `Fill.ApplyFountainFill`,
checks that the new collection has two endpoints, and adds interior stops.
Every segment uses a 50-percent midpoint and direct blend. Smoothing, pad spread,
normal merge, zero acceleration and opaque color stops are explicit. Native
`MakeOpaque` and `IsTransparent=false` must agree. Transparent gradient stops,
repeat/reflect spread, rainbow blending, arbitrary affine fill edits and spot/ICC
workflows remain separate work.

Targets are individual supported vectors or artistic/unlinked paragraph text,
with no outline or a readable ordinary process-color outline and no/readable uniform
transparency. Linked stories, enhanced outlines, mixed text formatting and other
effects are refused when required metadata cannot be reconciled. Existing gradient
revisions require the current inspection fingerprint. Replacing another
non-uniform fill requires `replace_existing=true`. Fingerprints bind native
shape identity and document session; they are not reopened-document identifiers.

Final checks reconcile all stop positions/models/components, native type,
angle/offset/padding/step controls and supported blend behavior. Complete measured
vector nodes/handles or text/body/frame metadata, bounds/matrix, outline and
separate transparency must remain unchanged. Partial/ignored assignments or
unexpected preservation changes quarantine subsequent writes; read-only
inspection remains available. No automatic native undo/restore is claimed.

Installed evidence in `x7_gradient_api_evidence.json` retains 103 descriptors
and three enum groups without connecting to CorelDRAW. Foreground requests to
three SDK pages returned HTTP 200 without readable API content. X7's
[fountain-fill help](https://product.corel.com/help/CorelDRAW/540229932/Main/EN/Documentation/CorelDRAW-Applying-fountain-fills.html)
returned readable descriptions of multicolor/type behavior. It establishes the
workflow requirement, not COM runtime semantics. Access results are retained in
`gradient_online_evidence.json`.

Thirty focused offline checks pass; the full suite has 637 tests, 613 passing
automated checks and 24 guarded live tests skipped. No native gate ran.

`CorelDisposableDocumentLiveTests.test_gradient_fills_live` creates its own four
vector-type fixtures, RGB/CMYK stops, artistic/paragraph text, guarded revisions
and CDR/PDF/readback artifacts. Endpoint-inclusive collection semantics, native
center/angle/step behavior and rendered interpolation remain unverified. Manual
CDR/PDF review, ICC/separation testing and the MCP-client campaign are still
required; native components alone do not establish production readiness.
