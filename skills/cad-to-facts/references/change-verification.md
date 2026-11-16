# Change preparation and verification

`facts prepare-change` and `facts verify-change` are implemented for STEP artifacts. They prepare an
immutable external-executor handoff and verify a separately produced new artifact. **Neither command
executes CAD, runs a source script, approves a change, or invokes text-to-cad.** text-to-cad and its
`cad-server` runtime remain separately installed tools, not Python dependencies of this project.

`facts bom` is implemented for assembly-aware STEP snapshots; see [BOM extraction](bom.md).
A constrained single-solid `facts process-input` profile is implemented; see
[ProcessCardInput](process-input.md). It does not perform manufacturing planning.

## Prepare a review-derived change

Start with a real baseline `ReviewReport` and a `violated` or `unknown` finding. The current
preparer derives a target only from a `numeric.compare` finding; it does not infer modeling intent
from other checker types.

```bash
facts prepare-change \
  --report review.json --finding finding-1 --before old.step \
  --requirements requirements.json --rules rules.json \
  --scope scope.json --context context.json \
  --spec prepare-spec.json --before-manifest old-manifest.json
```

`--before-manifest` is optional for a request with no source operations, but required when the spec
contains source operations. Its referenced files are validated relative to the manifest JSON's
directory. The manifest must contain the baseline STEP and match the declared generator. It must
also contain every existing baseline source referenced by a `set_parameter` or `remove_source`
operation; an `add_source` operation names a new source that is not in the baseline manifest.

`prepare-spec.json` is a `ChangePreparationSpec` with:

- `executor` and `target_executor_ref` for the external handoff;
- explicit source `operations`, controlled `payload`, and `output_policy`;
- an entity `matching` profile and numeric tolerances;
- baseline `preconditions`, `invariant_checks`, and optional `data_retention_checks`;
- a `comparison` policy naming required baseline entities, permitted additions/removals, and
  non-target predicates.

Set `output_policy.overwrite_base` to `false` (the only accepted value) and create a new output
artifact. If `comparison.required_baseline_entity_ids` is empty, preparation requires all baseline
entities except explicitly allowed removals. Declare either individual retention checks or
`comparison.data_retention_not_applicable=true`; the latter is valid only when no individual checks
are declared. If neither is supplied, verification reports `DATA_RETENTION_UNDECIDED` and cannot
pass.

The output is a `ChangePreparation` containing a bound `ChangeRequest` and `ChangePlan`. Save these
as separate JSON objects if the next command or an external executor needs them. Preparation checks
the original report against its actual inputs and binds a separate, expanded verification FactSet;
it does not silently replace the original review FactSet.

## Execute outside this project

For a user-approved source-backed edit, copy editable source into a new workspace and invoke the
separately installed text-to-cad skill there. Source scripts are executable, untrusted input: they
require explicit approval and isolation. Never run a script merely because a manifest references it.
The baseline source and STEP must remain unchanged.

A local text-to-cad 0.11.10 smoke test used `cad run model.py` and
`cad model export <id> <new-file>`. Run external modeling from the standalone model workspace, not
this repository root, so it does not inherit this project's `uv.lock`.

text-to-cad does not natively consume this project's `ChangeRequest` or `ChangePlan`. They are
project contracts and handoff records, not an executor payload. Translate `target_executor_ref`, the
source operations and the controlled payload into the executor's native inputs, and re-check the
preconditions against the current source before running. Skill invocation alone does not prove the
approved plan ran.

Execution requires an `ApprovalRecord` bound to the complete current request and plan. An
`ExecutionRecord` separately attests or observes what actually ran. Calling a skill or observing a
new STEP does not create either record and does not prove that the approved plan ran. Do not invent
or backdate these records.

## Verify the new artifact

Output verification does not require approval or execution records:

```bash
facts verify-change --request change.json --before old.step --after new.step
```

For the complete source-backed and review-derived workflow, provide the other records explicitly:

```bash
facts verify-change --request change.json --plan plan.json \
  --approval approval.json --execution execution.json \
  --before-manifest old-manifest.json --after-manifest new-manifest.json \
  --origin-review review.json --before old.step --after new.step
```

The command re-parses and extracts both artifacts using the request's fixed `VerificationProfile`.
It verifies content IDs and baseline freshness, evaluates preconditions, matches required entities,
and checks targets, invariants, non-target changes, data retention, manifests, and both the original
finding and complete original-rule re-review when supplied. The actual after location must match
`output_policy.path`: an absolute policy is compared after path normalization, while a relative
policy must match the actual path's trailing components. Archived evidence replay may explicitly
pass `--replay-relocated-output`: for an absolute recorded policy, this accepts only the same output
filename at a different `--after` directory and records in the output-location check that the old
absolute directory was not revalidated. It does not change any bound record or accept a different
filename. Never use it to bypass a live output mismatch; the public archived example is in
`examples/change-loop/README.md`. Manifest files are checked against actual
bytes relative to each manifest JSON's directory; their scripts are never run. Changed common
source paths must exactly match `modified_from`, and source additions/removals/changes must agree
with a supplied ChangePlan.

