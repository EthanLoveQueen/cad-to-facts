"""Check built distributions without extracting or executing their contents."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tarfile
import zipfile


REQUIRED_SDIST = {
    "src/cad_to_facts/cli.py",
    "skills/cad-to-facts/SKILL.md",
    "docs/installation.md",
    "docs/recovery.md",
    "docs/drawing-questions.md",
    "examples/change-loop/README.md",
    "examples/change-loop/baseline/box.step",
    "examples/change-loop/recorded/execution.json",
    "examples/box.step",
    "examples/question-assembly.step",
    "examples/question-drawing.dxf",
    "examples/drawing-question.json",
    "examples/machining-context.json",
    "rule-packs/step-file-health/rules.json",
    "evals/step-facts/prompt.md",
    "evals/evals.json",
    "evals/model-question-compound/prompt.md",
    "evals/model-question-alternatives/prompt.md",
    "evals/model-question-view/prompt.md",
    "scripts/check_dist.py",
    "uv.lock",
}


def _relative_sdist_name(name: str) -> str:
    parts = Path(name).parts
    return "/".join(parts[1:]) if len(parts) > 1 else ""


def _forbidden(name: str) -> bool:
    parts = Path(name).parts
    normalized = "/".join(parts)
    return (
        "test-data" in parts
        or "tests" in parts
        or "evals/results" in normalized
    )


def check(dist: Path) -> dict[str, object]:
    sdists = sorted(dist.glob("*.tar.gz"))
    wheels = sorted(dist.glob("*.whl"))
    if len(sdists) != 1 or len(wheels) != 1:
        raise ValueError("Expected exactly one sdist and one wheel in dist/")
    with tarfile.open(sdists[0], "r:gz") as archive:
        sdist_members = archive.getmembers()
        sdist_names = {member.name for member in sdist_members}
        relative_names = {_relative_sdist_name(name) for name in sdist_names}
        forbidden = sorted(name for name in sdist_names if _forbidden(name))
        missing = sorted(REQUIRED_SDIST - relative_names)
        leaked_tokens = []
        for member in sdist_members:
            if not member.isfile() or "examples/change-loop/" not in member.name:
                continue
            if member.size > 2_000_000:
                continue
            extracted = archive.extractfile(member)
            if extracted is not None and b"?token=" in extracted.read():
                leaked_tokens.append(member.name)
    with zipfile.ZipFile(wheels[0]) as archive:
        wheel_names = archive.namelist()
        wheel_forbidden = sorted(name for name in wheel_names if _forbidden(name))
        wheel_has_cli = "cad_to_facts/cli.py" in wheel_names
    failures = []
    if forbidden or wheel_forbidden:
        failures.append(f"Forbidden test/corpus entries: {forbidden + wheel_forbidden}")
    if missing:
        failures.append(f"Missing required sdist entries: {missing}")
    if leaked_tokens:
        failures.append(f"Viewer token query strings found: {leaked_tokens}")
    if not wheel_has_cli:
        failures.append("Wheel does not contain cad_to_facts/cli.py")
    if failures:
        raise ValueError("; ".join(failures))
    return {
        "status": "passed",
        "sdist": {"path": str(sdists[0]), "entries": len(sdist_names)},
        "wheel": {"path": str(wheels[0]), "entries": len(wheel_names)},
        "forbidden_entries": [],
        "viewer_token_query_strings": [],
        "required_sdist_entries": sorted(REQUIRED_SDIST),
    }


if __name__ == "__main__":
    try:
        result = check(Path(sys.argv[1] if len(sys.argv) > 1 else "dist"))
    except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as error:
        print(json.dumps({"status": "failed", "error": str(error)}))
        raise SystemExit(1) from error
    print(json.dumps(result, ensure_ascii=False))
