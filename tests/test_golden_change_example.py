import contextlib
import io
import json
from pathlib import Path
import shutil

from cad_to_facts import cli


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/change-loop"


def _arguments(replay_relocated_output=False):
    arguments = [
        "verify-change",
        "--request", str(EXAMPLE / "recorded/change-request.json"),
        "--plan", str(EXAMPLE / "recorded/change-plan.json"),
        "--approval", str(EXAMPLE / "recorded/approval.json"),
        "--execution", str(EXAMPLE / "recorded/execution.json"),
        "--before-manifest", str(EXAMPLE / "baseline/manifest.json"),
        "--after-manifest", str(EXAMPLE / "modified/manifest.json"),
        "--origin-review", str(EXAMPLE / "baseline/review.json"),
        "--before", str(EXAMPLE / "baseline/box.step"),
        "--after", str(EXAMPLE / "modified/box.step"),
    ]
    if replay_relocated_output:
        arguments.append("--replay-relocated-output")
    return arguments


def _run(arguments):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = cli.main(arguments)
    return exit_code, json.loads(output.getvalue())


def test_golden_example_replays_only_with_explicit_output_relocation():
    exit_code, strict = _run(_arguments())
    assert exit_code == 0
    assert strict["verification_status"] == "failed"
    assert "input_identity:output-location:OUTPUT_LOCATION_MISMATCH" in strict["unresolved_issues"]

    exit_code, report = _run(_arguments(replay_relocated_output=True))
    assert exit_code == 0
    assert report["verification_status"] == "passed"
    assert report["execution_provenance"] == "attested"
    assert report["change_observed"] == "changed"
    assert report["manifest_validation"] == "passed"
    assert report["approval_validation"] == "passed"
    assert report["unresolved_issues"] == []
    location = next(check for check in report["checks"] if check["check_id"] == "output-location")
    assert location["status"] == "passed"
    assert "explicit relocated-output replay" in location["message"]


def test_relocated_replay_still_rejects_a_different_output_filename(tmp_path):
    renamed = tmp_path / "renamed.step"
    shutil.copyfile(EXAMPLE / "modified/box.step", renamed)
    arguments = _arguments(replay_relocated_output=True)
    arguments[arguments.index("--after") + 1] = str(renamed)

    exit_code, report = _run(arguments)

    assert exit_code == 0
    assert report["verification_status"] == "failed"
    assert "input_identity:output-location:OUTPUT_LOCATION_MISMATCH" in report["unresolved_issues"]
