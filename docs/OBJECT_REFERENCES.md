# Session object references (ID-001)

**Implemented:** 2026-11-03. **Status:** `implemented_unverified`.

`find_objects` and single-object inspection return `object_reference` when the
bridge can read complete native identity metadata. Pass that JSON object back
unchanged as the sole selector. The worker resolves it against the explicitly
bound document. The reference contains ordinary JSON values, opaque native
identity tokens, and a signature; it retains no shape/page/layer COM proxies.

```python
match = bridge.find_objects(text_contains="Member Alice")["matches"][0]
reference = match["object_reference"]
bridge.get_text_properties(object_reference=reference)
bridge.set_text_content("Member Bob", object_reference=reference)
```

Accepted by `get_object_info`, `get_object_bounds`, `get_text_properties`,
`get_fill`, `set_fill_color`, `set_outline`, `move_object`, `resize_object`,
`set_text_content`, `set_text_style`, `rename_object`, and `duplicate_object`. References support
nested groups and duplicate names. Legacy names/indexes remain explicit
top-level active-page selectors. Inspection-only `object_id` strings and
`shape_path` arrays are not reference selectors.

## Identity and scope

Each reference records bridge/document session, page/layer native identity,
ancestor group identities, native shape identity, StaticID, full object name,
type, and diagnostic page/layer/path indices. A bridge-local secret produces
opaque HMAC tokens and authenticates the entire reference. Raw COM pointers
are not returned. Authentication is an integrity check for bridge-issued
selectors, not an authorization mechanism for arbitrary files or operations.

Resolution finds the recorded page/layer by native identity, then completely
walks that layer's groups. It requires one exact native shape identity and
unique StaticID within that scope, matching name, type, and group ancestry.
Indices are refreshed after reorder and do not determine the target. A master
layer shown on several pages has a separate page-scoped reference per appearance.

Reordering pages, layers, shapes, or group children preserves targeting.
Deleting/replacing objects or their page/layer, changing shape type/name, moving
to another layer/page/group, reopening the document, or restarting the bridge
requires fresh inspection. Rename and duplicate return fresh references in
their `object` result; the renamed object's old name reference is stale.
References are not persistent project IDs. Undo/redo/native identity behavior
requires fresh inspection when the native identity changes and remains subject
to the deferred X7 gate. Pointer reuse alone cannot authorize a replacement:
the native StaticID and all recorded metadata must also match.

Missing/unreadable StaticID, unavailable native identities, overlong names
(more than 256 characters), or incomplete issuance metadata return
`object_reference: null`. Names are never truncated into reliable selectors.
Search can emit references while its overall results are truncated; the later
resolution independently establishes complete scope uniqueness.

## Limits and errors

Resolution is capped at 10000 page/layer/shape entries and 32 group levels.
Oversized collections are refused before enumerating them. Duplicate native
identity/StaticID, cycles, and incomplete traversal return `AMBIGUOUS_SELECTOR`,
even if a plausible match was already found. Deleted/replaced identities and
foreign bridge/document sessions return `OBJECT_NOT_FOUND`; a proven closed
document uses the existing `NO_TARGET_DOCUMENT` guard. Malformed/altered
references return `INVALID_ARGUMENT`; conflicting selectors are ambiguous.
Unreadable native metadata returns sanitized `COREL_COM_ERROR` before editing.
There is no name/index fallback from a stale reference.

Inspection never activates a page/layer or changes selection. A reference edit
requires its page to be explicitly active and refuses before writing otherwise.
Bounds use the existing document-ruler coordinate contract; facing-page,
page-local, and outline-inclusive geometry is not claimed. Active-page
`shape_index` readback is null for nested or non-active-page objects; it is
derived from native identity rather than duplicate names.

## Evidence and deferred verification

X7's official [StaticID contract](https://community.coreldraw.com/sdk/api/draw/17/p/shape.staticid?lang=vb)
describes a unique integer that remains constant during a shape's lifetime.
It does not establish cross-document or cross-session persistence. The bridge
uses bounded enumeration instead of a first-match native FindShape shortcut.
Native IUnknown handling follows the installed pywin32 contract documented in
[DOCUMENT_TARGETING.md](DOCUMENT_TARGETING.md).

`tests/test_object_references.py` covers scope, reordering, aliases, deletion,
replacement, metadata changes, session retirement, limits, sanitation, schema
round trips, and real dispatcher-thread routing using fake COM. The disposable
`test_object_references_live` gate measures native proxy/ID stability through
stacking reorder, nested editing, rename/duplicate/delete, save/reopen, and
bridge restart. It uses the official X7
[ShapeRange.OrderToFront](https://community.coreldraw.com/sdk/api/draw/17/m/shaperange.ordertofront)
and [Application.OpenDocument](https://community.coreldraw.com/sdk/api/draw/17/m/application.opendocument?lang=cs)
APIs only on its own synthetic file. The gate remains skipped for the later
consolidated verification campaign; native persistence is not live verified.
