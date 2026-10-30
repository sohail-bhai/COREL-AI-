# Upgrade to v0.6

v0.6 introduces a versioned result envelope and new package modules. Keep the existing Antigravity/OpenCode MCP configuration; the server name, command, module entry point, and existing tool names have not changed.

## Important response change

v0.5 returned operation-specific fields directly and failures as:

```json
{"error": "message"}
```

v0.6 returns one contract for every tool:

```json
{
  "ok": true,
  "tool": "corel_status",
  "bridge_version": "0.6.0",
  "tool_schema_version": 1,
  "profile_id": "coreldraw-x7-17",
  "target_document": null,
  "data": {},
  "warnings": [],
  "error": null,
  "duration_ms": 1.0
}
```

Read operation-specific fields from `data`. On failure, `data` is `null` and `error` contains `code`, `message`, and `details`.

## Upgrade procedure

1. Ensure valuable client documents are closed or backed up. The upgrade itself does not need to open CorelDRAW.
2. Preserve the existing project/MCP configuration.
3. Update the project from Git, or copy the complete current `corel_operator/` package. Do not copy only `server.py` and `corel_bridge.py`; v0.6 also requires `errors.py`, `results.py`, and `version.py`.
4. Keep MCP SDK v1 and reinstall requirements if needed:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

5. Run non-COM checks:

   ```powershell
   .\.venv\Scripts\python.exe -m unittest discover -s tests -v
   .\.venv\Scripts\python.exe scripts\validate_catalog.py
   ```

6. Fully restart Antigravity/OpenCode so it launches a fresh MCP child process.
7. Call `corel_status` only. Confirm:
   - top-level `ok` is `true`;
   - `bridge_version` is `0.6.0`;
   - `tool_schema_version` is `1`;
   - `profile_id` is `coreldraw-x7-17`;
   - CorelDRAW version/build and runtime metadata appear under `data`.

Do not begin mutation regression tests on an active client file. The guarded disposable-document integration suite will be introduced separately.

## Compatibility

- Existing MCP tool names and input arguments are unchanged.
- Success and failure response shapes changed intentionally.
- Models or scripts that read fields directly must now read them from `data`.
- Models or scripts that checked for a top-level error string must now check `ok` and `error.code`.
