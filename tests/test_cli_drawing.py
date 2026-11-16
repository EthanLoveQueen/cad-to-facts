import contextlib
import io
import json

import ezdxf

from cad_to_facts import cli

from drawing_helpers import write_drawing


def test_cli_stdout_is_utf8_for_non_ascii_drawing_text(tmp_path):
    path = tmp_path / "cn.dxf"
    doc = ezdxf.new("R2018", units=4)
    doc.modelspace().add_text("零件A", dxfattribs={"layer": "标注"})
    doc.saveas(path)

    raw = io.BytesIO()
    wrapper = io.TextIOWrapper(raw, encoding="gbk", write_through=True)
    with contextlib.redirect_stdout(wrapper):
        exit_code = cli.main(["inspect", str(path)])
    wrapper.flush()

    text = raw.getvalue().decode("utf-8")
    assert exit_code == 0
    assert "零件A" in text
    assert "标注" in text


def _run(arguments):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = cli.main(arguments)
    return exit_code, json.loads(output.getvalue())


def test_cli_query_rejects_zero_page_size(tmp_path):
    path = tmp_path / "drawing.dxf"
    write_drawing(path)

    exit_code, result = _run(["query", str(path), "--limit", "0"])

    assert exit_code == 2
    assert "positive" in result["error"]["message"]


def test_cli_render_ignores_external_raster_images(tmp_path):
    path = tmp_path / "image.dxf"
    output = tmp_path / "image.svg"
    doc = ezdxf.new("R2018", units=4)
    image = doc.add_image_def("not-authorized-secret.jpg", size_in_pixel=(1, 1))
    doc.modelspace().add_image(image, (0, 0), size_in_units=(10, 10))
    doc.saveas(path)

    exit_code, result = _run(["render", str(path), "--output", str(output)])

    assert exit_code == 0
    assert "not-authorized-secret.jpg" not in output.read_text(encoding="utf-8")


def test_cli_summary_omits_entity_catalog_and_reports_counts(tmp_path):
    path = tmp_path / "drawing.dxf"
    write_drawing(path)

    exit_code, result = _run(["inspect", str(path), "--summary"])

    assert exit_code == 0
    assert "factset" not in result
    assert "entities" not in result["snapshot"]
    drawing = result["snapshot"]["drawing"]
    assert drawing["entity_count"] == 7
    assert drawing["entity_kind_counts"] == {"line": 2, "text": 2, "circle": 1, "lwpolyline": 1, "insert": 1}
    assert {item["name"]: item["entity_count"] for item in drawing["layouts"]} == {
        "Layout1": 1,
        "Model": 5,
    }
    assert drawing["blocks"] == [
        {"name": "Detail", "entity_count": 1, "is_xref": False, "xref_path": None}
    ]


def test_cli_query_filters_and_paginates_without_dumping_catalog(tmp_path):
    path = tmp_path / "drawing.dxf"
    write_drawing(path)

    first_code, first = _run(["query", str(path), "--kind", "line", "--limit", "1"])
    second_code, second = _run(
        ["query", str(path), "--kind", "line", "--limit", "1", "--cursor", first["selection"]["next_cursor"]]
    )

    assert first_code == second_code == 0
    assert "entities" not in first["snapshot"]
    assert first["selection"]["matched_total"] == 2
    assert first["selection"]["truncated"] is True
    assert first["entities"][0]["native_refs"][1]["value"] == "Model"
    assert second["selection"]["matched_total"] == 2
    assert second["selection"]["truncated"] is False
    assert second["entities"][0]["native_refs"][1]["value"] == "Detail"
    assert next(fact for fact in second["factset"]["facts"] if fact["predicate"] == "length")["value"] == 2.0

    code, filtered = _run(
        ["query", str(path), "--kind", "line", "--layer", "Geometry", "--container", "Model"]
    )
    assert code == 0
    assert filtered["selection"]["matched_total"] == 1
    assert next(fact for fact in filtered["factset"]["facts"] if fact["predicate"] == "length")["value"] == 5.0

    code, text = _run(["query", str(path), "--text", "PART-A"])
    assert code == 0
    assert [item["entity_kind"] for item in text["entities"]] == ["text"]


def test_cli_rejects_invalid_query_cursor(tmp_path):
    path = tmp_path / "drawing.dxf"
    write_drawing(path)

    exit_code, result = _run(["query", str(path), "--cursor", "drawing:999"])

    assert exit_code == 2
    assert "cursor" in result["error"]["message"]


