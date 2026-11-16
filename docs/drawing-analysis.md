# DWG and DXF drawing analysis

The drawing workflow is a separate format profile, not a STEP solid model:

```text
DXF ───────────────────────→ ezdxf recovery/audit ─→ DrawingSnapshot
DWG → optional local ODA → derived DXF → ezdxf ────→ DrawingSnapshot
XREF → explicit local roots → linked evidence or source-tagged flattened content
```

`facts inspect` and `facts review` accept `.dxf` directly. DWG requires a separately installed
ODA File Converter; neither the plugin nor `uv sync` installs or downloads it.

```bash
uv run facts inspect drawing.dxf
uv run facts inspect drawing.dwg --oda-path "C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe"
```

Use the same `--oda-path` option with `facts ask`, `facts review`, `query`, `render` and `drawing-bom`.
`--read-scope drawing` may be stated explicitly; it is inferred for registered DWG/DXF artifacts.
STEP read scopes do not apply to drawings. The DWG adapter never guesses an install location:
without an explicit path it returns `ADAPTER_UNAVAILABLE`.

## Security and licensing boundary

ODA File Converter is proprietary software, not an open-source dependency. The ODA public-examples FAQ
states that non-members may use it only for non-commercial applications. Users are responsible for
having the appropriate rights for their use case. The project does not bundle ODA or accept an ODA
license on the user's behalf.

The converter runs locally with a fixed executable path, no shell, a new isolated input/output
directory, a fixed ASCII input name, audit enabled, no recursion, and a timeout. The original source
is copied, never overwritten. This is process isolation, not a complete native-code sandbox; DWG/DXF
remain untrusted input. No file is uploaded by this adapter.

## Drawing structure

`ModelSnapshot.drawing` contains:

- source format and resulting DXF version;
- layers with off/frozen state;
- model-space and paper-space layouts and their entity IDs;
- non-layout block definitions and their entity IDs;
- declared external-reference flags and paths, plus explicit resolution records when enabled;
- for DWG, `conversion` evidence containing the ODA executable SHA-256 identity, fixed ACAD2018 DXF
  output options, audit setting, and derived DXF SHA-256/size.

Every cataloged graphical entity has a snapshot-scoped ID, DXF type, handle when present, container,
container kind, layer, source artifact hash/unit and stable adapter traversal key. Layout and block
entities are cataloged once; ordinary block references are not silently expanded into duplicate
geometry. ATTRIB values attached to an INSERT/MINSERT are cataloged once under the referencing
container, while ATTDEF definitions remain with their block.

The executable hash identifies the ODA program file, not every dependent DLL. Record an ODA product
version separately in external validation records when available.

## External references

The default `xref_mode=unresolved` does not read XREF files and emits `DRAWING_EXTERNAL_REFERENCE`
with partial discovery. Resolution is opt-in:

```bash
uv run facts inspect host.dxf --summary --xref-mode linked --xref-root /allowed/project
uv run facts query host.dxf --kind line --xref-mode flatten --xref-root /allowed/project
```

- `linked` records each reference edge in `drawing.external_references`, with owner and referenced
  artifact hashes, resolved state, units, entity/discovery counts, nested parent IDs and diagnostics.
  Referenced entities are not merged into the host catalog and host `query` does not select them.
- `flatten` uses ezdxf XREF embedding for referenced block content. In-memory entity copies carry
  their actual source artifact hash, `$INSUNITS` unit and derived-DXF hash. Facts therefore use the
  child's units and evidence hash rather than inheriting those of the host. Ordinary INSERT
  occurrences are still not expanded into repeated geometry.

Resolution accepts only local files beneath at least one explicit `--xref-root`. Absolute XREF paths
must also remain under a root; relative candidates are considered beside the owner and under the
roots, but are rejected if they escape every root. UNC, URL-style and network locations are rejected.
There is no ambient search path. Cycles and missing, outside-root, unsupported or failed files remain
partial. Defaults limit nesting to 8, files to 64, total referenced source bytes to 256 MiB and XREF
processing to 120 seconds; corresponding `--xref-max-*` and `--xref-timeout-seconds` options change
those budgets. The timeout bounds ODA subprocesses and is checked cooperatively around in-process
parsing; it is not a preemptive parser sandbox. Windows paths in documentation are examples, not
auto-discovery.

`DRAWING_EXTERNAL_REFERENCE_PARTIAL` records a resolved reference with incomplete structure, unknown
units or audit diagnostics. A linked or flattened snapshot is complete only when its own and all
referenced discovery requirements are complete.

## Facts and units

All cataloged entities support declared `entity_type`, `layer`, and `container` facts. Additional
predicates are deliberately limited:

