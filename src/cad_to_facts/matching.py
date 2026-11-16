"""Deterministic entity matching for a declared before/after profile.

This module is an internal library used by change verification. It has no
standalone CLI, does not execute or approve a change, and never treats a match
as proof that two entities are the same persistent object. A match is evidence
under exactly one declared method and tolerance.
"""

from collections import defaultdict

import math

from cad_to_facts.contract import verify_factset_identity, verify_snapshot_identity
from cad_to_facts.domain.facts import Fact, FactSet
from cad_to_facts.domain.matching import (
    EntityMatchReport,
    EntityMatchRequest,
    EntityMatchResult,
    EntityMatchingProfile,
)
from cad_to_facts.domain.snapshot import Diagnostic, EntityRef, ModelSnapshot
from cad_to_facts.errors import ConfigurationError
from cad_to_facts.identity import structured_hash


def _validate_profile(profile: EntityMatchingProfile) -> None:
    if profile.method != "fingerprint" and (
        profile.tolerance.absolute or profile.tolerance.relative
    ):
        raise ConfigurationError(
            "Numeric tolerance is only valid for fingerprint matching"
        )
    if profile.method == "native_ref":
        if not profile.native_ref_type:
            raise ConfigurationError(
                "native_ref matching requires a non-empty native_ref_type"
            )
        if profile.fingerprint_predicates:
            raise ConfigurationError(
                "fingerprint_predicates are not valid for native_ref matching"
            )
    elif profile.method == "adapter_key":
        if profile.native_ref_type is not None:
            raise ConfigurationError(
                "native_ref_type is not valid for adapter_key matching"
            )
        if profile.fingerprint_predicates:
            raise ConfigurationError(
                "fingerprint_predicates are not valid for adapter_key matching"
            )
    elif profile.method == "fingerprint":
        if profile.native_ref_type is not None:
            raise ConfigurationError(
                "native_ref_type is not valid for fingerprint matching"
            )
        if not profile.fingerprint_predicates:
            raise ConfigurationError(
                "fingerprint matching requires at least one fingerprint predicate"
            )
        if len(set(profile.fingerprint_predicates)) != len(
            profile.fingerprint_predicates
        ):
            raise ConfigurationError(
                "fingerprint_predicates must not contain duplicates"
            )
    else:  # pragma: no cover - rejected by the Literal type
        raise ConfigurationError(f"Unsupported matching method: {profile.method}")


def bind_matching_profile(profile: EntityMatchingProfile) -> EntityMatchingProfile:
    _validate_profile(profile)
    return profile.model_copy(
        update={
            "profile_id": structured_hash(
                "entity-matching-profile", profile, exclude={"profile_id"}
            )
        }
    )


def _canonical_required_ids(
    request: EntityMatchRequest, baseline: ModelSnapshot
) -> list[str]:
    identifiers = list(request.required_baseline_entity_ids)
    if not identifiers:
        raise ConfigurationError(
            "required_baseline_entity_ids must contain at least one entity"
        )
    if len(set(identifiers)) != len(identifiers):
        raise ConfigurationError(
            "required_baseline_entity_ids must not contain duplicates"
        )
    baseline_ids = [entity.entity_id for entity in baseline.entities]
    if len(set(baseline_ids)) != len(baseline_ids):
        raise ConfigurationError("Baseline snapshot contains duplicate entity IDs")
    known = set(baseline_ids)
    missing = sorted(set(identifiers) - known)
    if missing:
        raise ConfigurationError(
            f"Required baseline entity is not in the baseline snapshot: {missing[0]}"
        )
    return sorted(identifiers)


def _verify_factset_binding(factset: FactSet, snapshot: ModelSnapshot, role: str) -> FactSet:
    if (
        factset.snapshot_id != snapshot.snapshot_id
        or factset.snapshot_content_hash != snapshot.snapshot_content_hash
    ):
        raise ConfigurationError(f"{role} FactSet does not belong to its snapshot")
    for fact in factset.facts:
        if fact.evidence.artifact_sha256 != snapshot.artifact_sha256:
            raise ConfigurationError(
                f"{role} Fact evidence artifact does not match its snapshot"
            )
        if fact.subject.snapshot_id != snapshot.snapshot_id:
            raise ConfigurationError(
                f"{role} Fact subject does not belong to its snapshot"
            )
    return factset


