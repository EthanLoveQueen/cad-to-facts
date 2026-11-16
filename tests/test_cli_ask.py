import contextlib
import io
import json

from cad_to_facts import cli

from step_helpers import write_assembly, write_feature_assembly


def _run(arguments):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = cli.main(arguments)
    return exit_code, json.loads(output.getvalue())


def test_ask_executes_an_explicit_agent_question_spec(tmp_path):
    path = tmp_path / "spatial.step"
    write_assembly(
        path,
        sizes_mm=((10.0, 10.0, 10.0),) * 3,
        names=("Left door", "Reference", "Right door"),
        occurrence_names=("Left door", "Reference", "Right door"),
    )
    spec = tmp_path / "question.json"
    spec.write_text(json.dumps({
        "original_text": "How many occurrences have door in their names?",
        "interpretation_basis": "agent_interpretation",
        "interpretations": [{
            "interpretation_id": "count-doors",
            "intent": "occurrence_count",
            "selector": {"name_contains_any": ["door", "门"]},
        }],
    }), encoding="utf-8")

    exit_code, result = _run(["ask", str(path), "--spec", str(spec)])

    assert exit_code == 0
    report = result["answer"]
    assert report["status"] == "answered"
    assert report["complete"] is True
    assert report["question"]["question_id"] != "0" * 64
    assert report["question"]["interpretation_basis"] == "agent_interpretation"
    answer = report["answers"][0]
    assert answer["occurrence_count"] == {
        "value": 2,
        "state": "known",
        "unit": "occurrences",
        "evidence_refs": ["occurrence:1", "occurrence:3"],
    }
    assert answer["gaps"] == []


def test_ask_feature_answers_keep_general_coverage_unknown(tmp_path):
    path = tmp_path / "features.step"
    write_feature_assembly(path)
    spec = tmp_path / "feature-question.json"
    spec.write_text(json.dumps({
        "original_text": "How many holes are there, and what are their sizes and shapes?",
        "interpretation_basis": "agent_interpretation",
        "interpretations": [
            {
                "interpretation_id": "count-holes",
                "intent": "feature_count",
                "feature_kinds": ["hole"],
            },
            {
                "interpretation_id": "hole-geometry",
                "intent": "feature_geometry",
                "feature_kinds": ["hole"],
            },
        ],
    }), encoding="utf-8")

    exit_code, result = _run(["ask", str(path), "--spec", str(spec)])

    assert exit_code == 0
    report = result["answer"]
    assert report["status"] == "partial"
    assert report["complete"] is False
    count, geometry = report["answers"]
    assert count["feature_counts"]["hole"]["value"] == 1
    assert count["feature_counts"]["hole"]["state"] == "observed"
    assert count["feature_counts"]["hole"]["unit"] == "validated_features"
    assert {gap["code"] for gap in count["gaps"]} == {"GENERAL_FEATURE_COUNT_UNKNOWN"}
    assert len(geometry["geometry"]) == 1
    assert geometry["geometry"][0]["radius_mm"] == 3.0
    assert geometry["geometry"][0]["length_mm"] == 10.0
    assert {gap["code"] for gap in geometry["gaps"]} == {"GENERAL_FEATURE_GEOMETRY_INCOMPLETE"}


def test_ask_parses_chinese_spatial_locate_question(tmp_path):
    path = tmp_path / "spatial.step"
    write_assembly(
        path,
        sizes_mm=((10.0, 10.0, 10.0),) * 3,
        names=("Left door", "Reference", "Right door"),
        occurrence_names=("Left door", "Reference", "Right door"),
    )

    exit_code, result = _run(["ask", str(path), "--question", "左侧的门在哪里？"])

    assert exit_code == 0, result
    report = result["answer"]
    assert report["status"] == "answered"
    assert report["question"]["interpretation_basis"] == "deterministic_grammar"
    assert report["question"]["assumptions"]
    answer = report["answers"][0]
    assert answer["resolution"]["status"] == "resolved"
    assert answer["resolution"]["resolved_target"]["name"] == "Left door"
    selector = report["question"]["interpretations"][0]["selector"]
    assert selector["name_contains_any"] == ["door", "门"]
    assert selector["spatial"][0]["relation"] == "left_of"
    assert selector["spatial"][0]["reference"] == {
        "occurrence_id": None,
        "path": None,
        "name": None,
        "name_contains": None,
        "name_contains_any": None,
        "definition_id": None,
        "is_assembly": None,
        "is_root": True,
        "state": None,
        "spatial": [],
    }
    assert selector["spatial"][0]["frame"]["preset"] == "front"


