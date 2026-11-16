# CLI

The installed entry point is `facts`. In the repository, prefix commands with `uv run`. All output
is UTF-8 JSON on stdout; OCCT messenger output is suppressed so it cannot corrupt the JSON stream.
The CLI reconfigures stdout to UTF-8 so Windows console code pages do not leak into machine output.

## doctor

```bash
facts doctor --check
facts doctor --check --oda-path "/explicit/path/to/ODAFileConverter"
```

Returns machine-readable runtime, package, dependency-import, temporary-directory and CLI-on-PATH
checks. Required environment failures produce `status=failed`, `ok=false` and exit 1; a usable
environment returns `ready` and exit 0 even when optional ODA is `not_checked`. Without
`--oda-path`, no ODA install location or PATH is searched. With it, only that file's existence and
SHA-256 are checked; doctor does not execute the converter or prove DWG conversion works. A supplied
invalid ODA path is a failed required check. Use the repository's `docs/recovery.md` playbook for
safe next actions.

## inspect

```bash
uv run facts inspect part.step
uv run facts inspect multi-solid.step --limit 5
```

`--limit` defaults to 20 entities and bounds fact selection for STEP solids or drawing entities.
`--read-scope single_part|assembly|drawing` selects flattened STEP discovery, XCAF assembly structure,
or the drawing profile; the default is inferred from the registered format (`single_part` for STEP,
`drawing` for DWG/DXF). STEP inspection measures volume, area and the three bounding-box extents.
DXF inspection uses ezdxf for drawing structure and selected declared/2D numeric facts. DWG first
requires a separately installed ODA File Converter; its executable path must be supplied with
`--oda-path`, because no install location is discovered automatically.
See [DWG and DXF drawings](drawings.md). The command does not dump shapes, faces or mesh triangles.

Output top-level keys:

- `artifact`: raw-byte `sha256`, `size_bytes`, `format`, `source_locator`.
- `snapshot`: provenance, units, status, entity discovery, entities and diagnostics.
- `factset`: facts, gaps, extraction query and extractor version.
- `selection`: `entity_total`, `entities_returned`, `truncated`, and `next_cursor` (the next entity
  ID when truncated, otherwise `null`).

A malformed file is still an inspection result: the process exits 0, `snapshot.status` is `failed`,
`entity_discovery` is `unknown`, and a `PARSE_FAILED` diagnostic is present. Inspect the snapshot
before using any fact.

`--summary` replaces the full snapshot/FactSet with metadata, diagnostics and drawing counts; it does
not return `snapshot.entities`. Normal inspection retains the full catalog even when `--limit` bounds
fact selection.

Entity order is the adapter's stable discovery order (`solid:0`, `solid:1`, ...). To page, rerun with
a larger limit; `next_cursor` identifies the first entity not returned.

## query

```bash
uv run facts query drawing.dxf --kind line --layer Geometry --container Model --limit 20
uv run facts query drawing.dxf --kind line --cursor drawing:20 --limit 20
```

Drawing-only selective query returns a compact snapshot summary plus only selected EntityRefs and
their default facts. Repeat `--kind`, `--layer` or `--container` for OR values within a field;
different fields are ANDed. `--text` is a case-sensitive TEXT/MTEXT/ATTRIB/ATTDEF substring. `--limit`
defaults to 20 and must be positive. `next_cursor` is a snapshot-local catalog cursor; keep filters
unchanged across pages.
Output selection includes `matched_total`, `remaining_total`, `entities_returned`, `truncated` and
`next_cursor`. Query limits output and fact extraction, not initial parsing cost.

## resolve

```bash
uv run facts resolve assembly.step --selector examples/resolve-door.json
uv run facts resolve assembly.step --selector examples/resolve-root.json
```

STEP-only occurrence resolution using the assembly profile. The JSON `TargetSelector` requires at
least one constraint and ANDs all supplied fields: `occurrence_id`, `path`, `name`, `name_contains`,
`name_contains_any`, `definition_id`, `is_assembly`, `is_root`, `state`, and `spatial`. Name matching
inspects both occurrence and part-definition names; exact `name` is case-sensitive and substring/alias
matching uses Unicode casefolding. Candidate paths join snapshot-scoped occurrence IDs, while
`name_path` is display-only. Spatial relations use an explicit camera and unique reference, compare
world-bbox centers, or use world-bbox gap for `near` with `max_distance_mm`. A lone `{"is_root": true}`
spatial reference means the union of root boxes (`assembly:root`), not an arbitrary root occurrence.

