# Controlled native transparency

`get_transparency` reports the native effect type, uniform percentage, affected
fill/outline/both scope and merge-mode code. Missing properties are explicit;
fountain/pattern/texture internals and rendered appearance are outside its scope.

`set_uniform_transparency` accepts integer `percent` 1-100 and `applied_to`
`fill` (default), `outline` or `both`. It explicitly sets normal merge mode.
Zero removes the transparency effect. Replacing or removing a non-uniform
effect requires `replace_existing=true`; none/uniform effects can be revised
directly. Other merge modes remain inspection metadata, not exposed writes.

Common strict selectors or signed references identify individual vectors/text
and bitmaps. Group opacity and full complex-effect workflows are separate work.
Native metadata, exact percentage, affected scope and normal merge mode must all
match. Measured target geometry, identity and underlying fill/outline are checked
before and after writes; bitmap checks cover measured transforms/bounds rather
than pixel identity. Text preservation covers readable content/font/size/bold
and measured geometry rather than every mixed-run property.

Partial native failures and ignored/silently altered effect/scope/merge writes
quarantine subsequent mutations. There is no automatic undo for existing-object
edits. `get_transparency` remains available for inspection during recovery.

Installed X7 evidence in `x7_appearance_api_evidence.json` retains 274 descriptors
and six enum groups with no application connection. It confirms
`ApplyUniformTransparency(Value)`, `ApplyNoTransparency`, `Uniform`, `AppliedTo`
and `MergeMode`, with `cdrApplyToFill=0`, `cdrApplyToOutline=1`,
`cdrApplyToFillAndOutline=2` and `cdrMergeNormal=0`. The catalog retains and
validates these enums. The reference location is
[X7 uniform transparency](https://community.coreldraw.com/sdk/api/draw/17/m/transparency.applyuniformtransparency).
Installed descriptors support the wrapper; live behavior remains unverified.

Eighteen focused non-live checks cover unavailable/irrelevant properties,
non-uniform inspection/replacement, percentages, scopes, removal, merge reset,
ignored native writes, geometry/base-appearance corruption, supported bitmap
targets, unsafe target refusal and worker quarantine with continued inspection.
The prepared gate is
`CorelDisposableDocumentLiveTests.test_uniform_transparency_live`. It creates
synthetic vector/text/bitmap fixtures and its own CDR/PDF outputs. Native blending,
bitmap pixel preservation, visual appearance and printed output await that gate
and manual artifact review. Capabilities remain `implemented_unverified`.
