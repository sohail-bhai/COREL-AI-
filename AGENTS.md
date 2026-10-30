# Project Agent Instructions

## Azure cross-resource item incidents

Before doing project work, read `docs/HARNESS_INCIDENTS.md`.

This project has repeatedly encountered the harness error:

> The requested item was created under a different Azure OpenAI resource. Use the same resource that created the item to access it.

The exact trigger is not proven. To reduce recurrence:

1. Keep durable work in ordinary workspace files and Git commits, not managed item/file handles.
2. Prefer local `read`, `grep`, `glob`, `patch`, and foreground shell operations.
3. Keep reads and command output bounded; use targeted ranges/searches instead of retrieving very large files or pages.
4. Use sequential tool calls. Avoid parallel tool wrappers because repeated incidents now occur during otherwise local work and the routing trigger is unknown.
5. Do not use browser preview, browser-managed files/downloads, background jobs, subagents, or cross-session resources unless the user explicitly requests them and accepts the risk.
6. Never reuse a browser file ID, managed item ID, trace artifact, or resource handle from an earlier call/session.
7. If the error occurs, do not repeatedly access the failed item. Confirm local files/Git state, record the trace ID and preceding operation in `docs/HARNESS_INCIDENTS.md`, then continue from local state.
8. Treat the issue as a harness/platform routing problem unless evidence identifies a project-code cause. Incidents 3–5 occurred without browser/managed-file access; incident 4 appeared without an intervening project tool call, and incident 5 followed only a small local grep.

These constraints apply to coding workflow only; they must not weaken project tests or product safety.
