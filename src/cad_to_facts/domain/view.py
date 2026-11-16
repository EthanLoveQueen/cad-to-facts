from typing import Literal

from pydantic import Field, model_validator

from cad_to_facts.domain.snapshot import Diagnostic
from cad_to_facts.domain.source import DomainModel


class TargetSelector(DomainModel):
    """Declarative occurrence filters; every field is ANDed within one snapshot."""

    occurrence_id: str | None = None
    path: str | None = None
    name: str | None = None
    name_contains: str | None = None
    name_contains_any: list[str] | None = Field(default=None, min_length=1)
    definition_id: str | None = None
    is_assembly: bool | None = None
    is_root: bool | None = None
    state: Literal["active", "inactive", "unknown"] | None = None
    spatial: list["SpatialConstraint"] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_constraint(self):
        fields = (
            self.occurrence_id,
            self.path,
            self.name,
            self.name_contains,
            self.name_contains_any,
            self.definition_id,
            self.is_assembly,
            self.is_root,
            self.state,
            self.spatial or None,
        )
        if all(value is None for value in fields):
            raise ValueError("TargetSelector requires at least one constraint")
        if self.name == "" or self.name_contains == "" or self.path == "":
            raise ValueError("TargetSelector text constraints must not be empty")
        if self.name_contains_any is not None and any(
            not value for value in self.name_contains_any
        ):
            raise ValueError("TargetSelector text constraints must not be empty")
        return self


class BoundingBox(DomainModel):
    minimum: list[float] = Field(min_length=3, max_length=3)
    maximum: list[float] = Field(min_length=3, max_length=3)
    extents: list[float] = Field(min_length=3, max_length=3)
    center: list[float] = Field(min_length=3, max_length=3)
    unit: Literal["mm"] = "mm"
    method: Literal["BRepBndLib.AddOptimal"] = "BRepBndLib.AddOptimal"


class TargetCandidate(DomainModel):
    """One discovered occurrence candidate, not a persistent or functional identity."""

    occurrence_id: str
    path: str
    name_path: list[str]
    native_ref: str
    name: str | None
    definition_id: str
    definition_name: str | None
    is_assembly: bool
    state: Literal["active", "inactive", "unknown"]
    transformation: list[float] = Field(min_length=16, max_length=16)
    bbox: BoundingBox | None = None
    geometry_diagnostic: str | None = None
    spatial_evidence: list["SpatialMatchEvidence"] | None = None


class TargetResolution(DomainModel):
    schema_version: str = "0.1"
    resolution_id: str
    status: Literal["resolved", "ambiguous", "unresolved", "failed"]
    complete: bool
    discovery: Literal["complete", "partial", "unknown"]
    selector: TargetSelector
    candidate_total: int = Field(ge=0)
    candidates: list[TargetCandidate]
    resolved_target: TargetCandidate | None = None
    diagnostics: list[Diagnostic]


class SemanticViewIntent(DomainModel):
    """External meaning attached to a camera; it is not a source-file declaration."""

    label: str = Field(min_length=1)
    basis: Literal["user_selected", "assumed"]
    note: str | None = None


class CameraSpecification(DomainModel):
    preset: Literal["front", "back", "left", "right", "top", "bottom", "iso"] | None = None
    normal: list[float] | None = Field(default=None, min_length=3, max_length=3)
    right: list[float] | None = Field(default=None, min_length=3, max_length=3)

    @model_validator(mode="after")
    def require_one_frame(self):
        if self.preset is not None and (self.normal is not None or self.right is not None):
            raise ValueError("Camera preset cannot be combined with normal/right")
        if self.preset is None and (self.normal is None or self.right is None):
            raise ValueError("Camera requires a preset or both normal and right vectors")
        return self


class DisplaySpecification(DomainModel):
    show_hidden_lines: bool = False


class SpatialConstraint(DomainModel):
    """A bounded world-bbox relation in an explicit camera frame."""

    relation: Literal[
        "left_of", "right_of", "above", "below", "in_front_of", "behind", "near"
    ]
    reference: TargetSelector
    frame: CameraSpecification
    tolerance_mm: float = Field(default=1e-7, ge=0)
    max_distance_mm: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def bounded_relation(self):
        if self.reference.spatial:
            raise ValueError("Spatial reference selectors cannot contain nested spatial constraints")
        if self.relation == "near" and self.max_distance_mm is None:
            raise ValueError("Spatial near requires max_distance_mm")
        if self.relation != "near" and self.max_distance_mm is not None:
            raise ValueError("max_distance_mm is valid only for spatial near")
        return self


class SpatialMatchEvidence(DomainModel):
    relation: Literal[
        "left_of", "right_of", "above", "below", "in_front_of", "behind", "near"
    ]
    reference_occurrence_id: str
    candidate_coordinate: float | None = None
    reference_coordinate: float | None = None
    distance_mm: float | None = None
    frame: CameraSpecification
    method: Literal["world_bbox_center_projection", "world_bbox_gap"]


class ImageSpecification(DomainModel):
    width: int = Field(default=1200, ge=64, le=8192)
    height: int = Field(default=900, ge=64, le=8192)
    padding: float = Field(default=24.0, ge=0)
    curve_deflection_mm: float = Field(default=0.1, gt=0)
    max_points: int = Field(default=200000, ge=100, le=2000000)

    @model_validator(mode="after")
    def usable_page(self):
        if self.padding * 2 >= min(self.width, self.height):
            raise ValueError("Image padding leaves no drawable page")
        return self


class ViewSpecification(DomainModel):
    schema_version: str = "0.1"
    title: str | None = None
    camera: CameraSpecification
    display: DisplaySpecification = Field(default_factory=DisplaySpecification)
    image: ImageSpecification = Field(default_factory=ImageSpecification)
    semantic_intent: SemanticViewIntent | None = None


class RenderStats(DomainModel):
    visible_edge_count: int = Field(ge=0)
    hidden_edge_count: int = Field(ge=0)
    skipped_edge_count: int = Field(default=0, ge=0)
    point_count: int = Field(ge=0)
    projected_extents: list[float] = Field(min_length=2, max_length=2)


class RendererInfo(DomainModel):
    library: Literal["OCCT"] = "OCCT"
    kernel_version: str
    algorithm: Literal["HLRBRep_Algo + HLRBRep_HLRToShape"] = (
        "HLRBRep_Algo + HLRBRep_HLRToShape"
    )
    curve_discretization: Literal["GCPnts_QuasiUniformDeflection"] = (
        "GCPnts_QuasiUniformDeflection"
    )


class RenderOutput(DomainModel):
    path: str
    format: Literal["svg"] = "svg"
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)


class ViewRenderManifest(DomainModel):
    schema_version: str = "0.1"
    kind: Literal["step_view_render"] = "step_view_render"
    view_render_id: str
    artifact_sha256: str
    snapshot_id: str
    snapshot_content_hash: str
    target: TargetCandidate
    view: ViewSpecification
    renderer: RendererInfo
    render: RenderStats
    output: RenderOutput
    diagnostics: list[Diagnostic]
    fidelity: Literal["review_render_only_not_visual_or_geometric_equivalence"] = (
        "review_render_only_not_visual_or_geometric_equivalence"
    )


TargetSelector.model_rebuild()
SpatialConstraint.model_rebuild()
TargetCandidate.model_rebuild()