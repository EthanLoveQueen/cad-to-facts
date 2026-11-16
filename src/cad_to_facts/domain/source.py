from pydantic import BaseModel, ConfigDict, Field


class DomainModel(BaseModel):
    """Immutable base for objects whose content can be canonically hashed."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class SourceArtifact(DomainModel):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    format: str
    format_schema: str | None = None
    source_locator: str
    design_revision: str | None = None
