from typing import Any, Literal

from pydantic import Field, field_validator

from cad_to_facts.domain.source import DomainModel


class PartDefinition(DomainModel):
    """A reusable shape definition within one snapshot."""

    definition_id: str
    native_ref: str
    name: str | None = None
    is_assembly: bool


class Occurrence(DomainModel):
    """One active or unresolved use of a PartDefinition in an assembly."""

    occurrence_id: str
    definition_id: str
    parent_occurrence_id: str | None = None
    path: list[str] = Field(min_length=1)
    native_ref: str
    name: str | None = None
    transformation: list[float] = Field(min_length=16, max_length=16)
    state: Literal["active", "inactive", "unknown"] = "active"

    @field_validator("path")
    @classmethod
    def path_ends_at_occurrence(cls, value: list[str]) -> list[str]:
        return value


class AssemblyLink(DomainModel):
    parent_occurrence_id: str
    child_occurrence_id: str


class AssemblyStructure(DomainModel):
    """The occurrence graph represented by an assembly-aware snapshot."""

    schema_version: str = "0.1"
    snapshot_id: str
    discovery: Literal["complete", "partial", "unknown"]
    root_occurrence_ids: list[str] = Field(default_factory=list)
    source_product_count: int | None = Field(default=None, ge=0)
    source_occurrence_count: int | None = Field(default=None, ge=0)
    definitions: list[PartDefinition] = Field(default_factory=list)
    occurrences: list[Occurrence] = Field(default_factory=list)
    links: list[AssemblyLink] = Field(default_factory=list)
