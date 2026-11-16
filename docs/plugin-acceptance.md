# Plugin acceptance record

Date: 2026-11-15. All inputs were public analytic examples; no production design, ODA, text-to-cad
source execution, software download or external report publication was involved.

## Installed CLI and skill: passed

The local CLI was refreshed with:

```bash
uv tool install --force --python 3.13 .
```

`facts doctor --check` returned `status=ready`, `ok=true` on Python 3.13.13. An earlier refresh that
reused Python 3.14.4 correctly failed `PYTHON_VERSION_UNSUPPORTED`; the explicit interpreter fixed
the installation rather than weakening the check.

The same-version local plugin was deliberately reinstalled from current sources in user scope. A
fresh Claude Code session **without** `--plugin-dir` invoked `/cad-to-facts` and the installed
`facts process-input examples/box.step --context examples/machining-context.json`. Observed:

- `complete=true`, one fully measured solid;
- required missing inputs 0, optional missing inputs 3;
- volume 6000 mm³, area 2200 mm², X/Y/Z extents 10/20/30 mm;
- `declared_material`, `semantic_pmi` and `validated_features` remained optional unsupported gaps;
- at the time of this run, the response stated that semantic PMI was not implemented. This record
  predates the bounded `facts pmi` slice and does not exercise it; current limits are documented in
  [`semantic-pmi.md`](semantic-pmi.md).

A separate fresh current-source session also ran doctor successfully. The session emitted an
`unrecognized_model` warning for the locally selected model name but completed the CLI/skill task;
this warning is not claimed as a model-compatibility validation.

## Sandboxed plugin eval: environment-blocked, not passed

The `evals/step-facts/` suite was run locally with `--no-publish` and no scaffold. The default
with/without ablation launched two arms. Both returned score 0 with an execution error **before the
skill/CLI case could run**:

```text
A shell tool (Bash or PowerShell) was granted but this machine cannot confine it
Sandbox required but unavailable: Windows sandbox is not active on this session (feature gate off)
```

This is an environment refusal, not a passing eval and not evidence that the engineering assertions
failed. No sandbox check was disabled or bypassed. The local HTML/JSON report stayed under the
ignored `evals/results/` directory, and the two failed-run temporary directories were removed after
inspection.

The release command in `docs/release.md` uses `--ablation none` to avoid unnecessary baseline cost.
Rerun the suite on Linux/macOS with a working sandbox backend, or Windows with its sandbox feature
active, before recording a plugin-eval pass. The successful direct installed-skill acceptance above
is a separate result and does not convert the blocked eval into a pass.

## Direct local model-question workflow comparison

On 2026-11-16, three public analytic behavior cases compared the revised `cad-to-facts` skill with
its pre-revision snapshot. Each case ran once per configuration through direct local agents, with
`examples/question-assembly.step` as the only design input. Outputs, grader results, timings and the
static review viewer stayed under the ignored `evals/results/model-questions-workspace/` directory.
No report was published, and the orchestrator did not install or update software. The cases prohibited
production designs, ODA, text-to-cad, network and source execution; available artifacts contain no
evidence of those actions, subject to the transcript limitation below.

These are direct agent behavior evaluations, not a successful Windows sandbox plugin-eval run.
Machine-generated CLI reports and a deterministic SVG/manifest checker support the grades, but full
execution transcripts and executor metrics were not retained. Process claims that cannot be checked
from those artifacts remain unverified. One run per configuration also means the comparison has no
variance estimate or statistical-significance claim.

The PATH-installed `facts` was stale during this comparison and lacked the new question commands.
Successful current-source runs used `uv run --no-sync facts`; one old-skill orientation run instead
fell back to older read-only commands. This CLI-version/environment difference is a confound, so not
every behavioral or timing difference can be attributed to the revised skill prose. It does not
convert a heuristic prediction into actually executed per-target orientation evidence.

Independent graders inspected the saved machine artifacts and applied the same assertions to both
configurations:

| Case | Revised skill | Old snapshot | Revised time / tokens | Old time / tokens |
| --- | --- | --- | --- | --- |
| Compound evidence separation | 5/5 | 3/5 | 393.767 s / 40,790 | 1,237.770 s / 60,601 |
| Conditional per-target orientations | 4/4 | 3/4 | 399.004 s / 38,760 | 1,982.072 s / 60,817 |
| Assumed-left-door SVG handoff | 7/7 | 7/7 | 424.864 s / 35,167 | 351.017 s / 38,312 |

The old compound run used a candidate count where a known Occurrence count and a separate strict
unknown window total were required. The old orientation run gave correct conditional directions by
manual derivation but did not execute the unavailable per-target orientation commands. The revised
run preserved those evidence states and executed both exact-target orientation reports. Both view
runs passed all seven graded assertions and all eight deterministic output checks; this case is a
useful regression check but does not discriminate the skill versions.

Across the three single-run cases, mean assertion pass rate was 100% for the revised skill and 78.3%
for the old snapshot. Mean execution time was 405.9 s versus 1,190.3 s and mean reported token usage
was 38,239 versus 53,243. These figures describe these runs only: the stale-CLI confound, lack of
repetition, and much faster old-skill view run preclude a general productivity or causal claim.
