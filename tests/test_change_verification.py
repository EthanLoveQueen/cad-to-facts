import hashlib
import json
from pathlib import Path

import pytest

from cad_to_facts.artifact import register
from cad_to_facts.contract import (
    bind_approval_record,
    bind_change_plan,
    bind_change_request,
    bind_context,
    bind_execution_record,
    bind_factset,
    bind_requirement_bundle,
    bind_ruleset,
    bind_scope,
    bind_source_manifest,
    bind_verification_profile,
)
from cad_to_facts.domain.change import (
    ApprovalRecord,
    ChangePlan,
    ChangeRequest,
    ComparisonPolicy,
    DataRetentionCheck,
    ExecutionRecord,
    GeneratedArtifact,
    InvariantCheck,
    ManifestFile,
    OriginReview,
    OutputPolicy,
    SourceManifest,
    SourceModification,
    SourceOperation,
    TargetBinding,
    ValueCheck,
    VerificationProfile,
    VerificationRequest,
)
from cad_to_facts.domain.facts import ExtractionQuery, FactGap, FactRequest
from cad_to_facts.cli import main
from cad_to_facts.domain.matching import EntityMatchingProfile, NumericTolerance
from cad_to_facts.domain.review import (
    Requirement,
    RequirementBundle,
    ReviewContext,
    ReviewRequest,
    ReviewScope,
    RuleSet,
)
from cad_to_facts.facts import extract
from cad_to_facts.review import review
from cad_to_facts.snapshot import read
from cad_to_facts.verification import verify_change
from step_helpers import write_box, write_boxes, write_face


def _profile(snapshot):
    return bind_verification_profile(
        VerificationProfile(
            profile_id="0" * 64,
            adapter_id=snapshot.adapter_id,
            adapter_version=snapshot.adapter_version,
            parser_kernel_version=snapshot.parser_kernel_version,
            parse_options=snapshot.parse_options,
            extractor_version="0.1.0",
            extraction_query_template=ExtractionQuery(
                requests=[
                    FactRequest(
                        subject_id="*",
                        predicate=predicate,
                        name=predicate,
                    )
                    for predicate in (
                        "bbox.extent.x",
                        "bbox.extent.y",
                        "bbox.extent.z",
                    )
                ]
            ),
            matching=EntityMatchingProfile(
                profile_id="0" * 64,
                method="adapter_key",
            ),
        )
    )


def _facts(snapshot, profile):
    return extract(
        snapshot,
        ExtractionQuery(
            requests=[
                request.model_copy(update={"subject_id": entity.entity_id})
                for entity in snapshot.entities
                for request in profile.extraction_query_template.requests
            ]
        ),
    )


def _scenario(tmp_path, after_height=40.0, after_width=10.0):
    before_directory = tmp_path / "baseline"
    after_directory = tmp_path / "modified"
    before_directory.mkdir()
    after_directory.mkdir()
    before_source = before_directory / "model.py"
    after_source = after_directory / "model.py"
    before_source.write_text("HEIGHT = 30\n", encoding="utf-8")
    after_source.write_text(f"HEIGHT = {after_height}\n", encoding="utf-8")
    before_path = before_directory / "before.step"
    after_path = after_directory / "after.step"
    write_box(before_path, (10.0, 20.0, 30.0))
    write_box(after_path, (after_width, 20.0, after_height))
    before_artifact = register(before_path)
    after_artifact = register(after_path)
    before_snapshot = read(before_artifact)
    after_snapshot = read(after_artifact)
    profile = _profile(before_snapshot)
    before_facts = _facts(before_snapshot, profile)
    after_facts = _facts(after_snapshot, profile)
    change = bind_change_request(
        ChangeRequest(
            request_id="0" * 64,
            origin_kind="user_intended",
            user_intent="Increase height to 40 mm without changing width or depth",
            base_artifact_sha256=before_artifact.sha256,
            base_snapshot_id=before_snapshot.snapshot_id,
            base_factset_id=before_facts.factset_id,
            verification_profile=profile,
            target_entity_ids=["solid:0"],
            target_checks=[
                ValueCheck(
                    check_id="height-target",
                    subject_id="solid:0",
                    predicate="bbox.extent.z",
                    operator=">=",
                    value=40.0,
                    unit="mm",
                )
            ],
            invariant_checks=[
                InvariantCheck(
                    check_id="width-preserved",
                    subject_id="solid:0",
                    predicate="bbox.extent.x",
                    unit="mm",
                ),
                InvariantCheck(
                    check_id="depth-preserved",
                    subject_id="solid:0",
                    predicate="bbox.extent.y",
                    unit="mm",
                ),
            ],
            comparison=ComparisonPolicy(
                required_baseline_entity_ids=["solid:0"],
                data_retention_not_applicable=True,
            ),
            output_policy=OutputPolicy(path="after.step"),
        )
    )
    return {
        "change": change,
        "before_artifact": before_artifact,
        "after_artifact": after_artifact,
        "before_snapshot": before_snapshot,
        "after_snapshot": after_snapshot,
        "before_factset": before_facts,
        "after_factset": after_facts,
        "before_directory": before_directory,
        "after_directory": after_directory,
    }


def _verification_request(scenario, **updates):
    values = {
        key: scenario[key]
        for key in (
            "change",
            "before_artifact",
            "after_artifact",
            "before_snapshot",
            "after_snapshot",
            "before_factset",
            "after_factset",
        )
    }
    values.update(updates)
    return VerificationRequest(**values)


def _manifest_file(path):
    data = path.read_bytes()
    return ManifestFile(
        path=path.name,
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
    )


