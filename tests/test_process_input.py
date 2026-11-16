import contextlib
import io
import json
from pathlib import Path

from cad_to_facts import cli
from cad_to_facts.artifact import register
from cad_to_facts.contract import bind_context
from cad_to_facts.domain.facts import ExtractionQuery, FactRequest
from cad_to_facts.domain.process import ProcessInputOptions
from cad_to_facts.domain.review import ReviewContext
from cad_to_facts.facts import extract
from cad_to_facts.process import prepare
from cad_to_facts.snapshot import read

from step_helpers import write_box, write_boxes


PREDICATES = ["volume", "area", "bbox.extent.x", "bbox.extent.y", "bbox.extent.z"]
ROOT = Path(__file__).resolve().parents[1]


def _query(snapshot):
    return ExtractionQuery(requests=[
        FactRequest(name=f"{entity.entity_id}:{predicate}", predicate=predicate, subject_id=entity.entity_id)
        for entity in snapshot.entities
        for predicate in PREDICATES
    ])


def _context(values):
    return bind_context(ReviewContext(context_id="0" * 64, values=values))


def _run(arguments):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = cli.main(arguments)
    return exit_code, json.loads(output.getvalue())


def test_process_input_separates_geometry_user_inputs_and_optional_gaps(tmp_path):
    path = tmp_path / "box.step"
    write_box(path)
    snapshot = read(register(path), {"read_scope": "single_part"})
    factset = extract(snapshot, _query(snapshot))

    result = prepare(
        snapshot,
        factset,
        _context({"material": "6061-T6", "stock": "sawed bar", "batch_size": 25}),
    )

    assert result.complete is True
    assert len(result.entities) == 1
    assert len(result.entities[0].facts) == 5
    assert result.entities[0].gaps == []
    assert {item.name: item.value for item in result.external_inputs} == {
        "material": "6061-T6", "stock": "sawed bar", "batch_size": 25
    }
    assert {item.source for item in result.external_inputs} == {"user_supplied"}
    assert {item.field for item in result.missing_inputs} == {
        "declared_material", "semantic_pmi", "validated_features"
    }
    assert all(not item.required for item in result.missing_inputs)
    assert result.coverage.fully_measured_entity_total == 1
    forbidden = {"operations", "operation_sequence", "setups", "machine_selection", "tool_selection", "cutting_parameters"}
    assert forbidden.isdisjoint(result.model_dump())


def test_cli_process_input_reports_missing_context_without_inventing_it(tmp_path):
    path = tmp_path / "box.step"
    context = tmp_path / "context.json"
    write_box(path)
    context.write_text('{"values": {}}', encoding="utf-8")

    exit_code, result = _run(["process-input", str(path), "--context", str(context)])

    assert exit_code == 0
    assert result["complete"] is False
    missing = {(item["field"], item["reason_code"]) for item in result["missing_inputs"]}
    assert ("material", "ABSENT") in missing
    assert ("stock", "ABSENT") in missing
    assert ("batch_size", "ABSENT") in missing
    assert result["external_inputs"] == []
    assert len(result["entities"][0]["facts"]) == 5


def test_cli_process_input_required_pmi_stays_unsupported_and_incomplete(tmp_path):
    path = tmp_path / "box.step"
    context = tmp_path / "context.json"
    write_box(path)
    context.write_text(json.dumps({"values": {
        "material": "steel", "stock": "plate", "batch_size": 1
    }}), encoding="utf-8")

    exit_code, result = _run([
        "process-input", str(path), "--context", str(context),
        "--require-design-input", "semantic_pmi",
    ])

    assert exit_code == 0
    assert result["complete"] is False
    pmi = next(item for item in result["missing_inputs"] if item["field"] == "semantic_pmi")
    assert pmi["required"] is True
    assert pmi["reason_code"] == "UNSUPPORTED"


def test_process_input_does_not_choose_one_solid_from_a_multi_part_file(tmp_path):
    path = tmp_path / "boxes.step"
    write_boxes(path)
    snapshot = read(register(path), {"read_scope": "single_part"})
    factset = extract(snapshot, _query(snapshot))

    result = prepare(snapshot, factset, _context({
        "material": "steel", "stock": "plate", "batch_size": 1
    }))

    assert result.complete is False
    assert len(result.entities) == 2
    assert any(item.code == "PROCESS_SINGLE_PART_REQUIRED" for item in result.diagnostics)
    assert any(item.field == "part_identity" and item.required for item in result.missing_inputs)


def test_shipped_process_example_is_complete_for_its_declared_profile():
    exit_code, result = _run([
        "process-input", str(ROOT / "examples/box.step"),
        "--context", str(ROOT / "examples/machining-context.json"),
    ])

    assert exit_code == 0
    assert result["complete"] is True
    facts = {fact["predicate"]: fact for fact in result["entities"][0]["facts"]}
    assert facts["volume"]["value"] == 6000.0
    assert facts["area"]["value"] == 2200.0
    assert [facts[f"bbox.extent.{axis}"]["value"] for axis in "xyz"] == [10.0, 20.0, 30.0]
    assert result["coverage"]["required_missing_total"] == 0


def test_cli_process_input_rejects_process_planning_decisions(tmp_path):
    path = tmp_path / "box.step"
    context = tmp_path / "context.json"
    write_box(path)
    context.write_text(json.dumps({"values": {"cutting_parameters": {"rpm": 1200}}}), encoding="utf-8")

    exit_code, result = _run(["process-input", str(path), "--context", str(context)])

    assert exit_code == 2
    assert "outside" in result["error"]["message"]
