from collections import defaultdict

from cad_to_facts.contract import (
    canonicalize_requirement_bundle,
    canonicalize_ruleset,
    canonicalize_scope,
    verify_factset_identity,
    verify_snapshot_identity,
)
from cad_to_facts.domain.facts import Evidence, Fact, FactGap, FactRequest
from cad_to_facts.domain.review import (
    CandidateInspection,
    Coverage,
    Finding,
    ReviewReport,
    ReviewRequest,
    ReviewScope,
    ReviewTypeSummary,
    Rule,
    RuleSet,
)
from cad_to_facts.domain.snapshot import Diagnostic, EntityRef
from cad_to_facts.errors import ConfigurationError
from cad_to_facts.identity import structured_hash

_NUMERIC_OPERATORS = {"<=", ">=", "<", ">"}
_COUNT_OPERATORS = {"==", "<=", ">=", "<", ">"}
_SNAPSHOT_STATUSES = {"ready", "partial", "failed"}


def _matches(rule: Rule, snapshot_entities: list[EntityRef], request: ReviewRequest) -> list[EntityRef]:
    scope_kinds = {selector.entity_kind for selector in request.scope.subject_selectors}
    if rule.subject_selector.entity_kind == "snapshot":
        if "snapshot" not in scope_kinds:
            return []
        return [EntityRef(snapshot_id=request.snapshot.snapshot_id, entity_id="snapshot", entity_kind="snapshot")]
    return [
        entity
        for entity in snapshot_entities
        if entity.entity_kind == rule.subject_selector.entity_kind and entity.entity_kind in scope_kinds
    ]


def _inputs_for(
    rule: Rule,
    subject: EntityRef,
    request: ReviewRequest,
) -> tuple[list[Fact], list[FactGap]]:
    facts = [
        fact
        for fact in request.factset.facts
        if fact.subject.entity_id == subject.entity_id
        and fact.predicate in {item.predicate for item in rule.inputs}
    ]
    gaps = [
        gap
        for gap in request.factset.gaps
        if (gap.subject is None or gap.subject.entity_id == subject.entity_id)
        and gap.request.predicate in {item.predicate for item in rule.inputs}
    ]
    return facts, gaps


def _require_number(rule: Rule, key: str) -> None:
    value = rule.parameters.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"Rule {rule.rule_id}: parameter {key!r} must be numeric")


def _validate_rule(rule: Rule) -> None:
    """Validate a rule's shape independently of the data being reviewed."""

    if rule.applicability:
        if "fact_predicate" not in rule.applicability or "equals" not in rule.applicability:
            raise ConfigurationError(
                f"Rule {rule.rule_id}: applicability requires fact_predicate and equals"
            )
    if rule.checker == "snapshot.status":
        if rule.inputs:
            raise ConfigurationError(f"Rule {rule.rule_id}: snapshot.status does not accept inputs")
        if rule.parameters.get("equals") not in _SNAPSHOT_STATUSES:
            raise ConfigurationError(
                f"Rule {rule.rule_id}: snapshot.status requires equals in {sorted(_SNAPSHOT_STATUSES)}"
            )
        return
    if rule.checker == "fact.present":
        if not rule.inputs:
            raise ConfigurationError(f"Rule {rule.rule_id}: fact.present requires at least one input")
        return
    if len(rule.inputs) != 1:
        raise ConfigurationError(f"Rule {rule.rule_id}: {rule.checker} requires exactly one input")
    if rule.checker == "numeric.compare":
        if rule.parameters.get("operator") not in _NUMERIC_OPERATORS:
            raise ConfigurationError(
                f"Rule {rule.rule_id}: numeric.compare requires operator in {sorted(_NUMERIC_OPERATORS)}"
            )
        _require_number(rule, "threshold")
        _require_number(rule, "abs_tol")
        if rule.parameters["abs_tol"] < 0:
            raise ConfigurationError(f"Rule {rule.rule_id}: abs_tol must be non-negative")
        if not isinstance(rule.parameters.get("unit"), str):
            raise ConfigurationError(f"Rule {rule.rule_id}: numeric.compare requires a unit")
    elif rule.checker == "count.compare":
        if rule.parameters.get("operator") not in _COUNT_OPERATORS:
            raise ConfigurationError(
                f"Rule {rule.rule_id}: count.compare requires operator in {sorted(_COUNT_OPERATORS)}"
            )
        if not isinstance(rule.parameters.get("threshold"), int) or isinstance(
            rule.parameters.get("threshold"), bool
        ):
            raise ConfigurationError(f"Rule {rule.rule_id}: count.compare requires an integer threshold")
    elif rule.checker == "declared.value":
        if "equals" not in rule.parameters:
            raise ConfigurationError(f"Rule {rule.rule_id}: declared.value requires equals")
    else:
        raise ConfigurationError(f"Unsupported checker: {rule.checker}")