The response contains `artifact`, compact `snapshot` metadata and `resolution`. Status is `resolved`
for exactly one discovered candidate, `ambiguous` for multiple, `unresolved` for none and `failed` for
a failed snapshot. These are normal JSON results with exit 0; an invalid selector or non-STEP input
exits 2. No candidate is chosen by traversal order. `complete` means complete discovery plus a
measurable placed bounding box for every returned candidate, not full shape validation, successful or
globally unique resolution, or a diagnostic-free guarantee. Candidate world-placed bounding
boxes are system millimetres. IDs are snapshot-scoped, not persistent identity or source-code
locations. See the repository's `docs/model-views.md` for the full contract.

## features, orient and ask

```bash
uv run facts features examples/question-assembly.step --query examples/features-doors-windows-holes.json
uv run facts orient examples/question-assembly.step --selector examples/resolve-left-door.json
uv run facts ask model.step --question "where is the left door?"
uv run facts ask model.step --spec examples/question-door-candidates.json
uv run facts ask drawing.dxf --spec examples/drawing-question.json
```

`features` and `orient` are STEP assembly-profile commands. `features` returns unvalidated door/window
name candidates and conservative validated full cylindrical through-holes with radius/length/axis/area
geometry. Blind, counterbored, rectangular and other holes remain unsupported;
`general_feature_coverage=unknown` even when bounded execution is complete.

`orient` returns six world-bbox projection candidates. A unique largest-area axis pointing outward
from the assembly center produces an assumed ViewSpecification; tied axes or near-zero outward offset
return `ambiguous`. It never proves source-declared or functional front.

`ask` requires exactly one of `--spec` and `--question`. For STEP, `--question` is a bounded offline
Chinese/English grammar, not general NLP. Both produce an AnswerReport with original text,
interpretation basis, explicit interpretations, assumptions, evidence, counts/geometry and gaps.
Strict feature counts retain unknown general coverage; `candidates_allowed` reports candidate states,
not validated engineering quantities. Unsupported wording is a normal unsupported report with exit 0;
malformed input exits 2. See `docs/model-questions.md` for the full contract.

