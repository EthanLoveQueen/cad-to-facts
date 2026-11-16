import contextlib
import hashlib
import io
import json

import pytest

from cad_to_facts import cli

from step_helpers import write_assembly, write_box


def _run(arguments):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = cli.main(arguments)
    return exit_code, json.loads(output.getvalue())


def _write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return str(path)


def _front_view(**updates):
    value = {
        "title": "Door front",
        "camera": {"preset": "front"},
        "display": {"show_hidden_lines": False},
        "image": {
            "width": 600,
            "height": 400,
            "padding": 20,
            "curve_deflection_mm": 0.1,
            "max_points": 10000,
        },
        "semantic_intent": {
            "label": "front",
            "basis": "user_selected",
            "note": "The user selected the exterior side as front",
        },
    }
    value.update(updates)
    return value


def test_step_render_isolates_target_and_writes_svg_with_manifest(tmp_path):
    path = tmp_path / "assembly.step"
    write_assembly(
        path,
        sizes_mm=((10.0, 20.0, 30.0), (40.0, 10.0, 10.0)),
        names=("Door", "Other"),
        occurrence_names=("Door", "Other"),
    )
    selector = _write_json(tmp_path / "selector.json", {"name": "Door"})
    _, resolved = _run(["resolve", str(path), "--selector", selector])
    target = resolved["resolution"]["resolved_target"]
    view_spec = _write_json(tmp_path / "view.json", _front_view())
    output = tmp_path / "door.svg"

    exit_code, result = _run([
        "render",
        str(path),
        "--target",
        target["occurrence_id"],
        "--view-spec",
        view_spec,
        "--output",
        str(output),
    ])

    assert exit_code == 0
    manifest_path = tmp_path / "door.view.json"
    assert result["manifest_path"] == str(manifest_path)
    manifest = result["view_render"]
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == manifest
    assert manifest["kind"] == "step_view_render"
    assert len(manifest["view_render_id"]) == 64
    assert manifest["artifact_sha256"] == result["artifact"]["sha256"]
    assert manifest["snapshot_id"] == result["snapshot_id"]
    assert manifest["target"]["occurrence_id"] == target["occurrence_id"]
    assert manifest["view"]["semantic_intent"]["basis"] == "user_selected"
    assert manifest["render"]["projected_extents"] == pytest.approx([10.0, 30.0])
    assert manifest["render"]["visible_edge_count"] > 0
    assert manifest["render"]["point_count"] > 0
    content = output.read_bytes()
    assert b"<svg" in content
    assert manifest["output"]["sha256"] == hashlib.sha256(content).hexdigest()
    assert manifest["output"]["size_bytes"] == len(content)


def test_step_render_never_overwrites_svg_or_manifest(tmp_path):
    path = tmp_path / "assembly.step"
    write_assembly(path, names=("Door", "Other"), occurrence_names=("Door", "Other"))
    output = tmp_path / "door.svg"
    arguments = [
        "render", str(path), "--target", "occurrence:1",
        "--view-spec", _write_json(tmp_path / "view.json", _front_view()),
        "--output", str(output),
    ]
    source_before = path.read_bytes()
    first_code, _ = _run(arguments)
    manifest_path = tmp_path / "door.view.json"
    svg_before = output.read_bytes()
    manifest_before = manifest_path.read_bytes()

    second_code, second = _run(arguments)

    assert first_code == 0
    assert second_code == 2
    assert "exists" in second["error"]["message"].lower()
    assert output.read_bytes() == svg_before
    assert manifest_path.read_bytes() == manifest_before
    assert path.read_bytes() == source_before

    other_output = tmp_path / "other.svg"
    other_manifest = tmp_path / "other.view.json"
    other_manifest.write_bytes(b"keep this manifest")
    collision_arguments = list(arguments)
    collision_arguments[-1] = str(other_output)
    collision_code, collision = _run(collision_arguments)

    assert collision_code == 2
    assert "exists" in collision["error"]["message"].lower()
    assert not other_output.exists()
    assert other_manifest.read_bytes() == b"keep this manifest"


def test_step_render_rejects_unknown_target_without_creating_outputs(tmp_path):
    path = tmp_path / "assembly.step"
    write_assembly(path)
    output = tmp_path / "missing.svg"

    exit_code, result = _run([
        "render", str(path), "--target", "occurrence:999",
        "--view-spec", _write_json(tmp_path / "view.json", _front_view()),
        "--output", str(output),
    ])

    assert exit_code == 2
    assert "Unknown occurrence" in result["error"]["message"]
    assert not output.exists()
    assert not (tmp_path / "missing.view.json").exists()


def test_step_render_preserves_explicit_camera_and_assumed_semantics(tmp_path):
    path = tmp_path / "box.step"
    write_box(path)
    view = _front_view(
        camera={"normal": [0.0, -1.0, 0.0], "right": [1.0, 0.0, 0.0]},
        semantic_intent={"label": "front", "basis": "assumed"},
    )
    output = tmp_path / "assumed.svg"

    exit_code, result = _run([
        "render", str(path), "--target", "occurrence:0",
        "--view-spec", _write_json(tmp_path / "view.json", view),
        "--output", str(output),
    ])

    assert exit_code == 0
    manifest = result["view_render"]
    assert manifest["view"]["camera"]["normal"] == [0.0, -1.0, 0.0]
    assert manifest["view"]["camera"]["right"] == [1.0, 0.0, 0.0]
    assert manifest["view"]["semantic_intent"]["label"] == "front"
    assert manifest["view"]["semantic_intent"]["basis"] == "assumed"
    assert manifest["view"]["semantic_intent"]["note"] is None
    assert manifest["render"]["projected_extents"] == pytest.approx([10.0, 30.0])
    assert manifest["fidelity"] == "review_render_only_not_visual_or_geometric_equivalence"
