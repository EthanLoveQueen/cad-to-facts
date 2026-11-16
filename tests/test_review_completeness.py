import pytest

from cad_to_facts.domain.facts import Evidence, ExtractionQuery, Fact, FactGap, FactRequest, FactSet, Method
from cad_to_facts.domain.review import Requirement, RequirementBundle, ReviewContext, ReviewRequest, ReviewScope, Rule, RuleInput, RuleRef, RuleSet, SubjectSelector
from cad_to_facts.domain.snapshot import Diagnostic, EntityRef, ModelSnapshot
from cad_to_facts.review import review
from contract_helpers import bind_request


def _snapshot(status="ready", discovery="complete", diagnostics=None):
    subject = EntityRef(snapshot_id="b" * 64, entity_id="solid:0", entity_kind="solid")
    return ModelSnapshot(
        artifact_sha256="a" * 64,
        snapshot_id="b" * 64,
        snapshot_content_hash="c" * 64,
        adapter_id="test",
        adapter_version="1",
        parser_kernel_version="1",
        parse_options={},
        units={"length": "mm"},
        status=status,
        entity_discovery=discovery,
        entities=[subject],
        diagnostics=diagnostics or [],
    )


def _measured(subject, predicate, value, unit, fact_id="1" * 64):
    return Fact(
        fact_id=fact_id,
        kind="measured",
        subject=subject,
        predicate=predicate,
        value=value,
        unit=unit,
        evidence=Evidence(artifact_sha256="a" * 64, entity_refs=[subject]),
        method=Method(library="test", algorithm="literal", version="1"),
    )


def _request(snapshot, facts, gaps, rule, required_inputs=()):
    requirement = Requirement(
        requirement_id="req-1",
        text="Requirement under test",
        source_ref="test:1",
        content_hash="e" * 64,
    )
    return bind_request(
        ReviewRequest(
            snapshot=snapshot,
            factset=FactSet(
                factset_id="d" * 64,
                snapshot_id=snapshot.snapshot_id,
                snapshot_content_hash=snapshot.snapshot_content_hash,
                extraction_query=ExtractionQuery(requests=[*required_inputs]),
                extractor_version="1",
                facts=facts,
                gaps=gaps,
                diagnostics=[],
            ),
            ruleset=RuleSet(
                ruleset_id="2" * 64,
                version="1",
                requirement_bundle=RequirementBundle(bundle_id="f" * 64, requirements=[requirement]),
                rules=[rule],
            ),
            scope=ReviewScope(
                scope_id="3" * 64,
                included_rules=[rule.rule_id],
                subject_selectors=[SubjectSelector(entity_kind="solid")],
                required_inputs=list(required_inputs),
                discovery_requirements=["solid"],
            ),
            context=ReviewContext(context_id="4" * 64, values={}),
            reviewer_version="0.1.0",
        )
    )


def _height_rule(rule_id="max-height", inputs=None):
    return Rule(
        rule_id=rule_id,
        version="1",
        requirement_refs=["req-1"],
        subject_selector=SubjectSelector(entity_kind="solid"),
        inputs=inputs or [RuleInput(name="height", predicate="bbox.extent.z")],
        checker="numeric.compare",
        parameters={"operator": "<=", "threshold": 30.0, "unit": "mm", "abs_tol": 1e-7},
        severity="error",
        source={"reviewed_by": "test"},
    )


def test_scope_required_input_without_fact_or_gap_makes_report_incomplete():
    snapshot = _snapshot()
    mass_request = FactRequest(name="mass", predicate="mass", subject_id="solid:0")
    facts = [_measured(snapshot.entities[0], "bbox.extent.z", 10.0, "mm")]

    report = review(_request(snapshot, facts, [], _height_rule(), required_inputs=[mass_request]))

    assert report.findings[0].status == "satisfied"
    assert report.complete is False
    assert report.overall_status == "incomplete"
    assert [gap.request.predicate for gap in report.generated_gaps] == ["mass"]
    assert report.generated_gaps[0].reason_code == "NOT_COMPUTED"


def test_scope_required_input_with_unsupported_gap_blocks_completeness():
    snapshot = _snapshot()
    mass_request = FactRequest(name="mass", predicate="mass", subject_id="solid:0")
    facts = [_measured(snapshot.entities[0], "bbox.extent.z", 10.0, "mm")]
    gap = FactGap(
        request=mass_request,
        subject=snapshot.entities[0],
        reason_code="UNSUPPORTED",
        blocking_capabilities=["mass"],
    )

    report = review(
        _request(snapshot, facts, [gap], _height_rule(), required_inputs=[mass_request])
    )

    assert report.findings[0].status == "satisfied"
    assert report.complete is False
    assert report.overall_status == "incomplete"
    assert report.coverage.fully_inspected_entities == 0
    assert [diagnostic.code for diagnostic in report.diagnostics] == [
        "SCOPE_INPUT_UNRESOLVED"
    ]
    assert report.generated_gaps == []


