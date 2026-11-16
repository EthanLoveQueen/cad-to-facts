# Changelog

## Unreleased

### Added

- Extended `facts resolve` with alias/root filters and explicit-camera spatial constraints.
  Directional relations use world-bbox center projections; `near` requires a numeric world-bbox gap
  limit. References must be unique, while the lone `{"is_root": true}` reference explicitly denotes
  the union of root occurrences rather than choosing one.
- `facts features` for unvalidated door/window name candidates and conservative validated full
  cylindrical through-holes with radius, length, axis, area and explicit general-coverage gaps.
  Ordinary cylinders, blind/counterbored/rectangular/intersecting and other hole forms are not
  promoted to general validated feature recognition.
- `facts orient` for six world-bbox projection candidates and an explicitly assumed front based on
  the unique largest projected face pointing outward from the assembly center. Axis/outward ties
  return `ambiguous`; no source-declared or functional-front claim is made.
- `facts ask --spec ...` and bounded offline `facts ask --question ...` with common
  QuestionSpec/AnswerReport contracts. Explicit agent/user interpretations and a limited
  Chinese/English grammar share locate/count/feature-geometry/orientation execution, preserving
  original text, assumptions, alternatives, known/observed/candidate/unknown counts, evidence and
  gaps. Unsupported wording and missing natural-language near distances remain unsupported.
- Agent question workflow now decomposes compound requests, materializes reviewable interpretations,
  follows status/gap-driven evidence loops, offers exact-target conditional answers, asks only
  decision-changing questions, and synthesizes values/candidates/assumptions/gaps before handing
  exact targets to `cad-view`. Added the public analytic `question-assembly.step` and three local
  no-publish model-question eval cases for compound evidence, conditional orientations and SVG handoff.
- Bounded drawing questions through `facts ask drawing.dxf --spec ...` with a sibling
  `DrawingQuestionSpec`/`DrawingAnswerReport` profile. Intents cover entity count/lookup, display-text
  lookup, layer/block inventory, exact bulge-aware length/area/circumference summaries, declared
  DIMENSION values, unvalidated block/layer/text/attribute-tag name candidates, a declared
  semantic-evidence bundle with attached ATTRIB context for matched INSERTs and explicit
  attribute-BOM lookups. Counts preserve container and off/frozen-layer scope and distinguish
  known/partial/unknown; failed or unitless reads remain unknown rather than zero. STEP occurrence
  and feature intents are not reused. Added `examples/question-drawing.dxf`,
  `examples/drawing-question.json` and `docs/drawing-questions.md`.
- Target-isolated STEP `facts render --target ... --view-spec ...` using OCCT hidden-line removal,
  global or explicit orthographic cameras, optional hidden paths and a bounded SVG point budget.
  Each render creates a new-only SVG and `.view.json` manifest binding source, snapshot, target,
  view assumptions, renderer, projected statistics and output hash. `front` remains a global-axis
  preset, not automatic design-front recognition.
- Separate `cad-view` skill for deterministic STEP occurrence views and evidence-guided question/
  target-resolution references in `cad-to-facts`. No VLM, PNG or editable-source location mapping is
  claimed; assumed orientation remains distinct from declared front.
- Bounded `facts pmi` for declared AP242 semantic PMI: dimensions, geometric tolerances and datums
  with units, qualifiers/modifiers, datum references, XCAF-linked snapshot solids, raw source
  inventory, coverage, explicit gaps and deterministic content identities. NIST CTC-01 yields 12
  dimensions (8 valued), 6 tolerances, 3 datums, 19 resolved/2 absent links and seven gaps
  (including unsupported datum systems); files without semantic PMI return a ready, complete empty
  result.
- Constrained single-solid `facts process-input` with explicit user-context provenance, required
  missing inputs and no manufacturing planning.
- Optional review typing, per-type summaries and the sourced/validated `step-file-health` rule pack.
- Public real source-backed change records, sanitized supplementary native evidence and an offline
  golden replay regression.
