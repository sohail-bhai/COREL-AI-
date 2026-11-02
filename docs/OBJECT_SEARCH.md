# Bounded object search (INS-001)

**Implemented:** 2026-11-02

**Status:** `implemented_unverified`; default fake-COM tests pass, X7 live gate pending.

`find_objects` inspects the bridge's explicitly bound document. It does not
connect to CorelDRAW, bind another file, activate a page/layer, select objects,
or edit artwork. An unbound bridge returns `NO_TARGET_DOCUMENT`.

## Inputs

| Input | Default | Meaning and limit |
|---|---|---|
| `name_contains` | `""` | Literal substring, at most 256 characters |
| `shape_type_code` | `null` | Optional nonnegative X7 shape-type code; text is 6, group is 7 |
| `text_contains` | `""` | Literal story-text substring, at most 1024 characters; matches text shapes only |
| `page_index` | `null` | All pages, or an explicit positive 1-based page index |
| `layer_name` | `""` | All applicable layers, or an exact layer name of at most 256 characters |
| `max_results` | `100` | 1–1000 returned matches |
| `include_nested` | `true` | Traverse `cdrGroupShape` children |
| `case_sensitive` | `false` | Applies to name, text, and layer filters; default uses Unicode case folding |
| `max_depth` | `8` | 0–16; top-level objects have depth 0 |
| `max_scan` | `5000` | 1–10000 total page, layer, and shape visits |

All filters combine with AND. An empty request is a valid bounded inspection.
An out-of-range page returns `OBJECT_NOT_FOUND`, even when no layer matches.
Regex, CQL, macros, and arbitrary COM expressions are not accepted.

Example MCP arguments:

```json
{
  "name_contains": "title",
  "shape_type_code": 6,
  "text_contains": "Member",
  "page_index": 1,
  "layer_name": "Artwork",
  "max_results": 25,
  "include_nested": true
}
```

## Results and completeness

The standard tool-schema v1 envelope contains `document_name`,
`document_session_id`, `matches`, `scanned_objects`, `scanned_entries`,
`truncated`, and `incomplete_reasons` under `data`.

Each match carries its name, available StaticID/object ID, type, page/layer
indices, layer name, group depth, and 1-based path within the layer. Traversal
uses page order, layer order, and depth-first shape collection order. Duplicate
names produce separate matches. Master-layer objects can appear on multiple
pages with the same StaticID and distinct page locations.

Names and layer names are capped at 256 characters, text previews at 160.
Separate truncation flags describe these summaries; filtering uses the full
strings. Non-text objects have a null text preview. Missing StaticIDs produce
null IDs rather than a fabricated identity.

`truncated: true` means enumeration is incomplete. `incomplete_reasons` can
contain `max_results`, `max_scan`, `max_depth`, or `cycle`. A result cap is
reported only after one additional matching object proves that matches were
omitted. Scan/depth caps can hide matches even when the returned list is empty.
Do not use incomplete results to prove absence, uniqueness, or a total count.
An unexpected COM failure returns a sanitized `COREL_COM_ERROR` without a
partial successful result.

IDs and paths describe this inspection and are not edit selectors. Session IDs
are bridge-local; shape paths change after reorder/regroup, and StaticID
persistence across reopen/restart is unverified. Existing edits continue to
require a unique active-page name or an explicit active-page shape index.
Closed-document/reference detection is tracked separately as ID-001.
PowerClip, symbols, and other non-group containers are outside this traversal.

## Verification

`tests/test_object_search.py` covers bounds, duplicates, nested groups, multiple
pages, master layers, literal/Unicode filtering, no mutation, cycles, and errors.
`tests/test_server_contract.py` checks serialized dispatch and result envelopes.
The installed X7 type library confirms the group/text members and shape codes.
`test_find_objects_live` is prepared in the guarded disposable-document suite;
see [TESTING.md](TESTING.md) for explicit opt-in. Live evidence is required before
promoting the capability status.
