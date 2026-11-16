# DWG and DXF drawings

Use `facts inspect`, `query`, `review`, `render` or `drawing-bom` with a drawing-specific profile. DXF
is read directly by ezdxf; DWG requires a separately installed ODA File Converter.

```bash
facts inspect drawing.dxf --summary
facts query drawing.dxf --kind line --limit 20
facts inspect drawing.dwg --oda-path "C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe"
facts review drawing.dwg --oda-path ... --requirements ... --rules ... --scope ... --context ...
```

`--read-scope drawing` is optional for DWG/DXF and invalid for STEP. Without ODA, DWG returns a failed
snapshot with `ADAPTER_UNAVAILABLE`; never describe this as a parsed drawing. The converter path is
never guessed: ask the user for it and supply `--oda-path` (or `oda_executable` in JSON options).

ODA is proprietary. Its public-examples FAQ limits non-member use to non-commercial applications.
Do not bundle it, auto-install it, or ignore licensing. Conversion is local, audited, time-limited and
uses fresh input/output directories; source files are never overwritten. It is not a complete sandbox.

## Structure and XREFs

Read `snapshot.drawing` for layers, model/paper-space layouts, block definitions and external-reference
flags. Entities retain DXF type, handle when present, container, layer, source artifact hash and unit.
Block references are not expanded into duplicate geometry; ATTRIB values attached to a block reference
are cataloged once under the referencing container. Audit errors/fixes and empty entity catalogs
prevent unsupported complete claims.

The default `xref_mode=unresolved` produces `DRAWING_EXTERNAL_REFERENCE` and partial discovery. To
resolve references, ask the user for allowed local roots and choose a mode:

```bash
facts inspect host.dxf --summary --xref-mode linked --xref-root /allowed/project
facts query host.dxf --kind line --xref-mode flatten --xref-root /allowed/project
```

- `linked` keeps each referenced file as an independent SourceArtifact and records a flat reference
  graph in `drawing.external_references`; it does not merge child entities into host queries.
- `flatten` embeds referenced block content for host queries, measurements and SVG rendering. Each
  copied entity retains the real child artifact hash, unit and derived-DXF evidence. Never rebind a
  child fact to the host hash or apply host units to a child.

XREFs outside every root, UNC/URL/network paths, cycles, missing files and parse failures remain
partial. Defaults cap depth/files/bytes/time; `--xref-max-depth`, `--xref-max-files`,
`--xref-max-bytes` and `--xref-timeout-seconds` adjust the budgets. In-process parse timeouts are
cooperative, not a preemptive sandbox. Resolved references with unknown units or audit problems
produce `DRAWING_EXTERNAL_REFERENCE_PARTIAL`.

For DWG, `drawing.conversion` binds the original artifact to the derived ACAD2018 DXF SHA-256/size,
ODA executable identity and fixed conversion options. This is conversion evidence, not proof that the
DXF is visually or semantically identical to the DWG.

## Facts and rules

- All entities: declared `entity_type`, `layer`, `container`.
- TEXT/MTEXT/ATTRIB/ATTDEF: declared `text`; ATTRIB/ATTDEF also declare `attribute_tag`.
- INSERT/MINSERT: declared `block_name`.
- LINE, LWPOLYLINE, ARC: measured `length`.
- CIRCLE and closed LWPOLYLINE: measured `area`; CIRCLE also has `circumference`.

LWPOLYLINE bulges use exact arc and circular-segment formulas, not chord approximations. STEP volume
is unsupported for drawings. `$INSUNITS` governs numeric conversion; unitless drawings produce
`UNKNOWN_UNIT` numeric gaps and never default to mm. A unitless flattened child does not inherit the
host's units.

Rules select entity kinds such as `line`, `text`, `insert`, or `lwpolyline`. Use applicability
`{"fact_predicate": "container", "equals": "Model"}` to restrict a rule to model space. Declared
facts can be reviewed even when an entity has no supported geometric measurement, but unresolved
unit/discovery diagnostics still affect report completeness.

Do not infer title-block fields, manufacturing semantics, persistent entity identity, or a BOM merely
from text, layers or block names.

## Drawing questions

Use an explicit JSON `DrawingQuestionSpec`; drawing `--question` is not implemented. The deterministic
executor runs entity, text, layer, block, measurement, dimension, name-candidate and explicit
attribute-BOM intents. It does not reuse STEP occurrence/feature/orientation semantics.

```bash
facts ask drawing.dxf --spec examples/drawing-question.json
facts ask drawing.dwg --oda-path "C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe" --spec drawing-question.json
```

```json
{
  "original_text": "How many lines are in model space?",
  "interpretation_basis": "agent_interpretation",
  "interpretations": [{
    "interpretation_id": "model-lines",
    "intent": "entity_count",
    "selector": {"kinds": ["line"], "containers": ["Model"]}
  }]
}
```

