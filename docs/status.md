# Implementation status

cad-to-facts currently implements format-specific vertical slices, not complete P1/P2/P3/P4/P5
releases. This page records the implemented surface and explicit gaps; the [README](../README.md)
gives the short version. Design-only capabilities are labeled as such and must not be described as
operational.

## Implemented surface

- Immutable source-artifact registration using raw-byte SHA-256.
- OCCT STEP snapshots with parser provenance, source units, diagnostics, and snapshot-scoped entity
  references. A model with no solids is reported as `partial` with unknown discovery; it is never
  claimed as completely discovered.
- Verified millimetre normalization for geometric measurements; millimetre, centimetre, and inch
  STEP inputs are covered by analytic tests. A single unverified declared length unit (for example
  metre) keeps its entities and unit, marks the snapshot `partial`, and produces `UNKNOWN_UNIT` gaps
  for length facts instead of unverified measurements.
- Selective volume, surface-area, and bounding-box facts with method and evidence records.
  Measurement exceptions and negative/non-finite physical results become `MEASUREMENT_FAILED`
  gaps instead of aborting extraction or emitting invalid facts.
- Two explicit STEP read scopes. `single_part` detects assembly usage records before flattening
  and reports `ASSEMBLY_STRUCTURE_NOT_REPRESENTED` with `entity_discovery=partial`. `assembly`
  uses XCAF to preserve reusable part definitions, occurrence paths, local transformations and
  parent/child links. Reconciliation compares source PRODUCT/NAUO counts with XCAF results.
- DXF drawing snapshots and facts through ezdxf, with a separate drawing profile rather than a fake
  solid model. Layers, layouts, blocks, native handles and declared text/entity/container facts are
  preserved; LINE, ARC, CIRCLE and straight/curved LWPOLYLINE measurements normalize explicit units
  to mm/mm². Bulges use exact arc formulas; unitless input remains an explicit gap.
- Selective `inspect --summary` and filtered/paginated drawing `query` output avoid dumping large
  entity catalogs. Drawing `render` creates a new SVG for visual review without overwriting an
  existing file.
- Bounded drawing questions through `facts ask drawing.dxf --spec ...` with a sibling
  `DrawingQuestionSpec`/`DrawingAnswerReport` profile. Intents cover entity count/lookup, text lookup,
  layer/block inventory, length/area/circumference summaries, declared dimension values, unvalidated
  name candidates, a declared semantic-evidence bundle and explicit attribute-BOM lookups. Semantic
  evidence matches block names, layer names, text and attribute tags and includes attached ATTRIB
  values for INSERTs, but remains unvalidated context rather than an inferred material/part/function
  field. Counts separate known/partial/unknown and keep candidates in a separate layer; container and
  layer-state scope is preserved, and failures or unitless measurements never become numeric zero.
  General drawing semantics, title-block inference, INSERT expansion and dimension-to-geometry
  association remain unsupported.
- Explicit STEP occurrence resolution through `facts resolve`, with unique, ambiguous, unresolved
  and failed states. Selectors combine occurrence/definition names and aliases, paths, definitions,
  root/assembly kind, state and bounded spatial constraints; candidates include world-placed bounding
  boxes accumulated through nested occurrences. Spatial relations use explicit cameras/references and
  disclose center-projection or bbox-gap methods. Partial discovery never becomes global uniqueness.
- Bounded feature, orientation and question workflows through `facts features`, `facts orient`, and
  `facts ask`. Door/window names produce unvalidated candidates; conservative full cylindrical
  through-holes produce validated radius/length/axis/area geometry without claiming all hole forms.
  Orientation returns six bbox-projection candidates and only an explicitly assumed front. The common
  QuestionSpec/AnswerReport contract accepts explicit agent/user interpretations or a bounded offline
  Chinese/English grammar, preserving assumptions, count states, evidence and gaps.
- Target-isolated STEP SVG through `facts render --target occurrence:N --view-spec view.json`.
  OCCT hidden-line projection supports global-axis or explicit orthographic cameras, optional hidden
  lines and a bounded point count. A sibling `.view.json` manifest binds artifact, snapshot, target,
  camera/semantic assumptions, method, projected statistics and output hash. Both outputs are new-only.
- Explicit-root XREF handling supports independent `linked` artifact records and source-tagged
  `flatten` content with depth/file/byte/time budgets. Child evidence and units are preserved;
  unresolved, outside-root, cyclic or incomplete references prevent complete discovery.
- Neutral attribute-block drawing BOM through `drawing-bom`, with explicit part/quantity/material/
  description tags and containers, MINSERT multiplicity, and known/observed/unknown quantities. It
  does not infer title blocks or parse ACAD_TABLE semantics.
