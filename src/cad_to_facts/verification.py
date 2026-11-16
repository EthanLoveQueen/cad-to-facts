"""Deterministic, read-only verification of a separately produced CAD artifact."""

import math
from pathlib import Path, PureWindowsPath
from typing import Any

from cad_to_facts.contract import (
    bind_approval_record,
    bind_change_plan,
    bind_execution_record,
    bind_modification_report,
    verify_change_request_identity,
    verify_factset_identity,
    verify_snapshot_identity,
)
from cad_to_facts.domain.change import (
    ChangeRequest,
    ConditionalRef,
    DataRetentionCheck,
    InvariantCheck,
    ModificationReport,
    ValueCheck,
    VerificationCheck,
    VerificationRequest,
)
from cad_to_facts.domain.facts import Fact, FactGap, FactSet
from cad_to_facts.domain.matching import EntityMatchRequest, EntityMatchResult
from cad_to_facts.domain.review import ReviewReport, ReviewRequest
from cad_to_facts.errors import ConfigurationError
from cad_to_facts.identity import structured_hash
from cad_to_facts.manifest import validate_manifest_files
from cad_to_facts.matching import bind_matching_request, match_entities
from cad_to_facts.review import review


def _check(
    group: str,
    check_id: str,
    status: str,
    message: str,
    *,
    subject_id: str | None = None,
    reason_code: str | None = None,
    expected: Any = None,
    actual: Any = None,
    facts: list[Fact] | None = None,
    gaps: list[FactGap] | None = None,
) -> VerificationCheck:
    return VerificationCheck(
        group=group,
        check_id=check_id,
        subject_id=subject_id,
        status=status,
        reason_code=reason_code,
        expected=expected,
        actual=actual,
        facts=facts or [],
        gaps=gaps or [],
        message=message,
    )


def _fact_for(
    factset: FactSet, subject_id: str, predicate: str
) -> tuple[Fact | None, FactGap | None, str | None]:
    facts = [
        fact
        for fact in factset.facts
        if fact.subject.entity_id == subject_id and fact.predicate == predicate
    ]
    if len(facts) > 1:
        return None, None, "DUPLICATE_FACT"
    if facts:
        return facts[0], None, None
    gaps = [
        gap
        for gap in factset.gaps
        if gap.request.subject_id == subject_id and gap.request.predicate == predicate
    ]
    if len(gaps) == 1:
        return None, gaps[0], gaps[0].reason_code
    return None, None, "FACT_NOT_REQUESTED"


def _mapping(results: list[EntityMatchResult]) -> dict[str, str]:
    return {
        result.baseline_entity_id: result.candidate_entity_ids[0]
        for result in results
        if result.status == "matched" and len(result.candidate_entity_ids) == 1
    }


def _compare_value(operator: str, actual: Any, expected: Any, check: ValueCheck) -> bool | None:
    numeric = (
        isinstance(actual, (int, float))
        and not isinstance(actual, bool)
        and isinstance(expected, (int, float))
        and not isinstance(expected, bool)
    )
    if numeric:
        if not math.isfinite(float(actual)) or not math.isfinite(float(expected)):
            return None
        if operator == "==":
            return check.tolerance.within(float(actual), float(expected))
        if operator == "!=":
            return not check.tolerance.within(float(actual), float(expected))
        margin = check.tolerance.absolute + check.tolerance.relative * max(
            abs(float(actual)), abs(float(expected))
        )
        if operator == "<=":
            return actual <= expected + margin
        if operator == ">=":
            return actual >= expected - margin
        if operator == "<":
            return actual < expected
        return actual > expected
    if operator == "==":
        return actual == expected
    if operator == "!=":
        return actual != expected
    return None


def _target_check(
    check: ValueCheck, after_facts: FactSet, entity_map: dict[str, str]
) -> VerificationCheck:
    candidate_id = entity_map.get(check.subject_id)
    if candidate_id is None:
        return _check(
            "target",
            check.check_id,
            "incomplete",
            "The target baseline entity has no unambiguous candidate match",
            subject_id=check.subject_id,
            reason_code="TARGET_ENTITY_UNRESOLVED",
        )
    fact, gap, reason = _fact_for(after_facts, candidate_id, check.predicate)
    if fact is None:
        return _check(
            "target",
            check.check_id,
            "incomplete",
            "The target fact is unavailable",
            subject_id=check.subject_id,
            reason_code=reason,
            gaps=[gap] if gap else None,
        )
    if check.presence_only:
        passed = True
    elif fact.unit != check.unit:
        return _check(
            "target",
            check.check_id,
            "incomplete",
            "The target fact unit does not match the declared check unit",
            subject_id=check.subject_id,
            reason_code="UNIT_MISMATCH",
            expected=check.unit,
            actual=fact.unit,
            facts=[fact],
        )
    else:
        passed = _compare_value(check.operator, fact.value, check.value, check)
    if passed is None:
        return _check(
            "target",
            check.check_id,
            "incomplete",
            "The target values are not comparable",
            subject_id=check.subject_id,
            reason_code="INCOMPARABLE_VALUE",
            facts=[fact],
        )
    return _check(
        "target",
        check.check_id,
        "passed" if passed else "failed",
        "Target constraint evaluated",
        subject_id=check.subject_id,
        reason_code=None if passed else "TARGET_NOT_SATISFIED",
        expected=check.value,
        actual=fact.value,
        facts=[fact],
    )


