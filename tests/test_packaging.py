"""Packaging guard: user-supplied corpora must never enter the sdist."""

from pathlib import Path
import tomllib

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_sdist_include_list_excludes_local_corpus_and_tests():
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    include = config["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    roots = {entry.strip("/").split("/")[0] for entry in include}

    assert "test-data" not in roots
    assert "tests" not in roots
    assert {"src", "skills", "docs", "examples", "rule-packs", "evals", "scripts"} <= roots
    assert "/uv.lock" in include
