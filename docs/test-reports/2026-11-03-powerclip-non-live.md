# PowerClip offline verification — 2026-11-03

Status: `implemented_unverified`. No live CorelDRAW connection or mutation ran.

- Focused PowerClip suite: 34 passed.
- Full default suite: 606 tests, 583 passed, 23 guarded live tests skipped.
- Deferred coverage inventory: 74 registered tools, zero missing explicit native gates.
- Installed X7 evidence: 71 retained descriptors; `connection_attempted: false`.
- Online evidence: three HTTP 200 responses without readable API content;
  those responses do not confirm the requested semantics.

Coverage includes independent frame/content copies, editable text/bitmap/vector
content, stacking, contain/cover affine reconciliation, nested clip locks,
whole-name/body fingerprints, mutable curve/story alias checks, extraction and
component rebuilds. Ownership ambiguity, source changes, ignored/partial writes
and failed cleanup require worker reconciliation while inspection remains usable.

Limits and known gaps are in [../POWERCLIP.md](../POWERCLIP.md). The prepared
`CorelDisposableDocumentLiveTests.test_powerclip_workflows_live` gate uses its own
fixtures and saves CDR/PDF evidence. Native getters, copy/group/coordinates,
extraction identities, rendered clipping and manual artifact review remain pending.
