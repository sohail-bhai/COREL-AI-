# PDF prepress non-live validation - 2026-11-05

Validated the retained implementation on `feature/workflow-planning-slice`.
No CorelDRAW application connection or live verification ran.

- `.\.venv\Scripts\python.exe -m unittest discover -s tests`: 901 tests,
  871 passed, 30 guarded live tests skipped.
- `.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_pdf*.py'`:
  all 48 focused PDF production/prepress tests passed.
- `.\.venv\Scripts\python.exe scripts\validate_catalog.py`: passed;
  92 registered tools, 94 records, 314 native members, 272 schemas, 282 examples.
- `.\.venv\Scripts\python.exe scripts\build_verification_campaign.py --check`:
  current inventory, 92 tools, zero missing explicit native gate candidates.

The focused suite covers native bleed conversion, all-page trim/bleed checks,
supported nested/aliased PDF resources, spot/ICC inventory, overprint defaults,
malformed inputs and bounds, settings restoration, output identity and late
publication failures preserving concurrent user edits.

Direct package-style focused test invocation initially failed because these
fixtures import sibling modules from the discovery path. The documented
discovery invocation above resolves them and passes.

Native units, marks, artwork bleed, color/separation rendering, PDF/X conformance,
export-generated effective raster DPI and manual production approval remain
pending. All registered tools remain `implemented_unverified`.