def _precondition_validation(
    change: ChangeRequest, before_facts: FactSet
) -> list[VerificationCheck]:
    results: list[VerificationCheck] = []
    for precondition in change.preconditions:
        result = _target_check(
            precondition,
            before_facts,
            {precondition.subject_id: precondition.subject_id},
        )
        results.append(
            result.model_copy(
                update={
                    "group": "precondition",
                    "message": "Baseline precondition evaluated",
                    "reason_code": (
                        "PRECONDITION_NOT_SATISFIED"
                        if result.status == "failed"
                        else result.reason_code
                    ),
                }
            )
        )
    return results


def _invariant_check(
    check: InvariantCheck,
    before_facts: FactSet,
    after_facts: FactSet,
    entity_map: dict[str, str],
) -> VerificationCheck:
    candidate_id = entity_map.get(check.subject_id)
    if candidate_id is None:
        return _check(
            "invariant",
            check.check_id,
            "incomplete",
            "The invariant baseline entity has no unambiguous candidate match",
            subject_id=check.subject_id,
            reason_code="INVARIANT_ENTITY_UNRESOLVED",
        )
    before, before_gap, before_reason = _fact_for(
        before_facts, check.subject_id, check.predicate
    )
    after, after_gap, after_reason = _fact_for(
        after_facts, candidate_id, check.predicate
    )
    if before is None or after is None:
        return _check(
            "invariant",
            check.check_id,
            "incomplete",
            "A before or after invariant fact is unavailable",
            subject_id=check.subject_id,
            reason_code=before_reason or after_reason,
            gaps=[gap for gap in (before_gap, after_gap) if gap is not None],
        )
    if before.unit != check.unit or after.unit != check.unit:
        return _check(
            "invariant",
            check.check_id,
            "incomplete",
            "An invariant fact unit does not match the declared check unit",
            subject_id=check.subject_id,
            reason_code="UNIT_MISMATCH",
            expected=check.unit,
            actual={"before": before.unit, "after": after.unit},
            facts=[before, after],
        )
    numeric = (
        isinstance(before.value, (int, float))
        and not isinstance(before.value, bool)
        and isinstance(after.value, (int, float))
        and not isinstance(after.value, bool)
    )
    if numeric:
        if not math.isfinite(float(before.value)) or not math.isfinite(float(after.value)):
            passed = None
        else:
            passed = check.tolerance.within(float(before.value), float(after.value))
    else:
        passed = before.value == after.value
    if passed is None:
        return _check(
            "invariant",
            check.check_id,
            "incomplete",
            "The invariant values are not comparable",
            subject_id=check.subject_id,
            reason_code="INCOMPARABLE_VALUE",
            facts=[before, after],
        )
    return _check(
        "invariant",
        check.check_id,
        "passed" if passed else "failed",
        "Before/after invariant evaluated",
        subject_id=check.subject_id,
        reason_code=None if passed else "INVARIANT_CHANGED",
        expected=before.value,
        actual=after.value,
        facts=[before, after],
    )


def _validate_input_identity(request: VerificationRequest) -> list[VerificationCheck]:
    change = request.change
    expected = {
        "before artifact hash": (request.before_artifact.sha256, change.base_artifact_sha256),
        "before snapshot artifact": (
            request.before_snapshot.artifact_sha256,
            request.before_artifact.sha256,
        ),
        "after snapshot artifact": (
            request.after_snapshot.artifact_sha256,
            request.after_artifact.sha256,
        ),
        "base snapshot ID": (request.before_snapshot.snapshot_id, change.base_snapshot_id),
        "base FactSet ID": (
            request.before_factset.factset_id,
            change.verification_base_factset_id or change.base_factset_id,
        ),
    }
    failures = [name for name, (actual, wanted) in expected.items() if actual != wanted]
    if not failures:
        return []
    return [
        _check(
            "input_identity",
            "base-and-output-identity",
            "failed",
            f"Input identity mismatch: {', '.join(failures)}",
            reason_code="STALE_OR_MISMATCHED_INPUT",
            actual=failures,
        )
    ]


