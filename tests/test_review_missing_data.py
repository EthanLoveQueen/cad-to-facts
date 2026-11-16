from cad_to_facts.domain.facts import Evidence, ExtractionQuery, FactGap, FactRequest, FactSet
from cad_to_facts.domain.review import (
    Requirement,
    RequirementBundle,
    ReviewContext,
    ReviewRequest,
    ReviewScope,
    Rule,
    RuleInput,
    RuleSet,
    SubjectSelector,
)
from cad_to_facts.domain.snapshot import EntityRef, ModelSnapshot
from cad_to_facts.review import review
from contract_helpers import bind_request


def test_absent_material_violates_presence_but_value_comparison_is_unknown():
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
        entities=[EntityRef(snapshot_id="b" * 64, entity_id="solid:0", entity_kind="solid")],
        diagnostics=[],
    )
    request = FactRequest(name="material", predicate="material", subject_id="solid:0")
    gap = FactGap(
        request=request,
        subject=snapshot.entities[0],
        reason_code="ABSENT",
        evidence=Evidence(artifact_sha256=snapshot.artifact_sha256, entity_refs=[snapshot.entities[0]]),
    )
    factset = FactSet(
        factset_id="d" * 64,
        snapshot_id=snapshot.snapshot_id,
        snapshot_content_hash=snapshot.snapshot_content_hash,
        extraction_query=ExtractionQuery(requests=[request]),
        extractor_version="1",
        facts=[],
        gaps=[gap],
        diagnostics=[],
    )
    requirements = RequirementBundle(
        bundle_id="e" * 64,
        requirements=[
            Requirement(requirement_id="req-present", text="Material must be declared", source_ref="test:1", content_hash="f" * 64),
            Requirement(requirement_id="req-value", text="Material must be 6061", source_ref="test:2", content_hash="1" * 64),
        ],
    )
    rules = [
        Rule(
            rule_id="material-present",
            version="1",
            requirement_refs=["req-present"],
            subject_selector=SubjectSelector(entity_kind="solid"),
            inputs=[RuleInput(name="material", predicate="material")],
            checker="fact.present",
            parameters={},
            severity="error",
            source={"reviewed_by": "test"},
        ),
        Rule(
            rule_id="material-value",
            version="1",
            requirement_refs=["req-value"],
            subject_selector=SubjectSelector(entity_kind="solid"),
            inputs=[RuleInput(name="material", predicate="material")],
            checker="declared.value",
            parameters={"equals": "6061"},
            severity="error",
            source={"reviewed_by": "test"},
        ),
    ]
    ruleset = RuleSet(ruleset_id="2" * 64, version="1", requirement_bundle=requirements, rules=rules)
    scope = ReviewScope(
        scope_id="3" * 64,
        included_rules=[rule.rule_id for rule in rules],
        subject_selectors=[SubjectSelector(entity_kind="solid")],
        required_inputs=[request],
        discovery_requirements=["solid"],
    )
    request = bind_request(
        ReviewRequest(
            snapshot=snapshot,
            factset=factset,
            ruleset=ruleset,
            scope=scope,
            context=ReviewContext(context_id="4" * 64, values={}),
            reviewer_version="0.1.0",
        )
    )

    report = review(request)

    statuses = {finding.rule_id: finding.status for finding in report.findings}
    assert statuses == {"material-present": "violated", "material-value": "unknown"}
    assert report.overall_status == "non_compliant"
    assert report.complete is False
    assert report.coverage.rule_covered == 1
    assert report.coverage.rule_total == 2
    assert report.coverage.fully_inspected_entities == 0
    assert report.coverage.decision_required_entities == 1
