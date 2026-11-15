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
