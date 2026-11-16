# Review contract

A review is deterministic: the same immutable inputs produce the same report content. The CLI
builds content hashes for requirements, the requirement bundle, the ruleset, scope, context, review
run, findings and the report.

## Inputs

The `facts review` command requires four explicit JSON files. No file implies a default rule set or
an all-entities scope.

### RequirementBundle

A non-empty list of requirements. Each requirement has `requirement_id`, `text`, `source_ref`, an
optional `source_sha256` binding externally stored requirement bytes, and a content hash computed
by the CLI over all of those fields. Duplicate requirement IDs, or a rule referencing a requirement
that is not in the bundle, are configuration errors.

The bundle records what is being reviewed. It does not automatically become executable rules.

### RuleSet

A versioned set of declarative rules. Each rule has:

- `rule_id`, `version`, `requirement_refs`, `severity`, `source`.
- Optional `review_type`: `file_health`, `requirement_compliance` or `design_process_rule`.
- `subject_selector.entity_kind`, for example `solid` or `snapshot` for STEP, or `line`, `text`,
  `insert` and `lwpolyline` for drawings.
- `inputs`: `name`, `predicate`, and `required` (default `true`).
- `applicability`: optional `{"fact_predicate": ..., "equals": ...}`.
- `checker` and `parameters`.

Duplicate `(rule_id, version)` pairs are rejected. Several versions of one `rule_id` may coexist;
the scope must then name the version explicitly, because an unversioned reference is ambiguous.

When any selected rule is typed, findings receive a type and the report includes a sorted
`review_type_summary` with four-state counts per type. An untyped finding in such a run is classified
as `requirement_compliance`. A wholly legacy run leaves finding types and the summary null in JSON;
optional nulls are omitted from structured hashes, so legacy content identities remain unchanged.
The shipped `rule-packs/step-file-health/` pack has explicit source, reviewer, applicability and
validation metadata. It checks readiness only and is not a generic engineering/manufacturing
standard. Design-process rules need an identified source and validation on their intended corpus.

### ReviewScope

- `included_rules`: rules actually selected, each as a rule ID string or
  `{"rule_id": "...", "version": "..."}`. A string selects the only available version; it is a
  configuration error if that rule has multiple versions. Every reference must resolve to a rule in
  the RuleSet, and the same version cannot be listed twice.
- `subject_selectors`: entity kinds that define candidate scope.
- `required_inputs`: additional fact requests that must be resolved for completeness, whether or not
  a rule mentions them. A fact, or a proved `ABSENT` gap, resolves the input. `UNSUPPORTED`,
  `UNKNOWN_UNIT`, `PARSE_FAILED`, `MEASUREMENT_FAILED` and `NOT_COMPUTED` gaps are unresolved and
  block completeness.
  `subject_id: "*"` expands only to entity kinds in `subject_selectors`.
- `discovery_requirements`: entity kinds that must have been discovered. An unmet kind produces
  `DISCOVERY_REQUIREMENT_UNMET` and prevents completeness.

The scope never gains candidates from similarity or undeclared entities.

### ReviewContext

Explicit values independent of the file. The CLI hashes the supplied content; it does not apply
hidden defaults.

### Canonical content identities

Semantically unordered collections are sorted before hashing: requirements by ID, rules by
`(rule_id, version)`, rule requirement references, scope rule references/selectors/required
inputs/discovery requirements, and FactSet facts/gaps/query requests. Reordering any of these does
not change a report identity.

Before evaluating, the reviewer recomputes and verifies `snapshot_content_hash`, each requirement
`content_hash`, `bundle_id`, `ruleset_id`, `scope_id`, `context_id`, each `fact_id`, and
`factset_id`. A mismatch means the supplied object does not match its declared identity; it is a
configuration error (CLI exit 2), not a finding. The CLI computes all of these IDs for callers.

## Checkers

| Checker | Inputs | Parameters | Behavior |
| --- | --- | --- | --- |
| `snapshot.status` | none | `equals`: `ready`, `partial` or `failed` | `satisfied` when the snapshot status equals the parameter, otherwise `violated`. This keeps file-health review working when parsing yields no facts. |
| `fact.present` | one or more | none | A required `ABSENT` input is `violated`. Another missing required input is `unknown`. A missing optional input is `unknown` (`OPTIONAL_INPUT_MISSING`) because v0.1 has no audited default semantics. All required inputs present and no missing optional input is `satisfied`. |
| `numeric.compare` | exactly one | `operator` (`<=`, `>=`, `<`, `>`), numeric `threshold`, `unit`, numeric `abs_tol` | `unknown` with `UNIT_MISMATCH` if the fact unit differs. `<=` accepts `value <= threshold + abs_tol`; `>=` accepts `value >= threshold - abs_tol`; strict operators compare exactly. |
| `count.compare` | exactly one | integer `threshold`, `operator` (`==`, `<=`, `>=`, `<`, `>`) | Requires a dimensionless integer fact. A non-integer value is a checker failure. |
| `declared.value` | exactly one | `equals` | `satisfied` only when the value equals the declaration exactly. |

