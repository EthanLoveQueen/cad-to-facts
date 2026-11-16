# Reproducible source-backed change example

This directory packages the real local text-to-cad 0.11.10 run recorded on 2026-11-14. The approved
operation changed only `HEIGHT` from 30 to 40 mm in a separate copy of a 10 × 20 × 30 mm build123d
box. The baseline and modified STEP files, editable sources, manifests, reviews, request, plan,
approval, execution record and historical modification report are included.

This is a **test-harness attestation**, not independent cryptographic execution proof, production
approval, persistent cross-revision identity, or general text-to-cad interoperability. The source
scripts are executable examples, not data to run implicitly. Neither change command executes them.

## Offline replay

From the repository root, run exactly:

```bash
uv run facts verify-change \
  --request examples/change-loop/recorded/change-request.json \
  --plan examples/change-loop/recorded/change-plan.json \
  --approval examples/change-loop/recorded/approval.json \
  --execution examples/change-loop/recorded/execution.json \
  --before-manifest examples/change-loop/baseline/manifest.json \
  --after-manifest examples/change-loop/modified/manifest.json \
  --origin-review examples/change-loop/baseline/review.json \
  --before examples/change-loop/baseline/box.step \
  --after examples/change-loop/modified/box.step \
  --replay-relocated-output
```

Expected result:

```text
verification_status=passed
execution_provenance=attested
change_observed=changed
manifest_validation=passed
approval_validation=passed
unresolved_issues=[]
tool_error=false
```

`tests/test_golden_change_example.py` runs this public CLI path. The replay is deterministic and
offline; it does not require text-to-cad, ODA, network access or any source execution.

The original request binds an absolute output directory from the recorded Windows workspace. Moving
the evidence into this example would normally produce
`input_identity:output-location:OUTPUT_LOCATION_MISMATCH`. The explicit
`--replay-relocated-output` option permits only the same output filename at the supplied `--after`
location. The replay report says that the recorded absolute directory was not revalidated. The flag
is off by default and does not alter the request, approval or execution record; do not use it to
bypass an output-location failure during a live change.

`recorded/modification-report.json` is the historical report from the original location, not a file
to overwrite or a byte-for-byte replay snapshot. A relocated replay has a different actual output
locator and report identity.

## Recorded identities

```text
ChangeRequest      b3440c4cac5684726b943d8c17ff9ed3912bee1a69eb31a5636265e64f48b9c8
ChangePlan         bd610fa94a94dc19af98f5782485d341bdb78cfe5cf5b19e4deeb68f6b3147f9
root manifest      ac6c6840a3a8b717dee6ca3e81467dd410752b9b9108d51fd8aa02763f3633da
derived manifest   fde6d64c44ebee876b830c21634369c9f252be65283d90253f21415cf114cf89
ApprovalRecord     dea2dfdb8aba970e924ef5885547a9244f247563445a1b7ecea3394dbf43afeb
ExecutionRecord    ba6fb86d0ebff6a6f82b15accd9df7ba7e0a4724d4e196893c7a292061284cae
```

The approval precedes the execution timestamp. Both approval and attestation name
`cad-to-facts-test-harness`; this is intentionally disclosed rather than presented as independent
approval.

## Supplementary native evidence

`native-execution-evidence.json` records the observed text-to-cad document IDs, native build/export
observations and raw-log SHA-256 values. `baseline/*.log` and `modified/*.log` are sanitized UTF-8
copies: viewer URLs/tokens are omitted, legacy console separators are normalized and output paths
are relative. Raw logs are not redistributed, so their hashes are local audit references rather than
publicly reproducible downloads. No `closure.key` was observed or claimed.

This supplementary evidence does not replace `recorded/execution.json` and does not upgrade the
attestation into cryptographic proof.

## Preparing a new run

`prepare-spec.template.json` is separate from the recorded spec and uses the relative output path
`modified/box.step`. To derive a fresh request/plan without executing CAD:

```bash
uv run facts prepare-change \
  --report examples/change-loop/baseline/review.json \
  --finding 41cd4f98562e4bfdc0bae99931c1a90d1e848b56ff909bf1c67c02705e07595e \
  --before examples/change-loop/baseline/box.step \
  --read-scope assembly \
  --requirements examples/change-loop/review-inputs/requirements.json \
  --rules examples/change-loop/review-inputs/rules.json \
  --scope examples/change-loop/review-inputs/scope.json \
  --context examples/change-loop/review-inputs/context.json \
  --spec examples/change-loop/prepare-spec.template.json \
  --before-manifest examples/change-loop/baseline/manifest.json
```

Save the resulting `ChangePreparation` as a new work product. Its IDs differ from the recorded run.
Before any source execution, create a new explicit ApprovalRecord bound to that complete fresh
request and plan, copy the editable source into a new isolated workspace, and never overwrite the
baseline or packaged evidence. After actual execution, build manifests and an ExecutionRecord from
the observed bytes and explicit attestation; do not reuse or backdate this example's records. See
`docs/attested-change-smoke.md` and `skills/cad-to-facts/references/change-verification.md`.
