# Consolidated verification campaign

User decision: live verification runs later, once across all implemented
features. No gate in this document has run as part of the current implementation.

`catalog/verification_campaign.json` inventories every registered MCP tool.
Build or check it with:

```powershell
.\.venv\Scripts\python.exe scripts\build_verification_campaign.py
.\.venv\Scripts\python.exe scripts\build_verification_campaign.py --check
```

Each entry distinguishes local tests, native gate candidates, native execution,
MCP envelope verification and manual artifact review. Candidates are derived
from test call sites; their presence does not establish complete assertions or
live success. Missing explicit native gates must be prepared before the run.
Two planned catalog records are excluded because they are not registered tools.

The prepared campaign includes synthetic document/page/layer inspection,
object search/identity/liveness, common edits/grouping/import/save, fonts and
paragraph styles, transforms/distribution/order, numbering/design plans,
raster print placement, contour/imposition, text templates/CSV and controlled
PDF output, editable line/cubic paths, node/handle edits and source-preserving
shaping/compound curves. The vector gate explicitly covers native closure,
primitive display curves, cleanup and source preservation; manual fill-winding
and visual review remain required. The separate topology gate covers line/cubic
subdivision, explicit reconnection, primitive/rotated CopyAssign coordinates and
copied basic appearance. Recovery gates cover synthetic partial/late failures; real modal
and busy behavior still needs controlled observation during the later session.

The process-color gate covers exact native RGB/CMYK components on vectors/text,
ordinary-outline recoloring and measured geometry/other-channel preservation.
Its PDF/CDR artifacts require separate visual/color/prepress review; exact native
components do not establish ICC conversion or separation correctness.

Use `tests/integration/test_corel_live.py` with explicit live and disposable
mutation flags only when the user resumes native verification. All generated
fixtures and outputs belong to that run's unique temporary directory. Existing
user/client artwork is not a fixture. The gate report's success still needs
manual CDR/PDF/visual review and a real MCP-client envelope campaign.

The later report must account for every inventory entry with a result, artifact
where applicable, limitations and any failure. Leave capabilities
`implemented_unverified` until their applicable native/client/manual gates pass.
