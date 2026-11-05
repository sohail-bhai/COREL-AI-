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
No online API confirmation is inferred. Character/word write units, per-run,
linked/fitted edits, auto-fit and multilingual visual approval remain gaps.

The prepared `test_typography_live` campaign candidate includes all unit choices,
partial-unit-change refusal, content/style/frame preservation, overflow and an
editable CDR/JSON artifact. It remains unrun under the consolidated campaign policy.