def test_ask_natural_language_orientation_stays_assumed(tmp_path):
    path = tmp_path / "orientation.step"
    write_assembly(
        path,
        sizes_mm=((2.0, 30.0, 40.0), (10.0, 10.0, 10.0)),
        names=("Door Panel", "Other"),
        occurrence_names=("Door Panel", "Other"),
    )

    exit_code, result = _run(["ask", str(path), "--question", "门的正面是哪边？"])

    assert exit_code == 0
    report = result["answer"]
    assert report["status"] == "partial"
    answer = report["answers"][0]
    assert answer["orientation"]["status"] == "resolved"
    assert answer["orientation"]["semantic_status"] == "assumed"
    assert answer["orientation"]["selected_candidate"]["camera"]["preset"] == "left"
    assert answer["orientation"]["recommended_view"]["semantic_intent"]["basis"] == "assumed"
    assert {gap["code"] for gap in answer["gaps"]} == {"DESIGN_FRONT_DECLARATION_UNAVAILABLE"}


def test_ask_natural_language_feature_count_and_unsupported_question(tmp_path):
    path = tmp_path / "features.step"
    write_feature_assembly(path)

    count_code, count_result = _run(["ask", str(path), "--question", "有多少个孔？"])
    unsupported_code, unsupported = _run(["ask", str(path), "--question", "维护性怎么样？"])

    assert count_code == 0
    assert count_result["answer"]["status"] == "partial"
    assert count_result["answer"]["answers"][0]["feature_counts"]["hole"]["value"] == 1
    assert unsupported_code == 0
    assert unsupported["answer"]["status"] == "unsupported"
    assert unsupported["answer"]["answers"] == []
    assert unsupported["answer"]["gaps"][0]["code"] == "QUESTION_INTERPRETATION_UNSUPPORTED"


def test_ask_english_compound_geometry_and_explicit_candidate_policy(tmp_path):
    path = tmp_path / "features.step"
    write_feature_assembly(path)

    compound_code, compound = _run([
        "ask", str(path), "--question",
        "How many holes are there, and what are their sizes and shapes?",
    ])
    spec = tmp_path / "candidates.json"
    spec.write_text(json.dumps({
        "original_text": "Count name-based door and window candidates, not validated features",
        "interpretation_basis": "user_supplied",
        "interpretations": [{
            "interpretation_id": "candidate-count",
            "intent": "feature_count",
            "feature_kinds": ["door", "window"],
            "evidence_policy": "candidates_allowed",
        }],
    }), encoding="utf-8")
    candidate_code, candidates = _run(["ask", str(path), "--spec", str(spec)])

    assert compound_code == 0
    assert compound["answer"]["status"] == "partial"
    assert [item["interpretation_id"] for item in compound["answer"]["answers"]] == [
        "feature-count", "feature-geometry"
    ]
    assert compound["answer"]["answers"][0]["feature_counts"]["hole"]["value"] == 1
    assert compound["answer"]["answers"][1]["geometry"][0]["radius_mm"] == 3.0
    assert candidate_code == 0
    assert candidates["answer"]["status"] == "answered"
    counts = candidates["answer"]["answers"][0]["feature_counts"]
    assert counts["door"]["value"] == 1
    assert counts["door"]["state"] == "candidate"
    assert counts["door"]["unit"] == "feature_candidates"
    assert counts["door"]["evidence_refs"]
    assert counts["window"]["value"] == 1
    assert counts["window"]["state"] == "candidate"
    assert candidates["answer"]["answers"][0]["gaps"] == []


def test_ask_does_not_invent_a_near_distance(tmp_path):
    path = tmp_path / "features.step"
    write_feature_assembly(path)

    exit_code, result = _run([
        "ask", str(path), "--question", "Where is the door near the window?"
    ])

    assert exit_code == 0
    assert result["answer"]["status"] == "unsupported"
    assert "max_distance_mm" in result["answer"]["gaps"][0]["message"]


def test_ask_failed_read_does_not_turn_unknown_counts_into_zero(tmp_path):
    path = tmp_path / "broken.step"
    path.write_text(
        "ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n",
        encoding="ascii",
    )

    hole_code, holes = _run(["ask", str(path), "--question", "有多少个孔？"])
    spec = tmp_path / "occurrences.json"
    spec.write_text(json.dumps({
        "original_text": "How many door occurrences are present?",
        "interpretation_basis": "user_supplied",
        "interpretations": [{
            "interpretation_id": "doors",
            "intent": "occurrence_count",
            "selector": {"name_contains": "door"},
        }],
    }), encoding="utf-8")
    occurrence_code, occurrences = _run(["ask", str(path), "--spec", str(spec)])

    assert hole_code == 0
    hole_answer = holes["answer"]["answers"][0]
    assert holes["answer"]["status"] == "failed"
    assert hole_answer["feature_counts"]["hole"]["value"] is None
    assert hole_answer["feature_counts"]["hole"]["state"] == "unknown"
    assert "FEATURE_EXECUTION_FAILED" in {gap["code"] for gap in hole_answer["gaps"]}
    assert occurrence_code == 0
    occurrence_answer = occurrences["answer"]["answers"][0]
    assert occurrences["answer"]["status"] == "failed"
    assert occurrence_answer["occurrence_count"]["value"] is None
    assert occurrence_answer["occurrence_count"]["state"] == "unknown"




