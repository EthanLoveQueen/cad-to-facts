"""Canonical ordering and content-identity binding for review inputs.

Semantically unordered collections are normalized before hashing so that reordering
requirements, rules, scope references or extraction results does not change an identity.
"""

from cad_to_facts.domain.bom import BOMExtract
from cad_to_facts.domain.change import (
    ApprovalRecord,
    ChangePlan,
    ChangePreparation,
    ChangeRequest,
    ExecutionRecord,
    ModificationReport,
    SourceManifest,
    VerificationProfile,
)
from cad_to_facts.domain.facts import FactSet
from cad_to_facts.domain.pmi import PmiExtract
from cad_to_facts.domain.review import RequirementBundle, ReviewContext, ReviewScope, Rule, RuleSet
from cad_to_facts.domain.snapshot import ModelSnapshot
from cad_to_facts.errors import ConfigurationError
from cad_to_facts.identity import structured_hash


def canonicalize_requirement_bundle(bundle: RequirementBundle) -> RequirementBundle:
    requirements = sorted(bundle.requirements, key=lambda requirement: requirement.requirement_id)
    identifiers = [requirement.requirement_id for requirement in requirements]
    if len(set(identifiers)) != len(identifiers):
        raise ConfigurationError("RequirementBundle contains duplicate requirement_id values")
    return bundle.model_copy(update={"requirements": requirements})


def bind_requirement_bundle(bundle: RequirementBundle) -> RequirementBundle:
    bundle = canonicalize_requirement_bundle(bundle)
    requirements = [
        requirement.model_copy(
            update={
                "content_hash": structured_hash(
                    "requirement", requirement, exclude={"content_hash"}
                )
            }
        )
        for requirement in bundle.requirements
    ]
    bundle = bundle.model_copy(update={"requirements": requirements})
    return bundle.model_copy(
        update={
            "bundle_id": structured_hash(
                "requirement-bundle", bundle, exclude={"bundle_id"}
            )
        }
    )


def canonicalize_rule(rule: Rule) -> Rule:
    return rule.model_copy(update={"requirement_refs": sorted(set(rule.requirement_refs))})


def canonicalize_ruleset(ruleset: RuleSet) -> RuleSet:
    bundle = canonicalize_requirement_bundle(ruleset.requirement_bundle)
    rules = [canonicalize_rule(rule) for rule in ruleset.rules]
    rules.sort(key=lambda rule: (rule.rule_id, rule.version))
    keys = [(rule.rule_id, rule.version) for rule in rules]
    if len(set(keys)) != len(keys):
        raise ConfigurationError("RuleSet contains duplicate rule_id/version pairs")
    return ruleset.model_copy(update={"requirement_bundle": bundle, "rules": rules})


def bind_ruleset(ruleset: RuleSet) -> RuleSet:
    bundle = bind_requirement_bundle(ruleset.requirement_bundle)
    ruleset = canonicalize_ruleset(ruleset.model_copy(update={"requirement_bundle": bundle}))
    return ruleset.model_copy(
        update={"ruleset_id": structured_hash("ruleset", ruleset, exclude={"ruleset_id"})}
    )


def canonicalize_scope(scope: ReviewScope) -> ReviewScope:
    references = sorted(
        scope.included_rules, key=lambda reference: (reference.rule_id, reference.version or "")
    )
    reference_keys = [(reference.rule_id, reference.version) for reference in references]
    if len(set(reference_keys)) != len(reference_keys):
        raise ConfigurationError("ReviewScope contains duplicate included rule references")
    selectors = sorted(scope.subject_selectors, key=lambda selector: selector.entity_kind)
    selector_kinds = [selector.entity_kind for selector in selectors]
    if len(set(selector_kinds)) != len(selector_kinds):
        raise ConfigurationError("ReviewScope contains duplicate subject selectors")
    required_inputs = sorted(
        scope.required_inputs,
        key=lambda request: (request.subject_id, request.predicate, request.name),
    )
    input_keys = [
        (request.subject_id, request.predicate, request.name) for request in required_inputs
    ]
    if len(set(input_keys)) != len(input_keys):
        raise ConfigurationError("ReviewScope contains duplicate required inputs")
    discovery_requirements = sorted(scope.discovery_requirements)
    if len(set(discovery_requirements)) != len(discovery_requirements):
        raise ConfigurationError("ReviewScope contains duplicate discovery requirements")
    return scope.model_copy(
        update={
            "included_rules": references,
            "subject_selectors": selectors,
            "required_inputs": required_inputs,
            "discovery_requirements": discovery_requirements,
        }
    )