def _non_target_check(
    request: VerificationRequest,
    entity_map: dict[str, str],
    match_results: list[EntityMatchResult],
) -> VerificationCheck:
    policy = request.change.comparison
    if (
        request.before_snapshot.status != "ready"
        or request.after_snapshot.status != "ready"
        or request.before_snapshot.entity_discovery != "complete"
        or request.after_snapshot.entity_discovery != "complete"
        or any(result.status in {"ambiguous", "unresolved"} for result in match_results)
    ):
        return _check(
            "non_target",
            "non-target-comparison",
            "incomplete",
            "Non-target changes cannot be decided without complete discovery and matching",
            reason_code="NON_TARGET_COMPARISON_INCOMPLETE",
        )
    matched_candidates = set(entity_map.values())
    unexpected_added = sorted(
        entity.entity_id
        for entity in request.after_snapshot.entities
        if entity.entity_id not in matched_candidates
        and entity.entity_id not in policy.allowed_added_entity_ids
    )
    required_baseline = set(policy.required_baseline_entity_ids)
    allowed_removed = set(policy.allowed_removed_baseline_entity_ids)
    uncompared = sorted(
        entity.entity_id
        for entity in request.before_snapshot.entities
        if entity.entity_id not in required_baseline
        and entity.entity_id not in allowed_removed
    )
    if uncompared:
        return _check(
            "non_target",
            "non-target-comparison",
            "incomplete",
            "Some baseline entities were neither compared nor explicitly allowed to be removed",
            reason_code="UNCOMPARED_BASELINE_ENTITIES",
            actual=uncompared,
        )
    unexpected_removed = sorted(
        result.baseline_entity_id
        for result in match_results
        if result.status == "unmatched"
        and result.baseline_entity_id not in allowed_removed
    )
    if unexpected_added or unexpected_removed:
        return _check(
            "non_target",
            "entity-additions-removals",
            "failed",
            "The candidate contains unexpected entity additions or removals",
            reason_code="UNEXPECTED_ENTITY_CHANGE",
            actual={"added": unexpected_added, "removed": unexpected_removed},
        )
    target_predicates = {
        (check.subject_id, check.predicate) for check in request.change.target_checks
    }
    evidence: list[Fact] = []
    for baseline_id, candidate_id in entity_map.items():
        for predicate in policy.non_target_predicates:
            if (baseline_id, predicate) in target_predicates:
                continue
            before, _, before_reason = _fact_for(request.before_factset, baseline_id, predicate)
            after, _, after_reason = _fact_for(request.after_factset, candidate_id, predicate)
            if before is None or after is None:
                return _check(
                    "non_target",
                    "non-target-facts",
                    "incomplete",
                    "A non-target comparison fact is unavailable",
                    subject_id=baseline_id,
                    reason_code=before_reason or after_reason,
                )
            evidence.extend([before, after])
            if before.unit != after.unit:
                return _check(
                    "non_target",
                    "non-target-facts",
                    "incomplete",
                    "Non-target comparison units differ",
                    subject_id=baseline_id,
                    reason_code="UNIT_MISMATCH",
                    facts=[before, after],
                )
            if isinstance(before.value, (int, float)) and isinstance(after.value, (int, float)):
                same = policy.non_target_tolerance.within(before.value, after.value)
            else:
                same = before.value == after.value
            if not same:
                return _check(
                    "non_target",
                    "non-target-facts",
                    "failed",
                    "A non-target fact changed unexpectedly",
                    subject_id=baseline_id,
                    reason_code="NON_TARGET_FACT_CHANGED",
                    expected=before.value,
                    actual=after.value,
                    facts=[before, after],
                )
    return _check(
        "non_target",
        "non-target-comparison",
        "passed",
        "No unexpected entity or declared non-target fact change was found",
        facts=evidence,
    )


def _data_retention_validation(
    change: ChangeRequest,
    before_facts: FactSet,
    after_facts: FactSet,
    entity_map: dict[str, str],
) -> list[VerificationCheck]:
    if change.comparison.data_retention_not_applicable:
        return [
            _check(
                "data_retention",
                "data-retention",
                "not_applicable",
                "The request explicitly declares source data-retention checks not applicable",
                reason_code="EXPLICITLY_NOT_APPLICABLE",
            )
        ]
    if not change.data_retention_checks:
        return [
            _check(
                "data_retention",
                "data-retention",
                "incomplete",
                "No explicit data-retention checks or not-applicable decision were provided",
                reason_code="DATA_RETENTION_UNDECIDED",
            )
        ]
    results: list[VerificationCheck] = []
    for check in change.data_retention_checks:
        if check.expectation == "preserved":
            result = _invariant_check(
                InvariantCheck(
                    check_id=check.check_id,
                    subject_id=check.subject_id,
                    predicate=check.predicate,
                    unit=check.unit,
                    tolerance=check.tolerance,
                ),
                before_facts,
                after_facts,
                entity_map,
            )
            results.append(
                result.model_copy(
                    update={
                        "group": "data_retention",
                        "message": "Explicit data-retention constraint evaluated",
                        "reason_code": (
                            "DATA_RETENTION_CHANGED"
                            if result.status == "failed"
                            else result.reason_code
                        ),
                    }
                )
            )
            continue
        candidate_id = entity_map.get(check.subject_id)
        before, _, before_reason = _fact_for(
            before_facts, check.subject_id, check.predicate
        )
        after, gap, after_reason = _fact_for(after_facts, candidate_id, check.predicate) if candidate_id else (None, None, "DATA_ENTITY_UNRESOLVED")
        if before is None or candidate_id is None:
            results.append(
                _check(
                    "data_retention",
                    check.check_id,
                    "incomplete",
                    "The baseline data or matched candidate is unavailable",
                    subject_id=check.subject_id,
                    reason_code=before_reason or after_reason,
                )
            )
        elif after is not None:
            results.append(
                _check(
                    "data_retention",
                    check.check_id,
                    "failed",
                    "Data declared explicitly invalidated is still present",
                    subject_id=check.subject_id,
                    reason_code="DATA_NOT_INVALIDATED",
                    facts=[before, after],
                )
            )
        elif gap is not None and gap.reason_code == "ABSENT":
            results.append(
                _check(
                    "data_retention",
                    check.check_id,
                    "passed",
                    "Data invalidation is supported by a proven ABSENT gap",
                    subject_id=check.subject_id,
                    facts=[before],
                    gaps=[gap],
                )
            )
        else:
            results.append(
                _check(
                    "data_retention",
                    check.check_id,
                    "incomplete",
                    "Data invalidation requires a proven ABSENT gap, not an unknown value",
                    subject_id=check.subject_id,
                    reason_code=after_reason,
                    gaps=[gap] if gap else None,
                )
            )
    return results


