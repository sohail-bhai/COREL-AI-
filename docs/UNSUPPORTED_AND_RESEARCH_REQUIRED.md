# Unsupported and Research-Required Capabilities

**Revision:** 2026-11-03

**Target profile:** `coreldraw-x7-17`

This document prevents uncertain behavior from being presented as supported. An item remains here until evidence, implementation, and the required tests justify a catalog status change.

## Outstanding native verification dependencies

The table retains historical uncertainties. New inspection, identity/recovery,
typography, transforms, vector, appearance, templates and PDF wrappers now have
offline gates; their native/manual verification remains deferred. Current
implementation coverage and remaining work are tracked in
[CURRENT_IMPLEMENTATION_PRIORITIES.md](CURRENT_IMPLEMENTATION_PRIORITIES.md).

| Area | Current uncertainty | Required evidence before verification |
|---|---|---|
| Application caption | `Application.Caption` was not found in the official X7 Application class or installed type-library property map and was removed from `corel_status` in v0.6 | Keep unsupported unless future X7 evidence demonstrates a reliable member |
| Outline width | `Outline.Width` exists, but the inspected evidence does not prove the bridge's value is in points | Set several known widths in a disposable document, read them back under controlled document units, and visually inspect one result |
| Text insertion coordinates | `CreateArtisticText` is confirmed, but insertion point/baseline versus resulting bounds is not recorded | Create text at known coordinates and compare insertion point with actual bounds |
| Text charset | The type-library default is `cdrCharSetMixed (-1)` while the bridge explicitly passes ANSI `0` | Test ASCII and non-ASCII text; select an explicit documented policy |
| Font substitution | Font and size are now read back, but no recorded X7 run demonstrates substitution behavior | Compare requested and actual formatting on X7 with available/missing fonts |
| Rectangle/ellipse bounds | Actual bounds are returned and fake-COM tested, but not reproduced in a dated X7 run | Verify position and size after creation on a disposable X7 document |
| Drawing origin | Absolute movement assumes the document's drawing origin does not invalidate page-relative reasoning | Inspect origin and test movement in a disposable document |
| Resize anchor | Width/height properties are set without an explicit anchor policy | Test with each relevant reference point and standardize the operation |
| Object identity | StaticID/layer/page/type are now returned, but names remain mutable, indexes change, and StaticID persistence semantics are untested | Test StaticID uniqueness/persistence across reorder, save/reopen, and server restart |
| Nested objects | `Page.Shapes` enumeration behavior for groups and nested objects is not defined at the MCP boundary | Define top-level versus recursive traversal and test nested groups |
| Import filters | `Layer.Import` exists, but every allowlisted extension has not been tested in this X7 installation | Use non-confidential fixtures and record pass/fail per extension/filter |
| Import identification | Imported StaticID/layer/page metadata is returned, but selection-based detection and collection-position fallback still need live verification | Test one- and multi-object SVG/PDF/AI imports and inspect selection/range behavior |
| Import path safety | Extension and size limits exist, but UNC/device paths and allowed-root policy are not explicit | Define normalized path policy and unit tests before broad use |
| Save options | Enum values and properties are confirmed, but the full effective file settings are not read back | Save/reopen a disposable CDR and inspect version, pages, editability, and expected content |
| PDF output | Nonempty output existence is verified, but page dimensions, structure, and inherited settings are not inspected | Verify a unique PDF, inspect page box dimensions, and report unchecked settings |
| COM timeout | The MCP caller can time out while the COM worker continues executing | Design cancellation/recovery or explicit busy-state behavior and test a controlled timeout |
| Closed target document | The in-memory COM proxy can become stale if the user closes the target | Detect stale targets and return a stable error without falling back to another active document |
| Cross-page group copying | X7 `Shape.CopyToLayer` exists but failed for the disposable cross-page repeat group; the verified `Shape.Copy` / `Layer.Paste` fallback replaces system clipboard contents | Keep the clipboard warning in the approval plan and investigate a non-clipboard equivalent before removing this limitation |

## Planned capabilities requiring API expansion

The following remaining directions need further API/output research and bounded
implementation. Existing wrappers stay `implemented_unverified` until their
applicable consolidated checks pass:

- page orientation and multi-page activation;
- master/page layer traversal and layer state;
- mixed/linked text, spacing writes, glyph coverage and safe automatic fitting;
- native spot/ICC/separation workflows and proven outline-width units;
- patterns, transparent/nonlinear gradients, broader blending/group effects and
  in-place PowerClip edit mode. Opaque direct process gradients, uniform
  transparency and source-preserving clip/extract/rebuild workflows are implemented;
- layer/page organization, guides and outline-aware safe-area reflow;
- contour offsets, adjacent-node fitting/cropping and broader nested shaping;
- bitmap effective DPI, links, crop, and replacement;
- preview export with deterministic resolution and color settings;
- bleed, safe-margin, overlap, font, color, and asset preflight.

These are not exposed simply because related members appear on an X7 class page. Exact signatures, enum semantics, side effects, and rollback behavior must be cataloged first.

## Currently unsupported by product policy

The following capabilities are intentionally not exposed:

| Capability | Reason |
|---|---|
| Arbitrary Python execution | Grants unrestricted local-machine access and bypasses tool schemas/safety |
| Arbitrary shell execution | Same risk; not a CorelDRAW design capability |
| Arbitrary VBA/macro execution | Bypasses allowlisting and can mutate documents/application state unpredictably |
| Unrestricted COM member invocation | Raw API access is too broad and difficult to validate safely |
| Silent overwrite | Risks destroying CDR, PDF, image, or batch output |
| Automatic active-document mutation | Window focus is not sufficient authorization or identity |
| Automatic upload of user artwork | Confidential artwork must not leave the machine without explicit informed approval |
| “Print-ready” based only on export success | Production readiness depends on job-specific checks that may not have run |
| Claiming every UI feature is automatable | UI commands and object-model APIs are not equivalent |

## Deferred external capabilities

These are neither implemented nor promised for the current milestone:

- image generation through a provider API;
- background removal through an external provider/package;
- vision-model reference comparison;
- direct ChatGPT local write access for account types that do not officially support it;
- CorelDRAW versions other than X7/major 17;
- UI automation fallback for API-inaccessible dialogs/features;
- printer-driver-specific automation and press certification.

Provider selection, credentials, data-sharing consent, cost, and retention policy must be decided before any external adapter is added.

## Status-change rule

An item can leave `research_required` only when:

1. its X7 member/signature or bridge algorithm is documented;
2. input/output and failure semantics are defined;
3. safety and confirmation class are assigned;
4. non-live validation tests pass;
5. a disposable-document live test passes when CorelDRAW behavior is involved;
6. the result and limitations are recorded in the catalog and changelog.