def bind_scope(scope: ReviewScope) -> ReviewScope:
    scope = canonicalize_scope(scope)
    return scope.model_copy(
        update={"scope_id": structured_hash("review-scope", scope, exclude={"scope_id"})}
    )


def canonicalize_context(context: ReviewContext) -> ReviewContext:
    return context


def bind_context(context: ReviewContext) -> ReviewContext:
    context = canonicalize_context(context)
    return context.model_copy(
        update={
            "context_id": structured_hash("review-context", context, exclude={"context_id"})
        }
    )


def canonicalize_factset(factset: FactSet) -> FactSet:
    facts = sorted(
        factset.facts,
        key=lambda fact: (fact.subject.entity_id, fact.predicate, fact.fact_id),
    )
    gaps = sorted(
        factset.gaps,
        key=lambda gap: (
            gap.subject.entity_id if gap.subject is not None else "",
            gap.request.predicate,
            gap.request.name,
            gap.reason_code,
        ),
    )
    requests = sorted(
        factset.extraction_query.requests,
        key=lambda request: (request.subject_id, request.predicate, request.name),
    )
    diagnostics = sorted(
        factset.diagnostics,
        key=lambda diagnostic: (diagnostic.code, diagnostic.message),
    )
    return factset.model_copy(
        update={
            "facts": facts,
            "gaps": gaps,
            "diagnostics": diagnostics,
            "extraction_query": factset.extraction_query.model_copy(
                update={"requests": requests}
            ),
        }
    )


def bind_factset(factset: FactSet) -> FactSet:
    facts = [
        fact.model_copy(
            update={"fact_id": structured_hash("fact", fact, exclude={"fact_id"})}
        )
        for fact in factset.facts
    ]
    factset = canonicalize_factset(factset.model_copy(update={"facts": facts}))
    return factset.model_copy(
        update={"factset_id": structured_hash("factset", factset, exclude={"factset_id"})}
    )


def canonicalize_snapshot(snapshot: ModelSnapshot) -> ModelSnapshot:
    return snapshot


def canonicalize_bom_extract(bom: BOMExtract) -> BOMExtract:
    options = bom.options.model_copy(
        update={"required_properties": sorted(set(bom.options.required_properties))}
    )
    line_items = sorted(bom.line_items, key=lambda item: item.part_definition_id)
    line_items = [
        item.model_copy(
            update={
                "occurrence_refs": sorted(item.occurrence_refs),
                "counted_occurrence_refs": sorted(item.counted_occurrence_refs),
            }
        )
        for item in line_items
    ]
    links = sorted(
        bom.assembly_links,
        key=lambda link: (link.parent_occurrence_id, link.child_occurrence_id),
    )
    definitions = sorted(bom.definitions, key=lambda item: item.definition_id)
    occurrences = sorted(bom.occurrences, key=lambda item: item.occurrence_id)
    missing = sorted(
        bom.missing_inputs,
        key=lambda item: (item.subject_id, item.field, item.reason_code),
    )
    diagnostics = sorted(
        bom.diagnostics, key=lambda diagnostic: (diagnostic.code, diagnostic.message)
    )
    return bom.model_copy(
        update={
            "options": options,
            "line_items": line_items,
            "definitions": definitions,
            "occurrences": occurrences,
            "assembly_links": links,
            "missing_inputs": missing,
            "diagnostics": diagnostics,
        }
    )


def bind_bom_extract(bom: BOMExtract) -> BOMExtract:
    bom = canonicalize_bom_extract(bom)
    return bom.model_copy(
        update={"bom_id": structured_hash("bom-extract", bom, exclude={"bom_id"})}
    )


def verify_bom_identity(bom: BOMExtract) -> BOMExtract:
    canonical = canonicalize_bom_extract(bom)
    if bom.bom_id != structured_hash("bom-extract", canonical, exclude={"bom_id"}):
        raise ConfigurationError("bom_id does not match the BOMExtract content")
    return canonical.model_copy(update={"bom_id": bom.bom_id})


