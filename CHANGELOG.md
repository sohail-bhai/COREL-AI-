# Changelog

All notable changes to the CorelDRAW AI Operator will be documented in this file.

The project follows Semantic Versioning while experimental and keeps tool-schema compatibility separate from package versions. Dates use `YYYY-MM-DD`.

## [Unreleased]

## [0.6.0] - 2026-10-30

### Added

- Evidence-backed initial capability catalog for the 17 registered v0.5 MCP tools.
- Partial current-use CorelDRAW X7 API inventory based on official X7 class references and read-only inspection of the installed X7 type library.
- MCP tool registry with request/response schemas, permissions, confirmation policy, API dependencies, test state, and limitations.
- Capability matrix covering registered tools and the next approved inspection/batch capabilities.
- X7 enum reference for units, reference points, save/export constants, tri-state values, text defaults, and shape type codes used by the bridge.
- Explicit unsupported/research-required register.
- Product/tool/profile/catalog versioning policy.
- Local catalog validator that checks JSON Schemas, server-tool parity, API references, evidence IDs, CSV/registry parity, and duplicate records without starting CorelDRAW.
- Authoritative bridge version, tool-schema version, and capability-profile constants in `corel_operator/version.py`.
- Tool-schema v1 success/error envelope with operation duration, warnings, target identity when known, and operation-specific `data`.
- Stable expected error codes and safe fallback handling for unexpected exceptions.
- `corel_status` runtime metadata for bridge, schema, profile, ProgID, connection mode, Python, MCP SDK, pywin32, and CorelDRAW version/build.
- Fifty default tests covering versions, result envelopes, schemas/examples, validation, units, targeting, paths, dispatcher behavior, and status metadata; one live CorelDRAW test is skipped unless explicitly enabled.
- v0.6 upgrade guide documenting the response migration and complete package-copy requirement.
- Persistent harness-incident log and future-agent safeguards for recurring Azure cross-resource item failures.

### Changed

- Normalized all registered tools to `implemented_unverified` until historical successes are reproduced in a dated disposable-document test report.
- Wrapped prior v0.5 success dictionaries under `data`; all tools now use one deterministic top-level contract.
- Removed the unconfirmed dynamic `Application.Caption` read from `corel_status`.
- Added controlled `CorelDispatcher.close()` behavior for tests and future shutdown handling.
- Rejected Boolean RGB channel values instead of accepting them as Python integers.

### Security

- Documented the prohibition on arbitrary Python, shell, VBA, macro, and unrestricted COM execution.
- Documented confirmation, overwrite, active-document, local-file, and external-upload safety boundaries.
- Unexpected exception messages are no longer returned directly to MCP clients; only the exception type is included in safe details.

### Compatibility note

- v0.6 intentionally replaces the legacy direct success dictionary and `{error: string}` failure shape. Tool-specific success fields are now inside `data`; clients should first check `ok` and then inspect `data` or `error`.

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