| Predicate | Current subjects | Meaning |
| --- | --- | --- |
| `text` | TEXT, MTEXT, ATTRIB, ATTDEF | Declared text content; MTEXT formatting is not interpreted as engineering semantics. |
| `attribute_tag` | ATTRIB, ATTDEF | Declared attribute tag; e.g. `PART` on a title-block attribute. |
| `block_name` | INSERT, MINSERT | Declared referenced block name. |
| `length` | LINE, LWPOLYLINE, ARC | Euclidean, exact straight/bulge-arc, or radius-angle length. |
| `area` | CIRCLE, closed LWPOLYLINE | Circle area or shoelace plus signed circular-segment area. |
| `circumference` | CIRCLE | Circle circumference. |

For LWPOLYLINE bulge `b`, the implementation uses `theta=4*atan(b)`, chord-based radius and exact
arc/segment formulas, including major arcs and either orientation. It does not flatten a curved
polyline into chords. Other entity measurements and STEP `volume` produce `UNSUPPORTED` gaps;
measurement exceptions become `MEASUREMENT_FAILED` gaps.

DXF `$INSUNITS` is explicit in `snapshot.units.length`. Numeric facts normalize mm, cm, m, inch and
foot declarations to mm/mm² with recorded factors. Unitless or unverified declarations yield
`UNKNOWN_UNIT` for numeric facts; declared text/layer facts remain available. A flattened child with
unknown units produces gaps even when the host declares millimetres. A unitless declaration is never
silently treated as millimetres.

## Selective output and rendering

```bash
uv run facts inspect drawing.dxf --summary
uv run facts query drawing.dxf --kind line --layer Geometry --container Model --limit 20
uv run facts query drawing.dxf --kind line --cursor drawing:20 --limit 20
uv run facts render drawing.dxf --output drawing.svg --layout Model
```

`inspect --summary` omits the entity catalog and FactSet; it reports entity/layer/container counts,
compact layout/block membership counts, diagnostics, conversion and XREF evidence. Block summaries
are still included, so a file with many block definitions is not reduced to a fixed-size response.

`query` returns the same compact snapshot summary, only the selected entity references and their
facts. `--kind`, `--layer` and `--container` are repeatable; repeated values within one field are ORed
and different fields are ANDed. `--text` is a case-sensitive substring over TEXT/MTEXT/ATTRIB/ATTDEF.
Pagination follows stable catalog order; `next_cursor` is valid only for the same snapshot. Keep the
filter profile unchanged for consistent pages; the cursor is not a cross-snapshot or signed query token.
`--limit` must be a positive integer; zero and negative values are rejected rather than producing an
unadvanceable cursor. It bounds the returned entities and extracted facts, not the internal parse cost.

`render` writes a new SVG through ezdxf's SVG backend and returns its hash/size. Existing files are
never overwritten. External raster images are ignored (`ImagePolicy.IGNORE`), so rendering does not
implicitly read referenced image files; an otherwise empty render still produces an SVG. Rendering is
review material only: font substitution, SHX resources, layout and renderer behavior can differ from CAD. It is not pixel-fidelity or geometric-equivalence proof.
Linked mode renders the host layout without compositing linked child geometry; use `flatten` when a
single derived review view must include referenced blocks.

## Attribute-block drawing BOM

`drawing-bom` is separate from the STEP assembly `bom` command and never infers title-block meaning:

```bash
uv run facts drawing-bom drawing.dxf --part-tag PART \
  --material-tag MATERIAL --require-tag MATERIAL
uv run facts drawing-bom drawing.dxf --part-tag PART --quantity-tag QTY
```

`--part-tag` is required. By default only INSERT/MINSERT occurrences in `Model` are considered;
repeat `--container` to select other explicit containers. Tags are matched case-insensitively and
values are retained as declared text. Without `--quantity-tag`, quantity is the observed instance
count, including MINSERT row/column multiplicity. Non-positive counts or ambiguous multi-row/column
arrays with zero corresponding spacing make quantity unknown. With a quantity tag, every occurrence
must carry a canonical positive integer; missing, conflicting or invalid values make the grouped
quantity `unknown`, never a fallback count.

Rows group by declared part number, preserve block names and all source artifact hashes, and retain
configured material/description properties. Conflicting properties, missing required tags, unknown
part numbers, empty selections and incomplete discovery prevent `complete=true`. Quantities are
`known` only with complete discovery, `observed` otherwise, or `unknown` with a null value; coverage
separately totals all three states. The INSERT
that attaches a declared XREF is not itself a part occurrence. Linked XREF contents are not implicitly
counted; flattened child occurrences require explicit container selection. Every reference without a
counted occurrence is reported in external-reference coverage and prevents completeness by default.
`--allow-xref-exclusion` explicitly accepts that selected-scope exclusion, records it in the options
and resolves `BOM_EXTERNAL_REFERENCE_EXCLUDED`; it does not claim the excluded files were counted.
This is neutral attribute-block data, not a manufacturing/ERP BOM or ACAD_TABLE parser.

