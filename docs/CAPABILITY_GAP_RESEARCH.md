# Capability research and delivery backlog

**Research date:** 2026-11-03
**Target:** CorelDRAW X7 17.0.0.491; Python/MCP/serialized COM bridge.
**Authorization:** Continue the implementation plan autonomously, research online
capabilities, and use evidence-backed gaps to guide further work. Live checks
remain deferred to one consolidated campaign.

## Findings

The current server exposes 67 tools, all `implemented_unverified`. It has useful
inspection, simple drawing/editing, design-plan, numbering, and imposition
foundations. Tool count does not establish complete workflow coverage: there is
no node insertion/deletion, contour offsets, clipping/effects,
complete prepress production, or AI component
generation/revision interface yet. Specialist scripts are research artifacts,
not general MCP capabilities.

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
| Document/page/layer work | New document, inspect pages/layers, CDR save | Controlled open/close, page management, editable/visible layers, source checkpoints |
| Everyday typography | Artistic/paragraph creation, whole-story style edits, font catalog and aggregate/native chain overflow inspection | Spacing writes, per-run/linked/fitted editing, glyph checks and safe auto-fit |
| Layout/transforms | Move/proportional resize, pivot rotation, mirroring, native matrix inspection, sibling order, measured distribution and grouping | Layer/page organization, guides, outline-aware bounds and safe-area reflow |
| Vector construction | Line/cubic paths, full curve inspection, fingerprint-guarded nodes/handles; source-preserving combine/break apart and weld/trim/intersect | Node insertion/deletion, contour offsets, nested shaping and native winding/appearance gates |
| Appearance and clipping | RGB fill; native fill inspection; raw outline readback | Proven outline units, CMYK/spot writes, transparency/gradients and PowerClip workflows |
| Images and references | Validated imports; local cover/contain planning; retained tracing research | General crop/background/cleanup, effective-resolution checks, bounded tracing and fidelity reports |
| Templates and data | Numbering/chest-bib sequence; named text templates, literal CSV, duplicates/count/overflow reconciliation and independent full/partial sheets | Image fields, mixed/linked text, auto-fit and numbering variants |
| Publications and sheet production | Grid/contour planning; single-sheet execution | Multiple sheets, partial final sheets, page order, bleed/marks, source-preserving production outputs |
| Export and prepress | Non-overwriting CDR/PDF output; controlled zero-bleed PDF settings and parsed all-page/font checks; raster DPI and geometry checks | Nonzero bleed, ICC/PDF-X, color/spot/overprint and effective raster-resolution checks |
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
PowerClip still needs a wrapper and runtime evidence. General shaping now has
installed X7 signatures and 33 focused checks in [VECTOR_EDITING.md](VECTOR_EDITING.md),
informed by Corel's [shape programming guide](https://community.coreldraw.com/sdk/w/guide/214/8-6---working-with-shapes).

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
uses inconsistent unit wording in its summary and remarks. Retain nonzero bleed
as an explicit dependency until the conversion is established. Parsed PDF
page boxes and font resource checks are required; these do not prove PDF/X,
ICC accuracy, visual fidelity or printer readiness. Two PDF tools now pass 22
focused checks; see [PDF_PRODUCTION.md](PDF_PRODUCTION.md). The complete deferred
inventory accounts for all 67 registered tools and prepared native gate candidates.

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
