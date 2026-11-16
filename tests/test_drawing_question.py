import hashlib
import json

import pytest
from pydantic import ValidationError

from cad_to_facts import cli
from cad_to_facts.artifact import register
from cad_to_facts.domain.drawing_question import DrawingQuestionSpec
from cad_to_facts.drawing_question import answer_drawing_question
from cad_to_facts.snapshot import read

from drawing_helpers import (
    add_unresolved_xref,
    write_open_polyline_area_drawing,
    write_question_drawing,
    write_unitless_dimension_drawing,
    write_unitless_question_drawing,
)


def _snapshot(tmp_path, name="question.dxf"):
    path = tmp_path / name
    write_question_drawing(path)
    artifact = register(path)
    return path, artifact, read(artifact)


def _ask(snapshot, interpretations, *, text="drawing question", **kwargs):
    spec = DrawingQuestionSpec.model_validate({
        "original_text": text,
        "interpretation_basis": "agent_interpretation",
        "interpretations": interpretations,
        **kwargs,
    })
    return answer_drawing_question(snapshot, spec)


def _run(arguments):
    import contextlib
    import io

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = cli.main(arguments)
    return exit_code, json.loads(output.getvalue())


def test_drawing_entity_count_and_text_lookup_keep_scope_explicit(tmp_path):
    path, artifact, snapshot = _snapshot(tmp_path)

    report = _ask(snapshot, [
        {
            "interpretation_id": "model-lines",
            "intent": "entity_count",
            "selector": {"kinds": ["line"], "containers": ["Model"]},
            "include_layer_breakdown": True,
        },
        {
            "interpretation_id": "visible-model-lines",
            "intent": "entity_count",
            "selector": {
                "kinds": ["line"],
                "containers": ["Model"],
                "layer_state_policy": "visible",
            },
        },
        {
            "interpretation_id": "steel-text",
            "intent": "text_lookup",
            "selector": {"text_contains_any": ["steel"]},
        },
    ])

    assert report.status == "answered"
    assert report.complete is True
    lines, visible, text = report.answers
    assert lines.count.value == 4
    assert lines.count.state == "known"
    assert lines.count.by_kind == {"line": 4}
    assert lines.count.by_container_kind == {"model_space": 4}
    assert lines.count.by_layer == {"Frozen": 1, "Geometry": 2, "Hidden": 1}
    assert lines.count.scope.container_scope == "explicit"
    assert visible.count.value == 2
    assert visible.count.excluded_by_layer_state == 2
    assert visible.count.scope.excluded_by_layer_state == 2
    assert text.count.value == 2
    assert text.count.unit == "text_matches"
    assert text.entity_total == 2
    assert {entity.text for entity in text.entities} == {"材料: STEEL", "STEEL"}
    assert {entity.kind for entity in text.entities} == {"mtext", "attrib"}
    assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact.sha256


def test_drawing_lookup_layer_and_block_inventory_preserve_definition_semantics(tmp_path):
    _, _, snapshot = _snapshot(tmp_path)

    report = _ask(snapshot, [
        {
            "interpretation_id": "door-inserts",
            "intent": "entity_lookup",
            "selector": {"kinds": ["insert"], "containers": ["Model"]},
        },
        {"interpretation_id": "layers", "intent": "layer_inventory"},
        {"interpretation_id": "blocks", "intent": "block_inventory"},
    ])

    assert report.status == "answered"
    inserts, layers, blocks = report.answers
    assert inserts.count.value == 2
    assert inserts.entity_total == 2
    assert {entity.block_name for entity in inserts.entities} == {"DOOR"}
    layer_map = {layer.name: layer for layer in layers.layers}
    assert layer_map["Hidden"].off is True
    assert layer_map["Hidden"].entity_count == 1
    assert layer_map["Frozen"].frozen is True
    assert layer_map["Frozen"].entity_count == 1
    block_map = {block.name: block for block in blocks.blocks}
    assert block_map["DOOR"].declared is True
    assert block_map["DOOR"].definition_entity_count == 4
    assert block_map["DOOR"].insert_entity_count == 2
    assert block_map["TITLE"].definition_entity_count == 3
    assert block_map["TITLE"].insert_entity_count == 1
    assert block_map["TITLE"].instance_containers == {"Layout1": 1}
    assert {gap.code for gap in blocks.gaps} >= {"INSERT_GEOMETRY_NOT_EXPANDED"}


