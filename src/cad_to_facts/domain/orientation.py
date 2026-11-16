from typing import Literal

from pydantic import Field

from cad_to_facts.domain.snapshot import Diagnostic
from cad_to_facts.domain.source import DomainModel
from cad_to_facts.domain.view import (
    CameraSpecification,
    TargetCandidate,
    ViewSpecification,
)


class OrientationPolicy(DomainModel):
    method: Literal["largest_bbox_face_outward_from_assembly"] = (
        "largest_bbox_face_outward_from_assembly"
    )
    axis_relative_tolerance: float = Field(default=1e-6, ge=0)
    axis_absolute_tolerance_mm2: float = Field(default=1e-7, ge=0)
    outward_tolerance_mm: float = Field(default=1e-6, ge=0)
    semantic_label: str = Field(default="front", min_length=1)


class OrientationCandidate(DomainModel):
    camera: CameraSpecification
    axis: Literal["X", "Y", "Z"]
    projected_width_mm: float = Field(ge=0)
    projected_height_mm: float = Field(ge=0)
    projected_area_mm2: float = Field(ge=0)
    depth_mm: float = Field(ge=0)
    center_offset_mm: float
    method: Literal["world_bbox_projection"] = "world_bbox_projection"


class OrientationReference(DomainModel):
    minimum: list[float] = Field(min_length=3, max_length=3)
    maximum: list[float] = Field(min_length=3, max_length=3)
    center: list[float] = Field(min_length=3, max_length=3)
    unit: Literal["mm"] = "mm"
    method: Literal["union_of_root_occurrence_bboxes"] = "union_of_root_occurrence_bboxes"


class OrientationReport(DomainModel):
    schema_version: str = "0.1"
    orientation_id: str
    status: Literal["resolved", "ambiguous", "unresolved", "failed"]
    complete: bool
    semantic_status: Literal["assumed", "unresolved"]
    policy: OrientationPolicy
    target: TargetCandidate | None = None
    assembly_reference: OrientationReference | None = None
    candidates: list[OrientationCandidate]
    selected_candidate: OrientationCandidate | None = None
    recommended_view: ViewSpecification | None = None
    diagnostics: list[Diagnostic]