def _canonical_matching_request(request: EntityMatchRequest) -> EntityMatchRequest:
    _validate_profile(request.profile)
    baseline = verify_snapshot_identity(request.baseline)
    candidate = verify_snapshot_identity(request.candidate)
    baseline_facts = (
        verify_factset_identity(request.baseline_facts)
        if request.baseline_facts is not None
        else None
    )
    candidate_facts = (
        verify_factset_identity(request.candidate_facts)
        if request.candidate_facts is not None
        else None
    )
    if baseline_facts is not None:
        baseline_facts = _verify_factset_binding(baseline_facts, baseline, "Baseline")
    if candidate_facts is not None:
        candidate_facts = _verify_factset_binding(candidate_facts, candidate, "Candidate")
    if request.profile.method == "fingerprint":
        if baseline_facts is None or candidate_facts is None:
            raise ConfigurationError(
                "fingerprint matching requires baseline_facts and candidate_facts"
            )
    return request.model_copy(
        update={
            "baseline": baseline,
            "candidate": candidate,
            "baseline_facts": baseline_facts,
            "candidate_facts": candidate_facts,
            "required_baseline_entity_ids": _canonical_required_ids(request, baseline),
        }
    )


def bind_matching_request(request: EntityMatchRequest) -> EntityMatchRequest:
    request = _canonical_matching_request(request)
    profile = bind_matching_profile(request.profile)
    request = request.model_copy(update={"profile": profile})
    return request.model_copy(
        update={
            "request_id": structured_hash(
                "entity-match-request", request, exclude={"request_id"}
            )
        }
    )


def _result(
    entity: EntityRef,
    status: str,
    reason_code: str | None,
    candidate_entity_ids: list[str] | None = None,
) -> EntityMatchResult:
    candidates = candidate_entity_ids or []
    if status == "matched":
        detail = f"matched {candidates[0]}"
    elif status == "ambiguous":
        detail = f"matched {len(candidates)} candidates"
    elif status == "unmatched":
        detail = "no candidate matched"
    else:
        detail = reason_code or "unresolved"
    return EntityMatchResult(
        baseline_entity_id=entity.entity_id,
        entity_kind=entity.entity_kind,
        status=status,
        candidate_entity_ids=candidates,
        reason_code=reason_code,
        message=f"{entity.entity_id}: {detail}",
    )


def _native_ref_value(entity: EntityRef, ref_type: str) -> tuple[str | None, str | None]:
    references = [ref for ref in entity.native_refs if ref.get("type") == ref_type]
    if not references:
        return None, "MISSING_NATIVE_REF"
    values: list[str] = []
    for reference in references:
        value = reference.get("value")
        if not value:
            return None, "MALFORMED_NATIVE_REF"
        values.append(value)
    if len(set(values)) != 1:
        return None, "AMBIGUOUS_NATIVE_REF"
    return values[0], None


def _adapter_key(entity: EntityRef) -> tuple[str | None, str | None]:
    if not entity.adapter_key:
        return None, "MISSING_ADAPTER_KEY"
    return entity.adapter_key, None


def _index_by_key(
    entities: list[EntityRef], key_for
) -> dict[tuple[str, str], list[str]]:
    index: dict[tuple[str, str], list[str]] = defaultdict(list)
    for entity in entities:
        value, _ = key_for(entity)
        if value is not None:
            index[(entity.entity_kind, value)].append(entity.entity_id)
    return index


def _key_matching(
    request: EntityMatchRequest, key_for
) -> list[EntityMatchResult]:
    required = set(request.required_baseline_entity_ids)
    baseline_entities = [
        entity
        for entity in request.baseline.entities
        if entity.entity_id in required
    ]
    values: dict[str, tuple[str, str]] = {}
    results: list[EntityMatchResult] = []
    for entity in baseline_entities:
        value, reason = key_for(entity)
        if value is None:
            results.append(_result(entity, "unresolved", reason))
        else:
            values[entity.entity_id] = (entity.entity_kind, value)
    grouped: dict[tuple[str, str], list[EntityRef]] = defaultdict(list)
    for entity in baseline_entities:
        if entity.entity_id in values:
            grouped[values[entity.entity_id]].append(entity)
    index = _index_by_key(request.candidate.entities, key_for)
    for key, entities in grouped.items():
        if len(entities) > 1:
            for entity in entities:
                results.append(
                    _result(entity, "unresolved", "DUPLICATE_BASELINE_KEY")
                )
            continue
        entity = entities[0]
        candidates = index.get(key, [])
        if not candidates:
            results.append(_result(entity, "unmatched", "NO_CANDIDATE"))
        elif len(candidates) == 1:
            results.append(_result(entity, "matched", None, candidates))
        else:
            results.append(_result(entity, "ambiguous", "AMBIGUOUS_CANDIDATE", candidates))
    order = {entity_id: position for position, entity_id in enumerate(request.required_baseline_entity_ids)}
    return sorted(results, key=lambda result: order[result.baseline_entity_id])