def select_rules(ruleset: RuleSet, scope: ReviewScope) -> list[Rule]:
    """Resolve scope rule references to concrete versions, deterministically."""

    rules_by_id: dict[str, list[Rule]] = defaultdict(list)
    for rule in ruleset.rules:
        rules_by_id[rule.rule_id].append(rule)
    selected: list[Rule] = []
    seen: set[tuple[str, str]] = set()
    for reference in scope.included_rules:
        candidates = rules_by_id.get(reference.rule_id, [])
        if not candidates:
            raise ConfigurationError(
                f"ReviewScope.included_rules references unknown rule: {reference.rule_id}"
            )
        if reference.version is None:
            if len(candidates) != 1:
                raise ConfigurationError(
                    f"Rule {reference.rule_id} has multiple versions; specify a version in included_rules"
                )
            rule = candidates[0]
        else:
            matches = [candidate for candidate in candidates if candidate.version == reference.version]
            if not matches:
                raise ConfigurationError(
                    "ReviewScope.included_rules references unknown version "
                    f"{reference.version!r} of rule {reference.rule_id}"
                )
            rule = matches[0]
        key = (rule.rule_id, rule.version)
        if key in seen:
            raise ConfigurationError(
                f"ReviewScope includes rule {rule.rule_id} version {rule.version} more than once"
            )
        seen.add(key)
        selected.append(rule)
    return sorted(selected, key=lambda rule: (rule.rule_id, rule.version))


def _validate_request(request: ReviewRequest) -> None:
    """Reject inconsistent or foreign review inputs before evaluating anything."""

    if (
        request.factset.snapshot_id != request.snapshot.snapshot_id
        or request.factset.snapshot_content_hash != request.snapshot.snapshot_content_hash
    ):
        raise ConfigurationError("FactSet does not belong to the reviewed snapshot")
    allowed_artifacts = {request.snapshot.artifact_sha256}
    if (
        request.snapshot.drawing is not None
        and request.snapshot.parse_options.get("xref_mode") == "flatten"
    ):
        allowed_artifacts.update(
            reference.artifact.sha256
            for reference in request.snapshot.drawing.external_references
            if reference.state == "resolved" and reference.artifact is not None
        )
    for fact in request.factset.facts:
        if fact.evidence.artifact_sha256 not in allowed_artifacts:
            raise ConfigurationError(
                f"Fact evidence artifact does not match the reviewed artifact: {fact.fact_id}"
            )
    for gap in request.factset.gaps:
        if gap.evidence is not None and gap.evidence.artifact_sha256 not in allowed_artifacts:
            raise ConfigurationError(
                f"FactGap evidence artifact does not match the reviewed artifact: {gap.request.predicate}"
            )

    requirements = request.ruleset.requirement_bundle.requirements
    if not requirements:
        raise ConfigurationError("RequirementBundle must contain at least one requirement")
    requirement_ids = [requirement.requirement_id for requirement in requirements]
    if len(set(requirement_ids)) != len(requirement_ids):
        raise ConfigurationError("RequirementBundle contains duplicate requirement_id values")
    requirement_id_set = set(requirement_ids)
    for rule in request.ruleset.rules:
        for reference in rule.requirement_refs:
            if reference not in requirement_id_set:
                raise ConfigurationError(
                    f"Rule {rule.rule_id} references unknown requirement: {reference}"
                )

    rule_keys = [(rule.rule_id, rule.version) for rule in request.ruleset.rules]
    if len(set(rule_keys)) != len(rule_keys):
        raise ConfigurationError("RuleSet contains duplicate rule_id/version pairs")
    select_rules(request.ruleset, request.scope)
    for rule in request.ruleset.rules:
        _validate_rule(rule)


