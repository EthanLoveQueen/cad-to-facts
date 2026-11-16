from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from cad_to_facts.domain.answer import AnswerGap, AnswerStatus
from cad_to_facts.domain.drawing_bom import DrawingBOMExtract, DrawingBOMOptions
from cad_to_facts.domain.source import DomainModel


DrawingQuestionIntent = Literal[
    "entity_count",
    "entity_lookup",
    "text_lookup",
    "layer_inventory",
    "block_inventory",
    "measurement_summary",
    "dimension_inventory",
    "name_candidate_count",
    "semantic_evidence",
    "drawing_bom_lookup",
]
DrawingMeasurementPredicate = Literal["length", "area", "circumference"]
DrawingCandidateBasis = Literal["block_name", "layer_name", "text", "attribute_tag"]
DrawingDiscoveryState = Literal["complete", "partial", "unknown"]


class DrawingSelector(DomainModel):
    """Declared drawing-entity filters; no STEP occurrence or camera semantics."""

    kinds: list[str] | None = None
    layers: list[str] | None = None
    containers: list[str] | None = None
    handles: list[str] | None = None
    text_contains_any: list[str] | None = None
    case_sensitive: bool = False
    layer_state_policy: Literal["all", "visible"] = "all"

    @field_validator("kinds", "layers", "containers", "handles", "text_contains_any")
    @classmethod
    def clean_filters(cls, value: list[str] | None, info):
        if value is None:
            return None
        cleaned = [item.strip() for item in value]
        if not cleaned:
            raise ValueError(f"{info.field_name} cannot be an empty list")
        if any(not item for item in cleaned):
            raise ValueError(f"{info.field_name} cannot contain empty strings")
        if info.field_name == "kinds":
            cleaned = [item.lower() for item in cleaned]
        if info.field_name == "handles":
            cleaned = [item.upper() for item in cleaned]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError(f"{info.field_name} must be unique")
        return cleaned


class DrawingQuestionInterpretation(DomainModel):
    interpretation_id: str = Field(min_length=1)
    intent: DrawingQuestionIntent
    selector: DrawingSelector | None = None
    predicate: DrawingMeasurementPredicate | None = None
    include_values: bool = False
    max_results: int = Field(default=50, ge=1, le=1000)
    include_layer_breakdown: bool = False
    candidate_bases: list[DrawingCandidateBasis] | None = None
    candidate_terms: list[str] | None = None
    bom: DrawingBOMOptions | None = None
    evidence_policy: Literal["strict", "candidates_allowed"] = "strict"
    notes: list[str] = Field(default_factory=list)

    @field_validator("candidate_terms")
    @classmethod
    def clean_terms(cls, value: list[str] | None):
        if value is None:
            return None
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("candidate_terms cannot contain empty strings")
        if len({item.casefold() for item in cleaned}) != len(cleaned):
            raise ValueError("candidate_terms must be unique ignoring case")
        return cleaned

    @field_validator("candidate_bases")
    @classmethod
    def clean_bases(cls, value: list[DrawingCandidateBasis] | None):
        if value is not None and not value:
            raise ValueError("candidate_bases cannot be an empty list")
        if value is not None and len(set(value)) != len(value):
            raise ValueError("candidate_bases must be unique")
        return value

    @model_validator(mode="after")
    def required_inputs(self):
        if self.intent == "measurement_summary" and self.predicate is None:
            raise ValueError("measurement_summary requires predicate")
        if self.intent != "measurement_summary" and self.predicate is not None:
            raise ValueError("predicate is valid only for measurement_summary")
        if self.intent != "measurement_summary" and self.include_values:
            raise ValueError("include_values is valid only for measurement_summary")
        if self.intent != "entity_count" and self.include_layer_breakdown:
            raise ValueError("include_layer_breakdown is valid only for entity_count")
        if self.intent in {"name_candidate_count", "semantic_evidence"}:
            if not self.candidate_terms:
                raise ValueError(f"{self.intent} requires candidate_terms")
            if self.evidence_policy != "candidates_allowed":
                raise ValueError(
                    f"{self.intent} requires evidence_policy=candidates_allowed"
                )
        else:
            if self.candidate_terms is not None or self.candidate_bases is not None:
                raise ValueError(
                    "candidate_terms/candidate_bases are valid only for "
                    "name_candidate_count or semantic_evidence"
                )
            if self.evidence_policy != "strict":
                raise ValueError(
                    "evidence_policy=candidates_allowed is valid only for "
                    "name_candidate_count or semantic_evidence"
                )
        if self.intent == "drawing_bom_lookup" and self.bom is None:
            raise ValueError("drawing_bom_lookup requires bom options")
        if self.intent != "drawing_bom_lookup" and self.bom is not None:
            raise ValueError("bom options are valid only for drawing_bom_lookup")
        if self.intent == "layer_inventory" and self.selector is not None:
            selector = self.selector
            if (
                selector.kinds
                or selector.containers
                or selector.handles
                or selector.text_contains_any
                or selector.case_sensitive
                or selector.layer_state_policy != "all"
            ):
                raise ValueError(
                    "layer_inventory selector supports only layers; the inventory itself "
                    "reports off/frozen state"
                )
        if self.intent == "block_inventory" and self.selector is not None:
            raise ValueError(
                "block_inventory covers the full catalog and does not accept a selector"
            )
        if self.intent == "drawing_bom_lookup" and self.selector is not None:
            raise ValueError(
                "drawing_bom_lookup uses bom containers, not a drawing selector"
            )
        return self


