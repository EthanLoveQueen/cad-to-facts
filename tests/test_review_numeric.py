import pytest

from cad_to_facts.artifact import register
from cad_to_facts.domain.facts import ExtractionQuery, FactRequest
from cad_to_facts.domain.review import Requirement, RequirementBundle, ReviewContext, ReviewRequest, ReviewScope, Rule, RuleInput, RuleSet, SubjectSelector
from cad_to_facts.facts import extract
from cad_to_facts.review import review
from cad_to_facts.snapshot import read

from step_helpers import write_box
from contract_helpers import bind_request


@pytest.mark.parametrize(
    ("threshold", "expected_status", "expected_overall"),
    [(30.0, "satisfied", "compliant_for_scope"), (29.0, "violated", "non_compliant")],
)
def test_numeric_review_uses_measured_value_and_explicit_tolerance(tmp_path, threshold, expected_status, expected_overall):
    path = tmp_path / "box.step"
    write_box(path)
    snapshot = read(register(path))
    fact_request = FactRequest(name="height", predicate="bbox.extent.z", subject_id="solid:0")
    factset = extract(snapshot, ExtractionQuery(requests=[fact_request]))
    requirement = Requirement(
        requirement_id="req-height",
        text="Overall height must not exceed the limit",
        source_ref="test:height",
        content_hash="e" * 64,
    )
    rule = Rule(
        rule_id="max-height",
        version="1",
        requirement_refs=[requirement.requirement_id],
        subject_selector=SubjectSelector(entity_kind="solid"),
        inputs=[RuleInput(name="height", predicate="bbox.extent.z")],
        checker="numeric.compare",
        parameters={"operator": "<=", "threshold": threshold, "unit": "mm", "abs_tol": 1e-7},
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
                subject_selectors=[SubjectSelector(entity_kind="solid")],
                required_inputs=[fact_request],
                discovery_requirements=["solid"],
            ),
            context=ReviewContext(context_id="4" * 64, values={}),
            reviewer_version="0.1.0",
        )
    )

    report = review(request)

    assert report.findings[0].status == expected_status
    assert report.overall_status == expected_overall
    assert report.complete is True
    assert report.coverage.rule_coverage == 1.0
    assert report.coverage.entity_coverage == 1.0
