# Concurrent CorelDRAW work

The server starts with native editing paused. Research, local planning and local
artifact preparation can continue while the user works. CorelDRAW has no proven
atomic lock against human input, and a native call already running cannot be
cancelled. Simultaneous edits to the same document are not a supported contract.

## Reserved document mode

Prepare/bind an AI work document during a short exclusive setup, then activate
another document for personal work. Call `configure_editing_mode` with
`mode="background_document"` after the AI document is inactive. The policy pins
that document's COM identity; it does not follow the foreground document.

Background mode currently permits only `edit_text_range`. It requires a signed
object reference, exact inspected Unicode range/content and fingerprint. No
selection, page activation, application-wide options, save, Undo, document
creation or export is used on this path. Other native mutations require
exclusive mode until individually audited for shared-context effects.
Read tools with temporary native unit/reference setters obey the same policy
at their write markers; pure reads such as `inspect_text_range` can continue.

Every write boundary verifies that the reserved document is still open, bound
to the same application and inactive. The dispatcher also checks before reporting
success. Switching to the AI document or rebinding stops later writes. Existing
in-flight writes may have happened; partial failures require operation-ID
reconciliation and review. No rollback can overwrite a detected concurrent edit.

Keep the AI document reserved. Editing its objects through another interface or
switching documents during a native call is not an atomic, conflict-free workflow.
Fingerprints detect observed source changes; the tiny read/write race cannot be
eliminated with COM preflight. Native focus behavior still needs the deferred
disposable two-document campaign and manual acceptance.

## Pause and exclusive mode

`pause_native_editing` sets a Python event immediately, without waiting for the
COM queue. Subsequent native write boundaries stop. An already-running COM call
continues until it returns. A pause arriving while configuration runs wins over
that older resume request. `get_operator_state.accepting_mutations` becomes false.

Resume using `configure_editing_mode`. `mode="exclusive"` additionally requires
`confirm_exclusive=true`, representing the user's confirmation that they have
stopped editing. This mode enables existing native workflows in short agreed
apply windows. Recovery quarantine remains independent and must be reconciled.

This policy is enforced by the MCP dispatcher, tracked bridge edits and native
write markers. Direct embedded `CorelBridge` clients also start paused and must
explicitly configure their mode. Unknown embedded native operations are refused
in background mode. Use the dispatcher for immediate pause and worker recovery.

## Client migration

Bridge 0.7.0 uses tool schema v2 because startup confirmation behavior changed.
The result envelope has the same shape. Clients must configure an editing mode
before native mutations. A preflight policy refusal leaves the worker usable;
failures after a write require the existing explicit reconciliation protocol.

Tests: `tests/test_interaction_policy.py`. Native coverage:
`test_selected_text_and_background_policy_live`, deferred and unrun.

## Multiple AI clients

Codex and Antigravity can each prepare local plans and image files. Cooperating
bridge processes now share one nonblocking native-operation lease per OS user.
Each public bridge command, tracked embedded mutation and dispatcher operation
holds the lease through completion, including context restoration and the final
dispatcher policy check. Nested commands share the lease. A second native client
receives `WORKER_BUSY` before entering its operation. A caller timeout does not
release the lease while the worker is still running.

The lease uses a Windows byte-range file lock (POSIX flock for offline portability).
Production state is under `%LOCALAPPDATA%/CorelDRAW-AI-Operator/native-v1` on Windows.
It contains only method, process, operation ID and phase; no design text or paths.
All cooperating clients must run the updated bridge under the same OS user and
use this common directory. Raw COM scripts and older bridge versions do not
participate. Human input still follows the reserved-document/exclusive policy.

Every lease stores a durable running marker before entering native work. A crash
leaves it behind. A failure after a native write stores `recovery_required`,
unless rollback was explicitly verified. Releasing the OS lock does not clear
uncertainty. Missing/corrupt state cannot be repaired by deleting the marker as
part of normal operation; preserve corrupt state for investigation. Pure guarded
reads and explicit document binding can proceed during recovery, but their native
write markers refuse temporary setting changes.

Use `get_native_coordination_state` to inspect the marker immediately. After
reviewing any partial changes, connect and explicitly bind the reviewed document,
then call `reconcile_native_coordination` with that exact fingerprint and
`acknowledge_partial_changes=true`. It requires a complete bound-document probe,
refuses a busy lease or changed fingerprint, and performs no Undo, replay, save
or rebind. This probe describes the current bound document; it cannot prove that
all effects in a previous client were reviewed. The acknowledgement represents
that review. If the original worker also has recovery quarantine, reconcile it
separately using its operation ID. Shared recovery does not clear worker recovery.

Offline evidence: `tests/test_native_coordination.py` includes independent-process
exclusion, abrupt process exit, nested/subclass writes, temporary setter refusal,
late state-publication failure and fingerprinted acknowledgement. The deferred
selected-text/background native gate includes the real bound-document recovery
probe; it has not run.
