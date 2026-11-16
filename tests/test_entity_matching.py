import pytest

from cad_to_facts.artifact import register
from cad_to_facts.contract import bind_factset, bind_snapshot
from cad_to_facts.domain.facts import Evidence, ExtractionQuery, Fact, FactSet, Method
from cad_to_facts.domain.matching import (
    EntityMatchRequest,
    EntityMatchingProfile,
    NumericTolerance,
)
from cad_to_facts.domain.snapshot import EntityRef, ModelSnapshot
from cad_to_facts.matching import bind_matching_profile, bind_matching_request, match_entities
from cad_to_facts.snapshot import read

from step_helpers import write_box


def _snapshot(
    artifact,
    snapshot_id,
    entities,
    *,
    discovery="complete",
    status="ready",
    kernel="1",
    options=None,
):
    snapshot = ModelSnapshot(
        artifact_sha256=artifact,
        snapshot_id=snapshot_id,
        snapshot_content_hash="0" * 64,
        adapter_id="test-adapter",
        adapter_version="1",
        parser_kernel_version=kernel,
        parse_options=options or {},
        units={"length": "mm"},
        status=status,
        entity_discovery=discovery,
        entities=entities,
        diagnostics=[],
    )
    return bind_snapshot(snapshot)


def _fact(snapshot, entity, predicate, value, unit="mm^3"):
    return Fact(
        fact_id="0" * 64,
        kind="measured",
        subject=entity,
        predicate=predicate,
        value=value,
        unit=unit,
        evidence=Evidence(
            artifact_sha256=snapshot.artifact_sha256, entity_refs=[entity]
        ),
        method=Method(library="test", algorithm="literal", version="1"),
    )


def _factset(snapshot, facts):
    return bind_factset(
        FactSet(
            factset_id="0" * 64,
            snapshot_id=snapshot.snapshot_id,
            snapshot_content_hash=snapshot.snapshot_content_hash,
            extraction_query=ExtractionQuery(requests=[]),
            extractor_version="1",
            facts=facts,
            gaps=[],
            diagnostics=[],
        )
    )


def _profile(method, **values):
    return bind_matching_profile(
        EntityMatchingProfile(
            profile_id="0" * 64, method=method, **values
        )
    )


def _request(
    baseline,
    candidate,
    profile,
    required,
    baseline_facts=None,
    candidate_facts=None,
):
    return bind_matching_request(
        EntityMatchRequest(
            request_id="0" * 64,
            baseline=baseline,
            candidate=candidate,
            profile=profile,
            required_baseline_entity_ids=required,
            baseline_facts=baseline_facts,
            candidate_facts=candidate_facts,
        )
    )


def test_native_ref_matches_by_declared_reference_not_entity_id_or_order():
    baseline = _snapshot(
        "a" * 64,
        "1" * 64,
        [
            EntityRef(
                snapshot_id="1" * 64,
                entity_id="solid:0",
                entity_kind="solid",
                native_refs=[{"type": "ifc_guid", "value": "guid-a"}],
            ),
            EntityRef(
                snapshot_id="1" * 64,
                entity_id="solid:1",
                entity_kind="solid",
                native_refs=[{"type": "ifc_guid", "value": "guid-b"}],
            ),
        ],
    )
    candidate = _snapshot(
        "b" * 64,
        "2" * 64,
        [
            EntityRef(
                snapshot_id="2" * 64,
                entity_id="solid:0",
                entity_kind="solid",
                native_refs=[{"type": "ifc_guid", "value": "guid-b"}],
            ),
            EntityRef(
                snapshot_id="2" * 64,
                entity_id="solid:1",
                entity_kind="solid",
                native_refs=[{"type": "ifc_guid", "value": "guid-a"}],
            ),
        ],
    )
    request = _request(
        baseline,
        candidate,
        _profile("native_ref", native_ref_type="ifc_guid"),
        ["solid:0", "solid:1"],
    )

    report = match_entities(request)

    assert report.status == "complete"
    assert [result.status for result in report.results] == ["matched", "matched"]
    assert report.results[0].candidate_entity_ids == ["solid:1"]
    assert report.results[1].candidate_entity_ids == ["solid:0"]
    assert report.unmatched_candidate_entity_ids == []


