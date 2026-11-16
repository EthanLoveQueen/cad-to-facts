# Semantic PMI extraction

`facts pmi` extracts declared AP242 semantic product and manufacturing information from one STEP
artifact. It reports dimensions, geometric tolerances and datums that the file declares, together
with their values, units, geometry links, source inventory, coverage and gaps. It does not infer
missing annotations, recognize machining features, certify an inspection plan or claim full AP242
conformance.

The profile is read-only and offline. The artifact SHA-256 is checked before and after the read; the
source is never modified.

## Command

```bash
uv run facts pmi part.step
uv run facts pmi assembly.step --read-scope assembly
```

`--read-scope` selects the snapshot used to bind PMI geometry links. It defaults to `single_part`;
`assembly` uses the same XCAF assembly snapshot as `facts bom`. Drawing snapshots and non-STEP
artifacts are rejected as configuration errors. The output envelope is:

```json
{
  "artifact": {"sha256": "...", "format": "step", "...": "..."},
  "snapshot": {"snapshot_id": "...", "status": "ready", "...": "..."},
  "pmi": {"pmi_id": "...", "status": "partial", "annotations": [], "gaps": [], "...": "..."}
}
```

The snapshot is summarized without its full entity catalog. A PMI extraction that fails while
reading is still a result: `pmi.status=failed`, a fatal `PMI_READ_FAILED` diagnostic and
`complete=false`; the process exits 0, like a malformed `inspect` result. Invalid command input
exits 2.

## Source and identity

`PmiExtract` binds the artifact hash, `snapshot_id`, `snapshot_content_hash`, extractor version and
profile. `pmi_id` is the RFC 8785-based structured hash of those fields plus annotations, gaps,
inventory, coverage and diagnostics. Each annotation has its own content-derived `annotation_id`.
`verify_pmi_identity` recomputes both; supplied IDs are never trusted.

The XCAF reader is re-run with GD&T and name transfer enabled. The raw STEP model remains the source
for the observed entity inventory and measurement units. OCCT's XCAF GD&T projection supplies the
annotation values and shape links. Neither source is treated as a complete AP242 implementation.

## Extracted annotations

`PmiAnnotation.kind` is one of:

- `dimension`: XCAF dimension types other than presentation-only labels. The type string is a
  deterministic snake-case projection of the XCAF enum (for example `size.diameter`,
  `location.angular`, `location.none`), and `native_type` preserves the raw enum name.
- `geometric_tolerance`: all geometric-tolerance objects transferred by XCAF, such as `position`,
  `flatness`, `perpendicularity` and `profile_of_surface`, with tolerance magnitude, datum
  references, modifiers, material-requirement modifier and zone modifier when declared.
- `datum`: one merged annotation per `(identification, name, description)`, with its declared
  identification and linked datum feature where XCAF exposes one.

Dimensions retain the nominal value, unit, tolerance, qualifier, modifiers, semantic name and
presentation name. A dimension can exist as an annotation with `value=null` when the file declares
the semantic object but the reader exposes no usable nominal value; a `PmiGap` then explains why.
That is not a zero-valued dimension and not a fact. Presentation-only labels (graphical annotation)
are counted in `inventory.presentation_entities` and are not emitted as annotations or gaps.

Tolerance handling distinguishes two forms:

- `limits`: absolute lower and upper bounds, emitted when both are finite, at least one is nonzero
  and the lower bound does not exceed the upper bound. A zero bound is allowed and stays zero.
- `deviation_magnitudes`: the reader's tolerance values are stored as non-negative magnitudes.
  `sign_convention="not_reported_by_reader"` and a `PMI_TOLERANCE_SIGN_NOT_REPORTED` diagnostic make
  the missing sign explicit. The extractor does not guess which side is plus or minus.

A declared datum reference with no identification produces `PMI_DATUM_REFERENCE_UNRESOLVED`; it is
not replaced by a label position or a nearby datum. Duplicate datum labels with the same declared
identification are merged, because they describe one datum; their links are unioned.

## Units

Dimension units come from each `DIMENSIONAL_CHARACTERISTIC_REPRESENTATION` context. Geometric
tolerance units come from the tolerance magnitude's `MEASURE_WITH_UNIT`. SI prefixes and
conversion-based units are resolved recursively. Recognized canonical units are:

| Quantity | Units |
| --- | --- |
| length | `nm`, `um`, `mm`, `cm`, `m`, `km`, `in`, `ft`, `yd` |
| angle | `rad`, `deg`, `arcmin`, `arcsec` |

