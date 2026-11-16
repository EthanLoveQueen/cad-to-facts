# Assembly structure and model BOM extraction

`facts bom assembly.step` is implemented for STEP assemblies. It reads with
`read_scope=assembly` through OCCT XCAF and emits a neutral `BOMExtract`. It is not an ERP or
manufacturing BOM and performs no external-system writes.

```bash
facts bom assembly.step
facts bom assembly.step --require-property name
```

## Structure and identity

The snapshot preserves reusable `PartDefinition` records, `Occurrence` records with parent,
occurrence path, local row-major 4×4 transformation and state, and parent/child `AssemblyLink`
records. Definitions and occurrences are snapshot-scoped, not persistent part numbers. Leaf
occurrences are grouped by `definition_id`; names are never the merge key. Repeated definitions and
nested occurrences are counted from occurrence paths rather than flattened solids.

The BOM includes its own definitions, occurrences and links so its line-item references are
resolvable without a separate hidden model. Artifact, snapshot and extractor identities bind the
result to exact input bytes and parsing options.

## Quantity states

| `quantity_state` | Meaning |
| --- | --- |
| `known` | All occurrences counted under complete assembly discovery with no unresolved structural blocker. |
| `observed` | A numeric count of active occurrences observed under partial, unknown or unreconciled structure; not a complete total. |
| `unknown` | At least one relevant occurrence has unknown state; `quantity` is null. |

`complete=false` whenever required inputs are missing, quantity is unknown, discovery is incomplete,
or unresolved assembly/BOM/discovery diagnostics remain. An observed numeric quantity must never be
relabeled as a known complete quantity.

## Reconciliation and diagnostics

Assembly extraction compares raw STEP PRODUCT and `NEXT_ASSEMBLY_USAGE_OCCURRENCE` counts with XCAF
definition/component counts. Differences emit `ASSEMBLY_DEFINITION_RECONCILIATION` or
`ASSEMBLY_OCCURRENCE_RECONCILIATION` and prevent completeness. Other structural diagnostics include
`ASSEMBLY_EXTERNAL_REFERENCE`, `ASSEMBLY_OCCURRENCE_UNRESOLVED`, `ASSEMBLY_CYCLE`, and
`ASSEMBLY_ROOTS_UNKNOWN`. A single-part flattened snapshot cannot be passed off as a BOM: extraction
requires the assembly profile and otherwise reports `BOM_ASSEMBLY_NOT_REPRESENTED`.

## Required properties and missing inputs

`--require-property name` reports a proven `ABSENT` missing input for a completely discovered leaf
definition without a name. Other property names currently produce `UNSUPPORTED`: the extractor does
not invent material, part number or other declarations. `BOM_REQUIRED_PROPERTY_MISSING` accompanies
required-property gaps. Missing required properties block `complete` but do not erase valid observed
structure or quantities.

Coverage reports leaf definition and occurrence totals, counted occurrences, known/observed/unknown
quantity-definition totals and structure discovery. The three quantity-state totals sum to the leaf
definition total. These are model-extraction counts, not inventory, procurement or manufacturing
quantities.
