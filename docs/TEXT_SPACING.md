# Editable line and paragraph spacing in X7

`set_text_spacing` is `implemented_unverified`. It selects one whole artistic
or paragraph story by unique active-page name, index or signed object reference.
References must address the active page. Linked, fitted, mixed or unreadable
spacing and stories beyond 100000 characters are refused before writing.

Supply at least one of `line_spacing`, `paragraph_before`, `paragraph_after`.
Line spacing accepts 0.01–2000; paragraph spacing accepts 0–2000. These are
operator bounds. `spacing_unit` is `points`, `percent_character_height` (default)
or `percent_point_size`. Values are relative to the unit's documented basis.

Null values preserve the current numeric values when the unit stays the same.
Changing units requires all three explicit values: retaining a number in a new
unit could change a paragraph gap. The native call supplies all four arguments
to `TextRange.SetLineSpacing(Type, LineSpacing, ParaBefore, ParaAfter)`.
Although the type library lists optional -1 defaults, their preservation
semantics are not assumed. Native values/type are read back with 0.01 tolerance.

Text content is compared exactly before/after and never returned by this tool.
Aggregate font/size/style/alignment and horizontal spacing are also compared.
Aggregate equality cannot prove every character run's fidelity. The result
includes before/actual spacing, requested fields, signed identity, finite bounds,
and native linked-story overflow. It does not establish safe-area or glyph fit.

The mutation uses the existing stale-target guards, redacted operation records,
serialized worker and recovery quarantine. Native-call failure, uncertain
readback, changed content/formatting or bounds/context restoration failure
require inspection and operation reconciliation. No automatic replay, rollback
or document save occurs.

The installed X7 type library confirms Single get/let spacing properties,
the `SetLineSpacing` signature and `cdrLineSpacingType` values: character-height
percentage 0, points 1, point-size percentage 2, mixed 3. The mixed value is
refused. [Research script](../scripts/research_text_spacing.py) retains native
descriptors and actual online access results in
[evidence](x7_text_spacing_evidence.json), without application or browser access.

Corel's readable [X7 line/paragraph spacing help](https://product.corel.com/help/CorelDRAW/540229932/Main/EN/Documentation/CorelDRAW-Adjusting-line-and-paragraph-spacing.html)
documents all three unit choices. X7 SDK spacing requests returned HTTP 200
without readable member text; attempted character/word help paths were unavailable.
No online API confirmation is inferred. Per-run, linked/fitted edits, auto-fit
and multilingual visual approval remain gaps. Whole-story horizontal spacing
uses the separately researched structure path below.

The prepared `test_typography_live` campaign candidate includes all unit choices,
partial-unit-change refusal, content/style/frame preservation, overflow and an
editable CDR/JSON artifact. It remains unrun under the consolidated campaign policy.

## Whole-story character and word percentages

`set_text_horizontal_spacing` is `implemented_unverified`. Supply
`character_spacing_percent` (-100–2000), `word_spacing_percent` (0–2000), or both.
Both use percentages of the space character, distinct from leading's character
height and point-size bases. Null preserves the existing value. Native maximum
character and minimum/maximum word justification limits further constrain the
request; the tool does not change those limits.

One unfitted, unlinked artistic or paragraph frame with readable uniform basic
formatting is required. Targeting uses the existing active-page selector or signed
reference. Current content, six spacing fields, basic formatting, native limits,
scope and bounds are checked again after preparing the detached structure and
before applying it. All six fields are explicitly supplied, preserving leading
unit and paragraph gaps. The getter result is never populated; a distinct
`Application.CreateStructSpaceProperties()` result is populated and passed to
`Text.SetSpaceProperties(2, structure)`. No scalar spacing setter or character
start-index assumption is used.

The installed type library establishes `cdrTextFrames.cdrAllFrames=2`, both
indexed property signatures, six structure fields and native limit fields.
Offline pywin32 generation establishes the callable Python names
`Text.GetSpaceProperties`, `Text.SetSpaceProperties` and `Text.GetAlignProperties`.
These are generated accessors on **Text**, rather than native TextRange methods.
See [retained evidence](x7_horizontal_spacing_evidence.json) and
[inspection script](../scripts/inspect_x7_horizontal_spacing.py).

The [X7 character-structure API](https://community.coreldraw.com/sdk/api/draw/17/p/structspaceproperties.characterspacing?lang=cpp)
establishes the space-character basis and character bounds. Word units combine
the installed X7 structure with the X7 user guide's word-spacing instructions
and shared percentage basis on printed page 373.
[X7.4 word API remarks](https://community.coreldraw.com/sdk/api/draw/17.4/p/structspaceproperties.wordspacing?lang=cpp)
are supplementary evidence; they are not direct proof for installed 17.0.
Direct whole-frame/range API requests yielded no readable member text. Native
unit acceptance remains part of the deferred campaign.

Structure and scalar readbacks must agree before application and match the
expected six values afterward, within 0.01 for Single values. Content, basic
formatting, justification limits and frame scope must remain unchanged.
Paragraph frame geometry is compared exactly in unchanged native units; artistic bounds
can reflow. Native overflow is reported, without claiming glyph/safe-area fit,
per-run/appearance fidelity or artistic-anchor preservation. No auto-fit or
document save occurs.

Paragraph frames must belong to the target shape and be outside containers and
paths. Vertical alignment, up to 20 column widths, and following gutters are
read in unchanged native units and retained across the edit and final readback.

The shared native lease, exclusive apply-window requirement, pause boundary and
worker quarantine apply. A failure after native application preserves the edit
for inspection and explicit reconciliation, without replay or automatic undo.
The prepared typography gate now exercises artistic/paragraph percentages,
negative character spacing, native limit refusal and leading/content preservation,
with editable CDR/JSON evidence. It remains unrun.
