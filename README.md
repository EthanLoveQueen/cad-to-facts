# cad-to-facts

[![CI](https://github.com/EthanLoveQueen/cad-to-facts/actions/workflows/ci.yml/badge.svg)](https://github.com/EthanLoveQueen/cad-to-facts/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](pyproject.toml)
[![Agent skill](https://img.shields.io/badge/agent-skill-5A67D8)](skills/)

**Traceable CAD facts. Deterministic reviews. Verified changes.**

cad-to-facts is an agent-first CAD evidence toolkit. It turns STEP, DXF and optional DWG files into
evidence-bound JSON, answers bounded engineering questions, reviews files against explicit
requirements, and verifies externally produced changes. The deterministic core runs locally; packaged
agent skills tell the model when and how to call it without inventing facts.

> **Using an agent?** Start with [Use it as an agent skill](#use-it-as-an-agent-skill). The CLI is the
> deterministic engine underneath.

[Agent skill](#use-it-as-an-agent-skill) · [Capabilities](#capabilities) · [Quick start](#quick-start) · [How it works](#how-it-works) · [Scope](#scope-and-honest-limits) · [Docs](#documentation)

## Why cad-to-facts

- **Facts with provenance.** Every fact binds an artifact SHA-256, snapshot, units, method and source
  entities. Entity IDs are snapshot-scoped, not assumed stable across parsers or revisions.
- **Unknowns stay unknown.** Missing, unsupported, failed and not-applicable are separate states.
  Unverifiable measurements become explicit gaps, never zeroes or guesses.
- **Changes are verified, not assumed.** Request, plan, approval, execution and result are separate
  contracts. Output validation can pass while execution provenance remains `unattested`.
- **Agent-ready, deterministic underneath.** The same CLI powers a Claude Code plugin; parsing,
  measurement, review, BOM extraction and verification stay offline.

## Use it as an agent skill

The primary integration is an agent skill. The repository ships two Claude Code skills that turn the
deterministic `facts` CLI into an evidence-disciplined workflow:

| Skill | What the agent uses it for |
| --- | --- |
| [`cad-to-facts`](skills/cad-to-facts/SKILL.md) | Inspect STEP/DXF/DWG, resolve occurrences, ask bounded questions, extract PMI/BOM, review requirements, prepare and verify changes |
| [`cad-view`](skills/cad-view/SKILL.md) | Resolve an exact STEP occurrence and render a target-isolated SVG with its evidence manifest |

The skills are not a second AI layer. They contain `SKILL.md` routing and one-level references that
tell the agent which command to run, which inputs are required, and how to preserve assumptions,
coverage and gaps. Parsing, measurement, review, BOM extraction and verification remain in the
offline Python core. Output stays selective, so an agent does not need to ingest every face or
triangle; candidates, assumptions and unknown counts are never promoted to facts.

### How the agent uses it

```text
User question
  -> skill selects a bounded facts workflow
    -> facts CLI emits evidence-bound JSON
      -> agent answers with values, assumptions and gaps
```

Typical requests:

- **Locate a part / 定位零件**: "where is the left door?" or "左侧的门在哪里？" -> `facts ask` /
  `facts resolve` -> occurrence path, world bounding box and spatial assumptions.
- **Review a file**: "does this STEP meet the requirements?" -> `facts review` with explicit
  requirements/rules/scope/context -> findings, coverage and unresolved diagnostics.
- **Render a view**: "export the left door front view" -> `cad-to-facts` resolves the exact target;
  `cad-view` renders it -> SVG plus `.view.json` binding artifact, snapshot, target and camera.
- **Extract downstream data**: "what is the model BOM?" -> `facts bom` -> neutral BOM with
  known/observed/unknown quantities; `facts pmi` extracts declared semantic PMI separately.

### Install the skill

The plugin installs the skill, not the CLI. Install the CLI first:

```bash
uv tool install --python 3.13 "git+https://github.com/EthanLoveQueen/cad-to-facts.git"
facts doctor --check
```

Then install the plugin in Claude Code:

```bash
claude plugin marketplace add EthanLoveQueen/cad-to-facts
claude plugin install cad-to-facts@cad-to-facts
```

Then invoke `/cad-to-facts` in a Claude Code session:

```text
/cad-to-facts 检查 examples/question-assembly.step，左侧的门在哪里？
```

For local skill development:

```bash
git clone https://github.com/EthanLoveQueen/cad-to-facts.git
cd cad-to-facts
uv sync --locked
claude --plugin-dir .
```

The skill sources are plain `SKILL.md` plus one-level `references/`; an OpenAI agent interface file is
included at `skills/cad-to-facts/agents/openai.yaml`. The same CLI contract can be adapted by other
agent runtimes, but only the Claude Code packaging is validated in this repository. The modification
workflow calls the separately installed text-to-cad skill; neither text-to-cad nor its `cad-server`
runtime is a Python dependency. The skill folders contain their own MIT licenses.

Model-backed skill evals live under `evals/` and run locally with `--no-publish`; CI validates the
CLI, packaging and plugin manifest, not model behavior. See the
[skill](skills/cad-to-facts/SKILL.md), [view skill](skills/cad-view/SKILL.md) and
[installation guide](docs/installation.md).

## Capabilities

| Capability | Command | Result |
| --- | --- | --- |
| Inspect STEP | `facts inspect` | Artifact, snapshot, selective facts and explicit gaps |
| Query drawings | `facts query` / `facts inspect --summary` | Bounded DXF/DWG entity, layer, block and text output |
| Ask bounded questions | `facts ask` | AnswerReport with assumptions, count states, evidence and gaps |
| Resolve and view | `facts resolve` / `facts render` | Exact occurrence plus new-only SVG and `.view.json` |
| Review | `facts review` | `satisfied / violated / unknown / not_applicable` findings and coverage |
| BOM and PMI | `facts bom` / `facts pmi` | Neutral model BOM and declared AP242 semantic PMI |
| Prepare a change | `facts prepare-change` | Immutable `ChangeRequest` and external handoff plan; no execution |
| Verify a change | `facts verify-change` | Re-parsed output checks and separate execution provenance |
| Prepare process input | `facts process-input` | Constrained single-solid neutral work product |

All commands emit JSON with evidence and honest gaps. See the [command sections](#inspect-a-step-file).

## Quick start

### Install

Clone the repository and create the locked environment:

```bash
git clone https://github.com/EthanLoveQueen/cad-to-facts.git
cd cad-to-facts
uv sync --locked
uv run facts doctor --check
```

For an isolated CLI on PATH instead (the examples below require a checkout):

```bash
uv tool install --python 3.13 "git+https://github.com/EthanLoveQueen/cad-to-facts.git"
facts doctor --check
```

If you installed the CLI as a tool, use `facts` in place of `uv run facts` in the examples below.

Python 3.13 is the reference runtime; the explicit `--python 3.13` avoids reusing an unsupported
tool interpreter. `cadquery-ocp` and `ezdxf` are installed as dependencies. DWG support requires an
optional, separately installed ODA File Converter supplied with `--oda-path`; without it, DWG returns
`ADAPTER_UNAVAILABLE` instead of guessing.

### Inspect a STEP file

```bash
uv run facts inspect examples/box.step --limit 1
```

Abridged actual output:

```json
{
  "snapshot": {
    "status": "ready",
    "entity_discovery": "complete",
    "units": {"length": "mm", "angle": "rad", "solid_angle": "sr"},
    "diagnostics": []
  },
  "selection": {"entity_total": 1, "entities_returned": 1, "truncated": false},
  "factset": {
    "facts": [
      {"predicate": "volume", "value": 6000.0, "unit": "mm^3"},
      {"predicate": "area", "value": 2200.0, "unit": "mm^2"},
      {"predicate": "bbox.extent.z", "value": 30.0, "unit": "mm"}
    ],
    "gaps": []
  }
}
```

### Ask a bounded question

```bash
uv run facts ask examples/question-assembly.step --question "where is the left door?"
```

Abridged actual output:

```json
{
  "answer": {
    "status": "answered",
    "complete": true,
    "question": {
      "interpretation_basis": "deterministic_grammar",
      "assumptions": [
        "The implicit spatial reference is the union of all root-occurrence bounding boxes in the global front camera; left/right/up/down are not source-declared semantics"
      ]
    },
    "answers": [{
      "status": "answered",
      "resolution": {
        "status": "resolved",
        "candidate_total": 1,
        "candidates": [{"name": "Left door", "path": "occurrence:0/occurrence:1"}]
      }
    }]
  }
}
```

Name candidates and assumed directions are evidence, not validated function. Ambiguous results never
choose a first match.

### Next steps

- [Review against explicit requirements](#review-a-step-file)
- [Resolve an occurrence and render an SVG](#resolve-a-step-target-and-export-a-view)
- [Extract a model BOM](#extract-a-model-bom) or [declared semantic PMI](#extract-declared-semantic-pmi)
- [Prepare and verify an external change](#prepare-and-verify-a-change)

## How it works

```text
User question or reviewed change
  -> agent skill (SKILL.md + references) or direct CLI
    -> SourceArtifact (immutable bytes + SHA-256)
      -> ModelSnapshot (parser provenance, units, entity discovery, diagnostics)
        -> FactSet (declared / measured / derived facts + evidence + gaps)
          -> ReviewReport | BOMExtract | AnswerReport | ChangeRequest / ModificationReport
```

STEP B-rep, DXF drawings and assemblies keep format-specific profiles; there is no universal
`bodies/features` intermediate representation. OCCT handles geometry, ezdxf handles drawings, and the
project-owned code handles contracts, evidence, rules and verification.

## Scope and honest limits

cad-to-facts is **not** a geometry kernel or a universal CAD converter. It does not infer
manufacturing intent, certify a design, recognize arbitrary features, or claim STEP exporter
interoperability. AP242 semantic PMI, drawing semantics, feature recognition, orientation and
`process-input` are deliberately bounded profiles; required but unsupported inputs stay explicit
`UNSUPPORTED` gaps. The skill layer routes work to the CLI; it does not add VLM inference, general
feature recognition or general drawing understanding.

The implemented surface is intentionally narrow: STEP facts, review, model BOM, declared PMI,
target views and verified changes, plus a first DXF/DWG drawing slice and a constrained single-solid
process-input profile. It is not a complete release across all planned format slices. See
[implementation status](docs/status.md) for the exact supported/unsupported matrix.

## Supported formats

| Format | Read and measure | Review / BOM / PMI | Notes |
| --- | --- | --- | --- |
| STEP | OCCT B-rep; volume, area, bbox; assembly scope via XCAF | Review, model BOM, declared semantic PMI, change verification | `single_part` and `assembly` read scopes |
| DXF | ezdxf; layers, blocks, text, selected 2D measurements | Drawing BOM and bounded questions | Unitless values remain explicit gaps |
| DWG | Via optional ODA File Converter | Drawing workflows | Converter is proprietary, not bundled; explicit `--oda-path` required |

Not implemented: IFC, mesh adapters, general feature recognition, title-block inference, PNG output
and VLM inference.

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
uv run facts features examples/question-assembly.step --query examples/features-doors-windows-holes.json
uv run facts orient examples/question-assembly.step --selector examples/resolve-left-door.json
uv run facts ask examples/question-assembly.step --question "左侧的门在哪里？"
uv run facts ask examples/question-assembly.step --question "门的正面是哪边？"
uv run facts ask examples/question-assembly.step --question "有多少个孔？"
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
BOM or positive PMI coverage. Broader exporter coverage, full AP242 PMI coverage, source-native STEP
matching, and more source-backed change cases remain design/validation work.

## Documentation

- [Installation and setup](docs/installation.md)
- [Implementation status](docs/status.md)
- [Detailed design](docs/detailed-design.md)
- [STEP model views](docs/model-views.md)
- [Model questions](docs/model-questions.md)
- [Drawing analysis](docs/drawing-analysis.md) and [drawing questions](docs/drawing-questions.md)
- [Semantic PMI](docs/semantic-pmi.md)
- [Change verification](skills/cad-to-facts/references/change-verification.md)
- [Recovery](docs/recovery.md)
- [Corpus validation](docs/corpus-validation.md)

## Development and tests

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

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Production test data under `test-data/`, the private corpus
manifest and private regression modules are not published; do not add them to commits.

## License

MIT. See [LICENSE](LICENSE). The skill folders contain their own MIT license files.
