# P0 corpus validation

This document describes the reproducible P0 corpus matrix / regression inventory: which files are
in it, what each file is expected to do through the implemented public seams, how to obtain the
downloadable third-party files, and which behaviors are pinned anomalies versus supported
capability.

The private local corpus manifest (`tests/corpus/manifest.json`) and the regression modules that
bind user-supplied production files are git-ignored and are not part of the public repository. They
retain exact paths, hashes and measurements for the maintainer's local runs. A fresh public
checkout runs the analytic, synthetic and public-interface tests; private production and manifest
regressions are skipped or absent. The public documentation describes local production observations
only in generic terms.

## Scope and non-goals

- The matrix records **observed behavior** of the implemented `occt-step`,
  `ezdxf-drawing` and optional `oda-ezdxf-drawing` 0.1.0 adapters. Expectations
  that pin limitations are labeled as such; a behavior change must update the local manifest and
  this document together.
- This corpus is **not** an interoperability claim. Five downloadable third-party STEP files from
  two producers plus private user-supplied production assemblies from additional CAD toolchains do
  not establish exporter interoperability.
- No corpus test executes external CAD, external scripts, or downloaded content. Downloaded files
  are only ever passed as path arguments to `register` / `read` / `extract` or the `facts` CLI. The
  self-written semantic-PMI fixtures use the in-process OCCT writer only.
- Full-model sweeps are deliberately avoided for large private assemblies; only bounded selections
  are measured. Those regressions run only when the maintainer's private files and manifest are
  present.

## Matrix

### Private local production files (not published)

The rows below describe private regression coverage without disclosing identity, size, hashes or
measurements.

| ID | File | Format detection | Adapter expectation |
| --- | --- | --- | --- |
| `local-assembly-a` | user-supplied STEP, identity withheld | `step` | Single-part `status=partial`; assembly-usage diagnostic; centimetre normalization; bounded measurement with no gaps; assembly BOM observed/incomplete under PRODUCT/NAUO versus XCAF mismatch. |
| `local-assembly-b` | user-supplied STEP, identity withheld | `step` | Assembly `status=partial`; occurrence reconciliation mismatch; observed BOM rows; multi-solid `process-input` refusal; honest review coverage. |
| `local-assembly-c` | user-supplied AP242 STEP, identity withheld | `step` | Assembly `status=ready`/`complete`; complete BOM under the profile with known quantities; complete assembly-scope file-health review; centimetre normalization; no semantic PMI (negative control). |
| `local-assembly-d` | user-supplied AP214 STEP, identity withheld | `step` | Single-part transfer of one of two declared roots (`ROOTS_PARTIAL`); assembly PRODUCT/XCAF definition mismatch; observed BOM rows; no semantic PMI. |
| `local-drawing-a` | user-supplied DWG/DXF pair, identity withheld | `dwg` | With an explicitly nonexistent ODA path, `read()` returns `failed` / `ADAPTER_UNAVAILABLE`; the test does not depend on a local ODA installation. |
| `local-drawing-b` | user-supplied DWG/DXF pair, identity withheld | `dwg` | Same deterministic unavailable-path contract. |
| `local-drawing-c` | user-supplied DWG/DXF pair, identity withheld | `dwg` | Same deterministic unavailable-path contract. |

### Downloaded external files (in `test-data/external/`, tested when present)

| ID | File | Producer / provenance | Adapter expectation |
| --- | --- | --- | --- |
| `nist-ctc-01-ap242e1` | `nist_ctc_01_asme1_ap242-e1.stp` (396,445 B) | NIST MBE PMI project, AP242 ed.1, semantic + graphical PMI | `ready`/`complete`, mm, 1 solid, no snapshot diagnostics; `solid:0` volume 14,644,823.306 mm³ and recorded area/bbox values. PMI regressions separately pin semantic-PMI extraction: 12 dimensions (8 valued), 6 tolerances, 3 datums, 9 presentation labels, 19 resolved/2 absent links, 7 gaps, `status=partial`, `complete=false`. |
| `nist-ctc-01-ap203` | `nist_ctc_01_asme1_rd_ap203.stp` (235,171 B) | Same NIST CTC 01 model, AP203 geometry only | Same model through a different export; volume differs from the AP242 row by ~0.014 %, which pins measurement sensitivity. |
| `nist-ftc-11-ap203` | `nist_ftc_11_asme1_rb_ap203.stp` (7,634 B) | NIST MBE PMI project, AP203 geometry only | Smallest NIST row; `solid:0` volume 5,129.386 mm³. |
| `nist-ftc-08-ap242e1-tessellated` | `nist_ftc_08_asme1_ap242-e1-tg.stp` (2,120,356 B) | NIST MBE PMI project, AP242 ed.1, tessellated geometry | Parses `ready`/`complete` with 1 solid. Area remains a fact; negative signed volume and void bounding boxes are rejected as four `MEASUREMENT_FAILED` gaps with diagnostics, not invalid facts or propagated OCCT exceptions. |
| `kicad-r0402-resistor` | `kicad_R_0402_1005Metric.step` (40,756 B) | KiCad `kicad-packages3D` official library (CC BY-SA 4.0) | `ready`/`complete`, mm/rad/sr, 1 solid; sub-millimetre extents (1.0 × 0.5 × 0.35 mm) exercise small-value measurement. |

