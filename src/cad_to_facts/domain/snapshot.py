from typing import Any, Literal

from pydantic import Field, PrivateAttr

from cad_to_facts.domain.assembly import AssemblyStructure
from cad_to_facts.domain.drawing import DrawingStructure
from cad_to_facts.domain.source import DomainModel


class Diagnostic(DomainModel):
    code: str
    severity: Literal["info", "warning", "error", "fatal"]
    stage: Literal["probe", "read", "translate", "measure", "review", "change"]
    message: str
    scope_refs: list[str] = Field(default_factory=list)
    affects: list[str] = Field(default_factory=list)
    impact: Literal["none", "partial", "fatal"] = "none"
    discovery_impact: Literal["none", "partial", "unknown"] = "none"
    disposition: Literal["open", "resolved", "accepted"] = "open"
    entity_refs: list[str] = Field(default_factory=list)
    count: int | None = Field(default=None, ge=0)
    details: dict[str, Any] = Field(default_factory=dict)


class EntityRef(DomainModel):
    snapshot_id: str
    entity_id: str
    entity_kind: str
    identity_scope: Literal["snapshot"] = "snapshot"
    native_refs: list[dict[str, str]] = Field(default_factory=list)
    assembly_path: list[str] = Field(default_factory=list)
    adapter_key: str | None = None


class ModelSnapshot(DomainModel):
    schema_version: str = "0.1"
    artifact_sha256: str
    snapshot_id: str
    snapshot_content_hash: str
    adapter_id: str
    adapter_version: str
    parser_kernel_version: str
    parse_options: dict[str, Any]
    units: dict[str, str]
    status: Literal["failed", "partial", "ready"]
    entity_discovery: Literal["complete", "partial", "unknown"]
    entities: list[EntityRef]
    assembly: AssemblyStructure | None = None
    drawing: DrawingStructure | None = None
    diagnostics: list[Diagnostic]

    _adapter_payload: Any = PrivateAttr(default=None)

    def set_adapter_payload(self, payload: Any) -> None:
        object.__setattr__(self, "_adapter_payload", payload)
