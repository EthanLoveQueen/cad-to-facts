import contextlib
import io
import json

import pytest

from cad_to_facts import cli

from step_helpers import write_assembly, write_nested_assembly


def _run(arguments):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = cli.main(arguments)
    return exit_code, json.loads(output.getvalue())


def _selector(tmp_path, value):
    path = tmp_path / "selector.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return str(path)


def test_resolve_unique_occurrence_name_returns_placed_geometry(tmp_path):
    path = tmp_path / "assembly.step"
    write_assembly(
        path,
        sizes_mm=((10.0, 10.0, 10.0), (20.0, 5.0, 5.0), (30.0, 10.0, 15.0)),
        names=("Duplicate", "Duplicate", "Unique"),
        occurrence_names=("Duplicate", "Duplicate", "Unique"),
    )

    exit_code, result = _run([
        "resolve",
        str(path),
        "--selector",
        _selector(tmp_path, {"name": "Unique"}),
    ])

    assert exit_code == 0
    assert result["artifact"]["format"] == "step"
    assert result["snapshot"]["entity_discovery"] == "complete"
    resolution = result["resolution"]
    assert resolution["status"] == "resolved"
    assert resolution["complete"] is True
    assert resolution["candidate_total"] == 1
    assert len(resolution["resolution_id"]) == 64
    target = resolution["resolved_target"]
    assert resolution["candidates"] == [target]
    assert target["name"] == "Unique"
    assert target["name_path"] == ["Test assembly", "Unique"]
    assert target["path"].startswith("occurrence:0/occurrence:")
    assert target["is_assembly"] is False
    assert target["bbox"]["unit"] == "mm"
    assert target["bbox"]["method"] == "BRepBndLib.AddOptimal"
    assert target["bbox"]["minimum"] == pytest.approx([200.0, 0.0, 0.0])
    assert target["bbox"]["maximum"] == pytest.approx([230.0, 10.0, 15.0])
    assert target["bbox"]["extents"] == pytest.approx([30.0, 10.0, 15.0])
    assert target["bbox"]["center"] == pytest.approx([215.0, 5.0, 7.5])


def test_resolve_ambiguous_name_requires_an_exact_occurrence_path(tmp_path):
    path = tmp_path / "assembly.step"
    write_assembly(
        path,
        names=("Duplicate", "Duplicate", "Unique"),
        occurrence_names=("Duplicate", "Duplicate", "Unique"),
    )

    exit_code, result = _run([
        "resolve",
        str(path),
        "--selector",
        _selector(tmp_path, {"name": "Duplicate"}),
    ])

    assert exit_code == 0
    resolution = result["resolution"]
    assert resolution["status"] == "ambiguous"
    assert resolution["complete"] is True
    assert resolution["candidate_total"] == 2
    assert resolution["resolved_target"] is None
    assert len({item["path"] for item in resolution["candidates"]}) == 2
    assert [item["bbox"]["center"][0] for item in resolution["candidates"]] == pytest.approx(
        [5.0, 110.0]
    )

    selected = resolution["candidates"][1]
    path_selector = tmp_path / "path-selector.json"
    path_selector.write_text(json.dumps({"path": selected["path"]}), encoding="utf-8")
    second_code, second = _run([
        "resolve", str(path), "--selector", str(path_selector)
    ])

    assert second_code == 0
    assert second["resolution"]["status"] == "resolved"
    assert second["resolution"]["resolved_target"]["occurrence_id"] == selected["occurrence_id"]


def test_resolve_definition_name_fallback_and_complete_absence(tmp_path):
    path = tmp_path / "assembly.step"
    write_assembly(path, names=("Bracket", "Rail"))

    code, result = _run([
        "resolve", str(path), "--selector", _selector(tmp_path, {"name": "Rail"})
    ])
    missing_selector = tmp_path / "missing-selector.json"
    missing_selector.write_text(json.dumps({"name": "Missing"}), encoding="utf-8")
    missing_code, missing = _run([
        "resolve", str(path), "--selector", str(missing_selector)
    ])

    assert code == 0
    assert result["resolution"]["status"] == "resolved"
    assert result["resolution"]["resolved_target"]["definition_name"] == "Rail"
    assert missing_code == 0
    assert missing["resolution"]["status"] == "unresolved"
    assert missing["resolution"]["complete"] is True
    assert missing["resolution"]["candidate_total"] == 0
    assert missing["resolution"]["resolved_target"] is None


