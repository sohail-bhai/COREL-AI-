# Document organization offline verification — 2026-11-03

Status: `implemented_unverified`. No live CorelDRAW connection or mutation ran.

- Focused suite: `python -m unittest discover -s tests -p test_organization.py -q`;
  38 passed.
- Full suite: `python -m unittest discover -s tests -q`; 714 tests,
  688 passed, 26 guarded live tests skipped.
- Catalog: 84 tools, 86 records/matrix rows, 303 native members,
  226 schemas, 258 examples, 28 enum groups and 65 adapter capabilities.
- Deferred campaign: 84 tools, zero missing explicit native gates.
- Installed inspection: 47 descriptors, `connection_attempted:false`.

Checks exercise complete bounded structural readback, session fingerprints,
native page/local/master ownership, exact page/layer activation, cross-page
signed-reference admission, Unicode-capable names, explicit-size appended
pages, ordinary layer creation and visible/editable/printable flags.

Stale/malformed inputs, ambiguous identities, foreign roots, unreadable flags,
nonfinite dimensions, exhausted scan budgets, duplicate names and master/special
edits are refused. Temporary inch entry and original unit restoration reconcile.
Successful preflight clears only its proven temporary unit stage, so stale-state
refusals leave the worker available. Partial writes quarantine later mutations
while structure inspection remains available.

Known empty new containers can be discarded after original recorded structure
is rechecked. Foreign/populated/unknown/lost receipts, original changes, failed
cleanup and uncertain command-group begin/close prevent verified recovery.
Calls and failed command-group operations are not replayed; no native undo runs.
Recorded preservation covers structure and root membership, not descendant
geometry, artwork appearance or concurrent external edits.

Readable X7 page/layer help confirms the workflow requirements. Two SDK requests
returned HTTP 200 without readable API content. Evidence and limitations are in
[../DOCUMENT_ORGANIZATION.md](../DOCUMENT_ORGANIZATION.md).

Prepared gate: `CorelDisposableDocumentLiveTests.test_document_organization_live`.
Disposable page/layer/artwork fixtures prepare native state, CDR and PDF files.
Native lifecycle/units, active contexts, rendered visibility and printing still
require the user-deferred consolidated campaign and artifact review.
