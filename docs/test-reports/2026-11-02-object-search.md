# INS-001 Object Search Verification

- **Date:** 2026-11-02 (Asia/Calcutta)
- **Result:** PASS for default tests and catalog/schema validation
- **Capability status:** `implemented_unverified`
- **Live X7 search test:** Prepared, skipped; no live search run performed

## Implemented contract

`find_objects` searches the bound document with literal name/text/type filters,
explicit page/layer scope, and optional depth-first group traversal. Duplicate
names are retained with page/layer/group paths. Result, scan, and depth limits
and cycles report incomplete coverage. Names/text previews are bounded. COM
failure returns a sanitized error instead of a partial successful result.
No document/page/layer activation, selection, edit, or connection is required.
IDs/paths remain inspection-only.

## Default verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_object_search.py
```

Result: 20 focused tests passed. Coverage includes scoped filters, duplicates,
group paths, Unicode case folding, literal matching, depth limits, exact-size
result/scan boundaries, empty-page/layer scan budgets, cycles, master locations,
bounded summaries, unbound targets, input validation before document access,
sanitized COM failures, and actual output/schema agreement.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result: 221 tests run successfully; seven explicit live gates skipped.
This includes 214 passing default tests and serialized MCP-dispatch/envelope
coverage for the new search tool.

```powershell
.\.venv\Scripts\python.exe scripts\validate_catalog.py
```

Result: PASS. 41 registered tools, 45 registry/matrix records, 126 inventoried
API members, 100 schemas, 135 examples, 12 enum groups, 29 adapter capabilities.
Catalog validation also passes inside the final default suite.

## Installed X7 evidence

Read-only inspection of
`C:\Program Files\Corel\CorelDRAW Graphics Suite X7\Programs64\CorelDRAW.tlb`
confirmed `IVGShape.Shapes`, `IVGShapes.Item/Count`, `IVGPage.AllLayers/Layers`,
`IVGLayer.Shapes`, and `cdrTextShape=6` / `cdrGroupShape=7`.
Type-library existence is separate from live traversal/persistence behavior.

## Remaining gate and continuation

`CorelDisposableDocumentLiveTests.test_find_objects_live` creates only new
synthetic two-page artwork, checks nested duplicate names and scoped/limited
search, and verifies selection, active page/layer, unit/reference point, and
dirty-state preservation. It retains non-overwriting CDR, JSON readback, and a
dated report when explicitly enabled. See [TESTING.md](../TESTING.md).

Next implementation tickets: INS-002 focused text/bounds/fill inspection and
ID-001 stale document/object references. Do not promote search to `verified`
until the disposable X7 gate and its evidence review pass.
