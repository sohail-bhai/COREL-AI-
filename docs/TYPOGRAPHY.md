# Editable typography in X7

Status: `implemented_unverified`. Native and visual checks remain deferred to
the consolidated campaign. Three tools extend the common editing surface.

- `list_fonts(name_contains="", max_results=100, max_scan=5000)` reads CorelDRAW's
  catalog without requiring a bound document. Filters are literal and ignore
  case. At most 1000 matches and 10000 entries are exposed/scanned. An additional
  match proves result truncation. Unreadable entries and exhausted scan budgets
  produce explicit incomplete reasons. Presence does not prove glyph coverage
  or that a requested bold/italic face exists.
- `add_paragraph_text(text, x_inches, y_inches, width_inches, height_inches, ...)`
  creates an editable frame on the bound document's active layer. Coordinates
  locate the lower-left in document ruler inches. The native call receives
  `(left, top, right, bottom)`, with `top=y+height`. Text is limited to 100000
  characters; dimensions are 0.001-200 inches. Style options are font, 1-500
  point size, bold, italic, none/single underline, and left/right/center/justify/
  force_justify alignment. The verified mixed charset default (`-1`) replaces
  an ANSI assumption for this new tool. Line-break normalization is reported;
  other content mismatches fail.
- `set_text_style(...)` applies supplied properties to the whole story, preserving
  null properties. Select by one unique active-page name, index, or signed
  `object_reference`. References can address nested text; the referenced page
  must be active for editing. Mixed prior formatting may be explicitly replaced.
  Linked, fitted, or unreadably scoped text is refused before writing.

Font writes and paragraph creation require a complete bounded catalog check.
An absent font fails before editing; unreadable/oversized catalogs cannot prove
availability. Case-insensitive requests use the exact catalog spelling. Every
requested style property is read back and compared, including font substitution
and point-size tolerance of 0.01. Success reports actual styles, signed object
identity when available, and finite actual bounds. Editing uses font properties;
it does not resize the shape to scale glyphs.

`get_text_properties` now also returns `text.layout`: native subtype, frame count,
overflow, and raw character/word/line spacing plus line-spacing type code.
Unavailable data is null and named explicitly. Artistic text has no paragraph
overflow verdict. X7's `Text.Overflow` describes the entire linked story; it does
not determine whether an individual frame or artistic object fits a safe area.
Inspection does not link frames, fit text, select shapes, or change typography.

The new mutations participate in [worker recovery](WORKER_RECOVERY.md). A failure
after a native write or uncertain readback blocks follow-up mutations until
inspection and exact-ID reconciliation. No generic rollback, replay, or auto-fit
is performed by the original typography mutations. Independent copied-paragraph
fitting is now covered separately in [TEXT_FITTING.md](TEXT_FITTING.md).
Bounds inspection restores the original units/reference point;
failed restoration remains an error.

## Evidence and remaining work

The installed 17.0 type library was read without connecting to CorelDRAW.
[Reproducible inspector](../scripts/inspect_x7_typography_api.py) and
[signature/enum evidence](x7_typography_api_evidence.json) record the results.
Creation uses cdrTriState parameters; TextRange.Bold/Italic properties are Boolean.
The X7 alignment and underline values are independently confirmed in that file.

Primary online documentation:

- [X7 paragraph creation](https://community.coreldraw.com/sdk/api/draw/17/m/layer.createparagraphtext)
- [X7 linked-story overflow](https://community.coreldraw.com/sdk/api/draw/17/p/text.overflow)
- [X7 character spacing](https://community.coreldraw.com/sdk/api/draw/17/p/textrange.charspacing)
- [X7 word spacing](https://community.coreldraw.com/sdk/api/draw/17/p/textrange.wordspacing)

Line/paragraph spacing now has researched units and guarded write controls in
[TEXT_SPACING.md](TEXT_SPACING.md), with 23 focused checks. Character/word spacing
scales still require evidence before exposing write controls. Still pending:
per-run formatting, glyph/font-face coverage, linked/fitted story edits, broader
safe-area/artistic fitting, multilingual visual review, and template reflow.
[Copied paragraph fitting](TEXT_FITTING.md) now passes 28 focused non-live checks;
native/visual acceptance remains deferred.

`test_typography_live` is prepared in the disposable-document integration suite.
It checks native title formatting, paragraph bounds, chain overflow, content,
font absence refusal, color, context restoration, and saved editable artwork.
It closes only its owned target and fails on cleanup errors. It does not run
unless both existing live-test environment gates are explicitly enabled.
