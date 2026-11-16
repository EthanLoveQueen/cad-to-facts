import math

import pytest

from cad_to_facts.artifact import register
from cad_to_facts.domain.facts import ExtractionQuery, FactRequest
from cad_to_facts.drawing_facts import default_requests
from cad_to_facts.facts import extract
from cad_to_facts.snapshot import read

from drawing_helpers import (
    write_drawing,
    write_drawing_with_title_block,
    write_unitless_line,
)


def _entity(snapshot, dxf_type, container):
    return next(
        entity
        for entity in snapshot.entities
        if any(
            ref == {"type": "dxf_type", "value": dxf_type}
            for ref in entity.native_refs
        )
        and any(
            ref == {"type": "container", "value": container}
            for ref in entity.native_refs
        )
    )


def _extract(snapshot, entity, predicate):
    return extract(
        snapshot,
        ExtractionQuery(
            requests=[FactRequest(name=predicate, predicate=predicate, subject_id=entity.entity_id)]
        ),
    )


def test_dxf_snapshot_preserves_drawing_structure_and_native_handles(tmp_path):
    path = tmp_path / "drawing.dxf"
    write_drawing(path)

    artifact = register(path)
    snapshot = read(artifact)

    assert artifact.format == "dxf"
    assert snapshot.adapter_id == "ezdxf-drawing"
    assert snapshot.status == "ready"
    assert snapshot.entity_discovery == "complete"
    assert snapshot.units["length"] == "mm"
    assert snapshot.parse_options["read_scope"] == "drawing"
    assert snapshot.drawing.dxf_version == "AC1032"
    assert snapshot.drawing.source_format == "dxf"
    assert snapshot.drawing.conversion is None
    assert {layer.name for layer in snapshot.drawing.layers} >= {"Geometry", "Annotation"}
    layouts = {layout.name: layout for layout in snapshot.drawing.layouts}
    assert layouts["Model"].kind == "model_space"
    assert layouts["Layout1"].kind == "paper_space"
    assert len(layouts["Model"].entity_ids) == 5
    assert len(layouts["Layout1"].entity_ids) == 1
    block = next(block for block in snapshot.drawing.blocks if block.name == "Detail")
    assert len(block.entity_ids) == 1
    assert len(snapshot.entities) == 7
    line = _entity(snapshot, "LINE", "Model")
    assert line.entity_kind == "line"
    assert any(ref["type"] == "handle" and ref["value"] for ref in line.native_refs)


def test_dxf_declared_and_measured_facts_use_explicit_units(tmp_path):
    path = tmp_path / "drawing.dxf"
    write_drawing(path)
    snapshot = read(register(path))

    cases = [
        ("LINE", "Model", "length", 5.0, "mm", "measured"),
        ("TEXT", "Model", "text", "PART-A", "dimensionless", "declared"),
        ("TEXT", "Model", "layer", "Annotation", "dimensionless", "declared"),
        ("INSERT", "Model", "block_name", "Detail", "dimensionless", "declared"),
        ("CIRCLE", "Model", "area", math.pi * 4, "mm^2", "measured"),
        ("LWPOLYLINE", "Model", "length", 60.0, "mm", "measured"),
        ("LWPOLYLINE", "Model", "area", 200.0, "mm^2", "measured"),
        ("LINE", "Detail", "length", 2.0, "mm", "measured"),
    ]
    for dxf_type, container, predicate, expected, unit, kind in cases:
        factset = _extract(snapshot, _entity(snapshot, dxf_type, container), predicate)
        assert factset.gaps == []
        assert len(factset.facts) == 1
        fact = factset.facts[0]
        assert fact.value == pytest.approx(expected) if isinstance(expected, float) else fact.value == expected
        assert fact.unit == unit
        assert fact.kind == kind
        assert fact.method.library == "ezdxf"


def test_insert_attribute_values_and_tags_are_cataloged(tmp_path):
    path = tmp_path / "title-block.dxf"
    write_drawing_with_title_block(path)
    snapshot = read(register(path))

    assert snapshot.status == "ready"
    assert snapshot.entity_discovery == "complete"
    attribs = [entity for entity in snapshot.entities if entity.entity_kind == "attrib"]
    assert len(attribs) == 2
    for entity in attribs:
        assert any(
            ref["type"] == "container" and ref["value"] == "Model"
            for ref in entity.native_refs
        )

    factset = extract(snapshot, default_requests(snapshot, snapshot.entities))
    assert factset.gaps == []
    texts = {fact.value for fact in factset.facts if fact.predicate == "text"}
    tags = {fact.value for fact in factset.facts if fact.predicate == "attribute_tag"}
    assert {"A-123", "STEEL"} <= texts
    assert {"PART", "MATERIAL"} <= tags


