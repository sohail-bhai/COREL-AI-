# Typography implementation: automated evidence

Date: 2026-11-03. Target: CorelDRAW X7 17.0.0.491.
Status: `implemented_unverified`; live verification deferred by the user.

Implemented `list_fonts`, `add_paragraph_text`, and `set_text_style`. Extended
`get_text_properties` with native layout/overflow/spacing metadata. Read the
installed type library without connecting to CorelDRAW and researched X7
paragraph, overflow, character-spacing and word-spacing documentation.

Validation:

- Default suite: 399 tests run, 387 passed, 12 gated live tests skipped.
- Focused typography: 22 tests passed.
- Catalog: 50 registered tools, 52 records, 138 API inventory members,
  156 examples, 35 adapter capabilities; schemas and cross-links pass.
- Static diagnostics: passed with `connection_attempted: false`.
- Git whitespace check: passed.

Meaningful checks cover literal/bounded font search and unreadable entries,
complete availability beyond the default result limit, absent/oversized catalogs,
native paragraph argument order and mixed charset, lower-left frame coordinates,
line-break normalization, whole-story styling with preserved content/geometry,
mixed prior formatting, null preservation, signed targeting after reordering,
replacement/foreign-page refusal, linked/fitted/unknown scope refusal, actual
font substitution and nonfinite bounds, redacted partial failures, worker recovery
quarantine, strict runtime schemas, and invalid boolean/oversized numeric inputs.

The prepared native gate has not run. Font substitution, frame-count behavior,
actual X7 paragraph geometry, mixed charset and scripts/glyphs remain unverified.
Spacing writes, auto-fit and linked/per-run editing are still roadmap gaps.
