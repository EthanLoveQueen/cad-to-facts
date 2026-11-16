---
name: cad-view
description: Resolves STEP assembly occurrences and exports target-isolated orthographic SVG views with provenance manifests. Use for requests such as "export the front view of this door", "render only this occurrence", or "create a vector illustration for a document". Supports spatial selectors and an explicitly assumed-front heuristic; preserves camera versus semantic-front assumptions and never infers dimensions from pixels. PNG, photorealistic rendering, VLM interpretation, and declared/functional front recognition are not implemented.
license: MIT
---

# STEP occurrence views and technical illustrations

This skill drives the same local `facts` CLI as `cad-to-facts`. It creates read-only OCCT hidden-line
views of one explicitly selected STEP occurrence. The source artifact is never modified. Rendering is
offline and deterministic; it does not call an LLM/VLM or upload the model/image.

## Implemented scope

- `facts resolve`: exact occurrence/definition-name, substring/aliases, path, definition,
  root/assembly-kind, state and bounded world-bbox spatial constraints. Returns `resolved`,
  `ambiguous`, `unresolved` or `failed`; it never picks one of several candidates by traversal order.
- `facts orient`: six camera candidates and an optional `recommended_view` from the largest-bbox-face,
  outward-from-assembly heuristic. A recommendation is always `semantic_status=assumed`.
- `facts render` on STEP: one active `occurrence:N`, one explicit `ViewSpecification`, one new SVG,
  and one new sibling `.view.json` manifest.
- Global-axis camera presets and explicit normal/right vectors, visible/hidden-line output, bounded
  SVG point count, artifact/snapshot/output hashes with exact target binding, and optional
  user-selected or assumed view semantics.

PNG, section/exploded/shaded views, photorealistic output, dimension annotation, source-declared or
functional front recognition and visual inference are not implemented. SVG is a review/documentation
WorkProduct, not visual or geometric equivalence proof and not a FactSet.

## Setup

Use the repository's installed `facts` CLI, or `uv run --project /path/to/cad-to-facts facts ...`.
The reference environment is Python 3.13 with the locked OCCT dependencies. No ODA, text-to-cad,
Blender or network service is used for STEP SVG rendering.

## Resolve before rendering

Write a TargetSelector JSON such as:

```json
{"name_contains": "DOOR", "is_assembly": false}
```

Then run:

```bash
facts resolve assembly.step --selector door-selector.json
```

Read `resolution.status`, `resolution.complete`, `resolution.discovery`, candidates and diagnostics.
`name` and `name_contains` inspect both occurrence names and part-definition names because some STEP
files declare only PRODUCT names. Candidate `name_path` and `path` are different: the former is for
display, while the latter joins snapshot-scoped occurrence IDs and is the exact path-selector form.

- `resolved`: exactly one discovered candidate; use its `occurrence_id`.
- `ambiguous`: inspect the candidates' paths, names and placed bounding boxes, add constraints, or ask
  the user to choose. Never silently select the first.
- `unresolved`: no matching candidate was discovered. This is not proof of engineering absence.
- `failed`: the snapshot could not be read; do not render from it.

`complete` means complete occurrence discovery plus a measurable placed bounding box for every returned
candidate. It does not mean full shape validation, no diagnostics, successful resolution or global
uniqueness. An ambiguous or unresolved result can be complete when discovery is complete. With partial
or unknown discovery, uniqueness is only discovered-only and `complete=false`.

## Optional assumed-front selection

For a uniquely resolved target, `facts orient assembly.step --selector selector.json` returns six
world-bbox projection candidates. It selects only a unique largest-area axis whose outward sign from
the assembly center is unambiguous. Otherwise it returns `ambiguous` and no view. Copy a successful
`recommended_view` verbatim to a JSON file for rendering; it already has
`semantic_intent.basis=assumed`. Do not relabel it `user_selected` unless the user actually chooses it,
and never call it a source-declared front. Bounding-box heuristics can choose the wrong documentation
side, so disclose the assumption.

## Export a view

Write a ViewSpecification, for example `door-front-view.json`:

```json
{
  "title": "Door front",
  "camera": {"preset": "front"},
  "display": {"show_hidden_lines": false},
  "image": {
    "width": 1200,
    "height": 900,
    "padding": 24,
    "curve_deflection_mm": 0.1,
    "max_points": 200000
  },
  "semantic_intent": {
    "label": "front",
    "basis": "user_selected",
    "note": "The user selected the exterior side as front"
  }
}
```

Render the resolved target:

```bash
facts render assembly.step \
  --target occurrence:12 \
  --view-spec door-front-view.json \
  --output door-front.svg
```

This creates `door-front.svg` and `door-front.view.json`. Both paths must be new; neither is
overwritten. If either already exists, no new pair is written. The manifest binds artifact/snapshot
identity, the exact target, full view specification, renderer/version, projected extents, edge/point
counts, image SHA-256/size and diagnostics. Check those bytes before downstream use.

Resolve and render independently re-read the STEP file; render does not enforce a prior resolution ID.
Before relying on the selection, compare resolve's `artifact.sha256` and `snapshot.snapshot_id` with
render's `artifact.sha256` and `snapshot_id`. If either differs, discard the prior selection and resolve
again. The manifest records the snapshot and target actually rendered.

## Camera semantics are not design semantics

The `front` preset means only: viewer on global **-Y**, looking toward **+Y**, screen-right **+X** and
screen-up **+Z**. It does not prove the part's functional front. Other presets are documented in
[View contract](references/view-contract.md).

For a user-defined direction, use explicit `normal` and `right` vectors. `normal` points from the model
toward the viewer; `normal × right` determines screen-up. `semantic_intent.basis` is only:

- `user_selected`: the user supplied/confirmed this meaning;
- `assumed`: an explicit agent assumption that must be disclosed.

The current contract does not accept a `declared` basis: source-file front-side declarations are not
extracted. Omit `semantic_intent` for a purely geometric camera. Never turn a preset or an assumed
front into a claim that the source design declares that side.

## Honest limits

- Entity/occurrence IDs and paths are snapshot-scoped, not persistent cross-revision identity.
- Target resolution filters declared IDs, paths, names/aliases, definition, root/assembly kind, state
  and bounded world-bbox spatial relations. Placed bounding boxes and spatial evidence are returned.
  Directional relations compare centers in an explicit camera; `near` needs an explicit bbox-gap limit.
  These are not contact, containment, exact-distance or functional-feature proofs. Face/edge selectors
  and source-code `made_by` mapping are not implemented.
- Resolving geometry does not locate an editable source parameter. Existing change commands still
  require their explicit ChangePreparationSpec and SourceManifest evidence.
- OCCT HLR supplies projected edges; curves are discretized into SVG polylines. `skipped_edge_count`
  and `VIEW_EDGES_NOT_DISCRETIZED` disclose omitted paths. Point count is bounded, but HLR runtime is
  not a general large-assembly guarantee. Projected extents describe the emitted discretized point set,
  not exact source dimensions.
- A render can succeed with partial discovery or parser diagnostics; these remain in the manifest and
  prevent whole-model completeness claims.
- Never read dimensions from pixels. Use Facts for implemented measurements or semantic PMI for
  declared annotation values.
- Focused tests use analytic OCCT-generated STEP fixtures. Those tests and isolated real-file
  observations do not establish exporter interoperability or general large-assembly rendering.
- Do not send the source or derived SVG to an external visual model without separate authorization.

See [View contract](references/view-contract.md) for all selector, camera and manifest fields.