def test_drawing_measurement_summary_uses_units_and_reports_partial_coverage(tmp_path):
    _, _, snapshot = _snapshot(tmp_path)

    report = _ask(snapshot, [
        {
            "interpretation_id": "model-line-length",
            "intent": "measurement_summary",
            "predicate": "length",
            "selector": {"kinds": ["line"], "containers": ["Model"]},
            "include_values": True,
        },
        {
            "interpretation_id": "mixed-length",
            "intent": "measurement_summary",
            "predicate": "length",
            "selector": {
                "kinds": ["line", "text", "mtext"],
                "containers": ["Model"],
            },
        },
        {
            "interpretation_id": "area",
            "intent": "measurement_summary",
            "predicate": "area",
            "selector": {"kinds": ["circle", "lwpolyline"], "containers": ["Model"]},
        },
    ])

    assert report.status == "partial"
    lengths, mixed, areas = report.answers
    measurement = lengths.measurements
    assert measurement.state == "known"
    assert measurement.selected_entity_count == 4
    assert measurement.measured_entity_count == 4
    assert measurement.total == pytest.approx(26.0)
    assert measurement.minimum == pytest.approx(5.0)
    assert measurement.maximum == pytest.approx(10.0)
    assert measurement.unit == "mm"
    assert measurement.sum_scope == "all_selected_supported"
    assert len(measurement.values) == 4
    assert mixed.status == "partial"
    assert mixed.measurements.unsupported_entity_count == 2
    assert mixed.measurements.state == "partial"
    assert {gap.code for gap in mixed.gaps} >= {"MEASUREMENT_NOT_APPLICABLE"}
    assert areas.measurements.state == "known"
    assert areas.measurements.total == pytest.approx(200.0 + 4.0 * 3.141592653589793)
    assert areas.measurements.unit == "mm^2"


def test_drawing_measurement_does_not_turn_unitless_values_into_zero(tmp_path):
    path = tmp_path / "unitless.dxf"
    write_unitless_question_drawing(path)
    snapshot = read(register(path))

    report = _ask(snapshot, [
        {
            "interpretation_id": "unitless-length",
            "intent": "measurement_summary",
            "predicate": "length",
            "selector": {"kinds": ["line"]},
        },
        {
            "interpretation_id": "unitless-count",
            "intent": "entity_count",
            "selector": {"kinds": ["line"]},
        },
    ])

    measurement, count = report.answers
    assert count.count.state == "known"
    assert count.count.value == 1
    assert measurement.status == "partial"
    assert measurement.measurements.state == "unknown"
    assert measurement.measurements.total is None
    assert measurement.measurements.value_count == 0
    assert measurement.measurements.gap_counts == {"UNKNOWN_UNIT": 1}
    assert {gap.code for gap in measurement.gaps} >= {
        "MEASUREMENT_NO_VALUES",
        "DRAWING_MEASUREMENT_GAPS",
    }


def test_drawing_dimension_values_are_declared_without_geometry_association(tmp_path):
    _, _, snapshot = _snapshot(tmp_path)

    report = _ask(snapshot, [
        {"interpretation_id": "dimensions", "intent": "dimension_inventory"}
    ])

    assert report.status == "answered"
    inventory = report.answers[0].dimensions
    assert inventory.state == "known"
    assert inventory.dimension_total == 1
    assert inventory.valued_count == 1
    value = inventory.dimensions[0]
    assert value.dimension_type == "linear"
    assert value.measurement == pytest.approx(10.0)
    assert value.unit == "mm"
    assert value.state == "known"
    assert value.text_override == "10.0"
    assert inventory.association == "unsupported"
    assert {gap.code for gap in report.answers[0].gaps} >= {
        "DIMENSION_GEOMETRY_ASSOCIATION_UNSUPPORTED"
    }


