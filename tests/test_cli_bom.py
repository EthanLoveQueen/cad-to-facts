import json
import subprocess
import sys

from step_helpers import write_assembly


def test_cli_bom_outputs_neutral_grouped_extract(tmp_path):
    path = tmp_path / "assembly.step"
    write_assembly(path, names=("Bracket", "Rail"), occurrences_per_part=2)

    result = subprocess.run(
        [sys.executable, "-m", "cad_to_facts.cli", "bom", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    bom = json.loads(result.stdout)
    assert bom["complete"] is True
    assert len(bom["line_items"]) == 2
    assert {item["quantity"] for item in bom["line_items"]} == {2}
    assert bom["artifact_sha256"]
    assert bom["snapshot_content_hash"]
    assert bom["coverage"]["occurrence_total"] == 4
    assert bom["missing_inputs"] == []
