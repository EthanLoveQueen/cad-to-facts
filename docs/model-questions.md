# Bounded features, orientation and model questions

These STEP-only operations use the assembly-profile `ModelSnapshot`. They return separate candidate,
measurement, assumption and gap records. None treats a natural-language interpretation or declared
name as proof of engineering function. Source artifacts are never modified and no network or AI call
is made by the deterministic core.

DWG/DXF questions use a sibling drawing profile with entity, text, layer, block, measurement,
dimension, candidate and attribute-BOM intents. STEP occurrence/feature/orientation intents are not
reused for drawings. See [`drawing-questions.md`](drawing-questions.md).

## Bounded feature recognition

```bash
facts features model.step --query examples/features-doors-windows-holes.json
```

`FeatureQuery.kinds` contains unique `door`, `window` and/or `hole` values. An optional `selector`
limits occurrences. Default aliases are `door`/`门`, `window`/`窗`, and `hole`/`孔`; a query may provide
explicit per-kind aliases. Alias matching inspects declared occurrence and definition names.

Door and window results are `FeatureCandidate`s with `validation=unvalidated` and
`recognition_method=declared_name_alias`. Door/window geometric validation is unsupported. A matching
name does not establish that the object is a door/window, and a nonmatching name does not establish
absence.

Hole recognition also runs a conservative OCCT geometry validator. A `validated` cylindrical
through-hole must have a full 360-degree cylindrical face with inward (`TopAbs_REVERSED`) orientation,
two circular end edges, exactly two incident faces at each end edge, planar adjacent end faces,
end-plane normals parallel to the cylinder axis, and cylindrical area consistent with `2πr × length`.
The returned `ThroughHoleGeometry` records face reference, radius, length, axis, area, center and mm
units. Ordinary cylindrical solids do not satisfy the inward/open-end topology and are negative test
cases.

Blind, counterbored, rectangular, slotted, intersecting and other hole forms are outside this
validator. A validated count is an **observed recognizer result**, not the total number of engineering
holes. `general_feature_coverage` is always `unknown`. Report `complete` describes execution of this
bounded recognizer only; it never upgrades general coverage. `FeatureGap`s disclose unsupported
validation, incomplete discovery and unavailable shapes.

## Assumed orientation

```bash
facts orient model.step --selector examples/orient-right-door.json
```

The example selector targets `occurrence:343` in the documented real container; substitute an exact
occurrence from your own resolution for other models.

`OrientationPolicy` currently supports only `largest_bbox_face_outward_from_assembly`. After the target
selector resolves uniquely, `infer_orientation` constructs six global-axis camera candidates
(`front/back/left/right/top/bottom`) and records world-bbox projected width, height, area, depth and
center offset for each. The assembly reference is the union of root-occurrence world boxes.

The method selects the unique largest projected-area axis within explicit relative/absolute area
tolerances, then selects its outward sign from the target center relative to the assembly center. A
tied axis or near-zero offset returns `ambiguous`, with no recommendation. Diagnostics include
`ORIENTATION_AXIS_AMBIGUOUS`, `ORIENTATION_OUTWARD_DIRECTION_AMBIGUOUS`, and
`ORIENTATION_ASSEMBLY_REFERENCE_UNAVAILABLE`.

A successful result has `semantic_status=assumed`, never `declared`. Its `recommended_view` is a normal
`ViewSpecification` whose `semantic_intent.basis=assumed` and note disclose the heuristic. This is not
source-declared front recovery, functional-front proof, visual recognition, or a guarantee that the
largest face is the useful documentation side. To render it, write the returned `recommended_view` to
JSON and pass it with the exact target to `facts render`; compare artifact/snapshot bindings because
the commands independently re-read the source.

## QuestionSpec and AnswerReport

```bash
facts ask model.step --spec examples/question-door-candidates.json
facts ask model.step --question "左侧的门在哪里？"
facts ask model.step --question "门的正面是哪边？"
facts ask model.step --question "有多少个孔？"
```

