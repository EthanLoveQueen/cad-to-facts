import json
import subprocess
import sys

from step_helpers import write_box


def test_cli_inspect_returns_summary_and_selective_facts(tmp_path):
    path = tmp_path / "box.step"
    write_box(path)

    result = subprocess.run(
        [sys.executable, "-m", "cad_to_facts.cli", "inspect", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["artifact"]["sha256"]
    assert output["snapshot"]["status"] == "ready"
    assert output["snapshot"]["snapshot_content_hash"]
    assert len(output["snapshot"]["entities"]) == 1
    assert len(output["factset"]["facts"]) == 5
    assert {fact["predicate"] for fact in output["factset"]["facts"]} == {
        "volume",
        "area",
        "bbox.extent.x",
        "bbox.extent.y",
        "bbox.extent.z",
    }