## Drawing questions

`facts ask drawing.dxf --spec ...` executes a bounded `DrawingQuestionSpec` over the drawing catalog:
entity count/lookup, display-text lookup, layer/block inventory, supported length/area/circumference
summaries, declared DIMENSION values, unvalidated name candidates, a declared semantic-evidence bundle
and explicit attribute-BOM lookups. Semantic evidence can expose attached ATTRIB context for matched
INSERTs, but it is not an inferred material/part/function field. It deliberately does not reuse STEP
occurrence, feature or orientation intents. Counts preserve container and layer-state scope,
distinguish `known/partial/unknown/candidate`, and never turn failed or unitless reads into zero.
Natural-language drawing grammar is not implemented; an agent must write the explicit spec. See
[`drawing-questions.md`](drawing-questions.md) for the full contract and
`examples/drawing-question.json` for a runnable public example. This profile does not provide general
drawing semantic understanding, title-block inference, dimension-to-geometry association or INSERT
geometry expansion.

## Review and completeness

The existing review contract applies to entity kinds such as `line`, `text`, `insert`, and
`lwpolyline`. A rule can use `container` applicability to restrict a check to `Model`, a paper-space
layout, or a named block. Unknown units, unresolved external references, audit errors/fixes, and an
empty/unknown entity catalog prevent `compliant_for_scope` as appropriate. A readable drawing is not
proof of visual fidelity, title-block semantics, manufacturing correctness, or complete XREF content.

Change preparation/verification and assembly BOM remain STEP-focused; this drawing slice does not
claim a DWG modification loop. SVG, drawing BOM and query outputs are new work products/views and do
not modify the source artifact.

## Validation status

Verified by the automated suite:

- ezdxf-generated DXF fixtures for layers/layouts/blocks, ATTRIB/ATTDEF text and tag facts,
  LINE/ARC/CIRCLE/LWPOLYLINE measurements, exact clockwise/counter-clockwise bulge circles,
  unitless gaps, XREF partial discovery, recovery of truncated DXF, and UTF-8/BOM/comment preambles.
- Summary/query filtering, positive-size pagination, new-only SVG output, ignored external raster
  images (including an empty render), and attribute-block BOM counting, MINSERT multiplicity,
  invalid/ambiguous quantities and completeness behavior.
- Linked and flattened XREFs, child-unit conversion and evidence hashes, unitless children,
  outside-root rejection, cycles, nesting and byte budgets, explicit linked-reference BOM exclusion,
  and flattened child BOM occurrences bound to the child artifact.
- Drawing question intents: entity count/lookup, display-text lookup, layer/block inventories,
  length/area/circumference summaries, declared dimensions, unvalidated name candidates, declared
  semantic evidence with attached ATTRIB context and explicit attribute BOMs; container/layer-state
  scope, unitless and failed reads, partial XREF discovery, result limits, exact handle lookup and
  source immutability. `examples/question-drawing.dxf` with `examples/drawing-question.json` is the
  public end-to-end example.
- DWG registration and the deterministic `ADAPTER_UNAVAILABLE` and `CONVERSION_FAILED` paths with
  explicit converter configuration.

Verified locally against user files on 2026-11-14 (recorded in
[real-drawings.md](real-drawings.md)):

- All three supplied DWGs converted through ODA File Converter 27.10.0.0 with an explicit path and
  parsed as AC1032 DXF. Entity totals, kind histograms, layer/block counts, layout membership and
  diagnostics matched the separately user-converted DXFs exactly.
- The unitless drawing correctly stayed partial: unresolved XREFs and a unitless declaration
  produced `DRAWING_EXTERNAL_REFERENCE` and `UNIT_UNKNOWN`, with numeric gaps rather than millimetre
  assumptions. Explicit-root linked resolution later reported the references as `missing`, without
  searching outside the allowed root.
- Selective-output smoke checks returned a bounded page of LINE entities and generated a new review
  SVG. The linked summary retained host entities and partial discovery without dumping the full
  catalog. Details are intentionally withheld from the public real-drawing record.
- The derived DXFs were not byte-identical to the user-converted DXFs, so this is structural
  evidence only. No visual or geometric equivalence is claimed, and the automated suite does not
  require ODA or read the large local drawings.
