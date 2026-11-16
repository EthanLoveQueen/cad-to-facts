from cad_to_facts.domain.facts import ExtractionQuery, FactSet
from cad_to_facts.domain.review import Requirement, RequirementBundle, ReviewContext, ReviewRequest, ReviewScope, Rule, RuleInput, RuleSet, SubjectSelector
from cad_to_facts.domain.snapshot import EntityRef, ModelSnapshot
from cad_to_facts.review import review
from contract_helpers import bind_request


def test_missing_fact_and_gap_generates_not_computed_gap():
    subject = EntityRef(snapshot_id="b" * 64, entity_id="solid:0", entity_kind="solid")
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
        entities=[subject],
        diagnostics=[],
    )
    requirement = Requirement(
        requirement_id="req-height",
        text="Height must be measured",
        source_ref="test:height",
        content_hash="e" * 64,
    )
    rule = Rule(
        rule_id="height-present",
        version="1",
        requirement_refs=[requirement.requirement_id],
        subject_selector=SubjectSelector(entity_kind="solid"),
        inputs=[RuleInput(name="height", predicate="bbox.extent.z")],
        checker="fact.present",
        parameters={},
        severity="error",
        source={"reviewed_by": "test"},
    )
    request = bind_request(
        ReviewRequest(
            snapshot=snapshot,
            factset=FactSet(
                factset_id="d" * 64,
                snapshot_id=snapshot.snapshot_id,
                snapshot_content_hash=snapshot.snapshot_content_hash,
                extraction_query=ExtractionQuery(requests=[]),
                extractor_version="1",
                facts=[],
                gaps=[],
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
                required_inputs=[],
                discovery_requirements=["solid"],
            ),
            context=ReviewContext(context_id="4" * 64, values={}),
            reviewer_version="0.1.0",
        )
    )

    report = review(request)

    assert report.findings[0].status == "unknown"
    assert report.findings[0].reason_code == "NOT_COMPUTED"
    assert len(report.generated_gaps) == 1
    assert report.generated_gaps[0].reason_code == "NOT_COMPUTED"
    assert request.factset.gaps == []
