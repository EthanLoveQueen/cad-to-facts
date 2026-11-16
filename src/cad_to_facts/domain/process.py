from typing import Any, Literal

from pydantic import Field, field_validator

from cad_to_facts.domain.facts import Fact, FactGap
from cad_to_facts.domain.snapshot import Diagnostic, EntityRef
from cad_to_facts.domain.source import DomainModel


DesignInput = Literal["declared_material", "semantic_pmi", "validated_features"]


class ProcessInputOptions(DomainModel):
    """Declared preparation scope; it contains no manufacturing decisions."""

    required_context: list[str] = Field(
        default_factory=lambda: ["material", "stock", "batch_size"]
    )
    required_design_inputs: list[DesignInput] = Field(default_factory=list)


class ProcessExternalInput(DomainModel):
    name: str
    value: Any
    source: Literal["user_supplied"] = "user_supplied"

    @field_validator("value")
    @classmethod
    def value_is_present(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("A missing external input belongs in missing_inputs")
        return value


class ProcessMissingInput(DomainModel):
    subject_id: str
    field: str
    reason_code: Literal[
        "ABSENT", "UNSUPPORTED", "NOT_COMPUTED", "UNKNOWN_UNIT", "PARSE_FAILED", "MEASUREMENT_FAILED"
    ]
    required: bool
    message: str


class ProcessEntity(DomainModel):
    entity: EntityRef
    facts: list[Fact] = Field(default_factory=list)
    gaps: list[FactGap] = Field(default_factory=list)


class ProcessCoverage(DomainModel):
    entity_total: int = Field(ge=0)
    fully_measured_entity_total: int = Field(ge=0)
    required_missing_total: int = Field(ge=0)
    optional_missing_total: int = Field(ge=0)
    structure_discovery: Literal["complete", "partial", "unknown"]


class ProcessCardInput(DomainModel):
    """Neutral design-side process input, never an operation or production plan."""

    schema_version: str = "0.1"
    process_input_id: str
    artifact_sha256: str
    snapshot_id: str
    snapshot_content_hash: str
    factset_id: str
    context_id: str
    preparer_version: str
    options: ProcessInputOptions
    entities: list[ProcessEntity] = Field(default_factory=list)
    external_inputs: list[ProcessExternalInput] = Field(default_factory=list)
    missing_inputs: list[ProcessMissingInput] = Field(default_factory=list)
    coverage: ProcessCoverage
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    complete: bool