def _numeric_fingerprint(
    entity: EntityRef, facts: list[Fact], predicates: list[str]
) -> tuple[list[tuple[float, str]] | None, str | None]:
    fingerprint: list[tuple[float, str]] = []
    for predicate in predicates:
        matches = [
            fact
            for fact in facts
            if fact.subject.entity_id == entity.entity_id
            and fact.predicate == predicate
        ]
        if not matches:
            return None, "MISSING_FACT"
        if len(matches) > 1:
            return None, "DUPLICATE_FACT"
        fact = matches[0]
        if isinstance(fact.value, bool) or not isinstance(fact.value, (int, float)):
            return None, "NON_NUMERIC_FACT"
        value = float(fact.value)
        if not math.isfinite(value):
            return None, "NON_FINITE_FACT"
        fingerprint.append((value, fact.unit))
    return fingerprint, None


def _fingerprint_matching(request: EntityMatchRequest) -> list[EntityMatchResult]:
    assert request.baseline_facts is not None
    assert request.candidate_facts is not None
    predicates = list(request.profile.fingerprint_predicates)
    tolerance = request.profile.tolerance
    required = set(request.required_baseline_entity_ids)
    results: list[EntityMatchResult] = []
    for entity in request.baseline.entities:
        if entity.entity_id not in required:
            continue
        fingerprint, reason = _numeric_fingerprint(
            entity, request.baseline_facts.facts, predicates
        )
        if fingerprint is None:
            results.append(_result(entity, "unresolved", reason))
            continue
        candidates = [
            candidate
            for candidate in request.candidate.entities
            if candidate.entity_kind == entity.entity_kind
        ]
        if not candidates:
            results.append(_result(entity, "unmatched", "NO_CANDIDATE"))
            continue
        complete = 0
        comparable = 0
        unit_mismatch = False
        matches: list[str] = []
        for candidate in candidates:
            candidate_fingerprint, _ = _numeric_fingerprint(
                candidate, request.candidate_facts.facts, predicates
            )
            if candidate_fingerprint is None:
                continue
            complete += 1
            if any(
                baseline_unit != candidate_unit
                for (_, baseline_unit), (_, candidate_unit) in zip(
                    fingerprint, candidate_fingerprint
                )
            ):
                unit_mismatch = True
                continue
            comparable += 1
            if all(
                tolerance.within(baseline_value, candidate_value)
                for (baseline_value, _), (candidate_value, _) in zip(
                    fingerprint, candidate_fingerprint
                )
            ):
                matches.append(candidate.entity_id)
        if len(matches) == 1:
            results.append(_result(entity, "matched", None, matches))
        elif len(matches) > 1:
            results.append(_result(entity, "ambiguous", "AMBIGUOUS_CANDIDATE", matches))
        elif comparable:
            results.append(_result(entity, "unmatched", "NO_MATCHING_FINGERPRINT"))
        elif complete and unit_mismatch:
            results.append(_result(entity, "unresolved", "UNIT_MISMATCH"))
        else:
            results.append(
                _result(entity, "unresolved", "CANDIDATE_FACTS_UNAVAILABLE")
            )
    order = {entity_id: position for position, entity_id in enumerate(request.required_baseline_entity_ids)}
    return sorted(results, key=lambda result: order[result.baseline_entity_id])


def _resolve_candidate_conflicts(
    results: list[EntityMatchResult],
) -> tuple[list[EntityMatchResult], set[str]]:
    claims: dict[str, list[str]] = defaultdict(list)
    for result in results:
        if result.status == "matched":
            claims[result.candidate_entity_ids[0]].append(result.baseline_entity_id)
    conflicted = {
        baseline_id
        for baseline_ids in claims.values()
        if len(baseline_ids) > 1
        for baseline_id in baseline_ids
    }
    resolved = [
        result.model_copy(
            update={
                "status": "ambiguous",
                "reason_code": "CANDIDATE_CONFLICT",
                "message": (
                    f"{result.baseline_entity_id}: candidate "
                    f"{result.candidate_entity_ids[0]} is claimed by multiple baseline entities"
                ),
            }
        )
        if result.baseline_entity_id in conflicted
        else result
        for result in results
    ]
    return resolved, set(claims)