All external rows declare length unit `mm`. The NIST rows declare angle unit
`DEGREE`; the P1 adapter only verifies length units, so this is recorded, not
treated as a failure.

### Generated variants (built in-test by existing fixture helpers, always tested)

| ID | Fixture | Expectation |
| --- | --- | --- |
| `malformed-step-skeleton` | inline minimal STEP skeleton | `read()` → `failed` snapshot, `PARSE_FAILED` diagnostic. |
| `malformed-step-bad-entity` | inline valid header + unknown entity | `read()` → `failed` snapshot, `PARSE_FAILED` diagnostic. |
| `generated-face-only-mm` | `write_face` | `NO_SOLIDS` diagnostic, discovery `unknown`, 0 entities. |
| `generated-box-cm` | `write_box` CM | `ready`, cm, volume 24,000 mm³ with factor 1000, height 40 mm with factor 10. |
| `generated-box-inch` | `write_box` INCH | `ready`, in, volume 32,774.128 mm³ with factor 16,387.064; 1 inch ≠ 1 mm. |
| `generated-box-metre` | `write_box` M | `partial`, `UNIT_UNKNOWN` diagnostic, entities preserved, length facts blocked as `UNKNOWN_UNIT` gaps. |

Semantic-PMI generated variants are produced by `tests/pmi_helpers.py` and covered by
`tests/test_pmi_synthetic.py`: millimetre deviation/limit/angular dimensions,
datum-referenced position plus an unsupported datum system, and centimetre/inch conversions of
nominal values, dimension tolerances and geometric-tolerance magnitudes. They are self-written and
self-read regression fixtures, not external-corpus or exporter-interoperability evidence.

## Obtaining the external corpus

`test-data/external/` is created empty. To populate it:

1. Download the NIST MBE PMI STEP archive from
   <https://www.nist.gov/document/nist-pmi-step-files> (the document link
   serves `NIST-PMI-STEP-Files.zip`, ~14 MB at retrieval time; the member
   layout is described in the archive `README.txt`). Extract exactly these
   members and rename as follows:
   - `NIST-PMI-STEP-Files/nist_ctc_01_asme1_ap242-e1.stp` → `nist_ctc_01_asme1_ap242-e1.stp`
   - `NIST-PMI-STEP-Files/AP203 geometry only/nist_ctc_01_asme1_rd.stp` → `nist_ctc_01_asme1_rd_ap203.stp`
   - `NIST-PMI-STEP-Files/AP203 geometry only/nist_ftc_11_asme1_rb.stp` → `nist_ftc_11_asme1_rb_ap203.stp`
   - `NIST-PMI-STEP-Files/nist_ftc_08_asme1_ap242-e1-tg.stp` → `nist_ftc_08_asme1_ap242-e1-tg.stp`
2. Download the KiCad model from
   <https://cdn.jsdelivr.net/gh/KiCad/kicad-packages3D@master/Resistor_SMD.3dshapes/R_0402_1005Metric.step>
   (upstream repository <https://github.com/KiCad/kicad-packages3D>,
   CC BY-SA 4.0) and save it as `kicad_R_0402_1005Metric.step`.
3. The maintainer's private local manifest records the observed bytes and hashes. It is
   git-ignored and is not published; run the local integrity checks when it is present.

Provenance and licensing:

- NIST MBE PMI test cases are published by NIST for use without restrictions;
  the archive `README.txt` states the files were generated from the NIST
  CTC/FTC CAD models, that producer identity was removed, and that the files
  are **not** error-free reference files.
- KiCad library models are licensed CC BY-SA 4.0.
- The NIST archive was retrieved on 2026-11-14; local hashes pin the observed
  bytes regardless of later upstream changes.

## Handled failure boundaries and remaining limitations

These cases are pinned so behavior changes become visible manifest updates:

1. **Unknown or badly framed input is rejected before OCCT.** Earlier direct probes of
   `STEPControl_Reader.ReadFile` with DWG/plain/bare-prefix bytes crashed cadquery-ocp
   8.0.1.1.0. `read()` now dispatches recognized DWG/DXF to the drawing adapter and checks other
   formats plus complete STEP framing first: unknown formats return `failed` /
   `UNSUPPORTED_FORMAT`; incomplete STEP envelopes return `PARSE_FAILED`.
   Well-framed malformed entities also return `PARSE_FAILED`. This prevents those observed entry
   paths from reaching the native STEP parser; it is not a general native-code sandbox.
2. **Tessellated measurements fail independently.** NIST FTC 08 `_ap242-e1-tg` produces a negative
   signed volume and void bounding boxes. Extraction rejects negative/non-finite physical values
   and isolates OCCT exceptions per request: volume and all bbox predicates become
   `MEASUREMENT_FAILED` gaps with diagnostics, while area remains a measured fact.
