import pytest

from cad_to_facts.domain.facts import ExtractionQuery, FactRequest
from cad_to_facts.domain.snapshot import ModelSnapshot
from cad_to_facts.facts import extract


def test_unsupported_measurement_returns_fact_gap_instead_of_null_fact():
    snapshot = ModelSnapshot(
        artifact_sha256="a" * 64,
        snapshot_id="b" * 64,
        snapshot_content_hash="c" * 64,
        adapter_id="test",
        adapter_version="1",
        parser_kernel_version="1",
        parse_options={},
        units={},
        status="ready",
        entity_discovery="complete",
        entities=[],
        diagnostics=[],
    )
    query = ExtractionQuery(requests=[FactRequest(name="wall", predicate="wall.thickness", subject_id="solid:0")])

    factset = extract(snapshot, query)

    assert factset.facts == []
    assert len(factset.gaps) == 1
    assert factset.gaps[0].reason_code == "UNSUPPORTED"
    assert factset.gaps[0].request.name == "wall"


def test_unknown_subject_is_reported_as_input_configuration_error():
    snapshot = ModelSnapshot(
        artifact_sha256="a" * 64,
        snapshot_id="b" * 64,
        snapshot_content_hash="c" * 64,
        adapter_id="test",
        adapter_version="1",
        parser_kernel_version="1",
        parse_options={},
        units={},
        status="ready",
        entity_discovery="complete",
        entities=[],
        diagnostics=[],
    )
    query = ExtractionQuery(requests=[FactRequest(name="volume", predicate="volume", subject_id="solid:9")])

    with pytest.raises(ValueError, match="Unknown snapshot entity"):
        extract(snapshot, query)