@pytest.mark.parametrize(
    "prefix",
    [b"\xef\xbb\xbf", b"999\nExported by test\n"],
    ids=["utf8-bom", "leading-comment"],
)
def test_dxf_preamble_variants_are_recognized_and_parsed(tmp_path, prefix):
    path = tmp_path / "preamble.dxf"
    write_drawing(path)
    path.write_bytes(prefix + path.read_bytes())

    artifact = register(path)
    snapshot = read(artifact)

    assert artifact.format == "dxf"
    assert snapshot.status == "ready"
    assert len(snapshot.entities) == 7


def test_unitless_drawing_keeps_declared_facts_but_blocks_length(tmp_path):
    path = tmp_path / "unitless.dxf"
    write_unitless_line(path)
    snapshot = read(register(path))
    line = _entity(snapshot, "LINE", "Model")

    length = _extract(snapshot, line, "length")
    layer = _extract(snapshot, line, "layer")

    assert snapshot.units["length"] == "unitless"
    assert [gap.reason_code for gap in length.gaps] == ["UNKNOWN_UNIT"]
    assert length.facts == []
    assert layer.facts[0].value == "0"


def test_unsupported_step_volume_predicate_is_not_reused_for_drawings(tmp_path):
    path = tmp_path / "drawing.dxf"
    write_drawing(path)
    snapshot = read(register(path))

    factset = _extract(snapshot, _entity(snapshot, "CIRCLE", "Model"), "volume")

    assert factset.facts == []
    assert [gap.reason_code for gap in factset.gaps] == ["UNSUPPORTED"]


def test_source_supplied_provenance_xdata_cannot_spoof_artifact_or_units(tmp_path):
    import ezdxf

    path = tmp_path / "spoofed.dxf"
    doc = ezdxf.new("R2018", units=4)
    doc.appids.add("CAD_TO_FACTS")
    line = doc.modelspace().add_line((0, 0), (3, 4))
    line.set_xdata("CAD_TO_FACTS", [(1000, "0" * 64), (1000, "in"), (1000, "bad")])
    doc.saveas(path)

    artifact = register(path)
    snapshot = read(artifact)
    entity = _entity(snapshot, "LINE", "Model")
    factset = _extract(snapshot, entity, "length")

    assert factset.facts[0].value == 5.0
    assert factset.facts[0].evidence.artifact_sha256 == artifact.sha256
    native = {item["type"]: item["value"] for item in entity.native_refs}
    assert native["source_artifact_sha256"] == artifact.sha256
    assert native["source_length_unit"] == "mm"


def test_unresolved_external_reference_prevents_complete_discovery(tmp_path):
    path = tmp_path / "xref.dxf"
    write_drawing(path)
    import ezdxf

    doc = ezdxf.readfile(path)
    block = doc.blocks.new("External")
    block.block.dxf.flags = 4
    block.block.dxf.xref_path = "missing-reference.dwg"
    doc.saveas(path)

    snapshot = read(register(path))

    assert snapshot.status == "partial"
    assert snapshot.entity_discovery == "partial"
    assert any(item.code == "DRAWING_EXTERNAL_REFERENCE" for item in snapshot.diagnostics)


@pytest.mark.parametrize("bulge", [1.0, -1.0])
def test_curved_lwpolyline_uses_exact_bulge_arc_geometry(tmp_path, bulge):
    import ezdxf

    path = tmp_path / "curved.dxf"
    doc = ezdxf.new("R2018", units=4)
    # Two semicircles with radius 1 form a complete circle of area pi.
    doc.modelspace().add_lwpolyline(
        [(0, 0, 0, 0, bulge), (2, 0, 0, 0, bulge)],
        format="xyseb",
        close=True,
    )
    doc.saveas(path)
    snapshot = read(register(path))
    polyline = _entity(snapshot, "LWPOLYLINE", "Model")

    expected = {"length": 2 * math.pi, "area": math.pi}
    for predicate, value in expected.items():
        factset = _extract(snapshot, polyline, predicate)
        assert factset.gaps == []
        assert len(factset.facts) == 1
        assert factset.facts[0].value == pytest.approx(value, abs=1e-12)
        assert "bulge" in factset.facts[0].method.algorithm.lower()


