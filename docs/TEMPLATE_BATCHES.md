# Reusable text templates and CSV production

Implemented on 2026-11-03; native and manual verification remain deferred.

Four MCP tools provide a complete source-preserving text personalization job:

1. `inspect_text_template` captures a grouped template, named text fields, signed
   source reference, measured structure, geometry, text and basic appearance.
2. `read_template_csv` reads UTF-8 CSV into literal strings, preserving zeros,
   quoted/multiline values and formula-looking text. Headers and every row must
   be complete. Source lines and a file SHA-256 support reconciliation.
3. `plan_template_batch` maps columns to unique text names, validates all records,
   duplicates and optional field regions, and returns deterministic placements.
4. `execute_template_batch` requires that complete plan and its fingerprint,
   checks the source again, and creates a separately owned editable document.

Cards, certificates, labels and tickets can use the same mechanism. Every record
can have several copies, with full and partial final sheets. Leading zeros are
strings throughout. Extra columns are reported; duplicate rows require explicit
`allow` or `copies_per_record`. Default overflow policy discards an unacceptable
owned output; `report` retains it with explicit failed fit checks.

## Boundaries and verification

Limit inputs to 2 MiB, 1000 records, 128 columns, 10000 characters per cell,
1000 template nodes and 16 nested group levels. Jobs allow 2000 items and 500
pages; each page has at most 100 items and a conservative reference-scan budget.
Copies preserve the original template size; no implicit resizing or auto-fit.

Native root/page/layer/child identities must agree. Source and copies cannot
share shape identities. Final readback visits every output item, verifies text
and formatting, static component geometry and basic appearance, record counts,
page dimensions and field/item bounds. Only the first 100 item/fit summaries and
eight field summaries per item are returned; truncation is explicit.

Mapped fields require uniform readable whole-story formatting. Linked or fitted
stories are refused. Artistic text needs a declared field region to establish
its intended field box; otherwise its measured bounds are checked against the
whole item. Paragraph overflow uses native readback. These checks establish
neither glyph coverage nor visual/print readiness. Complex effects, clipping,
per-run styles, template image fields and font substitution need further work.

The system clipboard is replaced during copying and this is reported. The
source active page/layer, units and reference point are restored. Measured source
preservation has the explicit scope above; it is not a full native file diff.
Failures close only the independently created output, verify open-document
membership and source observations, and quarantine uncertain cleanup through
the existing exact-operation recovery protocol.

## Evidence

- Installed X7 signatures: `x7_template_api_evidence.json`, read without connecting
  to CorelDRAW; copy/paste returns and page APIs are retained as descriptors.
- 24 focused non-live tests: `tests/test_template_jobs.py`, including foreign
  paste, reused duplicates, shared stories, static corruption, nonactive source
  pages, malformed CSV/styles, overflow and verified/unverified cleanup.
- Deferred disposable native gate:
  `CorelDisposableDocumentLiveTests.test_template_batch_live`. It saves synthetic
  source/output CDR and PDF artifacts, checks full/partial pages and rejects an
  overflowing job. Manual artifact review must still check all rows and visuals.

Requirements references: Corel's
[print merge guide](https://product.corel.com/help/CorelDRAW/Documentation-Windows/CorelDRAW-en/CorelDRAW-Print-merge.html)
and [imposition guide](https://product.corel.com/help/CorelDRAW/Documentation-Windows/CorelDRAW-en/CorelDRAW-Imposition-layouts.html).
They describe workflow expectations; installed X7 evidence establishes the
native API baseline. The bridge does not invoke Print Merge or printer drivers.