def _facts_for(facts: list[Fact], subject: EntityRef, predicate: str) -> list[Fact]:
    return [fact for fact in facts if fact.subject.entity_id == subject.entity_id and fact.predicate == predicate]


def _gaps_for(gaps: list[FactGap], subject: EntityRef, predicate: str) -> list[FactGap]:
    return [
        gap
        for gap in gaps
        if (gap.subject is None or gap.subject.entity_id == subject.entity_id) and gap.request.predicate == predicate
    ]


def _gap_reason(gaps: list[FactGap]) -> str:
    for gap in gaps:
        if gap.reason_code != "ABSENT":
            return gap.reason_code
    return gaps[0].reason_code if gaps else "NOT_COMPUTED"


def _missing_gap(
    request: ReviewRequest,
    subject: EntityRef,
    name: str,
    predicate: str,
    existing: list[FactGap],
) -> list[FactGap]:
    if _gaps_for(existing, subject, predicate):
        return []
    return [
        FactGap(
            request=FactRequest(name=name, predicate=predicate, subject_id=subject.entity_id),
            subject=subject,
            reason_code="NOT_COMPUTED",
            blocking_capabilities=[predicate],
            evidence=Evidence(artifact_sha256=request.snapshot.artifact_sha256, entity_refs=[subject]),
        )
    ]


