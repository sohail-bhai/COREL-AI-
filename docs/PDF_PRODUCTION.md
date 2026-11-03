# Controlled PDF output and structural inspection

Implemented on 2026-11-03. Native and manual checks remain deferred.

`export_pdf_controlled` exports all bound-document pages with explicit PDF
1.4/1.7, native/RGB/CMYK color mode, embedded fonts, Unicode text, optional text
as curves, lossless bitmap compression, zero bleed and disabled printer marks.
It disables encryption, file embedding, downsampling and OPI links. It restores
every setting it changes and verifies restoration before publishing the output.
Uncertain restoration requires exact-operation worker reconciliation.

The native output is staged inside an independently created local directory.
The parser checks every page count/size and required font resource before final
publication. Final copying uses exclusive file creation and verifies the staged
bytes/SHA-256, so existing or concurrently created outputs are preserved. Failures
discard staging and any partial file created by this operation. The original CDR
is not saved or closed by this tool.

`inspect_pdf` is a local read-only tool for existing PDF files. Optional expected
page counts and per-page inch sizes produce explicit checks, as does requiring
embedded font programs. A successful parse with no expectations means structural
inspection succeeded; it does not establish project acceptance.

## Scope

- Inputs: absolute `.pdf` path, 50 MiB maximum, 1-500 pages, 10000 resource objects
  and 16 nested form levels. The dependency is `pypdf>=6.21.4,<7` with strict
  parsing and bounded cross-reference/root recovery settings.
- Page inspection: media/crop boxes, explicitly present trim/bleed boxes,
  rotation, effective dimensions and nondefault user-unit refusal. Every page
  and optional box is checked even when the returned list truncates at 100.
- Font inspection: direct and composite descendant fonts, including resources
  inside Form XObjects; nonempty embedded stream presence. It does not decode
  font programs or prove glyph coverage, legal embedding or visible text.
- Font summaries also truncate at 100 while all resource checks still run.
- `production_ready` stays false. Color mode selection does not prove accurate
  ICC conversion, spot/overprint correctness, PDF/X compliance, image resolution
  or visual fidelity. These remain explicit prepress/review work.
- Nonzero bleed is deferred. The official X7.4 property page uses conflicting
  units wording; no conversion is inferred. Zero bleed is independently safe.

The original `export_pdf` remains available with inherited-settings warnings.
Use the controlled tool when its explicit zero-bleed contract fits the job.

## Evidence and deferred gate

Installed X7 evidence is retained in `x7_pdf_api_evidence.json`: 126 descriptors
and 14 enum groups, collected without connecting to CorelDRAW. The catalog links
every controlled setting to that evidence. Twenty-two focused tests cover PDF
structure, all-page checks, direct/composite/Form fonts, native controls,
restoration, failed output, races, staging changes and worker quarantine.

`CorelDisposableDocumentLiveTests.test_controlled_pdf_live` prepares a synthetic
two-page document, verifies all changed settings return to their original values,
checks exported dimensions/fonts, saves its own source CDR and preserves an
existing output. It is prepared for the consolidated campaign and has not run.
Manual artifact review remains required after that gate.

Sources: [pypdf reader contract](https://pypdf.readthedocs.io/en/stable/modules/PdfReader.html),
[Corel X7.4 bleed property](https://community.coreldraw.com/sdk/api/draw/17.4/p/pdfvbasettings.bleed),
and [Corel PDF preflight requirements](https://help.coreldraw.com/CorelDRAW/540111192/Documentation-Windows/CorelDRAW-en/CorelDRAW-PDF-preflight-summaries.html).
