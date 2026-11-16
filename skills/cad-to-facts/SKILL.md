---
name: cad-to-facts
description: Extracts traceable STEP and DWG/DXF facts, declared AP242 semantic PMI and model/drawing BOMs; reviews explicit requirements, resolves STEP occurrences, answers bounded model questions, and verifies external changes. Use for evidence-guided design questions, feature candidates, assumed orientation, dimensions, drawing queries, file health, BOMs, or text-to-cad handoff. Returns provenance, coverage and honest unknowns. Use sibling cad-view for target-isolated STEP SVG. DWG needs optional ODA; VLM inference is not implemented.
license: MIT
---

# CAD facts and requirements review

This skill drives the `facts` command in the cad-to-facts repository. OCCT parses STEP; ezdxf parses
DXF and the DXF produced from DWG by optional local ODA conversion. The deterministic core measures,
evaluates and verifies. There is no AI in the measurement, review
or verification path, no network access, and no modification of the source file. Change preparation
and output verification are implemented; CAD execution remains external. Assembly-aware model BOM
extraction, a constrained single-solid ProcessCardInput profile, and bounded AP242 semantic-PMI
extraction are implemented.

## What exists

| Capability | Command | Status |
| --- | --- | --- |
| Artifact hash, snapshot, volume/area/bounding-box facts | `facts inspect model.step` | Implemented for STEP |
| Declared AP242 semantic dimensions, tolerances and datums | `facts pmi model.step` | Implemented subset; values, units, links, gaps and no conformance claim |
| Drawing structure, text/layer/block and basic 2D measurements | `facts inspect drawing.dxf` / `drawing.dwg` | Implemented; DWG needs optional ODA |
| Selective drawing summaries, filtered pages and SVG review renders | `facts inspect --summary`, `facts query`, `facts render` | Implemented |
| STEP occurrence and spatial reference resolution | `facts resolve --selector ...` | Implemented; unique/ambiguous/unresolved/failed, explicit camera/reference, never first-match |
| Bounded door/window/hole candidates and through-hole geometry | `facts features --query ...` | Implemented; name candidates stay unvalidated, general coverage unknown |
| Assumed design-front orientation | `facts orient --selector ...` | Implemented heuristic; six candidates, ambiguity diagnostics, never source-declared |
| STEP QuestionSpec/AnswerReport and bounded Chinese/English questions | `facts ask model.step --spec ...` / `--question ...` | Implemented; interpretations, counts, geometry, assumptions and gaps stay separate |
| Bounded drawing fact questions | `facts ask drawing.dxf --spec ...` | Implemented drawing profile; explicit spec only, entity/text/layer/block/measurement/dimension/candidate/BOM intents |
| Target-isolated STEP SVG + view manifest | `facts render --target ... --view-spec ...` | Implemented through the sibling `cad-view` workflow |
| Explicit-root linked/flattened XREF evidence | Drawing `--xref-mode` / `--xref-root` options | Implemented with safety budgets |
| Attribute-block drawing BOM | `facts drawing-bom --part-tag ...` | Implemented; explicit tags, incomplete stays incomplete |
| Requirements review with findings, gaps, diagnostics and coverage | `facts review` | Implemented |
| Immutable change request and external-executor plan | `facts prepare-change` | Implemented; no CAD execution |
| New-artifact checks, source manifests, execution provenance and re-review | `facts verify-change` | Implemented; no CAD execution |
| Assembly model BOM extract | `facts bom` | Implemented; incomplete structure stays incomplete |
| Process-card input preparation | `facts process-input` | Implemented for one STEP solid, five geometry facts and explicit user context; no planning |
| Local environment diagnostics | `facts doctor --check` | Implemented; optional ODA path is explicit and never executed |

IFC, meshes and general validated door/window/hole recognition are not implemented; only the bounded
feature recognizer above exists. Semantic PMI is implemented as a bounded STEP AP242 profile, not as
full AP242 conformance.
`single_part` STEP reads detect and disclose assembly flattening; `assembly` reads preserve XCAF
structure. DXF is available after normal dependency installation; DWG additionally requires ODA.

## Setup

