# Tool and Compatibility Versioning

**Revision:** 2026-10-30

CorelDRAW application versions, bridge releases, MCP tool schemas, compatibility profiles, and catalog formats are separate version domains. They must never be treated as interchangeable.

## 1. Bridge package version

The Python bridge will use Semantic Versioning:

- `0.x.y` while tool schemas and behavior remain experimental;
- patch increment for compatible fixes and documentation/test corrections;
- minor increment for backward-compatible tools or optional fields;
- major increment for intentional incompatible changes after a stable public contract exists.

The authoritative bridge version is `0.6.0`, defined in `corel_operator/version.py` and exported as `corel_operator.__version__`. `corel_status` and every result envelope read from the same source.

## 2. Tool schema version

`tool_schema_version` versions model-facing request and response semantics independently of package implementation.

Initial value: `1`.

Increment it only when a client must change how it constructs a request or interprets a response. Examples:

- renaming/removing a field;
- changing units or coordinate anchors;
- changing a selector's identity semantics;
- replacing the current result envelope with an incompatible response shape;
- changing confirmation behavior incompatibly.

Adding an optional field with a safe default normally does not require a schema-major change, but it does require a bridge minor release and registry/changelog update.

### Tool-schema v1 result envelope

Every registered tool returns:

- `ok`: success/failure boolean;
- `tool`: stable MCP tool name;
- `bridge_version`;
- `tool_schema_version`;
- `profile_id`;
- `target_document`: known target identity or `null`;
- `data`: operation-specific object on success, otherwise `null`;
- `warnings`: array of warning strings;
- `error`: `null` on success or `{code, message, details}` on failure;
- `duration_ms`.

The v0.5 success dictionary is preserved under `data`. The former unstructured `{error: string}` result is replaced by the stable error object in v0.6.

## 3. Capability profile

Initial profile ID: `coreldraw-x7-17`.

The profile identifies the application-major compatibility boundary, not the bridge version.

Profile metadata must include:

- product name and major version;
- verified builds;
- explicit ProgID preference;
- official reference root;
- per-capability support and test status;
- last live verification date.

A future CorelDRAW version receives a different profile and adapter. Do not scatter version checks through tool implementations or assume a newer version behaves identically.

The current implementation is `corel_operator/adapters/x7.py`. It owns ProgID order, major-version validation, verified X7 constants, unit names, and capability support details. Individual tools consume the adapter rather than duplicating version checks.

## 4. Catalog schema versions

Each machine-readable catalog carries its own format version:

- `registry_schema_version` for `mcp_tool_registry.json`;
- `schema_version` for API inventory and enum-reference files.

These values describe file structure for tooling and tests. They are not MCP protocol or bridge versions.

## 5. MCP SDK/protocol version

The current server imports `mcp.server.fastmcp.FastMCP` from MCP Python SDK v1 and requires:

```text
mcp>=1.28,<2
```

The installed environment inspected during catalog creation contains MCP SDK 1.30.0. Migrating to SDK v2 requires a deliberate bridge release, updated imports/configuration, schema regression tests, and client verification. It must not occur as an incidental dependency upgrade.

## 6. CorelDRAW versions and file versions

Keep these values distinct:

- Application version/build, such as `17.0.0.491`.
- COM/type-library registration version; X7 is registered as hexadecimal major `11`, equivalent to decimal 17.
- CDR save-format enum, such as `cdrCurrentVersion = 0` or `cdrVersion17 = 17`.
- Capability profile ID, `coreldraw-x7-17`.

The save-format value does not prove which CorelDRAW application is running.

## 7. Tool status lifecycle

Allowed statuses:

```text
planned
research_required
implemented_unverified
verified
unsupported
deprecated
```

Normal progression:

```text
planned
  -> research_required (when evidence is incomplete)
  -> implemented_unverified
  -> verified
```

Other transitions:

- Any state may become `unsupported` when evidence shows the capability is unavailable or unsafe for the profile.
- `verified` returns to `implemented_unverified` when behavior changes, a regression appears, or the implementation no longer matches its recorded evidence.
- Public tools become `deprecated` before an intentional incompatible removal whenever practical.

## 8. Verification policy

`verified` requires all of the following:

1. X7 documentation and/or installed type-library evidence.
2. Stable tool schema and error behavior.
3. Unit/schema tests.
4. Guarded live test on the target X7 profile when CorelDRAW behavior is involved.
5. Actual-state inspection after mutation.
6. Dated test evidence and known limitations in the repository.

Historical narrative reports are retained as evidence but are normalized to `implemented_unverified` until reproduced under this policy.

## 9. Compatibility rules

- Keep registered tool names stable.
- Add optional parameters rather than near-duplicate tool aliases.
- Never silently change inches to another unit or change the coordinate anchor.
- Never broaden destructive behavior under an existing harmless-looking tool name.
- Reject unsupported profiles with a stable error instead of attempting a best guess.
- Keep provider-specific image/vision APIs outside the CorelDRAW adapter.
- Update catalog, tests, documentation, and changelog in the same change as a tool contract.

## 10. Authoritative version source

The authoritative module is:

```text
corel_operator/version.py
```

It contains or exposes:

- bridge package version;
- tool schema version;
- supported capability profile IDs.

`corel_operator.__init__`, result envelopes, tests, catalog schemas, and `corel_status` use these values. Future packaging metadata must also read from this source rather than duplicating literals.
