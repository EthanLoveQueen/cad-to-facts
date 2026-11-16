"""Declared semantic PMI extracted from one parsed artifact.

The model keeps semantic annotations, gaps and source inventory separate so an
unread annotation is never confused with an absent one. It is not a CAD feature
model and does not claim AP242 conformance beyond the supported subset.
"""

from typing import Literal

from pydantic import Field

from cad_to_facts.domain.snapshot import Diagnostic, EntityRef
from cad_to_facts.domain.source import DomainModel

PmiKind = Literal["dimension", "geometric_tolerance", "datum"]
PmiLinkStatus = Literal["resolved", "unresolved", "absent"]


class PmiTolerance(DomainModel):
    """A declared tolerance, without inventing a sign the reader did not keep."""

    form: Literal["limits", "deviation_magnitudes"]
    lower_limit: float | None = None
    upper_limit: float | None = None
    lower_deviation_magnitude: float | None = Field(default=None, ge=0)
    upper_deviation_magnitude: float | None = Field(default=None, ge=0)
    sign_convention: Literal["not_reported_by_reader"] | None = None


class PmiAnnotation(DomainModel):
    """One declared semantic annotation with its geometry links and provenance."""

    annotation_id: str
    kind: PmiKind
    annotation_type: str
    native_type: str
    name: str | None = None
    semantic_name: str | None = None
    value: float | None = None
    unit: str | None = None
    tolerance: PmiTolerance | None = None
    qualifier: str | None = None
    modifiers: list[str] = Field(default_factory=list)
    material_requirement_modifier: str | None = None
    zone_modifier: str | None = None
    datums: list[str] = Field(default_factory=list)
    linked_entities: list[EntityRef] = Field(default_factory=list)
    native_shape_refs: list[dict[str, str]] = Field(default_factory=list)
    link_status: PmiLinkStatus
    native_ref: str


class PmiGap(DomainModel):
    kind: PmiKind | None = None
    annotation_type: str | None = None
    native_ref: str
    reason_code: Literal[
        "PMI_VALUE_UNAVAILABLE",
        "PMI_VALUE_INVALID",
        "PMI_TOLERANCE_INVALID",
        "PMI_UNIT_UNKNOWN",
        "PMI_UNIT_AMBIGUOUS",
        "PMI_GEOMETRY_LINK_ABSENT",
        "PMI_GEOMETRY_LINK_UNRESOLVED",
        "PMI_DATUM_IDENTIFICATION_MISSING",
        "PMI_DATUM_REFERENCE_UNRESOLVED",
        "PMI_UNSUPPORTED_TYPE",
        "PMI_READ_FAILED",
    ]
    message: str
    linked_entities: list[EntityRef] = Field(default_factory=list)


class PmiUnitContext(DomainModel):
    length: str | None = None
    angle: str | None = None
    dimension_representation_count: int = Field(ge=0)


class PmiSourceInventory(DomainModel):
    """Raw AP242 entities observed before the XCAF projection."""

    dimension_entities: int = Field(ge=0)
    dimension_representation_entities: int = Field(ge=0)
    geometric_tolerance_entities: int = Field(ge=0)
    datum_entities: int = Field(ge=0)
    datum_feature_entities: int = Field(ge=0)
    datum_system_entities: int = Field(ge=0)
    presentation_entities: int = Field(ge=0)
    unsupported_category_counts: dict[str, int] = Field(default_factory=dict)


class PmiCoverage(DomainModel):
    dimension_observed: int = Field(ge=0)
    dimension_annotations: int = Field(ge=0)
    dimension_with_value: int = Field(ge=0)
    geometric_tolerance_observed: int = Field(ge=0)
    geometric_tolerance_annotations: int = Field(ge=0)
    geometric_tolerance_with_value: int = Field(ge=0)
    datum_observed: int = Field(ge=0)
    datum_annotations: int = Field(ge=0)
    datum_with_identification: int = Field(ge=0)
    link_resolved: int = Field(ge=0)
    link_unresolved: int = Field(ge=0)
    link_absent: int = Field(ge=0)
    discovery: Literal["complete", "partial", "unknown"]


class PmiExtract(DomainModel):
    """Neutral semantic-PMI extraction bound to one snapshot and artifact."""

    schema_version: str = "0.1"
    pmi_id: str
    artifact_sha256: str
    snapshot_id: str
    snapshot_content_hash: str
    extractor_version: str
    profile: str = "step-semantic-pmi"
    reader: str = "occt-step-xcaf-gdt"
    units: dict[str, str] = Field(default_factory=dict)
    unit_contexts: list[PmiUnitContext] = Field(default_factory=list)
    inventory: PmiSourceInventory
    annotations: list[PmiAnnotation] = Field(default_factory=list)
    gaps: list[PmiGap] = Field(default_factory=list)
    coverage: PmiCoverage
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    status: Literal["failed", "partial", "ready"] = "ready"
    complete: bool