The current profile emits dimension values only when all semantic dimension representations in the
file resolve to one length unit and one angle unit; it emits tolerance values only when all tolerance
magnitudes resolve to one length unit. This is deliberately conservative because the XCAF dimension
object does not expose a per-dimension representation pointer. Mixed units therefore keep the
annotation but leave `value=null` and add `PMI_UNIT_AMBIGUOUS`; unreadable units add
`PMI_UNIT_UNKNOWN`. `units` and `unit_contexts` record what was actually observed. No unit is taken
from the snapshot's system unit or invented from a typical drawing convention.

OCCT's XCAF projection normalizes nominal dimension values, length-based tolerance magnitudes and
angular limit bounds to system units: millimetres for length and degrees for angles. The extractor
converts them back to the canonical unit declared by the representation context, so a `0.5 in`
nominal is reported as `0.5 in` rather than `12.7 in`. Angular deviation magnitudes remain in the
representation's declared angle unit because XCAF does not convert them. Generated centimetre and
inch fixtures pin this behavior.

## Geometry links

XCAF reference-shape labels are retained in `native_shape_refs` as label entries and shape types
(`face`, `edge`, `vertex`, `solid`, `null`). The extractor maps a linked shape to an owner solid in
the PMI document, then maps that solid to a snapshot solid only when the match is unique under
volume, area, centroid and bounding-box fingerprints with `rel_tol=1e-6, abs_tol=1e-6`. A resolved
link is an `EntityRef` such as `solid:0`.

`link_status` means:

- `resolved`: at least one linked shape mapped to a snapshot solid.
- `unresolved`: the annotation has linked XCAF shapes, but none mapped to a snapshot solid.
- `absent`: XCAF exposes no linked shape for this annotation.

These states describe the projection, not design intent or persistent identity. Duplicate solids
with indistinguishable fingerprints produce unresolved links rather than an arbitrary choice. A
face/edge/vertex reference is never converted to a stable face ID; `solid:N` is snapshot-scoped.
Datums B and C in the NIST CTC-01 fixture, for example, have no linked datum feature in the XCAF
projection and are reported `absent`, not silently dropped.

## Inventory, coverage and gaps

`inventory` counts raw STEP entities before projection: the recognized dimension classes,
dimensional characteristic representations, geometric tolerances, datums, datum features, datum
systems, presentation labels, and unsupported categories. Datum features are supporting geometry
links represented through datum annotations, not independent annotations. Datum systems, datum
targets and surface texture/finish entities are currently counted as unsupported when observed; the
profile does not extract their reference-frame grouping or parameter models.

`coverage` compares observed and extracted counts per annotation kind, counts annotations with
values or datum identification, and summarizes link states. `discovery` is `complete` only when every
observed annotation category is accounted for and no unsupported category was observed. Datum
features remain supporting entities; an observed datum feature that is not associated with a datum
annotation is not separately reported. Otherwise discovery is `partial`, with a
`PMI_COVERAGE_INCOMPLETE` diagnostic. With a read failure it is `unknown`.

`PmiExtract.status` is:

- `ready`: no gaps and complete discovery. A file with no semantic PMI is a valid ready result with
  zero annotations, zero gaps and `complete=true`; absence of PMI is different from an unread file.
- `partial`: at least one gap or incomplete discovery.
- `failed`: the STEP file could not be read or transferred for PMI.

`complete=true` requires `ready`, complete discovery, no gaps and no unsupported category. It means
this profile accounted for what it can see, not that the file is AP242-conformant or that the
annotations are correct engineering requirements.

Gap reason codes are:

| Code | Meaning |
| --- | --- |
| `PMI_VALUE_UNAVAILABLE` | The semantic object declares no usable nominal value. |
| `PMI_VALUE_INVALID` | The value is non-finite or an invalid non-positive size. |
| `PMI_TOLERANCE_INVALID` | The dimension's lower limit exceeds its upper limit. |
| `PMI_UNIT_UNKNOWN` | No readable unit was available for this value. |
| `PMI_UNIT_AMBIGUOUS` | Several units were observed and no per-annotation unit could be assigned. |
| `PMI_GEOMETRY_LINK_ABSENT` | The XCAF projection has no linked shape. |
| `PMI_GEOMETRY_LINK_UNRESOLVED` | Linked shapes exist but did not map to a snapshot solid. |
| `PMI_DATUM_IDENTIFICATION_MISSING` | A datum label cannot be referenced because it has no identification. |
| `PMI_DATUM_REFERENCE_UNRESOLVED` | A tolerance's datum reference has no identification. |
| `PMI_UNSUPPORTED_TYPE` | A recognized semantic PMI category is outside this profile. |
| `PMI_READ_FAILED` | STEP read/transfer failed before extraction. |

