import pytest

from cad_to_facts.artifact import register
from cad_to_facts.domain.facts import ExtractionQuery, FactRequest
from cad_to_facts.facts import extract
from cad_to_facts.snapshot import read

from step_helpers import write_box


def test_extract_analytic_box_measurements_with_units_and_evidence(tmp_path):
    path = tmp_path / "box.step"
    write_box(path)
    snapshot = read(register(path))
    query = ExtractionQuery(
        requests=[
            FactRequest(name="volume", predicate="volume", subject_id="solid:0"),
            FactRequest(name="area", predicate="area", subject_id="solid:0"),
            FactRequest(name="height", predicate="bbox.extent.z", subject_id="solid:0"),
        ]
    )

    factset = extract(snapshot, query)

    values = {fact.predicate: fact for fact in factset.facts}
    assert values["volume"].value == pytest.approx(6000.0, abs=1e-7)
    assert values["volume"].unit == "mm^3"
    assert values["area"].value == pytest.approx(2200.0, abs=1e-7)
    assert values["area"].unit == "mm^2"
    assert values["bbox.extent.z"].value == pytest.approx(30.0, abs=1e-7)
    assert values["bbox.extent.z"].unit == "mm"
    assert all(fact.evidence.artifact_sha256 == snapshot.artifact_sha256 for fact in factset.facts)
    assert factset.gaps == []
