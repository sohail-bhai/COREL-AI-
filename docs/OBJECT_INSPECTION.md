# Focused object inspection (INS-002)

**Implemented:** 2026-11-03

**Status:** `implemented_unverified`; fake-COM and catalog gates pass.
The disposable X7 gate is prepared and has not been run for this batch.

`get_object_bounds`, `get_text_properties`, and `get_fill` inspect only the
explicitly bound document. They never connect, bind another document, select
objects, activate a page/layer, or edit artwork.

## Selectors and identity

Supply exactly one `object_name`, positive 1-based `shape_index`, or signed
`object_reference`. References inspect nested groups and other pages using the
[ID-001 scope/lifecycle contract](OBJECT_REFERENCES.md). Legacy names are
literal, case-sensitive, nonblank strings of at most 256 characters. Lookup
covers top-level shapes on the bound document's active page. Duplicate names
return `AMBIGUOUS_SELECTOR`; missing names/indexes return `OBJECT_NOT_FOUND`.
A name lookup on a page exceeding 10000 objects refuses to claim uniqueness;
an explicit index reads one object without enumerating the whole page.

The v1 envelope's `data` contains `document_name`, `object`, and the requested
property section. `object` includes actual name, type, StaticID when available,
page/layer, active-page index, bridge-local session ID, and inspection-only ID.
Names/layer names are capped at 256 characters with explicit truncation flags.
IDs are not edit selectors and are not persistent across bridge restarts.
Closed-document detection uses the [bound-document guard](DOCUMENT_TARGETING.md).
`object_reference` is a separate accepted selector when complete identity metadata
is available; it is null otherwise. Native identity determines active-page
`shape_index`, which is null for nested or non-active-page reference targets.

## Bounds

`get_object_bounds` returns `bounds.lower_left`, `upper_right`, `center`,
`width`, and `height` in inches, rounded to four decimal places. Coordinates
use `document_ruler_bottom_left_reference`: the current ruler origin is retained.
These are Shape.PositionX/PositionY/SizeWidth/SizeHeight measurements; page-local,
facing-page, and outline-inclusive semantics are not claimed.

Document units and reference point are temporarily normalized and restored,
including after failed property reads. Missing/nonfinite dimensions, arithmetic
overflow, or failed context restoration return sanitized `COREL_COM_ERROR`.
Successful restoration of units/reference point is covered by fake-COM tests;
X7 dirty-state and selection preservation still require the live gate.

## Text

`get_text_properties` accepts `max_text_chars` from 0 through 10000 (default
2000). Zero requests metadata only. `text.content_length` reports the full
story length, and `content_truncated` explicitly identifies a capped preview.
Empty text is distinct from an unreadable story. Non-text shapes are rejected.

The `text` section also contains `font`, `size_points`, nullable `bold`/`italic`,
and raw `bold_code`, `italic_code`, `underline_code`, and `alignment_code`.
`formatting_scope` is `whole_story_aggregate`; this does not prove uniform
character formatting. Undefined tri-state values remain null rather than false.
`unavailable_properties` identifies failed reads; `indeterminate_properties`
identifies aggregate values that cannot describe a single style.
Font names are capped at 256 characters with `truncated_properties` reporting.
Text subtype, character runs, spacing, missing fonts, and overflow are deferred.

## Fill

`get_fill` returns the actual fill type and a uniform color in its native model.
RGB, CMYK, gray, and supported spot/Pantone values retain their original channels
and tint. No conversion methods are called. No fill is distinct from an
unreadable fill type, which returns `COREL_COM_ERROR`.

`fill.detail_scope` is `type_and_uniform_color`. Fountain/pattern/texture and
unknown fills retain their type without invented color details. Unsupported
color models retain their model/type code and null channel values. Missing
uniform color/channels appear in `unavailable_properties`; capped color/spot
names and hex strings appear in `truncated_properties`.
Standalone `get_outline` remains research-required until width units are proven.

## Verification

`tests/test_object_inspection.py` covers selectors, bounds/context failures,
Unicode and capped content, indeterminate formatting, native colors, bounded
summaries, artwork preservation, and strict request/result schemas.
`tests/test_server_contract.py` covers serialized dispatch.

The guarded `test_focused_object_inspection_live` creates only synthetic artwork
in a new document, checks known geometry/text/RGB and duplicate-name refusals,
and verifies unchanged selection/page/layer/units/reference/dirty state after
inspection. It retains a unique CDR, JSON readback, and dated report. See
[TESTING.md](TESTING.md) for the opt-in command and authorization boundary.