def test_required_entity_without_candidate_makes_report_incomplete():
    baseline = _snapshot(
        "a" * 64,
        "1" * 64,
        [
            EntityRef(
                snapshot_id="1" * 64,
                entity_id="solid:0",
                entity_kind="solid",
                native_refs=[{"type": "ifc_guid", "value": "guid-a"}],
            ),
            EntityRef(
                snapshot_id="1" * 64,
                entity_id="solid:1",
                entity_kind="solid",
                native_refs=[{"type": "ifc_guid", "value": "guid-b"}],
            ),
        ],
    )
    candidate = _snapshot(
        "b" * 64,
        "2" * 64,
        [
            EntityRef(
                snapshot_id="2" * 64,
                entity_id="solid:0",
                entity_kind="solid",
                native_refs=[{"type": "ifc_guid", "value": "guid-a"}],
            )
        ],
    )
    request = _request(
        baseline,
        candidate,
        _profile("native_ref", native_ref_type="ifc_guid"),
        ["solid:0", "solid:1"],
    )

    report = match_entities(request)

    assert report.status == "incomplete"
    assert [result.status for result in report.results] == ["matched", "unmatched"]
    assert report.results[1].reason_code == "NO_CANDIDATE"


def test_duplicate_candidate_reference_is_ambiguous():
    baseline = _snapshot(
        "a" * 64,
        "1" * 64,
        [
            EntityRef(
                snapshot_id="1" * 64,
                entity_id="solid:0",
                entity_kind="solid",
                native_refs=[{"type": "ifc_guid", "value": "guid-a"}],
            )
        ],
    )
    candidate = _snapshot(
        "b" * 64,
        "2" * 64,
        [
            EntityRef(
                snapshot_id="2" * 64,
                entity_id="solid:0",
                entity_kind="solid",
                native_refs=[{"type": "ifc_guid", "value": "guid-a"}],
            ),
            EntityRef(
                snapshot_id="2" * 64,
                entity_id="solid:1",
                entity_kind="solid",
                native_refs=[{"type": "ifc_guid", "value": "guid-a"}],
            ),
        ],
    )
    request = _request(
        baseline,
        candidate,
        _profile("native_ref", native_ref_type="ifc_guid"),
        ["solid:0"],
    )

    report = match_entities(request)

    assert report.status == "incomplete"
    assert report.results[0].status == "ambiguous"
    assert report.results[0].reason_code == "AMBIGUOUS_CANDIDATE"
    assert report.results[0].candidate_entity_ids == ["solid:0", "solid:1"]


def test_adapter_key_matching_requires_the_same_parse_profile():
    baseline = _snapshot(
        "a" * 64,
        "1" * 64,
        [
            EntityRef(
                snapshot_id="1" * 64,
                entity_id="solid:0",
                entity_kind="solid",
                adapter_key="solid:0",
            )
        ],
    )
    candidate = _snapshot(
        "b" * 64,
        "2" * 64,
        [
            EntityRef(
                snapshot_id="2" * 64,
                entity_id="solid:0",
                entity_kind="solid",
                adapter_key="solid:0",
            )
        ],
        kernel="2",
    )
    request = _request(
        baseline, candidate, _profile("adapter_key"), ["solid:0"]
    )

    report = match_entities(request)

    assert report.status == "incomplete"
    assert report.results[0].status == "unresolved"
    assert report.results[0].reason_code == "PARSE_PROFILE_MISMATCH"
    assert [diagnostic.code for diagnostic in report.diagnostics] == [
        "PARSE_PROFILE_MISMATCH"
    ]


def test_partial_discovery_prevents_complete_status():
    baseline = _snapshot(
        "a" * 64,
        "1" * 64,
        [
            EntityRef(
                snapshot_id="1" * 64,
                entity_id="solid:0",
                entity_kind="solid",
                adapter_key="solid:0",
            )
        ],
    )
    candidate = _snapshot(
        "b" * 64,
        "2" * 64,
        [
            EntityRef(
                snapshot_id="2" * 64,
                entity_id="solid:0",
                entity_kind="solid",
                adapter_key="solid:0",
            )
        ],
        discovery="partial",
    )
    request = _request(
        baseline, candidate, _profile("adapter_key"), ["solid:0"]
    )

    report = match_entities(request)

    assert report.results[0].status == "matched"
    assert report.status == "incomplete"
    assert [diagnostic.code for diagnostic in report.diagnostics] == [
        "CANDIDATE_DISCOVERY_INCOMPLETE"
    ]


def _fingerprint_fixture(baseline_value, candidate_value, unit="mm^3", tolerance=0.5):
    baseline_entity = EntityRef(
        snapshot_id="1" * 64, entity_id="solid:0", entity_kind="solid"
    )
    baseline = _snapshot("a" * 64, "1" * 64, [baseline_entity])
    candidate_entity = EntityRef(
        snapshot_id="2" * 64, entity_id="solid:0", entity_kind="solid"
    )
    candidate = _snapshot("b" * 64, "2" * 64, [candidate_entity])
    baseline_facts = _factset(
        baseline, [_fact(baseline, baseline_entity, "volume", baseline_value, unit)]
    )
    candidate_facts = _factset(
        candidate, [_fact(candidate, candidate_entity, "volume", candidate_value, unit)]
    )
    return _request(
        baseline,
        candidate,
        _profile(
            "fingerprint",
            fingerprint_predicates=["volume"],
            tolerance=NumericTolerance(absolute=tolerance),
        ),
        ["solid:0"],
        baseline_facts=baseline_facts,
        candidate_facts=candidate_facts,
    )


