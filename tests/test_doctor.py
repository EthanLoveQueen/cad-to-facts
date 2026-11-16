import contextlib
import hashlib
import io
import json
import sys

from cad_to_facts import cli


def _run(arguments):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = cli.main(arguments)
    return exit_code, json.loads(output.getvalue())


def test_doctor_check_reports_ready_reference_environment():
    exit_code, report = _run(["doctor", "--check"])

    assert exit_code == 0
    assert report["schema_version"] == "0.1"
    assert report["status"] == "ready"
    assert report["ok"] is True
    checks = {check["check_id"]: check for check in report["checks"]}
    assert checks["python"]["status"] == "passed"
    assert checks["python"]["actual"].startswith("3.13.")
    assert checks["package"]["actual"] == "0.1.0"
    assert checks["temporary_directory"]["status"] == "passed"
    assert checks["dependency:cadquery-ocp"]["status"] == "passed"
    assert checks["dependency:ezdxf"]["status"] == "passed"
    assert checks["oda"]["status"] == "not_checked"
    assert checks["oda"]["required"] is False
    assert sys.version_info[:2] == (3, 13)


def test_doctor_rejects_an_explicit_missing_oda_path(tmp_path):
    missing = tmp_path / "missing/ODAFileConverter.exe"

    exit_code, report = _run(["doctor", "--check", "--oda-path", str(missing)])

    assert exit_code == 1
    assert report["status"] == "failed"
    assert report["ok"] is False
    oda = next(check for check in report["checks"] if check["check_id"] == "oda")
    assert oda["status"] == "failed"
    assert oda["required"] is True
    assert oda["reason_code"] == "ODA_PATH_NOT_FILE"


def test_doctor_hashes_but_does_not_execute_an_explicit_oda_file(tmp_path):
    executable = tmp_path / "converter.exe"
    executable.write_bytes(b"not an executable; doctor must not run this file")

    exit_code, report = _run(["doctor", "--check", "--oda-path", str(executable)])

    assert exit_code == 0
    oda = next(check for check in report["checks"] if check["check_id"] == "oda")
    assert oda["status"] == "passed"
    assert oda["sha256"] == hashlib.sha256(executable.read_bytes()).hexdigest()
    assert "not executed" in oda["message"]
