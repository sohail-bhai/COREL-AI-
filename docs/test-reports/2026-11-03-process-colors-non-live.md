# Controlled process colors non-live verification — 2026-11-03

`set_process_color` remains `implemented_unverified`. No live CorelDRAW
connection/mutation, client artwork or browser preview was used.

- Focused process-color suite: 18 passed.
- Full default suite: 552 tests, 531 passed, 21 live gates skipped.
- Catalog: 69 registered tools, 71 records, 214 native members, 183 schemas,
  213 examples, 18 enum groups and 54 adapter capabilities; validation passed.
- Deferred campaign rebuilt with the process-color native gate candidate.

Tests cover exact RGB/CMYK model/channels, factory conversion refusal before
shape assignment, ignored/converted/partial writes, vector/text preservation,
ordinary-outline width and other-channel retention, explicit non-uniform fill
replacement, unsupported groups/bitmaps/outlines and worker quarantine.

Installed X7 inspection retains 274 appearance/transparency/clipping descriptors
and five enums with no application connection. The current wrapper uses only
the process-color subset. Native color fidelity, ICC/PDF-X/separation and spot
workflows, printed/visual correctness and outline-width units remain pending.
