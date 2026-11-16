from typing import Any, Literal

from pydantic import Field

from cad_to_facts.domain.source import DomainModel, SourceArtifact


class DrawingLayer(DomainModel):
    name: str
    off: bool = False
    frozen: bool = False


class DrawingLayout(DomainModel):
    name: str
    kind: Literal["model_space", "paper_space"]
    entity_ids: list[str] = Field(default_factory=list)


class DrawingBlock(DomainModel):
    name: str
    entity_ids: list[str] = Field(default_factory=list)
    is_xref: bool = False
    xref_path: str | None = None


class DrawingConversion(DomainModel):
    """Evidence for an ODA-produced intermediate DXF, without machine paths."""

    converter: str = "ODA File Converter"
    converter_identity: str
    output_version: str = "ACAD2018"
    output_format: str = "DXF"
    audit: bool = True
    output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_size_bytes: int = Field(ge=0)


class DrawingExternalReference(DomainModel):
    """One XREF edge; nested references use parent_reference_id rather than expansion."""

    reference_id: str
    parent_reference_id: str | None = None
    owner_artifact_sha256: str
    block_name: str
    declared_path: str
    depth: int = Field(ge=0)
    state: Literal[
        "resolved",
        "missing",
        "outside_root",
        "invalid_path",
        "unsupported_format",
        "adapter_unavailable",
        "parse_failed",
        "cycle",
        "limit_exceeded",
    ]
    resolved_locator: str | None = None
    artifact: SourceArtifact | None = None
    units: dict[str, str] = Field(default_factory=dict)
    entity_count: int | None = Field(default=None, ge=0)
    entity_discovery: Literal["complete", "partial", "unknown"] = "unknown"
    conversion: DrawingConversion | None = None
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)


class DrawingStructure(DomainModel):
    """Drawing-specific profile; drawing entities are not STEP solids."""

    schema_version: str = "0.1"
    source_format: Literal["dxf", "dwg"]
    dxf_version: str
    layers: list[DrawingLayer] = Field(default_factory=list)
    layouts: list[DrawingLayout] = Field(default_factory=list)
    blocks: list[DrawingBlock] = Field(default_factory=list)
    external_references: list[DrawingExternalReference] = Field(default_factory=list)
    conversion: DrawingConversion | None = None
