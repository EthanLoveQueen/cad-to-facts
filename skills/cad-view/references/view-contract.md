# Target and STEP view contract

## TargetSelector

All supplied constraints are ANDed; at least one is required.

| Field | Meaning |
| --- | --- |
| `occurrence_id` | Exact snapshot-scoped `occurrence:N`. |
| `path` | Exact occurrence-ID path such as `occurrence:0/occurrence:4`. |
| `name` | Case-sensitive exact match against occurrence or definition name. |
| `name_contains` | Unicode-casefolded substring against occurrence or definition name. |
| `name_contains_any` | Nonempty alias list; any alias may match either name. |
| `definition_id` | Exact snapshot-scoped `part:N`; repeated occurrences remain separate. |
| `is_assembly` | Filter by the referred definition's assembly flag. |
| `is_root` | Filter by whether the occurrence-ID path has exactly one segment. |
| `state` | `active`, `inactive` or `unknown`. |
| `spatial` | ANDed spatial constraints with reference, camera and relation. |

The command always uses `read_scope=assembly` and returns `artifact`, a compact `snapshot`, and
`resolution`. Candidates retain occurrence/definition names, canonical ID path, display name path,
native XCAF entry, transformation, state and a world-placed OCCT optimal bounding box in system mm.
A missing/unmeasurable shape leaves `bbox=null` with `geometry_diagnostic` and prevents `complete=true`.
`TARGET_GEOMETRY_UNAVAILABLE` is also reported.

`resolution_id` is content-derived. Status `resolved` means one discovered candidate, not persistent
identity or functional recognition. `complete` means complete occurrence discovery plus a measurable
placed bounding box for every returned candidate. It is not full shape validation, a diagnostic-free
guarantee, unique resolution or design-intent proof.

A spatial constraint supports `left_of`, `right_of`, `above`, `below`, `in_front_of`, `behind`, or
`near`. Directional tests project world-bbox centers onto explicit camera axes. `near` requires
`max_distance_mm` and computes world-bbox gap. Neither method proves contact, containment or exact
shape distance. Ordinary references must be unique; ambiguity/failure makes resolution incomplete.
The lone reference `{"is_root": true}` denotes the virtual whole assembly and unions root boxes,
using `assembly:root` in evidence. Reference selectors cannot contain nested spatial constraints.

## Assumed orientation

`facts orient model.step --selector selector.json` applies the same unique-target resolution, then
returns six camera candidates with projected area/depth and center offset. The implemented policy
chooses the unique largest projected bbox face and its outward direction from the root-bbox center.
Axis ties and near-zero offsets are ambiguous. A successful `recommended_view` has
`semantic_intent.basis=assumed`; it is not source-declared or functionally validated front evidence.
Write that view object to JSON and use it with the same exact occurrence for rendering, while checking
artifact/snapshot identities as below.

## ViewSpecification

```json
{
  "schema_version": "0.1",
  "title": "Optional SVG title",
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
    "note": "Optional external-context explanation"
  }
}
```

`camera` requires exactly one form:

1. `preset`: `front`, `back`, `left`, `right`, `top`, `bottom` or `iso`;
2. `normal` and `right`: two finite three-component, nonzero, non-parallel vectors.

Presets use the snapshot's global system coordinates, not a part-local or design-intent frame:

| Preset | Model-to-viewer normal | Screen right | Screen up |
| --- | --- | --- | --- |
| `front` | -Y | +X | +Z |
| `back` | +Y | -X | +Z |
| `left` | -X | -Y | +Z |
| `right` | +X | +Y | +Z |
| `top` | +Z | +X | +Y |
| `bottom` | -Z | +X | -Y |
| `iso` | (+X,-Y,+Z), normalized | (+X,+Y,0), normalized | derived by OCCT |

For an explicit camera, `normal × right` is screen-up. `projection` is orthographic in this slice.
`show_hidden_lines=true` adds gray dashed hidden paths. Image width/height are 64–8192 pixels;
`max_points` is 100–2,000,000 and applies across visible and hidden paths. Exceeding it rejects the
render without output. Padding must leave a drawable page. Curve deflection is positive and measured
in projected system-mm coordinates; it controls SVG polyline approximation, not dimensional evidence.

`semantic_intent` is optional and external to the source declaration. `basis=user_selected` records
user confirmation; `basis=assumed` records a disclosed assumption. No `declared` basis is implemented.

## Output and manifest

STEP syntax:

```bash
facts render model.step --target occurrence:0 --view-spec view.json --output model.svg
```

Only `.svg` is accepted. Resolve and render independently re-read the artifact; no prior resolution ID
is enforced. Compare resolve's `artifact.sha256` and `snapshot.snapshot_id` with render's
`artifact.sha256` and `snapshot_id`, and resolve again on mismatch.

The command uses assembly scope and requires an active occurrence with a
transferred shape. It writes `model.svg` and `model.view.json`, both with exclusive creation. Existing
image or manifest paths are rejected. If pair creation fails, newly created partial outputs are
removed where possible; pre-existing files are never replaced.

The CLI envelope contains `artifact`, `snapshot_id`, `manifest_path` and `view_render`. The manifest
contains:

- `kind=step_view_render` and content-derived `view_render_id`;
- artifact SHA-256, snapshot ID/content hash and exact `TargetCandidate`;
- complete `ViewSpecification`;
- OCCT kernel version, HLR and curve-discretization methods;
- visible/hidden/skipped edge counts, total point count and projected extents. Projected extents are
  system-millimetre spans of the emitted, discretized visible plus requested-hidden point set before
  SVG page scaling, not exact source dimensions—especially with curve approximation or skipped edges;
- output absolute path, format, byte SHA-256 and size;
- snapshot/render diagnostics and `review_render_only_not_visual_or_geometric_equivalence`.

These counts describe paths drawn, not a proof that every source edge was faithfully represented.
SVG contains no external raster/resource reads. It is suitable for local review/documentation but not
for pixel-based measurement, persistent identity, hidden-geometry completeness or design validation.