def _evaluate(rule: Rule, subject: EntityRef, request: ReviewRequest) -> tuple[Finding, list[FactGap]]:
    if rule.applicability:
        predicate = rule.applicability["fact_predicate"]
        applicability_facts = [
            fact
            for fact in request.factset.facts
            if fact.subject.entity_id == subject.entity_id and fact.predicate == predicate
        ]
        applicability_gaps = [
            gap
            for gap in request.factset.gaps
            if (gap.subject is None or gap.subject.entity_id == subject.entity_id)
            and gap.request.predicate == predicate
        ]
        if not applicability_facts:
            generated = _missing_gap(
                request, subject, "applicability", predicate, applicability_gaps
            )
            return Finding(
                finding_id="0" * 64,
                rule_id=rule.rule_id,
                rule_version=rule.version,
                review_type=rule.review_type,
                subject=subject,
                status="unknown",
                severity=rule.severity,
                reason_code="APPLICABILITY_UNKNOWN",
                gaps=[*applicability_gaps, *generated],
                message=f"{rule.rule_id}: applicability unknown",
            ), generated
        if applicability_facts[0].value != rule.applicability["equals"]:
            return Finding(
                finding_id="0" * 64,
                rule_id=rule.rule_id,
                rule_version=rule.version,
                review_type=rule.review_type,
                subject=subject,
                status="not_applicable",
                severity=rule.severity,
                reason_code="APPLICABILITY_FALSE",
                facts=applicability_facts,
                message=f"{rule.rule_id}: not applicable",
            ), []

    facts, existing_gaps = _inputs_for(rule, subject, request)
    generated: list[FactGap] = []
    for item in rule.inputs:
        if not _facts_for(facts, subject, item.predicate):
            generated.extend(
                _missing_gap(request, subject, item.name, item.predicate, [*existing_gaps, *generated])
            )
    gaps = [*existing_gaps, *generated]

    def input_state(item) -> tuple[bool, str | None]:
        if _facts_for(facts, subject, item.predicate):
            return True, None
        item_gaps = _gaps_for(gaps, subject, item.predicate)
        if not item_gaps:
            return False, "NOT_COMPUTED"
        if all(gap.reason_code == "ABSENT" for gap in item_gaps):
            return False, "ABSENT"
        return False, _gap_reason(item_gaps)

    reason_code: str | None = None
    if rule.checker == "snapshot.status":
        status = "satisfied" if request.snapshot.status == rule.parameters["equals"] else "violated"
    elif rule.checker == "fact.present":
        states = [(input_state(item), item.required) for item in rule.inputs]
        required_missing = [code for (present, code), required in states if not present and required]
        optional_missing = [code for (present, code), required in states if not present and not required]
        if "ABSENT" in required_missing:
            status, reason_code = "violated", "ABSENT"
        elif required_missing:
            status, reason_code = "unknown", required_missing[0]
        elif optional_missing:
            status, reason_code = "unknown", "OPTIONAL_INPUT_MISSING"
        else:
            status = "satisfied"
    elif rule.checker == "numeric.compare":
        input_item = rule.inputs[0]
        input_facts = _facts_for(facts, subject, input_item.predicate)
        input_gaps = _gaps_for(gaps, subject, input_item.predicate)
        if not input_facts:
            status = "unknown"
            reason_code = _gap_reason(input_gaps)
        elif input_facts[0].unit != rule.parameters["unit"]:
            status = "unknown"
            reason_code = "UNIT_MISMATCH"
        else:
            value = input_facts[0].value
            threshold = rule.parameters["threshold"]
            tolerance = rule.parameters["abs_tol"]
            operator = rule.parameters["operator"]
            if operator == "<=":
                passed = value <= threshold + tolerance
            elif operator == ">=":
                passed = value >= threshold - tolerance
            elif operator == "<":
                passed = value < threshold
            else:
                passed = value > threshold
            status = "satisfied" if passed else "violated"
    elif rule.checker == "count.compare":
        input_item = rule.inputs[0]
        input_facts = _facts_for(facts, subject, input_item.predicate)
        input_gaps = _gaps_for(gaps, subject, input_item.predicate)
        if not input_facts:
            status = "unknown"
            reason_code = _gap_reason(input_gaps)
        elif input_facts[0].unit != "dimensionless":
            status = "unknown"
            reason_code = "UNIT_MISMATCH"
        else:
            value = input_facts[0].value
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError("count.compare requires an integer Fact value")
            threshold = rule.parameters["threshold"]
            operator = rule.parameters["operator"]
            passed = {
                "==": value == threshold,
                "<=": value <= threshold,
                ">=": value >= threshold,
                "<": value < threshold,
                ">": value > threshold,
            }[operator]
            status = "satisfied" if passed else "violated"
    elif rule.checker == "declared.value":
        input_item = rule.inputs[0]
        input_facts = _facts_for(facts, subject, input_item.predicate)
        input_gaps = _gaps_for(gaps, subject, input_item.predicate)
        if not input_facts:
            status = "unknown"
            reason_code = _gap_reason(input_gaps)
        else:
            status = "satisfied" if input_facts[0].value == rule.parameters["equals"] else "violated"
    else:  # pragma: no cover - rejected by _validate_rule
        raise ConfigurationError(f"Unsupported checker: {rule.checker}")
    finding = Finding(
        finding_id="0" * 64,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        review_type=rule.review_type,
        subject=subject,
        status=status,
        severity=rule.severity,
        reason_code=reason_code,
        facts=facts,
        gaps=gaps,
        message=f"{rule.rule_id}: {status}",
    )
    return finding, generated


