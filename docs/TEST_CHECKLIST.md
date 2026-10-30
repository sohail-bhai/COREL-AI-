# CorelDRAW X7 Smoke Test Checklist

- [x] COM connection to CorelDRAW X7 17.0.0.491 confirmed by user diagnostic.
- [ ] Run `python -m corel_operator.smoke_test` with the updated v0.3 files.
- [ ] Verify the script opens a new document; it should not edit the existing document.
- [ ] Open the saved CDR file in `Documents\CorelDRAW-AI-Operator-Tests`.
- [ ] Confirm a rectangle and two editable text objects are visible.
- [ ] Check page dimensions are 8.5 × 11 inches.
- [ ] Report whether text/rectangle position and size look correct.
- [ ] Then configure OpenCode MCP and call `corel_status`.
- [ ] Configure Antigravity MCP and call `corel_status`.
- [ ] Test PDF publishing separately after page creation and CDR saving work.

Do not share CorelDRAW serial numbers, license keys, credentials, or confidential client work.
