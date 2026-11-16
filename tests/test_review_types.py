import contextlib
import io
import json
from pathlib import Path

from cad_to_facts import cli

from step_helpers import write_box


ROOT = Path(__file__).resolve().parents[1]


def _run(arguments):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = cli.main(arguments)
    return exit_code, json.loads(output.getvalue())


def test_typed_rule_appears_in_findings_and_review_type_summary(tmp_path):
    path = tmp_path / "box.step"
    write_box(path)
    rules = json.loads((ROOT / "examples/rules.json").read_text(encoding="utf-8"))
    rules["rules"][0]["review_type"] = "design_process_rule"
    typed_rules = tmp_path / "typed-rules.json"
    typed_rules.write_text(json.dumps(rules), encoding="utf-8")

    exit_code, result = _run([
        "review", str(path),
        "--requirements", str(ROOT / "examples/requirements.json"),
        "--rules", str(typed_rules),
        "--scope", str(ROOT / "examples/review-scope.json"),
        "--context", str(ROOT / "examples/review-context.json"),
    ])

    assert exit_code == 0
    assert result["findings"][0]["review_type"] == "design_process_rule"
    assert result["review_type_summary"] == [{
        "review_type": "design_process_rule",
        "satisfied": 1,
        "violated": 0,
        "unknown": 0,
        "not_applicable": 0,
    }]


def test_legacy_untyped_rules_keep_null_typed_fields_and_existing_behavior(tmp_path):
    path = tmp_path / "box.step"
    write_box(path)

    exit_code, result = _run([
        "review", str(path),
        "--requirements", str(ROOT / "examples/requirements.json"),
        "--rules", str(ROOT / "examples/rules.json"),
        "--scope", str(ROOT / "examples/review-scope.json"),
        "--context", str(ROOT / "examples/review-context.json"),
    ])

    assert exit_code == 0
    assert result["findings"][0]["review_type"] is None
    assert result["review_type_summary"] is None


def test_shipped_file_health_rule_pack_runs_without_custom_authoring(tmp_path):
    path = tmp_path / "box.step"
    write_box(path)
    pack = ROOT / "rule-packs/step-file-health"

    exit_code, result = _run([
        "review", str(path),
        "--requirements", str(pack / "requirements.json"),
        "--rules", str(pack / "rules.json"),
        "--scope", str(pack / "scope.json"),
        "--context", str(pack / "context.json"),
    ])

    assert exit_code == 0
    assert result["overall_status"] == "compliant_for_scope"
    assert result["complete"] is True
    assert result["findings"][0]["review_type"] == "file_health"
    rules = json.loads((pack / "rules.json").read_text(encoding="utf-8"))
    assert all(rule["source"].get("validation_ref") for rule in rules["rules"])
    assert all(rule["source"].get("applies_to") for rule in rules["rules"])