def canonicalize_pmi_extract(extract: PmiExtract) -> PmiExtract:
    annotations = sorted(
        extract.annotations,
        key=lambda item: (item.kind, item.native_ref, item.annotation_type),
    )
    gaps = sorted(
        extract.gaps,
        key=lambda item: (
            item.kind or "",
            item.native_ref,
            item.reason_code,
            item.annotation_type or "",
        ),
    )
    diagnostics = sorted(
        extract.diagnostics,
        key=lambda diagnostic: (diagnostic.code, diagnostic.message),
    )
    unit_contexts = sorted(
        extract.unit_contexts,
        key=lambda item: (
            item.length or "",
            item.angle or "",
            item.dimension_representation_count,
        ),
    )
    return extract.model_copy(
        update={
            "annotations": annotations,
            "gaps": gaps,
            "diagnostics": diagnostics,
            "unit_contexts": unit_contexts,
        }
    )


def bind_pmi_extract(extract: PmiExtract) -> PmiExtract:
    annotations = [
        annotation.model_copy(
            update={
                "annotation_id": structured_hash(
                    "pmi-annotation", annotation, exclude={"annotation_id"}
                )
            }
        )
        for annotation in extract.annotations
    ]
    extract = canonicalize_pmi_extract(extract.model_copy(update={"annotations": annotations}))
    return extract.model_copy(
        update={"pmi_id": structured_hash("pmi-extract", extract, exclude={"pmi_id"})}
    )


def verify_pmi_identity(extract: PmiExtract) -> PmiExtract:
    extract = canonicalize_pmi_extract(extract)
    for annotation in extract.annotations:
        expected = structured_hash(
            "pmi-annotation", annotation, exclude={"annotation_id"}
        )
        if annotation.annotation_id != expected:
            raise ConfigurationError(
                f"PMI annotation {annotation.annotation_id} does not match its content"
            )
    if extract.pmi_id != structured_hash("pmi-extract", extract, exclude={"pmi_id"}):
        raise ConfigurationError("PmiExtract pmi_id does not match its canonical content")
    return extract


def verify_snapshot_identity(snapshot: ModelSnapshot) -> ModelSnapshot:
    snapshot = canonicalize_snapshot(snapshot)
    if snapshot.snapshot_content_hash != structured_hash(
        "model-snapshot", snapshot, exclude={"snapshot_content_hash"}
    ):
        raise ConfigurationError("snapshot_content_hash does not match the snapshot content")
    return snapshot


def bind_snapshot(snapshot: ModelSnapshot) -> ModelSnapshot:
    snapshot = canonicalize_snapshot(snapshot)
    return snapshot.model_copy(
        update={
            "snapshot_content_hash": structured_hash(
                "model-snapshot", snapshot, exclude={"snapshot_content_hash"}
            )
        }
    )


def verify_factset_identity(factset: FactSet) -> FactSet:
    factset = canonicalize_factset(factset)
    for fact in factset.facts:
        expected = structured_hash("fact", fact, exclude={"fact_id"})
        if fact.fact_id != expected:
            raise ConfigurationError(f"Fact {fact.fact_id} does not match its content")
    if factset.factset_id != structured_hash(
        "factset", factset, exclude={"factset_id"}
    ):
        raise ConfigurationError("FactSet factset_id does not match its canonical content")
    return factset


def _reject_duplicate_paths(paths: list[str], label: str) -> None:
    if len(set(paths)) != len(paths):
        raise ConfigurationError(f"SourceManifest contains duplicate {label} paths")


def canonicalize_source_manifest(manifest: SourceManifest) -> SourceManifest:
    sources = sorted(manifest.sources, key=lambda item: item.path)
    dependencies = sorted(manifest.dependency_files, key=lambda item: item.path)
    artifacts = sorted(manifest.generated_artifacts, key=lambda item: item.path)
    modifications = sorted(
        manifest.modified_from, key=lambda item: (item.old_path, item.new_path)
    )
    _reject_duplicate_paths([item.path for item in sources], "source")
    _reject_duplicate_paths([item.path for item in dependencies], "dependency")
    _reject_duplicate_paths([item.path for item in artifacts], "generated artifact")
    modification_keys = [(item.old_path, item.new_path) for item in modifications]
    if len(set(modification_keys)) != len(modification_keys):
        raise ConfigurationError("SourceManifest contains duplicate modified_from entries")
    artifacts = [
        item.model_copy(update={"source_paths": sorted(set(item.source_paths))})
        for item in artifacts
    ]
    return manifest.model_copy(
        update={
            "sources": sources,
            "dependency_files": dependencies,
            "generated_artifacts": artifacts,
            "modified_from": modifications,
        }
    )


