from cad_to_facts.domain.facts import Evidence, ExtractionQuery, Fact, FactRequest, FactSet, Method
from cad_to_facts.domain.review import Requirement, RequirementBundle, ReviewContext, ReviewRequest, ReviewScope, Rule, RuleInput, RuleSet, SubjectSelector
from cad_to_facts.domain.snapshot import EntityRef, ModelSnapshot
from cad_to_facts.review import review
from contract_helpers import bind_request


def _fact(subject, predicate, value, unit, fact_id):
    return Fact(
        fact_id=fact_id,
        kind="declared" if predicate == "review.applicable" else "measured",
        subject=subject,
        predicate=predicate,
        value=value,
        unit=unit,
        evidence=Evidence(artifact_sha256="a" * 64, entity_refs=[subject]),
        method=Method(library="test", algorithm="literal", version="1"),
    )


def test_unknown_applicability_stays_in_entity_coverage_denominator():
    first = EntityRef(snapshot_id="b" * 64, entity_id="solid:0", entity_kind="solid")
    second = EntityRef(snapshot_id="b" * 64, entity_id="solid:1", entity_kind="solid")
    snapshot = ModelSnapshot(
        artifact_sha256="a" * 64,
        snapshot_id="b" * 64,
        snapshot_content_hash="c" * 64,
        adapter_id="test",
        adapter_version="1",
        parser_kernel_version="1",
        parse_options={},
        units={"length": "mm"},
        status="ready",
        entity_discovery="complete",
        entities=[first, second],
        diagnostics=[],
    )
    facts = [
        _fact(first, "review.applicable", True, "dimensionless", "1" * 64),
        _fact(first, "bbox.extent.z", 10.0, "mm", "2" * 64),
        _fact(second, "bbox.extent.z", 20.0, "mm", "3" * 64),
    ]
    requirement = Requirement(
        requirement_id="req-height",
        text="Applicable parts must satisfy the height limit",
        source_ref="test:height",
        content_hash="e" * 64,
    )
    rule = Rule(
        rule_id="max-height",
        version="1",
        requirement_refs=[requirement.requirement_id],
        subject_selector=SubjectSelector(entity_kind="solid"),
        applicability={"fact_predicate": "review.applicable", "equals": True},
        inputs=[RuleInput(name="height", predicate="bbox.extent.z")],
        checker="numeric.compare",
        parameters={"operator": "<=", "threshold": 30.0, "unit": "mm", "abs_tol": 1e-7},
        severity="error",
        source={"reviewed_by": "test"},
    )
    height_request = FactRequest(name="height", predicate="bbox.extent.z", subject_id="*")
    request = bind_request(
        ReviewRequest(
            snapshot=snapshot,
            factset=FactSet(
                factset_id="d" * 64,
                snapshot_id=snapshot.snapshot_id,
                snapshot_content_hash=snapshot.snapshot_content_hash,
                extraction_query=ExtractionQuery(requests=[height_request]),
                extractor_version="1",
                facts=facts,
                gaps=[],
                diagnostics=[],
            ),
            ruleset=RuleSet(
                ruleset_id="4" * 64,
                version="1",
                requirement_bundle=RequirementBundle(bundle_id="f" * 64, requirements=[requirement]),
                rules=[rule],
            ),
            scope=ReviewScope(
                scope_id="5" * 64,
                included_rules=[rule.rule_id],
                subject_selectors=[SubjectSelector(entity_kind="solid")],
                required_inputs=[height_request],
                discovery_requirements=["solid"],
            ),
            context=ReviewContext(context_id="6" * 64, values={}),
            reviewer_version="0.1.0",
        )
    )

    report = review(request)

    statuses = {finding.subject.entity_id: finding.status for finding in report.findings}
    assert statuses == {"solid:0": "satisfied", "solid:1": "unknown"}
    assert report.findings[1].reason_code == "APPLICABILITY_UNKNOWN"
    assert report.coverage.decision_required_entities == 2
    assert report.coverage.fully_inspected_entities == 1
    assert report.coverage.entity_coverage == 0.5
    assert report.overall_status == "incomplete"
