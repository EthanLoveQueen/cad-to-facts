from typing import Literal

from pydantic import Field

from cad_to_facts.domain.facts import FactSet
from cad_to_facts.domain.snapshot import Diagnostic, ModelSnapshot
from cad_to_facts.domain.source import DomainModel


class NumericTolerance(DomainModel):
    """Declared absolute/relative tolerance for numeric fingerprint comparison."""

    absolute: float = Field(default=0.0, ge=0)
    relative: float = Field(default=0.0, ge=0)

    def within(self, first: float, second: float) -> bool:
        return abs(first - second) <= self.absolute + self.relative * max(
            abs(first), abs(second)
        )


class EntityMatchingProfile(DomainModel):
    """A closed, declarative method for relating baseline entities to candidates."""

    profile_id: str
    schema_version: str = "0.1"
    method: Literal["native_ref", "adapter_key", "fingerprint"]
    native_ref_type: str | None = None
    fingerprint_predicates: list[str] = Field(default_factory=list)
    tolerance: NumericTolerance = Field(default_factory=NumericTolerance)


class EntityMatchRequest(DomainModel):
    """Match explicit required baseline entities under one declared profile."""

    request_id: str
    baseline: ModelSnapshot
    candidate: ModelSnapshot
    profile: EntityMatchingProfile
    required_baseline_entity_ids: list[str]
    baseline_facts: FactSet | None = None
    candidate_facts: FactSet | None = None


class EntityMatchResult(DomainModel):
    baseline_entity_id: str
    entity_kind: str
    status: Literal["matched", "unmatched", "ambiguous", "unresolved"]
    candidate_entity_ids: list[str] = Field(default_factory=list)
    reason_code: str | None = None
    message: str


class EntityMatchReport(DomainModel):
    schema_version: str = "0.1"
    report_id: str
    request_id: str
    profile_id: str
    baseline_snapshot_id: str
    baseline_snapshot_content_hash: str
    candidate_snapshot_id: str
    candidate_snapshot_content_hash: str
    status: Literal["complete", "incomplete"]
    results: list[EntityMatchResult]
    unmatched_candidate_entity_ids: list[str]
    diagnostics: list[Diagnostic]