def bind_source_manifest(manifest: SourceManifest) -> SourceManifest:
    manifest = canonicalize_source_manifest(manifest)
    return manifest.model_copy(
        update={
            "manifest_sha256": structured_hash(
                "source-manifest", manifest, exclude={"manifest_sha256"}
            )
        }
    )


def verify_source_manifest_identity(manifest: SourceManifest) -> SourceManifest:
    canonical = canonicalize_source_manifest(manifest)
    if manifest.manifest_sha256 != structured_hash(
        "source-manifest", canonical, exclude={"manifest_sha256"}
    ):
        raise ConfigurationError("manifest_sha256 does not match the manifest content")
    return canonical


def canonicalize_verification_profile(profile: VerificationProfile) -> VerificationProfile:
    requests = sorted(
        profile.extraction_query_template.requests,
        key=lambda request: (request.predicate, request.name),
    )
    if any(request.subject_id != "*" for request in requests):
        raise ConfigurationError("Verification extraction templates must use subject_id='*'")
    predicates = [request.predicate for request in requests]
    if len(set(predicates)) != len(predicates):
        raise ConfigurationError("Verification extraction templates contain duplicate predicates")
    matching = profile.matching.model_copy(
        update={
            "fingerprint_predicates": sorted(profile.matching.fingerprint_predicates),
            "profile_id": structured_hash(
                "entity-matching-profile",
                profile.matching.model_copy(
                    update={
                        "fingerprint_predicates": sorted(
                            profile.matching.fingerprint_predicates
                        )
                    }
                ),
                exclude={"profile_id"},
            ),
        }
    )
    return profile.model_copy(
        update={
            "extraction_query_template": profile.extraction_query_template.model_copy(
                update={"requests": requests}
            ),
            "matching": matching,
        }
    )


def bind_verification_profile(profile: VerificationProfile) -> VerificationProfile:
    profile = canonicalize_verification_profile(profile)
    return profile.model_copy(
        update={
            "profile_id": structured_hash(
                "verification-profile", profile, exclude={"profile_id"}
            )
        }
    )


def canonicalize_change_request(request: ChangeRequest) -> ChangeRequest:
    target_entity_ids = sorted(set(request.target_entity_ids))
    target_checks = sorted(request.target_checks, key=lambda check: check.check_id)
    invariant_checks = sorted(request.invariant_checks, key=lambda check: check.check_id)
    data_retention_checks = sorted(
        request.data_retention_checks, key=lambda check: check.check_id
    )
    preconditions = sorted(request.preconditions, key=lambda check: check.check_id)
    check_ids = [
        check.check_id
        for check in [
            *preconditions,
            *target_checks,
            *invariant_checks,
            *data_retention_checks,
        ]
    ]
    if len(set(check_ids)) != len(check_ids):
        raise ConfigurationError("ChangeRequest contains duplicate check IDs")
    comparison = request.comparison.model_copy(
        update={
            "required_baseline_entity_ids": sorted(
                set(request.comparison.required_baseline_entity_ids)
            ),
            "allowed_added_entity_ids": sorted(
                set(request.comparison.allowed_added_entity_ids)
            ),
            "allowed_removed_baseline_entity_ids": sorted(
                set(request.comparison.allowed_removed_baseline_entity_ids)
            ),
            "non_target_predicates": sorted(set(request.comparison.non_target_predicates)),
        }
    )
    origin = request.origin_review
    if origin is not None:
        origin = origin.model_copy(
            update={
                "ruleset": bind_ruleset(origin.ruleset),
                "scope": bind_scope(origin.scope),
                "context": bind_context(origin.context),
            }
        )
    return request.model_copy(
        update={
            "origin_review": origin,
            "verification_profile": bind_verification_profile(
                request.verification_profile
            ),
            "target_entity_ids": target_entity_ids,
            "preconditions": preconditions,
            "target_checks": target_checks,
            "invariant_checks": invariant_checks,
            "data_retention_checks": data_retention_checks,
            "comparison": comparison,
        }
    )