def _manifest(scenario, side, parent=None):
    directory = scenario[f"{side}_directory"]
    artifact = scenario[f"{side}_artifact"]
    source = _manifest_file(directory / "model.py")
    generated = GeneratedArtifact(
        **_manifest_file(Path(artifact.source_locator)).model_dump(),
        format="step",
        source_paths=["model.py"],
    )
    return bind_source_manifest(
        SourceManifest(
            manifest_sha256="0" * 64,
            lineage_kind="root" if parent is None else "derived",
            parent_manifest_sha256=parent.manifest_sha256 if parent else None,
            generator={"name": "text-to-cad", "version": "0.11.10"},
            sources=[source],
            generated_artifacts=[generated],
            modified_from=(
                []
                if parent is None
                else [SourceModification(old_path="model.py", new_path="model.py")]
            ),
        )
    )


def test_output_verification_passes_without_inventing_execution_provenance(tmp_path):
    scenario = _scenario(tmp_path)
    report = verify_change(_verification_request(scenario))

    assert report.verification_status == "passed"
    assert report.execution_provenance == "unattested"
    assert report.change_observed == "changed"
    assert report.approval_validation == "not_provided"
    assert report.manifest_validation == "not_applicable"
    assert report.origin_review.state == "not_applicable"
    assert report.after_review.state == "not_applicable"
    assert {check.group: check.status for check in report.checks} == {
        "input_identity": "passed",
        "target": "passed",
        "invariant": "passed",
        "matching": "passed",
        "non_target": "passed",
        "data_retention": "not_applicable",
    }
    assert report.tool_error is False


def _attested_updates(scenario):
    before_manifest = _manifest(scenario, "before")
    after_manifest = _manifest(scenario, "after", before_manifest)
    change = bind_change_request(
        scenario["change"].model_copy(
            update={"base_source_manifest_sha256": before_manifest.manifest_sha256}
        )
    )
    scenario["change"] = change
    plan = bind_change_plan(
        ChangePlan(
            plan_id="0" * 64,
            request_id=change.request_id,
            executor=before_manifest.generator,
            target_bindings=[
                TargetBinding(target_entity_id="solid:0", executor_ref="HEIGHT")
            ],
            operations=[
                SourceOperation(
                    operation_id="set-height",
                    kind="set_parameter",
                    source_path="model.py",
                    parameter="HEIGHT",
                    value=40.0,
                )
            ],
            expected_invalidated_refs=["solid:0"],
            payload={"entrypoint": "model.py"},
            payload_sha256="0" * 64,
            baseline_manifest_validation="passed",
        )
    )
    approval = bind_approval_record(
        ApprovalRecord(
            approval_id="0" * 64,
            request_id=change.request_id,
            plan_id=plan.plan_id,
            base_artifact_sha256=scenario["before_artifact"].sha256,
            base_source_manifest_sha256=before_manifest.manifest_sha256,
            executor=plan.executor,
            payload_sha256=plan.payload_sha256,
            approver="local-user",
            decision="approved",
            approved_at="2026-11-14T00:00:00Z",
        )
    )
    execution = bind_execution_record(
        ExecutionRecord(
            execution_id="0" * 64,
            approval_id=approval.approval_id,
            request_id=change.request_id,
            plan_id=plan.plan_id,
            executor=plan.executor,
            input_sources=before_manifest.sources,
            base_artifact_sha256=scenario["before_artifact"].sha256,
            payload_sha256=plan.payload_sha256,
            new_sources=after_manifest.sources,
            new_artifact_sha256=scenario["after_artifact"].sha256,
            new_source_manifest_sha256=after_manifest.manifest_sha256,
            result="succeeded",
            mode="attested_local",
            log_refs=["run.log"],
            executed_at="2026-11-14T00:01:00Z",
        )
    )
    return {
        "plan": plan,
        "approval": approval,
        "execution": execution,
        "before_manifest": before_manifest,
        "after_manifest": after_manifest,
        "before_manifest_directory": str(scenario["before_directory"]),
        "after_manifest_directory": str(scenario["after_directory"]),
    }


def test_consistent_manifest_approval_and_execution_are_attested(tmp_path):
    scenario = _scenario(tmp_path)
    updates = _attested_updates(scenario)

    report = verify_change(_verification_request(scenario, **updates))

    assert report.verification_status == "passed"
    assert report.manifest_validation == "passed"
    assert report.approval_validation == "passed"
    assert report.execution_provenance == "attested"


