# Whole-story horizontal spacing — non-live gate, 2026-11-15

Target: installed CorelDRAW X7 17.0.0.491; no application connection or live edits.
Feature status: `implemented_unverified`.

This batch adds whole-frame character/word spacing through explicit X7 spacing
structures, native justification limit checks, detached preparation, repeated
preflight and structure/scalar readback. Text and leading are retained; paragraph
frame bounds are checked. Exclusive apply windows and native failure quarantine
remain mandatory.

Validation:

- 29 horizontal-spacing checks pass: percent endpoints, null preservation,
  point leading, native justification limits, unavailable/mixed units/styles,
  scalar/structure disagreement, detached structure identity, preflight races,
  bounded content/geometry, stale replacement, pause/exclusive policy, native
  substitutions/failures, final-readback races, frame ownership/container/path
  refusal, column preservation, worker quarantine and strict runtime schemas.
- All 29 fitting checks pass, including the added spacing-then-fitting regression:
  negative character and nondefault word percentages survive on an independent
  editable fit copy, while source content, frame and measured state are retained.
- Full default suite: 1063 tests, 1032 passed, 31 guarded live gates skipped.
- Catalog: 106 registered tools, 108 registry/matrix records, 383 native members,
  310 checked schemas, 324 examples, 31 enum groups and 76 adapter capabilities.
- Consolidated inventory: 106 tools, zero missing explicit native gates.

Checks used the repository's `.venv/Scripts/python.exe` and its MCP 1.x runtime.
System Python has MCP 2.x and cannot load this project's FastMCP entry point;
no dependency or client configuration was changed.

The first focused pass caught a temporary unit-setting bounds context before
the intended native spacing boundary. Preflight now reads raw native geometry
and context with no setters, allowing clean refusal of concurrent edits and
pause requests. Final measured readback is followed by another preservation
check. The complete suite also required the expected catalog/capability totals
to account for the added tool; other existing checks passed.

Installed type-library/Python binding inspection confirms the explicit frame
enum and structure getter/setter path. X7 character API remarks and X7 user-guide
percentage/word instructions establish the chosen unit basis; X7.4 word API
remarks remain supplementary. Direct indexed API pages returned no readable
member text. Live structure/scalar unit equivalence is not claimed.

The extended disposable typography campaign covers artistic and paragraph
percentages, negative character spacing, limit refusal, leading/content retention
and spacing-then-fitting, with editable CDR/JSON evidence. It remains deferred.
No CorelDRAW connection, existing artwork change, document save or image
generation occurred. Per-run/glyph/appearance/anchor acceptance and broader
fitting remain gaps. All registered tools stay `implemented_unverified`.