def bind_change_request(request: ChangeRequest) -> ChangeRequest:
    request = canonicalize_change_request(request)
    return request.model_copy(
        update={
            "request_id": structured_hash(
                "change-request", request, exclude={"request_id"}
            )
        }
    )


def verify_change_request_identity(request: ChangeRequest) -> ChangeRequest:
    canonical = canonicalize_change_request(request)
    expected = structured_hash("change-request", canonical, exclude={"request_id"})
    if request.request_id != expected:
        raise ConfigurationError("request_id does not match the change request content")
    return canonical.model_copy(update={"request_id": request.request_id})


def canonicalize_change_plan(plan: ChangePlan) -> ChangePlan:
    bindings = sorted(plan.target_bindings, key=lambda item: item.target_entity_id)
    operations = sorted(plan.operations, key=lambda item: item.operation_id)
    binding_ids = [item.target_entity_id for item in bindings]
    operation_ids = [item.operation_id for item in operations]
    if len(set(binding_ids)) != len(binding_ids):
        raise ConfigurationError("ChangePlan contains duplicate target bindings")
    if len(set(operation_ids)) != len(operation_ids):
        raise ConfigurationError("ChangePlan contains duplicate operation IDs")
    return plan.model_copy(
        update={
            "target_bindings": bindings,
            "operations": operations,
            "expected_invalidated_refs": sorted(set(plan.expected_invalidated_refs)),
            "payload_sha256": structured_hash("change-plan-payload", plan.payload),
        }
    )


def bind_change_plan(plan: ChangePlan) -> ChangePlan:
    plan = canonicalize_change_plan(plan)
    return plan.model_copy(
        update={"plan_id": structured_hash("change-plan", plan, exclude={"plan_id"})}
    )


def bind_change_preparation(preparation: ChangePreparation) -> ChangePreparation:
    return preparation.model_copy(
        update={
            "preparation_id": structured_hash(
                "change-preparation", preparation, exclude={"preparation_id"}
            )
        }
    )


def bind_approval_record(record: ApprovalRecord) -> ApprovalRecord:
    return record.model_copy(
        update={
            "approval_id": structured_hash(
                "approval-record", record, exclude={"approval_id"}
            )
        }
    )


def bind_execution_record(record: ExecutionRecord) -> ExecutionRecord:
    input_sources = sorted(record.input_sources, key=lambda item: item.path)
    new_sources = sorted(record.new_sources, key=lambda item: item.path)
    if len({item.path for item in input_sources}) != len(input_sources):
        raise ConfigurationError("ExecutionRecord contains duplicate input source paths")
    if len({item.path for item in new_sources}) != len(new_sources):
        raise ConfigurationError("ExecutionRecord contains duplicate new source paths")
    record = record.model_copy(
        update={
            "input_sources": input_sources,
            "new_sources": new_sources,
            "log_refs": sorted(record.log_refs),
        }
    )
    return record.model_copy(
        update={
            "execution_id": structured_hash(
                "execution-record", record, exclude={"execution_id"}
            )
        }
    )


def bind_modification_report(report: ModificationReport) -> ModificationReport:
    checks = sorted(
        report.checks,
        key=lambda check: (check.group, check.check_id, check.subject_id or ""),
    )
    matches = sorted(
        report.entity_matches, key=lambda result: result.baseline_entity_id
    )
    diagnostics = sorted(
        report.diagnostics, key=lambda diagnostic: (diagnostic.code, diagnostic.message)
    )
    report = report.model_copy(
        update={
            "checks": checks,
            "entity_matches": matches,
            "unmatched_candidate_entity_ids": sorted(
                report.unmatched_candidate_entity_ids
            ),
            "diagnostics": diagnostics,
            "unresolved_issues": sorted(set(report.unresolved_issues)),
        }
    )
    return report.model_copy(
        update={
            "report_id": structured_hash(
                "modification-report", report, exclude={"report_id"}
            )
        }
    )

