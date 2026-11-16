import pytest

from cad_to_facts.domain.facts import Evidence, ExtractionQuery, Fact, FactGap, FactRequest, FactSet, Method
from cad_to_facts.domain.review import (
    Requirement,
    RequirementBundle,
    ReviewContext,
    ReviewRequest,
    ReviewScope,
    Rule,
    RuleInput,
    RuleRef,
    RuleSet,
    SubjectSelector,
)
from cad_to_facts.domain.snapshot import Diagnostic, EntityRef, ModelSnapshot
from cad_to_facts.review import review
from contract_helpers import bind_request


def _snapshot(artifact="a" * 64, discovery="complete", status="ready", diagnostics=None, kinds=("solid",)):
    entities = [
        EntityRef(snapshot_id="b" * 64, entity_id=f"{kind}:0", entity_kind=kind)
        for kind in kinds
    ]
    return ModelSnapshot(
        artifact_sha256=artifact,
        snapshot_id="b" * 64,
        snapshot_content_hash="c" * 64,
        adapter_id="test",
        adapter_version="1",
        parser_kernel_version="1",
        parse_options={},
        units={"length": "mm"},
        status=status,
        entity_discovery=discovery,
        entities=entities,
        diagnostics=diagnostics or [],
    )


def _fact(subject, predicate, value, unit="mm", artifact="a" * 64):
    return Fact(
        fact_id="1" * 64,
        kind="measured",
        subject=subject,
        predicate=predicate,
        value=value,
        unit=unit,
        evidence=Evidence(artifact_sha256=artifact, entity_refs=[subject]),
        method=Method(library="test", algorithm="literal", version="1"),
    )


def _requirement(requirement_id="req-1"):
    return Requirement(
        requirement_id=requirement_id,
        text="Requirement under test",
        source_ref="test:1",
        content_hash="e" * 64,
    )


def _rule(
    rule_id="max-height",
    inputs=None,
    checker="numeric.compare",
    parameters=None,
    applicability=None,
    version="1",
    requirement_refs=None,
):
    return Rule(
        rule_id=rule_id,
        version=version,
        requirement_refs=requirement_refs or ["req-1"],
        subject_selector=SubjectSelector(entity_kind="solid"),
        applicability=applicability or {},
        inputs=inputs or [RuleInput(name="height", predicate="bbox.extent.z")],
        checker=checker,
        parameters=parameters if parameters is not None else {"operator": "<=", "threshold": 30.0, "unit": "mm", "abs_tol": 1e-7},
        severity="error",
        source={"reviewed_by": "test"},
    )


def _request(
    snapshot,
    rules,
    facts=(),
    gaps=(),
    included_rules=None,
    subject_selectors=None,
    required_inputs=(),
    discovery_requirements=("solid",),
    requirements=None,
):
    requirement = requirements[0] if requirements else _requirement()
    bundle = RequirementBundle(bundle_id="f" * 64, requirements=requirements or [requirement])
    ruleset = RuleSet(ruleset_id="2" * 64, version="1", requirement_bundle=bundle, rules=rules)
    rule_ids = included_rules if included_rules is not None else [rule.rule_id for rule in rules]
    scope = ReviewScope(
        scope_id="3" * 64,
        included_rules=rule_ids,
        subject_selectors=subject_selectors
        or [
            SubjectSelector(entity_kind=kind)
            for kind in sorted({rule.subject_selector.entity_kind for rule in rules})
        ],
        required_inputs=list(required_inputs),
        discovery_requirements=list(discovery_requirements),
    )
    factset = FactSet(
        factset_id="d" * 64,
        snapshot_id=snapshot.snapshot_id,
        snapshot_content_hash=snapshot.snapshot_content_hash,
        extraction_query=ExtractionQuery(requests=list(required_inputs)),
        extractor_version="1",
        facts=list(facts),
        gaps=list(gaps),
        diagnostics=[],
    )
    return bind_request(
        ReviewRequest(
            snapshot=snapshot,
            factset=factset,
            ruleset=ruleset,
            scope=scope,
            context=ReviewContext(context_id="4" * 64, values={}),
            reviewer_version="0.1.0",
        )
    )


def test_factset_from_another_snapshot_is_rejected():
    snapshot = _snapshot()
    request = _request(snapshot, [_rule()])
    request = request.model_copy(
        update={"factset": request.factset.model_copy(update={"snapshot_content_hash": "9" * 64})}
    )

    with pytest.raises(ValueError, match="FactSet does not belong to the reviewed snapshot"):
        review(request)


def test_fact_from_another_artifact_is_rejected():
    snapshot = _snapshot()
    fact = _fact(snapshot.entities[0], "bbox.extent.z", 10.0, artifact="8" * 64)

    with pytest.raises(ValueError, match="Fact evidence artifact"):
        review(_request(snapshot, [_rule()], facts=[fact]))