The skill drives a Python CLI; installing the plugin does not install that CLI. Use a checkout of
this repository. The reference environment is Python 3.13 with the locked `cadquery-ocp` and `ezdxf`
dependencies. DWG additionally needs a separately installed ODA File Converter; `uv sync` does not
install or download it.

Run these commands from the repository root: the directory containing `pyproject.toml` and
`skills/cad-to-facts/`. If this skill is loaded from an installed plugin, that root is two levels
above the skill's base directory.

```bash
uv sync --locked
uv run facts doctor --check
uv run facts inspect part.step
```

To install `facts` as a uv tool for use from any working directory (ensure uv's tool bin
directory is on PATH):

```bash
uv tool install --python 3.13 .
facts inspect part.step
```

If `facts` is not on PATH, run `uv run --project /path/to/cad-to-facts facts ...` from anywhere.
Use `uv sync --locked`/`uv run` for the exact locked transitive environment; `uv tool install`
resolves package requirements in isolation and must still use explicit Python 3.13.
The CLI accepts JSON configuration, not YAML.

## Start with the task

| Task | Start with | Reference |
| --- | --- | --- |
| **Answer a question with ambiguous object wording** | Run `facts ask model.step --question "..."` for supported wording, or write an explicit QuestionSpec for `--spec`. Preserve interpretations, candidates, assumptions, count states and gaps. | [Evidence-guided questions](references/question-answering.md) |
| **Resolve a STEP occurrence** | `facts resolve assembly.step --selector selector.json`; read status, discovery, completeness and every candidate before binding later work. | [Evidence-guided questions](references/question-answering.md) |
| **Export a STEP occurrence view** | Use the sibling `cad-view` skill: resolve one occurrence, write a ViewSpecification, then `facts render --target ... --view-spec ... --output ....svg`. | Use `cad-view`; CLI syntax is also in [CLI](references/cli.md) |
| **Inspect a STEP file or collect evidence** | `facts inspect part.step`; read `snapshot.status`, `entity_discovery`, diagnostics, then facts and gaps. | [Facts and gaps](references/facts-and-gaps.md) |
| **Extract semantic PMI** | Run `facts pmi part.step`; read `status`, `complete`, `coverage`, `gaps`, units and link states before using any annotation. | [Semantic PMI](references/pmi.md) |
| **Inspect a DWG/DXF drawing** | Start with `facts inspect drawing.dxf --summary`; use `facts query` for filtered pages. For DWG, install ODA separately and pass its executable with `--oda-path`. Read drawing diagnostics before using facts. | [DWG and DXF drawings](references/drawings.md) |
| **Answer a bounded drawing question** | Write an explicit `DrawingQuestionSpec` and run `facts ask drawing.dxf --spec ...`. Set `containers`, entity kinds, layer-state policy and units deliberately; never treat raw entity counts or name candidates as engineering totals. | [Drawing questions](references/drawings.md#drawing-questions) |
| **Render a drawing for review** | `facts render drawing.dxf --output drawing.svg`; use explicit `--xref-root` and `--xref-mode flatten` only when referenced content is required. Never treat SVG as fidelity proof. | [DWG and DXF drawings](references/drawings.md) |
| **Review a STEP model or drawing** | Four explicit JSON files, then `facts review <file> --requirements ... --rules ... --scope ... --context ...`. Select drawing entities with kinds such as `line` or `text`, not `solid`. | [Review contract](references/review-contract.md) |
| **Explain a status, gap, diagnostic or coverage number** | The relevant report field; never infer beyond it. | [Review contract](references/review-contract.md) |
| **Fix a CLI error or interpret an exit code** | Run `facts doctor --check`; read its machine-readable checks and the JSON error object on stdout. Configuration errors are exit 2; doctor environment failure is exit 1. | [CLI](references/cli.md) |
| **Prepare or verify a text-to-cad change** | Run `facts prepare-change` with the original report and an explicit spec, invoke the separately installed CAD skill only with approval, then run `facts verify-change` on the new artifact. Never fabricate approvals, executions or manifests. | [Change verification](references/change-verification.md) |
| **Extract a model BOM** | Run `facts bom assembly.step`; check `complete`, reconciliation diagnostics, `quantity_state` and `missing_inputs` before using any quantity. | [BOM extraction](references/bom.md) |
| **Extract a drawing attribute BOM** | Run `facts drawing-bom drawing.dxf --part-tag ...` with explicit property/quantity tags and containers. Do not guess title-block tags or count linked XREFs implicitly. | [DWG and DXF drawings](references/drawings.md) |
| **Prepare a process-card input** | For one STEP solid, run `facts process-input part.step --context ...`; read `complete`, `missing_inputs` and external provenance. Never invent features, PMI or manufacturing plans. | [ProcessCardInput](references/process-input.md) |

## Question and target workflow

For free-form wording, use the evidence loop in
[Evidence-guided questions](references/question-answering.md), not a one-shot name search:

1. **Decompose** subject, intent, reference frame, evidence policy and deliverable. Split compound
   questions instead of letting one successful lookup answer everything.
2. **Interpret explicitly** with `--question` for bounded wording or an `agent_interpretation`
   QuestionSpec for `--spec`. Preserve original text, alternatives and introduced assumptions.
3. **Inspect the result** and choose the next evidence action from `answered / partial / ambiguous /
   unresolved / unsupported / failed`, discovery, candidates, diagnostics and gaps. Do not repeat an
   unchanged command without new evidence.
4. **Resolve decision-changing ambiguity** with an explicitly justified constraint, conditional answers
   for each exact target, or one focused user question. Never choose the first candidate.
5. **Orchestrate deliverables** across direct facts/PMI/BOM/review commands and `cad-view`; bind an SVG
   to one exact occurrence and preserve assumed-view semantics and artifact/snapshot checks.
6. **Synthesize by evidence class**: supported values, count state, candidates/alternatives, assumptions,
   gaps and output paths. `complete` covers only the declared interpretation and evidence policy.

```bash
uv run facts ask assembly.step --question "左侧的门在哪里？"
uv run facts ask assembly.step --spec examples/question-door-candidates.json
uv run facts resolve assembly.step --selector examples/resolve-left-door.json
```

Door/window name matches are unvalidated candidates; validated cylindrical through-hole counts are
observed-only and do not cover other hole forms. Spatial relations need an explicit camera/reference.
Assumed-front answers never become source declarations. No match is not proof of absence. A resolved
occurrence is not a ChangeRequest, persistent identity or editable source-code location.

### Drawing questions

DWG/DXF questions use a sibling `DrawingQuestionSpec` and do not reuse STEP occurrence, feature or
orientation intents. Drawing `--question` is not implemented; translate the user's wording into an
explicit spec with `interpretation_basis=agent_interpretation`. State the container scope (`Model`,
paper space or block definitions), entity kinds, layer-state policy and units because an omitted
container means the whole catalog. Raw counts are entity counts, not semantic edges or engineering
features. Unitless measurements remain unknown; INSERT geometry is not expanded; dimension values are
not associated with annotated geometry. Name candidates stay `unvalidated` with unknown general
semantic coverage. Use `semantic_evidence` to collect declared block/layer/text/attribute-tag context,
including attached ATTRIB values for matched INSERTs; it stays evidence, not an inferred
material/part/function field. For the full intent list, count states and limits, read
[Drawing questions](references/drawings.md#drawing-questions).

## Review workflow

### 1. Inspect before reviewing

```bash
uv run facts inspect part.step
```

The JSON contains `artifact` (raw-byte SHA-256 and size), `snapshot` (parser/kernel version, units,
status, discovery state, entities, diagnostics), `factset` (facts and gaps), and `selection` (entity
limit and cursor). For the 10 × 20 × 30 mm analytic box used by the tests, the snapshot is
`ready`/`complete` with one `solid:0`, and the fact values are 6000 mm³, 2200 mm², and extents
10/20/30 mm. A malformed file yields `status=failed`, `entity_discovery=unknown`, and a
`PARSE_FAILED` diagnostic instead of a crash.

### 2. Write the four review inputs explicitly

Requirements are not rules, and there is no default scope. A minimal review binding a 30 mm height
limit looks like this (the complete files are in `examples/`):

```json
{
  "requirements": [
    {
      "requirement_id": "req-height",
      "text": "Overall height must not exceed 30 mm",
      "source_ref": "requirements.json#req-height"
    }
  ]
}
```

```json
{
  "version": "1",
  "rules": [
    {
      "rule_id": "max-height",
      "version": "1",
      "requirement_refs": ["req-height"],
      "subject_selector": {"entity_kind": "solid"},
      "inputs": [{"name": "height", "predicate": "bbox.extent.z"}],
      "checker": "numeric.compare",
      "parameters": {"operator": "<=", "threshold": 30.0, "unit": "mm", "abs_tol": 1e-7},
      "severity": "error",
      "source": {"reviewed_by": "example"}
    }
  ]
}
```

The scope names included rules, subject selectors, required inputs and discovery requirements; the
context carries values independent of the file. Requirements are never silently treated as
executable rules. A scope entry may be `{"rule_id": "...", "version": "..."}`; use that form when
the RuleSet contains several versions of the same rule, since a bare ID is then ambiguous.

### 3. Run the review

```bash
uv run facts review part.step \
  --requirements examples/requirements.json \
  --rules examples/rules.json \
  --scope examples/review-scope.json \
  --context examples/review-context.json
```

A successful review prints one JSON `ReviewReport` object. A violation is still a successful review:
the process exits 0 and the report says `overall_status=non_compliant`. Exit 2 means the inputs are
invalid; exit 3 means an internal/checker failure (`tool_error=true` when a report was produced).

For readiness-only review, the four files in `rule-packs/step-file-health/` are a sourced,
applicability-limited pack with a public validation record. It is not a design or manufacturing
standard. Rules may declare `review_type=file_health|requirement_compliance|design_process_rule`;
typed reports include per-type summaries. Wholly legacy reports retain null optional typed fields
and their existing content identities. Never invent a generic manufacturing rule pack.

### 4. Read the result honestly

| Field | Meaning |
| --- | --- |
| `overall_status` | `non_compliant` if any finding is violated; otherwise `compliant_for_scope` only when `complete=true`; otherwise `incomplete`. |
| `complete` | Ready snapshot, complete discovery, no unresolved diagnostics, every scope-required input resolved by a fact or a proven `ABSENT` gap, no unknown rule evaluations, at least one decision, and every decision-required candidate fully inspected. |
| `coverage` | Rule coverage counts satisfied + violated over satisfied + violated + unknown. Entity coverage is `null` when discovery is not complete; a discovered-only ratio is reported separately. |
| `generated_gaps` | Missing required data the reviewer had to record; they block completeness. |
| `diagnostics` | Snapshot, FactSet and review diagnostics. Any non-resolved partial/fatal or discovery-affecting diagnostic blocks completeness, including `accepted`-but-unresolved ones. |
| `tool_error` | A checker failed while evaluating. It is never silently converted into satisfied. |

`compliant_for_scope` applies only to the declared rules and scope. It is not a product
certification, and it does not prove exporter interoperability.

### 5. Check each change

After changing a requirement, rule, scope or context file, re-run the review and verify the change
appeared where expected:

- a changed threshold changes the finding status, not just the report ID;
- a new `required_inputs` entry with no fact or gap produces a `NOT_COMPUTED` gap and `incomplete`;
  an existing `UNSUPPORTED`, `UNKNOWN_UNIT`, `PARSE_FAILED`, `MEASUREMENT_FAILED` or `NOT_COMPUTED`
  gap for a scope-required
  input also stays unresolved and keeps the report incomplete;
- a scope-required input resolved by a proved `ABSENT` gap counts as a resolved absence, not an
  extraction failure;
- a typo in `requirement_refs` or `included_rules` produces exit 2 and a JSON configuration error,
  not a report;
- a changed scope's `discovery_requirements` produces `DISCOVERY_REQUIREMENT_UNMET` when the entity
  kind was not discovered;
- an unsupported predicate produces an `UNSUPPORTED` gap; it stays incomplete when a rule or
  scope-required input depends on it.

Never hand-edit a report to change its status. Re-run the deterministic review instead.

## Drawing workflow

Run `facts inspect drawing.dxf --summary`, then use `facts query` for selected entities, or for DWG
ask the user for their ODA File Converter executable and pass it with `--oda-path`. The adapter does
not search PATH or default install locations. DXF needs no external converter. Read
`snapshot.drawing` for layers, layouts, blocks, XREF and conversion evidence; check audit, unit and
external-reference diagnostics before treating the result as complete.

Drawing facts cover declared type/layer/container, text and block names, plus selected lengths and
areas. Unitless drawings do not default to millimetres, and LWPOLYLINE bulges use exact arc formulas
rather than chord approximations. XREFs stay unresolved unless the user supplies explicit roots and
selects linked or flattened mode; flattened facts retain each child artifact and unit. `render`
creates a new SVG for review only. `drawing-bom` requires explicit attribute tags and never infers a
title block. See [DWG and DXF drawings](references/drawings.md) for ODA licensing, XREF safety,
conversion provenance and supported predicates.

## Model BOM workflow

Run `facts bom assembly.step`. It reads with `read_scope=assembly`, groups active leaf occurrences
by part-definition identity, and returns self-contained definitions, occurrences and links. Read
`complete` and diagnostics first: `quantity_state=observed` is not a known complete quantity,
`unknown` has `quantity=null`, and `coverage` totals all three quantity states. Add
`--require-property name` only when a missing name must be reported; arbitrary properties such as
material are currently unsupported, not inferred. See [BOM extraction](references/bom.md).

## Semantic PMI workflow

Run `facts pmi part.step`. Read `pmi.status`, `pmi.complete`, `pmi.coverage`, `pmi.gaps`,
`pmi.diagnostics`, `pmi.units` and each annotation's `value`, `unit` and `link_status` before using
a dimension, tolerance or datum. Presentation-only labels are counted, not emitted. A null value or
link is not zero and not absent by design; the matching gap states what the reader could not
provide. Magnitude tolerances have no plus/minus direction and must not be presented as signed.
Geometry links are snapshot-scoped `solid:N` references, not stable face IDs. A file with no
semantic PMI is `ready`/`complete` with zero annotations; AP242 conformance, inspection planning and
manufacturing decisions are not claimed. See [Semantic PMI](references/pmi.md).

## Constrained process-input workflow

For one STEP solid, run `facts process-input part.step --context context.json`. Default required
context is `material`, `stock`, `batch_size`; these remain user-supplied external inputs. The command
projects only existing volume, area and bbox facts. Declared material and validated features are
unsupported gaps. Semantic PMI can be extracted separately with `facts pmi`, but it is not projected
into ProcessCardInput; `--require-design-input semantic_pmi` therefore keeps the work product
incomplete. Zero or multiple solids remain incomplete; never select one implicitly. Read `complete`,
`coverage`, `missing_inputs` and diagnostics before downstream use. No operations, setups,
machine/tool selection, cutting parameters, cycle time, template or production approval is generated.
See [ProcessCardInput](references/process-input.md).

## Change workflow

1. Review the baseline and save the resulting report. Choose a `violated` or `unknown`
   `numeric.compare` finding and write an explicit `ChangePreparationSpec` with target binding,
   source operations, output policy, matching, preconditions, invariants and comparison policy.
   Declare retention checks or set `data_retention_not_applicable=true`; omitting both leaves
   verification incomplete.
2. Run `facts prepare-change` with the original report, review inputs, baseline STEP and spec. Add
   `--before-manifest` for source-backed operations. Save the returned `ChangeRequest` and
   `ChangePlan`; neither is an approval or execution record.
3. Obtain explicit approval before running untrusted source. Use the separately installed
   text-to-cad skill in a new workspace and create a new STEP; never overwrite the baseline.
   text-to-cad does not natively consume the request or plan: translate the target binding,
   operations and payload, and re-check preconditions before running.
4. Run `facts verify-change --request change.json --before old.step --after new.step`. Supply plan,
   approval, execution, before/after manifests and origin review when those records exist.
5. Read `verification_status` across output, manifest and record-binding checks, and read
   `execution_provenance` separately. Passing checks with `unattested` provenance do not prove the
   approved plan ran. Missing/ambiguous evidence remains incomplete; never fill it with inferred
   success.

The preparer currently derives targets only from `numeric.compare` findings. Both change commands
are offline and read-only with respect to CAD artifacts; neither invokes the external executor.
The public `examples/change-loop/README.md` gives an exact offline replay of a real
`passed / attested / changed` test-harness run. Its `--replay-relocated-output` flag is only for
archived output relocation: it checks the same filename, discloses that the recorded absolute
directory was not revalidated, and never rewrites the bound records. Do not use it to bypass a live
output-path failure. See [Change verification](references/change-verification.md) for all flags and
status semantics.

## Honest limits

- STEP measurements implemented: volume, surface area, and axis-aligned bounding-box extents. Minimum
  distance is not wall thickness; no wall-thickness or feature-recognition fact exists.
- Verified STEP length units are mm, cm, and inch. Drawing facts support mm, cm, m, inch and foot
  declarations. Other or unitless declarations produce partial snapshots and `UNKNOWN_UNIT` gaps for
  numeric length/area facts; declared drawing text/layer facts can still be present.
- Drawing measurements are limited to LINE, ARC, CIRCLE and LWPOLYLINE cases; bulges use exact arc
  formulas. Other curve, hatch, dimension and table measurements are not implemented. XREF content
  requires explicit roots and linked/flattened mode. Drawing BOM is limited to explicitly configured
  attribute blocks, not ACAD_TABLE or inferred title blocks. SVG is review rendering, and DWG
  conversion evidence does not prove visual or semantic equivalence.
- The default STEP read scope is `single_part`. Assembly usage records make that snapshot partial
  with `ASSEMBLY_STRUCTURE_NOT_REPRESENTED`; its flattened solids are not an assembly tree.
  `--read-scope assembly` and `facts bom` preserve XCAF occurrence structure, but reconciliation
  mismatches, unresolved references or unknown states still prevent complete BOM claims.
- Semantic PMI covers only the XCAF GD&T projection: dimensions, geometric tolerances and datums,
  with file-level unit contexts. Surface texture/finish, datum targets, datum systems, graphical
  annotation recognition, signed deviations and per-dimension mixed-unit contexts are unsupported or
  explicit gaps. `complete=true` is not AP242 conformance. PMI is not projected into process-input or
  review rules.
- Entity IDs such as `solid:0` and `occurrence:0` are snapshot-scoped. Face IDs are not assumed stable
  across parsers, platforms or revisions. Target resolution is not cross-revision EntityMatch.
- STEP target selectors cover declared occurrence/definition names, aliases, paths, IDs, root/kind/
  state and bounded world-bbox spatial relations. Door/window names are candidates only; conservative
  cylindrical through-holes are validated within explicit limits; general feature coverage is unknown.
  Orientation is an assumed bbox heuristic, not declared/functional-front recognition. Face/edge
  selectors and general feature recognition remain unimplemented. Ambiguity is not permission to guess.
- STEP SVG requires one active occurrence and a ViewSpecification, and writes a new-only manifest.
  Camera presets are global coordinates, not design semantics. PNG, section/exploded/photorealistic
  output and VLM inference are unimplemented; images never supply exact dimensions.
- Analytic OCCT-generated fixtures establish numerical repeatability, not CAD-exporter
  interoperability. Treat results as evidence for the declared scope, not as universal validity.

## References

- [Evidence-guided questions](references/question-answering.md): question routing, occurrence disambiguation, incomplete evidence and source/view boundaries.
- [Facts and gaps](references/facts-and-gaps.md): artifact, snapshot, fact and gap semantics.
- [Semantic PMI](references/pmi.md): declared AP242 dimensions, tolerances, datums, units, links, gaps and limits.
- [DWG and DXF drawings](references/drawings.md): drawing profile, ODA boundary, units and supported 2D facts.
- [Review contract](references/review-contract.md): rules, checkers, findings, completeness and coverage.
- [CLI](references/cli.md): commands, JSON inputs, exit codes and error shapes.
- [Change verification](references/change-verification.md): implemented preparation and verification commands, external execution and provenance limits.
- [BOM extraction](references/bom.md): assembly structure, quantity states, missing inputs and reconciliation.
- [ProcessCardInput](references/process-input.md): implemented single-solid profile, explicit context and unsupported design inputs.
