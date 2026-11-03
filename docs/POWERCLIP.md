# Source-preserving editable PowerClip workflows

Three tools create, inspect and extract clipped artwork. Capabilities remain
`implemented_unverified`; all live checks are deferred to the consolidated campaign.

`get_powerclip` returns a source-bound frame/content fingerprint and complete
bounded group/clip hierarchy. It includes native identities, whole-name/body
hashes with bounded previews, vector nodes/controls, native transforms,
fill/outline/transparency, bitmap size/resolution metadata and clip lock state.
Unreadable clip getters are not treated as proof that clipping is absent.
Native `PowerClip.Parent` and descendant page/layer ownership are checked.

`create_powerclip` accepts a closed rectangle/ellipse/polygon/curve frame and
1-64 content references. Inputs must be distinct exact roots on one active
page/layer. Content can include vectors, artistic/unlinked paragraph text,
bitmaps and nested groups/clips. The wrapper copies every input independently,
preserves original stacking, groups multiple copies and keeps text editable.
It rejects copied original/foreign descendants, aliased curves and shared text
stories before fitting. Native copy name changes are normalized only on owned
objects so named content remains usable.

Choose `fit_kind` `none`, `contain` or `cover`; fitting uses measured frame bounds
and `padding_inches`. Source bounds/scale and the total original/copied ownership
budget are checked before duplication. Fitted nodes, handles and descendant
bounds must match the affine placement plan. Nested copied clips are temporarily
locked during scaling, then their original lock settings are restored. Native
bitmap dimensions and editable text content/font/bold are reconciled; effective
resolution and native text size can change during fitting and are reported.
Irregular-frame visibility and glyph/render fidelity require manual review.

Clipping passes explicit `cdrFalse` to `CenterInContainer`; it does not use the
application's unspecified centering default. Final frame/content geometry,
identity and requested `contents_locked` are checked. Replacing copied existing
contents requires `replace_existing_contents=true`. The original clip remains
intact while the copied frame receives the new artwork.

`extract_powerclip_contents` requires the current frame/content fingerprint.
It copies the clip, unlocks only the owned copy, reconciles extracted native
identities/geometry and names each independent output deterministically. Its
empty copied frame is discarded. Extracted roots have ordinary signed editing
references; grouped descendants use the existing group-reference tools. A
revision cycle is extract copies, edit the desired component, then create a
revised copied clip with explicit content replacement. Existing clipped
descendants retain inspection identity metadata rather than fabricated general
editing references. In-place UI edit mode remains separate work.

Limits: 1000 shapes in the original/copied ownership scope, 32 levels, 64 immediate
clip roots and existing per-curve geometry limits. Linked paragraph stories and
unsupported native effects/types are refused. Fingerprints belong to the current
bridge/document session. Their raw bitmap metadata is not a pixel-content hash.

Both mutation tools verify original root membership/relative order and complete
measured source-tree/basic-appearance state. Cleanup deletes only established
owned roots whose complete descendant membership is owned. Unknown objects,
foreign aliases, changed sources and failed cleanup leave recovery required;
read-only PowerClip inspection remains available. This is not a complete native
file/effect or rendered-pixel diff, and does not establish production readiness.

Installed evidence in `x7_powerclip_api_evidence.json` retains 71 descriptors
without application access. It confirms native parent/contents/locks, explicit
centering parameters, extraction, grouping and bitmap metadata. Foreground
requests to the primary [AddToPowerClip](https://community.coreldraw.com/sdk/api/draw/17/m/shape.addtopowerclip?lang=cli),
[PowerClip getter](https://community.coreldraw.com/sdk/api/draw/17/p/shape.powerclip?lang=cli)
and [extraction](https://community.coreldraw.com/sdk/api/draw/17/m/powerclip.extractshapes?lang=cli)
pages returned HTTP 200 without readable API content. Those access results are
retained in `powerclip_online_evidence.json`; they do not confirm web semantics.

Thirty-four focused checks cover geometry, nested fitting, editable mixed content,
name/body fingerprints, extraction/rebuilds, ownership/alias failures and recovery.
The prepared gate is `CorelDisposableDocumentLiveTests.test_powerclip_workflows_live`.
It creates its own vector/text/bitmap fixtures, edits an extracted component,
rebuilds a clip and saves CDR/PDF artifacts. X7 getter absence, duplicate/group/
coordinate/extraction behavior and rendered clipping still need that native gate
and manual artifact review.
