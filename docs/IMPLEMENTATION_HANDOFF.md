# Implementation handoff - 2026-11-05

The user resumed the full autonomous implementation goal on 2026-11-05.
Autonomous work is active; the broader objective remains incomplete. All live
verification stays deferred to the user-requested consolidated campaign.

Branch: `feature/workflow-planning-slice`. Preserve this branch and read
`HARNESS_INCIDENTS.md` before project work. Inspect current Git status/history
to confirm batch commit/push state; do not infer commits from this document.

Current surface: 92 registered tools, all `implemented_unverified`; 94 registry
records/matrix rows, 314 native members, 272 checked schemas, 282 examples,
28 enum groups and 73 adapter capabilities. Default suite: 901 tests, 871 pass,
30 guarded live tests skipped. No live CorelDRAW verification ran this iteration.

Latest batch: researched X7 nonzero PDF bleed, explicit crop/registration marks
and overprint preservation, plus local `preflight_pdf`. Installed X7 PDF getter/
let documentation establishes bleed in 10-micrometre units (2540 per inch).
The retained evidence includes native descriptors and documentation without
application access. Current primary PDF preflight help was readable; X7 SDK
API pages supplied no readable API content, and attempted X7 prepress-help paths
were unavailable. No web/native confirmation is inferred from those responses.

Controlled export rounds and reports bleed, snapshots/writes/reads/restores
settings, measures every required trim/bleed box, checks fingerprints between
staged observations, publishes exclusively and checks final output identity/
bytes. Late cleanup removes only receipt-matching output; concurrent user edits
are preserved and uncertain cleanup is explicit. Existing CDR/artwork is not saved.

Preflight checks all pages despite 100-entry returned summaries. Resource
inventory covers supported nested/aliased colors, Separation/DeviceN, ICC
alternates, images/masks, patterns/shadings/groups, overprint flags/defaults,
and output-intent encoded-profile presence/hash. Unsupported resource scope is
explicit. Limits: 50 MiB encoded input, 500 pages, 10000 visits, 16 levels,
32 output intents. No artwork/ICC/tint/XMP decoding or inline-image/effective-DPI
coverage. Resource presence and PDF/X declarations cannot prove color/separation/
overprint rendering, artwork bleed/marks, conformance or printer readiness.

Forty-eight focused PDF checks cover the old contracts plus new physical-unit,
all-page/box/positive-bleed/crop checks, nested/aliased/spot/ICC/soft-mask resources,
overprint defaults/aggregate truncation, malformed inputs and limits, late
staging/publication/cleanup failures and preservation of concurrent edits.
Details: [PDF_PREPRESS.md](PDF_PREPRESS.md) and
[offline report](test-reports/2026-11-05-pdf-prepress-non-live.md).

The consolidated inventory covers all 92 tools with zero missing explicit native
gates. `test_pdf_prepress_live` prepares disposable 1 mm/3 mm multipage exports,
enabled marks, explicit overprint preservation, settings restoration and CDR/
PDF/JSON artifacts. The entire campaign and manual production review remain
pending. A prepared test is not native verification.

Continue from [CAPABILITY_GAP_RESEARCH.md](CAPABILITY_GAP_RESEARCH.md) and
`catalog/workflow_gaps.json` under `CURRENT_IMPLEMENTATION_PRIORITIES.md`.
Remaining implementation includes typography spacing/run/fitting, richer
template fields/reflow, controlled document checkpoints/organization, ICC/PDF-X
and export-generated raster coverage, general graphics/image cleanup, component
provider/generation/revision history, quality/reflow/mockups and researched
specialty workflows. Continue independent work for unresolved API/provider/output
dependencies. Custom Alhamdulillah calligraphy/reconstruction remains deferred.

Keep sequential bounded foreground operations and ordinary workspace files.
No browser preview, background jobs, parallel wrappers or subagents. Preserve
these unrelated untracked files untouched and uncommitted:

- `original_Alhamdulillah.jpeg`
- `scripts/_trellis_fit_probe.py`
- `scripts/create_membership_card_print_job.py`
- `scripts/inspect_membership_template.py`

No new harness incident occurred this iteration. Keep the full goal active and
retain `implemented_unverified` until applicable native/manual evidence is reviewed.