def test_linked_xref_preserves_independent_source_artifact(tmp_path):
    import ezdxf
    from ezdxf import xref

    child = tmp_path / "child.dxf"
    child_doc = ezdxf.new("R2018", units=4)
    child_doc.modelspace().add_line((0, 0), (3, 4))
    child_doc.saveas(child)
    host = tmp_path / "host.dxf"
    write_drawing(host)
    host_doc = ezdxf.readfile(host)
    xref.attach(host_doc, block_name="CHILD", filename=str(child))
    host_doc.saveas(host)

    host_artifact = register(host)
    snapshot = read(host_artifact, {"xref_mode": "linked", "xref_roots": [str(tmp_path)]})

    assert snapshot.status == "ready"
    assert snapshot.entity_discovery == "complete"
    assert len(snapshot.entities) == 8  # the new INSERT, not the child's LINE
    reference = snapshot.drawing.external_references[0]
    assert reference.state == "resolved"
    assert reference.owner_artifact_sha256 == host_artifact.sha256
    assert reference.artifact.sha256 == register(child).sha256
    assert reference.entity_count == 1
    assert reference.entity_discovery == "complete"


def test_xref_resolution_rejects_paths_outside_explicit_roots(tmp_path):
    import ezdxf
    from ezdxf import xref

    child = tmp_path / "child.dxf"
    ezdxf.new("R2018").saveas(child)
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    host = allowed / "host.dxf"
    host_doc = ezdxf.new("R2018")
    xref.attach(host_doc, block_name="CHILD", filename="../child.dxf")
    host_doc.saveas(host)

    snapshot = read(register(host), {"xref_mode": "linked", "xref_roots": [str(allowed)]})

    assert snapshot.entity_discovery == "partial"
    assert snapshot.drawing.external_references[0].state == "outside_root"
    assert any(item.code == "DRAWING_EXTERNAL_REFERENCE" for item in snapshot.diagnostics)


def test_flattened_xref_facts_keep_child_hash_and_convert_child_units(tmp_path):
    import ezdxf
    from ezdxf import xref

    child = tmp_path / "child.dxf"
    child_doc = ezdxf.new("R2018", units=5)  # centimetres
    child_doc.modelspace().add_line((0, 0), (3, 4))
    child_doc.saveas(child)
    child_artifact = register(child)
    host = tmp_path / "host.dxf"
    host_doc = ezdxf.new("R2018", units=4)
    xref.attach(host_doc, block_name="CHILD", filename=str(child))
    host_doc.saveas(host)

    snapshot = read(
        register(host), {"xref_mode": "flatten", "xref_roots": [str(tmp_path)]}
    )

    assert snapshot.status == "ready"
    assert snapshot.entity_discovery == "complete"
    line = _entity(snapshot, "LINE", "CHILD")
    factset = _extract(snapshot, line, "length")
    assert factset.gaps == []
    assert factset.facts[0].value == pytest.approx(50.0)
    assert factset.facts[0].evidence.artifact_sha256 == child_artifact.sha256
    native = {item["type"]: item["value"] for item in line.native_refs}
    assert native["source_artifact_sha256"] == child_artifact.sha256
    assert native["source_length_unit"] == "cm"
    assert snapshot.drawing.blocks[-1].is_xref is True


def test_flattened_unitless_xref_does_not_inherit_host_units(tmp_path):
    import ezdxf
    from ezdxf import xref

    child = tmp_path / "child.dxf"
    child_doc = ezdxf.new("R2018", units=0)
    child_doc.modelspace().add_line((0, 0), (3, 4))
    child_doc.saveas(child)
    host = tmp_path / "host.dxf"
    host_doc = ezdxf.new("R2018", units=4)
    xref.attach(host_doc, block_name="CHILD", filename=str(child))
    host_doc.saveas(host)

    snapshot = read(
        register(host), {"xref_mode": "flatten", "xref_roots": [str(tmp_path)]}
    )
    line = _entity(snapshot, "LINE", "CHILD")
    factset = _extract(snapshot, line, "length")

    assert factset.facts == []
    assert [gap.reason_code for gap in factset.gaps] == ["UNKNOWN_UNIT"]
    assert factset.gaps[0].evidence.artifact_sha256 == register(child).sha256


