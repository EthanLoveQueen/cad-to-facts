# STEP target resolution and model views

This document records the implemented target-resolution and SVG-render contracts. Bounded feature,
orientation and question-answering contracts are in [model questions](model-questions.md). VLM
inference and persistent design identity remain outside these operations.

## Why two operations

`resolve` converts explicit occurrence constraints into candidates; `render` consumes one exact
snapshot-scoped occurrence ID. Keeping them separate prevents a name collision or partial discovery
from silently selecting geometry. Both operations read STEP with the assembly profile and leave the
source artifact unchanged.

## `facts resolve`

```bash
facts resolve assembly.step --selector selector.json
```

The selector requires at least one constraint and ANDs all supplied fields:

| Field | Behavior |
| --- | --- |
| `occurrence_id` | Exact `occurrence:N` in this snapshot. |
| `path` | Exact slash-joined occurrence-ID path. |
| `name` | Exact case-sensitive occurrence or part-definition name. |
| `name_contains` | Unicode-casefolded substring of either name. |
| `name_contains_any` | Non-empty aliases; any alias may match either name. Aliases are ORed, then ANDed with other fields. |
| `definition_id` | Exact `part:N`; all its occurrences remain separate candidates. |
| `is_assembly` | Match the referred definition's assembly flag. |
| `is_root` | Match occurrences whose ID path has/does not have exactly one segment. As a lone spatial reference, `{"is_root": true}` denotes the virtual whole assembly instead. |
| `state` | Match `active`, `inactive` or `unknown`. |
| `spatial` | ANDed bounded spatial constraints described below. |

`name` and `name_contains` deliberately inspect both levels because STEP PRODUCT names and XCAF
occurrence labels are not interchangeable. The response preserves `name`, `definition_name`,
`path` and `name_path` separately so a definition-name match is not presented as a declared
occurrence name.

The response contains the registered artifact, compact snapshot metadata and a `TargetResolution`:

- `resolved`: exactly one discovered candidate and a populated `resolved_target`;
- `ambiguous`: two or more candidates and no resolved target;
- `unresolved`: no discovered candidate, not proof of engineering absence;
- `failed`: snapshot reading failed.

Ambiguous, unresolved and failed snapshot results are valid JSON results with exit 0. An invalid
selector or unsupported artifact is a configuration error with exit 2.

Each candidate contains its native XCAF entry, local transformation, occurrence state and an
axis-aligned bounding box of the shape placed in assembly world coordinates. Nested occurrence
locations are accumulated before measurement; values are system millimetres and use
`BRepBndLib.AddOptimal`. The box is a placement aid, not a semantic feature description.

`discovery` is the snapshot's assembly discovery state. `complete` requires complete discovery and a
measurable bounding box for every returned candidate. It does **not** mean full shape validation, no
diagnostics, that the status is resolved, that the candidate is globally unique under partial discovery,
or that its function was recognized.
Geometry failures retain the candidate with `bbox=null`, `geometry_diagnostic` and
`TARGET_GEOMETRY_UNAVAILABLE`.

Occurrence IDs, paths and native entries are snapshot-scoped. A `TargetResolution` is neither an
`EntityMatch` across revisions nor an editable-source location. It cannot replace the explicit target
binding, SourceManifest or approval evidence required by the change workflow.

### Spatial constraints

Each `spatial` item has a `relation`, a non-nested reference `TargetSelector`, an explicit
`CameraSpecification`, and an optional nonnegative `tolerance_mm` (default `1e-7`). Supported
relations are `left_of`, `right_of`, `above`, `below`, `in_front_of`, `behind`, and `near`.
Directional relations project candidate and reference world-bounding-box centers onto the camera's
screen-right, screen-up, or model-to-viewer normal axis. They are center-order tests, not clearance,
contact, containment, or minimum-distance proofs.

`near` requires a positive `max_distance_mm` and computes Euclidean separation between the two world
axis-aligned bounding boxes. Overlapping boxes have gap zero. This is a bounded proximity filter, not
exact shape distance; other relations reject `max_distance_mm`.

An ordinary reference must resolve to exactly one declared occurrence before target filtering.
Ambiguous/unresolved references produce `SPATIAL_REFERENCE_AMBIGUOUS` or
`SPATIAL_REFERENCE_UNRESOLVED`, clear the target candidates, and make resolution incomplete. A missing
reference box produces `SPATIAL_REFERENCE_GEOMETRY_UNAVAILABLE`. No reference is selected by order.

The sole reference object `{"is_root": true}` is the explicit virtual whole-assembly reference. It
unions all root-occurrence world boxes and uses `assembly:root` in `SpatialMatchEvidence`; it does not
choose one of those occurrences. Every spatial match retains the relation, reference ID, camera,
method, and projected coordinates or gap distance.

## `facts render` for STEP

```bash
facts resolve assembly.step --selector examples/resolve-door.json
facts render assembly.step \
  --target occurrence:12 \
  --view-spec examples/view-front.json \
  --output door-front.svg
```

