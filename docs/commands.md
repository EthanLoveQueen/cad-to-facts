# Command reference

Detailed walkthroughs for the `facts` CLI. The overview, installation, agent-skill setup and scope
live in the [README](../README.md). Examples use placeholder filenames (`part.step`,
`assembly.step`, `drawing.dxf`) unless they point at the public `examples/` fixtures; run commands
from the repository root.

## Inspect a STEP file

```bash
uv run facts inspect part.step
uv run facts inspect assembly.step --read-scope assembly --limit 5
```

`--read-scope` defaults to `single_part`; use `assembly` to include XCAF structure in the snapshot.
The same option is available on `review` and `prepare-change`; verification uses its fixed request profile.

The command writes one JSON object to stdout containing the SourceArtifact, ModelSnapshot summary,
selective FactSet, and a `selection` block with `entity_total`, `entities_returned`, `truncated`,
and `next_cursor`. Use `--limit` to bound the number of measured entities. It does not dump OCCT
shapes or every face.

## Resolve a STEP target and export a view

Use explicit occurrence/definition constraints first; do not silently choose among ambiguous names:

```bash
uv run facts resolve assembly.step --selector examples/resolve-door.json
uv run facts resolve assembly.step --selector examples/resolve-root.json
```

A `resolved` result supplies the exact snapshot-scoped `occurrence_id`. `ambiguous`, `unresolved` and
failed snapshots are normal JSON results, not permission to guess. Candidate bounding boxes are placed
in assembly world coordinates, including ancestor transformations. `complete` means complete discovery
and a measurable placed bounding box for every returned candidate, not full shape validation,
functional recognition, a diagnostic-free guarantee or persistent identity.

Render one active occurrence with an explicit camera:

```bash
uv run facts render assembly.step \
  --target occurrence:0 \
  --view-spec examples/view-front.json \
  --output root-front.svg
```

This creates `root-front.svg` and `root-front.view.json`, rejecting either path if it already exists.
The manifest binds source/snapshot/target, view parameters, OCCT methods, projected edge/point
statistics, diagnostics and output bytes. Resolve and render independently re-read the file; compare
`artifact.sha256` and `snapshot.snapshot_id` from resolve with `artifact.sha256` and `snapshot_id` from
render, and resolve again on mismatch because the prior resolution is not a CLI-enforced precondition.
`front` means the global -Y viewer direction, not an
automatically recognized design front. Use `semantic_intent.basis=user_selected` only when the user
selected that meaning, or `assumed` for a disclosed assumption; source-declared front recognition is
not implemented. SVG is for review/documentation, not dimensional evidence or fidelity proof. See
[`docs/model-views.md`](model-views.md) and the `cad-view` skill. Face/edge selectors, PNG and
VLM interpretation remain unimplemented.

## Ask bounded STEP model questions

```bash
uv run facts features examples/question-assembly.step --query examples/features-doors-windows-holes.json
uv run facts orient examples/question-assembly.step --selector examples/resolve-left-door.json
uv run facts ask examples/question-assembly.step --question "where is the left door?"
uv run facts ask examples/question-assembly.step --question "what is the front face of the door?"
uv run facts ask examples/question-assembly.step --question "how many holes are there?"
uv run facts ask examples/question-assembly.step --spec examples/question-door-candidates.json
```

`features` separates unvalidated door/window name candidates from conservative validated cylindrical
through-holes. It does not validate general doors/windows or recognize blind, counterbored,
rectangular, intersecting and other holes; `general_feature_coverage` remains `unknown`.
`resolve-left-door.json` selects the public example's left door. For other models, substitute an
explicit selector or an exact occurrence returned by your own `resolve` result.

`orient` chooses only a unique largest target-bbox projected face pointing outward from the assembly
bbox center. Ties return `ambiguous`; a recommendation is always `semantic_status=assumed`, not a
source declaration or functional-front proof. Its `recommended_view` can be saved as the view spec for
the exact target.

`ask --question` is a deliberately limited offline Chinese/English grammar, not general NLP.
`ask --spec` accepts explicit agent/user `QuestionSpec` interpretations for location, occurrence or
feature counts, validated feature geometry and orientation. Both produce the same `AnswerReport` with
assumptions, alternatives, count states, evidence and gaps. Candidate counts require the explicit
`candidates_allowed` policy and never become validated feature quantities. Strict feature answers and
assumed-front answers remain partial where general evidence is unavailable. Unsupported wording
returns `unsupported` instead of guessing. See
[`docs/model-questions.md`](model-questions.md).

