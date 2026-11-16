# Installation and setup

The Python CLI and Claude Code plugin are separate installations. The plugin invokes the CLI; it
does not embed OCCT, ezdxf, text-to-cad or ODA.

## Reference checkout

Prerequisites: `uv` and a local checkout of this repository. The lockfile selects Python 3.13 and
the reference dependency versions. Initial setup may download Python/packages; normal parsing,
review, BOM, process-input, doctor and change verification are offline.

```bash
git clone https://github.com/EthanLoveQueen/cad-to-facts.git
cd cad-to-facts
```

From the repository root:

```bash
uv sync --locked
uv run facts doctor --check
uv run facts inspect examples/change-loop/baseline/box.step --limit 1
uv run pytest
```

A successful doctor result has `status=ready` and `ok=true`. `oda=not_checked` is normal for
STEP/DXF-only use. If `facts` is not on PATH, `cli_on_path` may be a warning; `uv run` remains a
supported invocation.

## Isolated CLI on PATH

```bash
uv tool install --python 3.13 .
facts doctor --check
```

Or install directly from GitHub:

```bash
uv tool install --python 3.13 "git+https://github.com/EthanLoveQueen/cad-to-facts.git"
facts doctor --check
```

To refresh an existing local tool after changing the checkout:

```bash
uv tool install --force --python 3.13 .
facts doctor --check
```

The explicit `--python 3.13` is required for a reproducible supported interpreter, especially when
refreshing an existing tool environment. `uv tool install` resolves the package requirements into an
isolated tool environment; it is not a replay of every transitive pin in `uv.lock`. Use
`uv sync --locked` plus `uv run` when the exact locked reference environment is required, and run
doctor after either installation path.

Ensure uv's tool bin directory is on PATH. Otherwise use this from any directory without modifying
the global Python environment:

```bash
uv run --project /path/to/cad-to-facts facts doctor --check
```

Do not install the package into an unrelated Python 3.14/global environment: the reference runtime
is Python `>=3.13,<3.14`, with `cadquery-ocp==8.0.1.1.0` and `ezdxf==1.4.5`.

## Claude Code plugin

For one session using the current checkout:

```bash
claude --plugin-dir .
```

Or register the local marketplace and install for the user:

```bash
claude plugin marketplace add .
claude plugin install cad-to-facts@cad-to-facts --scope user
claude plugin validate .claude-plugin/marketplace.json
```

Or install the plugin directly from GitHub:

```bash
claude plugin marketplace add EthanLoveQueen/cad-to-facts
claude plugin install cad-to-facts@cad-to-facts --scope user
```

After a versioned update, refresh the local marketplace/plugin as needed and restart Claude Code:

```bash
claude plugin update cad-to-facts@cad-to-facts --scope user
```

`update` can report an unchanged version as `up_to_date`; during same-version development use
`claude --plugin-dir .` or deliberately reinstall the local plugin to refresh its copied sources.

Then invoke `/cad-to-facts`. Install/test the CLI separately first. The skill's repository root is
the directory containing `pyproject.toml`; when loaded from an installed plugin it is two levels
above `skills/cad-to-facts/`.

## Optional DWG support

DXF needs no external converter. DWG requires a separately installed ODA File Converter and an
explicit executable path every time:

```bash
facts inspect drawing.dwg --oda-path "/explicit/path/to/ODAFileConverter"
facts doctor --check --oda-path "/explicit/path/to/ODAFileConverter"
```

Doctor only checks and hashes that file; it does not execute a trial conversion. Neither command
searches PATH or default install locations. ODA is proprietary and is not bundled, downloaded or
auto-installed. The user is responsible for the applicable license, including ODA's non-member
restrictions.

The [official ODA converter page](https://www.opendesign.com/guestfiles/oda_file_converter) also
lists Linux x64 RPM/DEB/AppImage packages. A user-supplied, locally built Linux container is
technically feasible, but this repository does not currently ship a Docker image or bundle ODA.
Publicly redistributing an ODA-containing image requires separate license confirmation; an official
download link is not redistribution permission.

## text-to-cad

The change commands do not execute CAD. Source-backed execution uses a separately installed
text-to-cad skill/runtime and explicit approval/isolation. Do not add text-to-cad to this package's
Python dependencies. The public offline replay in `examples/change-loop/` does not require a
text-to-cad installation.

## What setup does not validate

Doctor checks the runtime, not exporter interoperability, full AP242 semantic-PMI coverage, feature
recognition, ODA conversion fidelity, manufacturing correctness or production readiness. The
analytic fixtures and recorded change example establish their declared regressions only. See
`docs/recovery.md` when a check or artifact diagnostic fails.