def _manifest_validation(request: VerificationRequest):
    before = request.before_manifest
    after = request.after_manifest
    if before is None and after is None:
        if request.change.base_source_manifest_sha256 is None:
            return [], [], "not_applicable"
        return [
            _check(
                "manifest",
                "required-manifests",
                "incomplete",
                "The request declares a source-backed base but its manifests were not provided",
                reason_code="REQUIRED_MANIFESTS_MISSING",
            )
        ], [], "incomplete"
    if before is None or after is None:
        return [
            _check(
                "manifest",
                "before-after-manifests",
                "incomplete",
                "Source-backed verification requires both before and after manifests",
                reason_code="MANIFEST_PAIR_INCOMPLETE",
            )
        ], [], "incomplete"
    checks: list[VerificationCheck] = []
    diagnostics = []
    for label, manifest, directory, artifact in (
        (
            "before",
            before,
            request.before_manifest_directory,
            request.before_artifact,
        ),
        (
            "after",
            after,
            request.after_manifest_directory,
            request.after_artifact,
        ),
    ):
        if directory is None:
            checks.append(
                _check(
                    "manifest",
                    f"{label}-files",
                    "incomplete",
                    f"The {label} manifest workspace was not provided for byte validation",
                    reason_code="MANIFEST_WORKSPACE_MISSING",
                )
            )
        else:
            file_diagnostics = validate_manifest_files(manifest, Path(directory))
            diagnostics.extend(file_diagnostics)
            checks.append(
                _check(
                    "manifest",
                    f"{label}-files",
                    "failed" if file_diagnostics else "passed",
                    f"The {label} manifest files were checked against actual bytes",
                    reason_code="MANIFEST_FILE_MISMATCH" if file_diagnostics else None,
                )
            )
        artifact_known = any(
            item.sha256 == artifact.sha256 for item in manifest.generated_artifacts
        )
        checks.append(
            _check(
                "manifest",
                f"{label}-artifact-binding",
                "passed" if artifact_known else "failed",
                f"The {label} artifact is bound to its source manifest",
                reason_code=None if artifact_known else "MANIFEST_ARTIFACT_MISMATCH",
                expected=artifact.sha256,
            )
        )
    lineage_valid = (
        after.lineage_kind == "derived"
        and after.parent_manifest_sha256 == before.manifest_sha256
    )
    before_by_path = {item.path: item for item in before.sources}
    after_by_path = {item.path: item for item in after.sources}
    declared_modifications = {
        (item.old_path, item.new_path) for item in after.modified_from
    }
    actual_modifications = {
        (path, path)
        for path in before_by_path.keys() & after_by_path.keys()
        if before_by_path[path].sha256 != after_by_path[path].sha256
    }
    modifications_valid = (
        all(
            item.old_path in before_by_path and item.new_path in after_by_path
            for item in after.modified_from
        )
        and declared_modifications == actual_modifications
    )
    plan_sources_valid = True
    if request.plan is not None:
        operations = request.plan.operations
        declared_additions = {
            item.source_path for item in operations if item.kind == "add_source"
        }
        declared_removals = {
            item.source_path for item in operations if item.kind == "remove_source"
        }
        declared_changes = {
            item.source_path for item in operations if item.kind == "set_parameter"
        }
        plan_sources_valid = (
            after_by_path.keys() - before_by_path.keys() == declared_additions
            and before_by_path.keys() - after_by_path.keys() == declared_removals
            and {old_path for old_path, _ in actual_modifications} <= declared_changes
        )
    lineage_valid = lineage_valid and modifications_valid and plan_sources_valid
    base_bound = request.change.base_source_manifest_sha256 == before.manifest_sha256
    checks.append(
        _check(
            "manifest",
            "source-lineage",
            "passed" if lineage_valid and base_bound else "failed",
            "Derived source lineage, plan source changes and request base binding were checked",
            reason_code=(
                None if lineage_valid and base_bound else "MANIFEST_LINEAGE_MISMATCH"
            ),
        )
    )
    statuses = [check.status for check in checks]
    status = (
        "failed"
        if "failed" in statuses
        else "incomplete"
        if "incomplete" in statuses
        else "passed"
    )
    return checks, diagnostics, status


