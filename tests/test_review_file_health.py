from cad_to_facts.artifact import register
from cad_to_facts.domain.facts import ExtractionQuery, FactSet
from cad_to_facts.domain.review import Requirement, RequirementBundle, ReviewContext, ReviewRequest, ReviewScope, Rule, RuleSet, SubjectSelector
from cad_to_facts.review import review
from cad_to_facts.snapshot import read
from contract_helpers import bind_request


def test_file_health_review_reports_violation_with_empty_factset(tmp_path):
    path = tmp_path / "broken.step"
    path.write_text("ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n", encoding="ascii")
    snapshot = read(register(path))
    factset = FactSet(
        factset_id="d" * 64,
        snapshot_id=snapshot.snapshot_id,
        snapshot_content_hash=snapshot.snapshot_content_hash,
        extraction_query=ExtractionQuery(requests=[]),
        extractor_version="1",
        facts=[],
        gaps=[],
        diagnostics=[],
    )
    requirement = Requirement(
        requirement_id="req-readable",
        text="The design file must be readable",
        source_ref="test:file-health",
        content_hash="e" * 64,
    )
    rule = Rule(
        rule_id="file-readable",
        version="1",
        requirement_refs=[requirement.requirement_id],
        subject_selector=SubjectSelector(entity_kind="snapshot"),
        inputs=[],
        checker="snapshot.status",
        parameters={"equals": "ready"},
        severity="error",
        source={"reviewed_by": "test"},
    )
    request = bind_request(
        ReviewRequest(
            snapshot=snapshot,
            factset=factset,
            ruleset=RuleSet(
                ruleset_id="2" * 64,
                version="1",
                requirement_bundle=RequirementBundle(bundle_id="f" * 64, requirements=[requirement]),
                rules=[rule],
            ),
            scope=ReviewScope(
                scope_id="3" * 64,
                included_rules=[rule.rule_id],
                subject_selectors=[SubjectSelector(entity_kind="snapshot")],
                required_inputs=[],
                discovery_requirements=[],
            ),
            context=ReviewContext(context_id="4" * 64, values={}),
            reviewer_version="0.1.0",
        )
    )

    report = review(request)

    assert report.findings[0].status == "violated"
    assert report.overall_status == "non_compliant"
    assert report.complete is False
    assert report.coverage.rule_coverage == 1.0
    assert report.coverage.entity_coverage is None
    assert report.diagnostics[0].code == "PARSE_FAILED"