def test_unresolved_requirement_reference_is_rejected():
    snapshot = _snapshot()
    rule = _rule()
    rule = rule.model_copy(update={"requirement_refs": ["req-missing"]})
    fact = _fact(snapshot.entities[0], "bbox.extent.z", 10.0)

    with pytest.raises(ValueError, match="requirement"):
        review(_request(snapshot, [rule], facts=[fact]))


def test_unknown_included_rule_is_rejected():
    snapshot = _snapshot()
    fact = _fact(snapshot.entities[0], "bbox.extent.z", 10.0)

    with pytest.raises(ValueError, match="included_rules"):
        review(_request(snapshot, [_rule()], facts=[fact], included_rules=["max-height", "typo-rule"]))


def test_versionless_reference_to_multiple_rule_versions_is_rejected():
    snapshot = _snapshot()
    first = _rule(version="1")
    second = _rule(version="2")
    fact = _fact(snapshot.entities[0], "bbox.extent.z", 10.0)

    with pytest.raises(ValueError, match="multiple versions; specify a version"):
        review(_request(snapshot, [first, second], facts=[fact], included_rules=["max-height"]))


def test_explicit_rule_version_selects_that_version():
    snapshot = _snapshot()
    strict = _rule(
        version="1",
        parameters={"operator": "<=", "threshold": 5.0, "unit": "mm", "abs_tol": 1e-7},
    )
    relaxed = _rule(
        version="2",
        parameters={"operator": "<=", "threshold": 30.0, "unit": "mm", "abs_tol": 1e-7},
    )
    fact = _fact(snapshot.entities[0], "bbox.extent.z", 10.0)

    strict_report = review(
        _request(
            snapshot,
            [strict, relaxed],
            facts=[fact],
            included_rules=[RuleRef(rule_id="max-height", version="1")],
        )
    )
    relaxed_report = review(
        _request(
            snapshot,
            [strict, relaxed],
            facts=[fact],
            included_rules=[RuleRef(rule_id="max-height", version="2")],
        )
    )

    assert [finding.status for finding in strict_report.findings] == ["violated"]
    assert [finding.rule_version for finding in strict_report.findings] == ["1"]
    assert [finding.status for finding in relaxed_report.findings] == ["satisfied"]
    assert [finding.rule_version for finding in relaxed_report.findings] == ["2"]


def test_unknown_rule_version_is_rejected():
    snapshot = _snapshot()
    fact = _fact(snapshot.entities[0], "bbox.extent.z", 10.0)

    with pytest.raises(ValueError, match="unknown version"):
        review(
            _request(
                snapshot,
                [_rule(version="1")],
                facts=[fact],
                included_rules=[RuleRef(rule_id="max-height", version="9")],
            )
        )


def test_duplicate_explicit_rule_version_is_rejected():
    snapshot = _snapshot()
    fact = _fact(snapshot.entities[0], "bbox.extent.z", 10.0)

    with pytest.raises(ValueError, match="duplicate included rule references"):
        review(
            _request(
                snapshot,
                [_rule()],
                facts=[fact],
                included_rules=[
                    RuleRef(rule_id="max-height", version="1"),
                    RuleRef(rule_id="max-height", version="1"),
                ],
            )
        )


def test_mixed_not_applicable_does_not_lower_entity_coverage():
    snapshot = _snapshot()
    satisfied = _rule()
    not_applicable = _rule(
        rule_id="max-width",
        applicability={"fact_predicate": "applicable", "equals": True},
        inputs=[RuleInput(name="width", predicate="bbox.extent.x")],
    )
    facts = [
        _fact(snapshot.entities[0], "bbox.extent.z", 10.0),
        _fact(snapshot.entities[0], "applicable", False, "dimensionless"),
    ]

    report = review(_request(snapshot, [satisfied, not_applicable], facts=facts))

    assert {finding.status for finding in report.findings} == {"satisfied", "not_applicable"}
    assert report.coverage.fully_inspected_entities == 1
    assert report.coverage.entity_coverage == 1.0
    assert report.overall_status == "compliant_for_scope"


def test_unresolved_scope_input_marks_candidate_not_fully_inspected():
    snapshot = _snapshot()
    fact = _fact(snapshot.entities[0], "bbox.extent.z", 10.0)
    mass = FactRequest(name="mass", predicate="mass", subject_id="solid:0")

    report = review(_request(snapshot, [_rule()], facts=[fact], required_inputs=[mass]))

    assert report.coverage.fully_inspected_entities == 0
    assert report.coverage.entity_coverage == 0.0
    assert report.complete is False


