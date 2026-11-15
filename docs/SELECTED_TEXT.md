# Safe selected-text editing

`inspect_text_range` returns exact Unicode selected content, signed object
reference, fingerprint and character formatting. Explicit bounds use Python
Unicode code-point offsets `[start,end)`. Omit both to capture the current native
`Text.Selection` once. An edit uses that captured object/range, never a later UI
selection or a name/index fallback.

`edit_text_range` requires that reference, bounds, exact `expected_text` and
`expected_fingerprint`. It can apply font/size/bold/italic/underline to mixed runs
or replace uniformly formatted selected content. Replacement and formatting are
separate operations with another inspection between them. No whole-story rewrite,
selection/activation, native Undo, existing-file save or automatic rollback occurs.

## Installed API and Unicode evidence

`scripts/research_selected_text.py` reads the installed X7 type library without
connecting to CorelDRAW. `docs/x7_selected_text_evidence.json` retains `Selection`,
`Characters.Item(Index,Count)`, `Count` including paragraph breaks, native
`Start`/`End`, range signatures and `cdrTextIndexingType`: character=0, word=1,
paragraph=2. The broader scalar descriptors are retained in
`docs/x7_text_range_evidence.json`. `WideText` is explicitly documented as Unicode
and has BSTR get/let descriptors.

Those descriptors do not prove UTF-16/code-point/grapheme indexing. The bridge
enumerates each `Characters.Item(i,1)` and concatenates exact native `WideText`.
It derives public-to-native boundaries from reconstructed Unicode. UTF-16
surrogate halves can be joined only at complete valid boundaries. Native selected
`Start`/`End` must match the enumerated first/last character positions and content
unambiguously. The combined range must independently read back the same text and
native character count. Ambiguous/inconsistent/partial mappings are refused.

No normalization is used to compare client content. Common combining marks,
variation selectors, ZWJ sequences, emoji modifiers, regional indicators, CRLF
and Jamo boundaries are conservatively protected. This is not a complete Unicode
grapheme algorithm, a glyph-coverage check, or proof of Arabic/Indic visual shaping.
Those acceptance checks remain part of native/manual verification.

## Preservation and bounds

One ordinary unfitted/unlinked text story, at most 1024 native characters and
2048 Unicode code points. Clipping/effects, unreadable scalar formatting,
unreadable/nonordinary process fills/outlines and character background fills are
refused. Selected replacement must be nonempty, uniform and contain no paragraph
breaks or tabs; it cannot insert them or exceed the native budget.

Each native character snapshots installed X7 scalar formatting, including
spacing/kerning, language/charset, paragraph indentation/hyphenation/bullets,
basic character style and process appearance. Complete preflight snapshots include
the whole story, object/page/layer identity, native placement matrix and document coordinate
context. The inspected fingerprint must still match before writes. Basic font
style may derive a changed native `Style` within the selected range; other
unrequested scalar properties must match exactly.

After every formatting write, all unrequested character properties and surrounding
content/formatting must match the expected state. Replacement reconciles shifted
native boundaries and verifies exact prefix/suffix content/styles plus inherited
selected styling and object location. Native Single size values are represented
as Single in the request/readback expectation. No geometric fit or native size
enlargement is implied.

Post-write uncertainty stops the operation and quarantines the worker. Detected
human/collateral edits are preserved for inspection. Preflight stale-content,
style/location changes refuse with zero writes. Fingerprints provide optimistic
conflict detection, not an atomic lock against simultaneous human input.

Focused fake-COM tests: `tests/test_text_ranges.py`. The disposable Unicode,
native-selection, formatting/replacement and two-document gate is prepared in
`tests/integration/test_corel_live.py`; it remains unrun. Every registered tool
stays `implemented_unverified`.
