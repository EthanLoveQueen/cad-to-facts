# Semantic PMI

`facts pmi part.step` extracts declared AP242 semantic dimensions, geometric tolerances and datums
from one STEP artifact. It is a read-only, offline, deterministic extraction. It does not infer
missing PMI, recognize features, evaluate GD&T or generate inspection/manufacturing decisions.

```bash
uv run facts pmi part.step
uv run facts pmi assembly.step --read-scope assembly
```

The output contains `artifact`, a summarized `snapshot`, and `pmi` (`PmiExtract`). Read
`pmi.status`, `pmi.complete`, `pmi.coverage.discovery`, `pmi.gaps`, `pmi.diagnostics` and
`pmi.annotations` before using any value. `ready` with zero annotations is a valid empty result; it
does not mean PMI was dropped.

## Annotation semantics

- `kind=dimension`: nominal value, unit, tolerance, qualifier and modifiers when declared.
  Presentation-only graphical labels are counted in `inventory.presentation_entities`, not emitted.
- `kind=geometric_tolerance`: magnitude, datum references (`A`, `A,B,C`), material-requirement and
  zone modifiers when declared.
- `kind=datum`: declared identification and linked datum feature where XCAF exposes one.

Tolerances have `form=limits` or `form=deviation_magnitudes`. Magnitude form has
`sign_convention=not_reported_by_reader`, plus a `PMI_TOLERANCE_SIGN_NOT_REPORTED` diagnostic: never
invent plus/minus sides.

A `PmiAnnotation` can have `value=null` when the semantic object exists but its value or unit is not
usable. A matching `PmiGap` explains why. Null is not zero.

## Units

Values are emitted only when the file's representation contexts provide one unambiguous unit for
that category. The current profile checks dimension length, dimension angle and tolerance length
globally because XCAF does not expose a per-dimension representation pointer. Mixed units keep the
annotation but leave the value null with `PMI_UNIT_AMBIGUOUS`; unreadable units produce
`PMI_UNIT_UNKNOWN`. Recognized length units: nm, um, mm, cm, m, km, in, ft, yd. Angle units: rad,
deg, arcmin, arcsec. `pmi.units` and `pmi.unit_contexts` record what was observed. XCAF normalizes
nominal values, length-based tolerances and angular limit bounds to system units (mm, degrees); the
extractor converts them back to the declared canonical unit. Angular deviation magnitudes stay in
the declared angle unit.

## Geometry links

`native_shape_refs` retains XCAF label entries and shape types. `linked_entities` contains
`EntityRef`s such as `solid:0` only when PMI-document solids uniquely match snapshot solids by
volume, area, centroid and bbox fingerprints. Status:

- `resolved`: at least one linked shape mapped to a snapshot solid;
- `unresolved`: linked XCAF shapes exist but none mapped;
- `absent`: XCAF exposes no linked shape.

These states describe the projection, not whether the design intended a link, and not persistent
identity. Duplicate/indistinguishable solids stay unresolved. Never convert them to a face ID or
pick the nearest solid.

## Coverage and completeness

`inventory` counts raw STEP entities. `coverage` compares observed and extracted counts and
summarizes link states. `discovery=complete` only when every observed annotation category is
accounted for and no unsupported category is present. Datum features are supporting links represented
through datum annotations, not separate annotations. Unsupported categories currently include datum
systems, datum targets and surface texture/finish; they produce `PMI_UNSUPPORTED_TYPE` and prevent
completeness.

- `status=ready`: no gaps, complete discovery. A file without semantic PMI is ready and complete
  with zero annotations.
- `status=partial`: gaps or incomplete discovery.
- `status=failed`: STEP read/transfer failed; a fatal `PMI_READ_FAILED` diagnostic is present.

`complete=true` means this profile accounted for what it could see, not AP242 conformance or
engineering correctness. Gap codes: `PMI_VALUE_UNAVAILABLE`, `PMI_VALUE_INVALID`,
`PMI_TOLERANCE_INVALID`, `PMI_UNIT_UNKNOWN`, `PMI_UNIT_AMBIGUOUS`, `PMI_GEOMETRY_LINK_ABSENT`,
`PMI_GEOMETRY_LINK_UNRESOLVED`, `PMI_DATUM_IDENTIFICATION_MISSING`,
`PMI_DATUM_REFERENCE_UNRESOLVED`, `PMI_UNSUPPORTED_TYPE`, `PMI_READ_FAILED`.

## Limits

- Full AP242 conformance is not claimed. Only the supported XCAF GD&T projection is reported.
- Surface texture/finish, datum targets and datum systems, graphical PMI and visual inference are
  unsupported. Datum features are represented only through datum links.
- Signed deviations are not recovered from magnitude-only reader values.
- Mixed per-dimension units are conservatively left unvalued.
- AP203 geometry-only files return an empty ready result; drawings are rejected.
- `process-input` does not project PMI: `semantic_pmi` remains an `UNSUPPORTED` design input.
- One NIST AP242 file plus self-written OCCT AP242 fixtures and analytic empty cases do not
  establish general exporter interoperability.

The NIST CTC-01 validation file currently yields 12 dimensions (8 valued), 6 tolerances, 3 datums,
9 presentation labels, 19 resolved and 2 absent links, 7 gaps, `discovery=partial` and
`status=partial`.
