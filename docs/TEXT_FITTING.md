# Source-preserving editable paragraph fitting

`fit_paragraph_text` is `implemented_unverified`. It fits an independent editable
copy of one signed root paragraph reference on the active page. The original
story, measured frame, basic appearance and original layer membership/order
are checked before and after the operation. Existing CDR/artwork is never saved.

Parameters are `minimum_size_points` (1–500, default 8),
`size_tolerance_points` (0.01–1, default 0.1), and optional `result_name`.
The minimum cannot exceed the current native point size. Text never enlarges.
An already fitting paragraph is copied without font-size writes. An overflowing
copy is measured at the minimum, then with bounded size/overflow probes to retain
the largest observed fitting candidate. A final probe/readback proves the retained
copy has no native story overflow. At most 24 probes run.

X7 `TextRange.Size` is native Single. Candidates round upward to a representable
value, and actual sizes must stay at/above the requested minimum and at/below
the original size. This avoids rounding below a readability limit. Native
`FitTextToFrame` is intentionally unused: Corel documents automatic shrink and
expansion, while its installed signature supplies no minimum-size parameter.
Global font-size optimality is not inferred from bounded probes.

If the minimum still overflows, the operation reports an explicit failure and
discards only a receipt-matching independent copy. A verified cleanup permits
further worker edits. Uncertain ownership, shared stories, moved copies, concurrent
source/output changes, failed deletion or uncertain command-group closure remain
explicit and require worker reconciliation. No source snapshot is restored over
concurrent edits. An uncertain native Begin/End call is not blindly replayed.

Supported scope: one ordinary, unfitted/unlinked paragraph, up to 10000 nonblank
characters, readable uniform basic font/style/spacing, up to 20 columns, no
effects/PowerClip/container/path fitting, and up to 1000 ownership nodes including
the copy. Text and frame appearance must be readable ordinary process fills/
outlines with no or complete uniform transparency. Independent story identity,
frame hosting identity, frame background/border, raw native column widths/gutters
with their read-time unit code, and geometric readback are checked.
Mixed sizes/styles and complex appearance require a separate preservation workflow.

Results include signed output identity, finite actual bounds, original/minimum/
actual font sizes, each bounded probe, content/source hashes and preservation scope.
Native chain overflow does not prove glyph coverage, character-run fidelity,
safe-area/outline containment or visual/print approval. No frame resize,
text-to-curves conversion, linked fitting or automatic template reflow occurs.

[Research script](../scripts/research_text_ranges.py) reads the installed X7
type library without application access and retains [evidence](x7_text_range_evidence.json).
It confirms text ranges/characters, `FitTextToFrame`, frame hosting/background/
border getters and font-size descriptors. Corel's readable
[X7 paragraph help](https://product.corel.com/help/CorelDRAW/540229932/Main/EN/Documentation/CorelDRAW-Adding-paragraph-text.html)
documents overflow, manual point-size correction and automatic fit shrink/expansion.
SDK requests returned HTTP 200 without readable member text; attempted dedicated
fit-help paths were unavailable. No online API confirmation is inferred.

The disposable typography campaign candidate prepares fitting/already-fitting/
minimum-refusal examples, unchanged source/frame checks and CDR/JSON evidence.
It remains unrun under the consolidated live-verification policy.