def test_review_derived_change_reruns_original_rule_and_resolves_finding(tmp_path):
    scenario = _scenario(tmp_path)
    bundle = bind_requirement_bundle(
        RequirementBundle(
            bundle_id="0" * 64,
            requirements=[
                Requirement(
                    content_hash="0" * 64,
                    requirement_id="req-height",
                    text="Overall height must be at least 40 mm",
                    source_ref="test#req-height",
                )
            ],
        )
    )
    ruleset = bind_ruleset(
        RuleSet(
            ruleset_id="0" * 64,
            version="1",
            requirement_bundle=bundle,
            rules=[
                {
                    "rule_id": "min-height",
                    "version": "1",
                    "requirement_refs": ["req-height"],
                    "subject_selector": {"entity_kind": "solid"},
                    "inputs": [{"name": "height", "predicate": "bbox.extent.z"}],
                    "checker": "numeric.compare",
                    "parameters": {
                        "operator": ">=",
                        "threshold": 40.0,
                        "unit": "mm",
                        "abs_tol": 1e-7,
                    },
                    "severity": "error",
                    "source": {"reviewed_by": "test"},
                }
            ],
        )
    )
    scope = bind_scope(
        ReviewScope(
            scope_id="0" * 64,
            included_rules=[{"rule_id": "min-height", "version": "1"}],
            subject_selectors=[{"entity_kind": "solid"}],
            required_inputs=[],
            discovery_requirements=["solid"],
        )
    )
    context = bind_context(ReviewContext(context_id="0" * 64, values={}))
    origin_facts = extract(
        scenario["before_snapshot"],
        ExtractionQuery(
            requests=[
                FactRequest(
                    subject_id="solid:0",
                    predicate="bbox.extent.z",
                    name="height",
                )
            ]
        ),
    )
    origin_report = review(
        ReviewRequest(
            snapshot=scenario["before_snapshot"],
            factset=origin_facts,
            ruleset=ruleset,
            scope=scope,
            context=context,
            reviewer_version="0.1.0",
        )
    )
    origin_finding = origin_report.findings[0]
    assert origin_finding.status == "violated"
    origin = OriginReview(
        review_run_id=origin_report.review_run_id,
        finding_id=origin_finding.finding_id,
        origin_report_id=origin_report.report_id,
        ruleset=ruleset,
        scope=scope,
        context=context,
        reviewer_version="0.1.0",
    )
    change = bind_change_request(
        scenario["change"].model_copy(
            update={
                "origin_kind": "review_derived",
                "origin_review": origin,
                "base_factset_id": origin_facts.factset_id,
                "verification_base_factset_id": scenario["before_factset"].factset_id,
            }
        )
    )
    scenario["change"] = change

    report = verify_change(
        _verification_request(scenario, origin_review=origin_report)
    )

    assert report.verification_status == "passed"
    assert report.origin_review.state == "present"
    assert report.after_review.state == "present"
    original_checks = [
        check for check in report.checks if check.group == "original_rule"
    ]
    assert len(original_checks) == 3
    assert all(check.status == "passed" for check in original_checks)


def test_unrelated_original_rule_violation_fails_re_review(tmp_path):
    scenario = _scenario(tmp_path)
    bundle = bind_requirement_bundle(
        RequirementBundle(
            bundle_id="0" * 64,
            requirements=[
                Requirement(
                    content_hash="0" * 64,
                    requirement_id="req-height",
                    text="Height must be at least 40 mm",
                    source_ref="test#height",
                ),
                Requirement(
                    content_hash="0" * 64,
                    requirement_id="req-depth",
                    text="Depth must not exceed 15 mm",
                    source_ref="test#depth",
                ),
            ],
        )
    )
    ruleset = bind_ruleset(
        RuleSet(
            ruleset_id="0" * 64,
            version="1",
            requirement_bundle=bundle,
            rules=[
                {
                    "rule_id": "min-height",
                    "version": "1",
                    "requirement_refs": ["req-height"],
                    "subject_selector": {"entity_kind": "solid"},
                    "inputs": [{"name": "height", "predicate": "bbox.extent.z"}],
                    "checker": "numeric.compare",
                    "parameters": {
                        "operator": ">=",
                        "threshold": 40.0,
                        "unit": "mm",
                        "abs_tol": 1e-7,
                    },
                    "severity": "error",
                    "source": {"reviewed_by": "test"},
                },
                {
                    "rule_id": "max-depth",
                    "version": "1",
                    "requirement_refs": ["req-depth"],
                    "subject_selector": {"entity_kind": "solid"},
                    "inputs": [{"name": "depth", "predicate": "bbox.extent.y"}],
                    "checker": "numeric.compare",
                    "parameters": {
                        "operator": "<=",
                        "threshold": 15.0,
                        "unit": "mm",
                        "abs_tol": 1e-7,
                    },
                    "severity": "error",
                    "source": {"reviewed_by": "test"},
                },
            ],
        )
    )
    scope = bind_scope(
        ReviewScope(
            scope_id="0" * 64,
            included_rules=[
                {"rule_id": "min-height", "version": "1"},
                {"rule_id": "max-depth", "version": "1"},
            ],
            subject_selectors=[{"entity_kind": "solid"}],
            required_inputs=[],
            discovery_requirements=["solid"],
        )
    )
    context = bind_context(ReviewContext(context_id="0" * 64, values={}))
    origin_facts = extract(
        scenario["before_snapshot"],
        ExtractionQuery(
            requests=[
                FactRequest(
                    subject_id="solid:0", predicate="bbox.extent.z", name="height"
                ),
                FactRequest(
                    subject_id="solid:0", predicate="bbox.extent.y", name="depth"
                ),
            ]
        ),
    )
    origin_report = review(
        ReviewRequest(
            snapshot=scenario["before_snapshot"],
            factset=origin_facts,
            ruleset=ruleset,
            scope=scope,
            context=context,
            reviewer_version="0.1.0",
        )
    )
    origin_finding = next(
        finding for finding in origin_report.findings if finding.rule_id == "min-height"
    )
    origin = OriginReview(
        review_run_id=origin_report.review_run_id,
        finding_id=origin_finding.finding_id,
        origin_report_id=origin_report.report_id,
        ruleset=ruleset,
        scope=scope,
        context=context,
        reviewer_version="0.1.0",
    )
    scenario["change"] = bind_change_request(
        scenario["change"].model_copy(
            update={
                "origin_kind": "review_derived",
                "origin_review": origin,
                "base_factset_id": origin_facts.factset_id,
                "verification_base_factset_id": scenario["before_factset"].factset_id,
            }
        )
    )

    report = verify_change(
        _verification_request(scenario, origin_review=origin_report)
    )

    assert report.verification_status == "failed"
    review_check = next(
        check for check in report.checks if check.check_id == "original-rule-review"
    )
    assert review_check.status == "failed"
    assert review_check.actual == "non_compliant"
    assert next(
        check for check in report.checks if check.check_id == "origin-finding-resolution"
    ).status == "passed"


