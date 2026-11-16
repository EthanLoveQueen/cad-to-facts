from typing import Literal

from pydantic import Field, model_validator

from cad_to_facts.domain.answer import AnswerGap, AnswerStatus
from cad_to_facts.domain.feature import (
    FeatureKind,
    FeatureRecognitionReport,
    ThroughHoleGeometry,
)
from cad_to_facts.domain.orientation import OrientationReport
from cad_to_facts.domain.source import DomainModel
from cad_to_facts.domain.view import TargetResolution, TargetSelector


QuestionIntent = Literal[
    "locate", "occurrence_count", "feature_count", "feature_geometry", "orientation"
]


class QuestionInterpretation(DomainModel):
    interpretation_id: str = Field(min_length=1)
    intent: QuestionIntent
    selector: TargetSelector | None = None
    feature_kinds: list[FeatureKind] | None = None
    evidence_policy: Literal["strict", "candidates_allowed"] = "strict"
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def required_inputs(self):
        if self.intent in {"locate", "occurrence_count", "orientation"} and self.selector is None:
            raise ValueError(f"{self.intent} requires a TargetSelector")
        if self.intent in {"feature_count", "feature_geometry"} and not self.feature_kinds:
            raise ValueError(f"{self.intent} requires feature_kinds")
        if self.feature_kinds is not None and len(set(self.feature_kinds)) != len(self.feature_kinds):
            raise ValueError("feature_kinds must be unique")
        return self


class QuestionSpec(DomainModel):
    schema_version: str = "0.1"
    question_id: str = "0" * 64
    original_text: str = Field(min_length=1)
    interpretation_basis: Literal[
        "deterministic_grammar", "agent_interpretation", "user_supplied"
    ]
    interpretations: list[QuestionInterpretation] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    interpretation_gaps: list[str] = Field(default_factory=list)


class CountAnswer(DomainModel):
    value: int | None = Field(default=None, ge=0)
    state: Literal["known", "observed", "candidate", "unknown"]
    unit: Literal["occurrences", "validated_features", "feature_candidates"]
    evidence_refs: list[str] = Field(default_factory=list)


class InterpretationAnswer(DomainModel):
    interpretation_id: str
    status: AnswerStatus
    resolution: TargetResolution | None = None
    features: FeatureRecognitionReport | None = None
    orientation: OrientationReport | None = None
    occurrence_count: CountAnswer | None = None
    feature_counts: dict[str, CountAnswer] = Field(default_factory=dict)
    geometry: list[ThroughHoleGeometry] = Field(default_factory=list)
    gaps: list[AnswerGap] = Field(default_factory=list)


class AnswerReport(DomainModel):
    schema_version: str = "0.1"
    answer_id: str
    status: AnswerStatus
    complete: bool
    question: QuestionSpec
    answers: list[InterpretationAnswer]
    gaps: list[AnswerGap]
