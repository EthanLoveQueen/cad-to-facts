# Facts and gaps

A result is evidence about one immutable artifact. Nothing in this file is a probability or an
LLM inference.

## SourceArtifact

`facts inspect` and `facts review` first register the exact bytes of the file:

- `sha256`: SHA-256 of the raw bytes, not of parsed geometry.
- `size_bytes`, `format` (`step`, `dwg`, `dxf`, or `unknown`), `source_locator`. Format detection
  uses content signatures rather than the filename extension.

The file is read again before and after parsing. If it changes, the operation fails rather than
mixing two reads. The source file is never modified. DWG conversion writes only to a fresh temporary
workspace and binds the derived DXF separately; see [DWG and DXF drawings](drawings.md).

## ModelSnapshot

A snapshot is bound to the artifact hash and records:

- `snapshot_id`: hash of artifact hash, adapter version, parser/kernel version and parse options.
- `snapshot_content_hash`: hash of the complete snapshot content.
- `adapter_id` / `adapter_version` / `parser_kernel_version` / `parse_options`.
- `units`: declared units, for example `{"length": "mm"}`.
- `status`: `ready`, `partial` or `failed`.
- `entity_discovery`: `complete`, `partial` or `unknown`.
- `entities`: snapshot-scoped `EntityRef` values with IDs such as `solid:0` or `drawing:0`.
- `drawing`: for DWG/DXF, the drawing-specific layers, layouts, blocks and optional conversion evidence.
- `diagnostics`: structured problems, each with stage, impact, discovery impact and disposition.

Status and discovery are independent. A file can be readable (`partial`) while discovery is
complete; a transferred model with no solids is `partial` with discovery `unknown`, because an
empty catalog does not prove complete discovery. Unknown formats return a failed snapshot with
`UNSUPPORTED_FORMAT` before OCCT; incomplete STEP framing returns `PARSE_FAILED`. Never infer
`ready` from the presence of facts.

Entity IDs are valid only inside their snapshot. Do not compare `solid:0` across files or revisions,
and do not treat face IDs as stable across parsers, platforms or exports.

## Fact

A fact exists only when a declared, measured or derived value is present:

- `kind`: `declared`, `measured` or `derived`.
- `subject`: the `EntityRef` the value is about.
- `predicate`: for example `volume`, `area`, `bbox.extent.x`.
- `value` and `unit`.
- `evidence`: artifact SHA-256 and the relevant entity references.
- `method`: library, algorithm, version and parameters.

A null value is invalid; use a `FactGap` instead.

### Supported measurements

STEP measurements:
| Predicate | Method | Unit |
| --- | --- | --- |
| `volume` | `BRepGProp.VolumeProperties` | `mm^3` |
| `area` | `BRepGProp.SurfaceProperties` | `mm^2` |
| `bbox.extent.x/y/z` | `BRepBndLib.AddOptimal` | `mm` |

All STEP values are measured after OCCT transfers the file into the system length unit (mm). The method
parameters record `declared_length_unit`, `system_length_unit: "mm"`, the `conversion_factor`
(multiply a declared-unit value by it to obtain mm^n), a `derived_source_value` (the system value
divided by that factor), and `unit_conversion: "occt_step_reader"`. OCCT does not expose its
internal pre-conversion coordinates as a separate value, so `derived_source_value` is explicitly
derived for audit, not presented as an independently parsed measurement.

The bounding box is axis-aligned in the snapshot coordinate system. Minimum shape/face distance is
not wall thickness, and no wall-thickness fact exists.

For drawings, declared `entity_type`, `layer`, `container`, `text` and `block_name` facts coexist
with selected measured `length`, `area` and `circumference` facts. Supported measurements cover
LINE, ARC, CIRCLE and LWPOLYLINE; bulges use exact arc/circular-segment formulas rather than chord
approximations. Other predicates become gaps. Drawing numeric values use `$INSUNITS` and normalize
supported declarations to mm/mm². Flattened XREF facts retain the actual child artifact and unit. See
[DWG and DXF drawings](drawings.md).

### Units

Verified STEP length units are `mm`, `cm`, and `in`; all are covered by tests that check the returned
millimetre values. If the STEP file declares another single unit, the snapshot keeps its entities,
declares the unit, becomes `partial`, and records `UNIT_UNKNOWN`. Length extraction then returns
`UNKNOWN_UNIT` gaps instead of facts. Ambiguous unit declarations fail the snapshot. Drawings support
`mm`, `cm`, `m`, `in`, and `ft` through `$INSUNITS`; unitless drawings likewise produce numeric
`UNKNOWN_UNIT` gaps while declared text/layer facts remain available.

### Assemblies

`read_scope=single_part` transfers one shape and enumerates its solids. If the STEP model contains
`NEXT_ASSEMBLY_USAGE_OCCURRENCE` records, that structure is detected before flattening: the snapshot
records `parse_options.source_structure="assembly_flattened"`, sets `entity_discovery=partial`, and
adds `ASSEMBLY_STRUCTURE_NOT_REPRESENTED` with the occurrence count. Solids remain measurable, but
that snapshot is not a represented assembly or BOM.

`read_scope=assembly` uses XCAF to preserve part definitions, occurrence paths, local transformations
and links. Structural reconciliation compares source PRODUCT/NAUO counts with XCAF results. External
references, unresolved occurrences, cycles, missing roots or reconciliation mismatches produce
explicit diagnostics and prevent complete structure/BOM claims. See [BOM extraction](bom.md).

## FactGap

A gap says why a requested fact is unavailable. It is not a zero and not a negative result.

| `reason_code` | Meaning | Can a presence rule be violated? |
| --- | --- | --- |
| `ABSENT` | The subject was completely inspected and the content is proven not to declare the item. | Yes, for a required-presence rule. |
| `UNKNOWN_UNIT` | The declared unit is outside the verified measurement set. | No; the result is unknown. |
| `UNSUPPORTED` | The predicate is not implemented by this extractor. | No; the result is unknown. |
| `PARSE_FAILED` | Reading or transferring the file failed. | No; the result is unknown. |
| `MEASUREMENT_FAILED` | OCCT raised, or a physical result was negative/non-finite and rejected. | No; other independent measurements can still succeed. |
| `NOT_COMPUTED` | The input was required but no extraction result exists. | No; the result is unknown. |

Only a proven `ABSENT` gap can support a violation. Every other reason keeps the decision unknown.
`blocking_capabilities` names predicates that would be needed to resolve the gap; `evidence` binds
the gap to the artifact and subject when available.

## What not to claim

- Do not attach a confidence score to a candidate feature. Unvalidated hole, fillet or pocket
  recognition is not a fact.
- Do not claim 100% coverage when discovery is partial or unknown; only a discovered-only ratio
  exists, and it must be labeled that way.
- Do not claim a downstream file is correct merely because OCCT reports the shape valid.
- Do not claim interoperability from analytic OCCT-written and OCCT-read fixtures.
