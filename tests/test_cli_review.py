import json
import subprocess
import sys

from step_helpers import write_assembly, write_box


def _write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def test_cli_review_outputs_machine_readable_compliant_report(tmp_path):
    step_path = tmp_path / "box.step"
    write_box(step_path)
    _write_json(
        tmp_path / "requirements.json",
        {
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
        {
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
        {
            "included_rules": ["max-height"],
            "subject_selectors": [{"entity_kind": "solid"}],
            "required_inputs": [],
            "discovery_requirements": ["solid"],
        },
    )
    _write_json(tmp_path / "context.json", {"values": {}})

    result = subprocess.run(
        [
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
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["overall_status"] == "compliant_for_scope"
    assert report["complete"] is True
    assert report["findings"][0]["status"] == "satisfied"
    assert report["findings"][0]["facts"][0]["value"] == 30.0
    assert report["coverage"]["entity_coverage"] == 1.0


def _versioned_fixture(tmp_path, included_rules):
    step_path = tmp_path / "box.step"
    write_box(step_path)
    _write_json(
        tmp_path / "requirements.json",
        {
            "requirements": [
                {
                    "requirement_id": "req-height",
                    "text": "Overall height must not exceed the limit",
                    "source_ref": "requirements.json#req-height",
                }
            ]
        },
    )

    def rule(version, threshold):
        return {
            "rule_id": "max-height",
            "version": version,
            "requirement_refs": ["req-height"],
            "subject_selector": {"entity_kind": "solid"},
            "inputs": [{"name": "height", "predicate": "bbox.extent.z"}],
            "checker": "numeric.compare",
            "parameters": {
                "operator": "<=",
                "threshold": threshold,
                "unit": "mm",
                "abs_tol": 1e-7,
            },
            "severity": "error",
            "source": {"reviewed_by": "test"},
        }

    _write_json(
        tmp_path / "rules.json",
        {"version": "1", "rules": [rule("1", 20.0), rule("2", 40.0)]},
    )
    _write_json(
        tmp_path / "scope.json",
        {
            "included_rules": included_rules,
            "subject_selectors": [{"entity_kind": "solid"}],
            "required_inputs": [],
            "discovery_requirements": ["solid"],
        },
    )
    _write_json(tmp_path / "context.json", {"values": {}})
    return step_path


def _run_review(tmp_path, step_path, read_scope=None):
    command = [
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
    if read_scope is not None:
        command.extend(["--read-scope", read_scope])
    return subprocess.run(command, capture_output=True, text=True, check=False)


def test_cli_selects_the_explicit_rule_version(tmp_path):
    step_path = _versioned_fixture(
        tmp_path, [{"rule_id": "max-height", "version": "2"}]
    )

    result = _run_review(tmp_path, step_path)

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["findings"][0]["rule_version"] == "2"
    assert report["findings"][0]["status"] == "satisfied"
    assert report["overall_status"] == "compliant_for_scope"


def test_cli_rejects_ambiguous_versionless_rule_reference(tmp_path):
    step_path = _versioned_fixture(tmp_path, ["max-height"])

    result = _run_review(tmp_path, step_path)

    assert result.returncode == 2
    error = json.loads(result.stdout)
    assert error["error"]["category"] == "configuration_or_input"
    assert "multiple versions; specify a version" in error["error"]["message"]


def test_cli_unsupported_scope_required_input_keeps_report_incomplete(tmp_path):
    step_path = _versioned_fixture(
        tmp_path, [{"rule_id": "max-height", "version": "2"}]
    )
    _write_json(
        tmp_path / "scope.json",
        {
            "included_rules": [{"rule_id": "max-height", "version": "2"}],
            "subject_selectors": [{"entity_kind": "solid"}],
            "required_inputs": [
                {"name": "mass", "predicate": "mass", "subject_id": "solid:0"}
            ],
            "discovery_requirements": ["solid"],
        },
    )

    result = _run_review(tmp_path, step_path)

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["findings"][0]["status"] == "satisfied"
    assert report["complete"] is False
    assert report["overall_status"] == "incomplete"
    assert [diagnostic["code"] for diagnostic in report["diagnostics"]] == [
        "SCOPE_INPUT_UNRESOLVED"
    ]
    assert report["coverage"]["fully_inspected_entities"] == 0


def test_cli_review_can_use_explicit_assembly_profile(tmp_path):
    step_path = _versioned_fixture(
        tmp_path, [{"rule_id": "max-height", "version": "2"}]
    )
    write_assembly(step_path)

    flattened = _run_review(tmp_path, step_path)
    represented = _run_review(tmp_path, step_path, "assembly")

    flattened_report = json.loads(flattened.stdout)
    assert flattened.returncode == 0
    assert flattened_report["complete"] is False
    assert flattened_report["diagnostics"][0]["code"] == (
        "ASSEMBLY_STRUCTURE_NOT_REPRESENTED"
    )
    assert represented.returncode == 0, represented.stderr
    represented_report = json.loads(represented.stdout)
    assert represented_report["complete"] is True
    assert represented_report["overall_status"] == "compliant_for_scope"
    assert len(represented_report["findings"]) == 2
    assert all(
        finding["status"] == "satisfied"
        for finding in represented_report["findings"]
    )