For an end-to-end agent-workflow check, `examples/question-assembly.step` contains left/right door
name candidates, one window name candidate and one known 3 mm-radius, 10 mm-long cylindrical
through-hole. The `evals/model-question-*` cases exercise compound evidence separation, conditional
per-target orientations and the assumed-left-door SVG handoff. They are local model-backed behavior
evaluations, not exporter-interoperability evidence; run them with `--no-publish` and keep their
reports under the ignored `evals/results/` directory.

## Inspect or review a DWG/DXF drawing

```bash
uv run facts inspect drawing.dxf --summary
uv run facts query drawing.dxf --kind line --layer Geometry --limit 20
uv run facts ask drawing.dxf --spec examples/drawing-question.json
uv run facts render drawing.dxf --output drawing.svg
uv run facts drawing-bom drawing.dxf --part-tag PART --material-tag MATERIAL
uv run facts inspect drawing.dwg --oda-path "C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe"
```

DXF is read directly with ezdxf. DWG uses a separately installed ODA File Converter to create a
temporary local ACAD2018 DXF, then parses that derivative; neither the plugin nor `uv sync` installs
ODA. The converter path must be supplied explicitly with `--oda-path` (also accepted by
`facts review`); install locations are not guessed. If ODA is unavailable, inspection still returns
JSON with `snapshot.status=failed` and `ADAPTER_UNAVAILABLE`.

`facts review` accepts drawing snapshots with the same explicit requirement/rule/scope/context
inputs as STEP. The drawing profile catalogs layers, model/paper-space layouts, non-layout blocks and
entities. It extracts declared type/layer/container, text and block-name/attribute facts, plus
selected 2D lengths, areas and circle circumferences. Curved LWPOLYLINEs use exact bulge-arc formulas.
XREFs remain unresolved by default; `--xref-mode linked|flatten` with explicit `--xref-root`
directories enables bounded local resolution. `drawing-bom --part-tag PART` extracts only explicitly
configured block attributes. Uncounted XREFs block BOM completeness unless `--allow-xref-exclusion`
explicitly accepts their exclusion from the selected scope. `facts ask` accepts an explicit
`DrawingQuestionSpec` for bounded drawing facts; drawing natural-language grammar, title-block
inference, INSERT geometry expansion and dimension-to-geometry association are not implemented.
`examples/question-drawing.dxf` and `examples/drawing-question.json` are a runnable analytic example;
they do not establish exporter interoperability. Query page sizes must be positive, and SVG rendering
ignores external raster images rather than reading them implicitly. None of these features infers
title-block semantics, and SVG is not fidelity proof. See
[the drawing contract](drawing-analysis.md) for units, licensing and security limits and
[drawing questions](drawing-questions.md) for the question profile.

## Review a STEP file

```bash
uv run facts review part.step \
  --requirements examples/requirements.json \
  --rules examples/rules.json \
  --scope examples/review-scope.json \
  --context examples/review-context.json
```

All four inputs are explicit. Requirements are not silently treated as executable rules, and there
is no hidden default review scope. The example checks that a single solid has a Z bounding-box
extent no greater than 30 mm; it is a demonstration rule, not a general engineering standard.

`compliant_for_scope` only describes the declared rules and scope. It is not a product
certification. A violated finding is a completed review result and still exits 0. Invalid inputs
(missing keys, empty requirements, unknown references, invalid checker parameters) exit 2 with a
JSON error; a checker failure produces a report with `tool_error=true` and exits 3.

To run the sourced file-health pack without authoring rules:

```bash
uv run facts review part.step \
  --requirements rule-packs/step-file-health/requirements.json \
  --rules rule-packs/step-file-health/rules.json \
  --scope rule-packs/step-file-health/scope.json \
  --context rule-packs/step-file-health/context.json
```

This checks snapshot readiness only. Typed runs add finding types and per-type summaries. Legacy
reports serialize the new optional fields as null, while their structured content identities remain
unchanged. See [`rule-packs/README.md`](../rule-packs/README.md) for source/applicability/validation
metadata and limits; no generic manufacturing rule pack is claimed.

## Prepare a constrained process-card input

```bash
uv run facts process-input examples/box.step --context examples/machining-context.json
```

The shipped analytic example returns `complete=true` for this narrow profile, with 6000 mm³,
2200 mm² and extents 10/20/30 mm; that is a numerical regression, not exporter interoperability.
The current profile requires exactly one discovered solid and existing volume, area and three
bounding-box extent facts. Default required user context is `material`, `stock`, and `batch_size`;
repeat `--require-context` to replace that list. Values remain `user_supplied`, never declared STEP
facts. Optional gaps disclose that declared material, PMI projection and validated features are
unsupported in this profile; semantic PMI can be extracted separately with `facts pmi`.
`--require-design-input semantic_pmi` makes the projection gap required and the result incomplete.
Multi-solid files remain incomplete rather than selecting one implicitly.