def _coverage(
    findings: list[Finding],
    candidates: dict[str, list[Finding]],
    discovery: str,
    scope_gaps: list[FactGap],
    unresolved_scope_gaps: list[FactGap],
) -> tuple[Coverage, list[CandidateInspection]]:
    counts = defaultdict(int)
    for finding in findings:
        counts[finding.status] += 1
    covered = counts["satisfied"] + counts["violated"]
    total = covered + counts["unknown"]
    unresolved_subjects = {
        gap.subject.entity_id
        for gap in [*scope_gaps, *unresolved_scope_gaps]
        if gap.subject is not None
    }
    inspections: list[CandidateInspection] = []
    for candidate, evaluations in candidates.items():
        applicable = [item for item in evaluations if item.status != "not_applicable"]
        not_required = bool(evaluations) and not applicable
        fully = (
            bool(applicable)
            and candidate not in unresolved_subjects
            and all(item.status in {"satisfied", "violated"} for item in applicable)
        )
        inspections.append(
            CandidateInspection(
                subject=evaluations[0].subject,
                fully_inspected=fully,
                inspection_not_required=not_required,
            )
        )
    decision_required = sum(not item.inspection_not_required for item in inspections)
    fully_inspected = sum(item.fully_inspected for item in inspections)
    entity_coverage = fully_inspected / decision_required if discovery == "complete" and decision_required else None
    discovered_ratio = fully_inspected / decision_required if discovery != "complete" and decision_required else None
    return Coverage(
        rule_satisfied=counts["satisfied"],
        rule_violated=counts["violated"],
        rule_unknown=counts["unknown"],
        rule_not_applicable=counts["not_applicable"],
        rule_covered=covered,
        rule_total=total,
        rule_coverage=covered / total if total else None,
        decision_required_entities=decision_required,
        fully_inspected_entities=fully_inspected,
        entity_coverage=entity_coverage,
        discovered_only_inspection_ratio=discovered_ratio,
    ), inspections


def _scope_input_status(
    request: ReviewRequest, generated: list[FactGap]
) -> tuple[list[FactGap], list[FactGap]]:
    """Return missing scope-input gaps and existing unresolved gaps.

    A required scope input is resolved by a fact or a proven ABSENT gap. Any
    other gap means extraction did not verify the declared input.
    """

    created: list[FactGap] = []
    unresolved: dict[tuple[str, str, str], FactGap] = {}
    known_gaps = [*request.factset.gaps, *generated]
    scope_kinds = {selector.entity_kind for selector in request.scope.subject_selectors}
    for required in request.scope.required_inputs:
        if required.subject_id == "*":
            subjects = [
                entity for entity in request.snapshot.entities if entity.entity_kind in scope_kinds
            ]
        else:
            subjects = [entity for entity in request.snapshot.entities if entity.entity_id == required.subject_id]
        if not subjects:
            created.append(
                FactGap(
                    request=required,
                    reason_code="NOT_COMPUTED",
                    blocking_capabilities=[required.predicate],
                    evidence=Evidence(artifact_sha256=request.snapshot.artifact_sha256),
                )
            )
            continue
        for subject in subjects:
            has_fact = bool(_facts_for(request.factset.facts, subject, required.predicate))
            if has_fact:
                continue
            matching_gaps = _gaps_for(known_gaps, subject, required.predicate)
            if not matching_gaps:
                created.append(
                    FactGap(
                        request=required.model_copy(update={"subject_id": subject.entity_id}),
                        subject=subject,
                        reason_code="NOT_COMPUTED",
                        blocking_capabilities=[required.predicate],
                        evidence=Evidence(
                            artifact_sha256=request.snapshot.artifact_sha256,
                            entity_refs=[subject],
                        ),
                    )
                )
                continue
            for gap in matching_gaps:
                if gap.reason_code == "ABSENT":
                    continue
                attributed = (
                    gap
                    if gap.subject is not None
                    else gap.model_copy(update={"subject": subject})
                )
                unresolved[
                    (
                        subject.entity_id,
                        gap.request.predicate,
                        gap.reason_code,
                    )
                ] = attributed
    return created, list(unresolved.values())