def _parse_profile_diagnostics(
    baseline: ModelSnapshot, candidate: ModelSnapshot
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if (
        baseline.adapter_id != candidate.adapter_id
        or baseline.adapter_version != candidate.adapter_version
        or baseline.parser_kernel_version != candidate.parser_kernel_version
        or baseline.parse_options != candidate.parse_options
    ):
        diagnostics.append(
            Diagnostic(
                code="PARSE_PROFILE_MISMATCH",
                severity="error",
                stage="change",
                message="Baseline and candidate were not parsed with the same profile",
                affects=["change", "discovery"],
                impact="fatal",
                discovery_impact="none",
            )
        )
    for role, snapshot in (("Baseline", baseline), ("Candidate", candidate)):
        if snapshot.status != "ready":
            diagnostics.append(
                Diagnostic(
                    code=f"{role.upper()}_SNAPSHOT_NOT_READY",
                    severity="error",
                    stage="change",
                    message=f"{role} snapshot status is {snapshot.status}",
                    affects=["discovery"],
                    impact="partial",
                    discovery_impact="none",
                )
            )
        if snapshot.entity_discovery != "complete":
            diagnostics.append(
                Diagnostic(
                    code=f"{role.upper()}_DISCOVERY_INCOMPLETE",
                    severity="warning",
                    stage="change",
                    message=(
                        f"{role} entity discovery is {snapshot.entity_discovery}"
                    ),
                    affects=["discovery"],
                    impact="partial",
                    discovery_impact=snapshot.entity_discovery,
                )
            )
    return diagnostics


def match_entities(request: EntityMatchRequest) -> EntityMatchReport:
    """Match required baseline entities and report completeness honestly."""

    canonical = _canonical_matching_request(request)
    expected_profile_id = structured_hash(
        "entity-matching-profile", request.profile, exclude={"profile_id"}
    )
    if request.profile.profile_id != expected_profile_id:
        raise ConfigurationError(
            "profile_id does not match the canonical matching profile"
        )
    canonical = canonical.model_copy(update={"profile": request.profile})
    expected_request_id = structured_hash(
        "entity-match-request", canonical, exclude={"request_id"}
    )
    if request.request_id != expected_request_id:
        raise ConfigurationError(
            "request_id does not match the canonical matching request"
        )

    diagnostics = _parse_profile_diagnostics(canonical.baseline, canonical.candidate)
    if any(diagnostic.code == "PARSE_PROFILE_MISMATCH" for diagnostic in diagnostics):
        required = set(canonical.required_baseline_entity_ids)
        order = {
            entity_id: position
            for position, entity_id in enumerate(canonical.required_baseline_entity_ids)
        }
        results = sorted(
            [
                _result(entity, "unresolved", "PARSE_PROFILE_MISMATCH")
                for entity in canonical.baseline.entities
                if entity.entity_id in required
            ],
            key=lambda result: order[result.baseline_entity_id],
        )
        matched_candidates: set[str] = set()
    else:
        if canonical.profile.method == "native_ref":
            ref_type = canonical.profile.native_ref_type
            assert ref_type is not None
            results = _key_matching(
                canonical, lambda entity: _native_ref_value(entity, ref_type)
            )
        elif canonical.profile.method == "adapter_key":
            results = _key_matching(canonical, _adapter_key)
        else:
            results = _fingerprint_matching(canonical)
        results, matched_candidates = _resolve_candidate_conflicts(results)

    unmatched = sorted(
        entity.entity_id
        for entity in canonical.candidate.entities
        if entity.entity_id not in matched_candidates
    )
    blocking = [
        diagnostic
        for diagnostic in diagnostics
        if diagnostic.impact != "none" or diagnostic.discovery_impact != "none"
    ]
    complete = not blocking and all(
        result.status == "matched" for result in results
    )
    report = EntityMatchReport(
        report_id="0" * 64,
        request_id=canonical.request_id,
        profile_id=canonical.profile.profile_id,
        baseline_snapshot_id=canonical.baseline.snapshot_id,
        baseline_snapshot_content_hash=canonical.baseline.snapshot_content_hash,
        candidate_snapshot_id=canonical.candidate.snapshot_id,
        candidate_snapshot_content_hash=canonical.candidate.snapshot_content_hash,
        status="complete" if complete else "incomplete",
        results=results,
        unmatched_candidate_entity_ids=unmatched,
        diagnostics=diagnostics,
    )
    return report.model_copy(
        update={
            "report_id": structured_hash(
                "entity-match-report", report, exclude={"report_id"}
            )
        }
    )