- Optional local DWG support requires a separately installed ODA File Converter and an explicitly
  supplied path. The original DWG remains the source artifact; the snapshot records the converter
  executable identity and derived DXF hash/size. ODA is proprietary, is not bundled or
  auto-installed, and its non-member license limits use to non-commercial applications. Without
  ODA, DWG returns `ADAPTER_UNAVAILABLE`.
- Declarative reviews with `snapshot.status`, `fact.present`, `numeric.compare` (`<=`, `>=`, `<`,
  `>`), `count.compare`, and `declared.value` checkers. Optional rule/finding `review_type` values
  distinguish `file_health`, `requirement_compliance` and `design_process_rule`, with per-type
  summaries in typed runs. Sourced packs under `rule-packs/` are explicit inputs, not hidden
  defaults or generic manufacturing standards. Requirements may carry an optional
  `source_sha256` for externally stored requirement bytes. Rules, parameters, requirement
  references, included-rule references and FactSet/snapshot/artifact binding are validated before
  evaluation. A scope selects an explicit `(rule_id, version)` when several versions coexist.
- `satisfied / violated / unknown / not_applicable` findings, scoped coverage, and RFC 8785-based
  content identities. Unordered inputs are canonicalized before hashing, and review recomputes and
  verifies every content ID instead of trusting supplied values. Unresolved partial/fatal
  diagnostics, unverified scope-required inputs, unmet discovery requirements, checker failures,
  empty requirements and in-scope rules with no candidates keep the report `incomplete`;
  `compliant_for_scope` requires ready status, complete discovery, full coverage, and no unresolved
  diagnostics.
- Entity matching (`native_ref`, `adapter_key`, and numeric `fingerprint` methods with explicit
  tolerances) used by change verification. It remains a library contract with no standalone match
  CLI; unmatched, ambiguous, incompletely discovered or cross-profile entities make the match report
  `incomplete`.
- Immutable `ChangeRequest`, `ChangePlan`, before/after `SourceManifest`, `ApprovalRecord`,
  `ExecutionRecord`, and `ModificationReport` contracts with recomputed content identities.
  Library builders construct root/derived manifests and approval/execution records from exact
  workspace bytes and explicit identities, timestamps and attestations; they never execute source.
  `facts prepare-change` derives a review-based request and external handoff plan without executing
  CAD. `facts verify-change` re-parses both artifacts under a fixed profile and checks preconditions,
  targets, invariants, non-target changes, data retention, manifests, original-rule re-review and
  optional approval/execution consistency.
- Independent output and provenance states: `verification_status=passed/failed/incomplete`,
  `execution_provenance=attested/unattested/contradicted`, and
  `change_observed=changed/no_change/unknown`. Passing output validation without an execution record
  remains `unattested`; an external handoff or new STEP alone never attests execution.
- Neutral model BOM extraction from assembly-aware snapshots. `facts bom` groups active occurrences
  by part definition, preserves definitions/occurrences/links, and reports explicit missing inputs.
  Quantities are `known` only with complete structure, `observed` when discovery/reconciliation is
  incomplete, or `unknown` with a null quantity when occurrence state is unknown.
- Read-only AP242 semantic-PMI extraction through `facts pmi`. A second XCAF read with GD&T transfer
  supplies declared dimensions, geometric tolerances and datums with values, units, qualifiers,
  modifiers, datum references, geometry links and source entries; the raw STEP model supplies the
  observed entity inventory and representation units. Presentation-only labels are counted but not
  emitted. Unreadable values, units, links and unsupported categories become explicit `PmiGap`s;
  `complete=true` means this bounded profile accounted for what it observed, not full AP242
  conformance. A file without semantic PMI returns a ready, complete empty result.
- Constrained neutral ProcessCardInput preparation for exactly one discovered STEP solid.
  `facts process-input` projects existing volume/area/bbox facts and explicit user-supplied context,
  and reports required `missing_inputs`. Declared material, semantic PMI projection and validated
  features are currently `UNSUPPORTED`; no feature values or manufacturing decisions are invented.
  Semantic PMI can be read separately with `facts pmi`.
- Machine-readable `inspect`, `query`, `resolve`, `features`, `orient`, `ask`, `render`, `review`,
  `drawing-bom`, `prepare-change`, `verify-change`, `bom`, `pmi`, `process-input`, and `doctor` CLI
  commands, including bounded selective output and JSON configuration errors with exit code 2.
  `doctor --check` diagnoses the local runtime and only hashes an explicitly supplied ODA file; it
  never discovers or executes ODA.

## Explicit limits

These are limited format-specific slices, not complete P1/P2/P3/P4/P5 releases. CAD execution is not
embedded or invoked by either change command; target derivation currently supports only
`numeric.compare` findings. Full AP242 semantic-PMI coverage, general ProcessCardInput preparation,
wall-thickness measurement, general feature recognition, suppression semantics, IFC and mesh adapters
remain unimplemented. The public design contract lives in
[detailed-design.md](detailed-design.md).
