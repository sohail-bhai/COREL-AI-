# Upgrade from v0.4 to v0.5 (keep your existing Antigravity connection)

The current user's existing project is:

`G:\sohail\COREL AI\CorelDRAW_AI_Operator_Prototype\CorelDRAW_AI_Operator_Prototype`

Do not replace the Antigravity config; the existing server already connected successfully.

## 1. Back up the two files

In the existing project folder, copy these files to a temporary backup location:

- `corel_operator\corel_bridge.py`
- `corel_operator\server.py`

## 2. Replace only those two files

From this v0.5 package, copy:

- `corel_operator\corel_bridge.py`
- `corel_operator\server.py`

into the matching `corel_operator` directory in your existing project.

Replace `requirements.txt` with this project's version, or edit its MCP line to:

`mcp>=1.28,<2`

Your venv should already use MCP v1 after the last fix. If needed, run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 3. Restart the MCP server

Completely quit Antigravity and reopen it. This causes its MCP child process to restart with the new tools.

## 4. Verify new tool list

Ask Antigravity:

> Call `corel_status` and `list_objects` only. Do not edit, create, save, or import anything. Report the target-document binding status and the tool results.

`corel_status` should report whether a target document is bound. Until `create_document` is called, the bridge does not silently choose an active file for mutation. This is intentional to protect client work.

## New v0.5 tools

- `use_active_document` — explicitly permits targeting the active document only when `confirm_existing_document=True`
- `list_objects` — lists named objects, positions, sizes, and text where available
- `set_fill_color` — RGB fill
- `set_outline` — outline RGB and width, or remove outline with width 0
- `move_object` — set an object's bottom-left reference point in inches
- `resize_object` — resize bounding box; optionally preserve aspect ratio
- `set_text_content` — edit text objects
- `rename_object` — give objects stable names
- `duplicate_object` — duplicate objects with offsets
- `import_artwork` — import local artwork from common image/vector formats

Newly created objects receive stable names such as `AI_Text_001` unless a name is provided. Prefer `object_name` over shape indexes because indexes can change as objects are added.

## Safe first test

Use a new document. Prompt Antigravity to create a new 8.5 × 11 inch document, add a rectangle named `panel`, add bold editable text named `title`, set the panel fill to RGB (20, 45, 90), set a white outline, then call `list_objects`. Save it to a unique `.cdr` filename under Documents\CorelDRAW-AI-Operator-Tests.

Don't run destructive test operations on customer work. The current prototype intentionally has no delete-object tool.