def test_same_file_reports_no_change_without_overriding_target_checks(tmp_path):
    scenario = _scenario(tmp_path)
    change = bind_change_request(
        scenario["change"].model_copy(
            update={
                "target_checks": [
                    scenario["change"].target_checks[0].model_copy(
                        update={"operator": ">=", "value": 30.0}
                    )
                ],
                "output_policy": OutputPolicy(path="before.step"),
            }
        )
    )
    scenario["change"] = change

    report = verify_change(
        _verification_request(
            scenario,
            after_artifact=scenario["before_artifact"],
            after_snapshot=scenario["before_snapshot"],
            after_factset=scenario["before_factset"],
        )
    )

    assert report.change_observed == "no_change"
    assert report.verification_status == "passed"
    assert not any(check.reason_code == "NO_CHANGE_OBSERVED" for check in report.checks)


@pytest.mark.parametrize(
    ("scenario_options", "failed_check"),
    [
        ({"after_height": 39.0}, "height-target"),
        ({"after_width": 11.0}, "width-preserved"),
    ],
)
def test_target_or_invariant_failure_fails_verification(
    tmp_path, scenario_options, failed_check
):
    scenario = _scenario(tmp_path, **scenario_options)
    report = verify_change(_verification_request(scenario))

    assert report.verification_status == "failed"
    assert next(
        check for check in report.checks if check.check_id == failed_check
    ).status == "failed"
    assert report.execution_provenance == "unattested"


def test_target_unit_mismatch_stays_incomplete(tmp_path):
    scenario = _scenario(tmp_path)
    scenario["change"] = bind_change_request(
        scenario["change"].model_copy(
            update={
                "target_checks": [
                    scenario["change"].target_checks[0].model_copy(update={"unit": "in"})
                ]
            }
        )
    )

    report = verify_change(_verification_request(scenario))

    assert report.verification_status == "incomplete"
    target = next(
        check for check in report.checks if check.check_id == "height-target"
    )
    assert target.reason_code == "UNIT_MISMATCH"
    assert target.expected == "in"
    assert target.actual == "mm"


def test_stale_base_artifact_is_rejected(tmp_path):
    scenario = _scenario(tmp_path)
    scenario["change"] = bind_change_request(
        scenario["change"].model_copy(update={"base_artifact_sha256": "0" * 64})
    )

    report = verify_change(_verification_request(scenario))

    assert report.verification_status == "failed"
    identity = next(check for check in report.checks if check.group == "input_identity")
    assert identity.reason_code == "STALE_OR_MISMATCHED_INPUT"


def test_unresolved_candidate_discovery_makes_verification_incomplete(tmp_path):
    scenario = _scenario(tmp_path)
    after_path = scenario["after_directory"] / "after.step"
    write_face(after_path)
    after_artifact = register(after_path)
    after_snapshot = read(after_artifact)
    after_facts = _facts(after_snapshot, scenario["change"].verification_profile)

    report = verify_change(
        _verification_request(
            scenario,
            after_artifact=after_artifact,
            after_snapshot=after_snapshot,
            after_factset=after_facts,
        )
    )

    assert report.verification_status == "incomplete"
    assert report.entity_matches[0].status == "unmatched"
    assert next(
        check for check in report.checks if check.group == "non_target"
    ).status == "incomplete"
    assert not any(check.status == "failed" for check in report.checks)


def test_changing_plan_after_approval_invalidates_provenance(tmp_path):
    scenario = _scenario(tmp_path)
    updates = _attested_updates(scenario)
    changed_plan = bind_change_plan(
        updates["plan"].model_copy(
            update={
                "operations": [
                    updates["plan"].operations[0].model_copy(update={"value": 41.0})
                ]
            }
        )
    )
    updates["plan"] = changed_plan

    report = verify_change(_verification_request(scenario, **updates))

    assert report.verification_status == "failed"
    assert report.approval_validation == "failed"
    assert report.execution_provenance == "contradicted"


def test_changing_request_after_approval_invalidates_provenance(tmp_path):
    scenario = _scenario(tmp_path)
    updates = _attested_updates(scenario)
    scenario["change"] = bind_change_request(
        scenario["change"].model_copy(
            update={
                "target_checks": [
                    scenario["change"].target_checks[0].model_copy(
                        update={"value": 41.0}
                    )
                ]
            }
        )
    )

    report = verify_change(_verification_request(scenario, **updates))

    assert report.approval_validation == "failed"
    assert report.execution_provenance == "contradicted"
    assert next(
        check
        for check in report.checks
        if check.check_id == "complete-request-plan-binding"
    ).reason_code == "APPROVAL_BINDING_MISMATCH"


def test_execution_record_for_a_different_output_is_contradicted(tmp_path):
    scenario = _scenario(tmp_path)
    updates = _attested_updates(scenario)
    updates["execution"] = bind_execution_record(
        updates["execution"].model_copy(update={"new_artifact_sha256": "0" * 64})
    )

    report = verify_change(_verification_request(scenario, **updates))

    assert report.verification_status == "failed"
    assert report.approval_validation == "passed"
    assert report.execution_provenance == "contradicted"


