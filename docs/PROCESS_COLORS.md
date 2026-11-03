# Controlled native process colors

`set_process_color` writes an explicitly requested RGB or CMYK fill, or recolors
an existing ordinary outline. All capabilities remain `implemented_unverified`.

RGB inputs use `{"model":"rgb","red":20,"green":100,"blue":180}` with integer
channels 0-255. CMYK inputs use
`{"model":"cmyk","cyan":80,"magenta":40,"yellow":0,"black":10}` with integer
channels 0-100. Mixed model fields, floats, booleans, unavailable native factories
and factories that change the requested model/components are refused before
shape assignment. Spot-color creation and conversion are separate work.

Exact signed references or the common strict object selectors target individual
vectors/text, including supported referenced children. Groups, bitmap
colorization and complex effect targets require their own workflows. A fill
assignment replaces none/uniform fills. Replacing a fountain/pattern/texture
fill requires `replace_non_uniform=true`; otherwise preflight refuses it.

`channel="outline"` requires an existing readable ordinary outline. It changes
color and preserves raw width/type and the fill. Enhanced/absent outlines and
outline creation are outside this wrapper. The native outline-width unit
convention remains unresolved and is reported as such.

Native factories and final colors must retain the exact process model and every
requested channel. Readback also checks the other appearance channel, signed
identity, native matrix/bounds and supported full vector geometry. Text checks
cover readable whole-story content/font/size/bold and measured bounds; this does
not establish per-run or every effect-property preservation. Partial failures
and readback discrepancies have no automatic undo and quarantine subsequent
mutations through exact-operation recovery.

Installed X7 evidence in `x7_appearance_api_evidence.json` retains 274 descriptors
and five enums with `connection_attempted:false`, including
`Application.CreateCMYKColor(Cyan, Magenta, Yellow, Black)`, native CMYK channels,
`Fill.ApplyUniformFill` and `Outline.Color`. The evidence also inventories
transparency/PowerClip APIs for subsequent work; it does not register them.
The primary API reference location is
[CreateCMYKColor](https://community.coreldraw.com/sdk/api/draw/17/m/application.createcmykcolor).
Installed signatures support this wrapper; native execution remains deferred.

Eighteen non-live checks cover RGB/CMYK components, geometry and other-channel
preservation, explicit non-uniform replacement, native factory/assignment
failures, readable text, unsupported targets and worker quarantine. The prepared
gate `CorelDisposableDocumentLiveTests.test_native_process_colors_live` will
create its own vector/text fixtures and CDR/PDF outputs during the consolidated
campaign. Native color fidelity, ICC conversion, PDF/X compliance, separations,
spot colors and printed/visual correctness remain separate acceptance checks.
