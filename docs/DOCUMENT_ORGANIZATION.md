# Page and layer organization

Status: `implemented_unverified`. Live CorelDRAW checks remain deferred.

Seven tools extend document organization:

- `get_document_structure` returns page/local/master layer identities, native
  names, inch dimensions, visible/editable/printable flags, root shape membership
  and order, active page and each page's active layer, plus a session fingerprint.
- `activate_page` changes the exact inspected active page. Existing signed object
  references can then pass the cross-page editing guard.
- `activate_layer` selects an ordinary visible/editable local layer and its page,
  enabling subsequent drawing/import/text creation in that layer.
- `rename_page` changes a page name with case-insensitive duplicate preflight.
- `create_page` appends one named page with explicit inch dimensions and returns
  its identity while preserving existing structure and active context.
- `create_layer` creates one empty ordinary local layer on an inspected page and
  restores the previous active page and affected page's active layer.
- `set_layer_properties` changes a nonempty subset of `name`, `visible`,
  `editable` and `printable` on an ordinary local layer.

Every mutation requires the current `expected_fingerprint` from inspection or
the preceding result. Reinspect after intervening changes. Fingerprints include
the bridge/document session, complete recorded page/layer state and root order;
they become stale on metadata, membership, active-context or session changes.
Selection uses identities instead of page numbers or names. Master and special
layers are inspectable but are refused for activation or property editing.

For example, inspect, create a page, create a layer using the returned page
identity and fresh fingerprint, then activate that layer with the next returned
fingerprint. Later bridge creation tools use the activated layer. A layer must
be explicitly visible and editable before activation; enabling it is a separate
fingerprint-guarded property change.

Inspection is bounded to 256 pages, 128 local/master layers per collection and
4096 total scanned page/layer/root entries. Repeated `AllLayers` exposures consume
the budget too. Ambiguous identities, unknown master membership, foreign roots,
unreadable flags/dimensions and malformed collections are refused. Names may
contain Unicode; new names have 1-128 characters without control characters.
Page size inputs range from 0.01 to 2000 inches. Actual native rounding is
retained after tolerance-based size reconciliation.
Creation reserves scan capacity before native writes: two additional entries
for a local layer and capacity for the bounded new-page default layer set.

Temporary unit changes must enter inches and return exactly to the original
unit. Successful inspection restores the previous native-mutation marker, so a
stale structural preflight does not quarantine the worker after proven unit
restoration. A failed or ignored unit restoration remains a recovery condition.

Creation calls native `AddPages(1)` or `CreateLayer(name)` once and verifies the
returned receipt in the bound document. Original names, sizes, flags, identities,
root order and active context must reconcile. On failure, only a known new empty
page/layer can be deleted, after original structure is rechecked. Unknown extra
objects, populated or foreign receipts, source changes, cleanup failures and
lost receipts prevent deletion and success. A failed command-group close is
never replayed and cannot be reported recovered; a failed begin also retains
explicit command-group uncertainty. Partial property writes and
activation mismatches quarantine later mutations while structure inspection
remains available; there is no automatic native undo.

The preservation contract covers recorded structure and root membership.
Descendant geometry, appearance, clipping contents and simultaneous external
artwork changes are outside that contract. Existing-page size/reorder/deletion,
cross-layer/page object moves, master/special edits, guides and controlled
document open/close/checkpoints remain broader work.

Installed evidence: [x7_organization_api_evidence.json](x7_organization_api_evidence.json)
contains 47 descriptors and `connection_attempted:false`. The X7
[page help](https://product.corel.com/help/CorelDRAW/540229932/Main/EN/Documentation/CorelDRAW-Adding-duplicating-renaming-and-deleting-pages.html)
and [layer help](https://product.corel.com/help/CorelDRAW/540229932/Main/EN/Documentation/CorelDRAW-Working-with-layers.html)
returned readable workflow documentation. Two SDK API requests returned HTTP
200 without readable API content; these results are retained honestly in
[organization_online_evidence.json](organization_online_evidence.json).

The guarded `CorelDisposableDocumentLiveTests.test_document_organization_live`
gate creates its own pages/layers/artwork and prepares native state, CDR and PDF
artifacts. Native layer visibility/editability/printing, unit semantics, page
lifecycle and rendered output still require the consolidated campaign and review.
