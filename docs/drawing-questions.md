# Drawing questions

`facts ask drawing.dxf --spec drawing-question.json` executes an explicit, bounded
`DrawingQuestionSpec` against a DWG/DXF drawing snapshot. It is a drawing-specific profile beside the
STEP `QuestionSpec`; it does not reuse STEP occurrence, feature or orientation intents. The shared
answer envelope carries status, completeness, assumptions, evidence scope and gaps, while drawing
results keep their own entity, measurement and dimension semantics.

This is not general drawing semantic understanding. It reports declared drawing facts, supported 2D
measurements, explicit attribute-BOM lookups and an unvalidated semantic-evidence bundle over declared
block names, layer names, text and attribute tags. It does not infer title-block fields, functional
doors/windows/holes, assembly intent, manufacturing requirements or dimension-to-geometry links.

```bash
facts ask drawing.dxf --spec examples/drawing-question.json
facts ask drawing.dwg --oda-path <explicit-ODA-executable> --spec drawing-question.json
facts ask host.dxf --spec drawing-question.json --xref-mode linked --xref-root <allowed-root>
```

DWG requires a caller-supplied ODA path; the CLI never searches PATH or install locations. DWG
questions are bound to the derived-DXF conversion evidence recorded in `snapshot.drawing.conversion`.
Drawing `--question` is intentionally unsupported: the bounded offline Chinese/English grammar is
STEP-only. An agent interprets the user's wording and writes the explicit JSON spec; the deterministic
executor does the counting and measurement.

## Spec and answer envelope

```json
{
  "original_text": "How many lines are in model space?",
  "interpretation_basis": "agent_interpretation",
  "interpretations": [
    {
      "interpretation_id": "model-lines",
      "intent": "entity_count",
      "selector": {"kinds": ["line"], "containers": ["Model"]}
    }
  ],
  "assumptions": ["Line means raw LINE entities, not semantic edges"],
  "interpretation_gaps": []
}
```

`DrawingQuestionSpec` preserves `original_text`, the interpretation basis
(`agent_interpretation|user_supplied`; drawing has no deterministic grammar), one or more
interpretations, assumptions and interpretation gaps. Interpretation IDs must be unique. A report is
`complete=true` only when all declared interpretations are `answered`; `complete` never means the
drawing has been semantically understood. Candidate answers can be `answered` for the declared name
query while their general semantic coverage remains explicitly unknown.

## Selectors

`DrawingSelector` ANDs the supplied filters:

| Field | Meaning |
| --- | --- |
| `kinds` | Exact DXF entity kinds, normalized to lower case (`line`, `text`, `insert`, `dimension`, ...). |
| `layers` | Exact layer names. |
| `containers` | Exact layout/block container names (`Model`, `Layout1`, a block definition, ...). |
| `handles` | Exact DXF handles, normalized to upper case. Handles are snapshot-scoped evidence, not persistent identity. |
| `text_contains_any` | Case-insensitive substring match on display text by default; applies to TEXT/MTEXT/ATTRIB/ATTDEF values. |
| `case_sensitive` | Makes `text_contains_any` case-sensitive. |
| `layer_state_policy` | `all` includes entities on off/frozen layers; `visible` excludes them. Default `all`. |

If `containers` is omitted, the query covers the whole catalog, including model space, paper space and
block definitions. It is therefore `container_scope=all_catalog`, not a semantic drawing total.
Questions about what is shown in model space should set `containers=["Model"]` explicitly. If a
matched entity references a layer absent from the layer table, it is treated as visible and counted in
`unknown_layer_state_entities`; a `LAYER_STATE_UNKNOWN` gap is reported. Unsupported selector fields
for an inventory or BOM intent are rejected rather than silently ignored.

## Intents

