# cad-to-facts

[![CI](https://github.com/EthanLoveQueen/cad-to-facts/actions/workflows/ci.yml/badge.svg)](https://github.com/EthanLoveQueen/cad-to-facts/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Local-first, evidence-driven CAD facts and deterministic requirements review, packaged as an agent
skill and a Python CLI.

## Current implementation status

The repository contains P1 STEP vertical slices, a first DWG/DXF drawing-analysis slice, a bounded AP242 semantic-PMI slice, a P2 change-preparation/output-verification slice, a P3 assembly/model-BOM slice, and a constrained P4 single-solid process-input slice:

- Immutable source-artifact registration using raw-byte SHA-256.
- OCCT STEP snapshots with parser provenance, source units, diagnostics, and snapshot-scoped entity
  references. A model with no solids is reported as `partial` with unknown discovery; it is never
  claimed as completely discovered.
- Verified millimetre normalization for geometric measurements; millimetre, centimetre, and inch
  STEP inputs are covered by analytic tests. A single unverified declared length unit (for example
  metre) keeps its entities and unit, marks the snapshot `partial`, and produces `UNKNOWN_UNIT` gaps
  for length facts instead of unverified measurements.
- Selective volume, surface-area, and bounding-box facts with method and evidence records.
  Measurement exceptions and negative/non-finite physical results become `MEASUREMENT_FAILED`
  gaps instead of aborting extraction or emitting invalid facts.
- Two explicit STEP read scopes. `single_part` detects assembly usage records before flattening
  and reports `ASSEMBLY_STRUCTURE_NOT_REPRESENTED` with `entity_discovery=partial`. `assembly`
  uses XCAF to preserve reusable part definitions, occurrence paths, local transformations and
  parent/child links. Reconciliation compares source PRODUCT/NAUO counts with XCAF results.
- DXF drawing snapshots and facts through ezdxf, with a separate drawing profile rather than a fake
  solid model. Layers, layouts, blocks, native handles and declared text/entity/container facts are
  preserved; LINE, ARC, CIRCLE and straight/curved LWPOLYLINE measurements normalize explicit units
  to mm/mm². Bulges use exact arc formulas; unitless input remains an explicit gap.
- Selective `inspect --summary` and filtered/paginated drawing `query` output avoid dumping large
  entity catalogs. Drawing `render` creates a new SVG for visual review without overwriting an
  existing file.
- Bounded drawing questions through `facts ask drawing.dxf --spec ...` with a sibling
  `DrawingQuestionSpec`/`DrawingAnswerReport` profile. Intents cover entity count/lookup, text lookup,
  layer/block inventory, length/area/circumference summaries, declared dimension values, unvalidated
  name candidates, a declared semantic-evidence bundle and explicit attribute-BOM lookups. Semantic
  evidence matches block names, layer names, text and attribute tags and includes attached ATTRIB
  values for INSERTs, but remains unvalidated context rather than an inferred material/part/function
  field. Counts separate known/partial/unknown and keep candidates in a separate layer; container and
  layer-state scope is preserved, and failures or unitless measurements never become numeric zero.
  General drawing semantics, title-block inference, INSERT expansion and dimension-to-geometry
  association remain unsupported.
- Explicit STEP occurrence resolution through `facts resolve`, with unique, ambiguous, unresolved
  and failed states. Selectors combine occurrence/definition names and aliases, paths, definitions,
  root/assembly kind, state and bounded spatial constraints; candidates include world-placed bounding
  boxes accumulated through nested occurrences. Spatial relations use explicit cameras/references and
  disclose center-projection or bbox-gap methods. Partial discovery never becomes global uniqueness.
- Bounded feature, orientation and question workflows through `facts features`, `facts orient`, and
  `facts ask`. Door/window names produce unvalidated candidates; conservative full cylindrical
  through-holes produce validated radius/length/axis/area geometry without claiming all hole forms.
  Orientation returns six bbox-projection candidates and only an explicitly assumed front. The common
  QuestionSpec/AnswerReport contract accepts explicit agent/user interpretations or a bounded offline
  Chinese/English grammar, preserving assumptions, count states, evidence and gaps.
- Target-isolated STEP SVG through `facts render --target occurrence:N --view-spec view.json`.
  OCCT hidden-line projection supports global-axis or explicit orthographic cameras, optional hidden
  lines and a bounded point count. A sibling `.view.json` manifest binds artifact, snapshot, target,
  camera/semantic assumptions, method, projected statistics and output hash. Both outputs are new-only.
- Explicit-root XREF handling supports independent `linked` artifact records and source-tagged
  `flatten` content with depth/file/byte/time budgets. Child evidence and units are preserved;
  unresolved, outside-root, cyclic or incomplete references prevent complete discovery.
- Neutral attribute-block drawing BOM through `drawing-bom`, with explicit part/quantity/material/
  description tags and containers, MINSERT multiplicity, and known/observed/unknown quantities. It
  does not infer title blocks or parse ACAD_TABLE semantics.
- Optional local DWG support requires a separately installed ODA File Converter and an explicitly
  supplied path. The original DWG remains the source artifact; the snapshot records the converter
  executable identity and derived DXF hash/size. ODA is proprietary, is not bundled or
  auto-installed, and its non-member license limits use to non-commercial applications. Without
  ODA, DWG returns `ADAPTER_UNAVAILABLE`.
- Declarative reviews with `snapshot.status`, `fact.present`, `numeric.compare` (`<=`, `>=`, `<`,
  `>`), `count.compare`, and `declared.value` checkers. Optional rule/finding `review_type` values
  distinguish `file_health`, `requirement_compliance` and `design_process_rule`, with per-type
  summaries in typed runs. Sourced packs under `rule-packs/` are explicit inputs, not hidden
  defaults or generic manufacturing standards. Requirements may carry an optional
  `source_sha256` for externally stored requirement bytes. Rules, parameters, requirement
  references, included-rule references and FactSet/snapshot/artifact binding are validated before
  evaluation. A scope selects an explicit `(rule_id, version)` when several versions coexist.
- `satisfied / violated / unknown / not_applicable` findings, scoped coverage, and RFC 8785-based
  content identities. Unordered inputs are canonicalized before hashing, and review recomputes and
  verifies every content ID instead of trusting supplied values. Unresolved partial/fatal
  diagnostics, unverified scope-required inputs, unmet discovery requirements, checker failures,
  empty requirements and in-scope rules with no candidates keep the report `incomplete`;
  `compliant_for_scope` requires ready status, complete discovery, full coverage, and no unresolved
  diagnostics.
- Entity matching (`native_ref`, `adapter_key`, and numeric `fingerprint` methods with explicit
  tolerances) used by change verification. It remains a library contract with no standalone match
  CLI; unmatched, ambiguous, incompletely discovered or cross-profile entities make the match report
  `incomplete`.
- Immutable `ChangeRequest`, `ChangePlan`, before/after `SourceManifest`, `ApprovalRecord`,
  `ExecutionRecord`, and `ModificationReport` contracts with recomputed content identities.
  Library builders construct root/derived manifests and approval/execution records from exact
  workspace bytes and explicit identities, timestamps and attestations; they never execute source.
  `facts prepare-change` derives a review-based request and external handoff plan without executing
  CAD. `facts verify-change` re-parses both artifacts under a fixed profile and checks preconditions,
  targets, invariants, non-target changes, data retention, manifests, original-rule re-review and
  optional approval/execution consistency.
- Independent output and provenance states: `verification_status=passed/failed/incomplete`,
  `execution_provenance=attested/unattested/contradicted`, and
  `change_observed=changed/no_change/unknown`. Passing output validation without an execution record
  remains `unattested`; an external handoff or new STEP alone never attests execution.
- Neutral model BOM extraction from assembly-aware snapshots. `facts bom` groups active occurrences
  by part definition, preserves definitions/occurrences/links, and reports explicit missing inputs.
  Quantities are `known` only with complete structure, `observed` when discovery/reconciliation is
  incomplete, or `unknown` with a null quantity when occurrence state is unknown.
- Read-only AP242 semantic-PMI extraction through `facts pmi`. A second XCAF read with GD&T transfer
  supplies declared dimensions, geometric tolerances and datums with values, units, qualifiers,
  modifiers, datum references, geometry links and source entries; the raw STEP model supplies the
  observed entity inventory and representation units. Presentation-only labels are counted but not
  emitted. Unreadable values, units, links and unsupported categories become explicit `PmiGap`s;
  `complete=true` means this bounded profile accounted for what it observed, not full AP242
  conformance. A file without semantic PMI returns a ready, complete empty result.
- Constrained neutral ProcessCardInput preparation for exactly one discovered STEP solid.
  `facts process-input` projects existing volume/area/bbox facts and explicit user-supplied context,
  and reports required `missing_inputs`. Declared material, semantic PMI projection and validated
  features are currently `UNSUPPORTED`; no feature values or manufacturing decisions are invented.
  Semantic PMI can be read separately with `facts pmi`.
- Machine-readable `inspect`, `query`, `resolve`, `features`, `orient`, `ask`, `render`, `review`,
  `drawing-bom`, `prepare-change`, `verify-change`, `bom`, `pmi`, `process-input`, and `doctor` CLI
  commands, including bounded selective output and JSON configuration errors with exit code 2. `doctor --check` diagnoses the
  local runtime and only hashes an explicitly supplied ODA file; it never discovers or executes ODA.

These are limited format-specific slices, not complete P1/P2/P3/P4/P5 releases. CAD execution is not embedded or invoked
by either change command; target derivation currently supports only `numeric.compare` findings.
Full AP242 semantic-PMI coverage, general ProcessCardInput preparation, wall-thickness measurement,
general feature recognition, suppression semantics, IFC and mesh adapters remain unimplemented. The
public design contract lives in [`docs/detailed-design.md`](docs/detailed-design.md).

## Use as an agent skill

The repository is also a Claude Code plugin. `.claude-plugin/plugin.json` points at `skills/`.
[`skills/cad-to-facts/SKILL.md`](skills/cad-to-facts/SKILL.md) routes facts, evidence-guided questions,
occurrence resolution, semantic PMI, drawings, review, BOM and change preparation/verification to
one-level references. [`skills/cad-view/SKILL.md`](skills/cad-view/SKILL.md) handles target-isolated
STEP SVG views and their manifests. Both drive the same `facts` CLI and deterministic core; neither
adds an AI layer to parsing, review, rendering or verification. A separate `cad-visual` VLM workflow
is only a future option, not an installed capability.

The plugin installs the skill, not the Python CLI. Install the CLI from a checkout of this
repository first:

```bash
uv tool install --python 3.13 .   # installs `facts` in an isolated uv tool environment
# or from GitHub:
uv tool install --python 3.13 "git+https://github.com/EthanLoveQueen/cad-to-facts.git"
# or: uv sync --locked       # then run `uv run facts ...` from the repository root
```

The explicit interpreter avoids accidentally reusing an unsupported tool Python. Tool installation
resolves package requirements rather than replaying every transitive `uv.lock` pin; use `uv run`
for the exact locked reference environment.

Load the skill for one session from the repository root:

```bash
claude --plugin-dir .
```

Or register the local marketplace and install the plugin:

```bash
claude plugin marketplace add .
claude plugin install cad-to-facts@cad-to-facts
```

Or install the plugin directly from GitHub:

```bash
claude plugin marketplace add EthanLoveQueen/cad-to-facts
claude plugin install cad-to-facts@cad-to-facts
```

If `facts` is not on PATH, run `uv run --project /path/to/cad-to-facts facts ...` from any working
directory. Use a clean checkout when publishing or installing from a local path: the plugin source
is the repository root, and local workspace artifacts such as `.venv/` should not be distributed.
The skill folders contain their own MIT `LICENSE` files.

The modification workflow calls the separately installed text-to-cad CAD skill; neither
text-to-cad nor its `cad-server` runtime is a Python dependency of this package.

## Environment and tests

The reference environment is Python 3.13 with `cadquery-ocp==8.0.1.1.0` and `ezdxf==1.4.5`.
ODA File Converter is an optional external DWG prerequisite, not a Python dependency.

```bash
uv sync --locked
uv run facts doctor --check
uv run pytest
```

`uv sync` downloads the locked Python and project dependencies into the local `.venv` when they are
not already available; the deterministic commands themselves are offline. See the
[installation guide](docs/installation.md) for isolated CLI/plugin installation and updates and the
[recovery playbook](docs/recovery.md) for doctor codes, adapter failures and verification recovery.
CI and distribution checks are defined in `.github/workflows/ci.yml` and `scripts/check_dist.py`.

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
[`docs/model-views.md`](docs/model-views.md) and the `cad-view` skill. Face/edge selectors, PNG and
VLM interpretation remain unimplemented.

## Ask bounded STEP model questions

```bash
uv run facts features assembly.step --query examples/features-doors-windows-holes.json
uv run facts orient assembly.step --selector examples/orient-right-door.json
uv run facts ask assembly.step --question "左侧的门在哪里？"
uv run facts ask assembly.step --question "门的正面是哪边？"
uv run facts ask assembly.step --question "有多少个孔？"
uv run facts ask assembly.step --spec examples/question-door-candidates.json
```

`features` separates unvalidated door/window name candidates from conservative validated cylindrical
through-holes. It does not validate general doors/windows or recognize blind, counterbored,
rectangular, intersecting and other holes; `general_feature_coverage` remains `unknown`.
`examples/orient-right-door.json` targets `occurrence:343` in the documented real container; for other
models, substitute an exact occurrence returned by your own `resolve` result.

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
[`docs/model-questions.md`](docs/model-questions.md).

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
uv run facts inspect drawing.dwg --oda-path "C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe"
```

DXF is read directly with ezdxf. DWG uses a separately installed ODA File Converter to create a
temporary local ACAD2018 DXF, then parses that derivative; neither the plugin nor `uv sync` installs
ODA. The converter path must be supplied explicitly with `--oda-path` (also accepted by
`facts review`); install locations are not guessed. If ODA is unavailable, inspection still returns
JSON with `snapshot.status=failed` and `ADAPTER_UNAVAILABLE`.

The drawing profile catalogs layers, model/paper-space layouts, non-layout blocks and entities. It
extracts declared type/layer/container, text and block-name/attribute facts, plus selected 2D lengths,
areas and circle circumferences. Curved LWPOLYLINEs use exact bulge-arc formulas. XREFs remain
unresolved by default; `--xref-mode linked|flatten` with explicit `--xref-root` directories enables
bounded local resolution. `drawing-bom --part-tag PART` extracts only explicitly configured block
attributes. Uncounted XREFs block BOM completeness unless `--allow-xref-exclusion` explicitly accepts
their exclusion from the selected scope. `facts ask` accepts an explicit `DrawingQuestionSpec` for
bounded drawing facts; drawing natural-language grammar, title-block inference, INSERT geometry
expansion and dimension-to-geometry association are not implemented. `examples/question-drawing.dxf`
and `examples/drawing-question.json` are a runnable analytic example; they do not establish exporter
interoperability. Query page sizes must be positive, and SVG rendering ignores
external raster images rather than reading them implicitly. None of these features infers title-block
semantics, and SVG is not fidelity proof. See
[the drawing contract](docs/drawing-analysis.md) for units, licensing and security limits and
[drawing questions](docs/drawing-questions.md) for the question profile.

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
unchanged. See [`rule-packs/README.md`](rule-packs/README.md) for source/applicability/validation
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
[`docs/semantic-pmi.md`](docs/semantic-pmi.md). OCCT-generated AP242 fixtures additionally pin
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
[change-verification reference](skills/cad-to-facts/references/change-verification.md) for the full
spec and record contract, or replay the packaged real run with the exact command in
[`examples/change-loop/README.md`](examples/change-loop/README.md). The example returns
`passed / attested / changed` and includes sanitized native build/export evidence; it remains a
test-harness attestation, not independent cryptographic proof. Its explicit
`--replay-relocated-output` option is only for archived path relocation and is disclosed in the
replay report.

## Validation limits

Current geometric fixtures are analytic parts written and read with OCCT. They establish repeatable
numerical smoke tests, not CAD-exporter interoperability. The pinned [P0 corpus](docs/corpus-validation.md)
adds local real files, malformed inputs, generated unit variants, NIST AP203/AP242 models and a KiCad
model. A local text-to-cad 0.11.10 smoke test observed an earlier real export and passed output
verification with honestly `unattested` provenance; its detailed record is maintainer-only and not
published. A separate attested change run used pre-execution approval and an explicit local execution
attestation, then achieved `verification_status=passed` and `execution_provenance=attested`; the
replayable public record is in [`examples/change-loop/README.md`](examples/change-loop/README.md).
This is a test-harness attestation, not independent cryptographic proof or production approval.
[Real-file validation records](docs/real-corpus.md) summarize read-only observations on
user-supplied production assemblies. Their identity, sizes, hashes and measurements are withheld,
and the files and private regression modules are not redistributed. The observations cover
centimetre normalization on a large flattened assembly, observed/incomplete BOMs where
PRODUCT/NAUO and XCAF counts do not reconcile, one AP242 assembly with complete discovery and a
complete BOM under this profile, a multi-root AP214 assembly with a partial single-part transfer,
and explicit no-PMI behavior on AP242/AP214 controls. The NIST AP242 fixture separately pins a
bounded semantic-PMI extraction: 12 dimensions (8 with values), 6 tolerances, 3 datums, 19 resolved
and 2 absent links, and seven explicit gaps including unsupported datum systems. These local
production observations are regression evidence, not exporter interoperability, a manufacturing
BOM or positive PMI coverage. Broader exporter coverage, full AP242 PMI coverage, source-native STEP matching, and more
source-backed change cases remain design/validation work.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Production test data under `test-data/`, the private corpus
manifest and private regression modules are not published; do not add them to commits.

## License

MIT. See [LICENSE](LICENSE). The skill folders contain their own MIT license files.
