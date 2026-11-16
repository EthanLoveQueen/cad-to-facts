"""Local installation diagnostics; no artifact parsing, conversion or network access."""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
from pathlib import Path
import platform
import shutil
import sys
import tempfile
from typing import Any

from cad_to_facts import __version__


_DEPENDENCIES = {
    "cadquery-ocp": ("OCP", "==8.0.1.1.0"),
    "ezdxf": ("ezdxf", "==1.4.5"),
    "pydantic": ("pydantic", ">=2.12,<3"),
    "rfc8785": ("rfc8785", ">=0.1,<1"),
}


def _check(
    check_id: str,
    status: str,
    message: str,
    *,
    required: bool = True,
    reason_code: str | None = None,
    **details: Any,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "status": status,
        "required": required,
        "reason_code": reason_code,
        "message": message,
        **details,
    }


def _version_supported(distribution: str, version: str) -> bool:
    numeric = tuple(int(part) for part in version.split(".")[:3] if part.isdigit())
    if distribution == "cadquery-ocp":
        return version == "8.0.1.1.0"
    if distribution == "ezdxf":
        return version == "1.4.5"
    if distribution == "pydantic":
        return len(numeric) == 3 and (2, 12, 0) <= numeric < (3, 0, 0)
    if distribution == "rfc8785":
        return len(numeric) >= 2 and (0, 1) <= numeric[:2] < (1, 0)
    return False


def _dependency_check(distribution: str, module: str, requirement: str) -> dict[str, Any]:
    check_id = f"dependency:{distribution}"
    try:
        version = importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return _check(
            check_id,
            "failed",
            f"Install the locked project environment; {distribution} is not installed",
            reason_code="DEPENDENCY_NOT_INSTALLED",
            expected=requirement,
            actual=None,
        )
    if not _version_supported(distribution, version):
        return _check(
            check_id,
            "failed",
            f"Use the locked reference dependency version for {distribution}",
            reason_code="DEPENDENCY_VERSION_MISMATCH",
            expected=requirement,
            actual=version,
        )
    try:
        importlib.import_module(module)
    except Exception as error:
        return _check(
            check_id,
            "failed",
            f"{distribution} is installed but {module} could not be imported: {error}",
            reason_code="DEPENDENCY_IMPORT_FAILED",
            expected=requirement,
            actual=version,
        )
    return _check(
        check_id,
        "passed",
        f"{distribution} version and {module} import were checked",
        expected=requirement,
        actual=version,
    )


def _temporary_directory_check() -> dict[str, Any]:
    try:
        with tempfile.TemporaryDirectory(prefix="cad-to-facts-doctor-") as directory:
            probe = Path(directory) / "write-probe"
            probe.write_bytes(b"doctor")
            if probe.read_bytes() != b"doctor":
                raise OSError("temporary write probe did not round-trip")
    except OSError as error:
        return _check(
            "temporary_directory",
            "failed",
            f"Temporary directory is not writable: {error}",
            reason_code="TEMPORARY_DIRECTORY_UNWRITABLE",
        )
    return _check(
        "temporary_directory",
        "passed",
        "A unique temporary directory and write probe were created and removed",
    )


def _oda_check(configured: str | None) -> dict[str, Any]:
    if configured is None:
        return _check(
            "oda",
            "not_checked",
            "ODA was not configured; STEP and DXF do not need it, and no install location was searched",
            required=False,
            reason_code="ODA_NOT_CONFIGURED",
        )
    path = Path(configured).expanduser().resolve()
    if not path.is_file():
        return _check(
            "oda",
            "failed",
            "Supply the explicit ODAFileConverter executable path; no install location is searched",
            reason_code="ODA_PATH_NOT_FILE",
            path=str(path),
        )
    try:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        return _check(
            "oda",
            "failed",
            f"The explicit ODA executable could not be read: {error}",
            reason_code="ODA_PATH_UNREADABLE",
            path=str(path),
        )
    return _check(
        "oda",
        "passed",
        "The explicit ODA file exists and was hashed; it was not executed and conversion was not validated",
        path=str(path),
        sha256=digest.hexdigest(),
    )


def run_checks(oda_path: str | None = None) -> dict[str, Any]:
    """Check the active runtime without discovering or executing external tools."""

    python_ok = sys.version_info[:2] == (3, 13)
    checks = [
        _check(
            "python",
            "passed" if python_ok else "failed",
            "Python 3.13 is the reference runtime" if python_ok else "Use Python >=3.13,<3.14",
            reason_code=None if python_ok else "PYTHON_VERSION_UNSUPPORTED",
            expected=">=3.13,<3.14",
            actual=platform.python_version(),
            executable=sys.executable,
        ),
        _check("package", "passed", "cad-to-facts package version was read", actual=__version__),
    ]
    checks.extend(
        _dependency_check(distribution, module, requirement)
        for distribution, (module, requirement) in _DEPENDENCIES.items()
    )
    checks.append(_temporary_directory_check())
    facts_path = shutil.which("facts")
    checks.append(_check(
        "cli_on_path",
        "passed" if facts_path else "warning",
        "facts is on PATH" if facts_path else "facts is not on PATH; use uv run --project <checkout> facts ...",
        required=False,
        reason_code=None if facts_path else "CLI_NOT_ON_PATH",
        path=facts_path,
    ))
    checks.append(_oda_check(oda_path))
    failed = any(check["required"] and check["status"] == "failed" for check in checks)
    return {
        "schema_version": "0.1",
        "command": "doctor",
        "status": "failed" if failed else "ready",
        "ok": not failed,
        "platform": sys.platform,
        "checks": checks,
    }
