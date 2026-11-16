import pytest

from cad_to_facts.artifact import register
from cad_to_facts.domain.facts import ExtractionQuery, FactRequest
from cad_to_facts.facts import extract
from cad_to_facts.snapshot import read

from step_helpers import write_box


def test_inch_declaration_is_not_silently_read_as_millimetres(tmp_path):
    path = tmp_path / "one-inch.step"
    write_box(path, (25.4, 50.8, 25.4), "INCH")

    snapshot = read(register(path))
    factset = extract(
        snapshot,
        ExtractionQuery(requests=[FactRequest(name="height", predicate="bbox.extent.z", subject_id="solid:0")]),
    )

    assert snapshot.status == "ready"
    assert snapshot.units["length"] == "in"
    assert snapshot.parse_options["target_length_unit"] == "mm"
    assert factset.facts[0].value == pytest.approx(25.4, abs=1e-6)
    assert factset.facts[0].unit == "mm"
    assert factset.facts[0].method.parameters["declared_length_unit"] == "in"
    assert factset.facts[0].method.parameters["system_length_unit"] == "mm"
    assert factset.facts[0].method.parameters["conversion_factor"] == 25.4
    assert factset.facts[0].method.parameters["derived_source_value"] == pytest.approx(1.0, abs=1e-9)


def test_centimetre_declaration_is_converted_to_millimetres(tmp_path):
    path = tmp_path / "centimetres.step"
    write_box(path, (20.0, 30.0, 40.0), "CM")

    snapshot = read(register(path))
    factset = extract(
        snapshot,
        ExtractionQuery(
            requests=[
                FactRequest(name="height", predicate="bbox.extent.z", subject_id="solid:0"),
                FactRequest(name="volume", predicate="volume", subject_id="solid:0"),
                FactRequest(name="area", predicate="area", subject_id="solid:0"),
            ]
        ),
    )

    assert snapshot.status == "ready"
    assert snapshot.units["length"] == "cm"
    facts = {fact.predicate: fact for fact in factset.facts}
    assert facts["bbox.extent.z"].value == pytest.approx(40.0, abs=1e-9)
    assert facts["volume"].value == pytest.approx(24000.0, abs=1e-9)
    assert facts["area"].value == pytest.approx(5200.0, abs=1e-9)
    assert facts["bbox.extent.z"].method.parameters["conversion_factor"] == 10.0
    assert facts["volume"].method.parameters["conversion_factor"] == 1000.0
    assert facts["area"].method.parameters["conversion_factor"] == 100.0
    assert facts["bbox.extent.z"].method.parameters["derived_source_value"] == pytest.approx(4.0)
    assert facts["volume"].method.parameters["derived_source_value"] == pytest.approx(24.0)
    assert facts["area"].method.parameters["derived_source_value"] == pytest.approx(52.0)


def test_unverified_length_unit_preserves_entities_and_blocks_length_facts(tmp_path):
    path = tmp_path / "one-metre.step"
    write_box(path, (1000.0, 1000.0, 1000.0), "M")

    snapshot = read(register(path))
    factset = extract(
        snapshot,
        ExtractionQuery(requests=[FactRequest(name="height", predicate="bbox.extent.z", subject_id="solid:0")]),
    )

    assert snapshot.status == "partial"
    assert snapshot.entity_discovery == "complete"
    assert snapshot.units["length"] == "metre"
    assert [entity.entity_id for entity in snapshot.entities] == ["solid:0"]
    assert [diagnostic.code for diagnostic in snapshot.diagnostics] == ["UNIT_UNKNOWN"]
    assert factset.facts == []
    assert [gap.reason_code for gap in factset.gaps] == ["UNKNOWN_UNIT"]
    assert factset.gaps[0].subject is not None
    assert factset.gaps[0].subject.entity_id == "solid:0"