def test_resolve_rejects_an_empty_selector(tmp_path):
    path = tmp_path / "assembly.step"
    write_assembly(path)

    exit_code, result = _run([
        "resolve", str(path), "--selector", _selector(tmp_path, {})
    ])

    assert exit_code == 2
    assert "at least one constraint" in result["error"]["message"]


def test_resolve_accumulates_nested_occurrence_placements(tmp_path):
    path = tmp_path / "nested.step"
    write_nested_assembly(path, subassembly_x=50.0)

    exit_code, result = _run([
        "resolve",
        str(path),
        "--selector",
        _selector(tmp_path, {"name": "Shared part", "is_assembly": False}),
    ])

    assert exit_code == 0
    resolution = result["resolution"]
    assert resolution["status"] == "ambiguous"
    assert resolution["candidate_total"] == 3
    positioned = sorted(
        (len(item["path"].split("/")), item["bbox"]["minimum"][0])
        for item in resolution["candidates"]
    )
    assert positioned == [(2, 100.0), (3, 50.0), (3, 70.0)]


def test_resolve_spatial_relation_requires_explicit_frame_and_unique_reference(tmp_path):
    path = tmp_path / "spatial.step"
    write_assembly(
        path,
        sizes_mm=((10.0, 10.0, 10.0), (10.0, 10.0, 10.0), (10.0, 10.0, 10.0)),
        names=("Left door", "Reference", "Right door"),
        occurrence_names=("Left door", "Reference", "Right door"),
    )
    spatial = {
        "relation": "left_of",
        "reference": {"name": "Reference"},
        "frame": {"preset": "front"},
    }

    exit_code, result = _run([
        "resolve",
        str(path),
        "--selector",
        _selector(tmp_path, {"name_contains": "door", "spatial": [spatial]}),
    ])

    assert exit_code == 0
    resolution = result["resolution"]
    assert resolution["status"] == "resolved"
    assert resolution["candidate_total"] == 1
    target = resolution["resolved_target"]
    assert target["name"] == "Left door"
    assert target["spatial_evidence"] == [{
        "relation": "left_of",
        "reference_occurrence_id": "occurrence:2",
        "candidate_coordinate": 5.0,
        "reference_coordinate": 105.0,
        "distance_mm": None,
        "frame": {"preset": "front", "normal": None, "right": None},
        "method": "world_bbox_center_projection",
    }]

    spatial["reference"] = {"name_contains": "door"}
    ambiguous_code, ambiguous = _run([
        "resolve",
        str(path),
        "--selector",
        _selector(tmp_path, {"name_contains": "door", "spatial": [spatial]}),
    ])
    assert ambiguous_code == 0
    assert ambiguous["resolution"]["status"] == "unresolved"
    assert ambiguous["resolution"]["candidate_total"] == 0
    assert ambiguous["resolution"]["complete"] is False
    assert "SPATIAL_REFERENCE_AMBIGUOUS" in {
        item["code"] for item in ambiguous["resolution"]["diagnostics"]
    }


def test_resolve_near_uses_an_explicit_world_bbox_gap_limit(tmp_path):
    path = tmp_path / "near.step"
    write_assembly(
        path,
        sizes_mm=((10.0, 10.0, 10.0),) * 2,
        names=("Door", "Reference"),
        occurrence_names=("Door", "Reference"),
    )
    spatial = {
        "relation": "near",
        "reference": {"name": "Reference"},
        "frame": {"preset": "front"},
        "max_distance_mm": 95.0,
    }

    exit_code, result = _run([
        "resolve", str(path), "--selector",
        _selector(tmp_path, {"name": "Door", "spatial": [spatial]}),
    ])
    missing_code, missing = _run([
        "resolve", str(path), "--selector",
        _selector(tmp_path, {
            "name": "Door",
            "spatial": [{key: value for key, value in spatial.items() if key != "max_distance_mm"}],
        }),
    ])

    assert exit_code == 0
    resolution = result["resolution"]
    assert resolution["status"] == "resolved"
    evidence = resolution["resolved_target"]["spatial_evidence"][0]
    assert evidence["method"] == "world_bbox_gap"
    assert evidence["distance_mm"] == 90.0
    assert missing_code == 2
    assert "near requires max_distance_mm" in missing["error"]["message"]
