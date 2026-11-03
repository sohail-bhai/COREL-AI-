# Source-preserving editable contour offsets

`create_contour_offsets` remains `implemented_unverified`. No live CorelDRAW
verification runs in this batch; native and manual checks stay deferred.

The tool accepts one exact root rectangle, ellipse, polygon or curve whose paths
are closed and whose effects/clip metadata establishes an ordinary source.
Choose inside/outside, 0.0001-100 inches offset, 1-32 steps and an explicit RGB or
CMYK output color. Default output is opaque black fill without an outline.
All six installed native corner codes are exposed; miter-limit values are
reported as native controls, with their exact semantics still unverified.
Open paths/caps, text-to-curves and retained interactive contour effects remain
separate work.

Original inputs stay intact. The wrapper duplicates and proves source/copy
identity and complete measured geometry. Only an owned primitive copy converts
to curves. Whole supported fill/gradient, outline and uniform transparency
metadata are reconciled before effect creation. Sources with unsupported or
unreadable effects, paints or identities are refused before edits.

Creation passes every `Shape.CreateContour` argument explicitly. The returned
effect must be the copy's contour effect, with a consistent native parent/group.
Distance in controlled document inches, direction, steps, corners/caps, colors
and accelerations must read back as requested. Contour-group descendant ownership
is established before separation. Source and baseline descendant curve identities
cannot alias any owned editable curve; copied/generated curves cannot share
mutable data with each other.

`Effect.Separate` receipts must account for existing owned leaves, with only
verified replacement group containers admitted. Ordinary groups are ungrouped
while retaining exact child identities. All generated curve nodes/controls,
bounds and matrix read back identically after separation/ungrouping. Unknown
new leaves, roots, foreign aliases and changed source membership/order prevent
success and require recovery.

The live effect can change the controller's reported bounding box; its underlying
nodes/handles must remain intact and its pre-effect geometry/bounds must return
after separation. Verified replacement containers can retire while every owned
leaf retains identity and geometry.

Final contours are ordinary effect-free editable curves with signed references,
deterministic names, explicit opaque process fill and no outline/transparency.
Geometry must remain unchanged while styling. Compound paths remain complete;
their native ordering is returned without inventing a per-step map. Inside
collapse can produce fewer curves than requested steps or an explicit empty
result. Output counts are measured rather than inferred from `Steps`.

Round outside contours reconcile the combined bounds against the farthest
requested offset. Inside bounds reconcile an inset margin envelope. Other
corners reconcile direction bounds and native control values. These gates do
not independently establish arbitrary pointwise offset distance, winding,
self-intersection resolution, rendered border quality or cutter accuracy.
Native/manual review remains required before production use.

Limits: 1000 original/owned shapes, 32 levels, 64 independent output curves,
16384 generated nodes and the existing per-curve budgets. Cleanup deletes only
owned roots whose complete group/clip trees and contour-effect affiliates are
owned. Known owned outputs can be discarded with measured-source verification;
uncertain ownership, source changes or failed cleanup quarantine further writes.
No automatic native undo is claimed.

After a native throw, local metadata can establish an owned controller's contour
affiliates for cleanup without replaying the call. Remaining live objects must
stay in the expected page/layer. Stray or unreadable ownership cannot report
verified rollback merely because the original layer appears restored.

Installed evidence in `x7_contour_offset_api_evidence.json` retains 47 descriptors
and five enum groups without application access. X7's
[contour help](https://product.corel.com/help/CorelDRAW/540229932/Main/EN/Documentation/CorelDRAW-Contouring-objects.html)
returned readable inside/outside, step/distance, separation and cutting-workflow
descriptions. Three SDK pages returned HTTP 200 without readable API text; an
alternate help path was unavailable. Access results are retained in
`contour_offset_online_evidence.json` without claiming web confirmation of COM
semantics.

Prepared gate: `CorelDisposableDocumentLiveTests.test_contour_offsets_live`.
Thirty-seven focused checks and the full offline suite pass: 675 tests, 650
passing checks and 25 guarded live tests skipped. No native gate ran.
Its disposable rectangle, ellipse, cubic and compound fixtures retain native
readback and CDR/PDF artifacts. Exact native lifecycle, offsets, hole winding,
miter behavior, rendered output and any cutting/print approval remain deferred.
