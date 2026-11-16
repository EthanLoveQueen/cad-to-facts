# Contributing

## Environment

- Python 3.13 and `uv`.
- Install and verify from a clean checkout:

```bash
uv sync --locked
uv run facts doctor --check
uv run pytest
uv build
uv run python scripts/check_dist.py dist
```

## Project boundaries

- Keep the deterministic core offline. Parsing, measurement, rule evaluation, BOM extraction and
  change verification must not require AI or network access.
- Do not add ERP/PLM/PDM/MES/CAPP connectors, template rendering, tool/machine databases, operation
  sequencing or production release features.
- Never overwrite a source artifact. A modification creates a new artifact and must be verified
  afterward; reject stale base hashes.
- Do not promote candidates, assumptions, inferences or unvalidated recognitions to facts. Keep
  unknown, failed, unsupported and not-applicable states distinct.
- Keep README, skill and CLI claims synchronized with what is implemented. Label design-only
  behavior as design-only.
- Update `CHANGELOG.md` and the relevant document when behavior or contracts change.
- Self-written/self-read STEP fixtures do not establish exporter interoperability. Describe test
  evidence at that level.

## Private production data

`test-data/`, `tests/corpus/` and `tests/test_private_*.py` are intentionally git-ignored. They hold
user-supplied production files, hashes and measurements that are not redistributed and must not be
added to commits, issues or pull requests. Public tests use analytic OCCT/ezdxf fixtures and
optionally downloaded public NIST/KiCad files.

## Pull requests

- Add or update tests for behavior changes.
- Report the commands actually run and their outcomes. Do not claim an unrun CI job, review or
  external validation passed.
- Keep changes focused; unrelated refactors make evidence review harder.