| Intent | Result | Required inputs |
| --- | --- | --- |
| `entity_count` | Raw matched-entity count, kind/container-kind breakdowns and optional layer breakdown. | Optional selector. |
| `entity_lookup` | Bounded entity descriptors with handle, layer, container, type, text and block name. | Optional selector; `max_results`. |
| `text_lookup` | Text-bearing entity matches; defaults to TEXT/MTEXT/ATTRIB/ATTDEF. | Optional selector; `max_results`. |
| `layer_inventory` | Declared layers with off/frozen state plus observed-only layers and catalog counts. | Optional `selector.layers` narrowing only. |
| `block_inventory` | Block definitions and INSERT/MINSERT instance counts. | No selector; full catalog. |
| `measurement_summary` | Aggregate length, area or circumference over supported selected entities. | `predicate`; optional selector. |
| `dimension_inventory` | Declared DIMENSION values, type, override text and unit state. | Optional selector. |
| `name_candidate_count` | Unvalidated declared-name candidates on block names, layer names, text or attribute tags. | `candidate_terms`; `evidence_policy=candidates_allowed`. |
| `semantic_evidence` | Declared semantic-evidence bundle with entity context and attached ATTRIB values. | `candidate_terms`; `evidence_policy=candidates_allowed`. |
| `drawing_bom_lookup` | Existing explicit-tag attribute BOM extract. | `bom` with at least `part_tag`. |

### Count states

| State | Meaning |
| --- | --- |
| `known` | Entity discovery is complete and the query scope is fully enumerated. |
| `partial` | Discovery is partial (for example an unresolved XREF, recovery issue or unknown audit impact); the value is discovered-only. |
| `unknown` | The snapshot failed or discovery is unknown. `value` is null; `observed_value` may preserve the discovered catalog count. |

Entity and text counts use known/partial/unknown. `name_candidate_count` and `semantic_evidence` have
their own `state=candidate` layers with `validation=unvalidated`; candidate is not an
engineering-feature count state.

A failed read is never reported as an observed zero. An unmatched name candidate is not proof that the
intended feature is absent. Layer, block and dimension inventories can be `answered` while still
carrying explicit capability gaps.

### Measurements

`measurement_summary` supports:

- `length`: LINE, LWPOLYLINE (including exact bulge arcs), ARC.
- `area`: CIRCLE, closed LWPOLYLINE.
- `circumference`: CIRCLE.

Values are converted to `mm` or `mm^2` from the declared drawing unit. Unitless drawings produce
`UNKNOWN_UNIT` gaps and no numeric value. `total`, `minimum` and `maximum` are computed only over
entities that produced a fact. When only some selected entities produce values,
`sum_scope=measured_entities_only` and `state=partial`; nothing is extrapolated. An empty selection
has no measurement total, not a measured zero. `include_values=true` adds a bounded per-entity sample
with `values_truncated` when the sample limit applies. When `kinds` is omitted, the executor
preselects only entities that support the predicate; explicitly including unsupported kinds reports
them in `unsupported_entity_count` and adds `MEASUREMENT_NOT_APPLICABLE`.

### Dimensions

`dimension_inventory` reads declared DIMENSION entities, including custom entity kinds whose DXF type
ends with `DIMENSION`. Linear/aligned/diameter/radius values are converted to `mm`; angular values are
reported in `deg`; ordinate vectors and unsupported measurement types remain `unknown` with a reason.
`text_override` is the annotation's declared override text, not a parsed tolerance.

Dimension values are **not** associated with the geometry they annotate. The answer always carries
`association=unsupported` and `DIMENSION_GEOMETRY_ASSOCIATION_UNSUPPORTED`. Do not turn a dimension
value into a part dimension, wall thickness or feature size claim.

### Name candidates

`name_candidate_count` matches substrings case-insensitively (unless `case_sensitive=true`) on:

- `block_name`: INSERT/MINSERT block names.
- `layer_name`: entity layer names.
- `text`: display text of TEXT/MTEXT/ATTRIB/ATTDEF entities.
- `attribute_tag`: ATTRIB/ATTDEF tag names. This basis is available when explicitly requested; the
  default candidate bases remain block name, layer name and text.

The result counts distinct matching entities (`value`) and also reports per-basis distinct counts and a
bounded match sample (`matches`). `match_rows_total` counts entity/basis matches, so one entity that
matches on both a block name and a layer contributes two rows but one distinct entity. `state=candidate`,
`validation=unvalidated` and `general_semantic_coverage=unknown` are fixed. Because the default
container scope includes block definitions and ATTDEF templates, set `containers=["Model"]` (or another
placed container) when only placed instance evidence is intended.
This intent answers questions such as "how many objects are declared as DOOR blocks?" but never "how
many functioning doors does the design have?". The same wording does not prove door/window/hole
function, and a zero candidate count does not prove absence.

### Semantic evidence

`semantic_evidence` is the evidence bundle an agent can use to answer a free-form semantic question
without treating a name match as a field fact. It uses the same declared match bases as
`name_candidate_count`, defaulting to all four, and returns each match with its context:

