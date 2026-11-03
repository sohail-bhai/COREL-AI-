# Redacted operation records (SAFE-001)

**Implemented:** 2026-11-03. Recording is disabled by default.

All 47 MCP tools have optional operation events, including pure planning tools.
Enable recording by setting `COREL_OPERATION_LOG_DIR` to an absolute directory
outside this repository before starting the MCP server. Environment files are
not loaded automatically. No files or logging output are created when disabled.

```powershell
$env:COREL_OPERATION_LOG_DIR = 'C:\Users\ADMIN\AppData\Local\CorelOperator\records'
```

The server creates exclusive `operations-<session>-<segment>.jsonl` files.
Existing files are never overwritten or deleted. Each segment is capped at
2 MiB, each process at eight segments, and each event at 32 KiB. Capacity or
filesystem failure disables further recording for that process and adds a
fixed warning to subsequent results; the operation still executes. Restart
with a working directory to resume recording. Retention/removal is manual.
Journal appends are serialized, flushed, and fsynced. Canonical repository
paths, including resolved junction/symlink aliases, are refused.

## Event contract

An enabled tool returns an optional envelope `operation_id`, a 32-character
UUID hex value. The same value correlates these JSONL events:

- `requested`: caller timestamp and top-level parameter type counts.
- `worker_started`: already-known bridge/document session IDs, read on the
  COM worker without accessing document properties.
- `worker_completed` / `worker_failed`: actual method result code, available
  created object IDs, elapsed time, and explicit rollback flags.
- `worker_cancelled`: a queued future was cancelled before running.
- `returned`: the caller's result code and elapsed time. Pure tools have only
  requested/returned events.

Records include schema/profile/bridge version and UTC timestamps. Core text,
rectangle, and ellipse creation now return object identity metadata, allowing
available StaticIDs to be recorded. Imported/duplicated objects use their
existing identity results. Extraction scans only fixed result keys within a
256-entry/five-level budget. Missing IDs remain explicitly unavailable;
recording does not invent IDs or rescan the document to find them.

If the caller times out while native work continues, `returned` carries
`OPERATION_TIMEOUT`. A later worker event records actual completion/failure.
A caller return is not proof that COM stopped. Worker completion alone does
not prove successful rollback or visual correctness. Busy/recovery mutation
gating is now implemented by [SAFE-002](WORKER_RECOVERY.md).

## Redaction and failure limits

Input summaries contain only parameter count and type counts. They contain no
values, parameter names, nested keys, text, artwork, object/document names,
filenames, paths, tokens, hashes derived from client content, or raw exception
messages. Result extraction accepts only native StaticIDs, bounded inspection
IDs, stable result codes, booleans, and duration. The writer independently
enforces this allowlist again at the disk boundary.

No record is printed to MCP stdout or stderr. An unavailable journal reports
only the fixed warning `Operation recording could not persist all events.`
The journal is diagnostic evidence, not a transaction database: a crash or
storage failure can leave requested work without a completion event. A missing
completion requires state reconciliation rather than automatic replay.
Source documents/checkpoints remain the durable recovery mechanism.

## Verification

`tests/test_operation_records.py` covers redaction/injection, no default I/O,
external-path enforcement, exclusive files, capacity, concurrent appends,
disk failure, pure tools, real dispatcher-thread events with fake COM,
late worker completion after timeout, optional envelope compatibility,
and preserved FastMCP parameter schemas. The default suite passes.

The consolidated campaign should enable recording in its unique external
output directory and inspect records for the guarded MCP creation/edit/save
flow. It must verify available native target/created IDs and separate caller
and worker events, without client content. CorelDRAW has not been connected
for this implementation batch; live tool behavior remains unverified.