All rule shapes and parameters are validated before any entity is evaluated. Missing or invalid
parameters are configuration errors, not findings. A checker that raises on malformed data becomes
an `unknown` finding with `reason_code=CHECKER_FAILED`, sets `tool_error=true`, and makes the report
incomplete; it never becomes satisfied.

Missing rule inputs produce `NOT_COMPUTED` gaps in the finding and the report. A required scope input
with neither a fact nor any gap also gets a `NOT_COMPUTED` gap. An existing non-`ABSENT` gap for a
scope-required input is unresolved: it adds a `SCOPE_INPUT_UNRESOLVED` review diagnostic, blocks
completeness and keeps the candidate from counting as fully inspected. A proved `ABSENT` gap is a
resolved absence.

## Findings

Each rule × candidate subject yields one finding:

- `satisfied`: evaluated and met.
- `violated`: evaluated and not met; still a complete evaluation.
- `unknown`: the required data, unit, applicability or checker result is unavailable.
- `not_applicable`: the applicability predicate evaluated false.

Applicability false is `not_applicable`; applicability data missing is `unknown` with
`APPLICABILITY_UNKNOWN`. A candidate whose every evaluation is not applicable has
`inspection_not_required=true` and is excluded from the entity-coverage denominator. If the whole
scope is not applicable, the report is not compliant: `rule_total` is zero, so `complete=false` and
the overall status is `incomplete`.

## Coverage

Coverage counts rule × candidate evaluations, not merely rule definitions:

- `rule_covered = satisfied + violated`.
- `rule_total = satisfied + violated + unknown`; not-applicable evaluations are reported separately.
- `rule_coverage = rule_covered / rule_total`, or `null` when the denominator is zero.
- `decision_required_entities` includes every candidate that is not wholly not-applicable,
  including candidates with unknown applicability.
- `fully_inspected` requires at least one applicable evaluation, all applicable evaluations
  satisfied or violated, and no unresolved required input for that candidate.
- With complete discovery, `entity_coverage = fully_inspected / decision_required_entities`.
- With partial or unknown discovery, `entity_coverage` is `null`; the report may provide
  `discovered_only_inspection_ratio` instead. Never present that ratio as total coverage.

## Completeness and overall status

`complete=true` requires all of:

- snapshot `status=ready`;
- `entity_discovery=complete`;
- no unresolved diagnostic with non-`none` impact or discovery impact;
- no unresolved scope-required input gap (a fact or proved `ABSENT` gap resolves it);
- `tool_error=false`;
- zero unknown rule evaluations and at least one evaluation requiring a decision;
- every decision-required candidate fully inspected (not-applicable candidates excluded);
- at least one candidate inspection.

Overall status:

- `non_compliant`: at least one violated finding. The rest of the review may still be incomplete.
- `incomplete`: no violation, but completeness failed. This includes unknown applicability, unknown
  findings, partial/unknown discovery, open diagnostics, checker failure and empty scope.
- `compliant_for_scope`: every applicable evaluation satisfied and completeness holds.

`compliant_for_scope` is scoped evidence, not file certification. An empty requirement bundle, a
reference to an unknown rule/requirement, a rule with invalid checker parameters, or a duplicate
`(rule_id, version)` pair is rejected before a report is produced (CLI exit 2).

## Diagnostics

Diagnostics are preserved from the snapshot, the FactSet and the review. Their `impact` and
`discovery_impact` decide whether they block completeness. A diagnostic with `disposition=resolved`
is ignored for completeness; accepting a diagnostic does not turn partial or unknown discovery into
complete discovery.

Review diagnostics include:

- `EMPTY_SCOPE`: an in-scope entity rule found no candidate subjects. It is not not-applicable and
  cannot produce compliant status.
- `DISCOVERY_REQUIREMENT_UNMET`: a scope-required entity kind was not discovered.
- `SCOPE_INPUT_UNRESOLVED`: a scope-required input has a non-`ABSENT` FactGap. It blocks
  completeness and is not silently converted into a fact.
- `ASSEMBLY_STRUCTURE_NOT_REPRESENTED` comes from the single-part read scope: the STEP model contains
  assembly usage occurrences, but only flattened solids are enumerated. It sets
  `entity_discovery=partial` and blocks complete coverage. Use `--read-scope assembly` to preserve
  XCAF structure; any reconciliation or structural diagnostic still blocks completeness.
- `NO_SOLIDS` and `ROOTS_PARTIAL` come from the STEP adapter and describe discovery limits.
- `ADAPTER_UNAVAILABLE`, `CONVERSION_FAILED`, `DRAWING_AUDIT_ERROR`, `DRAWING_AUDIT_FIX`,
  `DRAWING_EXTERNAL_REFERENCE`, `NO_DRAWING_ENTITIES` and drawing `UNIT_UNKNOWN` come from the
  drawing read/conversion path. Their declared impact and discovery fields participate in the same
  completeness rules; see [DWG and DXF drawings](drawings.md).