def test_fingerprint_matches_within_declared_tolerance():
    report = match_entities(_fingerprint_fixture(1000.0, 1000.4))

    assert report.status == "complete"
    assert report.results[0].status == "matched"


def test_fingerprint_outside_tolerance_is_unmatched_not_unknown():
    report = match_entities(_fingerprint_fixture(1000.0, 1001.0))

    assert report.status == "incomplete"
    assert report.results[0].status == "unmatched"
    assert report.results[0].reason_code == "NO_MATCHING_FINGERPRINT"


def test_fingerprint_unit_mismatch_is_unresolved():
    request = _fingerprint_fixture(1000.0, 1000.4, tolerance=0.5)
    candidate_facts = _factset(
        request.candidate,
        [
            _fact(
                request.candidate,
                request.candidate.entities[0],
                "volume",
                1000.4,
                "cm^3",
            )
        ],
    )
    request = request.model_copy(update={"candidate_facts": candidate_facts})
    request = bind_matching_request(request)

    report = match_entities(request)

    assert report.status == "incomplete"
    assert report.results[0].status == "unresolved"
    assert report.results[0].reason_code == "UNIT_MISMATCH"


def test_fingerprint_missing_baseline_fact_is_unresolved():
    baseline = _snapshot(
        "a" * 64,
        "1" * 64,
        [EntityRef(snapshot_id="1" * 64, entity_id="solid:0", entity_kind="solid")],
    )
    candidate_entity = EntityRef(
        snapshot_id="2" * 64, entity_id="solid:0", entity_kind="solid"
    )
    candidate = _snapshot("b" * 64, "2" * 64, [candidate_entity])
    request = _request(
        baseline,
        candidate,
        _profile(
            "fingerprint", fingerprint_predicates=["volume"]
        ),
        ["solid:0"],
        baseline_facts=_factset(baseline, []),
        candidate_facts=_factset(
            candidate, [_fact(candidate, candidate_entity, "volume", 1000.0)]
        ),
    )

    report = match_entities(request)

    assert report.results[0].status == "unresolved"
    assert report.results[0].reason_code == "MISSING_FACT"


def test_two_baseline_entities_claiming_one_candidate_are_conflicted():
    baseline_entities = [
        EntityRef(snapshot_id="1" * 64, entity_id="solid:0", entity_kind="solid"),
        EntityRef(snapshot_id="1" * 64, entity_id="solid:1", entity_kind="solid"),
    ]
    baseline = _snapshot("a" * 64, "1" * 64, baseline_entities)
    candidate_entity = EntityRef(
        snapshot_id="2" * 64, entity_id="solid:0", entity_kind="solid"
    )
    candidate = _snapshot("b" * 64, "2" * 64, [candidate_entity])
    baseline_facts = _factset(
        baseline,
        [
            _fact(baseline, entity, "volume", 1000.0)
            for entity in baseline_entities
        ],
    )
    candidate_facts = _factset(
        candidate, [_fact(candidate, candidate_entity, "volume", 1000.0)]
    )
    request = _request(
        baseline,
        candidate,
        _profile("fingerprint", fingerprint_predicates=["volume"]),
        ["solid:0", "solid:1"],
        baseline_facts=baseline_facts,
        candidate_facts=candidate_facts,
    )

    report = match_entities(request)

    assert [result.status for result in report.results] == ["ambiguous", "ambiguous"]
    assert [result.reason_code for result in report.results] == [
        "CANDIDATE_CONFLICT",
        "CANDIDATE_CONFLICT",
    ]
    assert report.status == "incomplete"


def test_reordering_required_entities_preserves_request_and_report_identity():
    baseline = _snapshot(
        "a" * 64,
        "1" * 64,
        [
            EntityRef(
                snapshot_id="1" * 64,
                entity_id="solid:0",
                entity_kind="solid",
                adapter_key="solid:0",
            ),
            EntityRef(
                snapshot_id="1" * 64,
                entity_id="solid:1",
                entity_kind="solid",
                adapter_key="solid:1",
            ),
        ],
    )
    candidate = _snapshot(
        "b" * 64,
        "2" * 64,
        [
            EntityRef(
                snapshot_id="2" * 64,
                entity_id="solid:0",
                entity_kind="solid",
                adapter_key="solid:0",
            ),
            EntityRef(
                snapshot_id="2" * 64,
                entity_id="solid:1",
                entity_kind="solid",
                adapter_key="solid:1",
            ),
        ],
    )
    first = _request(baseline, candidate, _profile("adapter_key"), ["solid:0", "solid:1"])
    second = _request(baseline, candidate, _profile("adapter_key"), ["solid:1", "solid:0"])

    first_report = match_entities(first)
    second_report = match_entities(second)

    assert first.request_id == second.request_id
    assert first_report.report_id == second_report.report_id
    assert first_report.results == second_report.results


