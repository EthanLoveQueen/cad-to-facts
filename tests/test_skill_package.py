import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    assert lines[0] == "---"
    end = lines.index("---", 1)
    values: dict[str, str] = {}
    for line in lines[1:end]:
        key, separator, value = line.partition(":")
        assert separator, f"Invalid frontmatter line: {line}"
        values[key.strip()] = value.strip()
    return values


def test_plugin_manifests_are_valid_and_wired_to_the_skill_directory():
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))

    assert plugin["name"] == "cad-to-facts"
    assert plugin["license"] == "MIT"
    assert (ROOT / plugin["skills"]).is_dir()
    assert plugin["skills"] == "./skills/"

    entries = [entry for entry in marketplace["plugins"] if entry["name"] == plugin["name"]]
    assert len(entries) == 1
    assert (ROOT / entries[0]["source"]).resolve() == ROOT
    assert marketplace["version"] == plugin["version"]


def test_skill_frontmatter_matches_the_directory_and_references_resolve():
    for skill_dir in (ROOT / "skills" / "cad-to-facts", ROOT / "skills" / "cad-view"):
        path = skill_dir / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        frontmatter = _frontmatter(text)

        assert frontmatter["name"] == skill_dir.name
        assert frontmatter["license"] == "MIT"
        assert 200 <= len(frontmatter["description"]) <= 600
        assert len(text.splitlines()) < 500

        links = re.findall(r"\]\((references/[^)#]+)", text)
        assert links, "SKILL.md must route to at least one reference"
        for link in links:
            assert (skill_dir / link).is_file(), f"Missing skill reference: {link}"
        assert (skill_dir / "LICENSE").is_file()
        assert (ROOT / "LICENSE").is_file()
