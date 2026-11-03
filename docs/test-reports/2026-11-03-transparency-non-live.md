# Native transparency non-live verification — 2026-11-03

`get_transparency` and `set_uniform_transparency` remain
`implemented_unverified`. No live CorelDRAW connection/mutation, client artwork
or browser preview was used.

- Focused transparency suite: 18 passed.
- Full default suite: 571 tests, 549 passed, 22 live gates skipped.
- Catalog: 71 registered tools, 73 records, 221 native members, 188 schemas,
  219 examples, 21 enum groups and 56 adapter capabilities; validation passed.
- Deferred campaign rebuilt with the uniform-transparency native gate candidate.

Tests cover explicit unavailable metadata, non-uniform inspection/replacement,
percentage/scope/normal-merge readback, ignored/partial native writes, removal,
measured vector/bitmap geometry and base-appearance preservation, unsupported
groups, closed targets and worker quarantine with continued read-only inspection.

Installed X7 appearance evidence now retains 274 descriptors and six enums
without application access. Catalog constants validate exact transparency
scope/normal-merge codes. The later gate creates synthetic vector/text/bitmap
fixtures and its own CDR/PDF outputs; native rendering, bitmap pixel identity,
printed appearance and full complex-effect preservation remain unverified.