```json
{
  "interpretation_id": "material-context",
  "intent": "semantic_evidence",
  "candidate_terms": ["material", "steel"],
  "candidate_bases": ["text", "attribute_tag"],
  "evidence_policy": "candidates_allowed"
}
```

Each `DrawingSemanticEvidenceItem` records the entity ID, kind, layer, container, handle, match basis,
matched term, declared value, source artifact hash, block name, display text, attribute tag and — for
INSERT/MINSERT entities — the attached ATTRIB values as `{tag: [declared values]}`. For example, a
matched title-block INSERT can expose `{"PART": ["A-123"], "MATERIAL": ["STEEL"], "QTY": ["2"]}`.
`attributed_insert_count` reports how many distinct matched inserts carried attached attributes.

The bundle still has `state=candidate`, `validation=unvalidated` and
`general_semantic_coverage=unknown`. `SEMANTIC_CONTEXT_DECLARED_ONLY` states that attached attributes
and matched text are declared source context, not inferred material, part, function or other semantic
field facts. The agent may quote the context, combine it with `drawing_bom_lookup`, text/measurement
evidence and explicit user assumptions, but must not promote it to a Fact or a validated engineering
conclusion. The default all-catalog scope includes block definitions and ATTDEF templates; set
`containers` when only placed-instance context is intended.

### Attribute BOM

`drawing_bom_lookup` reuses the existing `drawing-bom` extractor with explicit `part_tag`,
optional quantity/material/description tags, required tags and containers. Missing or conflicting
attributes, unknown quantities, unresolved external references and partial discovery keep
`complete=false`; the answer is then `partial` and carries `DRAWING_BOM_INCOMPLETE`. XREF attachment
INSERTs are not part occurrences. This is not an ACAD_TABLE parser, title-block inference, ERP or
manufacturing BOM.

## Evidence scope and gaps

Every interpretation carries `DrawingQueryScope` with:

- artifact SHA-256, snapshot ID/content hash, parser options and declared units;
- discovery state, effective filters, container scope and layer-state policy;
- the sorted source artifact hashes represented by the selected entities;
- the count of matched entities excluded by the visible-layer policy and the count whose layer state
  was absent from the layer table.

Resolved DXF handles, entity IDs and source hashes are snapshot-scoped. They are not persistent
cross-revision identity or editable-source locations. XREF `linked` mode keeps child entities as
independent artifacts outside the host catalog; `flatten` embeds child entities with their real source
hash/unit. In either mode, partial reference coverage prevents a complete drawing total.

Common gaps include `DRAWING_DISCOVERY_PARTIAL`, `DRAWING_DISCOVERY_UNKNOWN`,
`DRAWING_SNAPSHOT_FAILED`, `LAYER_STATE_UNKNOWN`, `RESULT_LIMIT_APPLIED`,
`MEASUREMENT_NOT_APPLICABLE`, `MEASUREMENT_NO_VALUES`, `DRAWING_MEASUREMENT_GAPS`,
`DIMENSION_MEASUREMENT_GAPS`, `INSERT_GEOMETRY_NOT_EXPANDED`, `MINSERT_ARRAY_NOT_EXPANDED`,
`DIMENSION_GEOMETRY_ASSOCIATION_UNSUPPORTED`, `DRAWING_BOM_INCOMPLETE`,
`SEMANTIC_CANDIDATES_UNVALIDATED`, `SEMANTIC_CONTEXT_DECLARED_ONLY` and
`SEMANTIC_COVERAGE_UNKNOWN`.

## Limits

- No general drawing semantic understanding, functional feature recognition, title-block field
  inference, material inference, dimension association or process intent. `semantic_evidence` is
  declared contextual evidence, not field extraction or inference.
- No INSERT geometry expansion. `block_inventory` counts definitions and insert entities separately.
- No paper-space viewport scale heuristics. Measurements use model/paper-space coordinates and declared
  drawing units; a layout scale is not silently applied.
- No persistent entity identity, editable-source location or cross-revision matching.
- No STEP occurrence, orientation or validated through-hole semantics on drawings.
- Drawing questions need an explicit JSON spec; natural-language drawing grammar is not implemented.
- VLM inference remains disabled, isolated from facts and unauthorized for uploading design files or
  derived images.