def test_cli_renders_new_svg_without_overwriting_output(tmp_path):
    import hashlib

    path = tmp_path / "drawing.dxf"
    output = tmp_path / "drawing.svg"
    write_drawing(path)

    exit_code, result = _run(["render", str(path), "--output", str(output)])

    assert exit_code == 0
    content = output.read_bytes()
    assert b"<svg" in content
    assert result["output"]["layout"] == "Model"
    assert result["output"]["sha256"] == hashlib.sha256(content).hexdigest()
    assert result["output"]["size_bytes"] == len(content)

    second_code, second = _run(["render", str(path), "--output", str(output)])
    assert second_code == 2
    assert "exists" in second["error"]["message"].lower()


def _write_bom_drawing(path, quantities=None):
    doc = ezdxf.new("R2018", units=4)
    block = doc.blocks.new("PART_BLOCK")
    block.add_attdef("PART", (0, 0))
    block.add_attdef("MATERIAL", (0, 5))
    block.add_attdef("QTY", (0, 10))
    quantities = quantities or [None, None]
    for index, quantity in enumerate(quantities):
        reference = doc.modelspace().add_blockref("PART_BLOCK", (index * 20, 0))
        reference.add_attrib("PART", "A-123", (0, 0))
        reference.add_attrib("MATERIAL", "STEEL", (0, 5))
        if quantity is not None:
            reference.add_attrib("QTY", quantity, (0, 10))
    doc.saveas(path)


def test_cli_drawing_bom_counts_explicit_part_attributes(tmp_path):
    path = tmp_path / "bom.dxf"
    _write_bom_drawing(path)

    exit_code, result = _run([
        "drawing-bom", str(path), "--part-tag", "PART",
        "--material-tag", "MATERIAL", "--require-tag", "MATERIAL",
    ])

    assert exit_code == 0
    assert result["complete"] is True
    assert len(result["line_items"]) == 1
    line = result["line_items"][0]
    assert line["part_number"] == "A-123"
    assert line["declared_properties"]["MATERIAL"] == "STEEL"
    assert line["quantity"] == 2
    assert line["quantity_state"] == "known"
    assert len(line["occurrence_refs"]) == 2
    assert result["coverage"]["occurrence_total"] == 2
    assert result["coverage"]["known_quantity_definition_total"] == 1
    assert result["coverage"]["observed_quantity_definition_total"] == 0
    assert result["coverage"]["unknown_quantity_definition_total"] == 0
    assert (
        result["coverage"]["known_quantity_definition_total"]
        + result["coverage"]["observed_quantity_definition_total"]
        + result["coverage"]["unknown_quantity_definition_total"]
        == result["coverage"]["definition_total"]
    )


def test_cli_drawing_bom_counts_minsert_array_instances(tmp_path):
    path = tmp_path / "minsert.dxf"
    doc = ezdxf.new("R2018", units=4)
    block = doc.blocks.new("PART_BLOCK")
    block.add_attdef("PART", (0, 0))
    reference = doc.modelspace().add_blockref(
        "PART_BLOCK",
        (0, 0),
        dxfattribs={
            "row_count": 2,
            "column_count": 3,
            "row_spacing": 10,
            "column_spacing": 10,
        },
    )
    reference.add_attrib("PART", "A-123", (0, 0))
    doc.saveas(path)

    exit_code, result = _run(["drawing-bom", str(path), "--part-tag", "PART"])

    assert exit_code == 0
    assert result["line_items"][0]["quantity"] == 6
    assert result["occurrences"][0]["instance_count"] == 6


def test_cli_drawing_bom_sums_valid_declared_quantities_without_property_conflict(tmp_path):
    path = tmp_path / "bom.dxf"
    _write_bom_drawing(path, quantities=["2", "3"])

    exit_code, result = _run([
        "drawing-bom", str(path), "--part-tag", "PART", "--quantity-tag", "QTY"
    ])

    assert exit_code == 0
    assert result["line_items"][0]["quantity"] == 5
    assert result["line_items"][0]["property_conflicts"] == []
    assert result["complete"] is True


def _write_minsert(path, attributes):
    doc = ezdxf.new("R2018", units=4)
    block = doc.blocks.new("PART_BLOCK")
    block.add_attdef("PART", (0, 0))
    reference = doc.modelspace().add_blockref("PART_BLOCK", (0, 0), dxfattribs=attributes)
    reference.add_attrib("PART", "A-123", (0, 0))
    doc.saveas(path)


def test_cli_drawing_bom_invalid_zero_minsert_count_is_unknown(tmp_path):
    path = tmp_path / "invalid-zero-minsert.dxf"
    _write_minsert(
        path,
        {"row_count": 1, "column_count": 1, "row_spacing": 10, "column_spacing": 10},
    )
    # ezdxf omits default row/column counts when exporting. Inject a raw zero row
    # count so recovery exposes the malformed value instead of silently fixing the
    # fixture during save.
    content = path.read_text(encoding="utf-8")
    content = content.replace(
        " 45\n10.0\n  0\nATTRIB\n",
        " 45\n10.0\n 70\n0\n 71\n1\n  0\nATTRIB\n",
        1,
    )
    path.write_text(content, encoding="utf-8")

    exit_code, result = _run(["drawing-bom", str(path), "--part-tag", "PART"])

    assert exit_code == 0
    assert result["line_items"][0]["quantity"] is None
    assert result["line_items"][0]["quantity_state"] == "unknown"
    assert result["complete"] is False
    assert any(item["field"] == "instance_count" for item in result["missing_inputs"])