A missing `--after` file produces a `ModificationReport` with missing after-artifact references,
rather than pretending the output was checked. It is typically `incomplete`; it is `failed` when a
baseline identity, precondition or supplied approval/execution check fails. A failed or incomplete
engineering verification is still a report and normally exits 0. Invalid request/configuration input
exits 2; an internal error or a report with `tool_error=true` exits 3.

Read the independent result fields:

| Field | Meaning |
| --- | --- |
| `verification_status` | `passed`, `failed`, or `incomplete` across the declared output, manifest and record-binding checks. |
| `execution_provenance` | `attested`, `unattested`, or `contradicted`, reported separately from the check outcomes. |
| `change_observed` | `changed`, `no_change`, or `unknown` from artifact identity/availability. `no_change` alone does not pass or fail the request. |
| `manifest_validation` | Actual source/output byte and lineage validation, or an explicit unavailable/not-applicable state. |
| `origin_review` / `after_review` | Conditional references to the original and new review reports. |

Output verification can pass with `execution_provenance=unattested` when no approval or execution
record was supplied; that is not an attested execution. Inconsistent execution records, or an
execution record without its valid approval, produce `contradicted`; they are not repaired or
ignored, and the failed record-binding check prevents `verification_status=passed`. An invalid
approval with no execution record leaves `approval_validation=failed` and provenance `unattested`.
A profile mismatch, incomplete discovery, ambiguous match, or unavailable required input keeps
dependent checks incomplete rather than converting uncertainty into success.

## Deterministic record builders

The library module `cad_to_facts.records` exposes `build_root_source_manifest`,
`build_derived_source_manifest`, `build_approval_record`, and `build_execution_record`, plus
`GeneratedArtifactInput` for declared outputs. Builders recompute exact raw-byte hashes and sizes,
confine manifest paths to normalized workspace-relative POSIX paths, reject duplicate/overlapping
path sets, and compare actual derived source changes with the bound plan. They do not execute CAD
or scripts and do not infer approvals or execution from output existence.

Approval requires an explicit approver, decision and timestamp. Execution requires explicit mode,
result, timestamp, `attested_by`, and `attestation`; those fields are retained in the record. An
attested record remains a declared local observation, not independent cryptographic proof. A real
pre-approval/post-attestation text-to-cad 0.11.10 run is recorded in the repository's
`docs/attested-change-smoke.md`; the earlier `docs/text-to-cad-smoke.md` remains unattested.

## Source-backed provenance

A hash of an exported STEP alone does not identify editable source. Source-backed changes use
before/after `SourceManifest` objects linking:

- editable source files and their hashes;
- dependency/configuration locks and generator version;
- generated outputs and their correspondence to source;
- `lineage_kind=root|derived`, with `parent_manifest_sha256` and `modified_from` only for derived
  manifests.

A root manifest must not invent a parent or old source. A derived manifest must name the exact
previous manifest and old-to-new source mappings. A request declaring a source-backed baseline but
missing its manifests cannot pass manifest validation. A manifest is a traceable declaration bound
to bytes, not independent proof that its generator produced those bytes.

## Matching and evidence limits

`native_ref`, `adapter_key`, and numeric `fingerprint` matching are used by change verification;
there is no standalone match CLI. A match is evidence under the declared method and tolerances, not
persistent cross-revision identity. Required unmatched/ambiguous entities prevent a passed result.
With complete discovery, a proven unexpected deletion can fail; incomplete discovery or unresolved
matching stays incomplete.

## BOM and process-card inputs

`facts bom` is implemented; see [BOM extraction](bom.md). It exposes incomplete assembly discovery,
source/XCAF reconciliation and `known / observed / unknown` quantity states. `facts process-input`
is implemented only for one STEP solid and existing volume/area/bbox facts plus explicit user
context; see [ProcessCardInput](process-input.md). Declared material and validated features remain
unsupported gaps there, and semantic PMI extraction is a separate `facts pmi` command rather than a
ProcessCardInput field. ERP/PLM/PDM/MES/CAPP connectors, template
rendering, tool/machine databases, operation sequencing, setup planning, machining parameters,
approval-workflow systems, and production release remain out of scope.