def _approval_and_execution_validation(
    request: VerificationRequest, manifest_status: str
):
    plan = request.plan
    approval = request.approval
    execution = request.execution
    checks: list[VerificationCheck] = []
    if plan is None:
        if approval is not None or execution is not None:
            checks.append(
                _check(
                    "approval",
                    "plan-present",
                    "failed",
                    "Approval or execution records were provided without a ChangePlan",
                    reason_code="PLAN_MISSING",
                )
            )
            return checks, "failed", "contradicted" if execution else "unattested"
        return checks, "not_provided", "unattested"

    rebound_plan = bind_change_plan(plan)
    target_bindings_valid = {
        item.target_entity_id for item in plan.target_bindings
    } == set(request.change.target_entity_ids)
    plan_valid = (
        rebound_plan.plan_id == plan.plan_id
        and rebound_plan.payload_sha256 == plan.payload_sha256
        and plan.request_id == request.change.request_id
        and target_bindings_valid
        and not (
            plan.baseline_manifest_validation == "passed"
            and manifest_status != "passed"
        )
    )
    if request.before_manifest is not None:
        plan_valid = plan_valid and plan.executor == request.before_manifest.generator
    if request.after_manifest is not None:
        plan_valid = plan_valid and plan.executor == request.after_manifest.generator
    if not plan_valid:
        checks.append(
            _check(
                "approval",
                "plan-binding",
                "failed",
                "The ChangePlan does not match its content, request, targets or executor",
                reason_code="PLAN_BINDING_MISMATCH",
            )
        )
    if approval is None:
        if execution is not None:
            checks.append(
                _check(
                    "execution",
                    "approval-present",
                    "failed",
                    "An ExecutionRecord cannot attest an approved run without its ApprovalRecord",
                    reason_code="APPROVAL_MISSING",
                )
            )
            return checks, "failed", "contradicted"
        return checks, "failed" if not plan_valid else "not_provided", "unattested"

    rebound_approval = bind_approval_record(approval)
    approval_valid = (
        plan_valid
        and rebound_approval.approval_id == approval.approval_id
        and approval.decision == "approved"
        and approval.request_id == request.change.request_id
        and approval.plan_id == plan.plan_id
        and approval.base_artifact_sha256 == request.change.base_artifact_sha256
        and approval.base_source_manifest_sha256
        == request.change.base_source_manifest_sha256
        and approval.executor == plan.executor
        and approval.payload_sha256 == plan.payload_sha256
    )
    checks.append(
        _check(
            "approval",
            "complete-request-plan-binding",
            "passed" if approval_valid else "failed",
            "ApprovalRecord binding to the complete request and plan was checked",
            reason_code=None if approval_valid else "APPROVAL_BINDING_MISMATCH",
        )
    )
    if execution is None:
        return checks, "passed" if approval_valid else "failed", "unattested"

    rebound_execution = bind_execution_record(execution)
    execution_valid = (
        approval_valid
        and rebound_execution.execution_id == execution.execution_id
        and execution.result == "succeeded"
        and execution.approval_id == approval.approval_id
        and execution.request_id == request.change.request_id
        and execution.plan_id == plan.plan_id
        and execution.executor == plan.executor
        and execution.base_artifact_sha256 == request.change.base_artifact_sha256
        and execution.payload_sha256 == plan.payload_sha256
        and execution.new_artifact_sha256 == request.after_artifact.sha256
    )
    if request.before_manifest is not None:
        execution_valid = execution_valid and sorted(
            execution.input_sources, key=lambda item: item.path
        ) == request.before_manifest.sources
    if request.after_manifest is not None:
        execution_valid = (
            execution_valid
            and sorted(execution.new_sources, key=lambda item: item.path)
            == request.after_manifest.sources
            and execution.new_source_manifest_sha256
            == request.after_manifest.manifest_sha256
        )
    checks.append(
        _check(
            "execution",
            "approved-execution-output-binding",
            "passed" if execution_valid else "failed",
            "ExecutionRecord and actual output binding were checked",
            reason_code=None if execution_valid else "EXECUTION_BINDING_MISMATCH",
        )
    )
    return (
        checks,
        "passed" if approval_valid else "failed",
        "attested" if execution_valid else "contradicted",
    )


def _original_rule_validation(
    request: VerificationRequest, entity_map: dict[str, str]
) -> tuple[list[VerificationCheck], ReviewReport | None, list]:
    if request.change.origin_kind == "user_intended":
        return [], None, []
    origin = request.change.origin_review
    assert origin is not None
    if request.origin_review is None:
        return [
            _check(
                "original_rule",
                "origin-review-available",
                "incomplete",
                "The original ReviewReport was not provided",
                reason_code="ORIGIN_REVIEW_MISSING",
            )
        ], None, []
    origin_valid = (
        request.origin_review.report_id == origin.origin_report_id
        and request.origin_review.review_run_id == origin.review_run_id
        and request.origin_review.report_id
        == structured_hash(
            "review-report", request.origin_review, exclude={"report_id"}
        )
        and request.origin_review.snapshot_id == request.change.base_snapshot_id
        and request.origin_review.snapshot_content_hash
        == request.before_snapshot.snapshot_content_hash
        and request.origin_review.factset_id == request.change.base_factset_id
        and request.origin_review.ruleset_id == origin.ruleset.ruleset_id
        and request.origin_review.scope_id == origin.scope.scope_id
        and request.origin_review.context_id == origin.context.context_id
    )
    origin_finding = next(
        (
            finding
            for finding in request.origin_review.findings
            if finding.finding_id == origin.finding_id
        ),
        None,
    )
    if origin_finding is not None:
        origin_valid = origin_valid and origin_finding.finding_id == structured_hash(
            "finding",
            {
                "review_run_id": origin.review_run_id,
                "rule_id": origin_finding.rule_id,
                "rule_version": origin_finding.rule_version,
                "subject": origin_finding.subject,
            },
        )
    origin_valid = origin_valid and origin_finding is not None and origin_finding.status in {
        "violated",
        "unknown",
    }
    checks = [
        _check(
            "original_rule",
            "origin-review-binding",
            "passed" if origin_valid else "failed",
            "The original report content IDs and baseline references were checked",
            reason_code=None if origin_valid else "ORIGIN_REVIEW_MISMATCH",
        )
    ]
    after_review = review(
        ReviewRequest(
            snapshot=request.after_snapshot,
            factset=request.after_factset,
            ruleset=origin.ruleset,
            scope=origin.scope,
            context=origin.context,
            reviewer_version=origin.reviewer_version,
        )
    )
    candidate_id = (
        entity_map.get(origin_finding.subject.entity_id) if origin_finding else None
    )
    resolved_finding = next(
        (
            finding
            for finding in after_review.findings
            if origin_finding is not None
            and finding.rule_id == origin_finding.rule_id
            and finding.rule_version == origin_finding.rule_version
            and finding.subject.entity_id == candidate_id
        ),
        None,
    )
    resolution_status = (
        "incomplete"
        if resolved_finding is None
        else "passed"
        if resolved_finding.status == "satisfied"
        else "failed"
        if resolved_finding.status == "violated"
        else "incomplete"
    )
    checks.append(
        _check(
            "original_rule",
            "origin-finding-resolution",
            resolution_status,
            "The originating finding was evaluated on the matched candidate entity",
            reason_code=(
                None
                if resolution_status == "passed"
                else "ORIGIN_FINDING_NOT_RESOLVED"
            ),
            actual=resolved_finding.status if resolved_finding else None,
        )
    )
    review_status = (
        "failed"
        if after_review.overall_status == "non_compliant"
        else "passed"
        if after_review.overall_status == "compliant_for_scope"
        and after_review.complete
        and not after_review.tool_error
        else "incomplete"
    )
    checks.append(
        _check(
            "original_rule",
            "original-rule-review",
            review_status,
            "The complete original RuleSet, scope and context were re-evaluated",
            reason_code=(
                None
                if review_status == "passed"
                else "ORIGINAL_RULE_REVIEW_NON_COMPLIANT"
                if review_status == "failed"
                else "ORIGINAL_RULE_REVIEW_INCOMPLETE"
            ),
            actual=after_review.overall_status,
        )
    )
    return checks, after_review, after_review.diagnostics