`complete=true` covers only this declared extraction/context profile. It is not a manufacturing
plan or production-ready process card. Operation sequencing, setups, tool/machine selection,
cutting parameters, cycle time, templates and external-system connectors are rejected or out of
scope.

## Extract declared semantic PMI

```bash
uv run facts pmi part.step
uv run facts pmi assembly.step --read-scope assembly
```

The command re-reads the STEP file with XCAF GD&T transfer and returns `artifact`, a summarized
`snapshot`, and a neutral `PmiExtract`. Annotations cover declared dimensions, geometric tolerances
and datums; presentation-only labels are counted but not emitted. Values are reported only with a
declared unit from the PMI representation context. Mixed or unreadable units, missing/invalid values,
unresolved geometry links and unsupported categories are explicit gaps, never zeroes or guesses.
Tolerance deviations are exposed by OCCT as magnitudes, so their sign is left
`not_reported_by_reader` and a diagnostic records the limitation.

Read `status`, `complete` and `coverage.discovery` before using the result. A file without semantic
PMI returns `status=ready`, `complete=true` and empty annotations/gaps. A declared but unvalued
annotation or an absent/unresolved link keeps the result `partial`. Geometry links are resolved only
when PMI-document solids uniquely match snapshot solids by volume, area, centroid and bbox
fingerprints; `solid:N` references remain snapshot-scoped and faces are not assigned stable IDs.
`complete=true` is not full AP242 conformance or inspection approval. The NIST CTC-01 observation,
gap semantics and current unsupported subset are documented in
[`docs/semantic-pmi.md`](semantic-pmi.md). OCCT-generated AP242 fixtures additionally pin
mm/cm/in/rad conversion, deviation and limit dimensions, datums, material modifiers and the
unsupported datum-system gap. They are self-written and do not establish exporter interoperability.

## Extract a model BOM

```bash
uv run facts bom assembly.step
uv run facts bom assembly.step --require-property name
```

The command always reads with the assembly profile and emits a neutral `BOMExtract`, not an ERP or
manufacturing BOM. Only leaf part definitions become line items; occurrences are grouped by definition
identity rather than name. `quantity_state=observed` preserves numeric counts discovered under partial
or unreconciled structure, but `complete=false` prevents treating them as complete quantities. Coverage
separately counts known, observed and unknown quantity-definition totals, so every leaf row is
accounted for. Required properties other than `name` currently produce `UNSUPPORTED` missing inputs.

## Prepare and verify a change

Prepare an immutable request and external handoff plan from a real `violated` or `unknown`
`numeric.compare` finding:

```bash
uv run facts prepare-change \
  --report review.json --finding finding-1 --before old.step \
  --requirements examples/requirements.json --rules examples/rules.json \
  --scope examples/review-scope.json --context examples/review-context.json \
  --spec prepare-spec.json --before-manifest old-manifest.json
```

The command validates the original review and any baseline manifest, then emits a
`ChangePreparation` containing the `ChangeRequest` and `ChangePlan`. It does not invoke text-to-cad,
run a source script, approve a plan or modify an artifact. Source operations require a validated
baseline `SourceManifest`; source scripts remain executable, untrusted input requiring explicit
approval and isolation outside this CLI.

After the separately installed executor creates a new artifact, verify it without requiring an
approval or execution record:

```bash
uv run facts verify-change --request change.json --before old.step --after new.step
```

Add `--plan`, `--approval`, `--execution`, `--before-manifest`, `--after-manifest`, and
`--origin-review` when those records are available. The resulting `ModificationReport` distinguishes
output verification from execution provenance. For example, `verification_status=passed` with
`execution_provenance=unattested` means the declared output checks passed, not that the approved
plan was observed or attested. A missing after artifact yields an incomplete report. See the
[change-verification reference](../skills/cad-to-facts/references/change-verification.md) for the full
spec and record contract, or replay the packaged real run with the exact command in
[`examples/change-loop/README.md`](../examples/change-loop/README.md). The example returns
`passed / attested / changed` and includes sanitized native build/export evidence; it remains a
test-harness attestation, not independent cryptographic proof. Its explicit
`--replay-relocated-output` option is only for archived path relocation and is disclosed in the
replay report.
