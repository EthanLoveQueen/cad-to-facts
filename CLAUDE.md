# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository status

The repository contains P1 STEP vertical slices, a first DWG/DXF drawing-analysis slice, a bounded AP242 semantic-PMI slice, a P2 change-preparation/output-verification slice with deterministic manifest/approval/execution record builders, a P3 assembly-structure/model-BOM slice, and a constrained P4 single-solid ProcessCardInput slice, plus design documents. A maintainer-only product plan (not published) remains the internal product/architecture source of truth, `docs/detailed-design.md` defines full behavioral contracts, and `GLOSSARY.md` fixes domain terminology. Implemented code is under `src/cad_to_facts/`, with public-interface tests under `tests/` and runnable JSON examples under `examples/`. `inspect`, `query`, `resolve`, `features`, `orient`, `ask`, `render`, `review`, `drawing-bom`, `prepare-change`, `verify-change`, `bom`, `pmi`, `process-input`, and `doctor` currently exist as CLI commands. `pmi` re-reads STEP with XCAF GD&T transfer and reports declared dimensions, geometric tolerances and datums with values, units, datum references, snapshot-scoped geometry links, raw inventory, coverage and explicit gaps; it does not infer annotations, recover signed tolerance deviations from magnitude-only reader values, handle surface texture/datum targets/datum systems, or claim full AP242 conformance. `process-input` requires exactly one discovered solid and currently projects only volume/area/bbox facts plus explicit user context; declared material, PMI projection and validated features remain unsupported gaps. Neither change command executes CAD or source scripts. `read_scope=single_part` detects `NEXT_ASSEMBLY_USAGE_OCCURRENCE` records and reports `ASSEMBLY_STRUCTURE_NOT_REPRESENTED` with partial discovery; `read_scope=assembly` uses XCAF to preserve definitions, occurrence paths and local transformations. BOM quantities and coverage distinguish `known`, `observed`, and `unknown`; PRODUCT/NAUO versus XCAF reconciliation mismatches prevent completeness. `src/cad_to_facts/matching.py` is an internal entity-matching module used by `verify_change`; it has no standalone CLI surface and a match is not persistent identity or execution proof. `resolve` returns unique, ambiguous, unresolved or failed occurrence candidates from explicit name/alias/path/definition/root/state and bounded spatial constraints, with nested world-coordinate bounding boxes; it never chooses the first ambiguous match. `features` separates unvalidated door/window name candidates from conservative validated cylindrical through-holes and keeps general coverage unknown. `orient` returns six bbox-projection candidates and only an assumed heuristic front. `ask` executes explicit STEP QuestionSpec interpretations or a bounded offline Chinese/English grammar and preserves assumptions, count states, evidence and gaps; for DWG/DXF it dispatches to a sibling DrawingQuestionSpec profile covering entity/text/layer/block/measurement/dimension/name-candidate/semantic-evidence/attribute-BOM intents, never reusing STEP occurrence or feature semantics. STEP `render` requires an exact active occurrence and ViewSpecification, uses OCCT hidden-line projection, and writes new-only SVG plus `.view.json` evidence. Camera `front` is a global-axis preset, not semantic front recognition. Neither resolver nor render provides general feature recognition, persistent identity or editable-source location. Do not describe planned capabilities as operational.

The repository is also a Claude Code plugin: `.claude-plugin/plugin.json` and `marketplace.json` point at `skills/`. `skills/cad-to-facts/` covers facts, evidence-guided questions, review and change/BOM workflows; `skills/cad-view/` covers deterministic target-isolated STEP SVG views. Each contains `SKILL.md`, one-level `references/` where needed, and its own license. Keep skill claims synchronized with the implemented CLI; design-only commands must stay labeled as such. A future `cad-visual` VLM workflow is not implemented or enabled.