class DrawingQuestionSpec(DomainModel):
    schema_version: str = "0.1"
    question_id: str = "0" * 64
    original_text: str = Field(min_length=1)
    interpretation_basis: Literal["agent_interpretation", "user_supplied"]
    interpretations: list[DrawingQuestionInterpretation] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    interpretation_gaps: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_interpretation_ids(self):
        ids = [item.interpretation_id for item in self.interpretations]
        if len(set(ids)) != len(ids):
            raise ValueError("interpretation_id values must be unique")
        return self


class DrawingQueryScope(DomainModel):
    snapshot_id: str
    artifact_sha256: str
    snapshot_content_hash: str
    parse_options: dict[str, Any] = Field(default_factory=dict)
    units: dict[str, str] = Field(default_factory=dict)
    discovery: DrawingDiscoveryState
    filters: dict[str, Any] = Field(default_factory=dict)
    container_scope: Literal["all_catalog", "explicit"]
    layer_state_policy: Literal["all", "visible"]
    source_artifact_sha256s: list[str] = Field(default_factory=list)
    unknown_layer_state_entities: int = Field(default=0, ge=0)
    excluded_by_layer_state: int = Field(default=0, ge=0)


class DrawingCountAnswer(DomainModel):
    value: int | None = Field(default=None, ge=0)
    observed_value: int | None = Field(default=None, ge=0)
    state: Literal["known", "partial", "unknown"]
    unit: Literal["entities", "text_matches"]
    by_kind: dict[str, int] = Field(default_factory=dict)
    by_container_kind: dict[str, int] = Field(default_factory=dict)
    by_layer: dict[str, int] | None = None
    excluded_by_layer_state: int = Field(default=0, ge=0)
    method: str = "drawing_entity_catalog_filter"
    scope: DrawingQueryScope


class DrawingEntitySummary(DomainModel):
    entity_id: str
    kind: str
    layer: str
    container: str
    container_kind: str
    handle: str | None = None
    text: str | None = None
    attribute_tag: str | None = None
    block_name: str | None = None
    source_artifact_sha256: str
    source_length_unit: str


class DrawingLayerSummary(DomainModel):
    name: str
    declared: bool
    off: bool | None = None
    frozen: bool | None = None
    entity_count: int = Field(ge=0)
    kind_counts: dict[str, int] = Field(default_factory=dict)


class DrawingBlockSummary(DomainModel):
    name: str
    declared: bool
    definition_entity_count: int = Field(ge=0)
    insert_entity_count: int = Field(ge=0)
    minsert_array_total: int = Field(ge=0)
    is_xref: bool = False
    xref_path: str | None = None
    instance_containers: dict[str, int] = Field(default_factory=dict)


class DrawingMeasurementValue(DomainModel):
    entity_id: str
    kind: str
    layer: str
    container: str
    handle: str | None = None
    value: float
    unit: str
    source_artifact_sha256: str


class DrawingMeasurementSummary(DomainModel):
    predicate: DrawingMeasurementPredicate
    selected_entity_count: int = Field(ge=0)
    supported_entity_count: int = Field(ge=0)
    unsupported_entity_count: int = Field(ge=0)
    measured_entity_count: int = Field(ge=0)
    value_count: int = Field(ge=0)
    total: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    unit: str
    state: Literal["known", "partial", "unknown"]
    sum_scope: Literal["all_selected_supported", "measured_entities_only", "empty"]
    values: list[DrawingMeasurementValue] | None = None
    values_truncated: bool = False
    unmeasured_entity_ids: list[str] = Field(default_factory=list)
    unmeasured_entity_count: int = Field(default=0, ge=0)
    gap_counts: dict[str, int] = Field(default_factory=dict)


