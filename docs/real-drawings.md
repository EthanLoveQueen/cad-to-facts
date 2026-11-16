# Real drawing validation record

One-off local validation of the DWG/DXF drawing slice against three user-supplied production
drawing pairs. The files are not redistributed. Their names, sizes, SHA-256 values, exact entity
counts and local paths are withheld from the public repository; a private local corpus manifest
retains them for the maintainer's local runs.

## Environment

- Observed 2026-11-14 on Windows 11, using the locked `uv` environment.
- Reader: `ezdxf 1.4.5`.
- Converter: ODA File Converter 27.10.0.0, supplied explicitly through `--oda-path` /
  `oda_executable`. The adapter does not search `PATH` or installation directories.
- Without that explicit path, a DWG read returns `snapshot.status=failed`,
  `entity_discovery=unknown`, no entities and `ADAPTER_UNAVAILABLE`. That is a capability gap, not a
  parse failure.
- ODA is proprietary. The convertor is not bundled, auto-installed or treated as an open-source
  Python dependency; the user is responsible for its permitted use.

## Method

1. Registered each user-converted DXF and each source DWG as immutable source artifacts. The
   private local manifest pins their bytes and hashes.
2. Read each user DXF directly with the `ezdxf-drawing` adapter.
3. Read each DWG through `oda-ezdxf-drawing` with the explicit converter path. The adapter converted
   the DWG to an audited ACAD2018 DXF in a temporary directory and parsed that derivative.
4. Compared cataloged structure: entity total, entity-kind histogram, layer count, block count,
   layout membership, XREF flags and diagnostics.
5. Extracted default facts for the first five cataloged entities in each snapshot.

## Observed structure

- All three DWG conversions and parses succeeded. The parsed structure of each user DXF and the
  adapter's derived DXF matched exactly; the bytes did not.
- Two drawing pairs were `ready`/`complete` with explicit millimetre units and no diagnostics.
- One pair was `partial`/`partial` and unitless, with unresolved external references and a
  `UNIT_UNKNOWN` diagnostic. Length facts remained gaps rather than guessed or zero values.
- The derived DXFs were not byte-identical to the separately user-converted DXFs. A different ODA
  invocation, product version, options or later post-processing could explain the difference; the
  cause was not established. This record claims matching parsed structure, not byte equality,
  visual fidelity or geometric equivalence.
- `inspect --summary` omitted the entity catalog and FactSet; `query` paginated a selected entity
  kind; `render` wrote a new SVG without modifying the source. The SVG was not used as
  visual/geometric equivalence evidence.
- Linked-XREF handling beneath an explicit root preserved host content and reported missing child
  references as missing with unknown discovery. No external path was searched implicitly.
- Unitless input did not become millimetres by default, and unresolved XREFs prevented complete or
  compliant claims.

## Limits of this record

- No visual comparison or renderer-fidelity assessment was performed. Matching entity counts and
  histograms do not prove that drawings look identical, and SVG output itself is not equivalence
  evidence.
- Measured facts are limited to the implemented predicates. SPLINE, HATCH, ELLIPSE, POLYLINE, SOLID,
  DIMENSION, LEADER, REGION and other kinds have declared facts only.
- Text values were not interpreted as title blocks, materials or manufacturing requirements. No BOM
  was inferred from blocks; `drawing-bom` still requires an explicit attribute-tag profile.
- Large DXF files still require a full in-memory parse. `inspect --summary` and `query` bound JSON
  output, not initial parsing cost; linked/flattened XREF processing has explicit resource budgets.
- This is one run on one Windows machine with one ODA version. The automated suite does not install,
  discover or depend on ODA.

## Reproduction

```bash
ODA="<explicit path to ODAFileConverter.exe>"
uv run facts inspect "<local-drawing>.dxf" --summary
uv run facts inspect "<local-drawing>.dwg" --oda-path "$ODA" --limit 5
uv run facts query "<local-drawing>.dxf" --kind line --limit 2
uv run facts render "<local-drawing>.dxf" --output new-review.svg
uv run facts inspect "<local-drawing>.dxf" --summary --xref-mode linked --xref-root test-data
```

Without `--oda-path`, the DWG command returns `ADAPTER_UNAVAILABLE`; it is not a parsing failure.
Exact local paths, hashes and structural counts are intentionally confined to the private,
git-ignored corpus manifest and regression modules.
