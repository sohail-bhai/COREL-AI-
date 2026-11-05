# Capability research and delivery backlog

**Research date:** 2026-11-05
**Target:** CorelDRAW X7 17.0.0.491; Python/MCP/serialized COM bridge.
**Authorization:** Continue the implementation plan autonomously, research online
capabilities, and use evidence-backed gaps to guide further work. Live checks
remain deferred to one consolidated campaign.

## Findings

The current server exposes 94 tools, all `implemented_unverified`. It covers
inspection, editable typography/layout, reusable text batches, vectors, process
colors/gradients/transparency, clipping, copied contour derivatives and guarded
page/local-layer creation, activation, naming and flags, plus verified local
raster derivative preparation and document-wide native raster preflight. Complete prepress production, background/cleanup
image workflows and AI component generation/revisions
remain incomplete. Specialist scripts are retained research artifacts.

The relevant work spans logos and vector illustration, cards and certificates,
flyers and publications, signs, labels, apparel artwork, and packaging. These
are documented CorelDRAW workflow families, not a promise of universal automation.
See Corel's [industry overview](https://www.coreldraw.com/en/licensing/industries/)
and [vector design examples](https://www.coreldraw.com/en/learn/guide-to-vector-design/what-can-you-make-with-vector-graphics/).

X7's own [Help](https://product.corel.com/help/CorelDRAW/540229932/Main/EN/Documentation/CorelDRAW-Welcome-to-CorelDRAW-Help.html)
and [User Guide](https://product.corel.com/help/CorelDRAW/540229932/Main/EN/User-Guide/CorelDRAW-X7.pdf)
establish the older product baseline. Current product pages identify useful
expectations, but variable fonts, newer AI features, and modern export/data
options must not be assumed to exist in X7. The
[version comparison](https://www.coreldraw.com/en/product/coreldraw/compare/)
is a requirements reference, not X7 automation evidence.

## Evidence-backed gaps

| Workflow family | Current coverage | Missing behavior and implementation target |
|---|---|---|
| Reliable targeting | Bound-document liveness, bounded search and signed page/layer/group/object references | Persistent/reopened document strategies and broader reference-aware tools |
| Recovery and records | Bounded redacted records, explicit busy/timeout state, late/partial quarantine and guarded reconciliation | Existing-document checkpoints and specialized rollback policies |
| Document/page/layer work | New document, bounded structure/fingerprints, appended explicit-size pages, local layer creation, activation/names/flags, CDR save | Controlled open/close/checkpoints, existing-page resize/reorder/deletion, master/special editing and cross-layer/page object moves |
| Everyday typography | Artistic/paragraph creation, whole-story styles/spacing, source-preserving bounded paragraph fitting, font catalog and native chain overflow inspection | Character/word units, per-run/linked/fitted editing, glyph/safe-area acceptance and broader reflow |
| Layout/transforms | Move/proportional resize, pivot rotation, mirroring, native matrix inspection, sibling order, measured distribution/grouping and guarded page/local-layer controls | Cross-layer/page object moves, guides, outline-aware bounds and safe-area reflow |
| Vector construction | Line/cubic paths and guarded nodes/handles; copied topology/shaping/compound revisions; native inside/outside contour derivatives | Adjacent deletion/fitting, open endpoint cropping, nested shaping, text/effect/open contours and exact native winding/offset/cutting gates |
| Appearance and clipping | Native RGB/CMYK process colors; uniform transparency; PowerClip fitting/extraction/rebuilds; opaque direct multicolor gradients with guarded revisions | Proven outline units, spot/ICC, wider gradient/blend/group effects, in-place clip editing and native/visual verification |
| Images and references | Validated imports; source/pixel fingerprints and verified PNG/TIFF derivatives; native affine DPI plus document-wide page/master/group/clip and local-link preflight | Background removal/cleanup and AI enhancement, native/source-detail/color/visual acceptance, export-generated rasterization, bounded tracing and fidelity reports |
| Templates and data | Numbering/chest-bib sequence; named text templates, literal CSV, duplicates/count/overflow reconciliation and independent full/partial sheets | Image fields, mixed/linked text, auto-fit and numbering variants |
| Publications and sheet production | Independent source-preserving full/partial-sheet repeat runs with exact quantity and final copy/page reconciliation | Native/manual repeat acceptance, job-specific allowances and artwork bleed/mark coverage |
| Export and prepress | Non-overwriting CDR/PDF output; researched bleed/mark/overprint controls with all-page/font/trim/bleed checks; supported PDF color/spot/overprint/image/output-intent resource inventory | Native units/box/mark and content bleed acceptance, ICC/PDF-X/color/separation correctness and export-generated effective raster DPI |
| Codes and specialty output | No general registered workflow | QR/barcodes, cut paths, sign/banner allowances and apparel separations after format/API research |
| Component AI design | Structured executable plans with imported artwork | Provider interface; separate raster/vector/text components; regenerate one component; preserve approved pieces |
| Smart redesign/revisions | Basic plan/readback and selected rollback | Reflow to new size, selective high-resolution regeneration, component history, diff and verified restore |
| Quality and operator experience | Structured envelopes/preflight/discrepancies | Job-intent routing, coverage explanation, bounded correction loops, visual-review evidence and revision previews |

These gaps are derived from the repository's registered tools and limitations,
compared with the cited workflow documentation. UI feature existence is not
proof of a safe COM implementation.

Useful implementation evidence includes X7's
[CreateParagraphText signature](https://community.coreldraw.com/sdk/api/draw/17/m/layer.createparagraphtext),
[shape lookup](https://community.coreldraw.com/sdk/api/draw/17/m/shapes.findshape),
and [PowerClip contents](https://community.coreldraw.com/sdk/api/draw/17/p/powerclip.shapes).
Paragraph creation now has local type-library evidence and fake-COM/schema
coverage in [TYPOGRAPHY.md](TYPOGRAPHY.md); native verification remains deferred.
Common transforms and measured distribution have the same implementation
status; see [LAYOUT_TRANSFORMS.md](LAYOUT_TRANSFORMS.md) for X7 signatures,
actual readback, projected-overlap scope and the pending native gate.
PowerClip wrappers now pass 34 focused checks in [POWERCLIP.md](POWERCLIP.md);
native copy/fitting/extraction and visual evidence remain deferred. General shaping now has
installed X7 signatures and 33 focused checks in [VECTOR_EDITING.md](VECTOR_EDITING.md),
informed by Corel's [shape programming guide](https://community.coreldraw.com/sdk/w/guide/214/8-6---working-with-shapes).
Source-preserving node topology revisions add 22 focused checks and installed
`Curve.CopyAssign` evidence in [VECTOR_TOPOLOGY.md](VECTOR_TOPOLOGY.md). New online
API requests returned no readable documentation; their access result is retained
without claiming web confirmation. Native assignment/closure remains deferred.
Native process-color wrappers now have 18 focused checks and installed factory/
channel evidence in [PROCESS_COLORS.md](PROCESS_COLORS.md). The appearance
inspector retained transparency/PowerClip signatures. Uniform transparency now
has two registered wrappers and 18 focused checks in [TRANSPARENCY.md](TRANSPARENCY.md).
Three PowerClip wrappers add copied mixed-content fitting, extraction and rebuilds
with installed X7 evidence and owned-output recovery checks. Online API requests
returned no readable content; in-place editing and outline-width units remain
unresolved work. Native blending/clipping remains deferred.

Two gradient tools now pass 30 focused checks in [GRADIENTS.md](GRADIENTS.md).
Installed X7 evidence retains 103 descriptors and three enum groups. X7's
[fountain-fill help](https://product.corel.com/help/CorelDRAW/540229932/Main/EN/Documentation/CorelDRAW-Applying-fountain-fills.html)
returned readable descriptions of multicolor/type workflows, while three SDK
requests returned no readable API content. Opaque direct RGB/CMYK stops, guarded
revisions and measured text/vector preservation are implemented; native stop
collection/coordinates/interpolation and rendered appearance remain deferred.

Copied inside/outside contours now pass 37 focused checks in
[CONTOUR_OFFSETS.md](CONTOUR_OFFSETS.md). X7's
[contour help](https://product.corel.com/help/CorelDRAW/540229932/Main/EN/Documentation/CorelDRAW-Contouring-objects.html)
documents step/distance controls and separated cuttable outlines. Installed
evidence retains 47 descriptors and five enum groups without application access;
three SDK requests returned no readable API text. Native controls, editable
derivatives and owned-tree recovery are implemented. Exact arbitrary-curve
distance, winding, miter semantics and cutting/native artifact review remain
deferred; no production readiness is inferred from these offline checks.

Seven page/local-layer tools now pass 38 focused checks in
[DOCUMENT_ORGANIZATION.md](DOCUMENT_ORGANIZATION.md). Readable X7 page/layer help
supports multi-page documents and visible/editable/printable layers; 47 installed
descriptors establish the automation signatures without application access.
Two SDK requests returned no readable API text. Structural fingerprints,
activation, named explicit-size append and local-layer flags are implemented;
existing-page size/order/deletion, cross-layer moves, master/special edits,
checkpoints and native/artifact verification remain broader work.

Native bitmap inspection now passes 38 focused checks in
[BITMAP_INSPECTION.md](BITMAP_INSPECTION.md). Pixel dimensions and the uncropped
affine grid yield axis and worst directional DPI, with separate native metadata,
crop/scope checks and two-read consistency. Readable X7 size/resolution help and
32 installed descriptors support the requirement; three SDK pages returned no
readable API content. Native coordinates/crop/skew/groups, source detail and
color/print approval remain deferred.

Local source-preserving raster inspection/preparation passes 49 focused checks in
[RASTER_PREPARATION.md](RASTER_PREPARATION.md). Primary Pillow EXIF-transform,
resampling and image-format metadata references returned readable HTTP 200
content; [retained evidence](raster_preparation_online_evidence.json) records the
actual access dates. PNG/TIFF derivatives have pixel/source/ICC/DPI readback,
explicit fitting/upscale rules and exclusive publication. Multiple frames and
precision/color conversion remain explicit separate workflows. Background
removal/cleanup, AI enhancement, tracing and Corel/visual handoff remain pending.

Document-wide [raster preflight](RASTER_PREFLIGHT.md) now passes 47 focused
checks. Two native graph scans and three structure snapshots reconcile page/master
membership, group/clip paths, ancestor transforms, bitmap DPI and local linked-file
presence while preserving native context. Four additional native getters are
supported by 24 installed descriptors, including `PowerClipParent -> IVGShape`.
Readable primary PDF preflight and X7 resolution help support the requirement;
the SDK link page supplied no readable API text. Partial/changed/effect/EPS/unknown
or clipping/master/relative/OPI coordinate and source evidence cannot establish a
complete pass. Native/manual acceptance and export-generated raster coverage remain
pending. Opaque symbol/OLE/EPS/custom containers and special effect groups prevent
clean coverage. Multi-sheet production is the next implementation work.

Data and print requirements are supported by Corel's
[print merge documentation](https://product.corel.com/help/CorelDRAW/Documentation-Windows/CorelDRAW-en/CorelDRAW-Print-merge.html),
[page layout guide](https://help.coreldraw.com/CorelDRAW/540111192/Documentation-Windows/CorelDRAW-en/CorelDRAW-Page-layout.html),
and [PDF preflight guide](https://help.coreldraw.com/CorelDRAW/540111192/Documentation-Windows/CorelDRAW-en/CorelDRAW-PDF-preflight-summaries.html).
The current guides establish desired behavior; X7 compatibility is a separate gate.
For image conversion, Corel documents [tracing controls](https://product.corel.com/help/CorelDRAW/Documentation-Windows/CorelDRAW-en/CorelDRAW-Trace-bitmaps.html);
automatic tracing still requires explicit raster/vector status and visual evidence.

## Delivery sequence

**Template update:** Four registered template tools now pass 25 focused local
checks; see [TEMPLATE_BATCHES.md](TEMPLATE_BATCHES.md). Live and manual review
remain deferred. They cover text personalization and independent multi-page
outputs; generalized imposition and prepress remain separate gaps.

**PDF research update:** The installed X7 type library confirms 126 PDF
descriptors and 14 enum groups without connecting to CorelDRAW; see
`x7_pdf_api_evidence.json`. Whole-document range, embedding, text-as-curves,
RGB/CMYK/native color modes, zero bleed and disabled marks can be controlled.
Corel's [X7.4 bleed property](https://community.coreldraw.com/sdk/api/draw/17.4/p/pdfvbasettings.bleed)
previously supplied inconsistent unit wording. The 2026-11-05 installed X7
getter/let documentation explicitly defines **tens of micron**, establishing
2540 integer units per inch without application access. Controlled export now
rounds that conversion, writes explicit crop/registration/overprint controls,
restores settings and requires all-page measured trim/bleed boxes. The new local
`preflight_pdf` inventories supported color/spot/image/overprint/output-intent
resources and declarations with bounded work and explicit unsupported scope.
Resource presence is separate from content usage and color/rendering correctness.
The PDF tests now cover conversion, boxes, nested/aliased resources, overprint
defaults, late staging/publication failures and preservation of concurrent edits;
see [PDF_PREPRESS.md](PDF_PREPRESS.md). Current primary preflight help was readable;
X7 SDK API text was unavailable. Native conversion/box/mark behavior, artwork bleed,
ICC/PDF-X and export-generated raster DPI remain deferred or missing work.
The consolidated inventory covers all 94 tools with prepared native candidates.

**Typography spacing update:** [TEXT_SPACING.md](TEXT_SPACING.md) adds guarded
whole-story leading/paragraph spacing in points or documented character-height/
point-size percentages. Installed X7 `SetLineSpacing` and enum evidence, readable
X7 unit-choice help and 23 focused non-live checks establish implementation scope.
All unit changes require explicit line/before/after values, avoiding reinterpretation
of preserved gaps. SDK pages supplied no readable member text. Character/word units,
per-run/glyph fidelity, broader fitting/reflow and native/visual acceptance remain gaps.

**Paragraph fitting update:** [TEXT_FITTING.md](TEXT_FITTING.md) adds an independent
editable copy with 1–500 point readability bounds and at most 24 measured native
size/overflow probes. Source/story/frame identity, basic appearance, frame background/
border, raw column dimensions and membership/order are reconciled. Receipt-matching
copies can be removed; shared/moved/concurrently edited or uncertain objects remain
explicit. Native Single candidates round upward so actual size stays within bounds.
Installed X7 descriptors and readable paragraph help support the implementation;
SDK pages lacked readable member text. Twenty-eight focused non-live checks pass.
Per-run/artistic/linked/container fitting, glyph/safe-area acceptance, automatic
template reflow and the consolidated native/manual gate remain pending.

1. **Reliability foundation:** ID-001 stale targets; SAFE-001 redacted records;
   SAFE-002 busy/timeout state and guarded recovery. Keep inspection bounded and
   prevent fallback to a different document/object.
2. **Complete a small editable job:** paragraph text and typography revisions,
   proportional transforms, distribution/rotation, layer/z-order organization,
   and source-safe card/flyer revisions.
3. **Reusable production:** named-field templates and deterministic CSV batches,
   numbering variants, multisheet/partial-sheet materialization, controlled
   export and reconciliation reports.
4. **General graphics:** bounded path/node editing and shaping, PowerClip,
   native appearance/effects, image preparation and simpler reference recreation.
5. **AI design and revisions:** component generation/provider boundary, targeted
   regeneration, smart size adaptation, quality checks, product mockups, and
   local component/document version history.
6. **Specialized work:** codes, signs, cut/engrave/artwork preparation and other
   industry workflows only after their output/API requirements are established.

The broad goal is flexible design and production coverage through typed tools
and composable workflows. It does not authorize pretending a raster is editable
vector work, ignoring unsupported APIs, submitting files to an unspecified
external provider, or bypassing source/output safety.

## Working rules and completion evidence

- Complete coherent batches autonomously, retain durable state in ordinary
  files/Git, and keep the existing user artwork and pending edits intact.
- Add only evidenced, bounded tools; validate complete jobs before mutation,
  read back actual results, and keep limits/unsupported behavior visible.
- Run the default tests, catalog validator and static diagnostics for every
  implementation batch. Commit and push completed batches.
- Preserve prepared live gates and reconcile every registered tool/workflow
  against the final consolidated campaign. Status stays unverified until the
  applicable live and manual checks pass.
- An unresolved signature, provider credential, output specification, or
  external-state requirement is recorded as an explicit dependency. Continue
  independent work rather than inventing a successful result.

The machine-readable gap backlog is
[`../catalog/workflow_gaps.json`](../catalog/workflow_gaps.json). It is a workflow
coverage report and delivery queue, not an expansion of the registered MCP surface.