def test_xref_byte_and_depth_budgets_are_enforced(tmp_path):
    import ezdxf
    from ezdxf import xref

    grandchild = tmp_path / "grandchild.dxf"
    ezdxf.new("R2018").saveas(grandchild)
    child = tmp_path / "child.dxf"
    child_doc = ezdxf.new("R2018")
    xref.attach(child_doc, block_name="GRANDCHILD", filename=str(grandchild))
    child_doc.saveas(child)
    host = tmp_path / "host.dxf"
    host_doc = ezdxf.new("R2018")
    xref.attach(host_doc, block_name="CHILD", filename=str(child))
    host_doc.saveas(host)

    limited_depth = read(register(host), {
        "xref_mode": "linked", "xref_roots": [str(tmp_path)], "xref_max_depth": 0,
    })
    assert [item.state for item in limited_depth.drawing.external_references] == [
        "resolved", "limit_exceeded",
    ]
    limited_bytes = read(register(host), {
        "xref_mode": "linked", "xref_roots": [str(tmp_path)],
        "xref_max_bytes": child.stat().st_size - 1,
    })
    assert limited_bytes.drawing.external_references[0].state == "limit_exceeded"
    assert limited_bytes.entity_discovery == "partial"


def test_xref_cycles_stay_partial(tmp_path):
    import ezdxf
    from ezdxf import xref

    first = tmp_path / "first.dxf"
    second = tmp_path / "second.dxf"
    second_doc = ezdxf.new("R2018")
    xref.attach(second_doc, block_name="FIRST", filename=str(first))
    second_doc.saveas(second)
    first_doc = ezdxf.new("R2018")
    xref.attach(first_doc, block_name="SECOND", filename=str(second))
    first_doc.saveas(first)

    snapshot = read(
        register(first), {"xref_mode": "linked", "xref_roots": [str(tmp_path)]}
    )

    states = [item.state for item in snapshot.drawing.external_references]
    assert states == ["resolved", "cycle"]
    assert snapshot.entity_discovery == "partial"
    assert snapshot.drawing.external_references[1].parent_reference_id == "xref:0"


def test_truncated_dxf_recovery_cannot_claim_entity_discovery(tmp_path):
    path = tmp_path / "malformed.dxf"
    path.write_text("0\nSECTION\n2\nENTITIES\n0\nLINE\n", encoding="ascii")

    snapshot = read(register(path))

    assert snapshot.status == "partial"
    assert snapshot.entity_discovery == "unknown"
    assert snapshot.entities == []
    assert "NO_DRAWING_ENTITIES" in {item.code for item in snapshot.diagnostics}


def test_dwg_without_explicit_available_converter_returns_adapter_unavailable(tmp_path):
    path = tmp_path / "drawing.dwg"
    path.write_bytes(b"AC1032\r\nnot-a-real-model")

    artifact = register(path)
    snapshot = read(artifact, {"oda_executable": str(tmp_path / "missing.exe")})

    assert artifact.format == "dwg"
    assert snapshot.status == "failed"
    assert snapshot.entity_discovery == "unknown"
    assert [item.code for item in snapshot.diagnostics] == ["ADAPTER_UNAVAILABLE"]


def test_dwg_without_configured_converter_never_searches_install_locations(tmp_path):
    path = tmp_path / "drawing.dwg"
    path.write_bytes(b"AC1032\r\nnot-a-real-model")

    snapshot = read(register(path))

    assert snapshot.status == "failed"
    assert snapshot.entity_discovery == "unknown"
    assert snapshot.entities == []
    assert [item.code for item in snapshot.diagnostics] == ["ADAPTER_UNAVAILABLE"]
    assert "install locations are not searched automatically" in snapshot.diagnostics[0].message


def test_dwg_with_unusable_converter_reports_conversion_failure(tmp_path):
    path = tmp_path / "drawing.dwg"
    path.write_bytes(b"AC1032\r\nnot-a-real-model")
    converter = tmp_path / "fake-oda.exe"
    converter.write_text("not an executable", encoding="ascii")

    snapshot = read(register(path), {"oda_executable": str(converter)})

    assert snapshot.status == "failed"
    assert snapshot.entity_discovery == "unknown"
    assert snapshot.entities == []
    assert [item.code for item in snapshot.diagnostics] == ["CONVERSION_FAILED"]