| Intent | Answers |
| --- | --- |
| `entity_count` / `entity_lookup` | Raw matched entities; lookup returns bounded descriptors. |
| `text_lookup` | Declared TEXT/MTEXT/ATTRIB/ATTDEF display text. |
| `layer_inventory` | Declared layers with off/frozen state, observed-only layers and catalog counts. |
| `block_inventory` | Block definitions versus INSERT/MINSERT instances; geometry is not expanded. |
| `measurement_summary` | Length, area or circumference over supported entities; explicit units. |
| `dimension_inventory` | Declared DIMENSION values and override text; no geometry association. |
| `name_candidate_count` | Unvalidated block-name/layer-name/text/attribute-tag matches; semantic coverage stays unknown. |
| `semantic_evidence` | Declared candidate context, including attached ATTRIB values for matched INSERTs. |
| `drawing_bom_lookup` | Existing explicit-tag attribute BOM extract. |

Selectors AND `kinds`, `layers`, `containers`, `handles` and `text_contains_any`.
`layer_state_policy=all|visible` controls off/frozen layers. Omitting `containers` means the whole
catalog, including model space, paper space and block definitions; say so in the answer. Entity/text
count states are `known` only with complete discovery, `partial` with partial discovery, and `unknown`
on failed/unknown reads (`value=null`, never zero). `name_candidate_count` uses its own
`state=candidate` layer. Unitless measurements are unknown. `measurement_summary` aggregates only
measured entities and never extrapolates. Dimension values are not part dimensions. Name candidates
are not validated doors/windows/holes. `semantic_evidence` returns declared block/layer/text/
attribute-tag matches plus attached ATTRIB context for INSERTs; it is `unvalidated` and
`general_semantic_coverage=unknown`, never an inferred material/part/function field. Attribute BOM
completeness follows the existing `drawing-bom` rules. `layer_inventory` accepts only
`selector.layers`; `block_inventory` and `drawing_bom_lookup` reject selectors instead of silently
ignoring them.

Read `DrawingQueryScope` for artifact/snapshot binding, filters, container scope, layer-state policy
and source artifact hashes. Common gaps include `DRAWING_DISCOVERY_PARTIAL`,
`DRAWING_DISCOVERY_UNKNOWN`, `DRAWING_SNAPSHOT_FAILED`, `RESULT_LIMIT_APPLIED`,
`INSERT_GEOMETRY_NOT_EXPANDED`, `DIMENSION_GEOMETRY_ASSOCIATION_UNSUPPORTED`,
`SEMANTIC_CANDIDATES_UNVALIDATED`, `SEMANTIC_CONTEXT_DECLARED_ONLY` and
`SEMANTIC_COVERAGE_UNKNOWN`. General drawing semantics, title-block inference, paper-space scale
heuristics and persistent identity remain unimplemented. The full contract is in
`docs/drawing-questions.md`.

## Selective output and SVG

`inspect --summary` omits the entity catalog and facts. `query` supports repeated `--kind`, `--layer`
and `--container` filters, case-sensitive `--text` substring matching, and positive `--limit`/`--cursor`
pagination. Values within a field are ORed; fields are ANDed. Cursors are snapshot-local; keep the
same filters for consistent pages. These options bound JSON output, not initial parsing cost.

```bash
facts render drawing.dxf --output drawing.svg --layout Model
```

SVG is created exclusively and never overwrites an existing file. External raster images are ignored,
preventing implicit external image reads; an otherwise empty render still produces SVG. It is
visual-review material, not proof of rendering fidelity or geometry. Linked XREF content is not
composited into the host layout; use `flatten` for a derived view containing referenced blocks.

## Attribute-block BOM

```bash
facts drawing-bom drawing.dxf --part-tag PART --material-tag MATERIAL --require-tag MATERIAL
facts drawing-bom drawing.dxf --part-tag PART --quantity-tag QTY
```

The part tag is explicit and required. Default scope is model-space INSERT/MINSERT occurrences;
repeat `--container` for other containers. Without a quantity tag, instances including MINSERT
multiplicity are counted; non-positive counts and ambiguous zero-spacing arrays become unknown.
With a quantity tag, missing or non-canonical/non-positive quantities become unknown. Rows retain
part/material/description declarations, block names, occurrence refs and every source artifact hash.
Coverage separately totals known, observed and unknown quantity states. Missing required tags,
conflicting properties, unknown parts and partial discovery prevent `complete=true`. XREF attachment INSERTs are not part occurrences. Uncounted external references
block completeness unless `--allow-xref-exclusion` explicitly accepts their exclusion from the
selected scope; that acceptance does not claim their contents were counted. This is not an
ACAD_TABLE, title-block-inference, manufacturing or ERP BOM.