def test_drawing_name_candidates_never_become_validated_features(tmp_path):
    _, _, snapshot = _snapshot(tmp_path)

    report = _ask(snapshot, [
        {
            "interpretation_id": "door-candidates",
            "intent": "name_candidate_count",
            "candidate_terms": ["door"],
            "evidence_policy": "candidates_allowed",
        }
    ])

    assert report.status == "answered"
    candidates = report.answers[0].candidates
    assert candidates.state == "candidate"
    assert candidates.value == 3
    assert candidates.unit == "semantic_candidates"
    assert candidates.validation == "unvalidated"
    assert candidates.general_semantic_coverage == "unknown"
    assert candidates.by_basis == {"block_name": 2, "layer_name": 2, "text": 1}
    assert candidates.match_rows_total == 5
    assert {gap.code for gap in report.answers[0].gaps} >= {
        "SEMANTIC_CANDIDATES_UNVALIDATED",
        "SEMANTIC_COVERAGE_UNKNOWN",
    }

    with pytest.raises(ValidationError):
        DrawingQuestionSpec.model_validate({
            "original_text": "strict candidate question",
            "interpretation_basis": "agent_interpretation",
            "interpretations": [{
                "interpretation_id": "bad",
                "intent": "name_candidate_count",
                "candidate_terms": ["door"],
            }],
        })


def test_drawing_semantic_evidence_returns_declared_context_not_fields(tmp_path):
    _, _, snapshot = _snapshot(tmp_path)

    report = _ask(snapshot, [
        {
            "interpretation_id": "semantic-evidence",
            "intent": "semantic_evidence",
            "candidate_terms": [
                "door", "门", "title", "part", "material", "steel", "材料"
            ],
            "candidate_bases": [
                "block_name", "layer_name", "text", "attribute_tag"
            ],
            "evidence_policy": "candidates_allowed",
        }
    ])

    assert report.status == "answered"
    answer = report.answers[0]
    summary = answer.semantic_evidence
    assert summary.state == "candidate"
    assert summary.validation == "unvalidated"
    assert summary.general_semantic_coverage == "unknown"
    assert summary.value == 9
    assert summary.by_basis == {
        "block_name": 3,
        "layer_name": 2,
        "text": 3,
        "attribute_tag": 4,
    }
    assert summary.match_rows_total == 12
    assert summary.attributed_insert_count == 1
    title = next(
        evidence for evidence in summary.evidence
        if evidence.block_name == "TITLE"
    )
    assert title.attributes == {
        "PART": ["A-123"],
        "MATERIAL": ["STEEL"],
        "QTY": ["2"],
    }
    material = next(
        evidence for evidence in summary.evidence
        if evidence.basis == "attribute_tag"
        and evidence.declared_value == "MATERIAL"
    )
    assert material.attribute_tag == "MATERIAL"
    assert {gap.code for gap in answer.gaps} >= {
        "SEMANTIC_CANDIDATES_UNVALIDATED",
        "SEMANTIC_CONTEXT_DECLARED_ONLY",
        "SEMANTIC_COVERAGE_UNKNOWN",
    }
    context_gap = next(
        gap for gap in answer.gaps if gap.code == "SEMANTIC_CONTEXT_DECLARED_ONLY"
    )
    assert "not inferred material" in context_gap.message


def test_drawing_bom_lookup_uses_explicit_tags_and_containers(tmp_path):
    _, _, snapshot = _snapshot(tmp_path)

    report = _ask(snapshot, [
        {
            "interpretation_id": "title-bom",
            "intent": "drawing_bom_lookup",
            "bom": {
                "part_tag": "PART",
                "quantity_tag": "QTY",
                "material_tag": "MATERIAL",
                "containers": ["Layout1"],
            },
        }
    ])

    assert report.status == "answered"
    answer = report.answers[0]
    assert answer.bom.complete is True
    assert len(answer.bom.line_items) == 1
    line = answer.bom.line_items[0]
    assert line.part_number == "A-123"
    assert line.quantity == 2
    assert line.quantity_state == "known"
    assert line.declared_properties["MATERIAL"] == "STEEL"


def test_drawing_partial_discovery_keeps_counts_partial_not_complete(tmp_path):
    path = tmp_path / "xref.dxf"
    write_question_drawing(path)
    add_unresolved_xref(path)
    snapshot = read(register(path))
    assert snapshot.entity_discovery == "partial"

    report = _ask(snapshot, [
        {
            "interpretation_id": "lines",
            "intent": "entity_count",
            "selector": {"kinds": ["line"], "containers": ["Model"]},
        },
        {
            "interpretation_id": "lengths",
            "intent": "measurement_summary",
            "predicate": "length",
            "selector": {"kinds": ["line"], "containers": ["Model"]},
        },
    ])

    assert report.status == "partial"
    assert report.complete is False
    lines, lengths = report.answers
    assert lines.count.state == "partial"
    assert lines.count.value == 4
    assert lengths.measurements.state == "partial"
    assert {gap.code for gap in lines.gaps} >= {"DRAWING_DISCOVERY_PARTIAL"}