def test_bad_manifest_parent_fails_source_lineage(tmp_path):
    scenario = _scenario(tmp_path)
    updates = _attested_updates(scenario)
    updates["after_manifest"] = bind_source_manifest(
        updates["after_manifest"].model_copy(
            update={"parent_manifest_sha256": "0" * 64}
        )
    )
    for key in ("plan", "approval", "execution"):
        updates.pop(key)

    report = verify_change(_verification_request(scenario, **updates))

    assert report.verification_status == "failed"
    assert report.manifest_validation == "failed"
    assert report.execution_provenance == "unattested"
    assert next(
        check for check in report.checks if check.check_id == "source-lineage"
    ).status == "failed"


def test_wrong_modified_from_source_mapping_fails_lineage(tmp_path):
    scenario = _scenario(tmp_path)
    updates = _attested_updates(scenario)
    updates["after_manifest"] = bind_source_manifest(
        updates["after_manifest"].model_copy(
            update={
                "modified_from": [
                    SourceModification(old_path="other.py", new_path="model.py")
                ]
            }
        )
    )
    for key in ("plan", "approval", "execution"):
        updates.pop(key)

    report = verify_change(_verification_request(scenario, **updates))

    assert report.manifest_validation == "failed"
    assert next(
        check for check in report.checks if check.check_id == "source-lineage"
    ).reason_code == "MANIFEST_LINEAGE_MISMATCH"


def test_changed_source_requires_an_explicit_modified_from_mapping(tmp_path):
    scenario = _scenario(tmp_path)
    updates = _attested_updates(scenario)
    updates["after_manifest"] = bind_source_manifest(
        updates["after_manifest"].model_copy(update={"modified_from": []})
    )
    for key in ("plan", "approval", "execution"):
        updates.pop(key)

    report = verify_change(_verification_request(scenario, **updates))

    assert report.manifest_validation == "failed"
    assert next(
        check for check in report.checks if check.check_id == "source-lineage"
    ).reason_code == "MANIFEST_LINEAGE_MISMATCH"


def test_unplanned_added_source_fails_manifest_plan_binding(tmp_path):
    scenario = _scenario(tmp_path)
    updates = _attested_updates(scenario)
    extra_source = scenario["after_directory"] / "extra.py"
    extra_source.write_text("EXTRA = True\n", encoding="utf-8")
    after_manifest = updates["after_manifest"]
    updates["after_manifest"] = bind_source_manifest(
        after_manifest.model_copy(
            update={"sources": [*after_manifest.sources, _manifest_file(extra_source)]}
        )
    )
    updates.pop("approval")
    updates.pop("execution")

    report = verify_change(_verification_request(scenario, **updates))

    assert report.manifest_validation == "failed"
    assert report.approval_validation == "failed"
    assert next(
        check for check in report.checks if check.check_id == "source-lineage"
    ).reason_code == "MANIFEST_LINEAGE_MISMATCH"


def test_source_backed_request_without_manifests_is_incomplete(tmp_path):
    scenario = _scenario(tmp_path)
    scenario["change"] = bind_change_request(
        scenario["change"].model_copy(
            update={"base_source_manifest_sha256": "a" * 64}
        )
    )

    report = verify_change(_verification_request(scenario))

    assert report.verification_status == "incomplete"
    assert report.manifest_validation == "incomplete"
    assert report.execution_provenance == "unattested"
    assert next(
        check for check in report.checks if check.group == "manifest"
    ).reason_code == "REQUIRED_MANIFESTS_MISSING"


def test_explicit_data_retention_check_is_evaluated(tmp_path):
    scenario = _scenario(tmp_path)
    scenario["change"] = bind_change_request(
        scenario["change"].model_copy(
            update={
                "comparison": scenario["change"].comparison.model_copy(
                    update={"data_retention_not_applicable": False}
                ),
                "data_retention_checks": [
                    DataRetentionCheck(
                        check_id="external-width-declaration",
                        subject_id="solid:0",
                        predicate="bbox.extent.x",
                        unit="mm",
                        expectation="preserved",
                    )
                ],
            }
        )
    )

    report = verify_change(_verification_request(scenario))

    assert report.verification_status == "passed"
    retention = next(
        check for check in report.checks if check.group == "data_retention"
    )
    assert retention.check_id == "external-width-declaration"
    assert retention.status == "passed"


def test_explicit_data_invalidation_requires_and_accepts_proven_absence(tmp_path):
    scenario = _scenario(tmp_path)
    predicate = "declared.external_note"
    template_request = FactRequest(
        subject_id="*", predicate=predicate, name="external-note"
    )
    concrete_request = template_request.model_copy(update={"subject_id": "solid:0"})
    before_facts = scenario["before_factset"]
    after_facts = scenario["after_factset"]
    declaration = before_facts.facts[0].model_copy(
        update={"predicate": predicate, "value": "obsolete", "unit": ""}
    )
    before_facts = bind_factset(
        before_facts.model_copy(
            update={
                "facts": [*before_facts.facts, declaration],
                "extraction_query": ExtractionQuery(
                    requests=[
                        *before_facts.extraction_query.requests,
                        concrete_request,
                    ]
                ),
            }
        )
    )
    after_gap = FactGap(
        request=concrete_request,
        subject=after_facts.facts[0].subject,
        reason_code="ABSENT",
        evidence=after_facts.facts[0].evidence,
    )
    after_facts = bind_factset(
        after_facts.model_copy(
            update={
                "gaps": [*after_facts.gaps, after_gap],
                "extraction_query": ExtractionQuery(
                    requests=[*after_facts.extraction_query.requests, concrete_request]
                ),
            }
        )
    )
    profile = bind_verification_profile(
        scenario["change"].verification_profile.model_copy(
            update={
                "extraction_query_template": ExtractionQuery(
                    requests=[
                        *scenario[
                            "change"
                        ].verification_profile.extraction_query_template.requests,
                        template_request,
                    ]
                )
            }
        )
    )
    scenario["change"] = bind_change_request(
        scenario["change"].model_copy(
            update={
                "base_factset_id": before_facts.factset_id,
                "verification_profile": profile,
                "comparison": scenario["change"].comparison.model_copy(
                    update={"data_retention_not_applicable": False}
                ),
                "data_retention_checks": [
                    DataRetentionCheck(
                        check_id="external-note-invalidated",
                        subject_id="solid:0",
                        predicate=predicate,
                        unit="",
                        expectation="explicitly_invalidated",
                    )
                ],
            }
        )
    )
    scenario["before_factset"] = before_facts
    scenario["after_factset"] = after_facts

    report = verify_change(_verification_request(scenario))

    assert report.verification_status == "passed"
    retention = next(
        check
        for check in report.checks
        if check.check_id == "external-note-invalidated"
    )
    assert retention.status == "passed"
    assert retention.gaps[0].reason_code == "ABSENT"