def test_tampered_profile_or_request_identity_is_rejected():
    baseline = _snapshot(
        "a" * 64,
        "1" * 64,
        [EntityRef(snapshot_id="1" * 64, entity_id="solid:0", entity_kind="solid")],
    )
    candidate = _snapshot(
        "b" * 64,
        "2" * 64,
        [EntityRef(snapshot_id="2" * 64, entity_id="solid:0", entity_kind="solid")],
    )
    request = _request(baseline, candidate, _profile("adapter_key"), ["solid:0"])

    tampered_profile = request.model_copy(
        update={"profile": request.profile.model_copy(update={"profile_id": "0" * 64})}
    )
    with pytest.raises(ValueError, match="profile_id"):
        match_entities(tampered_profile)

    other_profile = _profile("adapter_key", schema_version="0.2")
    tampered_request = request.model_copy(update={"profile": other_profile})
    with pytest.raises(ValueError, match="request_id"):
        match_entities(tampered_request)


def test_matching_configuration_errors_are_rejected():
    baseline = _snapshot(
        "a" * 64,
        "1" * 64,
        [EntityRef(snapshot_id="1" * 64, entity_id="solid:0", entity_kind="solid")],
    )
    candidate = _snapshot(
        "b" * 64,
        "2" * 64,
        [EntityRef(snapshot_id="2" * 64, entity_id="solid:0", entity_kind="solid")],
    )

    with pytest.raises(ValueError, match="native_ref_type"):
        _profile("native_ref")
    with pytest.raises(ValueError, match="fingerprint predicate"):
        _profile("fingerprint")
    with pytest.raises(ValueError, match="not valid for native_ref"):
        _profile("native_ref", native_ref_type="x", fingerprint_predicates=["volume"])
    with pytest.raises(ValueError, match="only valid for fingerprint"):
        _profile(
            "adapter_key", tolerance=NumericTolerance(relative=0.1)
        )
    with pytest.raises(ValueError, match="at least one entity"):
        _request(baseline, candidate, _profile("adapter_key"), [])
    with pytest.raises(ValueError, match="duplicates"):
        _request(baseline, candidate, _profile("adapter_key"), ["solid:0", "solid:0"])
    with pytest.raises(ValueError, match="not in the baseline"):
        _request(baseline, candidate, _profile("adapter_key"), ["solid:9"])


def test_fact_subject_from_another_snapshot_is_rejected():
    baseline = _snapshot(
        "a" * 64,
        "1" * 64,
        [EntityRef(snapshot_id="1" * 64, entity_id="solid:0", entity_kind="solid")],
    )
    candidate = _snapshot(
        "b" * 64,
        "2" * 64,
        [EntityRef(snapshot_id="2" * 64, entity_id="solid:0", entity_kind="solid")],
    )
    foreign_subject = EntityRef(
        snapshot_id="9" * 64, entity_id="solid:0", entity_kind="solid"
    )
    baseline_facts = _factset(
        baseline, [_fact(baseline, foreign_subject, "volume", 1000.0)]
    )
    candidate_facts = _factset(
        candidate,
        [
            _fact(
                candidate,
                candidate.entities[0],
                "volume",
                1000.0,
            )
        ],
    )

    with pytest.raises(ValueError, match="subject does not belong"):
        _request(
            baseline,
            candidate,
            _profile("fingerprint", fingerprint_predicates=["volume"]),
            ["solid:0"],
            baseline_facts=baseline_facts,
            candidate_facts=candidate_facts,
        )


def test_analytic_step_files_match_by_adapter_key(tmp_path):
    before_path = tmp_path / "before.step"
    after_path = tmp_path / "after.step"
    write_box(before_path, (10.0, 20.0, 30.0))
    write_box(after_path, (10.0, 20.0, 40.0))
    baseline = read(register(before_path))
    candidate = read(register(after_path))
    request = _request(
        baseline, candidate, _profile("adapter_key"), ["solid:0"]
    )

    report = match_entities(request)

    assert report.status == "complete"
    assert report.results[0].status == "matched"
    assert report.results[0].candidate_entity_ids == ["solid:0"]