- Explicit archived-output relocation replay with strict default output-location behavior.
- `facts doctor --check`, installation/recovery/release guides, distribution checks, CI workflow and
  a local no-publish plugin acceptance eval case.
- Second real-corpus stress record and conditional regression for a larger user-supplied production
  assembly: hundreds of solids, an unreconciled source-NAUO versus XCAF component count, observed
  BOM rows, and explicit ProcessCardInput multi-solid refusal. Production data, paths, hashes and
  measurements are git-ignored and are not published.
- Conditional real-corpus regressions for two further user-supplied assemblies: an AP242 assembly
  with complete assembly discovery, centimetre normalization, a complete BOM under the profile and
  a complete assembly-scope file-health review; and an AP214 multi-root assembly with a
  1-of-2-root single-part transfer, a PRODUCT-versus-XCAF definition mismatch and observed BOM
  rows. The AP242 file is also pinned as a no-PMI negative control even though its header names
  AP242 Edition 2 and the CAx-IF PMI recommended practices. Production data and details are not
  published.
- Self-written OCCT AP242 semantic-PMI fixtures covering millimetre, centimetre and inch values,
  deviation and limit dimensions, angular dimensions, datum-referenced position, material modifier
  MMC and the unsupported datum-system gap. The fixtures are generated in temporary test
  directories and do not establish exporter interoperability.

### Fixed

- Failed question snapshot/feature reads now return null `unknown` counts rather than observed zeroes.
  Spatial filtering also retains candidate geometry diagnostics and prevents completeness when an
  unevaluable candidate bounding box is missing.
- Model and drawing BOM coverage now report `known_quantity_definition_total`, so
  known/observed/unknown quantity states reconcile to `definition_total` instead of leaving `known`
  rows implicit.
- PMI nominal values, length-based tolerance/geometric-tolerance magnitudes and angular limit bounds
  are converted from OCCT XCAF system units back to the representation's declared unit. Angular
  deviation magnitudes stay in the declared angle unit. An inch fixture now pins `0.5 in` as
  `0.5 in`, not `12.7 in`.

### Limits

- STEP target selectors cover declared fields and bounded world-bbox spatial relations, not face/edge
  geometry or general functional features. Door/window names remain candidates; validated holes cover
  only conservative cylindrical through-holes. Offline natural language is intentionally limited, and
  orientation is assumed rather than declared. Resolved IDs remain snapshot-scoped.
- Drawing questions answer only bounded declared/measured drawing facts. General drawing semantic
  understanding, functional feature validation, title-block/material inference, dimension-to-geometry
  association, INSERT expansion, paper-space scale heuristics and drawing natural-language grammar are
  unimplemented. Entity counts are raw catalog counts, not semantic edges or engineering quantities.
  Semantic evidence is declared block/layer/text/attribute context, not an inferred field.
- STEP views are SVG-only orthographic hidden-line WorkProducts. Global `front` is not automatic
  design-front recognition; PNG, shaded/photorealistic/section/exploded views and VLM inference remain
  unimplemented. Renders and their manifests do not establish visual/geometric equivalence.
- Semantic PMI extraction is limited to the XCAF GD&T projection and file-level unit contexts.
  Surface texture/finish, datum targets, datum systems, graphical annotation recognition, signed
  tolerance deviations and per-dimension mixed units are unsupported or explicit gaps. It does not
  claim full AP242 conformance and is not projected into ProcessCardInput or review rules.
- General validated feature recognition, persistent cross-revision identity and general exporter
  interoperability remain unimplemented; bounded through-hole validation does not change this limit.
- ProcessCardInput completeness covers only its declared geometry/context profile.
- The golden execution attestation is a test-harness declaration, not independent cryptographic
  proof.
- The shell-granted plugin eval requires a working Claude Code sandbox; it is not claimed as passed
  on a Windows session where that backend is unavailable.