def test_scope_required_input_with_proven_absent_gap_is_resolved():
    snapshot = _snapshot()
    mass_request = FactRequest(name="mass", predicate="mass", subject_id="solid:0")
    facts = [_measured(snapshot.entities[0], "bbox.extent.z", 10.0, "mm")]
    gap = FactGap(
        request=mass_request,
        subject=snapshot.entities[0],
        reason_code="ABSENT",
    )

    report = review(
        _request(snapshot, facts, [gap], _height_rule(), required_inputs=[mass_request])
    )

    assert report.complete is True
    assert report.overall_status == "compliant_for_scope"
    assert report.coverage.fully_inspected_entities == 1
    assert report.diagnostics == []


def test_unresolved_partial_diagnostic_prevents_complete_report():
    diagnostic = Diagnostic(
        code="ENTITY_SKIPPED",
        severity="warning",
        stage="read",
        message="One entity was skipped",
        affects=["geometry"],
        impact="partial",
        discovery_impact="none",
        disposition="open",
    )
    snapshot = _snapshot(status="partial", diagnostics=[diagnostic])
    facts = [_measured(snapshot.entities[0], "bbox.extent.z", 10.0, "mm")]

    report = review(_request(snapshot, facts, [], _height_rule()))

    assert report.findings[0].status == "satisfied"
    assert report.complete is False
    assert report.overall_status == "incomplete"


def test_multi_input_presence_rule_is_unknown_when_one_input_is_not_computed():
    snapshot = _snapshot()
    height_present = RuleInput(name="height", predicate="bbox.extent.z")
    width = RuleInput(name="width", predicate="bbox.extent.x")
    rule = Rule(
        rule_id="dimensions-present",
        version="1",
        requirement_refs=["req-1"],
        subject_selector=SubjectSelector(entity_kind="solid"),
        inputs=[height_present, width],
        checker="fact.present",
        parameters={},
        severity="error",
        source={"reviewed_by": "test"},
    )
    facts = [_measured(snapshot.entities[0], "bbox.extent.z", 10.0, "mm")]

    report = review(_request(snapshot, facts, [], rule))

    assert report.findings[0].status == "unknown"
    assert report.complete is False


def test_numeric_rule_with_multiple_inputs_is_a_configuration_error():
    snapshot = _snapshot()
    rule = _height_rule(inputs=[RuleInput(name="height", predicate="bbox.extent.z"), RuleInput(name="width", predicate="bbox.extent.x")])
    facts = [_measured(snapshot.entities[0], "bbox.extent.z", 10.0, "mm")]

    with pytest.raises(ValueError, match="exactly one input"):
        review(_request(snapshot, facts, [], rule))


def test_in_scope_entity_rule_without_candidates_is_reported_as_empty_scope():
    snapshot = _snapshot()
    height_rule = _height_rule()
    snapshot_rule = Rule(
        rule_id="file-readable",
        version="1",
        requirement_refs=["req-1"],
        subject_selector=SubjectSelector(entity_kind="snapshot"),
        inputs=[],
        checker="snapshot.status",
        parameters={"equals": "ready"},
        severity="error",
        source={"reviewed_by": "test"},
    )
    facts = [_measured(snapshot.entities[0], "bbox.extent.z", 10.0, "mm")]
    request = _request(snapshot, facts, [], height_rule)
    request = bind_request(
        request.model_copy(
            update={
                "scope": ReviewScope(
                    scope_id="0" * 64,
                    included_rules=[
                        RuleRef(rule_id="max-height"),
                        RuleRef(rule_id="file-readable"),
                    ],
                    subject_selectors=[SubjectSelector(entity_kind="snapshot")],
                    required_inputs=[],
                    discovery_requirements=["solid"],
                ),
                "ruleset": RuleSet(
                    ruleset_id="0" * 64,
                    version="1",
                    requirement_bundle=request.ruleset.requirement_bundle,
                    rules=[height_rule, snapshot_rule],
                ),
            }
        )
    )

    report = review(request)

    assert [finding.rule_id for finding in report.findings] == ["file-readable"]
    assert report.complete is False
    assert report.overall_status == "incomplete"
    assert [diagnostic.code for diagnostic in report.diagnostics] == ["EMPTY_SCOPE"]
