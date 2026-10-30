# Connect CorelDRAW AI Operator to Antigravity and OpenCode

The successful local smoke test showed that CorelDRAW X7 17.0.0.491 can be reached, that a new document and shapes/text were created, and that CDR save now succeeds. This is the next phase: configure the local MCP server.

## Project path currently used

`G:\sohail\COREL AI\CorelDRAW_AI_Operator_Prototype\CorelDRAW_AI_Operator_Prototype`

If you move the project folder, update all paths in the client config.

## Important: this is an MCP stdio server

Do not run `python -m corel_operator.server` manually and leave it open. Each AI client starts the MCP server itself as a child process.

## A. Antigravity

1. In Antigravity, open the agent-side-panel menu (`...`), choose **MCP Servers**, then **Manage MCP Servers** and **View raw config**.
2. This opens `mcp_config.json`. The global config is normally at `%USERPROFILE%\.gemini\config\mcp_config.json`.
3. Merge the `mcpServers` entry from `config/antigravity.mcp-fragment.json` into your existing JSON. Do not erase any existing servers or settings.
4. Save the file and refresh/reload MCP servers (or restart Antigravity).

If your file is empty/new, its contents can be the entire fragment file. If it already has other servers, copy only the entry under `mcpServers` into the existing `mcpServers` object.

## B. OpenCode

1. The global Windows OpenCode config is normally `%USERPROFILE%\.config\opencode\opencode.json` or `opencode.jsonc`.
2. If no config exists, create `opencode.json` in that folder. If one exists, merge the `mcp` server entry from `config/opencode.mcp-fragment.json` into the existing `mcp` object. Do not replace your provider/model settings.
3. Save and fully restart OpenCode.

The current OpenCode docs support local MCP servers via `type: "local"`, a command array, `cwd`, `environment`, and an enabled flag. If you prefer to limit this to the operator project only, place an `opencode.json` containing the fragment in the project root instead.

## Test in either client

First ask the client to call `corel_status` only. Expected outcome includes `connected: true`, version `Version 17.0.0.491`, and the active document name.

Then use this prompt:

> Use the CorelDRAW AI Operator MCP tools. Create a NEW 8.5 × 11 inch test document. Add a rectangle at x=1, y=8.5, width=6.5, height=1.3 inches. Add bold Arial text `MCP CONNECTION TEST` at x=1.2, y=9.0, 22 pt. Save it as a new CDR file in my Documents\CorelDRAW-AI-Operator-Tests folder using a unique filename. Do not overwrite any existing file. Execute the CorelDRAW tools; don't just describe what you would do.

Inspect the document in CorelDRAW. Do not run this on a client file.

## If a client cannot see the tools

- Confirm the configured path exactly matches this project location.
- Confirm `.venv\Scripts\python.exe` exists.
- Ensure the venv dependencies were installed (`pip install -r requirements.txt`).
- Restart the client and inspect MCP server logs/status.
- Run the diagnostic again in PowerShell.
- Share only error messages, not API keys, serial numbers, or client artwork.

## Current limitations

- This is still a prototype with a deliberately small drawing tool set.
- The client connection is not confirmed until the MCP tool list appears and `corel_status` succeeds inside the client.
- A natural-language prompt works by having the AI plan and call these tools, so prompt quality and model tool-use behavior matter.
- ChatGPT direct local MCP write access is a separate account/plan capability question and is not part of this Antigravity/OpenCode setup.