The target must be an active occurrence in a readable assembly-profile snapshot with a transferred
shape. This can be a leaf or a subassembly; only that occurrence's placed shape is projected. There is
no implicit "first match" and no multi-target selection in this slice.

`resolve` and `render` independently register and re-read the artifact. Render accepts an occurrence ID,
not a resolution ID or expected snapshot ID, so a prior resolution is a workflow safeguard rather than
an enforced precondition. Compare resolve's `artifact.sha256` and `snapshot.snapshot_id` with render's
`artifact.sha256` and `snapshot_id`; if either differs, discard the prior selection and resolve again.
The render manifest always records the snapshot and target actually used.

The command creates two new files:

- the requested `.svg`;
- a sibling manifest formed by replacing the suffix with `.view.json` (for example,
  `door-front.view.json`).

Existing image or manifest paths are rejected before CAD reading. Neither file overwrites an existing
file. If writing the pair fails after creating one member, the command attempts to remove only the
newly created member; it never removes a pre-existing file. A malformed target/view, inactive or
missing target, projection failure, exhausted point budget or existing output exits 2. Unexpected
internal failures use the CLI's normal exit 3.

Drawing `render` remains a separate DXF/DWG workflow and does not accept `--target` or `--view-spec`.

## ViewSpecification

```json
{
  "schema_version": "0.1",
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
    "note": "User confirmed the exterior side"
  }
}
```

The camera is either one preset or explicit `normal` and `right` vectors, never both. Explicit vectors
contain three finite values, are nonzero and are not parallel. The normal points from the model toward
the viewer; `normal × right` defines screen-up. Rendering is orthographic.

| Preset | Normal | Right | Up |
| --- | --- | --- | --- |
| `front` | -Y | +X | +Z |
| `back` | +Y | -X | +Z |
| `left` | -X | -Y | +Z |
| `right` | +X | +Y | +Z |
| `top` | +Z | +X | +Y |
| `bottom` | -Z | +X | -Y |
| `iso` | (+X,-Y,+Z), normalized | (+X,+Y,0), normalized | derived by OCCT |

Presets are global system-coordinate conventions, not design-intent recognition. In particular,
`front` does not establish a door's exterior side. `semantic_intent` optionally records an external
label with `basis=user_selected` or `basis=assumed`. There is no implemented `declared` basis because
the STEP adapter does not extract a design-front declaration. An assumed intent must be disclosed and
must not be rewritten as a source Fact.

Image dimensions are 64–8192 pixels. Padding is nonnegative and must leave a drawable page.
`curve_deflection_mm` is positive and controls curve polyline sampling in projected system-mm space.
`max_points` is 100–2,000,000 across visible and requested hidden paths; exceeding it fails the render
instead of silently truncating geometry.

`show_hidden_lines=false` emits visible paths only. When true, hidden paths use a separate gray dashed
SVG group. OCCT `HLRBRep_Algo` performs hidden-line removal and `HLRBRep_HLRToShape` exposes the
visible/hidden compounds. `GCPnts_QuasiUniformDeflection` discretizes projected curves. Project-owned
code only orchestrates the target, view, SVG serialization and evidence.

## ViewRenderManifest

The CLI result contains `artifact`, `snapshot_id`, `manifest_path` and `view_render`. The manifest
binds:

- raw artifact SHA-256, snapshot ID and snapshot content hash;
- the complete target candidate, including its placed bounding box;
- the complete view specification and semantic-intent basis, if any;
- OCCT kernel version and HLR/discretization method identifiers;
- visible, hidden and skipped projected-edge counts, total SVG point count and projected extents.
  Projected extents are system-millimetre spans of the emitted, discretized visible plus requested-hidden
  point set before SVG page scaling, not exact source dimensions—especially with curve approximation or
  skipped edges;
- the SVG's absolute output path, byte SHA-256 and size;
- all snapshot diagnostics plus `VIEW_EDGES_NOT_DISCRETIZED` when applicable.

`view_render_id` is content-derived from the manifest without that field. Output path participates in
the manifest identity; SVG bytes are separately hashed. The fixed fidelity value is
`review_render_only_not_visual_or_geometric_equivalence`.

The SVG uses a white background and inline vector paths. It does not reference or implicitly load
external raster images or other resources. It is a neutral downstream WorkProduct for local review or
document illustration, not a Fact, Finding, Inference, engineering drawing release or pixel-measurement
source.

## Current limits and next decisions

Implemented tests cover unique/ambiguous/unresolved selectors, alias/root/spatial filters, unique and
whole-assembly references, explicit near distances, nested world placement, target isolation, global
and explicit cameras, manifest binding, and new-only output protection. They use analytic
OCCT-generated STEP fixtures and therefore do not establish exporter interoperability.

Not implemented: face or edge selectors; general geometric-feature selection beyond the bounded
recognizer in `model-questions.md`; declared/functional design-front recognition; PNG,
shaded/photorealistic, section or exploded views; dimensions in the image; visual question answering;
persistent occurrence identity; and editable source `made_by` mapping.

Any future VLM workflow remains an optional separate Inference path, disabled by default, independently
validated, and outside FactSet. No design file or derived image is uploaded by these commands.
