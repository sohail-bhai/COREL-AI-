# PDF bleed controls and bounded prepress inspection

Implemented 2026-11-05; native and manual verification remain deferred.

`export_pdf_controlled` now accepts `bleed_inches` (0–1), `crop_marks`,
`registration_marks`, and `preserve_overprints`. Defaults keep zero bleed and
disabled marks, and explicitly preserve document overprints. The installed X7
`IPDFVBASettings.Bleed` getter/let documentation says **“Specifies the bleed
amount in tens of micron”**. One inch is 25,400 micrometres, so the integer scale
is 2,540 units per inch. The requested amount rounds to the nearest 10 micrometres;
the result reports requested inches, native units and resulting inches. A positive
amount rounding to zero is refused. The installed descriptors and documentation
are retained in `x7_pdf_api_evidence.json`; no application connection was made.

For nonzero bleed or enabled marks, export requires explicit measured `TrimBox`
sizes on every page. Nonzero bleed also requires an explicit `BleedBox` and all
four margins matching the quantized request within 0.001 inch. At zero bleed a
missing bleed box is accepted only with an explicit trim box. All available boxes
must fit the media and crop boxes, and bleed must contain trim. Positive requested
bleed must have positive measured margins even below the numeric tolerance.
Rotated trim sizes are checked
against the effective page orientation. A missing/wrong box prevents publication.
This conservative contract may reject X7 outputs; the native campaign must resolve
any actual box conventions before acceptance. Page boxes do not prove artwork
extends into bleed or that marks are correctly drawn.

Settings are snapshotted, written, read back, restored and read back again.
The staged PDF receives all-page/font inspection and prepress checks, with matching
byte fingerprints across observations. Publication remains exclusive and checks
both copied and final output bytes/identity; an existing output is preserved.
Late cleanup removes only output still matching the operation's byte/identity
receipt. Concurrent output edits are retained and reported as uncertain cleanup.
Observations are bounded and do not lock paths against changes between them.
The source CDR is not saved.
Failed native restoration requires the existing exact-operation recovery flow.

`preflight_pdf` is an independent local tool. It reads one bounded immutable byte
snapshot and accepts optional expected trim sizes/bleed, embedded-font presence
and output-intent presence. The result checks every page even when summaries
truncate. `checks_passed` describes these checks only; `production_ready` is false.
Supported resource inventory includes:

- Device/calibrated/ICC/Indexed/Pattern color spaces and aliases, Separation and
  DeviceN colorants, including DeviceN colorant resources and alternate spaces.
- Nested Form, tiling/shading pattern, transparency-group and soft-mask resources;
  image width/height and masks; Type3 font resources with explicit glyph-scope limits.
- Overprint stroke/fill flags and mode, including the PDF fill-default rule, with
  all-state totals retained beyond the 100-entry returned summary.
- Output-intent identifier/subtype and encoded embedded-profile presence/hash;
  information-dictionary PDF/X declarations, labeled as declarations only.

Limits are 50 MiB encoded bytes, 500 pages, 10,000 resource visits, 16 resource
levels, 32 output intents and 100 entries per returned resource/page summary.
Every resource edge consumes budget, including aliases and shared references.
Shared resources using different parent aliases are inspected in each scope.
Malformed flags, structures and cycles exceeding limits are refused. Unknown
color/resource/XObject types, external/OPI resources, annotation appearances,
marked-content properties and Type3 glyph content make the supported-resource
inventory incomplete. Counts for images/states represent inspected resource scopes.

Artwork/content streams, inline images, tint transforms, ICC programs and XMP
are not decoded. Unused resources may appear; direct artwork color operators
may have no resource entry. Effective raster DPI, valid profiles, color conversion,
spot/separation correctness, overprint rendering, artwork bleed coverage, mark
appearance, PDF/X compliance and printer/visual acceptance remain unchecked.

Primary online access results are retained in `pdf_prepress_online_evidence.json`.
Corel's [current PDF preflight help](https://help.coreldraw.com/CorelDRAW/540111192/Documentation-Windows/CorelDRAW-en/CorelDRAW-PDF-preflight-summaries.html)
returned readable HTTP 200 requirements text; it is a newer-product reference.
X7.4 SDK requests returned HTTP 200 without readable API content, and attempted X7
prepress help paths were unavailable. The [Adobe PDF standard](https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/PDF32000_2008.pdf)
was reachable but the bounded PDF download was not parsed. None supplies new web
confirmation of X7 units. Installed X7 documentation supplies the conversion.

The prepared `test_pdf_prepress_live` gate creates disposable multipage fixtures
with off-page bleed artwork, native process color and explicit overprint preservation,
checks two physical bleed
amounts and enabled marks, verifies all restored settings, and retains CDR/PDF/JSON.
It has not run. Consolidated MCP envelopes and manual prepress review remain pending.
