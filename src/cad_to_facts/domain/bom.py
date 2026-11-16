from typing import Any, Literal

from pydantic import Field

from cad_to_facts.domain.assembly import AssemblyLink, Occurrence, PartDefinition
from cad_to_facts.domain.snapshot import Diagnostic
from cad_to_facts.domain.source import DomainModel


class BOMOptions(DomainModel):
    required_properties: list[str] = Field(default_factory=list)


class BOMLineItem(DomainModel):
    part_definition_id: str
    name: str | None = None
    declared_properties: dict[str, Any] = Field(default_factory=dict)
    quantity: int | None = Field(default=None, ge=0)
    quantity_state: Literal["known", "observed", "unknown"]
    occurrence_refs: list[str] = Field(default_factory=list)
    counted_occurrence_refs: list[str] = Field(default_factory=list)


class BOMMissingInput(DomainModel):
    subject_id: str
    field: str
    reason_code: Literal["ABSENT", "UNSUPPORTED", "NOT_COMPUTED"]
    message: str


class BOMCoverage(DomainModel):
    definition_total: int = Field(ge=0)
    occurrence_total: int = Field(ge=0)
    counted_occurrence_total: int = Field(ge=0)
    unknown_quantity_definition_total: int = Field(ge=0)
    observed_quantity_definition_total: int = Field(ge=0)
    # Default preserves validation of BOMExtract documents written before this
    # field existed; newly extracted BOMs always set it from line-item states.
    known_quantity_definition_total: int = Field(default=0, ge=0)
    structure_discovery: Literal["complete", "partial", "unknown"]


class BOMExtract(DomainModel):
    """Neutral model BOM data; not an ERP or manufacturing BOM."""

    schema_version: str = "0.1"
    bom_id: str
    artifact_sha256: str
    snapshot_id: str
    snapshot_content_hash: str
    extractor_version: str
    options: BOMOptions
    line_items: list[BOMLineItem]
    definitions: list[PartDefinition] = Field(default_factory=list)
    occurrences: list[Occurrence] = Field(default_factory=list)
    assembly_links: list[AssemblyLink] = Field(default_factory=list)
    missing_inputs: list[BOMMissingInput] = Field(default_factory=list)
    coverage: BOMCoverage
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    complete: bool
