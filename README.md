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

**Status:** `0.1.0` alpha. The implemented surface is intentionally narrow; see
[scope and honest limits](#scope-and-honest-limits).

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

- **Locate a part**: "where is the left door?" -> `facts ask` / `facts resolve` -> occurrence path,
  world bounding box and spatial assumptions.
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
/cad-to-facts where is the left door in examples/question-assembly.step?
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
| [Inspect STEP](docs/commands.md#inspect-a-step-file) | `facts inspect` | Artifact, snapshot, selective facts and explicit gaps |
| [Query drawings](docs/commands.md#inspect-or-review-a-dwgdxf-drawing) | `facts query` / `facts inspect --summary` | Bounded DXF/DWG entity, layer, block and text output |
| [Ask bounded questions](docs/commands.md#ask-bounded-step-model-questions) | `facts ask` | AnswerReport with assumptions, count states, evidence and gaps |
| [Feature candidates and orientation](docs/commands.md#ask-bounded-step-model-questions) | `facts features` / `facts orient` | Unvalidated name candidates, validated through-holes, assumed front |
| [Resolve and view](docs/commands.md#resolve-a-step-target-and-export-a-view) | `facts resolve` / `facts render` | Exact occurrence plus new-only SVG and `.view.json` |
| [Review](docs/commands.md#review-a-step-file) | `facts review` | Findings and coverage for STEP and drawing snapshots |
| [BOM and PMI](docs/commands.md#extract-a-model-bom) | `facts bom` / `facts pmi` | Neutral model BOM and declared AP242 semantic PMI |
| [Drawing BOM](docs/commands.md#inspect-or-review-a-dwgdxf-drawing) | `facts drawing-bom` | Explicit attribute-tag BOM from drawing blocks |
| [Prepare a change](docs/commands.md#prepare-and-verify-a-change) | `facts prepare-change` | Immutable `ChangeRequest` and external handoff plan; no execution |
| [Verify a change](docs/commands.md#prepare-and-verify-a-change) | `facts verify-change` | Re-parsed output checks and separate execution provenance |
| [Prepare process input](docs/commands.md#prepare-a-constrained-process-card-input) | `facts process-input` | Constrained single-solid neutral work product |
| [Diagnose setup](#development-and-tests) | `facts doctor --check` | Python, dependency, temp-directory and optional ODA diagnostics |

All commands emit JSON with evidence and honest gaps. See the [command reference](docs/commands.md).

## Quick start

### Install

Prerequisites: `uv` and Python 3.13. Clone the repository and create the locked environment:

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

- [Review against explicit requirements](docs/commands.md#review-a-step-file)
- [Resolve an occurrence and render an SVG](docs/commands.md#resolve-a-step-target-and-export-a-view)
- [Extract a model BOM](docs/commands.md#extract-a-model-bom) or [declared semantic PMI](docs/commands.md#extract-declared-semantic-pmi)
- [Prepare and verify an external change](docs/commands.md#prepare-and-verify-a-change)

## CLI conventions

- Every command writes one JSON object to stdout; errors are JSON objects too.
- Exit `0` for a normal result, including `violated` findings and `ambiguous` answers.
- Exit `2` for configuration or input errors.
- Exit `3` for internal or checker failures; `review` and `verify-change` also return `3` when
  `tool_error=true`.
- Source files are read-only. Commands that create output (`render`) refuse to overwrite existing
  files.
- The deterministic core is offline and does not call AI or network services.
- Configuration inputs are JSON; YAML is not accepted.
- Envelopes carry `schema_version`; persisted records use RFC 8785 canonical JSON content identities.

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
| DXF | ezdxf; layers, blocks, text, selected 2D measurements | Review, drawing BOM and bounded questions | Unitless values remain explicit gaps |
| DWG | Via optional ODA File Converter | Review and drawing workflows | Converter is proprietary, not bundled; explicit `--oda-path` required |

Not implemented: IFC, mesh adapters, general feature recognition, title-block inference, PNG output
and VLM inference.

## Command reference

The full walkthrough for every command — inputs, outputs, limits and runnable examples — is in
[`docs/commands.md`](docs/commands.md). The [capability table](#capabilities) links directly to each
section.

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

- [Command reference](docs/commands.md)
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
- [Glossary](GLOSSARY.md)
- [Security policy](SECURITY.md)

## Repository layout

| Path | Contents |
| --- | --- |
| `src/cad_to_facts/` | Deterministic core and `facts` CLI |
| `skills/` | Two Claude Code skills and one-level references |
| `docs/` | Behavioral contracts, installation, recovery and implementation status |
| `tests/` | Public-interface and regression tests |
| `examples/` | Runnable analytic STEP/DXF/JSON examples |
| `rule-packs/` | Explicit, sourced review rule packs |
| `evals/` | Local model-backed skill behavior evaluations |
| `.claude-plugin/` | Plugin and marketplace manifests |

The CLI and its JSON envelopes are the primary integration surface. Python modules under `src/` are
importable and used by the tests, but no separately versioned library API is promised yet. See the
[detailed design](docs/detailed-design.md) for the contracts.

## Development and tests

The reference environment is Python 3.13 with `cadquery-ocp==8.0.1.1.0` and `ezdxf==1.4.5`.
ODA File Converter is an optional external DWG prerequisite, not a Python dependency.

```bash
uv sync --locked
uv run facts doctor --check
uv run pytest
uv run pytest tests/test_review_numeric.py   # one module
uv build
uv run python scripts/check_dist.py dist
claude plugin validate .claude-plugin/marketplace.json
```

`uv sync` downloads the locked Python and project dependencies into the local `.venv` when they are
not already available; the deterministic commands themselves are offline. See the
[installation guide](docs/installation.md) for isolated CLI/plugin installation and updates and the
[recovery playbook](docs/recovery.md) for doctor codes, adapter failures and verification recovery.
CI runs the locked install, doctor, tests, build and archive checks on Ubuntu, Windows and macOS; see
`.github/workflows/ci.yml` and `scripts/check_dist.py`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Production test data under `test-data/`, the private corpus
manifest and private regression modules are not published; do not add them to commits.

## License

MIT. See [LICENSE](LICENSE). The skill folders contain their own MIT license files.