Diagnostics supplement gaps and do not replace them: `PMI_TOLERANCE_SIGN_NOT_REPORTED`,
`PMI_UNIT_CONTEXT_AMBIGUOUS`, `PMI_COVERAGE_INCOMPLETE` and `PMI_READ_FAILED`.

## NIST CTC-01 observation

The local NIST AP242 edition 1 CTC-01 fixture is a validation observation, not a capability limit.
The current profile reports:

- 12 semantic dimensions and 8 dimensional representations; 8 dimensions with values and 4
  `location.none` annotations without a usable value;
- 6 geometric tolerances, all with values and resolved links;
- 3 datums (A, B, C), 3 datum features and 2 datum systems; A resolves to `solid:0`, B and C are
  link-absent in the XCAF projection; datum systems are counted as unsupported because their
  reference-frame grouping is not emitted;
- 9 presentation-only labels, not emitted;
- units `mm` for dimensions and tolerances, `deg` for angles;
- 19 resolved links and 2 absent links;
- 4 `PMI_VALUE_UNAVAILABLE`, 2 `PMI_GEOMETRY_LINK_ABSENT` and 1 `PMI_UNSUPPORTED_TYPE`
  (datum_system) gaps;
- the 6 magnitude tolerances carry the sign-not-reported diagnostic;
- `status=partial`, `complete=false`, `coverage.discovery=partial` because the declared gaps and
  unsupported datum systems remain.

The four unvalued dimensions, the two datum link gaps and the unsupported datum systems are kept
visible. Treating them as zero, omitting them, or claiming complete extraction would overstate the
evidence.

## No-PMI controls

Two user-supplied real assemblies were also read:

- A user-supplied AP242 MIM assembly whose header names AP242 Edition 2 and the CAx-IF PMI
  recommended practices contains zero semantic dimension, tolerance or datum entities:
  `status=ready`, `complete=true`, empty annotations/gaps and zero inventory. The local regression
  is private and is not part of the published test suite.
- A user-supplied AP214 assembly returns the same ready/complete empty semantic result. It is a
  manual observation because the PMI read is slow on the local reference environment.

These are negative controls. They show that schema names, header descriptions and originating-system
strings are not treated as PMI, and they do not extend positive AP242 or exporter-interoperability
evidence.

## Generated semantic-PMI fixtures

`tests/pmi_helpers.py` writes AP242 files through OCCT XCAF, and
`tests/test_pmi_synthetic.py` checks them. They cover:

- deviation and limit dimensions in millimetres;
- angular deviation and limit dimensions represented in radians;
- millimetre, centimetre and inch conversion of nominal values and dimension tolerances, plus
  inch geometric-tolerance magnitudes;
- flatness plus datum-referenced position, material modifier MMC, resolved datums A/B/C, and the
  unsupported datum-system gap.

The files are generated in temporary test directories. They are self-written and self-read by OCCT
and this project; they do not establish exporter interoperability, AP242 conformance or external
validation. The NIST CTC-01 file remains the only positive external semantic-PMI file in the corpus.

## Unsupported and out of scope

- Full AP242 semantic-PMI conformance. Only the XCAF GD&T projection and the neutral fields above
  are covered.
- Surface texture/finish extraction, datum-target extraction, datum-system reference-frame grouping
  and their semantic parameter models.
- A datum feature that is not associated with any datum annotation; datum features are supporting
  links, not independent annotations.
- Per-dimension unit contexts when a file mixes units; the conservative global check leaves such
  values unvalued.
- Signed tolerance deviations when the reader returns magnitudes only.
- Graphical PMI interpretation, raster/vector annotation recognition, OCR and visual inference.
- Inspection planning, GD&T rule evaluation and manufacturing decisions. `facts pmi` reports
  declared annotations; it does not decide whether a tolerance is achievable or a datum scheme is
  correct.
- Projection of PMI into `facts process-input`, review rules or BOM work products. `process-input`
  still reports `semantic_pmi` as an `UNSUPPORTED` design input, so requiring it keeps the work
  product incomplete.
- AP203, DXF and DWG semantic PMI. AP203 geometry-only files return an empty ready result; drawings
  are rejected for this command.

## Determinism and verification

The extractor records no timestamps or environment paths in the PMI identity. Repeated runs over the
same artifact under the same profile produce the same `pmi_id` and annotation IDs. Tests pin the
NIST counts and values when the external corpus is present, always test the empty-PMI behavior on the
analytic example, and pin the AP242 no-PMI local file's empty result in a private local regression
when that file is present.
Self-written/self-read PMI fixtures and one NIST positive file do not establish general exporter
interoperability; AP242 exporters vary in how they encode semantic versus presentation PMI.