def test_failed_drawing_snapshot_returns_failed_answer_not_zero(tmp_path):
    path = tmp_path / "drawing.dwg"
    path.write_bytes(b"AC1032\r\nnot-a-real-model")
    snapshot = read(register(path), {"oda_executable": str(tmp_path / "missing.exe")})

    report = _ask(snapshot, [
        {
            "interpretation_id": "lines",
            "intent": "entity_count",
            "selector": {"kinds": ["line"]},
        }
    ])

    assert report.status == "failed"
    assert report.complete is False
    assert report.answers[0].status == "failed"
    assert {gap.code for gap in report.answers[0].gaps} >= {"DRAWING_SNAPSHOT_FAILED"}


def test_unknown_drawing_discovery_keeps_observed_count_separate(tmp_path):
    path = tmp_path / "malformed.dxf"
    path.write_text("0\nSECTION\n2\nENTITIES\n0\nLINE\n", encoding="ascii")
    snapshot = read(register(path))
    assert snapshot.entity_discovery == "unknown"

    report = _ask(snapshot, [
        {
            "interpretation_id": "lines",
            "intent": "entity_count",
            "selector": {"kinds": ["line"]},
        }
    ])

    assert report.status == "partial"
    assert report.complete is False
    count = report.answers[0].count
    assert count.state == "unknown"
    assert count.value is None
    assert count.observed_value == 0
    assert {gap.code for gap in report.answers[0].gaps} >= {
        "DRAWING_DISCOVERY_UNKNOWN"
    }


def test_cli_ask_drawing_spec_and_rejects_natural_language_without_spec(tmp_path):
    path = tmp_path / "question.dxf"
    write_question_drawing(path)
    original = path.read_bytes()
    spec = tmp_path / "drawing-question.json"
    spec.write_text(json.dumps({
        "original_text": "模型空间有多少条线？",
        "interpretation_basis": "agent_interpretation",
        "interpretations": [{
            "interpretation_id": "model-lines",
            "intent": "entity_count",
            "selector": {"kinds": ["line"], "containers": ["Model"]},
        }],
    }), encoding="utf-8")

    exit_code, result = _run(["ask", str(path), "--spec", str(spec)])

    assert exit_code == 0
    answer = result["answer"]
    assert answer["profile"] == "drawing"
    assert answer["status"] == "answered"
    assert answer["complete"] is True
    assert answer["answers"][0]["count"]["value"] == 4
    assert answer["question"]["question_id"] != "0" * 64
    assert path.read_bytes() == original

    exit_code, error = _run(["ask", str(path), "--question", "模型空间有多少条线？"])

    assert exit_code == 2
    assert "explicit DrawingQuestionSpec" in error["error"]["message"]


def test_drawing_unitless_dimension_value_is_unknown_not_zero(tmp_path):
    path = tmp_path / "unitless-dimension.dxf"
    write_unitless_dimension_drawing(path)
    snapshot = read(register(path))

    report = _ask(snapshot, [
        {"interpretation_id": "dimensions", "intent": "dimension_inventory"}
    ])

    inventory = report.answers[0].dimensions
    assert report.status == "partial"
    assert inventory.state == "unknown"
    assert inventory.valued_count == 0
    assert inventory.unknown_count == 1
    assert inventory.dimensions[0].measurement is None
    assert inventory.dimensions[0].reason == "UNKNOWN_UNIT"
    assert inventory.gap_counts == {"UNKNOWN_UNIT": 1}


def test_drawing_bom_lookup_reports_incomplete_scope_honestly(tmp_path):
    _, _, snapshot = _snapshot(tmp_path)

    report = _ask(snapshot, [
        {
            "interpretation_id": "model-bom",
            "intent": "drawing_bom_lookup",
            "bom": {
                "part_tag": "PART",
                "quantity_tag": "QTY",
                "containers": ["Model"],
            },
        }
    ])

    assert report.status == "partial"
    answer = report.answers[0]
    assert answer.bom.complete is False
    assert answer.bom.missing_inputs
    assert {gap.code for gap in answer.gaps} >= {"DRAWING_BOM_INCOMPLETE"}