def _missing_after_report(request: VerificationRequest) -> ModificationReport:
    change = verify_change_request_identity(request.change)
    before_snapshot = verify_snapshot_identity(request.before_snapshot)
    before_facts = verify_factset_identity(request.before_factset)
    request = request.model_copy(
        update={"before_snapshot": before_snapshot, "before_factset": before_facts}
    )
    checks: list[VerificationCheck] = []
    base_valid = (
        request.before_artifact.sha256 == change.base_artifact_sha256
        and before_snapshot.artifact_sha256 == request.before_artifact.sha256
        and before_snapshot.snapshot_id == change.base_snapshot_id
        and before_facts.factset_id
        == (change.verification_base_factset_id or change.base_factset_id)
    )
    if not base_valid:
        checks.append(
            _check(
                "input_identity",
                "base-identity",
                "failed",
                "The baseline does not match the ChangeRequest",
                reason_code="STALE_OR_MISMATCHED_INPUT",
            )
        )
    checks.extend(_precondition_validation(change, before_facts))
    kinds = {entity.entity_id: entity.entity_kind for entity in before_snapshot.entities}
    matches = [
        EntityMatchResult(
            baseline_entity_id=entity_id,
            entity_kind=kinds.get(entity_id, "unknown"),
            status="unresolved",
            reason_code="AFTER_ARTIFACT_MISSING",
            message=f"{entity_id}: no candidate artifact was available",
        )
        for entity_id in change.comparison.required_baseline_entity_ids
    ]
    checks.append(
        _check(
            "matching",
            "required-entities",
            "incomplete",
            "Required entities cannot be matched without the new artifact",
            reason_code="AFTER_ARTIFACT_MISSING",
        )
    )
    for group, pending in (
        ("target", change.target_checks),
        ("invariant", change.invariant_checks),
        ("data_retention", change.data_retention_checks),
    ):
        checks.extend(
            _check(
                group,
                item.check_id,
                "incomplete",
                "The check requires the missing after artifact",
                subject_id=item.subject_id,
                reason_code="AFTER_ARTIFACT_MISSING",
            )
            for item in pending
        )
    checks.append(
        _check(
            "non_target",
            "non-target-comparison",
            "incomplete",
            "Non-target comparison requires the missing after artifact",
            reason_code="AFTER_ARTIFACT_MISSING",
        )
    )
    if change.comparison.data_retention_not_applicable:
        checks.append(
            _check(
                "data_retention",
                "data-retention",
                "not_applicable",
                "The request explicitly declares data-retention checks not applicable",
                reason_code="EXPLICITLY_NOT_APPLICABLE",
            )
        )
    elif not change.data_retention_checks:
        checks.append(
            _check(
                "data_retention",
                "data-retention",
                "incomplete",
                "No explicit data-retention decision was provided",
                reason_code="DATA_RETENTION_UNDECIDED",
            )
        )
    if change.origin_kind == "review_derived":
        checks.append(
            _check(
                "original_rule",
                "original-rule-re-review",
                "incomplete",
                "Original-rule re-review requires the missing after artifact",
                reason_code="AFTER_ARTIFACT_MISSING",
            )
        )
    if (
        change.base_source_manifest_sha256 is not None
        or request.before_manifest is not None
        or request.after_manifest is not None
    ):
        manifest_status = "incomplete"
        checks.append(
            _check(
                "manifest",
                "output-manifest-validation",
                "incomplete",
                "Source-backed output validation requires the missing after artifact",
                reason_code="AFTER_ARTIFACT_MISSING",
            )
        )
    else:
        manifest_status = "not_applicable"
    provenance_checks, approval_status, _ = _approval_and_execution_validation(
        request.model_copy(update={"execution": None}), manifest_status
    )
    checks.extend(provenance_checks)
    if request.execution is not None:
        checks.append(
            _check(
                "execution",
                "execution-output",
                "incomplete",
                "The ExecutionRecord cannot be matched to the missing output artifact",
                reason_code="AFTER_ARTIFACT_MISSING",
            )
        )
        execution_provenance = "contradicted"
    else:
        execution_provenance = "unattested"
    statuses = [check.status for check in checks]
    verification_status = "failed" if "failed" in statuses else "incomplete"
    origin_state = "not_applicable" if change.origin_kind == "user_intended" else "missing"
    report = ModificationReport(
        report_id="0" * 64,
        request_id=change.request_id,
        plan_id=request.plan.plan_id if request.plan else None,
        verification_profile_id=change.verification_profile.profile_id,
        after_artifact=ConditionalRef(
            state="missing", reason_code="AFTER_ARTIFACT_MISSING"
        ),
        after_snapshot=ConditionalRef(
            state="missing", reason_code="AFTER_ARTIFACT_MISSING"
        ),
        after_factset=ConditionalRef(
            state="missing", reason_code="AFTER_ARTIFACT_MISSING"
        ),
        before_manifest=ConditionalRef(
            state="present" if request.before_manifest else "not_provided",
            ref=request.before_manifest.manifest_sha256 if request.before_manifest else None,
        ),
        after_manifest=ConditionalRef(
            state="present" if request.after_manifest else "not_provided",
            ref=request.after_manifest.manifest_sha256 if request.after_manifest else None,
        ),
        origin_review=ConditionalRef(
            state="present" if request.origin_review else origin_state,
            ref=request.origin_review.review_run_id if request.origin_review else None,
        ),
        after_review=ConditionalRef(
            state="not_applicable"
            if change.origin_kind == "user_intended"
            else "missing",
            reason_code=(
                None
                if change.origin_kind == "user_intended"
                else "AFTER_ARTIFACT_MISSING"
            ),
        ),
        manifest_validation=manifest_status,
        approval_validation=approval_status,
        verification_status=verification_status,
        execution_provenance=execution_provenance,
        change_observed="unknown",
        checks=checks,
        entity_matches=matches,
        diagnostics=[*before_snapshot.diagnostics, *before_facts.diagnostics],
        unresolved_issues=[
            f"{check.group}:{check.check_id}:{check.reason_code or check.status}"
            for check in checks
            if check.status in {"failed", "incomplete"}
        ],
    )
    return bind_modification_report(report)


