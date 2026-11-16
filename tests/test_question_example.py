import contextlib
import io
import json
from pathlib import Path

from cad_to_facts import cli


def _run(arguments):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = cli.main(arguments)
    return exit_code, json.loads(output.getvalue())


def test_public_question_example_supports_agent_workflow_evals(tmp_path):
    path = Path(__file__).parents[1] / "examples" / "question-assembly.step"
    source_bytes = path.read_bytes()

    features_code, features = _run([
        "features", str(path), "--query",
        str(path.parent / "features-doors-windows-holes.json"),
    ])
    locate_code, locate = _run([
        "ask", str(path), "--question", "左侧的门在哪里？",
    ])

    assert features_code == 0
    report = features["features"]
    assert report["candidate_counts"] == {"door": 2, "window": 1, "hole": 2}
    assert report["validated_counts"] == {"door": 0, "window": 0, "hole": 1}
    geometry = next(
        item["geometry"] for item in report["candidates"] if item["validation"] == "validated"
    )
    assert geometry["radius_mm"] == 3.0
    assert geometry["length_mm"] == 10.0
    assert locate_code == 0
    target = locate["answer"]["answers"][0]["resolution"]["resolved_target"]
    assert target["name"] == "Left door"
    assert target["spatial_evidence"][0]["reference_occurrence_id"] == "assembly:root"

    selector = tmp_path / "left-door.json"
    selector.write_text(json.dumps({"occurrence_id": target["occurrence_id"]}), encoding="utf-8")
    orient_code, orient = _run([
        "orient", str(path), "--selector", str(selector),
    ])
    assert orient_code == 0
    assert orient["orientation"]["target"]["name"] == "Left door"
    assert orient["orientation"]["selected_candidate"]["camera"]["preset"] == "left"
    assert orient["orientation"]["semantic_status"] == "assumed"
    assert path.read_bytes() == source_bytes
