# ID-001 document-liveness guard — automated verification

- **Date:** 2026-11-03
- **Result:** Automated gates pass; consolidated X7 live gate deferred.
- **Scope:** Document portion of ID-001; object-reference resolution is next.

The bridge checks bounded open-document membership and application identity
before targeted operations. Closed/replaced/lost targets are cleared, stale
document sessions are retired, and unreadable/oversized document collections
block use without redirecting work to the active document.

| Gate | Result |
|---|---|
| Default suite | PASS — 281 tests; 9 live tests skipped |
| Focused liveness tests | PASS — 24 tests |
| Catalog | PASS — 44 registered tools; 46 records; 138 examples |
| Static diagnostics | PASS — X7 registration present; no connection attempted |

Tests cover closed and same-name-reopened documents, user focus changes,
application replacement/loss, COM proxy churn, session invalidation, explicit
binding, unreadable collections, enumeration bounds, status/listing, and
rejection before shape access/mutation. Existing operation fixtures provide
open-document collections and exercise the real guard.

Installed pywin32 inspection exposed the previous unavailable `GetIUnknown`
assumption. The corrected helper uses canonical IUnknown representation and
native equality, following the [binding implementation](https://github.com/mhammond/pywin32/blob/main/com/win32com/src/PyIUnknown.cpp).
A generic `Scripting.Dictionary` COM smoke check passed distinct-wrapper,
same-key/equality, and different-object tests without launching CorelDRAW.

The prepared two-document X7 gate uses saved synthetic fixtures and checks
closed-target refusal while the other document remains unchanged. It is skipped
by default and belongs to the consolidated verification campaign. No live,
persistent-object-ID or production-ready claim is made by this batch.
