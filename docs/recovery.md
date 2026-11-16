# Recovery playbook

Start with machine-readable evidence rather than retrying blindly:

```bash
uv run facts doctor --check
```

Doctor exits 0 for a usable required environment, 1 for a failed required check, 2 for invalid
command input and 3 for an unexpected internal error. It does not parse a design artifact. An ODA
path is checked only when explicitly supplied.

## Doctor codes

| Code | Meaning | Safe next action |
| --- | --- | --- |
| `PYTHON_VERSION_UNSUPPORTED` | Active runtime is not Python 3.13. | Use `uv sync --locked` and invoke through `uv run`; for an installed tool, refresh with `uv tool install --force --python 3.13 .`. Do not mix a global 3.14 environment. |
| `DEPENDENCY_NOT_INSTALLED` | A required distribution is absent. | Run `uv sync --locked` in a clean checkout; then rerun doctor. |
| `DEPENDENCY_VERSION_MISMATCH` | Active dependency differs from the reference contract. | Restore `uv.lock` versions with `uv sync --locked`; do not edit the lockfile merely to silence the check. |
| `DEPENDENCY_IMPORT_FAILED` | Package metadata exists but native/module import fails. | Preserve the error, recreate the isolated environment from the lockfile, and check platform/native-library compatibility. Do not suppress the import error. |
| `TEMPORARY_DIRECTORY_UNWRITABLE` | The process cannot create/write a private temporary directory. | Select a user-writable local temp directory through the normal OS environment, then rerun doctor. Do not loosen source-directory permissions. |
| `CLI_NOT_ON_PATH` | Optional PATH warning. | Use `uv run --project /path/to/cad-to-facts facts ...`, install with `uv tool install --python 3.13 .`, or configure uv's tool bin directory on PATH. |
| `ODA_NOT_CONFIGURED` | Informational; no ODA path was supplied. | No action for STEP/DXF. For DWG, install/license ODA separately and pass its exact executable path. |
| `ODA_PATH_NOT_FILE` | Explicit ODA path is absent or not a regular file. | Correct `--oda-path`; no fallback search exists. |
| `ODA_PATH_UNREADABLE` | Explicit ODA file cannot be read/hashed. | Fix user-level read access or supply the correct local file. Do not run an unknown executable as an elevated user. |

A passed ODA doctor check means only that the explicit file exists and could be hashed. It does not
prove that the converter runs, that its license permits the intended use, or that DWG/DXF conversion
is visually or semantically equivalent.

## CLI and parse failures

| Symptom | Recovery |
| --- | --- |
| Exit 2, `configuration_or_input` | Fix malformed JSON, missing flags/keys, unsupported options or stale content identities. These are not transient errors. |
| Exit 3 or `tool_error=true` | Preserve stdout JSON and the failing input; treat it as an internal/checker failure, not a violated engineering rule. |
| `PARSE_FAILED` / failed snapshot | Do not use extracted values as complete facts. File-health review can still produce findings from the failed snapshot. |
| `UNKNOWN_UNIT` / unitless drawing | Supply an artifact with an explicit supported declaration or keep the gap. Never default unitless geometry to mm. |
| `ADAPTER_UNAVAILABLE` for DWG | Pass `--oda-path` explicitly, or have the user convert locally to DXF and inspect that derivative. ODA is never auto-discovered or auto-installed. |
| `CONVERSION_FAILED` | Check the explicit converter path and local ODA installation/license, then retry in a new temp run. A manual user-produced DXF remains a separate derivative, not proof of equivalent conversion. |
| `ASSEMBLY_STRUCTURE_NOT_REPRESENTED` | Re-read STEP with `--read-scope assembly`; flattened solids are not an assembly tree. |
| Render output already exists | Choose a new SVG path. Existing artifacts are never overwritten. |
| XREF outside-root/cycle/budget failure | Keep it unresolved or explicitly supply the correct local roots/budgets. Do not widen roots to the whole filesystem or fetch network references. |

## Review and rule packs

A `non_compliant` or `incomplete` report is normally a valid result with exit 0. Do not "repair" it
by editing JSON. Change the actual artifact, requirement, rule, scope or context as appropriate and
rerun so new content identities are derived.

- `unknown` is not `violated`; missing/unsupported/uncomputed inputs stay unknown unless a required
  presence rule has a proven `ABSENT` gap.
- Partial discovery cannot yield 100% true coverage or `compliant_for_scope`.
- The file-health pack checks readiness only. A failed readiness finding does not identify a design
  defect, and a passed one does not certify engineering correctness.
- Legacy typed fields serialized as null are expected; do not backfill old bound reports merely to
  populate `review_type`.

## ProcessCardInput

- `PROCESS_SINGLE_PART_REQUIRED`: use an actual single-solid STEP artifact. The command will not
  select one solid from a multi-solid file.
- Required context `ABSENT`: provide explicit local `{"values": {...}}`; values remain
  `user_supplied`.
- Required design input `UNSUPPORTED`: declared material, PMI projection and validated features are
  not implemented. Semantic PMI can be extracted separately with `facts pmi`, but it is not
  projected into ProcessCardInput; remove the requirement only if the downstream task explicitly
  accepts the geometry/context-only profile, otherwise keep the work product incomplete.
- Planning context rejected with exit 2: remove operation/setup/tool/machine/cutting/cycle-time
  decisions. They belong to engineers or external systems, not renamed free-form context.

## Change verification and archived evidence

- `OUTPUT_LOCATION_MISMATCH`: during a live change, produce the artifact at the approved declared
  location or prepare and approve a new request. Do not bypass it with replay flags.
- `--replay-relocated-output` is only for archived evidence such as `examples/change-loop/`. It
  accepts the same filename at a new directory and explicitly discloses that the recorded absolute
  directory was not revalidated. It never rewrites bound records.
- Stale artifact/manifest/content hashes: return to the actual original bytes and regenerate derived
  work products. Do not hand-edit hashes, approvals or execution records.
- Source/manifest/plan disagreement: inspect the real source differences. A changed request or plan
  requires a new approval; never backdate or fabricate an ExecutionRecord.
- `verification_status=passed` with `execution_provenance=unattested` is valid output verification,
  not proof the approved plan ran.
- Missing after artifact or unmatched required entity: keep verification incomplete/failed as
  reported; do not convert missing evidence into success.

For the complete known-good recovery baseline, run the offline command in
`examples/change-loop/README.md`; expected states are `passed / attested / changed` under its
explicit archived-relocation policy.
