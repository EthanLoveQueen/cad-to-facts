"""Prepare immutable change requests and external-executor plans without executing CAD."""

from pathlib import Path

from cad_to_facts.contract import (
    bind_change_plan,
    bind_change_preparation,
    bind_change_request,
    bind_verification_profile,
)
from cad_to_facts.domain.change import (
    ChangePlan,
    ChangePreparation,
    ChangePreparationSpec,
    ChangeRequest,
    OriginReview,
    SourceManifest,
    TargetBinding,
    ValueCheck,
    VerificationProfile,
)
from cad_to_facts.domain.facts import ExtractionQuery, FactRequest, FactSet
from cad_to_facts.domain.matching import NumericTolerance
from cad_to_facts.domain.review import (
    ReviewContext,
    ReviewReport,
    ReviewRequest,
    ReviewScope,
    RuleSet,
)
from cad_to_facts.domain.snapshot import ModelSnapshot
from cad_to_facts.errors import ConfigurationError
from cad_to_facts.facts import extract
from cad_to_facts.manifest import validate_manifest_files
from cad_to_facts.review import review, select_rules


def _target_from_finding(finding, ruleset: RuleSet, scope: ReviewScope) -> ValueCheck:
    rule = next(
        (
            item
            for item in select_rules(ruleset, scope)
            if item.rule_id == finding.rule_id and item.version == finding.rule_version
        ),
        None,
    )
    if rule is None or rule.checker != "numeric.compare":
        raise ConfigurationError(
            "prepare-change currently derives targets only from numeric.compare findings"
        )
    parameters = rule.parameters
    return ValueCheck(
        check_id=f"resolve:{finding.finding_id}",
        subject_id=finding.subject.entity_id,
        predicate=rule.inputs[0].predicate,
        operator=parameters["operator"],
        value=parameters["threshold"],
        unit=parameters["unit"],
        tolerance=NumericTolerance(absolute=parameters["abs_tol"]),
    )


def _extraction_template(
    ruleset: RuleSet,
    scope: ReviewScope,
    spec: ChangePreparationSpec,
    target: ValueCheck,
) -> ExtractionQuery:
    predicates = {target.predicate}
    for rule in select_rules(ruleset, scope):
        predicates.update(item.predicate for item in rule.inputs)
        applicability = rule.applicability.get("fact_predicate")
        if applicability:
            predicates.add(applicability)
    predicates.update(item.predicate for item in scope.required_inputs)
    for check in [
        *spec.preconditions,
        *spec.invariant_checks,
        *spec.data_retention_checks,
    ]:
        predicates.add(check.predicate)
    predicates.update(spec.comparison.non_target_predicates)
    predicates.update(spec.matching.fingerprint_predicates)
    return ExtractionQuery(
        requests=[
            FactRequest(subject_id="*", predicate=predicate, name=predicate)
            for predicate in sorted(predicates)
        ]
    )


def _validated_baseline_manifest(
    manifest: SourceManifest | None,
    directory: str | None,
    snapshot: ModelSnapshot,
    spec: ChangePreparationSpec,
) -> tuple[str | None, str]:
    if manifest is None:
        if spec.operations:
            raise ConfigurationError(
                "Source operations require a validated baseline SourceManifest"
            )
        return None, "not_applicable"
    if directory is None:
        raise ConfigurationError("A baseline manifest workspace is required")
    diagnostics = validate_manifest_files(manifest, Path(directory))
    if diagnostics:
        raise ConfigurationError(
            "Baseline SourceManifest validation failed: "
            + ", ".join(diagnostic.code for diagnostic in diagnostics)
        )
    if not any(
        item.sha256 == snapshot.artifact_sha256
        for item in manifest.generated_artifacts
    ):
        raise ConfigurationError("Baseline manifest does not contain the base artifact")
    if manifest.generator != spec.executor:
        raise ConfigurationError("Preparation executor does not match the baseline generator")
    known_sources = {item.path for item in manifest.sources}
    for operation in spec.operations:
        if operation.kind != "add_source" and operation.source_path not in known_sources:
            raise ConfigurationError(
                f"Operation references unknown baseline source: {operation.source_path}"
            )
    return manifest.manifest_sha256, "passed"


