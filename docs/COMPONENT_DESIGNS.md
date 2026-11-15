# Local component designs and revisions

Five local tools can run while CorelDRAW editing is paused. They use ordinary
JSON/raster files and never access CorelDRAW, a browser, a model API or a network
service. They do not claim native component replacement or completed AI generation.

## Tool flow

1. `create_component_design(plan,destination_path)` records a validated editable
   design plan with stable element IDs and an initial immutable revision.
2. `inspect_component_design(path)` verifies the bounded revision chain and current
   raster receipts, then returns the current editable plan and history summary.
3. `revise_component_design` requires the inspected fingerprint and a new output
   path. Replace one component using the same ID, or choose `restore_revision`.
   Replacements preserve every other element, ordering, canvas and plan metadata.
   Restore creates another revision and verifies the selected historical assets.
4. `resize_component_design` creates a proportional fitted/centered draft on a
   new canvas. Geometry, editable font sizes and outline widths scale uniformly.
   It refuses fonts below an explicit readable minimum and reports only raster
   components needing more pixels at the requested minimum DPI.
5. `prepare_component_generation` saves a literal prompt/pixel-size request for
   one existing component and the exact source design fingerprint. The current
   provider boundary is `local_asset_handoff`: `provider_connected=false`,
   `generated=false`, `network_request_sent=false`. A separately prepared local
   raster can be accepted through a reviewed replacement element/revision.

The user chose preparing a local interface first on 2026-11-15. Preparing a request
is not image generation, and no paid service connection is implied. Native assembly
can use the existing editable design-plan workflow in an exclusive apply window;
native component-targeted replacement and acceptance are still separate work.

## Preservation and recovery

Plans support editable text, rectangle/ellipse primitives and fingerprinted local
raster artwork. General imported vector payloads need their own preservation
workflow and are refused here. Local raster paths are checked before general
design-plan file preflight, avoiding UNC/network file access. Existing raster
inspection supplies EXIF-normalized pixel and source-byte fingerprints.

Every revision retains its parent fingerprint and complete prior plan/asset
receipts, with a whole-manifest fingerprint. Current asset changes refuse use;
changed/missing historical assets refuse the applicable restore. Keep source
assets immutable: these receipts identify files, rather than embedding raster
bytes or treating a file path as proof that its contents stayed unchanged.

Outputs use new absolute local `.json` paths. Staging is read back, source identity/
bytes/assets are rechecked, and a hard link publishes atomically without overwrite
on a supporting local filesystem such as NTFS. Final output identity, length,
mtime and bytes plus source/assets are checked again. On failure only an exactly
receipt-matching output can be removed. Concurrent source/output edits are
preserved; uncertain cleanup is explicit. No existing CDR/JSON save, Undo or
destructive revision restore occurs.

Limits: 200 plan elements, 64 revisions and 5 MiB JSON; existing raster decode
limits apply. Provider requests allow 1–16384 pixels per side, at most 64 million
pixels, and 4000 prompt characters. Duplicate JSON keys and nonfinite data are
refused. Each new revision includes the old history; larger jobs require an
explicitly reviewed new design root.

## Practical limits

Proportional resize preserves aspect ratios and centers the design; it does not
perform responsive/native layout reflow, paragraph fitting or bleed/safe-area
acceptance. Text bounds/glyphs, native composition, visual layout and color/print
acceptance remain explicitly unchecked. Raster DPI flags are axis-aligned draft
placement calculations; native import/rotation/crop must be verified separately.

The source design remains available, so preparation/revisions can happen alongside
personal CorelDRAW work. Applying the design through native tools still obeys
[CONCURRENT_EDITING.md](CONCURRENT_EDITING.md). All registered tools remain
`implemented_unverified` until their applicable consolidated client/native/manual
acceptance is reviewed.

Tests: `tests/test_component_designs.py` covers preservation, chain/asset changes,
restore, minimum sizes, selective resolution flags, provider isolation, publication
races and actual strict request/output schemas. No native gate ran.

## Client-generated images

The active client may fulfill `local_asset_handoff` with its own image-generation
tool. Codex's built-in image generation can supply a local bitmap when that tool
is available in the session; having the imagegen skill file alone does not prove
tool availability. Antigravity can use whichever image tool its session exposes.
The bridge neither reads client credentials nor invokes a client subscription as
an image API. A separately configured provider is optional for unattended jobs
or clients without image-generation capability.

Client workflow:

1. Inspect the component design and prepare a generation request for the selected
   component, using the current design fingerprint.
2. Give its prompt and requested dimensions to the client's image tool. Keep
   essential copy as editable text components; review generated imagery visually.
3. Save the chosen PNG/JPEG or supported raster in an ordinary project asset
   directory with a new filename. Do not leave a project asset only in the
   client's managed artifact or temporary storage.
4. Inspect the raster asset and check its resolution at the intended print size.
   Then revise that component with a new image element using the source design
   fingerprint. Existing components and source assets stay intact.
5. Review the new local revision. Native component assembly/selective replacement
   is a separate unfinished capability; a local revision does not edit a CDR file.

`prepare_component_generation` still reports `provider_connected=false`,
`generated=false` and `network_request_sent=false`. These describe what the bridge
did when preparing the request, even when the client subsequently generates the
image. A generation request is not evidence that a usable image exists.
