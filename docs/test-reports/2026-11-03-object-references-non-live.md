# ID-001 object references — non-live report

Date: 2026-11-03. Status: `implemented_unverified`.

Implemented signed, ordinary-JSON bridge/document/page/layer/group/native shape
references in eleven common inspection/edit tools. Resolution independently
establishes complete scoped identity/StaticID uniqueness within 10000 entries
and 32 group levels, refreshes reordered indices, and rejects stale/ambiguous
targets before editing. No COM proxies are persisted in references. Missing
identity metadata emits null. Rename/duplicate return fresh references.

Evidence:

- `python -m unittest discover -s tests`: 314 tests, passed; ten live gates skipped.
- `tests/test_object_references.py`: 31 safety/dispatcher/schema tests passed.
- `tests/test_server_contract.py`: all eleven reference wrapper arguments covered.
- `scripts/validate_catalog.py`: passed; 44 registered tools, 46 records,
  126 API members, 138 validated examples, 32 adapter capabilities.
- `python -m corel_operator.diagnostics --static-only`: passed; X7 registration
  detected, `connection_attempted: false`.
- `git diff --check`: passed.

Cases include reordered pages/layers/groups, nested duplicate names, master
layer page scope, deleted/replaced objects/pages/layers/parents, changed
metadata, duplicate native identities/StaticIDs, malformed/altered references,
closed/reopened documents, bridge restart, incomplete traversal, cycles,
unreadable COM metadata, and exact nested edits through the real dispatcher
thread with fake COM objects. Active-page index now compares native identity.

Primary X7 StaticID documentation confirms shape-lifetime stability. It does
not establish cross-session persistence. The synthetic
`test_object_references_live` gate is prepared for the user-requested later
consolidated campaign; no CorelDRAW connection or live gate was run in this batch.
See [OBJECT_REFERENCES.md](../OBJECT_REFERENCES.md).
