# Shared native coordination — offline report, 2026-11-15

Implemented nonblocking native-operation exclusion across cooperating bridge
processes using a per-user Windows byte-range lock and atomic ordinary JSON state.
The lock stays held through actual worker completion, context cleanup and the
final interaction-policy check. Public commands, nested calls and tracked
embedded/subclass mutations participate. Pause remains immediate and in-process.

Durable running/recovery markers survive abrupt exit or uncertain write failure.
Pure reads can preserve a recovery marker; temporary native setters refuse.
`get_native_coordination_state` returns bounded metadata without entering the COM
queue. `reconcile_native_coordination` requires the inspected fingerprint,
explicit acknowledgement and a valid connected/bound document probe. It clears
neither worker recovery nor artwork. Corrupt markers are preserved for diagnosis.

Validation:

- 18 focused coordinator tests pass, including a foreground independent process
  refused during a lease, successful access after release, abrupt process exit,
  uncertain write quarantine, verified rollback, reentrancy/thread contention,
  temporary setter refusal, stale acknowledgement, unavailable/malformed probe,
  late atomic publication failure, embedded/subclass coverage and actual schemas.
- Full default suite: 1033 tests, 1002 passed, 31 live gates skipped.
- Catalog validation: 105 registered tools, 107 registry/matrix records,
  371 native members, 306 schemas, 321 examples, 30 enum groups, 75 capabilities.
- Consolidated coverage: 105 tools, zero missing explicit native gates.

The suite caught an outer native-write marker being reset by a nested public
command; preserving the outer depth and tracking subclass leases fixes it. The
existing worker recovery regression passes. Independent-process tests also caught
an attempted read of the locked lease byte; lock initialization now occurs after
acquisition, so contention correctly returns WORKER_BUSY.

No CorelDRAW connection, live gate, existing artwork operation, provider request
or client-configuration change ran. Client image-generation handoff guidance was
added to COMPONENT_DESIGNS.md. All registered tools remain implemented_unverified.
Human same-document concurrency is unsupported; general background native
workflows, broader typography/templates/recovery/prepress and native component
replacement remain unfinished.
