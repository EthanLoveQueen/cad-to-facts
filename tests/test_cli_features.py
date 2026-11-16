import contextlib
import io
import json

import pytest

from cad_to_facts import cli

from step_helpers import write_feature_assembly


def _run(arguments):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = cli.main(arguments)
    return exit_code, json.loads(output.getvalue())


def test_features_separate_name_candidates_from_a_validated_through_hole(tmp_path):
    path = tmp_path / "features.step"
    write_feature_assembly(path)
    query = tmp_path / "features.json"
    query.write_text(json.dumps({"kinds": ["door", "window", "hole"]}), encoding="utf-8")

    exit_code, result = _run(["features", str(path), "--query", str(query)])

    assert exit_code == 0
    report = result["features"]
    assert report["status"] == "ready"
    assert report["discovery"] == "complete"
    assert report["complete"] is True
    assert report["general_feature_coverage"] == "unknown"
    assert report["candidate_counts"] == {"door": 1, "window": 1, "hole": 1}
    assert report["validated_counts"] == {"door": 0, "window": 0, "hole": 1}
    by_kind = {item["kind"]: item for item in report["candidates"]}
    assert by_kind["door"]["validation"] == "unvalidated"
    assert by_kind["door"]["recognition_method"] == "declared_name_alias"
    assert by_kind["door"]["matched_alias"] == "door"
    assert by_kind["window"]["validation"] == "unvalidated"
    hole = by_kind["hole"]
    assert hole["validation"] == "validated"
    assert hole["recognition_method"] == "occt_full_cylinder_open_endpoints"
    assert hole["target"]["bbox"]["extents"] == pytest.approx([20.0, 20.0, 10.0])
    assert hole["geometry"]["radius_mm"] == pytest.approx(3.0)
    assert hole["geometry"]["length_mm"] == pytest.approx(10.0)
    assert hole["geometry"]["axis"] == pytest.approx([0.0, 0.0, 1.0])
    assert hole["geometry"]["area_mm2"] == pytest.approx(60.0 * 3.141592653589793)
    assert {item["code"] for item in report["gaps"]} == {
        "DOOR_GEOMETRY_VALIDATION_UNSUPPORTED",
        "WINDOW_GEOMETRY_VALIDATION_UNSUPPORTED",
        "GENERAL_HOLE_RECOGNITION_UNSUPPORTED",
    }