def _discovery_diagnostics(request: ReviewRequest) -> list[Diagnostic]:
    discovered_kinds = {entity.entity_kind for entity in request.snapshot.entities}
    diagnostics: list[Diagnostic] = []
    for kind in request.scope.discovery_requirements:
        if kind == "snapshot" or kind in discovered_kinds:
            continue
        diagnostics.append(
            Diagnostic(
                code="DISCOVERY_REQUIREMENT_UNMET",
                severity="warning",
                stage="review",
                message=f"Scope requires complete discovery of {kind!r} but no such entity was discovered",
                scope_refs=[kind],
                affects=["review", "discovery"],
                impact="partial",
                discovery_impact="unknown",
                count=0,
            )
        )
    return diagnostics


def _verify_identities(request: ReviewRequest) -> ReviewRequest:
    """Verify content IDs and return the canonical request used for evaluation."""

    snapshot = verify_snapshot_identity(request.snapshot)

    bundle = canonicalize_requirement_bundle(request.ruleset.requirement_bundle)
    for requirement in bundle.requirements:
        expected = structured_hash("requirement", requirement, exclude={"content_hash"})
        if requirement.content_hash != expected:
            raise ConfigurationError(
                f"Requirement {requirement.requirement_id} content_hash does not match its content"
            )
    if bundle.bundle_id != structured_hash(
        "requirement-bundle", bundle, exclude={"bundle_id"}
    ):
        raise ConfigurationError(
            "RequirementBundle bundle_id does not match its canonical content"
        )

    ruleset = canonicalize_ruleset(
        request.ruleset.model_copy(update={"requirement_bundle": bundle})
    )
    if request.ruleset.ruleset_id != structured_hash(
        "ruleset", ruleset, exclude={"ruleset_id"}
    ):
        raise ConfigurationError("RuleSet ruleset_id does not match its canonical content")

    scope = canonicalize_scope(request.scope)
    if request.scope.scope_id != structured_hash(
        "review-scope", scope, exclude={"scope_id"}
    ):
        raise ConfigurationError("ReviewScope scope_id does not match its canonical content")

    context = request.context
    if context.context_id != structured_hash(
        "review-context", context, exclude={"context_id"}
    ):
        raise ConfigurationError("ReviewContext context_id does not match its canonical content")

    factset = verify_factset_identity(request.factset)

    return request.model_copy(
        update={
            "snapshot": snapshot,
            "factset": factset,
            "ruleset": ruleset,
            "scope": scope,
            "context": context,
        }
    )