def test_cli_drawing_bom_zero_spacing_minsert_count_is_unknown(tmp_path):
    path = tmp_path / "zero-spacing-minsert.dxf"
    _write_minsert(
        path,
        {"row_count": 2, "column_count": 1, "row_spacing": 0, "column_spacing": 10},
    )

    exit_code, result = _run(["drawing-bom", str(path), "--part-tag", "PART"])

    assert exit_code == 0
    assert result["line_items"][0]["quantity"] is None
    assert result["line_items"][0]["quantity_state"] == "unknown"
    assert result["complete"] is False
    assert any(item["field"] == "instance_count" for item in result["missing_inputs"])


def test_cli_drawing_bom_linked_xref_exclusion_requires_explicit_acceptance(tmp_path):
    from ezdxf import xref

    child = tmp_path / "child.dxf"
    child_doc = ezdxf.new("R2018", units=4)
    child_doc.modelspace().add_line((0, 0), (1, 1))
    child_doc.saveas(child)
    host = tmp_path / "host.dxf"
    _write_bom_drawing(host)
    host_doc = ezdxf.readfile(host)
    xref.attach(host_doc, block_name="CHILD", filename=str(child))
    host_doc.saveas(host)

    base = [
        "drawing-bom", str(host), "--part-tag", "PART", "--material-tag", "MATERIAL",
        "--require-tag", "MATERIAL", "--xref-mode", "linked", "--xref-root", str(tmp_path),
    ]
    exit_code, result = _run(base)
    allowed_code, allowed = _run(base + ["--allow-xref-exclusion"])

    assert exit_code == allowed_code == 0
    assert result["complete"] is False
    assert result["coverage"]["uncounted_external_reference_total"] == 1
    assert allowed["complete"] is True


def test_cli_drawing_bom_flatten_counts_child_occurrences_with_child_evidence(tmp_path):
    import hashlib
    from ezdxf import xref

    child = tmp_path / "child.dxf"
    _write_bom_drawing(child)
    child_hash = hashlib.sha256(child.read_bytes()).hexdigest()
    host = tmp_path / "host.dxf"
    host_doc = ezdxf.new("R2018", units=4)
    xref.attach(host_doc, block_name="CHILD", filename=str(child))
    host_doc.saveas(host)

    exit_code, result = _run([
        "drawing-bom", str(host), "--part-tag", "PART",
        "--xref-mode", "flatten", "--xref-root", str(tmp_path),
        "--container", "CHILD",
    ])

    assert exit_code == 0
    assert result["complete"] is True
    assert result["line_items"][0]["quantity"] == 2
    assert result["line_items"][0]["source_artifact_sha256s"] == [child_hash]
    assert result["coverage"]["counted_external_reference_total"] == 1
    assert result["coverage"]["uncounted_external_reference_total"] == 0


def test_cli_drawing_bom_invalid_declared_quantity_is_unknown(tmp_path):
    path = tmp_path / "bom.dxf"
    _write_bom_drawing(path, quantities=["2", "bad"])

    exit_code, result = _run([
        "drawing-bom", str(path), "--part-tag", "PART", "--quantity-tag", "QTY"
    ])

    assert exit_code == 0
    line = result["line_items"][0]
    assert line["quantity"] is None
    assert line["quantity_state"] == "unknown"
    assert len(line["counted_occurrence_refs"]) == 1
    assert result["complete"] is False
    assert any(item["reason_code"] == "INVALID" for item in result["missing_inputs"])


def test_cli_query_supports_explicit_flattened_xrefs(tmp_path):
    from ezdxf import xref

    child = tmp_path / "child.dxf"
    child_doc = ezdxf.new("R2018", units=4)
    child_doc.modelspace().add_line((0, 0), (3, 4))
    child_doc.saveas(child)
    host = tmp_path / "host.dxf"
    host_doc = ezdxf.new("R2018", units=4)
    xref.attach(host_doc, block_name="CHILD", filename=str(child))
    host_doc.saveas(host)

    exit_code, result = _run([
        "query", str(host), "--kind", "line", "--xref-mode", "flatten",
        "--xref-root", str(tmp_path),
    ])

    assert exit_code == 0
    assert result["selection"]["matched_total"] == 1
    assert result["snapshot"]["drawing"]["external_references"][0]["state"] == "resolved"
    length = next(fact for fact in result["factset"]["facts"] if fact["predicate"] == "length")
    assert length["value"] == 5.0


