# Worker state and guarded reconciliation (SAFE-002)

**Implemented:** 2026-11-03. **Status:** `implemented_unverified`.

The dispatcher admits one native call at a time. It refuses concurrent calls
before enqueueing, caps its queue at 32 entries, and uses a 120-second caller
timeout. A pending timed-out call is cancelled before execution. Running native
work continues; the dispatcher never terminates it or automatically retries it.
Cancelled entries cannot later edit a document.

## State and outcome tools

`get_operator_state` and `get_operation_status(operation_id)` read bounded
Python metadata immediately, without connecting to or calling CorelDRAW.
Local planning tools also remain available while native work is busy.

| State | Meaning | Native follow-up calls |
|---|---|---|
| `idle` | No active native call | Reads allowed; mutation also requires no recovery block and available queue capacity |
| `running` | A call is pending or running | Refused with `WORKER_BUSY` |
| `timed_out_but_running` | Caller stopped waiting while native work continues | Refused with `WORKER_BUSY` |
| `unavailable` | Worker stopped, failed startup, or is closing | Refused with `WORKER_UNAVAILABLE` |

Execution state and recovery state are separate. After a late mutation completes,
the worker can be idle while `recovery_required` remains true. Further edits,
imports, saves, and exports then return `RECOVERY_REQUIRED`. Inspection remains
available once native work has stopped.

Operation IDs are generated even with disk recording disabled. Timeout and
completed-error envelopes include their ID. Outcome history retains 64
metadata-only entries and pins the unresolved recovery operation. It contains
method/status/timing, known result/created IDs, rollback flags and a native-busy
flag, never arguments, text, paths, names, or raw exception messages. It does not
retain shape/document COM proxies or full result payloads.

## Recovery policy

- Late mutation success requires native reconciliation before further edits.
- Uncertain mutation failure or unverified rollback requires reconciliation and
  explicit acknowledgement of any partial changes.
- A verified rollback leaves known state. A preflight refusal is treated as safe
  only when the tracked bridge proves the native edit stage has not started.
- Validation error codes after an edit are still partial failures. Nested calls
  cannot erase an outer operation's edit stage. Unclassified future methods are
  conservatively mutating.
- Native read failures require a successful probe; they do not require claiming
  partial artwork changes. A successful late read releases the busy state.
- Unit/reference restoration failures after operations are errors and block unsafe
  continuation rather than silently reporting success.

COM rejected/busy HRESULTs are recognized through at most eight exception-chain
links. No native call is replayed. An unresolved modal dialog or busy application
can make reconciliation fail; the original recovery block then remains intact.

## Reconciliation flow

1. Poll metadata until the native operation has a terminal outcome.
2. Inspect its outcome and the actual bound document with the available read tools.
3. Call `reconcile_operator_state` with the exact recovery operation ID. For an
   uncertain failed mutation, explicitly set `acknowledge_partial_changes=true`
   only after reviewing the current state.
4. Continue with a deliberate next operation after successful reconciliation.

The probe executes on the same COM worker. It verifies bounded open-document
membership, application/document identity, active-page membership and finite
page/count/unit/reference/dirty metadata. It never reconnects, activates, binds
another document, edits artwork, undoes, or repeats the earlier operation.
Closed/replaced/lost targets become explicitly unbound and require a later
explicit binding. A malformed, stale-ID, failed or incomplete probe cannot clear
recovery, even when acknowledgement is supplied.

Reconciliation reports current state; acknowledgement does not prove rollback,
visual correctness, or file-output validity. Existing-document checkpoints and
specialized workflow rollback remain separate roadmap requirements. A caller
must not interpret `OPERATION_TIMEOUT` as permission to repeat the same edit.

Shutdown refuses new jobs and waits for native work. A shutdown timeout reports
incomplete termination without killing CorelDRAW. Native proxies are released
on their owning STA before COM uninitialization. Process restart begins unbound;
it does not recover old in-memory IDs or infer that an earlier edit completed.

## Evidence and deferred verification

The [Python 3.11 Future contract](https://docs.python.org/3.11/library/concurrent.futures.html)
states that running work cannot be cancelled and that a result timeout only
limits the caller's wait. Microsoft documents
[busy/rejected COM HRESULTs](https://learn.microsoft.com/en-us/windows/win32/com/com-error-codes-3)
and [rejected-call handling](https://learn.microsoft.com/en-us/windows/win32/api/objidl/nf-objidl-imessagefilter-retryrejectedcall).

`tests/test_worker_recovery.py` covers state, concurrency, pending cancellation,
deadline races, late success/failure, native busy errors, partial edits,
restoration failure, pinned history, stale IDs, schema round trips, strict
reconciliation and shutdown. The guarded `test_worker_recovery_live` uses its
own native synthetic document, delays return after an edit to force a caller
timeout, injects a failure after a second native edit, checks recovery and
redacted events, and saves the fixture. Real modal/busy behavior still needs a
controlled manual check on disposable artwork during the consolidated campaign.
No native gate has run for this batch.
