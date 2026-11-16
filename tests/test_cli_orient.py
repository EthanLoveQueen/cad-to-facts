import contextlib
import io
import json

import pytest

from cad_to_facts import cli

from step_helpers import write_assembly


def _run(arguments):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = cli.main(arguments)
    return exit_code, json.loads(output.getvalue())


def _selector(tmp_path, value):
    path = tmp_path / "selector.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return str(path)


def test_orient_returns_an_explicit_outward_large_face_assumption(tmp_path):
    path = tmp_path / "orientation.step"
    write_assembly(
        path,
        sizes_mm=((2.0, 30.0, 40.0), (10.0, 10.0, 10.0)),
        names=("Thin Panel", "Other"),
        occurrence_names=("Thin Panel", "Other"),
    )

    exit_code, result = _run([
        "orient", str(path), "--selector", _selector(tmp_path, {"name": "Thin Panel"})
    ])

    assert exit_code == 0
    report = result["orientation"]
    assert report["status"] == "resolved"
    assert report["complete"] is True
    assert report["semantic_status"] == "assumed"
    assert report["selected_candidate"]["camera"]["preset"] == "left"
    assert report["selected_candidate"]["projected_area_mm2"] == pytest.approx(1200.0)
    assert report["selected_candidate"]["depth_mm"] == pytest.approx(2.0)
    assert report["selected_candidate"]["center_offset_mm"] < 0
    assert report["recommended_view"]["camera"]["preset"] == "left"
    assert report["recommended_view"]["semantic_intent"]["basis"] == "assumed"
    assert report["recommended_view"]["semantic_intent"]["label"] == "front"
    assert report["recommended_view"]["semantic_intent"]["note"]
    assert len(report["candidates"]) == 6


def test_orient_refuses_to_invent_an_outward_sign_at_the_assembly_center(tmp_path):
    path = tmp_path / "centered.step"
    write_assembly(path, sizes_mm=((10.0, 20.0, 30.0),))

    exit_code, result = _run([
        "orient", str(path), "--selector", _selector(tmp_path, {"path": "occurrence:0"})
    ])

    assert exit_code == 0
    report = result["orientation"]
    assert report["status"] == "ambiguous"
    assert report["selected_candidate"] is None
    assert report["recommended_view"] is None
    assert report["semantic_status"] == "unresolved"
    assert "ORIENTATION_OUTWARD_DIRECTION_AMBIGUOUS" in {
        item["code"] for item in report["diagnostics"]
    }
