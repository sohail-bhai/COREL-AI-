# Changelog

All notable changes to the CorelDRAW AI Operator will be documented in this file.

The project follows Semantic Versioning while experimental and keeps tool-schema compatibility separate from package versions. Dates use `YYYY-MM-DD`.

## [Unreleased]

### Added

- Evidence-backed initial capability catalog for the 17 registered v0.5 MCP tools.
- Partial current-use CorelDRAW X7 API inventory based on official X7 class references and read-only inspection of the installed X7 type library.
- MCP tool registry with request/response schemas, permissions, confirmation policy, API dependencies, test state, and limitations.
- Capability matrix covering registered tools and the next approved inspection/batch capabilities.
- X7 enum reference for units, reference points, save/export constants, tri-state values, text defaults, and shape type codes used by the bridge.
- Explicit unsupported/research-required register.
- Product/tool/profile/catalog versioning policy.
- Local catalog validator that checks JSON Schemas, server-tool parity, API references, evidence IDs, CSV/registry parity, and duplicate records without starting CorelDRAW.

### Changed

- Normalized all registered tools to `implemented_unverified` until historical successes are reproduced in a dated disposable-document test report.

### Security

- Documented the prohibition on arbitrary Python, shell, VBA, macro, and unrestricted COM execution.
- Documented confirmation, overwrite, active-document, local-file, and external-upload safety boundaries.

### Runtime behavior

- No MCP or CorelDRAW runtime behavior changed in this catalog-only batch.

## [0.5.0] - Historical prototype

### Added

- Explicit active-document binding confirmation.
- Object listing and bridge-generated object names.
- RGB fill and outline controls.
- Move, resize, text replacement, rename, and duplicate operations.
- Local artwork import.
- Single serialized COM worker thread.
- CDR/PDF overwrite protection.

### Known state

- Repository documentation reports successful CorelDRAW X7 connection, an Antigravity `corel_status` call, editable text/rectangle creation, and CDR save.
- Most v0.5 additions did not receive recorded live tests.
- No authoritative package version constant or automated test suite existed.