def test_failed_baseline_precondition_rejects_change(tmp_path):
    scenario = _scenario(tmp_path)
    scenario["change"] = bind_change_request(
        scenario["change"].model_copy(
            update={
                "preconditions": [
                    ValueCheck(
                        check_id="base-height",
                        subject_id="solid:0",
                        predicate="bbox.extent.z",
                        operator="==",
                        value=31.0,
                        unit="mm",
                    )
                ]
            }
        )
    )

    report = verify_change(_verification_request(scenario))

    assert report.verification_status == "failed"
    precondition = next(
        check for check in report.checks if check.group == "precondition"
    )
    assert precondition.status == "failed"
    assert precondition.reason_code == "PRECONDITION_NOT_SATISFIED"


def test_snapshots_must_match_the_approved_verification_profile(tmp_path):
    scenario = _scenario(tmp_path)
    profile = scenario["change"].verification_profile
    scenario["change"] = bind_change_request(
        scenario["change"].model_copy(
            update={
                "verification_profile": profile.model_copy(
                    update={"parse_options": {**profile.parse_options, "read_scope": "other"}}
                )
            }
        )
    )

    report = verify_change(_verification_request(scenario))

    assert report.verification_status == "incomplete"
    profile_check = next(
        check for check in report.checks if check.check_id == "fixed-verification-profile"
    )
    assert profile_check.status == "incomplete"
    assert profile_check.reason_code == "VERIFICATION_PROFILE_MISMATCH"


def test_unexpected_added_entity_fails_non_target_comparison(tmp_path):
    scenario = _scenario(tmp_path)
    after_path = Path(scenario["after_artifact"].source_locator)
    write_boxes(after_path, ((10.0, 20.0, 40.0), (10.0, 20.0, 40.0)))
    after_artifact = register(after_path)
    after_snapshot = read(after_artifact)
    after_facts = _facts(after_snapshot, scenario["change"].verification_profile)

    report = verify_change(
        _verification_request(
            scenario,
            after_artifact=after_artifact,
            after_snapshot=after_snapshot,
            after_factset=after_facts,
        )
    )

    assert report.verification_status == "failed"
    comparison = next(check for check in report.checks if check.group == "non_target")
    assert comparison.status == "failed"
    assert comparison.actual["added"] == ["solid:1"]


def test_unexpected_removed_entity_fails_non_target_comparison(tmp_path):
    scenario = _scenario(tmp_path)
    before_path = Path(scenario["before_artifact"].source_locator)
    write_boxes(before_path)
    before_artifact = register(before_path)
    before_snapshot = read(before_artifact)
    before_facts = _facts(before_snapshot, scenario["change"].verification_profile)
    scenario.update(
        before_artifact=before_artifact,
        before_snapshot=before_snapshot,
        before_factset=before_facts,
    )
    scenario["change"] = bind_change_request(
        scenario["change"].model_copy(
            update={
                "base_artifact_sha256": before_artifact.sha256,
                "base_snapshot_id": before_snapshot.snapshot_id,
                "base_factset_id": before_facts.factset_id,
                "comparison": ComparisonPolicy(
                    required_baseline_entity_ids=["solid:0", "solid:1"],
                    data_retention_not_applicable=True,
                ),
            }
        )
    )

    report = verify_change(_verification_request(scenario))

    assert report.verification_status == "failed"
    comparison = next(check for check in report.checks if check.group == "non_target")
    assert comparison.status == "failed"
    assert comparison.actual["removed"] == ["solid:1"]


def test_ambiguous_fingerprint_match_makes_verification_incomplete(tmp_path):
    scenario = _scenario(tmp_path)
    after_path = Path(scenario["after_artifact"].source_locator)
    write_boxes(after_path, ((10.0, 20.0, 40.0), (10.0, 20.0, 40.0)))
    after_artifact = register(after_path)
    after_snapshot = read(after_artifact)
    profile = bind_verification_profile(
        scenario["change"].verification_profile.model_copy(
            update={
                "matching": EntityMatchingProfile(
                    profile_id="0" * 64,
                    method="fingerprint",
                    fingerprint_predicates=["bbox.extent.x", "bbox.extent.y"],
                )
            }
        )
    )
    after_facts = _facts(after_snapshot, profile)
    scenario["change"] = bind_change_request(
        scenario["change"].model_copy(update={"verification_profile": profile})
    )

    report = verify_change(
        _verification_request(
            scenario,
            after_artifact=after_artifact,
            after_snapshot=after_snapshot,
            after_factset=after_facts,
        )
    )

    assert report.verification_status == "incomplete"
    assert report.entity_matches[0].status == "ambiguous"
    assert report.entity_matches[0].reason_code == "AMBIGUOUS_CANDIDATE"
    assert next(
        check for check in report.checks if check.group == "non_target"
    ).status == "incomplete"


