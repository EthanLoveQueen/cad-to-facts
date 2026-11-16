# Constrained ProcessCardInput

`facts process-input` is implemented for a narrow STEP single-solid profile. It prepares neutral
design-side input for a person or system outside this project; it is not a process plan, operation
sequence, setup plan, template renderer or production release.

```bash
facts process-input examples/box.step --context examples/machining-context.json
facts process-input part.step --require-context material
facts process-input part.step --context context.json --require-design-input semantic_pmi
```

The context file is JSON with a `values` object. Default required keys are `material`, `stock` and
`batch_size`; one or more explicit `--require-context` options replace that default. Every supplied
value is emitted as `external_inputs[]` with `source=user_supplied`. A user saying "material is
steel" does not turn it into a declared STEP material.

## Current coverage

- Exactly one discovered solid is required. Zero or multiple solids produce
  `PROCESS_SINGLE_PART_REQUIRED`, a required `part_identity` missing input and `complete=false`.
  Never silently select the first solid.
- Existing `volume`, `area`, `bbox.extent.x`, `bbox.extent.y` and `bbox.extent.z` facts are copied
  with their evidence. Missing geometry becomes required `missing_inputs[]`.
- `declared_material`, `semantic_pmi` and `validated_features` are reported as `UNSUPPORTED` gaps.
  They are optional by default so their absence is visible without blocking a geometry/context-only
  result. Requiring one with `--require-design-input` makes the result incomplete. Semantic PMI can
  be extracted separately with `facts pmi`, but this command does not project it into
  ProcessCardInput.
- `complete=true` additionally requires ready/complete snapshot discovery, all five geometry facts,
  no required missing input and no unresolved blocking diagnostic. It covers only this profile.

The result binds artifact SHA-256, snapshot/content IDs, FactSet, ReviewContext, preparer version and
explicit options. It contains `coverage` and diagnostics. It does not infer holes, pockets, fillets,
dimensions, tolerances, material declarations or inspection features.

Context keys representing manufacturing decisions—including `operations`, `operation_sequence`,
`setups`, `setup_plan`, `machine_selection`, `tool_selection`, `cutting_parameters`, `cycle_time`
and `process_route`—are rejected with exit 2, including when nested. Do not work around that guard
by renaming a manufacturing plan as free-form context.

A completed or incomplete ProcessCardInput normally exits 0 because it is a valid work product.
Invalid JSON, unsupported artifact format or forbidden planning context exits 2; an unexpected
internal failure exits 3. Missing design knowledge stays in `missing_inputs`, never in invented
facts or confidence scores.
