import json
import subprocess
import sys


def _write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def test_cli_file_health_keeps_occt_logs_out_of_json_stdout(tmp_path):
    step_path = tmp_path / "broken.step"
    step_path.write_text("ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n", encoding="ascii")
    _write_json(
        tmp_path / "requirements.json",
        {"requirements": [{"requirement_id": "req-readable", "text": "File must be readable", "source_ref": "inline#readable"}]},
    )
    _write_json(
        tmp_path / "rules.json",
        {
            "version": "1",
            "rules": [
                {
                    "rule_id": "file-readable",
                    "version": "1",
                    "requirement_refs": ["req-readable"],
                    "subject_selector": {"entity_kind": "snapshot"},
                    "inputs": [],
                    "checker": "snapshot.status",
                    "parameters": {"equals": "ready"},
                    "severity": "error",
                    "source": {"reviewed_by": "test"},
                }
            ],
        },
    )
    _write_json(
        tmp_path / "scope.json",
        {
            "included_rules": ["file-readable"],
            "subject_selectors": [{"entity_kind": "snapshot"}],
            "required_inputs": [],
            "discovery_requirements": [],
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
    assert report["overall_status"] == "non_compliant"
    assert report["findings"][0]["status"] == "violated"
    assert report["diagnostics"][0]["code"] == "PARSE_FAILED"