3. **Real assembly counts either reconcile completely or stay observed.** One private large
   assembly exposes more XCAF definitions/occurrences than the source PRODUCT/NAUO records explain;
   its leaf quantities therefore stay `observed` and its BOM remains `complete=false`. A second
   private assembly exposes an occurrence mismatch and refuses multi-solid process input rather
   than selecting one solid. One private AP242 assembly reconciles completely and yields known
   quantities and a complete BOM under the profile. One private AP214 multi-root assembly reports a
   PRODUCT-versus-XCAF definition mismatch and keeps its rows `observed`. `complete=true` is
   completeness under this profile, not an ERP or manufacturing-BOM claim.
4. **Multi-root single-part reads are explicit.** One private AP214 assembly declares two roots;
   the flattened single-part profile transfers one and reports `ROOTS_PARTIAL` with both counts.
   Assembly scope preserves the discovered solids and does not reuse the single-part flattened
   structural claim.
5. **Semantic PMI extraction is bounded.** The NIST AP242 CTC-01 row pins the XCAF GD&T projection,
   but four declared dimensions have no usable nominal value, datums B and C have no linked datum
   feature in the projection, tolerance deviations lose their signs, and datum systems, datum
   targets and surface texture are unsupported. The result remains `partial`; see
   `docs/semantic-pmi.md`. This is not a general AP242 conformance or exporter-interoperability
   claim.
6. **DEGREE angle declarations pass through unverified.** Only length units
   gate geometry measurement in the current STEP extractor. Semantic-PMI angle units are decoded
   separately from the PMI representation context and do not change geometry facts.

## Private local manifest schema

`tests/corpus/manifest.json` is git-ignored and exists only in the maintainer's local checkout. It
is not packaged in the sdist or published in the repository.

- `manifest_version` — currently `1`.
- `entries[]` — one object per corpus row:
  - `id`, `category` (`local-real`, `local-negative-unsupported`,
    `external-nist-pmi`, `external-kicad`, `malformed-step`,
    `generated-variant`).
  - `path` — repo-relative file, or `null` for inline/generated rows.
  - `source` — `origin` (human provenance), `url`, `license`,
    `retrieved_utc`, optional `archive`/`upstream`/`notes`.
  - `bytes` — pinned `size_bytes` + `sha256` (absent for generated rows).
  - `inline_content` — literal file bytes for malformed rows.
  - `generation` — `helper` + `args` for rows built by `tests/step_helpers.py`.
  - `expected` — `format`, `snapshot` (`status`, `entity_discovery`, `units`,
    `entity_count`, `diagnostics`, optional `parse_options`), optional
    `facts_solid_0` (number or a `MEASUREMENT_FAILED` gap expectation), optional
    `cli_inspect_limit_3` / `cli_inspect_assembly_summary` /
    `assembly_reconciliation` / `cli_bom` / `cli_pmi_assembly` /
    `cli_review_assembly`, and free-text `notes`.

Per-row tolerances are recorded in the private manifest. Public analytic and external fixtures use
the tolerances documented by their own tests; private production measurements are not published.

## Known gaps

- **CAx-IF benchmark files** (e.g. the AS1/AS2 assemblies) were not obtained:
  the classic suite files are not reliably reachable without registration, so
  no AS1 row exists. The private local assembly rows are each single-file evidence
  from their producer; none is an independently reconciled public benchmark.
- **Exporter diversity is still thin.** Five downloadable third-party STEP files
  from two producers plus private user-supplied assemblies form a smoke corpus, not an
  interoperability study. Only one private AP242 assembly produced a complete real-file BOM under
  the implemented profile.
- **DWG parsing depends on external ODA availability.** The private DWG rows pin the deterministic
  `ADAPTER_UNAVAILABLE` contract using an explicit nonexistent converter path; they do not parse the
  real drawings and never discover an installed converter implicitly. Local DXF fixtures pin the
  implemented ezdxf drawing behavior. A separate one-off local run with ODA File Converter 27.10.0.0
  converted three private DWGs and matched the user-converted DXFs structurally; see
  `docs/real-drawings.md`. That observation is not part of the automated public suite.
- **Unit variants are mostly generated**: mm/cm/in/m rows come from the existing
  analytic fixtures, and generated AP242 PMI fixtures add mm/cm/in and rad.
  The private user-supplied assemblies additionally exercise centimetre normalization on real
  files, but the downloadable corpus remains millimetre-only.
- **Semantic-PMI external coverage remains one positive file.** NIST CTC-01 is
  the only public corpus file with declared semantic PMI. The private AP242 and AP214 assemblies
  contain zero semantic-PMI entities and are negative controls only; the generated AP242 fixtures
  are regression coverage, not external validation. None of these extends positive AP242 PMI or
  exporter-interoperability evidence.
- **Full-model measurement sweeps** for large private assemblies are local observations only. The
  public regression inventory intentionally measures bounded selections to keep the suite fast.