class DrawingDimensionValue(DomainModel):
    entity_id: str
    kind: str
    layer: str
    container: str
    handle: str | None = None
    dimension_type: str
    dimension_type_code: int
    measurement: float | None = None
    unit: str | None = None
    state: Literal["known", "unknown"]
    reason: str | None = None
    text_override: str | None = None
    source_artifact_sha256: str


class DrawingDimensionInventory(DomainModel):
    selected_entity_count: int = Field(ge=0)
    dimension_total: int = Field(ge=0)
    valued_count: int = Field(ge=0)
    unknown_count: int = Field(ge=0)
    state: Literal["known", "partial", "unknown"]
    dimensions: list[DrawingDimensionValue] = Field(default_factory=list)
    truncated: bool = False
    association: Literal["unsupported"] = "unsupported"
    gap_counts: dict[str, int] = Field(default_factory=dict)


class DrawingCandidateMatch(DomainModel):
    entity_id: str
    kind: str
    layer: str
    container: str
    handle: str | None = None
    basis: DrawingCandidateBasis
    term: str
    declared_value: str
    source_artifact_sha256: str


class DrawingCandidateSummary(DomainModel):
    value: int | None = Field(default=None, ge=0)
    state: Literal["candidate", "unknown"]
    unit: Literal["semantic_candidates"] = "semantic_candidates"
    validation: Literal["unvalidated"] = "unvalidated"
    general_semantic_coverage: Literal["unknown"] = "unknown"
    discovery: DrawingDiscoveryState
    terms: list[str]
    bases: list[DrawingCandidateBasis]
    by_basis: dict[str, int] = Field(default_factory=dict)
    match_rows_total: int = Field(default=0, ge=0)
    matches: list[DrawingCandidateMatch] = Field(default_factory=list)
    matches_truncated: bool = False


class DrawingSemanticEvidenceItem(DomainModel):
    entity_id: str
    kind: str
    layer: str
    container: str
    handle: str | None = None
    basis: DrawingCandidateBasis
    term: str
    declared_value: str
    source_artifact_sha256: str
    block_name: str | None = None
    text: str | None = None
    attribute_tag: str | None = None
    attributes: dict[str, list[str]] = Field(default_factory=dict)


class DrawingSemanticEvidenceSummary(DomainModel):
    value: int | None = Field(default=None, ge=0)
    state: Literal["candidate", "unknown"]
    unit: Literal["semantic_evidence"] = "semantic_evidence"
    validation: Literal["unvalidated"] = "unvalidated"
    general_semantic_coverage: Literal["unknown"] = "unknown"
    discovery: DrawingDiscoveryState
    terms: list[str]
    bases: list[DrawingCandidateBasis]
    by_basis: dict[str, int] = Field(default_factory=dict)
    match_rows_total: int = Field(default=0, ge=0)
    evidence: list[DrawingSemanticEvidenceItem] = Field(default_factory=list)
    evidence_truncated: bool = False
    attributed_insert_count: int = Field(default=0, ge=0)


class DrawingInterpretationAnswer(DomainModel):
    interpretation_id: str
    status: AnswerStatus
    count: DrawingCountAnswer | None = None
    entities: list[DrawingEntitySummary] = Field(default_factory=list)
    entity_total: int | None = Field(default=None, ge=0)
    entities_truncated: bool = False
    layers: list[DrawingLayerSummary] = Field(default_factory=list)
    blocks: list[DrawingBlockSummary] = Field(default_factory=list)
    measurements: DrawingMeasurementSummary | None = None
    dimensions: DrawingDimensionInventory | None = None
    candidates: DrawingCandidateSummary | None = None
    semantic_evidence: DrawingSemanticEvidenceSummary | None = None
    bom: DrawingBOMExtract | None = None
    scope: DrawingQueryScope
    gaps: list[AnswerGap] = Field(default_factory=list)


class DrawingAnswerReport(DomainModel):
    schema_version: str = "0.1"
    profile: Literal["drawing"] = "drawing"
    answer_id: str
    status: AnswerStatus
    complete: bool
    question: DrawingQuestionSpec
    answers: list[DrawingInterpretationAnswer]
    gaps: list[AnswerGap]