def _output_location_matches(
    declared_raw: str, actual_raw: str, allow_relocated: bool
) -> tuple[bool, bool]:
    """Compare output locations without assuming the recording platform.

    A recorded Windows absolute path is still absolute when replayed on POSIX.
    Explicit relocated-output replay may accept a different directory only when
    the recorded filename matches the actual filename.
    """

    declared = Path(declared_raw)
    declared_windows = PureWindowsPath(declared_raw)
    actual = Path(actual_raw).resolve()
    if declared.is_absolute() or declared_windows.is_absolute():
        matches = (
            declared.is_absolute()
            and str(declared.resolve()).casefold() == str(actual).casefold()
        )
        relocated = False
        if not matches and allow_relocated:
            relocated = declared_windows.name.casefold() == actual.name.casefold()
            matches = relocated
        return matches, relocated

    declared_parts = tuple(part.casefold() for part in declared.parts)
    matches = (
        bool(declared_parts)
        and "." not in declared_parts
        and ".." not in declared_parts
        and len(declared_parts) <= len(actual.parts)
        and tuple(part.casefold() for part in actual.parts[-len(declared_parts) :])
        == declared_parts
    )
    return matches, False


def _output_location_check(request: VerificationRequest) -> VerificationCheck:
    """Check the declared semantic output location without writing either artifact."""

    assert request.after_artifact is not None
    matches, relocated = _output_location_matches(
        request.change.output_policy.path,
        request.after_artifact.source_locator,
        request.allow_relocated_output,
    )
    message = (
        "The output filename was checked under explicit relocated-output replay; "
        "the recorded absolute directory was not revalidated"
        if relocated
        else "The actual new artifact location was checked against output_policy.path"
    )
    return _check(
        "input_identity",
        "output-location",
        "passed" if matches else "failed",
        message,
        reason_code=None if matches else "OUTPUT_LOCATION_MISMATCH",
        expected=request.change.output_policy.path,
        actual=request.after_artifact.source_locator,
    )


def _fixed_profile_check(request: VerificationRequest) -> VerificationCheck:
    profile = request.change.verification_profile
    mismatches: list[str] = []
    for role, snapshot, factset in (
        ("before", request.before_snapshot, request.before_factset),
        ("after", request.after_snapshot, request.after_factset),
    ):
        expected = (
            snapshot.adapter_id == profile.adapter_id,
            snapshot.adapter_version == profile.adapter_version,
            snapshot.parser_kernel_version == profile.parser_kernel_version,
            snapshot.parse_options == profile.parse_options,
            factset.extractor_version == profile.extractor_version,
        )
        if not all(expected):
            mismatches.append(role)
    return _check(
        "matching",
        "fixed-verification-profile",
        "passed" if not mismatches else "incomplete",
        "Snapshots and FactSets were checked against the fixed verification profile",
        reason_code=None if not mismatches else "VERIFICATION_PROFILE_MISMATCH",
        actual=mismatches,
    )


