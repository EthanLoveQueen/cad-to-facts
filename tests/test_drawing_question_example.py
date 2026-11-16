import contextlib
import hashlib
import io
import json
from pathlib import Path

from cad_to_facts import cli
from cad_to_facts.domain.drawing_question import DrawingQuestionSpec


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "examples" / "question-drawing.dxf"
SPEC = ROOT / "examples" / "drawing-question.json"


def _run(arguments):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = cli.main(arguments)
    return exit_code, json.loads(output.getvalue())


def test_public_drawing_question_example_runs_end_to_end():
    before = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    spec = DrawingQuestionSpec.model_validate(json.loads(SPEC.read_text(encoding="utf-8")))

    exit_code, result = _run(["ask", str(SOURCE), "--spec", str(SPEC)])

    assert exit_code == 0
    report = result["answer"]
    assert report["profile"] == "drawing"
    assert report["status"] == "answered"
    assert report["complete"] is True
    assert report["question"]["original_text"] == spec.original_text
    assert report["question"]["question_id"] != "0" * 64
    answers = {answer["interpretation_id"]: answer for answer in report["answers"]}

    assert answers["model-line-count"]["count"]["value"] == 4
    assert answers["model-line-count"]["count"]["state"] == "known"
    assert answers["visible-line-count"]["count"]["value"] == 2
    assert answers["visible-line-count"]["count"]["excluded_by_layer_state"] == 2
    assert answers["model-line-length"]["measurements"]["total"] == 26.0
    assert answers["model-line-length"]["measurements"]["state"] == "known"
    layers = {layer["name"]: layer for layer in answers["layer-inventory"]["layers"]}
    assert layers["Hidden"]["off"] is True
    assert layers["Frozen"]["frozen"] is True
    blocks = {block["name"]: block for block in answers["block-inventory"]["blocks"]}
    assert blocks["DOOR"]["definition_entity_count"] == 4
    assert blocks["DOOR"]["insert_entity_count"] == 2
    assert blocks["TITLE"]["insert_entity_count"] == 1
    texts = answers["steel-text"]["entities"]
    assert {entity["kind"] for entity in texts} == {"mtext", "attrib"}
    assert {entity["text"] for entity in texts} == {"材料: STEEL", "STEEL"}
    dimensions = answers["dimension-inventory"]["dimensions"]
    assert dimensions["valued_count"] == 1
    assert dimensions["dimensions"][0]["measurement"] == 10.0
    assert dimensions["dimensions"][0]["unit"] == "mm"
    candidates = answers["door-name-candidates"]["candidates"]
    assert candidates["state"] == "candidate"
    assert candidates["validation"] == "unvalidated"
    assert candidates["value"] == 3
    semantic = answers["semantic-evidence"]["semantic_evidence"]
    assert semantic["state"] == "candidate"
    assert semantic["validation"] == "unvalidated"
    assert semantic["general_semantic_coverage"] == "unknown"
    assert semantic["value"] == 9
    assert semantic["by_basis"] == {
        "block_name": 3,
        "layer_name": 2,
        "text": 3,
        "attribute_tag": 4,
    }
    assert semantic["attributed_insert_count"] == 1
    title_context = next(
        item for item in semantic["evidence"]
        if item["block_name"] == "TITLE"
    )
    assert title_context["attributes"] == {
        "PART": ["A-123"],
        "MATERIAL": ["STEEL"],
        "QTY": ["2"],
    }
    assert {gap["code"] for gap in answers["semantic-evidence"]["gaps"]} >= {
        "SEMANTIC_CANDIDATES_UNVALIDATED",
        "SEMANTIC_CONTEXT_DECLARED_ONLY",
        "SEMANTIC_COVERAGE_UNKNOWN",
    }
    bom = answers["title-block-bom"]["bom"]
    assert bom["complete"] is True
    assert [(item["part_number"], item["quantity"]) for item in bom["line_items"]] == [
        ("A-123", 2)
    ]
    assert answers["door-name-candidates"]["status"] == "answered"
    assert {gap["code"] for gap in answers["door-name-candidates"]["gaps"]} >= {
        "SEMANTIC_CANDIDATES_UNVALIDATED",
        "SEMANTIC_COVERAGE_UNKNOWN",
    }
    assert answers["block-inventory"]["gaps"][0]["code"] == "INSERT_GEOMETRY_NOT_EXPANDED"
    assert answers["dimension-inventory"]["gaps"][0]["code"] == (
        "DIMENSION_GEOMETRY_ASSOCIATION_UNSUPPORTED"
    )

    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == before
