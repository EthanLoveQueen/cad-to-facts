from typing import Any, Literal

from pydantic import Field, field_validator

from cad_to_facts.domain.facts import Fact, FactGap, FactRequest, FactSet
from cad_to_facts.domain.snapshot import Diagnostic, EntityRef, ModelSnapshot
from cad_to_facts.domain.source import DomainModel


class Requirement(DomainModel):
    requirement_id: str
    text: str
    source_ref: str
    source_sha256: str | None = None
    content_hash: str


class RequirementBundle(DomainModel):
    bundle_id: str
    requirements: list[Requirement]


class SubjectSelector(DomainModel):
    entity_kind: str


class RuleRef(DomainModel):
    rule_id: str
    version: str | None = None


class RuleInput(DomainModel):
    name: str
    predicate: str
    required: bool = True


ReviewType = Literal["file_health", "requirement_compliance", "design_process_rule"]


class Rule(DomainModel):
    rule_id: str
    version: str
    review_type: ReviewType | None = None
    requirement_refs: list[str]
    subject_selector: SubjectSelector
    applicability: dict[str, Any] = Field(default_factory=dict)
    inputs: list[RuleInput]
    checker: Literal["snapshot.status", "fact.present", "numeric.compare", "count.compare", "declared.value"]
    parameters: dict[str, Any]
    severity: Literal["info", "warning", "error"]
    source: dict[str, Any]


class RuleSet(DomainModel):
    ruleset_id: str
    version: str
    requirement_bundle: RequirementBundle
    rules: list[Rule]


class ReviewScope(DomainModel):
    scope_id: str
    included_rules: list[RuleRef]
    subject_selectors: list[SubjectSelector]
    required_inputs: list[FactRequest]
    discovery_requirements: list[str]

    @field_validator("included_rules", mode="before")
    @classmethod
    def accept_rule_id_strings(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [{"rule_id": item} if isinstance(item, str) else item for item in value]
        return value


class ReviewContext(DomainModel):
    context_id: str
    values: dict[str, Any]


class ReviewRequest(DomainModel):
    snapshot: ModelSnapshot
    factset: FactSet
    ruleset: RuleSet
    scope: ReviewScope
    context: ReviewContext
    reviewer_version: str


class Finding(DomainModel):
    finding_id: str
    rule_id: str
    rule_version: str
    review_type: ReviewType | None = None
    subject: EntityRef
    status: Literal["satisfied", "violated", "unknown", "not_applicable"]
    severity: Literal["info", "warning", "error"]
    reason_code: str | None = None
    facts: list[Fact] = Field(default_factory=list)
    gaps: list[FactGap] = Field(default_factory=list)
    message: str


class CandidateInspection(DomainModel):
    subject: EntityRef
    fully_inspected: bool
    inspection_not_required: bool = False


class Coverage(DomainModel):
    rule_satisfied: int = Field(ge=0)
    rule_violated: int = Field(ge=0)
    rule_unknown: int = Field(ge=0)
    rule_not_applicable: int = Field(ge=0)
    rule_covered: int = Field(ge=0)
    rule_total: int = Field(ge=0)
    rule_coverage: float | None = Field(default=None, ge=0, le=1)
    decision_required_entities: int = Field(ge=0)
    fully_inspected_entities: int = Field(ge=0)
    entity_coverage: float | None = Field(default=None, ge=0, le=1)
    discovered_only_inspection_ratio: float | None = Field(default=None, ge=0, le=1)


class ReviewTypeSummary(DomainModel):
    review_type: ReviewType
    satisfied: int = Field(ge=0)
    violated: int = Field(ge=0)
    unknown: int = Field(ge=0)
    not_applicable: int = Field(ge=0)


class ReviewReport(DomainModel):
    schema_version: str = "0.1"
    report_id: str
    review_run_id: str
    snapshot_id: str
    snapshot_content_hash: str
    factset_id: str
    ruleset_id: str
    scope_id: str
    context_id: str
    overall_status: Literal["non_compliant", "incomplete", "compliant_for_scope"]
    complete: bool
    tool_error: bool
    entity_discovery: Literal["complete", "partial", "unknown"]
    findings: list[Finding]
    review_type_summary: list[ReviewTypeSummary] | None = None
    generated_gaps: list[FactGap]
    candidates: list[CandidateInspection]
    coverage: Coverage
    diagnostics: list[Diagnostic]