For DWG/DXF, `ask` accepts only an explicit `DrawingQuestionSpec` through `--spec`; drawing
`--question` exits 2 because no drawing grammar is implemented. The drawing profile covers entity
count/lookup, display text, layer/block inventories, supported 2D measurements, declared dimensions,
unvalidated name candidates, a declared semantic-evidence bundle with attached ATTRIB context and
explicit attribute BOMs. Set `containers` and `layer_state_policy` deliberately; raw entity counts,
name candidates and semantic evidence are not engineering totals or inferred fields. See
[Drawing questions](drawings.md#drawing-questions).

## render

Drawing SVG:

```bash
uv run facts render drawing.dxf --output drawing.svg --layout Model
```

Target-isolated STEP SVG and manifest:

```bash
uv run facts resolve assembly.step --selector examples/resolve-door.json
uv run facts render assembly.step --target occurrence:12 \
  --view-spec examples/view-front.json --output door-front.svg
```

Drawing rendering writes one new SVG and returns its artifact/snapshot binding, output hash and size.
Existing outputs are rejected rather than overwritten. External raster images are ignored so rendering
cannot trigger implicit external image reads; an empty result still produces an SVG. Use `--oda-path`
for DWG and the XREF options below when needed. Drawing inputs reject `--target` and `--view-spec`.

STEP rendering requires both flags, accepts only `.svg`, and creates `door-front.svg` plus
`door-front.view.json`. Both are exclusive new files; if either already exists, no pair is written.
The target must be one active `occurrence:N` in a readable assembly-profile snapshot. Only that
occurrence's placed shape is projected. The ViewSpecification requires either a global camera preset
(`front`, `back`, `left`, `right`, `top`, `bottom`, `iso`) or explicit finite, nonzero, non-parallel
`normal`/`right` vectors. Optional display/image fields control hidden lines, pixel width/height,
padding, curve deflection and the total point budget.

Resolve and render independently register and re-read the STEP file; render does not require or verify
a prior resolution ID. Before relying on the prior selection, compare resolve's `artifact.sha256` and
`snapshot.snapshot_id` with render's `artifact.sha256` and `snapshot_id`. On mismatch, resolve again.

The manifest binds artifact/snapshot/target identities, complete view, OCCT renderer and method,
projected extents, visible/hidden/skipped edge counts, SVG hash/size and diagnostics. Projected extents
are system-millimetre spans of the emitted, discretized visible plus requested-hidden point set before
SVG page scaling; they are not exact source dimensions, especially with curve approximation or skipped
edges. `front` is the global -Y viewer direction, not automatic design-front recognition. `semantic_intent.basis` can only
be `user_selected` or `assumed`; no source-declared basis is implemented. STEP and drawing SVGs are
review/documentation WorkProducts, not visual/geometric fidelity proof or dimensional evidence.
PNG, photorealistic output and VLM interpretation are not implemented.

## drawing-bom

```bash
uv run facts drawing-bom drawing.dxf --part-tag PART --material-tag MATERIAL --require-tag MATERIAL
uv run facts drawing-bom drawing.dxf --part-tag PART --quantity-tag QTY
```

Extracts neutral BOM rows from explicitly configured INSERT/MINSERT attributes, separately from STEP
`bom`. Default container is `Model`; repeat `--container` for others. Optional description/material
tags retain declarations and `--require-tag` makes a tag mandatory. Without a quantity tag, counts
include MINSERT multiplicity. With one, invalid or missing canonical positive integers produce
`quantity=null` and `quantity_state=unknown`. Read `complete`, `missing_inputs`, property conflicts
and discovery before using quantities. XREF attachment INSERTs are not part occurrences. Uncounted
external references block completeness unless `--allow-xref-exclusion` explicitly accepts their
exclusion from the selected BOM scope; the acceptance is recorded and is not a claim they were counted.
No ACAD_TABLE or title-block semantics are inferred.

## Drawing XREF options

`inspect`, `query`, `render`, `review` and `drawing-bom` accept `--xref-mode unresolved|linked|flatten`
and repeatable `--xref-root`. Default is unresolved. Linked records independent child artifacts;
flatten embeds block content while preserving each child source hash/unit. Resolution requires at
least one allowed local root and rejects outside-root, UNC/URL/network paths and cycles. Safety flags:
`--xref-max-depth`, `--xref-max-files`, `--xref-max-bytes`, `--xref-timeout-seconds`. See
[DWG and DXF drawings](drawings.md).

## review

```bash
uv run facts review part.step \
  --requirements requirements.json \
  --rules rules.json \
  --scope scope.json \
  --context context.json
```

All four flags are required. The CLI registers the artifact, reads a snapshot, extracts every rule
input plus every scope-required input, constructs the bound `ReviewRequest`, and prints one
`ReviewReport` JSON object.

- Requirements file shape: `{"requirements": [...]}`.
- Rules file shape: `{"version": "...", "rules": [...]}`.
- Scope file shape: `{"included_rules": [...], "subject_selectors": [...], "required_inputs": [...],
  "discovery_requirements": [...]}`. An `included_rules` entry is either a rule ID string or
  `{"rule_id": "...", "version": "..."}`; use the object form when the RuleSet has several versions
  of that rule.
- Context file shape: `{"values": {...}}`.

The CLI computes content hashes for requirements, rules, scope and context; callers do not supply
them. Review verifies these identities before evaluating. `review` and `prepare-change` also accept
`--read-scope single_part|assembly|drawing`; `verify-change` always uses the profile fixed by its
request. Drawing-facing commands accept `--oda-path` for DWG. Drawing rules select entity kinds such
as `line`, `text`, `insert` or `lwpolyline`; see [DWG and DXF drawings](drawings.md).

## prepare-change

```bash
uv run facts prepare-change \
  --report review.json --finding finding-1 --before old.step \
  --requirements requirements.json --rules rules.json \
  --scope scope.json --context context.json \
  --spec prepare-spec.json --before-manifest old-manifest.json
```

This derives a `ChangePreparation` containing an immutable `ChangeRequest` and external-executor
`ChangePlan`; it does not execute CAD or scripts. The finding must be `violated` or `unknown`, and
current target derivation supports `numeric.compare` only. The spec declares executor, target
binding, source operations, payload, output policy, matching, preconditions, invariants, data
retention and comparison policy. `--before-manifest` is required for source operations and is
validated against actual bytes relative to the manifest file's directory. See
[Change verification](change-verification.md) for the contract and limits.

## verify-change

```bash
uv run facts verify-change --request change.json --before old.step --after new.step
uv run facts verify-change --request change.json --plan plan.json \
  --approval approval.json --execution execution.json \
  --before-manifest old-manifest.json --after-manifest new-manifest.json \
  --origin-review review.json --before old.step --after new.step
```

The command re-parses both artifacts under the request's fixed profile and prints a
`ModificationReport`. Plan, approval, execution, manifests and origin review are optional inputs,
but their absence limits the corresponding provenance/review result. Output verification can pass
while `execution_provenance=unattested`. Neither form executes CAD.

For archived evidence moved away from a recorded absolute output directory,
`--replay-relocated-output` explicitly accepts only the same output filename at `--after`. The
report discloses that the recorded directory was not revalidated. Default verification remains
strict, and a different filename still fails. Never use this replay option to waive a live change's
output-location mismatch. The complete public example and expected statuses are in
`examples/change-loop/README.md`.

A nonexistent after artifact produces a report with missing after references. It is typically
incomplete, and failed when a baseline identity, precondition or supplied approval/execution check
fails. Other failed/incomplete verification results normally exit 0; malformed
request/configuration input exits 2, and `tool_error=true` or an unexpected internal failure exits 3.

## bom

```bash
uv run facts bom assembly.step
uv run facts bom assembly.step --require-property name
```

The command always reads with `read_scope=assembly` and prints a neutral `BOMExtract`. Quantities
are `known`, `observed`, or `unknown`; observed counts under incomplete/reconciliation-mismatched
structure are not complete quantities. `coverage` separately totals all three states, and the three
totals sum to the leaf definition count. See [BOM extraction](bom.md) for states, missing inputs and
diagnostics. An incomplete BOM is still a normal result and exits 0.

## pmi

```bash
uv run facts pmi part.step
uv run facts pmi assembly.step --read-scope assembly
```

Extracts declared AP242 semantic PMI without inferring annotations. The output contains `artifact`, a
summarized `snapshot`, and `pmi` (`PmiExtract`). `--read-scope single_part|assembly` controls the
snapshot used to bind links; the default is `single_part`. Drawings and non-STEP inputs are rejected
as configuration errors. Read `status`, `complete`, `coverage`, `gaps`, `diagnostics`, `units` and
annotation `link_status` before using a value. A file without semantic PMI returns `status=ready`,
`complete=true`, and empty annotations/gaps. A fatal read result is still JSON and exits 0; invalid
command input exits 2. See [Semantic PMI](pmi.md).

## process-input

```bash
facts process-input examples/box.step --context examples/machining-context.json
facts process-input part.step --require-context material
facts process-input part.step --require-design-input semantic_pmi
```

Implemented only for the constrained STEP single-solid profile. It emits ProcessCardInput with five
existing geometry facts, explicit user-supplied context, missing inputs, coverage and provenance.
Zero/multiple solids and required missing inputs prevent completeness. Declared material and validated
features are unsupported gaps, not inferred values. Semantic PMI can be extracted separately with
`facts pmi` but is not projected here, so requiring `semantic_pmi` keeps the result incomplete.
Manufacturing-planning context is rejected. See [ProcessCardInput](process-input.md) for the full
contract.

## Exit codes

| Exit | Meaning | Output |
| --- | --- | --- |
| 0 | A report, inspection or successful doctor check was produced. | Result JSON. `non_compliant` and `incomplete` reports still exit 0. |
| 1 | `doctor --check` found a failed required environment check. | Doctor JSON with `status=failed` and `ok=false`. |
| 2 | Configuration or input error; no report exists. | `{"error": {"category": "configuration_or_input", "message": "..."}}` |
| 3 | Internal failure, or a review report with `tool_error=true`. | Error JSON, or the review report. |

Configuration errors include missing arguments, unknown JSON keys, malformed JSON, missing required
keys, empty requirements, unknown requirement/rule references, ambiguous or unknown rule versions,
duplicate `(rule_id, version)` pairs, content-ID mismatches, invalid checker parameters and
unsupported parse options. Do not retry these as if they were transient.

When a report is produced, `facts review` exits 3 only if that report carries `tool_error=true` (a
checker raised). An unexpected internal exception also exits 3, with an error object and no report.
A violated finding is a normal completed review and exits 0.

## Paths and environment

- `uv sync` installs the locked Python 3.13 environment and dependencies.
- `uv run pytest` runs the test suite; `uv run pytest tests/test_review_numeric.py` runs one module.
- The CLI accepts JSON, not YAML.
- The core is offline; no command calls a network service or an LLM.
- The source file is opened read-only; register, read and review do not write to it.