Drawing reads use a separate `ModelSnapshot.drawing` profile. DXF is parsed directly with ezdxf recovery/audit; DWG requires a separately installed ODA File Converter whose executable path the user must supply explicitly (`--oda-path`/`oda_executable`; the adapter never searches PATH or install locations) and records derived-DXF conversion evidence. ODA is proprietary, is not bundled or auto-installed, and its non-member use is restricted by ODA's license. Without an explicit path, DWG returns `ADAPTER_UNAVAILABLE`. Drawing facts cover declared entity/layer/container/text/block-name values and selected 2D measurements, including exact LWPOLYLINE bulge geometry; unitless values must remain gaps rather than guesses. XREFs default to unresolved; `linked` keeps independent artifact evidence and `flatten` preserves each child artifact hash/unit, only beneath explicit roots with resource budgets. `query`/`inspect --summary` provide selective output, `render` writes new-only review SVG, and `drawing-bom` uses explicit attribute tags without title-block inference. `facts ask drawing.dxf --spec ...` executes bounded drawing questions over entities, text, layers, blocks, supported 2D measurements, declared dimension values, unvalidated name candidates, a declared semantic-evidence bundle and explicit attribute BOMs; semantic evidence can include attached ATTRIB context but is not an inferred material/part/function field. It does not implement drawing natural-language grammar, general drawing semantics, title-block inference, INSERT geometry expansion or dimension-to-geometry association. Change and assembly BOM workflows remain STEP-focused.

## Commands

```bash
uv sync                 # install the locked Python 3.13 reference environment and dependencies
uv run pytest           # run all tests
uv run pytest tests/test_review_numeric.py  # run one test module
uv run facts inspect part.step
uv run facts inspect drawing.dxf
uv run facts inspect drawing.dxf --summary
uv run facts query drawing.dxf --kind line --layer Geometry --limit 20
uv run facts render drawing.dxf --output drawing.svg
uv run facts resolve assembly.step --selector examples/resolve-door.json
uv run facts features assembly.step --query examples/features-doors-windows-holes.json
uv run facts orient assembly.step --selector examples/orient-right-door.json
uv run facts ask assembly.step --question "左侧的门在哪里？"
uv run facts ask assembly.step --spec examples/question-door-candidates.json
uv run facts ask examples/question-drawing.dxf --spec examples/drawing-question.json
uv run facts render assembly.step --target occurrence:0 --view-spec examples/view-front.json --output root-front.svg
uv run facts drawing-bom drawing.dxf --part-tag PART --material-tag MATERIAL
uv run facts inspect drawing.dwg --oda-path "C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe"
uv run facts review part.step --requirements examples/requirements.json --rules examples/rules.json --scope examples/review-scope.json --context examples/review-context.json
uv run facts prepare-change --report review.json --finding finding-1 --before old.step --requirements requirements.json --rules rules.json --scope scope.json --context context.json --spec prepare-spec.json --before-manifest old-manifest.json
uv run facts verify-change --request change.json --before old.step --after new.step
uv run facts verify-change --request change.json --plan plan.json --approval approval.json --execution execution.json --before-manifest old-manifest.json --after-manifest new-manifest.json --origin-review review.json --before old.step --after new.step
uv run facts bom assembly.step --require-property name
uv run facts pmi part.step
uv run facts pmi assembly.step --read-scope assembly
uv run facts process-input examples/box.step --context examples/machining-context.json
uv run facts doctor --check
uv tool install --python 3.13 .  # install the facts CLI on PATH in an isolated tool environment
claude --plugin-dir .   # load this repository as a local Claude Code plugin for one session
claude plugin validate .claude-plugin/marketplace.json  # validate plugin packaging
```

The CLI currently accepts JSON configuration, not YAML. Tests use analytic OCCT-generated STEP fixtures and ezdxf-generated DXF fixtures; `tests/pmi_helpers.py` writes AP242 semantic-PMI fixtures through OCCT XCAF for unit, tolerance, datum and gap regressions. Self-written/self-read fixtures do not establish exporter interoperability. `uv build` must keep `test-data/` and `tests/` out of the sdist: `test-data/` holds user-supplied production files that are not redistributed, so the `[tool.hatch.build.targets.sdist]` include list in `pyproject.toml` is deliberate.