def review(request: ReviewRequest) -> ReviewReport:
    """Evaluate a completely bound, deterministic review request."""

    _validate_request(request)
    request = _verify_identities(request)
    run_id = structured_hash("review-run", request)
    selected = select_rules(request.ruleset, request.scope)
    typed_run = any(rule.review_type is not None for rule in selected)
    findings: list[Finding] = []
    generated_gaps: list[FactGap] = []
    review_diagnostics: list[Diagnostic] = _discovery_diagnostics(request)
    candidates: dict[str, list[Finding]] = {}
    tool_error = False
    for rule in selected:
        subjects = _matches(rule, request.snapshot.entities, request)
        if not subjects:
            review_diagnostics.append(
                Diagnostic(
                    code="EMPTY_SCOPE",
                    severity="warning",
                    stage="review",
                    message=f"Rule {rule.rule_id} has no in-scope candidate subjects",
                    scope_refs=[rule.rule_id],
                    affects=["review"],
                    impact="partial",
                    discovery_impact="none",
                )
            )
        for subject in subjects:
            try:
                finding, new_gaps = _evaluate(rule, subject, request)
            except ConfigurationError:
                raise
            except Exception as error:  # checker failure is an outcome, not a crash
                tool_error = True
                finding = Finding(
                    finding_id="0" * 64,
                    rule_id=rule.rule_id,
                    rule_version=rule.version,
                    review_type=rule.review_type,
                    subject=subject,
                    status="unknown",
                    severity=rule.severity,
                    reason_code="CHECKER_FAILED",
                    message=f"{rule.rule_id}: checker failed: {error}",
                )
                new_gaps = []
            if typed_run and finding.review_type is None:
                finding = finding.model_copy(update={"review_type": "requirement_compliance"})
            generated_gaps.extend(new_gaps)
            object.__setattr__(
                finding,
                "finding_id",
                structured_hash(
                    "finding",
                    {
                        "review_run_id": run_id,
                        "rule_id": rule.rule_id,
                        "rule_version": rule.version,
                        "subject": subject,
                    },
                ),
            )
            findings.append(finding)
            candidates.setdefault(subject.entity_id, []).append(finding)
    scope_gaps, unresolved_scope_gaps = _scope_input_status(request, generated_gaps)
    generated_gaps.extend(scope_gaps)
    for gap in unresolved_scope_gaps:
        subject_id = gap.subject.entity_id if gap.subject is not None else None
        review_diagnostics.append(
            Diagnostic(
                code="SCOPE_INPUT_UNRESOLVED",
                severity="warning",
                stage="review",
                message=(
                    f"Scope-required input {gap.request.name!r} is unresolved "
                    f"({gap.reason_code})"
                    + (f" for {subject_id}" if subject_id else "")
                ),
                scope_refs=[ref for ref in (subject_id, gap.request.predicate) if ref],
                affects=["review"],
                impact="partial",
                discovery_impact="none",
            )
        )
    coverage, inspections = _coverage(
        findings,
        candidates,
        request.snapshot.entity_discovery,
        scope_gaps,
        unresolved_scope_gaps,
    )
    has_violated = any(finding.status == "violated" for finding in findings)
    unresolved_diagnostics = [
        diagnostic
        for diagnostic in [*request.snapshot.diagnostics, *request.factset.diagnostics, *review_diagnostics]
        if diagnostic.disposition != "resolved"
        and (diagnostic.impact != "none" or diagnostic.discovery_impact != "none")
    ]
    complete = (
        request.snapshot.status == "ready"
        and request.snapshot.entity_discovery == "complete"
        and not unresolved_diagnostics
        and not scope_gaps
        and not unresolved_scope_gaps
        and not tool_error
        and coverage.rule_unknown == 0
        and coverage.rule_total > 0
        and all(item.fully_inspected or item.inspection_not_required for item in inspections)
        and bool(inspections)
    )
    if has_violated:
        overall = "non_compliant"
    elif complete:
        overall = "compliant_for_scope"
    else:
        overall = "incomplete"
    type_summary = None
    if typed_run:
        type_summary = []
        review_types = sorted({
            rule.review_type or "requirement_compliance" for rule in selected
        })
        for review_type in review_types:
            typed_findings = [
                finding for finding in findings
                if (finding.review_type or "requirement_compliance") == review_type
            ]
            type_summary.append(ReviewTypeSummary(
                review_type=review_type,
                satisfied=sum(item.status == "satisfied" for item in typed_findings),
                violated=sum(item.status == "violated" for item in typed_findings),
                unknown=sum(item.status == "unknown" for item in typed_findings),
                not_applicable=sum(item.status == "not_applicable" for item in typed_findings),
            ))
    report = ReviewReport(
        report_id="0" * 64,
        review_run_id=run_id,
        snapshot_id=request.snapshot.snapshot_id,
        snapshot_content_hash=request.snapshot.snapshot_content_hash,
        factset_id=request.factset.factset_id,
        ruleset_id=request.ruleset.ruleset_id,
        scope_id=request.scope.scope_id,
        context_id=request.context.context_id,
        overall_status=overall,
        complete=complete,
        tool_error=tool_error,
        entity_discovery=request.snapshot.entity_discovery,
        findings=findings,
        review_type_summary=type_summary,
        generated_gaps=generated_gaps,
        candidates=inspections,
        coverage=coverage,
        diagnostics=[*request.snapshot.diagnostics, *request.factset.diagnostics, *review_diagnostics],
    )
    object.__setattr__(report, "report_id", structured_hash("review-report", report, exclude={"report_id"}))
    return report
