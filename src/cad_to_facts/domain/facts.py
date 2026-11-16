from typing import Any, Literal

from pydantic import Field, field_validator

from cad_to_facts.domain.snapshot import Diagnostic, EntityRef
from cad_to_facts.domain.source import DomainModel


class FactRequest(DomainModel):
    name: str
    predicate: str
    subject_id: str


class ExtractionQuery(DomainModel):
    requests: list[FactRequest]


class Evidence(DomainModel):
    artifact_sha256: str
    entity_refs: list[EntityRef] = Field(default_factory=list)


class Method(DomainModel):
    library: str
    algorithm: str
    version: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class Fact(DomainModel):
    fact_id: str
    kind: Literal["declared", "measured", "derived"]
    subject: EntityRef
    predicate: str
    value: Any
    unit: str
    evidence: Evidence
    method: Method

    @field_validator("value")
    @classmethod
    def value_must_be_present(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("A null value must be represented by FactGap, not Fact")
        return value


class FactGap(DomainModel):
    request: FactRequest
    subject: EntityRef | None = None
    reason_code: Literal[
        "ABSENT",
        "UNKNOWN_UNIT",
        "UNSUPPORTED",
        "PARSE_FAILED",
        "NOT_COMPUTED",
        "MEASUREMENT_FAILED",
    ]
    blocking_capabilities: list[str] = Field(default_factory=list)
    evidence: Evidence | None = None


class FactSet(DomainModel):
    schema_version: str = "0.1"
    factset_id: str
    snapshot_id: str
    snapshot_content_hash: str
    extraction_query: ExtractionQuery
    extractor_version: str
    facts: list[Fact]
    gaps: list[FactGap]
    diagnostics: list[Diagnostic]