## Project goal

Build a local-first agent skill and deterministic engineering core for:

1. Extracting traceable facts from design files.
2. Reviewing files against explicit requirements, design rules, and task context.
3. Preparing changes for text-to-cad and verifying the resulting new files.
4. Preparing neutral downstream data such as model BOM extracts and process-card inputs.

The project is an evidence-driven workflow core, not a new geometry kernel or a universal CAD converter.

## Planned architecture

```text
SourceArtifact (immutable bytes + SHA-256)
  → ModelSnapshot (parser provenance, entities, units, coordinates, diagnostics)
  → FactSet (declared / measured / derived facts + evidence)
  → ReviewReport, ChangeRequest, or downstream WorkProduct
```

Review combines facts and snapshot diagnostics with an immutable `RequirementBundle`, versioned `RuleSet`, explicit `ReviewScope`, and `ReviewContext`, so file-health review still works when parsing yields no facts. Change requests are handed off to the separately installed text-to-cad CAD skill; text-to-cad is not embedded in this project or added to its Python dependencies. A handoff contract translates targets and checks preconditions. Execution requires an `ApprovalRecord` bound to the complete request and plan, creates a new artifact, and is followed by re-parsing, acceptance checks, and another review.

Source-backed changes use before/after `SourceManifest` objects linking editable source, parameters/dependency configuration, and generated artifacts. A hash of the exported STEP alone does not identify the editable source. An `ExecutionRecord` separately attests or observes the actual execution: output validation can pass while execution provenance remains `unattested`, and an external handoff alone never proves the approved plan ran. Before/after checks need a fixed parse/extraction profile, explicit entity-matching methods, and numeric tolerances; unmatched required entities make verification incomplete, never passed. Source scripts are executable, untrusted input and require approval and isolation.

Use a common envelope plus format-specific profiles. Do not flatten STEP B-rep, DXF drawings, IFC semantics, and meshes into one universal `bodies/features` model.

## Non-negotiable design rules

1. **Reuse mature projects:** OCCT performs B-rep geometry; mature domain libraries handle meshes and other representations; format libraries perform parsing; text-to-cad performs supported modeling changes. Project-owned code handles contracts, orchestration, rules, evidence, and verification.
2. **Keep domain objects separate:** facts are not findings, LLM/VLM inferences, change requests, or downstream work products.
3. **Preserve provenance:** every result is bound to an artifact hash, parser/method version, units, and relevant source entities.
4. **Represent unknowns honestly:** missing, unsupported, failed, and not-applicable are different states. A Fact exists only when a declared/measured/derived value is present; use `FactGap` for an unavailable or incomplete extraction rather than a null-valued fact. Only a proven `ABSENT` gap can violate a required-presence rule; parse failures and uncomputed inputs stay unknown. Rule coverage counts only satisfied/violated applicable rule evaluations as covered; unknown stays in the denominator and not-applicable is reported separately. Entity coverage counts fully inspected entities over all candidates requiring a decision, including unknown applicability, only when discovery is complete. With partial/unknown discovery, true coverage is unknown and any discovered-only ratio must be labeled as such; never claim 100% coverage or `compliant_for_scope`.
5. **Never overwrite source files:** modification creates a new artifact. Reject stale base hashes and verify both target and invariant constraints afterward.
6. **Do not invent confidence:** unvalidated hole/fillet/pocket recognition remains a candidate or inference, not a fact with an arbitrary probability.
7. **Keep the deterministic core offline:** parsing, measurements, rule evaluation, BOM extraction, and change verification do not require AI or network access.
8. **Prefer selective output:** large models need summaries and selective entity queries rather than dumping every face or mesh triangle to an agent.

## Accuracy constraints

`BRepExtrema_DistShapeShape` computes minimum shape/face distance; it is not automatically a general wall-thickness measurement. `BRepCheck_Analyzer` validity is not sufficient proof of downstream correctness. Face IDs such as `F7` are not assumed stable across parsers, platforms, or revisions.