def test_optional_missing_input_is_unknown_not_violated():
    snapshot = _snapshot()
    rule = Rule(
        rule_id="material-rule",
        version="1",
        requirement_refs=["req-1"],
        subject_selector=SubjectSelector(entity_kind="solid"),
        inputs=[
            RuleInput(name="material", predicate="material", required=True),
            RuleInput(name="finish", predicate="finish", required=False),
        ],
        checker="fact.present",
        parameters={},
        severity="error",
        source={"reviewed_by": "test"},
    )
    material = _fact(snapshot.entities[0], "material", "6061", "dimensionless")
    finish = FactGap(
        request=FactRequest(name="finish", predicate="finish", subject_id="solid:0"),
        subject=snapshot.entities[0],
        reason_code="ABSENT",
        evidence=Evidence(artifact_sha256="a" * 64, entity_refs=[snapshot.entities[0]]),
    )

    report = review(_request(snapshot, [rule], facts=[material], gaps=[finish]))

    assert report.findings[0].status == "unknown"
    assert report.findings[0].reason_code != "ABSENT"


def test_mixed_absent_and_unsupported_gaps_do_not_prove_absence():
    snapshot = _snapshot()
    rule = Rule(
        rule_id="material-required",
        version="1",
        requirement_refs=["req-1"],
        subject_selector=SubjectSelector(entity_kind="solid"),
        inputs=[RuleInput(name="material", predicate="material", required=True)],
        checker="fact.present",
        parameters={},
        severity="error",
        source={"reviewed_by": "test"},
    )
    absent = FactGap(
        request=FactRequest(name="material", predicate="material", subject_id="solid:0"),
        subject=snapshot.entities[0],
        reason_code="ABSENT",
        evidence=Evidence(artifact_sha256="a" * 64, entity_refs=[snapshot.entities[0]]),
    )
    unsupported = FactGap(
        request=FactRequest(name="material", predicate="material", subject_id="solid:0"),
        subject=snapshot.entities[0],
        reason_code="UNSUPPORTED",
        evidence=Evidence(artifact_sha256="a" * 64, entity_refs=[snapshot.entities[0]]),
    )

    report = review(_request(snapshot, [rule], gaps=[absent, unsupported]))

    assert report.findings[0].status == "unknown"
    assert report.findings[0].reason_code == "UNSUPPORTED"


def test_count_compare_evaluates_integer_fact():
    snapshot = _snapshot()
    rule = Rule(
        rule_id="hole-count",
        version="1",
        requirement_refs=["req-1"],
        subject_selector=SubjectSelector(entity_kind="solid"),
        inputs=[RuleInput(name="holes", predicate="hole.count")],
        checker="count.compare",
        parameters={"operator": "==", "threshold": 4},
        severity="error",
        source={"reviewed_by": "test"},
    )
    holes = _fact(snapshot.entities[0], "hole.count", 4, "dimensionless")

    report = review(_request(snapshot, [rule], facts=[holes], discovery_requirements=("solid",)))

    assert report.findings[0].status == "satisfied"
    assert report.overall_status == "compliant_for_scope"


def test_checker_exception_becomes_checker_failed_and_tool_error():
    snapshot = _snapshot()
    bad = _fact(snapshot.entities[0], "bbox.extent.z", "abc")

    report = review(_request(snapshot, [_rule()], facts=[bad]))

    assert report.findings[0].status == "unknown"
    assert report.findings[0].reason_code == "CHECKER_FAILED"
    assert report.tool_error is True
    assert report.complete is False
    assert report.overall_status == "incomplete"


def test_unmet_discovery_requirement_prevents_compliance():
    snapshot = _snapshot()
    fact = _fact(snapshot.entities[0], "bbox.extent.z", 10.0)

    report = review(
        _request(snapshot, [_rule()], facts=[fact], discovery_requirements=("solid", "face"))
    )

    assert report.findings[0].status == "satisfied"
    assert report.complete is False
    assert [diagnostic.code for diagnostic in report.diagnostics] == ["DISCOVERY_REQUIREMENT_UNMET"]


def test_all_not_applicable_scope_is_not_compliant():
    snapshot = _snapshot()
    rule = _rule(applicability={"fact_predicate": "applicable", "equals": True})
    facts = [_fact(snapshot.entities[0], "applicable", False, "dimensionless")]

    report = review(_request(snapshot, [rule], facts=facts))

    assert report.findings[0].status == "not_applicable"
    assert report.complete is False
    assert report.overall_status == "incomplete"


def test_discovery_impact_diagnostic_blocks_complete():
    diagnostic = Diagnostic(
        code="ENTITY_SKIPPED",
        severity="warning",
        stage="read",
        message="Skipped entity",
        impact="none",
        discovery_impact="partial",
        disposition="open",
    )
    snapshot = _snapshot(diagnostics=[diagnostic])
    fact = _fact(snapshot.entities[0], "bbox.extent.z", 10.0)

    report = review(_request(snapshot, [_rule()], facts=[fact]))

    assert report.complete is False
    assert report.overall_status == "incomplete"


