from typing import Any, Literal

from pydantic import Field

from cad_to_facts.domain.snapshot import Diagnostic
from cad_to_facts.domain.source import DomainModel


class DrawingBOMOptions(DomainModel):
    part_tag: str = Field(min_length=1)
    quantity_tag: str | None = None
    material_tag: str | None = None
    description_tag: str | None = None
    required_tags: list[str] = Field(default_factory=list)
    containers: list[str] = Field(default_factory=lambda: ["Model"])
    allow_external_reference_exclusion: bool = False


class DrawingBOMOccurrence(DomainModel):
    entity_id: str
    artifact_sha256: str
    block_name: str
    part_number: str | None = None
    declared_properties: dict[str, str] = Field(default_factory=dict)
    declared_quantity: int | None = Field(default=None, ge=1)
    instance_count: int = Field(ge=0)


class DrawingBOMMissingInput(DomainModel):
    subject_id: str
    field: str
    reason_code: Literal["ABSENT", "INVALID", "AMBIGUOUS", "NOT_COMPUTED"]
    message: str


class DrawingBOMLineItem(DomainModel):
    line_item_id: str
    part_number: str | None = None
    block_names: list[str] = Field(default_factory=list)
    source_artifact_sha256s: list[str] = Field(default_factory=list)
    declared_properties: dict[str, Any] = Field(default_factory=dict)
    property_conflicts: list[str] = Field(default_factory=list)
    quantity: int | None = Field(default=None, ge=0)
    quantity_state: Literal["known", "observed", "unknown"]
    occurrence_refs: list[str] = Field(default_factory=list)
    counted_occurrence_refs: list[str] = Field(default_factory=list)


class DrawingBOMCoverage(DomainModel):
    definition_total: int = Field(ge=0)
    occurrence_total: int = Field(ge=0)
    counted_occurrence_total: int = Field(ge=0)
    unknown_quantity_definition_total: int = Field(ge=0)
    observed_quantity_definition_total: int = Field(ge=0)
    known_quantity_definition_total: int = Field(default=0, ge=0)
    external_reference_total: int = Field(default=0, ge=0)
    counted_external_reference_total: int = Field(default=0, ge=0)
    uncounted_external_reference_total: int = Field(default=0, ge=0)
    structure_discovery: Literal["complete", "partial", "unknown"]


class DrawingBOMExtract(DomainModel):
    """Neutral attribute-block BOM; not a manufacturing or ERP BOM."""

    schema_version: str = "0.1"
    bom_id: str
    artifact_sha256: str
    snapshot_id: str
    snapshot_content_hash: str
    extractor_version: str
    options: DrawingBOMOptions
    line_items: list[DrawingBOMLineItem]
    occurrences: list[DrawingBOMOccurrence] = Field(default_factory=list)
    missing_inputs: list[DrawingBOMMissingInput] = Field(default_factory=list)
    coverage: DrawingBOMCoverage
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    complete: bool