Validation must include analytic parts, NIST/CAx-IF AP242 PMI models, files from different CAD exporters, unit variants, assemblies, malformed inputs, and end-to-end review/change/BOM tasks. Self-written/self-read STEP files alone do not establish interoperability.

## Reuse and ecosystem

- `cadquery-ocp` / OCCT: initial STEP geometry and assembly foundation.
- `cad-mcp-server`: direct read-only STEP baseline; compare capabilities and tests before duplicating them.
- `cadtokens`: candidate AP242 semantic-PMI path and NIST-based comparison source.
- `text-to-cad`: externally installed CAD skill and modification executor, initially for source-backed/parametric models; never a required Python dependency of this package.
- `ezdxf`: installed DXF drawing parser and recovery/audit foundation.
- ODA File Converter: optional, separately installed proprietary DWG→DXF converter; never bundled, auto-installed or treated as an open-source Python dependency.
- IfcOpenShell and trimesh: later task-driven format adapters, not initial mandatory dependencies.

Do not assume the text-to-cad skill natively consumes this project's `ChangeRequest`; the handoff must translate targets and verify preconditions. Skill invocation alone is not execution provenance: retain an explicit `ExecutionRecord` or report `unattested`.

## External systems are out of scope

Do not add ERP/PLM/PDM/MES/CAPP connectors, enterprise master-data synchronization, process-card template rendering, tool/machine databases, automated operation sequencing, setup planning, machining-parameter selection, approval workflows, or production release to this skill. Downstream outputs are neutral, provenance-rich JSON with explicit `missing_inputs`; external systems and engineers consume them separately.

## Implemented and remaining CLI scope

`resolve` and target-isolated STEP `render` are implemented with the commands above; their behavioral contract is in `docs/model-views.md`. Target resolution uses explicit declared occurrence/definition filters, bounded world-bbox spatial relations and nested world placement, while rendering uses OCCT HLR and writes new-only SVG plus a ViewRenderManifest. `features`, `orient`, and `ask` implement bounded feature candidates/through-hole validation, assumed orientation, and common STEP QuestionSpec/AnswerReport workflows; their contract is in `docs/model-questions.md`. DWG/DXF `ask` uses the drawing-profile `DrawingQuestionSpec` described in `docs/drawing-questions.md`: entity/text/layer/block inventories, supported 2D measurements, declared dimensions, unvalidated name candidates, a declared semantic-evidence bundle and explicit attribute BOMs. Drawing counts keep container and layer-state scope, distinguish known/partial/unknown/candidate, and never turn failed or unitless reads into zero. Semantic evidence is declared block/layer/text/attribute context and is not field inference. Drawing natural-language grammar, general drawing semantic understanding, title-block inference, dimension-to-geometry association and INSERT expansion remain unimplemented. Door/window names remain unvalidated, general feature coverage is unknown, and heuristic front is never source-declared. General NLP/feature recognition, declared or functional front recognition, PNG, photorealistic output and VLM inference remain unimplemented. `pmi`, `prepare-change`, `verify-change`, `bom`, and the constrained single-solid `process-input` profile are implemented with the commands above. Semantic PMI extraction is a separate bounded result; it is not yet projected into `process-input` or review rules, so required process design inputs such as `semantic_pmi` remain explicit `UNSUPPORTED` gaps and prevent process-input completeness. The command never creates operations, setups, tool/machine selections, cutting parameters or a production process plan. `doctor --check` reports installation diagnostics and accepts only an explicit optional `--oda-path`; it never discovers or executes ODA. `examples/change-loop/` contains the recorded real change loop and an offline replay regression.

Implementation order is P0 ecosystem/corpus validation, P1 STEP facts and requirements review, P2 the verified text-to-cad change loop, P3 assemblies and BOM extraction, P4 process-card input preparation, then task-driven format expansion. A first P5 drawing slice is implemented ahead of P4, but does not complete general DXF/DWG engineering analysis. Optional visual inference is isolated from facts and remains disabled unless explicitly enabled and independently validated.
