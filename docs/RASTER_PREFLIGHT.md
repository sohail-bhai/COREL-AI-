# Document-wide raster preflight

Status: `implemented_unverified`. Live CorelDRAW, consolidated MCP client and
manual artifact verification remain deferred by the user.

`preflight_document_rasters(minimum_dpi=150, include_nonprinting=false,
max_shapes=1000)` inspects native bitmap objects throughout the bound document.
It traverses page layers, nested groups, PowerClip contents and master layers.
Master bitmaps appear once with their applied-page indices from `Page.AllLayers`;
the result does not duplicate master source shapes for every page. Nonprinting
and unapplied master layers are excluded by default and listed explicitly.
Hidden printable layers remain included. `include_nonprinting=true` extends the
scope to those excluded layers.

Every raster has a page/layer/shape identity and a root/group/PowerClip path,
native bitmap metadata, placed transform/uncropped box, effective resolution,
linked-file presence evidence, per-check status and reasons. Clipped/master
objects use observation locations rather than ordinary signed editing references.
Those locations must not be used to bypass reference-aware editing guards.

The resolution check reuses the existing native affine pixel-grid inspector.
Axis and worst directional DPI come from the placed uncropped parallelogram and
pixel dimensions, including scale, rotation, mirror and skew. Matrix scale is
not applied twice; cropping does not add source pixels. A value below the requested
minimum is `failed`; verified calculated evidence above it is `passed`. Missing,
degenerate, inconsistent or imprecise geometry is `indeterminate`. Effects,
PowerClip coordinates, master-page placement and EPS placeholder resolution also
remain indeterminate. Unreadable ancestor transforms invalidate child resolution.

Native `ExternallyLinked`, `OPILinked`, `IsEPS` and `LinkFileName` distinguish
ordinary bitmap evidence from links/placeholders. Absolute local linked files
are checked for nonempty regular-file presence. Missing, empty or non-file
sources fail this presence check. Unreadable metadata/stat calls are indeterminate.
Direct UNC/device paths are not checked. Relative paths expose a candidate based
on a saved local CDR directory, but relative-base and OPI source semantics remain
indeterminate pending native verification. Native links are never resolved,
updated, relinked or written. Linked files are not decoded, read or hashed;
presence does not prove source quality or freshness of Corel's cached pixels.

The scanner reconciles two bounded graph observations and three document
structure snapshots. It compares identities, order, types, names, group/clip
membership, ancestor transforms/effect counts, bitmap evidence, native link
metadata and local file-state fingerprints based on path/identity/size/timestamps.
Changes invalidate every current pass/fail status while preserving the original
`observed_status` and evidence. This is observation consistency, not atomic
locking against edits after or between the final reads.

Native units, reference point, dirty state, selection and active page/layer must
remain readable and exactly preserved. The scanner does not activate pages or
layers, select shapes, change pixel data or write document content. Failed context
verification refuses the tool; existing worker recovery guards block later writes.
Read-only preflight remains available during mutation quarantine.

`minimum_dpi` must be finite in [1, 2400], `max_shapes` is an integer in [1, 4096]
and nesting is capped at 32 levels. Structure inspection also retains its
256-page/128-layer/4096-entry limits. Exhausted graph budgets, aliases/cycles,
foreign ownership and unreadable branches produce explicit partial coverage.
Symbol/OLE/EPS/custom/unknown containers also require partial coverage; special
effect groups enumerate readable child shapes while retaining unresolved rendering.
Uninspectable structure/context refuses the operation instead of declaring an
empty or clean document. No text bodies or native pointer strings are exposed.

`summary` counts `passed`, `failed`, `indeterminate` and total observed rasters.
`overall_status` is `failed` when a stable observed check fails, `indeterminate`
when coverage/evidence is incomplete or changed, `passed` only when a nonempty
complete stable scope passes, or `not_applicable` for a complete empty scope.
`raster_checks_passed` is true only for the complete pass. `production_ready`
remains false. Source detail/fidelity, cache freshness, ICC/spot/overprint,
export-generated rasterization, visual fidelity and printer approval are explicit
unchecked categories. Vector effects/export settings can create raster output
that is outside this native bitmap-object inventory.

Evidence: [47 focused offline checks](test-reports/2026-11-04-raster-preflight-non-live.md),
[24 installed X7 descriptors](x7_raster_preflight_api_evidence.json) and
[bounded primary online excerpts](raster_preflight_online_evidence.json).
`PowerClipParent` resolves to the installed `IVGShape` return interface. Readable
Corel PDF preflight and X7 bitmap-resolution help returned HTTP 200; the SDK
`LinkFileName` page returned HTTP 200 without readable API text. Their actual
access dates are retained, and no application connection was used for research.

Prepared deferred gate:
`CorelDisposableDocumentLiveTests.test_document_raster_preflight_live`. It creates
an independent prepared transparent PNG, two owned pages and a nested low-DPI
bitmap on the inactive page, checks evidence/context at two thresholds, then
saves CDR/PDF and JSON readback. Native linked-file, OPI/EPS, clipping/master,
nonprinting and unusual-coordinate cases require later native/manual expansion.
Review prepared-image alpha/color/placement and artifacts before raising status.
