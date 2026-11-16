from typing import Literal

from pydantic import Field, model_validator

from cad_to_facts.domain.snapshot import Diagnostic
from cad_to_facts.domain.source import DomainModel
from cad_to_facts.domain.view import TargetCandidate, TargetSelector


FeatureKind = Literal["door", "window", "hole"]
RecognitionMethod = Literal["declared_name_alias", "occt_full_cylinder_open_endpoints"]


class FeatureQuery(DomainModel):
    kinds: list[FeatureKind] = Field(min_length=1)
    selector: TargetSelector | None = None
    recognition_methods: list[RecognitionMethod] = Field(
        default_factory=lambda: [
            "declared_name_alias", "occt_full_cylinder_open_endpoints"
        ],
        min_length=1,
    )
    additional_aliases: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_aliases(self):
        if len(set(self.kinds)) != len(self.kinds):
            raise ValueError("Feature kinds must be unique")
        for kind, aliases in self.additional_aliases.items():
            if kind not in {"door", "window", "hole"} or not aliases:
                raise ValueError("additional_aliases must use supported kinds and nonempty lists")
            if any(not alias.strip() for alias in aliases):
                raise ValueError("Feature aliases must not be empty")
        return self


class ThroughHoleGeometry(DomainModel):
    face_ref: str
    radius_mm: float = Field(gt=0)
    length_mm: float = Field(gt=0)
    axis: list[float] = Field(min_length=3, max_length=3)
    area_mm2: float = Field(gt=0)
    center: list[float] = Field(min_length=3, max_length=3)
    unit: Literal["mm"] = "mm"


class FeatureCandidate(DomainModel):
    feature_id: str
    kind: FeatureKind
    target: TargetCandidate
    validation: Literal["unvalidated", "validated"]
    recognition_method: RecognitionMethod
    matched_alias: str | None = None
    matched_text: str | None = None
    geometry: ThroughHoleGeometry | None = None


class FeatureGap(DomainModel):
    code: Literal[
        "DOOR_GEOMETRY_VALIDATION_UNSUPPORTED",
        "WINDOW_GEOMETRY_VALIDATION_UNSUPPORTED",
        "GENERAL_HOLE_RECOGNITION_UNSUPPORTED",
        "FEATURE_DISCOVERY_INCOMPLETE",
        "FEATURE_SHAPE_UNAVAILABLE",
    ]
    kind: FeatureKind | None = None
    message: str
    occurrence_ids: list[str] = Field(default_factory=list)


class FeatureRecognitionReport(DomainModel):
    schema_version: str = "0.1"
    feature_recognition_id: str
    status: Literal["ready", "partial", "failed"]
    complete: bool
    discovery: Literal["complete", "partial", "unknown"]
    general_feature_coverage: Literal["unknown"] = "unknown"
    query: FeatureQuery
    candidate_total: int = Field(ge=0)
    validated_total: int = Field(ge=0)
    candidate_counts: dict[str, int]
    validated_counts: dict[str, int]
    candidates: list[FeatureCandidate]
    gaps: list[FeatureGap]
    diagnostics: list[Diagnostic]