def test_verify_change_cli_reparses_and_reports_unattested_output(tmp_path, capsys):
    scenario = _scenario(tmp_path)
    request_path = tmp_path / "change.json"
    request_path.write_text(scenario["change"].model_dump_json(), encoding="utf-8")

    exit_code = main(
        [
            "verify-change",
            "--request",
            str(request_path),
            "--before",
            scenario["before_artifact"].source_locator,
            "--after",
            scenario["after_artifact"].source_locator,
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["request_id"] == scenario["change"].request_id
    assert output["verification_status"] == "passed"
    assert output["execution_provenance"] == "unattested"
    assert output["after_artifact"]["state"] == "present"


def test_prepare_change_cli_builds_verifiable_review_derived_request(tmp_path, capsys):
    scenario = _scenario(tmp_path)
    requirements_path = tmp_path / "requirements.json"
    rules_path = tmp_path / "rules.json"
    scope_path = tmp_path / "scope.json"
    context_path = tmp_path / "context.json"
    requirements_path.write_text(
        json.dumps(
            {
                "requirements": [
                    {
                        "requirement_id": "req-height",
                        "text": "Overall height must be at least 40 mm",
                        "source_ref": "test#req-height",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    rules_path.write_text(
        json.dumps(
            {
                "version": "1",
                "rules": [
                    {
                        "rule_id": "min-height",
                        "version": "1",
                        "requirement_refs": ["req-height"],
                        "subject_selector": {"entity_kind": "solid"},
                        "inputs": [{"name": "height", "predicate": "bbox.extent.z"}],
                        "checker": "numeric.compare",
                        "parameters": {
                            "operator": ">=",
                            "threshold": 40.0,
                            "unit": "mm",
                            "abs_tol": 1e-7,
                        },
                        "severity": "error",
                        "source": {"reviewed_by": "test"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    scope_path.write_text(
        json.dumps(
            {
                "included_rules": [{"rule_id": "min-height", "version": "1"}],
                "subject_selectors": [{"entity_kind": "solid"}],
                "required_inputs": [],
                "discovery_requirements": ["solid"],
            }
        ),
        encoding="utf-8",
    )
    context_path.write_text('{"values": {}}', encoding="utf-8")
    before = scenario["before_artifact"].source_locator
    assert main(
        [
            "review",
            before,
            "--requirements",
            str(requirements_path),
            "--rules",
            str(rules_path),
            "--scope",
            str(scope_path),
            "--context",
            str(context_path),
        ]
    ) == 0
    origin_report = json.loads(capsys.readouterr().out)
    origin_path = tmp_path / "origin-review.json"
    origin_path.write_text(json.dumps(origin_report), encoding="utf-8")
    finding_id = origin_report["findings"][0]["finding_id"]
    before_manifest = _manifest(scenario, "before")
    after_manifest = _manifest(scenario, "after", before_manifest)
    before_manifest_path = scenario["before_directory"] / "manifest.json"
    after_manifest_path = scenario["after_directory"] / "manifest.json"
    before_manifest_path.write_text(before_manifest.model_dump_json(), encoding="utf-8")
    after_manifest_path.write_text(after_manifest.model_dump_json(), encoding="utf-8")
    spec_path = tmp_path / "prepare.json"
    spec_path.write_text(
        json.dumps(
            {
                "executor": {"name": "text-to-cad", "version": "0.11.10"},
                "target_executor_ref": "HEIGHT",
                "operations": [
                    {
                        "operation_id": "set-height",
                        "kind": "set_parameter",
                        "source_path": "model.py",
                        "parameter": "HEIGHT",
                        "value": 40.0,
                    }
                ],
                "payload": {"entrypoint": "model.py"},
                "output_policy": {"path": "after.step"},
                "matching": {"profile_id": "0" * 64, "method": "adapter_key"},
                "preconditions": [
                    {
                        "check_id": "base-height",
                        "subject_id": "solid:0",
                        "predicate": "bbox.extent.z",
                        "operator": "==",
                        "value": 30.0,
                        "unit": "mm",
                        "tolerance": {"absolute": 1e-7, "relative": 0.0},
                    }
                ],
                "invariant_checks": [
                    {
                        "check_id": "width-preserved",
                        "subject_id": "solid:0",
                        "predicate": "bbox.extent.x",
                        "unit": "mm",
                        "tolerance": {"absolute": 1e-7, "relative": 0.0},
                    },
                    {
                        "check_id": "depth-preserved",
                        "subject_id": "solid:0",
                        "predicate": "bbox.extent.y",
                        "unit": "mm",
                        "tolerance": {"absolute": 1e-7, "relative": 0.0},
                    },
                ],
                "comparison": {
                    "required_baseline_entity_ids": ["solid:0"],
                    "data_retention_not_applicable": True,
                },
            }
        ),
        encoding="utf-8",
    )

    assert main(
        [
            "prepare-change",
            "--report",
            str(origin_path),
            "--finding",
            finding_id,
            "--before",
            before,
            "--requirements",
            str(requirements_path),
            "--rules",
            str(rules_path),
            "--scope",
            str(scope_path),
            "--context",
            str(context_path),
            "--spec",
            str(spec_path),
            "--before-manifest",
            str(before_manifest_path),
        ]
    ) == 0
    preparation = json.loads(capsys.readouterr().out)
    request_path = tmp_path / "prepared-request.json"
    plan_path = tmp_path / "prepared-plan.json"
    request_path.write_text(json.dumps(preparation["request"]), encoding="utf-8")
    plan_path.write_text(json.dumps(preparation["plan"]), encoding="utf-8")

    assert preparation["request"]["origin_kind"] == "review_derived"
    assert preparation["request"]["target_checks"][0]["value"] == 40.0
    assert (
        preparation["request"]["verification_base_factset_id"]
        != preparation["request"]["base_factset_id"]
    )
    assert preparation["plan"]["request_id"] == preparation["request"]["request_id"]

    assert main(
        [
            "verify-change",
            "--request",
            str(request_path),
            "--plan",
            str(plan_path),
            "--before-manifest",
            str(before_manifest_path),
            "--after-manifest",
            str(after_manifest_path),
            "--origin-review",
            str(origin_path),
            "--before",
            before,
            "--after",
            scenario["after_artifact"].source_locator,
        ]
    ) == 0
    verification = json.loads(capsys.readouterr().out)

    assert verification["verification_status"] == "passed"
    assert verification["manifest_validation"] == "passed"
    assert verification["approval_validation"] == "not_provided"
    assert verification["execution_provenance"] == "unattested"
    assert verification["origin_review"]["state"] == "present"
    assert verification["after_review"]["state"] == "present"


def test_target_inequality_uses_declared_tolerance(tmp_path):
    scenario = _scenario(tmp_path, after_height=40.0 - 5e-8)
    target = scenario["change"].target_checks[0]
    scenario["change"] = bind_change_request(
        scenario["change"].model_copy(
            update={
                "target_checks": [
                    target.model_copy(
                        update={"tolerance": NumericTolerance(absolute=1e-7)}
                    )
                ]
            }
        )
    )

    report = verify_change(_verification_request(scenario))

    assert report.verification_status == "passed"
    assert next(
        check for check in report.checks if check.check_id == "height-target"
    ).status == "passed"


def test_verify_change_cli_reports_missing_after_artifact(tmp_path, capsys):
    scenario = _scenario(tmp_path)
    request_path = tmp_path / "change.json"
    request_path.write_text(scenario["change"].model_dump_json(), encoding="utf-8")
    missing = tmp_path / "missing.step"

    exit_code = main(
        [
            "verify-change",
            "--request",
            str(request_path),
            "--before",
            scenario["before_artifact"].source_locator,
            "--after",
            str(missing),
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["verification_status"] == "incomplete"
    assert output["change_observed"] == "unknown"
    assert output["after_artifact"] == {
        "state": "missing",
        "reason_code": "AFTER_ARTIFACT_MISSING",
    }
    assert output["execution_provenance"] == "unattested"


def test_missing_after_artifact_with_failed_precondition_is_failed(tmp_path, capsys):
    scenario = _scenario(tmp_path)
    scenario["change"] = bind_change_request(
        scenario["change"].model_copy(
            update={
                "preconditions": [
                    ValueCheck(
                        check_id="base-height",
                        subject_id="solid:0",
                        predicate="bbox.extent.z",
                        operator="==",
                        value=31.0,
                        unit="mm",
                    )
                ]
            }
        )
    )
    request_path = tmp_path / "change.json"
    request_path.write_text(scenario["change"].model_dump_json(), encoding="utf-8")

    exit_code = main(
        [
            "verify-change",
            "--request",
            str(request_path),
            "--before",
            scenario["before_artifact"].source_locator,
            "--after",
            str(tmp_path / "missing.step"),
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["verification_status"] == "failed"
    assert output["after_artifact"]["state"] == "missing"
    assert output["execution_provenance"] == "unattested"


def test_invalid_approval_without_execution_leaves_provenance_unattested(tmp_path):
    scenario = _scenario(tmp_path)
    updates = _attested_updates(scenario)
    updates["approval"] = bind_approval_record(
        updates["approval"].model_copy(update={"plan_id": "0" * 64})
    )
    updates.pop("execution")

    report = verify_change(_verification_request(scenario, **updates))

    assert report.verification_status == "failed"
    assert report.approval_validation == "failed"
    assert report.execution_provenance == "unattested"


def test_output_location_must_match_the_request_policy(tmp_path):
    scenario = _scenario(tmp_path)
    scenario["change"] = bind_change_request(
        scenario["change"].model_copy(
            update={"output_policy": OutputPolicy(path="different.step")}
        )
    )

    report = verify_change(_verification_request(scenario))

    assert report.verification_status == "failed"
    location = next(
        check for check in report.checks if check.check_id == "output-location"
    )
    assert location.status == "failed"
    assert location.reason_code == "OUTPUT_LOCATION_MISMATCH"


def test_relocated_replay_accepts_a_windows_recorded_output_path(tmp_path):
    """A Windows-recorded absolute path must relocate on POSIX replays too."""

    scenario = _scenario(tmp_path)
    scenario["change"] = bind_change_request(
        scenario["change"].model_copy(
            update={
                "output_policy": OutputPolicy(
                    path="D:/recorded-run/modified/after.step"
                )
            }
        )
    )

    report = verify_change(
        _verification_request(scenario, allow_relocated_output=True)
    )

    assert report.verification_status == "passed"
    location = next(
        check for check in report.checks if check.check_id == "output-location"
    )
    assert location.status == "passed"
    assert "relocated-output replay" in location.message
