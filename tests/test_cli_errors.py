import json
import subprocess
import sys

from step_helpers import write_box


def _write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def _contract_files(tmp_path, *, rules=None, requirements=None, scope=None):
    step_path = tmp_path / "box.step"
    write_box(step_path)
    _write_json(
        tmp_path / "requirements.json",
        requirements
        if requirements is not None
        else {
            "requirements": [
                {
                    "requirement_id": "req-height",
                    "text": "Overall height must not exceed 30 mm",
                    "source_ref": "requirements.json#req-height",
                }
            ]
        },
    )
    _write_json(
        tmp_path / "rules.json",
        rules
        if rules is not None
        else {
            "version": "1",
            "rules": [
                {
                    "rule_id": "max-height",
                    "version": "1",
                    "requirement_refs": ["req-height"],
                    "subject_selector": {"entity_kind": "solid"},
                    "inputs": [{"name": "height", "predicate": "bbox.extent.z"}],
                    "checker": "numeric.compare",
                    "parameters": {"operator": "<=", "threshold": 30.0, "unit": "mm", "abs_tol": 1e-7},
                    "severity": "error",
                    "source": {"reviewed_by": "test"},
                }
            ],
        },
    )
    _write_json(
        tmp_path / "scope.json",
        scope
        if scope is not None
        else {
            "included_rules": ["max-height"],
            "subject_selectors": [{"entity_kind": "solid"}],
            "required_inputs": [],
            "discovery_requirements": ["solid"],
        },
    )
    _write_json(tmp_path / "context.json", {"values": {}})
    return [
        sys.executable,
        "-m",
        "cad_to_facts.cli",
        "review",
        str(step_path),
        "--requirements",
        str(tmp_path / "requirements.json"),
        "--rules",
        str(tmp_path / "rules.json"),
        "--scope",
        str(tmp_path / "scope.json"),
        "--context",
        str(tmp_path / "context.json"),
    ]


def _run(command):
    return subprocess.run(command, capture_output=True, text=True, check=False)


def _assert_configuration_error(result):
    assert result.returncode == 2, (result.stdout, result.stderr)
    error = json.loads(result.stdout)["error"]
    assert error["category"] == "configuration_or_input"
    assert error["message"]


def test_cli_missing_rule_parameter_is_a_configuration_error(tmp_path):
    rules = {
        "version": "1",
        "rules": [
            {
                "rule_id": "max-height",
                "version": "1",
                "requirement_refs": ["req-height"],
                "subject_selector": {"entity_kind": "solid"},
                "inputs": [{"name": "height", "predicate": "bbox.extent.z"}],
                "checker": "numeric.compare",
                "parameters": {"operator": "<=", "threshold": 30.0, "unit": "mm"},
                "severity": "error",
                "source": {"reviewed_by": "test"},
            }
        ],
    }

    _assert_configuration_error(_run(_contract_files(tmp_path, rules=rules)))


def test_cli_negative_tolerance_is_a_configuration_error(tmp_path):
    rules = {
        "version": "1",
        "rules": [
            {
                "rule_id": "max-height",
                "version": "1",
                "requirement_refs": ["req-height"],
                "subject_selector": {"entity_kind": "solid"},
                "inputs": [{"name": "height", "predicate": "bbox.extent.z"}],
                "checker": "numeric.compare",
                "parameters": {"operator": "<=", "threshold": 30.0, "unit": "mm", "abs_tol": -1.0},
                "severity": "error",
                "source": {"reviewed_by": "test"},
            }
        ],
    }

    _assert_configuration_error(_run(_contract_files(tmp_path, rules=rules)))


def test_cli_empty_requirements_is_a_configuration_error(tmp_path):
    _assert_configuration_error(_run(_contract_files(tmp_path, requirements={"requirements": []})))


def test_cli_requirements_file_must_be_an_object(tmp_path):
    requirements = [
        {
            "requirement_id": "req-height",
            "text": "Overall height must not exceed 30 mm",
            "source_ref": "requirements.json#req-height",
        }
    ]

    _assert_configuration_error(_run(_contract_files(tmp_path, requirements=requirements)))


def test_cli_unresolved_requirement_reference_is_a_configuration_error(tmp_path):
    rules = {
        "version": "1",
        "rules": [
            {
                "rule_id": "max-height",
                "version": "1",
                "requirement_refs": ["req-typo"],
                "subject_selector": {"entity_kind": "solid"},
                "inputs": [{"name": "height", "predicate": "bbox.extent.z"}],
                "checker": "numeric.compare",
                "parameters": {"operator": "<=", "threshold": 30.0, "unit": "mm", "abs_tol": 1e-7},
                "severity": "error",
                "source": {"reviewed_by": "test"},
            }
        ],
    }

    _assert_configuration_error(_run(_contract_files(tmp_path, rules=rules)))


def test_cli_unknown_included_rule_is_a_configuration_error(tmp_path):
    scope = {
        "included_rules": ["max-height", "typo-rule"],
        "subject_selectors": [{"entity_kind": "solid"}],
        "required_inputs": [],
        "discovery_requirements": ["solid"],
    }

    _assert_configuration_error(_run(_contract_files(tmp_path, scope=scope)))


def test_cli_argument_error_is_reported_as_json(tmp_path):
    result = _run([sys.executable, "-m", "cad_to_facts.cli"])

    _assert_configuration_error(result)


def test_cli_inspect_limit_reports_truncation_and_cursor(tmp_path):
    path = tmp_path / "box.step"
    write_box(path)

    result = _run([sys.executable, "-m", "cad_to_facts.cli", "inspect", str(path), "--limit", "0"])

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["selection"] == {
        "entity_total": 1,
        "entities_returned": 0,
        "truncated": True,
        "next_cursor": "solid:0",
    }
    assert output["factset"]["facts"] == []