def prepare_change(
    *,
    snapshot: ModelSnapshot,
    origin_factset: FactSet,
    origin_report: ReviewReport,
    ruleset: RuleSet,
    scope: ReviewScope,
    context: ReviewContext,
    reviewer_version: str,
    finding_id: str,
    spec: ChangePreparationSpec,
    before_manifest: SourceManifest | None = None,
    before_manifest_directory: str | None = None,
) -> ChangePreparation:
    """Bind a review-derived request and external handoff plan, with no execution."""

    expected_origin = review(
        ReviewRequest(
            snapshot=snapshot,
            factset=origin_factset,
            ruleset=ruleset,
            scope=scope,
            context=context,
            reviewer_version=reviewer_version,
        )
    )
    if expected_origin.report_id != origin_report.report_id:
        raise ConfigurationError("The supplied origin report does not match its review inputs")
    finding = next(
        (item for item in origin_report.findings if item.finding_id == finding_id), None
    )
    if finding is None or finding.status not in {"violated", "unknown"}:
        raise ConfigurationError("prepare-change requires a violated or unknown origin finding")
    target = _target_from_finding(finding, ruleset, scope)
    known_entities = {entity.entity_id for entity in snapshot.entities}
    referenced_entities = {
        check.subject_id
        for check in [
            *spec.preconditions,
            *spec.invariant_checks,
            *spec.data_retention_checks,
        ]
    }
    if not referenced_entities <= known_entities:
        raise ConfigurationError("A preparation check references an unknown baseline entity")
    comparison = spec.comparison
    if not comparison.required_baseline_entity_ids:
        comparison = comparison.model_copy(
            update={
                "required_baseline_entity_ids": [
                    entity.entity_id
                    for entity in snapshot.entities
                    if entity.entity_id not in comparison.allowed_removed_baseline_entity_ids
                ]
            }
        )
    if finding.subject.entity_id not in comparison.required_baseline_entity_ids:
        raise ConfigurationError("The target entity must be required for before/after matching")
    base_manifest_hash, manifest_validation = _validated_baseline_manifest(
        before_manifest, before_manifest_directory, snapshot, spec
    )
    template = _extraction_template(ruleset, scope, spec, target)
    profile = bind_verification_profile(
        VerificationProfile(
            profile_id="0" * 64,
            adapter_id=snapshot.adapter_id,
            adapter_version=snapshot.adapter_version,
            parser_kernel_version=snapshot.parser_kernel_version,
            parse_options=snapshot.parse_options,
            extractor_version=origin_factset.extractor_version,
            extraction_query_template=template,
            matching=spec.matching,
        )
    )
    verification_base_factset = extract(
        snapshot,
        ExtractionQuery(
            requests=[
                item.model_copy(update={"subject_id": entity.entity_id})
                for entity in snapshot.entities
                for item in template.requests
            ]
        ),
    )
    origin = OriginReview(
        review_run_id=origin_report.review_run_id,
        finding_id=finding.finding_id,
        origin_report_id=origin_report.report_id,
        ruleset=ruleset,
        scope=scope,
        context=context,
        reviewer_version=reviewer_version,
    )
    change = bind_change_request(
        ChangeRequest(
            request_id="0" * 64,
            origin_kind="review_derived",
            origin_review=origin,
            base_artifact_sha256=snapshot.artifact_sha256,
            base_snapshot_id=snapshot.snapshot_id,
            base_factset_id=origin_factset.factset_id,
            verification_base_factset_id=verification_base_factset.factset_id,
            base_source_manifest_sha256=base_manifest_hash,
            verification_profile=profile,
            target_entity_ids=[finding.subject.entity_id],
            preconditions=spec.preconditions,
            target_checks=[target],
            invariant_checks=spec.invariant_checks,
            data_retention_checks=spec.data_retention_checks,
            comparison=comparison,
            output_policy=spec.output_policy,
        )
    )
    plan = bind_change_plan(
        ChangePlan(
            plan_id="0" * 64,
            request_id=change.request_id,
            executor=spec.executor,
            target_bindings=[
                TargetBinding(
                    target_entity_id=finding.subject.entity_id,
                    executor_ref=spec.target_executor_ref,
                )
            ],
            operations=spec.operations,
            expected_invalidated_refs=[finding.subject.entity_id],
            payload=spec.payload,
            payload_sha256="0" * 64,
            baseline_manifest_validation=manifest_validation,
        )
    )
    return bind_change_preparation(
        ChangePreparation(preparation_id="0" * 64, request=change, plan=plan)
    )
