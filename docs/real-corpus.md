# Real-file validation records: user-supplied STEP assemblies

These notes summarize read-only observations on user-supplied production STEP assemblies. The
artifacts are not redistributed. Their filenames, byte sizes, SHA-256 values, exact dimensions,
part names and other identifying measurements are withheld from the public repository; a private
local corpus manifest and private regression modules retain them for the maintainer's local runs.

Each record is a corpus observation. It is not a claim that the file is representative, that a
particular exporter is interoperable, or that a manufacturing BOM was produced.

## Case A: large flattened assembly with centimetre units

Observed:

- Single-part scope reports `partial` discovery and detects assembly usage records before
  flattening. It emits `ASSEMBLY_STRUCTURE_NOT_REPRESENTED` instead of presenting the flattened
  solid set as one completely discovered part.
- Declared centimetre length units are normalized to millimetres with explicit conversion factors.
  A bounded selection completes with no measurement gaps; a larger requested sweep also completed
  every measurement rather than silently dropping failures.
- Assembly-aware BOM extraction exposes XCAF definitions and occurrences that do not reconcile
  one-to-one with the source PRODUCT and `NEXT_ASSEMBLY_USAGE_OCCURRENCE` records. Leaf quantities
  therefore remain `observed`, the BOM remains `complete=false`, and explicit definition and
  occurrence reconciliation diagnostics are reported.
- The mismatch is not converted into missing or extra physical parts. No complete quantity or
  manufacturing-BOM claim is made.

What it validates: unit normalization, assembly-structure detection, bounded measurement, neutral
BOM extraction, and honest incomplete quantities under unreconciled structure.

## Case B: larger assembly and multi-solid process-input boundary

Observed:

- Assembly scope reports `partial` discovery with an occurrence-count reconciliation diagnostic
  between the source NAUO records and the XCAF component traversal.
- The BOM retains observed quantities and real declared names while remaining `complete=false`.
- A single-solid `process-input` request refuses to choose one solid implicitly, reports the
  multi-solid requirement diagnostic, and keeps required material/part-identity inputs missing.
- File-health review remains `non_compliant`/`complete=false` under partial discovery. The
  discovered-only inspection ratio is reported separately and is not treated as true coverage.
- A synthetic, explicitly non-standard review rule exercised `prepare-change`/`verify-change`
  plumbing without executing CAD or modifying the file. A missing after artifact stayed
  `incomplete`/`unattested`, not successful.

What it validates: large-assembly bounds, BOM quantity states, single-solid refusal, honest review
coverage, and change records that keep missing evidence incomplete.

## Case C: AP242 assembly with complete discovery

Observed:

- Assembly scope reports `ready`/`complete` discovery with no diagnostics, and the BOM reconciles
  its source PRODUCT/NAUO records with XCAF definitions and component links. All leaf quantities
  are `known` under the implemented profile, so `complete=true`.
- File-health review in assembly scope is `compliant_for_scope` with complete rule and entity
  coverage under the selected readiness rule pack.
- The file declares centimetres and is normalized to millimetres like Case A.
- Its header advertises AP242 Edition 2 and CAx-IF PMI practices, but it contains no semantic
  dimension, tolerance or datum entities. `facts pmi` returns a ready, complete, empty result.
  This is a no-PMI negative control; header text is not treated as PMI.
- Read-only target resolution, render, feature-candidate, orientation and question runs were also
  exercised. Ambiguous door name selectors stayed ambiguous; an explicit occurrence had to be
  supplied. Orientation returned an expressly assumed front, and the rendered SVG/manifest stayed
  bound to the source artifact hash.

What it validates: complete assembly discovery under this profile, a complete model-BOM extract, a
complete readiness review, centimetre normalization, honest no-PMI behavior, and evidence-bound
target/view workflows. `complete=true` is profile completeness, not ERP, procurement or
manufacturing-BOM data.

## Case D: AP214 multi-root assembly

Observed:

- Single-part scope transfers one of two declared roots and reports `ROOTS_PARTIAL`; it does not
  present the transferred root as the whole file.
- Assembly scope preserves the discovered solids but reports a PRODUCT-versus-XCAF definition
  reconciliation diagnostic. The BOM keeps leaf quantities `observed` and remains
  `complete=false`.
- The file contains no semantic PMI; `facts pmi` returns a ready, complete, empty result.
- Mis-encoded internal filename bytes are not rewritten or silently "repaired"; XCAF names that
  decode correctly are retained.

What it validates: multi-root partial-transfer visibility, unreconciled definition counts, observed
BOM quantities, and AP214 no-PMI behavior.

## What these records do not validate

- General STEP exporter interoperability, including the exporters that produced these files.
- A complete or manufacturing BOM, stable part identity across revisions, or procurement data.
- Semantic-PMI extraction or full AP242 conformance.
- Modification, approval, execution or downstream manufacturing results for any observed file.
- General natural-language understanding, general feature recognition, source-declared or
  functional front recognition, visual/geometric equivalence, or VLM inference.

## Reproduction

The source files are local and are not distributed. Commands follow the public CLI, for example:

```bash
uv run facts inspect "<local-assembly>.step" --summary --read-scope assembly
uv run facts bom "<local-assembly>.step"
uv run facts review "<local-assembly>.step" \
  --requirements rule-packs/step-file-health/requirements.json \
  --rules rule-packs/step-file-health/rules.json \
  --scope rule-packs/step-file-health/scope.json \
  --context rule-packs/step-file-health/context.json
```

Exact local paths, hashes and expectations are intentionally confined to the private, git-ignored
corpus manifest and regression modules. A fresh public checkout skips those local regressions and
runs the public analytic, synthetic and external-corpus checks that are documented in
[corpus-validation.md](corpus-validation.md).
