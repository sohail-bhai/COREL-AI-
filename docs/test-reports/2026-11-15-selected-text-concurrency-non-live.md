# Selected text and concurrency — offline report, 2026-11-15

Branch: `feature/workflow-planning-slice`. Bridge 0.7.0, tool schema v2.
No CorelDRAW application connection, mutation, native test or manual artifact
approval occurred. Installed type-library reads do not connect to CorelDRAW.

## Validation

- 21 focused selected-text checks pass: exact captured selection, zero/one-based
  native positions, code-point and UTF-16 surrogate mapping, malformed/ambiguous
  Unicode refusal, mixed formatting, uniform replacement, prefix/suffix
  preservation, stale content/style/placement, concurrent preflight changes,
  collateral/partial-write failure, boundaries/limits and actual strict schemas.
- 15 focused policy checks pass: paused startup, exclusive confirmation,
  reserved inactive-document/background allowlist, switch/rebind/close refusal,
  temporary context write guards, direct-client bypass prevention, immediate
  pause during an in-flight fake call and pause-versus-resume ordering.
- Full default suite: **989 tests; 958 pass; 31 guarded live tests skipped**.
- Catalog: **98 tools**, 100 records/matrix rows, 371 native members, 289 schemas,
  300 examples, 30 enum groups and 75 adapter capabilities.
- Consolidated inventory: all 98 tools accounted for; **zero missing explicit
  native gates**. Prepared candidates do not prove native success.
- `git diff --check` passes.

Commands: `.venv\Scripts\python.exe -m unittest discover -s tests -q`,
`scripts/validate_catalog.py`, `scripts/build_verification_campaign.py --check`.
Both live environment flags were explicitly zero for the default suite.

## API evidence and limits

`research_selected_text.py` retains installed `cdrTextIndexingType`, selection,
range and character-enumeration descriptors. `WideText` has Unicode BSTR get/let
documentation in the retained full range evidence. No global indexing assumption
is made: each story must reconstruct exact native character content and mapping.

The native placement matrix avoids conflating changed glyph bounds with object
movement. Per-character scalar/ordinary process-appearance preservation is
bounded; complete named-style relationships, glyph shaping, linked/container
stories, background fills and broader automatic fitting remain outside this batch.

Server and embedded mutations start paused. The immediate pause cannot cancel
an already-entered native call. Background mode reserves another inactive
document and permits only explicit signed/fingerprinted text-range edits. General
background CorelDRAW workflows and atomic same-document concurrency are not
claimed. A native/manual two-document campaign remains mandatory before acceptance.

Preflight refusals perform zero artwork writes and leave the worker usable.
Observed collateral/user edits and uncertain partial changes are preserved;
worker reconciliation is required instead of automatic Undo/replay. Existing fake
fault tests explicitly enter exclusive mode to retain their original safety coverage.

All 98 tools remain **implemented_unverified**. The broader saved backlog remains
incomplete; this report covers the selected-text/concurrency batch only.