def verify_change(request: VerificationRequest) -> ModificationReport:
    """Verify output facts independently of approval or execution provenance."""

    change = verify_change_request_identity(request.change)
    if request.after_artifact is None:
        return _missing_after_report(request)
    assert request.after_snapshot is not None and request.after_factset is not None
    before_snapshot = verify_snapshot_identity(request.before_snapshot)
    after_snapshot = verify_snapshot_identity(request.after_snapshot)
    before_facts = verify_factset_identity(request.before_factset)
    after_facts = verify_factset_identity(request.after_factset)
    request = request.model_copy(
        update={
            "change": change,
            "before_snapshot": before_snapshot,
            "after_snapshot": after_snapshot,
            "before_factset": before_facts,
            "after_factset": after_facts,
        }
    )
    checks = _validate_input_identity(request)
    checks.append(_output_location_check(request))
    checks.extend(_precondition_validation(change, before_facts))
    required_predicates = {
        check.predicate
        for check in [
            *change.preconditions,
            *change.target_checks,
            *change.invariant_checks,
            *change.data_retention_checks,
        ]
    }
    template_predicates = {
        item.predicate for item in change.verification_profile.extraction_query_template.requests
    }
    if not required_predicates <= template_predicates:
        raise ConfigurationError(
            "Verification extraction template does not cover every target/invariant predicate"
        )

    profile_check = _fixed_profile_check(request)
    checks.append(profile_check)
    profile_valid = profile_check.status == "passed"

    matching_request = bind_matching_request(
        EntityMatchRequest(
            request_id="0" * 64,
            baseline=before_snapshot,
            candidate=after_snapshot,
            profile=change.verification_profile.matching,
            required_baseline_entity_ids=change.comparison.required_baseline_entity_ids,
            baseline_facts=before_facts,
            candidate_facts=after_facts,
        )
    )
    matching_report = match_entities(matching_request)
    if not profile_valid:
        matching_report = matching_report.model_copy(
            update={
                "status": "incomplete",
                "results": [
                    result.model_copy(
                        update={
                            "status": "unresolved",
                            "candidate_entity_ids": [],
                            "reason_code": "VERIFICATION_PROFILE_MISMATCH",
                            "message": (
                                f"{result.baseline_entity_id}: unresolved because the "
                                "fixed verification profile does not match"
                            ),
                        }
                    )
                    for result in matching_report.results
                ],
            }
        )
    entity_map = _mapping(matching_report.results)
    checks.append(
        _check(
            "matching",
            "required-entities",
            "passed" if matching_report.status == "complete" else "incomplete",
            "Required baseline entities matched"
            if matching_report.status == "complete"
            else "Required entity matching is incomplete",
            reason_code=None if matching_report.status == "complete" else "ENTITY_MATCH_INCOMPLETE",
        )
    )
    checks.extend(
        _target_check(check, after_facts, entity_map) for check in change.target_checks
    )
    checks.extend(
        _invariant_check(check, before_facts, after_facts, entity_map)
        for check in change.invariant_checks
    )
    checks.append(_non_target_check(request, entity_map, matching_report.results))
    if profile_valid:
        original_checks, after_review, review_diagnostics = _original_rule_validation(
            request, entity_map
        )
    elif change.origin_kind == "user_intended":
        original_checks, after_review, review_diagnostics = [], None, []
    else:
        original_checks = [
            _check(
                "original_rule",
                "original-rule-profile",
                "incomplete",
                "Original-rule re-review requires the fixed verification profile",
                reason_code="VERIFICATION_PROFILE_MISMATCH",
            )
        ]
        after_review, review_diagnostics = None, []
    checks.extend(original_checks)
    checks.extend(
        _data_retention_validation(change, before_facts, after_facts, entity_map)
    )

    manifest_checks, manifest_diagnostics, manifest_status = _manifest_validation(request)
    provenance_checks, approval_status, execution_provenance = (
        _approval_and_execution_validation(request, manifest_status)
    )
    checks.extend(manifest_checks)
    checks.extend(provenance_checks)

    observed = (
        "changed"
        if request.before_artifact.sha256 != request.after_artifact.sha256
        else "no_change"
    )
    statuses = [check.status for check in checks]
    verification_status = (
        "failed"
        if "failed" in statuses
        else "incomplete"
        if "incomplete" in statuses
        else "passed"
    )
    unresolved = [
        f"{check.group}:{check.check_id}:{check.reason_code or check.status}"
        for check in checks
        if check.status in {"failed", "incomplete"}
    ]
    origin_state = "not_applicable" if change.origin_kind == "user_intended" else "missing"
    after_review_state = (
        "not_applicable" if change.origin_kind == "user_intended" else "not_provided"
    )
    report = ModificationReport(
        report_id="0" * 64,
        request_id=change.request_id,
        plan_id=request.plan.plan_id if request.plan else None,
        verification_profile_id=change.verification_profile.profile_id,
        after_artifact=ConditionalRef(state="present", ref=request.after_artifact.sha256),
        after_snapshot=ConditionalRef(state="present", ref=after_snapshot.snapshot_content_hash),
        after_factset=ConditionalRef(state="present", ref=after_facts.factset_id),
        before_manifest=ConditionalRef(
            state="present" if request.before_manifest else "not_provided",
            ref=request.before_manifest.manifest_sha256 if request.before_manifest else None,
        ),
        after_manifest=ConditionalRef(
            state="present" if request.after_manifest else "not_provided",
            ref=request.after_manifest.manifest_sha256 if request.after_manifest else None,
        ),
        origin_review=ConditionalRef(
            state="present" if request.origin_review else origin_state,
            ref=request.origin_review.review_run_id if request.origin_review else None,
        ),
        after_review=ConditionalRef(
            state="present" if after_review else after_review_state,
            ref=after_review.report_id if after_review else None,
        ),
        manifest_validation=manifest_status,
        approval_validation=approval_status,
        verification_status=verification_status,
        execution_provenance=execution_provenance,
        change_observed=observed,
        checks=checks,
        entity_matches=matching_report.results,
        unmatched_candidate_entity_ids=matching_report.unmatched_candidate_entity_ids,
        diagnostics=[
            *matching_report.diagnostics,
            *manifest_diagnostics,
            *review_diagnostics,
        ],
        unresolved_issues=unresolved,
    )
    return bind_modification_report(report)
