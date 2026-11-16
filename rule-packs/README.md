# Rule packs

A rule pack contains the four explicit review inputs plus a validation record. It is not activated
implicitly and never replaces a project-specific `ReviewScope` or engineering review.

Every shipped rule declares:

- `review_type`: `file_health`, `requirement_compliance`, or `design_process_rule`;
- source and reviewer metadata;
- `applies_to` limits;
- a `validation_ref` with the public commands and observed results;
- the conclusions the rule cannot support.

`step-file-health` checks only the documented snapshot readiness contract. It is not a design standard.
No generic manufacturing/design-process rule pack is claimed: those rules must come from an identified
customer, standard, or validated engineering source and be tested on the intended process and corpus.

Run a pack explicitly from the repository root:

```bash
uv run facts review part.step \
  --requirements rule-packs/step-file-health/requirements.json \
  --rules rule-packs/step-file-health/rules.json \
  --scope rule-packs/step-file-health/scope.json \
  --context rule-packs/step-file-health/context.json
```

Untyped legacy rules keep their behavior and content identities. JSON serialization includes the
new optional `finding.review_type` and `review_type_summary` keys with null values for a wholly
legacy report; typed runs populate those fields and per-type summaries. Optional null fields are
excluded from structured content hashing, so existing bound review and change identities do not
change. The four-state finding semantics are unchanged.