def test_wildcard_scope_input_only_covers_in_scope_kinds():
    snapshot = _snapshot(kinds=("solid", "body"))
    fact = _fact(snapshot.entities[0], "bbox.extent.z", 10.0)
    mass = FactRequest(name="mass", predicate="mass", subject_id="*")
    rule = _rule()
    rule = rule.model_copy(update={"subject_selector": SubjectSelector(entity_kind="solid")})

    report = review(
        _request(
            snapshot,
            [rule],
            facts=[fact],
            required_inputs=[mass],
            discovery_requirements=("solid",),
        )
    )

    assert {gap.subject.entity_id for gap in report.generated_gaps if gap.subject} == {"solid:0"}
    assert report.coverage.fully_inspected_entities == 0


def _bound_request():
    snapshot = _snapshot()
    facts = [
        _fact(snapshot.entities[0], "bbox.extent.z", 10.0),
        _fact(snapshot.entities[0], "bbox.extent.x", 20.0),
    ]
    return _request(snapshot, [_rule()], facts=facts)


@pytest.mark.parametrize(
    ("update", "message"),
    [
        (lambda request: {"snapshot": request.snapshot.model_copy(update={"parse_options": {"x": 1}})}, "snapshot_content_hash"),
        (
            lambda request: {
                "ruleset": request.ruleset.model_copy(
                    update={
                        "requirement_bundle": request.ruleset.requirement_bundle.model_copy(
                            update={
                                "requirements": [
                                    request.ruleset.requirement_bundle.requirements[0].model_copy(
                                        update={"text": "Changed text"}
                                    )
                                ]
                            }
                        )
                    }
                )
            },
            "content_hash",
        ),
        (
            lambda request: {
                "ruleset": request.ruleset.model_copy(
                    update={
                        "requirement_bundle": request.ruleset.requirement_bundle.model_copy(
                            update={"bundle_id": "0" * 64}
                        )
                    }
                )
            },
            "bundle_id",
        ),
        (lambda request: {"ruleset": request.ruleset.model_copy(update={"ruleset_id": "0" * 64})}, "ruleset_id"),
        (lambda request: {"scope": request.scope.model_copy(update={"scope_id": "0" * 64})}, "scope_id"),
        (lambda request: {"context": request.context.model_copy(update={"context_id": "0" * 64})}, "context_id"),
        (lambda request: {"factset": request.factset.model_copy(update={"factset_id": "0" * 64})}, "factset_id"),
    ],
)
def test_tampered_content_identity_is_rejected(update, message):
    request = _bound_request()
    request = request.model_copy(update=update(request))

    with pytest.raises(ValueError, match=message):
        review(request)


def test_tampered_fact_identity_is_rejected():
    request = _bound_request()
    facts = [request.factset.facts[0].model_copy(update={"value": 11.0}), *request.factset.facts[1:]]
    request = request.model_copy(update={"factset": request.factset.model_copy(update={"facts": facts})})

    with pytest.raises(ValueError, match="does not match its content"):
        review(request)


def test_reordering_unordered_inputs_preserves_report_identity():
    first_requirement = _requirement("req-a")
    second_requirement = _requirement("req-b")
    first_rule = _rule(rule_id="a-rule", requirement_refs=["req-a", "req-b"])
    second_rule = _rule(rule_id="b-rule", requirement_refs=["req-b", "req-a"])
    first_snapshot = _snapshot()
    second_snapshot = _snapshot()
    first_facts = [
        _fact(first_snapshot.entities[0], "bbox.extent.z", 10.0),
        _fact(first_snapshot.entities[0], "bbox.extent.x", 20.0),
    ]
    second_facts = [
        _fact(second_snapshot.entities[0], "bbox.extent.x", 20.0),
        _fact(second_snapshot.entities[0], "bbox.extent.z", 10.0),
    ]
    first = _request(
        first_snapshot,
        [first_rule, second_rule],
        facts=first_facts,
        included_rules=[RuleRef(rule_id="a-rule"), RuleRef(rule_id="b-rule")],
        discovery_requirements=("solid",),
        requirements=[first_requirement, second_requirement],
    )
    second = _request(
        second_snapshot,
        [second_rule, first_rule],
        facts=second_facts,
        included_rules=[RuleRef(rule_id="b-rule"), RuleRef(rule_id="a-rule")],
        discovery_requirements=("solid",),
        requirements=[second_requirement, first_requirement],
    )

    first_report = review(first)
    second_report = review(second)

    assert first_report.review_run_id == second_report.review_run_id
    assert first_report.report_id == second_report.report_id
    assert [finding.finding_id for finding in first_report.findings] == [
        finding.finding_id for finding in second_report.findings
    ]
