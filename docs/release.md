# Release and acceptance checklist

This repository has build/release tooling, but this document does not claim that a public release,
package upload, marketplace publication, container publication or signed engineering release has
occurred. No repository/support URL is invented here.

## 1. Synchronize versions and claims

Keep these versions aligned when making a release:

- `pyproject.toml`;
- `src/cad_to_facts/__init__.py`;
- `.claude-plugin/plugin.json`;
- `.claude-plugin/marketplace.json`.

Update `CHANGELOG.md`, README/skill command claims, detailed contracts and rule-pack validation
references together. The bounded `facts pmi` profile may be described as implemented only within its
documented XCAF/GD&T subset; it must not be promoted to full AP242 conformance or a general exporter
claim. Bounded feature candidates/through-hole validation and assumed orientation must retain their
limits; general feature recognition, persistent cross-revision identity, general exporter
interoperability and manufacturing certification must not be promoted to implemented status.
Bounded drawing questions must remain an explicit-spec profile over declared/measured drawing facts;
general drawing semantic understanding, title-block inference, functional feature validation,
dimension-to-geometry association and drawing natural-language grammar must not be promoted. Semantic
evidence must remain declared block/layer/text/attribute context, never an inferred material, part or
function field.

## 2. Run deterministic preflight

From a clean checkout:

```bash
uv sync --locked
uv run facts doctor --check
uv run pytest
uv build
uv run python scripts/check_dist.py dist
claude plugin validate .claude-plugin/marketplace.json
```

`scripts/check_dist.py` inspects archives without extracting or executing them. It requires the
public examples, rule pack, eval sources, docs and lockfile in the sdist, requires the CLI in the
wheel, rejects `test-data/` and `tests/`, and rejects viewer-token query strings in the packaged
change example. The wheel remains the Python package; plugin/rule-pack/example sources are
distributed through the source/plugin package, not assumed to be inside the wheel.

`.github/workflows/ci.yml` runs the locked install, doctor, tests, build and archive checks on
Linux, Windows and macOS. A workflow file being present is not evidence that a remote CI run has
passed; record the actual run result when a repository is hosted.

## 3. Run the public offline acceptance paths

```bash
uv run pytest tests/test_golden_change_example.py tests/test_process_input.py tests/test_review_types.py
uv run pytest tests/test_drawing_question_example.py
```

Follow `examples/change-loop/README.md` for the full recorded run. Expected states are
`verification_status=passed`, `execution_provenance=attested` and `change_observed=changed` under
the explicit archived-relocation option. This remains test-harness evidence. The drawing question
example runs the public analytic `examples/question-drawing.dxf` with
`examples/drawing-question.json`; it creates no external artifact and does not modify the DXF.

## 4. Run plugin eval locally without publication

The `evals/step-facts/` case uses only the public analytic STEP and the installed `facts` CLI. It
uses model-backed judging and can incur model cost. It does not need user production files, ODA,
text-to-cad or source execution.

```bash
claude plugin eval . \
  --case step-facts \
  --ablation none \
  --runs 1 \
  --no-publish \
  --no-scaffold \
  --trust-plugin \
  --allow-tools 'Bash(facts:*)' \
  --output-dir evals/results/local
```

The `evals/model-question-*` cases use the public analytic `examples/question-assembly.step` to test
compound-question decomposition, conditional orientation alternatives, and the assumed-left-door SVG
handoff. Run each separately with the same local/no-publication boundary:

```bash
claude plugin eval . --case model-question-compound --ablation none --runs 1 \
  --no-publish --no-scaffold --trust-plugin --allow-tools 'Bash(facts:*)' \
  --output-dir evals/results/local
claude plugin eval . --case model-question-alternatives --ablation none --runs 1 \
  --no-publish --no-scaffold --trust-plugin --allow-tools 'Bash(facts:*)' \
  --output-dir evals/results/local
claude plugin eval . --case model-question-view --ablation none --runs 1 \
  --no-publish --no-scaffold --trust-plugin --allow-tools 'Bash(facts:*)' \
  --output-dir evals/results/local
```

These are model-backed behavior evaluations and can incur model cost. They test how the agent uses
evidence; the analytic fixture does not establish exporter interoperability. The view case creates a
new SVG/manifest pair in its isolated work directory.

Use `--trust-plugin` only for this reviewed local suite; it does not grant scaffold execution or
unrestricted shell access. Keep `--no-publish`: publishing an eval report to an external service is
a separate action requiring explicit authorization. `evals/results/` is ignored and must not be
packaged as release evidence without review.

The shell-granted eval requires a working Claude Code sandbox backend. On Windows, if the sandbox
feature is unavailable/inactive, the runner refuses the case before skill execution. Do not disable
sandbox enforcement to force a pass; rerun on supported Linux/macOS or a Windows session with the
sandbox active, and record the environment failure honestly. A no-plugin ablation is optional and
adds cost, so the acceptance command above uses `--ablation none`. See
`docs/plugin-acceptance.md` for the 2026-11-15 installed-skill pass and the separate Windows
sandbox-blocked eval result.

## 5. Review publication boundaries

Before any separately authorized release:

- Inspect the actual sdist/wheel lists and hashes; never add `test-data/` production designs or the
  test suite to the sdist.
- Keep raw text-to-cad viewer tokens/logs out. The public change logs are sanitized supplements,
  not ExecutionRecord replacements.
- Do not bundle or publish ODA binaries, ODA-containing Docker images, auto-installers or default
  install-path discovery. Linux packages do not remove licensing/redistribution constraints.
- Do not upload user design files or publish eval HTML/JSON externally without approval.
- Do not execute source scripts as part of build, CI, doctor or release checks.
- Do not fabricate attestations, approvals, remote CI results, download counts, signatures or
  support/repository URLs.

Package uploads, git tags/pushes, marketplace publication and production release are separate
outward-facing actions, not performed by this checklist.