def _write_line_review_inputs(tmp_path):
    inputs = {
        "requirements": {"requirements": [{
            "requirement_id": "req-line-length",
            "text": "Line length must be at least 5 mm",
            "source_ref": "test#req-line-length",
        }]},
        "rules": {"version": "1", "rules": [{
            "rule_id": "line-length",
            "version": "1",
            "requirement_refs": ["req-line-length"],
            "subject_selector": {"entity_kind": "line"},
            "applicability": {},
            "inputs": [{"name": "length", "predicate": "length"}],
            "checker": "numeric.compare",
            "parameters": {"operator": ">=", "threshold": 5.0, "unit": "mm", "abs_tol": 1e-9},
            "severity": "error",
            "source": {"reviewed_by": "test"},
        }]},
        "scope": {
            "included_rules": ["line-length"],
            "subject_selectors": [{"entity_kind": "line"}],
            "required_inputs": [],
            "discovery_requirements": ["line"],
        },
        "context": {"values": {}},
    }
    paths = {}
    for name, value in inputs.items():
        path = tmp_path / f"flatten-review-{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        paths[name] = path
    return paths


def test_cli_review_accepts_registered_flattened_xref_evidence(tmp_path):
    from ezdxf import xref

    child = tmp_path / "child.dxf"
    child_doc = ezdxf.new("R2018", units=4)
    child_doc.modelspace().add_line((0, 0), (3, 4))
    child_doc.saveas(child)
    host = tmp_path / "host.dxf"
    host_doc = ezdxf.new("R2018", units=4)
    xref.attach(host_doc, block_name="CHILD", filename=str(child))
    host_doc.saveas(host)
    paths = _write_line_review_inputs(tmp_path)

    exit_code, report = _run([
        "review", str(host), "--xref-mode", "flatten", "--xref-root", str(tmp_path),
        "--requirements", str(paths["requirements"]), "--rules", str(paths["rules"]),
        "--scope", str(paths["scope"]), "--context", str(paths["context"]),
    ])

    assert exit_code == 0
    assert report["overall_status"] == "compliant_for_scope"
    assert report["complete"] is True


def test_cli_inspects_dxf_without_step_solid_gaps(tmp_path):
    path = tmp_path / "drawing.dxf"
    write_drawing(path)

    exit_code, result = _run(["inspect", str(path)])

    assert exit_code == 0
    assert result["artifact"]["format"] == "dxf"
    assert result["snapshot"]["drawing"]["source_format"] == "dxf"
    assert result["selection"]["entity_total"] == 7
    assert result["selection"]["entities_returned"] == 7
    assert result["factset"]["gaps"] == []
    predicates = {fact["predicate"] for fact in result["factset"]["facts"]}
    assert {"entity_type", "layer", "container", "length", "area", "text", "block_name"} <= predicates
    assert "volume" not in predicates


def test_cli_reviews_dxf_line_length_with_existing_rule_contract(tmp_path):
    path = tmp_path / "drawing.dxf"
    write_drawing(path)
    inputs = {
        "requirements": {
            "requirements": [
                {
                    "requirement_id": "req-line-length",
                    "text": "Model-space line length must be 5 mm",
                    "source_ref": "test#req-line-length",
                }
            ]
        },
        "rules": {
            "version": "1",
            "rules": [
                {
                    "rule_id": "line-length",
                    "version": "1",
                    "requirement_refs": ["req-line-length"],
                    "subject_selector": {"entity_kind": "line"},
                    "applicability": {"fact_predicate": "container", "equals": "Model"},
                    "inputs": [{"name": "length", "predicate": "length"}],
                    "checker": "numeric.compare",
                    "parameters": {
                        "operator": ">=",
                        "threshold": 5.0,
                        "unit": "mm",
                        "abs_tol": 1e-9,
                    },
                    "severity": "error",
                    "source": {"reviewed_by": "test"},
                }
            ],
        },
        "scope": {
            "included_rules": ["line-length"],
            "subject_selectors": [{"entity_kind": "line"}],
            "required_inputs": [],
            "discovery_requirements": ["line"],
        },
        "context": {"values": {}},
    }
    paths = {}
    for name, value in inputs.items():
        input_path = tmp_path / f"{name}.json"
        input_path.write_text(json.dumps(value), encoding="utf-8")
        paths[name] = input_path

    exit_code, report = _run(
        [
            "review",
            str(path),
            "--requirements",
            str(paths["requirements"]),
            "--rules",
            str(paths["rules"]),
            "--scope",
            str(paths["scope"]),
            "--context",
            str(paths["context"]),
        ]
    )

    assert exit_code == 0
    assert report["overall_status"] == "compliant_for_scope"
    assert report["complete"] is True
    assert report["coverage"]["decision_required_entities"] == 1
    assert report["coverage"]["fully_inspected_entities"] == 1