`--spec` and `--question` are mutually exclusive and one is required. Both paths execute the same
`answer_question(snapshot, spec)` implementation. Invalid JSON/specification input exits 2.
Unsupported interpretation is a normal `AnswerReport` with exit 0.

### Explicit interpretation

`QuestionSpec` preserves `original_text`, `interpretation_basis`, one or more interpretations,
`assumptions`, and `interpretation_gaps`. Basis is `deterministic_grammar`, `agent_interpretation`, or
`user_supplied`. Agents may translate arbitrary user wording into explicit selectors/intents, but must
not put that interpretation into FactSet or omit competing decision-changing interpretations.

Each `QuestionInterpretation` has an ID, an intent, and optional notes/evidence policy:

| Intent | Required input | Result |
| --- | --- | --- |
| `locate` | `selector` | `TargetResolution`, including alternatives and spatial evidence |
| `occurrence_count` | `selector` | Known count under complete resolution, otherwise observed-only |
| `feature_count` | unique `feature_kinds` | Per-kind validated or explicitly allowed candidate counts |
| `feature_geometry` | unique `feature_kinds` | Only validated `ThroughHoleGeometry` in this slice |
| `orientation` | `selector` | Six candidates, diagnostics and optional assumed view |

The default `evidence_policy=strict` reports validated hole counts as `observed`, leaves strict
door/window feature counts `unknown`, and retains `GENERAL_FEATURE_COUNT_UNKNOWN`. Feature geometry
similarly retains `GENERAL_FEATURE_GEOMETRY_INCOMPLETE`. With explicit
`evidence_policy=candidates_allowed`, feature counts report all bounded-recognizer candidates using
`state=candidate` and `unit=feature_candidates`; incomplete execution makes the answer partial. This
policy never changes a candidate into a validated feature.

`CountAnswer.state` distinguishes `known`, `observed`, `candidate`, and `unknown`. An occurrence count
is `known` only with complete discovery/candidate geometry; otherwise it is `observed` with
`OCCURRENCE_COUNT_OBSERVED_ONLY`. A failed snapshot/recognizer produces `status=failed`, a null value
and `state=unknown`, never an observed zero.

For `locate`, a unique complete target is `answered`; unique but incomplete is `partial`; other target
states remain `ambiguous`, `unresolved`, or `failed`. For `orientation`, a heuristic result under the
strict policy is `partial` with `DESIGN_FRONT_DECLARATION_UNAVAILABLE`. `candidates_allowed` explicitly
accepts the assumption as answer scope, but does not change `semantic_status=assumed`; incomplete
execution remains partial.

`AnswerReport.complete=true` only when every interpretation is `answered`. Mixed answered/partial
results are `partial`; execution failure dominates, then ambiguity/unresolved/unsupported states are
preserved. Every answer and the report carry content-derived IDs. Gaps appear both on the responsible
interpretation and in report-level aggregation. They are not confidence scores.

### Bounded offline language grammar

`--question` uses a deliberately limited Chinese/English grammar. It recognizes door/window/hole
aliases; locate, count, geometry and front-orientation wording; and left/right/above/below/in-front/
behind phrases. A count plus size/shape question produces separate count and geometry interpretations.
Other subjects and intents return `QUESTION_INTERPRETATION_UNSUPPORTED` instead of a guessed selector.
This grammar is not a general NLP model.

For a directional phrase without an explicit reference, the grammar emits a spatial constraint using
the global `front` camera and the virtual whole-assembly reference `{"is_root": true}`. It records that
choice in `QuestionSpec.assumptions`; source coordinates do not thereby acquire semantic left/right.
Natural-language `near` is not executed without an explicit distance: the grammar returns an
interpretation gap rather than inventing `max_distance_mm`. Explicit agent/user specs can supply a
unique named reference, another camera, and a numeric near limit.

Name-based location still selects candidates rather than proving function. Feature counts and geometry
retain the general-coverage gaps above. An assumed-front answer always retains its semantic status and
declaration gap, even when the deterministic geometry completed successfully.
