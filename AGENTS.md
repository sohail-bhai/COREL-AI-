# Project Agent Instructions

## Azure cross-resource item incidents

Before doing project work, read `docs/HARNESS_INCIDENTS.md`.

This project has repeatedly encountered the harness error:

> The requested item was created under a different Azure OpenAI resource. Use the same resource that created the item to access it.

The exact trigger is not proven. To reduce recurrence:

1. Keep durable work in ordinary workspace files and Git commits, not managed item/file handles.
2. Prefer local `read`, `grep`, `glob`, `patch`, and foreground shell operations.
3. Keep reads and command output bounded; use targeted ranges/searches instead of retrieving very large files or pages. After Incident 6, keep individual reads at roughly 80 lines or fewer and filter potentially large shell output.
4. Use sequential tool calls. Avoid parallel tool wrappers because repeated incidents now occur during otherwise local work and the routing trigger is unknown.
5. Do not use browser preview, browser-managed files/downloads, background jobs, subagents, or cross-session resources unless the user explicitly requests them and accepts the risk.
6. Never reuse a browser file ID, managed item ID, trace artifact, or resource handle from an earlier call/session.
7. If the error occurs, do not repeatedly access the failed item. Confirm local files/Git state, record the trace ID and preceding operation in `docs/HARNESS_INCIDENTS.md`, then continue from local state.
8. Treat the issue as a harness/platform routing problem unless evidence identifies a project-code cause. Incident 7 confirms small sequential outputs also fail. The leading hypothesis is non-sticky provider routing of Azure resource-scoped response/tool item IDs; repository commands cannot fully prevent it.
9. If failures become too disruptive, preserve and push local work, then continue in a fresh session configured to stay on one provider resource/deployment. Report all trace IDs to the OpenCode/provider operator.

These constraints apply to coding workflow only; they must not weaken project tests or product safety.
