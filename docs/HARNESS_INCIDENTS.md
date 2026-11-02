# Harness Incident Log

This log records recurring OpenCode/Azure item-access failures so future sessions can avoid depending on cross-resource managed artifacts.

## Error signature

```text
The requested item was created under a different Azure OpenAI resource.
Use the same resource that created the item to access it.
```

## Recorded incidents

| Incident | Date | Trace ID | Context immediately before report | Conclusion |
|---:|---|---|---|---|
| 1 | 2026-10-30 | `f4b6b368c8741119973bda5d22e300b9` | Capability-catalog research had used direct web reference calls and an in-app browser tab while investigating protected Corel documentation pages. | A browser/managed artifact may have contributed, but the exact failed item was not identified. Browser/preview/background artifact use was stopped. |
| 2 | 2026-10-30 | `e3a10f9c3f54b04e71bec4e9da1c6d53` | Version/result-contract work was continuing with local patch, read, grep, and foreground shell operations. No browser preview, subagent, or background job had been used after Incident 1. | The recurrence shows the browser is not a proven sole cause. Platform resource routing or another managed response item may be involved. The same trace was reported in two consecutive user messages and is counted once. |
| 3 | 2026-10-30 | `77546a40a2491c92ae3777728d56ba78` | The completed v0.6 feature branch had been pushed, followed by a sequential local `git switch main`. No browser, preview, subagent, background job, or cross-session handle was used. | Ordinary local Git activity does not create an Azure item, so the error is increasingly likely to be harness/provider routing rather than a repository operation. |
| 4 | 2026-10-30 | `ceb10f86f4b61647fa12de32a30b30a2` | Reported immediately after Incident 3, without an intervening project tool call. | Confirms that avoiding a particular project command cannot guarantee prevention. Continue minimizing managed/parallel operations and preserve all work locally in Git. |
| 5 | 2026-10-30 | `bacb6bc0971c8c9fdc5866375d4e311b` | Occurred immediately after a small sequential local `grep` used to locate registry records. No browser, parallel wrapper, background job, subagent, preview, or managed item was used. | Further confirms a provider/harness routing fault independent of repository command type. Prevention cannot be guaranteed from project workflow; local files and frequent Git commits remain the reliable recovery path. |
| 6 | 2026-10-30 | `de567845bd8f62fac414c2167f6ab8bd` | Request ID `20261030175919304938962lnjXXiFt`. Appeared while OpenCode rendered a 175-line local file-read result; the user supplied a screenshot showing the failed item immediately below the read operation. | Stronger evidence that larger tool outputs may be retained as managed items and later routed across Azure resources. Cap reads/output to small chunks (about 80 lines maximum) and avoid large rendered results. |
| 7 | 2026-10-30 | `1c36ff46e747cb133f1daf28f775f50b` | Appeared after a local temporary script and a short catalog-validator traceback. The output was small, sequential, and contained no browser/preview/background artifact. | Confirms output size is not the root cause. Most likely the provider routes a session/item lookup between Azure resources even though Azure item IDs are resource-scoped. |
| 8 | 2026-11-02 | response `resp_04ed6db6bfadb686006ae85b4468108…` (user report; no trace ID supplied) | Reported while continuing the retained Alhamdulillah V2 work. The failed response was truncated, so its exact immediately preceding operation is unavailable from durable local state. | Continue from repository files, keep calls sequential and bounded, and give the provider operator the response ID if a full trace becomes available. |

**Unique incident count:** 8

## Current root-cause hypothesis

Azure OpenAI stored response/tool “items” are scoped to the Azure resource that created them. OpenCode or its model router appears to occasionally send a later turn or item lookup to a different Azure resource. That resource cannot retrieve the earlier item, producing this exact error. The incidents occur after unrelated local commands and even without intervening tools, so repository code cannot be the cause.

The provider-level fix is sticky routing to one Azure resource/deployment for the full session, or transmitting full message/tool content rather than referencing resource-scoped item IDs. Project-side mitigations can preserve work but cannot guarantee prevention.

## Required mitigation

- Store plans, findings, diagnostics, and generated content directly in repository files.
- Commit and push completed batches so work does not depend on session artifacts.
- Use targeted local reads and searches; avoid unnecessarily large tool responses.
- Keep individual file reads at roughly 80 lines or fewer and filter shell output before returning it.
- Use sequential calls only; avoid parallel tool wrappers while the routing cause remains unknown.
- Avoid browser review/preview items, browser file IDs, background jobs, subagents, and cross-session handles unless explicitly needed.
- Do not retry the same failed managed item.
- After any recurrence:
  1. capture the new trace ID;
  2. note the preceding tool/action;
  3. verify `git status` and important local files;
  4. add one row here for each unique trace ID;
  5. continue from local repository state.

## What this issue is not currently known to mean

- It is not evidence that CorelDRAW COM failed.
- It is not evidence that repository files were lost or corrupted.
- It is not currently linked to an MCP tool implementation.
- It should not trigger destructive recovery, resets, or repeated remote-item access.
