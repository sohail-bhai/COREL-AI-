# SAFE-001 operation records — non-live report

Date: 2026-11-03. Recording is opt-in; native tool verification remains pending.

All 44 MCP tools record metadata-only events when an absolute external
`COREL_OPERATION_LOG_DIR` is configured. Exclusive bounded JSONL files preserve
prior logs. Caller/worker events share an optional result-envelope operation ID.
Core text/rectangle/ellipse creation now returns available native identity.
Input/output content, names, paths, and raw COM errors are excluded at both
extraction and writer boundaries. Nested design-plan and flat imposition
rollback booleans are recorded without copying confidential detail fields.

Validation:

- Default suite: 334 tests passed; ten guarded live gates skipped.
- Twenty focused journal/MCP/dispatcher tests passed.
- Catalog validation: passed; 44 registered tools, 46 records, 126 API members,
  138 validated examples, and 32 adapter capabilities.
- Static diagnostics: passed; `connection_attempted: false`.
- `git diff --check`: passed.

Meaningful cases cover no default filesystem I/O, external canonical paths,
injection/redaction, unavailable IDs, bounded/cyclic extraction, existing file
preservation, log capacity, concurrent JSONL events, disk failure with no
stdout/stderr, optional envelope compatibility, unchanged FastMCP parameter
schemas, pure tools, and actual dispatcher threads with fake COM operations.
A bounded fake operation proves the caller's timeout is recorded first and the
worker's later actual completion is a distinct event under the same ID.

No CorelDRAW connection was made. The later consolidated campaign should enable
the journal in its unique external output directory and verify native IDs and
caller/worker correlation for the guarded MCP creation/edit/save flow.
SAFE-002 busy/timeout mutation gating remains the next implementation ticket.