def test_drawing_result_limits_keep_matched_total_and_exact_handle_lookup(tmp_path):
    _, _, snapshot = _snapshot(tmp_path)
    line = next(
        entity for entity in snapshot.entities
        if entity.entity_kind == "line"
        and any(
            ref == {"type": "container", "value": "Model"}
            for ref in entity.native_refs
        )
    )
    handle = next(
        ref["value"] for ref in line.native_refs if ref["type"] == "handle"
    )

    report = _ask(snapshot, [
        {
            "interpretation_id": "steel-text-sample",
            "intent": "text_lookup",
            "selector": {"text_contains_any": ["STEEL"]},
            "max_results": 1,
        },
        {
            "interpretation_id": "exact-handle",
            "intent": "entity_lookup",
            "selector": {"handles": [handle]},
        },
    ])

    sample, handle_answer = report.answers
    assert sample.count.value == 2
    assert sample.entity_total == 2
    assert len(sample.entities) == 1
    assert sample.entities_truncated is True
    assert {gap.code for gap in sample.gaps} >= {"RESULT_LIMIT_APPLIED"}
    assert handle_answer.count.value == 1
    assert handle_answer.entities[0].entity_id == line.entity_id


def test_drawing_question_without_interpretations_is_unsupported(tmp_path):
    _, _, snapshot = _snapshot(tmp_path)

    report = _ask(snapshot, [], interpretation_gaps=["No drawing subquestion supplied"])

    assert report.status == "unsupported"
    assert report.complete is False
    assert report.gaps[0].code == "DRAWING_QUESTION_INTERPRETATION_UNSUPPORTED"
    assert "No drawing subquestion supplied" in report.gaps[0].message


def test_drawing_default_area_filter_ignores_open_polylines_but_explicit_scope_reports_them(tmp_path):
    path = tmp_path / "open-area.dxf"
    write_open_polyline_area_drawing(path)
    snapshot = read(register(path))

    report = _ask(snapshot, [
        {
            "interpretation_id": "default-area",
            "intent": "measurement_summary",
            "predicate": "area",
        },
        {
            "interpretation_id": "explicit-area",
            "intent": "measurement_summary",
            "predicate": "area",
            "selector": {"kinds": ["circle", "lwpolyline"]},
        },
    ])

    default, explicit = report.answers
    assert default.measurements.state == "known"
    assert default.measurements.selected_entity_count == 1
    assert default.measurements.unsupported_entity_count == 0
    assert default.measurements.total == pytest.approx(4.0 * 3.141592653589793)
    assert explicit.measurements.state == "partial"
    assert explicit.measurements.selected_entity_count == 2
    assert explicit.measurements.supported_entity_count == 1
    assert explicit.measurements.unsupported_entity_count == 1
    assert {gap.code for gap in explicit.gaps} >= {"MEASUREMENT_NOT_APPLICABLE"}


def test_drawing_spec_rejects_claimed_deterministic_grammar():
    with pytest.raises(ValidationError):
        DrawingQuestionSpec.model_validate({
            "original_text": "模型空间有多少条线？",
            "interpretation_basis": "deterministic_grammar",
            "interpretations": [{
                "interpretation_id": "lines",
                "intent": "entity_count",
                "selector": {"kinds": ["line"], "containers": ["Model"]},
            }],
        })


def test_drawing_inventory_and_bom_intents_reject_ignored_selector_fields():
    base = {
        "original_text": "invalid scope",
        "interpretation_basis": "agent_interpretation",
    }
    invalid = [
        {
            "interpretation_id": "layers",
            "intent": "layer_inventory",
            "selector": {"kinds": ["line"]},
        },
        {
            "interpretation_id": "blocks",
            "intent": "block_inventory",
            "selector": {"layers": ["Geometry"]},
        },
        {
            "interpretation_id": "bom",
            "intent": "drawing_bom_lookup",
            "selector": {"layers": ["Geometry"]},
            "bom": {"part_tag": "PART"},
        },
        {
            "interpretation_id": "semantic",
            "intent": "semantic_evidence",
            "candidate_terms": ["door"],
        },
    ]
    for interpretation in invalid:
        with pytest.raises(ValidationError):
            DrawingQuestionSpec.model_validate({
                **base,
                "interpretations": [interpretation],
            })
