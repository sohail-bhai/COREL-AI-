# Bound-document liveness (ID-001, document guard)

**Implemented:** 2026-11-03
**Status:** Automated gates pass; consolidated X7 live evidence pending.

Every operation that uses `_target_document` verifies that the target still
belongs to the bound application's open `Documents` collection before accessing
artwork. Enumeration is capped at 1000 open documents. Comparison uses COM
IUnknown identity when available and Python identity for fake-COM fixtures;
document names and current application focus are not substitutes for identity.

The installed pywin32 `PyIUnknown` has no `GetIUnknown` method and is unhashable.
The helper queries canonical IUnknown, extracts its attached pointer from the
[documented pywin32 representation](https://github.com/mhammond/pywin32/blob/main/com/win32com/src/PyIUnknown.cpp),
and uses native IUnknown equality for membership checks. Unsupported native
identity formats or failed comparisons block use with `COREL_COM_ERROR`.
A generic in-process COM smoke check verified distinct wrappers for one object
and rejection of another object without connecting to CorelDRAW.

A closed/replaced document, changed application, lost application, or direct
unapproved binding replacement returns `NO_TARGET_DOCUMENT` and clears the
binding. The retired bound-document session is removed so an explicit rebind
cannot reuse its previous session ID. Creating a new document starts a fresh
document session; reconnecting to another application invalidates old bindings.
Renaming or saving the same live document under a new path keeps its identity.

An unreadable open-document collection or exceeded enumeration limit returns a
sanitized `COREL_COM_ERROR` before using the target. It preserves the existing
binding for possible reconciliation, without claiming the document is closed.
Busy/timeout recovery and exact-ID reconciliation are implemented by
[SAFE-002](WORKER_RECOVERY.md).

`corel_status` and `list_open_documents` clear proven stale bindings. Status can
still describe the explicitly reported active document after the target is
cleared; subsequent editing continues to require a new explicit binding.
The guard does not reconnect, activate, bind, or select another document.

## Coverage and remaining identity work

Twenty-four fake-COM tests cover closure, same-name replacements, application loss,
focus changes, proxy churn, session retirement, strict binding replacement,
collection failures/limits, status/listing, and rejection before mutation.
Existing operation tests now provide realistic open-document collections and
exercise the actual guard rather than bypassing it.

`test_closed_document_guard_live` is prepared for the consolidated campaign.
It creates and saves two synthetic documents, closes the bound first document,
verifies edit refusal and unchanged second artwork, then closes the remaining
owned fixture. See [TESTING.md](TESTING.md).

This completes the document-liveness portion of ID-001. Signed
[object references](OBJECT_REFERENCES.md) now add exact page/layer/group/native
shape identity to eleven common inspection/editing tools. Existing object_id
strings remain inspection-only, and legacy integer indexes describe current
active-page order. Required native lifecycle/persistence gates remain deferred.
