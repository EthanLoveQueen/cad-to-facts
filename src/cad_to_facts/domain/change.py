from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from cad_to_facts.domain.facts import ExtractionQuery, Fact, FactGap, FactRequest, FactSet
from cad_to_facts.domain.matching import (
    EntityMatchResult,
    EntityMatchingProfile,
    NumericTolerance,
)
from cad_to_facts.domain.review import ReviewContext, ReviewReport, ReviewScope, RuleSet
from cad_to_facts.domain.snapshot import Diagnostic, ModelSnapshot
from cad_to_facts.domain.source import DomainModel, SourceArtifact


class ManifestFile(DomainModel):
    """A workspace-relative file bound by exact bytes."""

    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)

    @field_validator("path")
    @classmethod
    def normalized_relative_path(cls, value: str) -> str:
        if (
            not value
            or "\\" in value
            or PureWindowsPath(value).is_absolute()
            or PurePosixPath(value).is_absolute()
            or PurePosixPath(value).as_posix() != value
            or any(part in {"", ".", ".."} for part in value.split("/"))
        ):
            raise ValueError("Manifest paths must be normalized workspace-relative POSIX paths")
        return value


class GeneratedArtifact(ManifestFile):
    format: str
    source_paths: list[str] = Field(default_factory=list)


class SourceModification(DomainModel):
    old_path: str
    new_path: str

    @field_validator("old_path", "new_path")
    @classmethod
    def normalized_paths(cls, value: str) -> str:
        return ManifestFile.normalized_relative_path(value)


class GeneratorRef(DomainModel):
    name: str
    version: str


class SourceManifest(DomainModel):
    schema_version: str = "0.1"
    manifest_sha256: str
    lineage_kind: Literal["root", "derived"]
    parent_manifest_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    generator: GeneratorRef
    parameters: dict[str, Any] = Field(default_factory=dict)
    sources: list[ManifestFile]
    dependency_files: list[ManifestFile] = Field(default_factory=list)
    generated_artifacts: list[GeneratedArtifact] = Field(default_factory=list)
    modified_from: list[SourceModification] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_lineage(self):
        if self.lineage_kind == "root":
            if self.parent_manifest_sha256 is not None:
                raise ValueError("A root manifest cannot have a parent manifest")
            if self.modified_from:
                raise ValueError("A root manifest cannot contain modified_from entries")
        elif self.parent_manifest_sha256 is None:
            raise ValueError("A derived manifest requires parent_manifest_sha256")
        return self


class ValueCheck(DomainModel):
    """One explicit target constraint on a measured or derived fact."""

    check_id: str
    subject_id: str
    predicate: str
    operator: Literal["==", "!=", "<", "<=", ">", ">="] | None = None
    value: Any = None
    unit: str | None = None
    tolerance: NumericTolerance = Field(default_factory=NumericTolerance)
    presence_only: bool = False

    @model_validator(mode="after")
    def validate_constraint(self):
        if self.presence_only:
            if self.operator is not None or self.value is not None or self.unit is not None:
                raise ValueError("A presence-only check cannot have a value constraint")
        elif self.operator is None or self.value is None:
            raise ValueError("A value check requires an operator and a non-null value")
        if self.value is not None and isinstance(self.value, (int, float)) and not self.unit:
            raise ValueError("A numeric value check requires an explicit unit")
        return self


class InvariantCheck(DomainModel):
    """A fact that must remain equal between matched before/after entities."""

    check_id: str
    subject_id: str
    predicate: str
    unit: str
    tolerance: NumericTolerance = Field(default_factory=NumericTolerance)


class DataRetentionCheck(DomainModel):
    """Retention or explicit invalidation of a declared non-geometric data channel."""

    check_id: str
    subject_id: str
    predicate: str
    unit: str
    expectation: Literal["preserved", "explicitly_invalidated"] = "preserved"
    tolerance: NumericTolerance = Field(default_factory=NumericTolerance)


class ComparisonPolicy(DomainModel):
    required_baseline_entity_ids: list[str] = Field(default_factory=list)
    allowed_added_entity_ids: list[str] = Field(default_factory=list)
    allowed_removed_baseline_entity_ids: list[str] = Field(default_factory=list)
    non_target_predicates: list[str] = Field(default_factory=list)
    non_target_tolerance: NumericTolerance = Field(default_factory=NumericTolerance)
    data_retention_not_applicable: bool = False


class OutputPolicy(DomainModel):
    format: Literal["step"] = "step"
    path: str
    overwrite_base: Literal[False] = False

    @field_validator("path")
    @classmethod
    def non_empty_path(cls, value: str) -> str:
        if not value or "\0" in value:
            raise ValueError("Output path must be non-empty and contain no NUL bytes")
        return value


class VerificationProfile(DomainModel):
    """The fixed parser, extractor and entity-matching configuration."""

    schema_version: str = "0.1"
    profile_id: str
    adapter_id: str
    adapter_version: str
    parser_kernel_version: str
    parse_options: dict[str, Any] = Field(default_factory=dict)
    extractor_version: str
    extraction_query_template: ExtractionQuery
    matching: EntityMatchingProfile


class OriginReview(DomainModel):
    """The complete immutable review inputs from which a change was derived."""

    review_run_id: str
    finding_id: str
    origin_report_id: str
    ruleset: RuleSet
    scope: ReviewScope
    context: ReviewContext
    reviewer_version: str


class ChangeRequest(DomainModel):
    schema_version: str = "0.1"
    request_id: str
    origin_kind: Literal["review_derived", "user_intended"]
    origin_review: OriginReview | None = None
    user_intent: str | None = None
    base_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    base_snapshot_id: str
    base_factset_id: str
    verification_base_factset_id: str | None = None
    base_source_manifest_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    verification_profile: VerificationProfile
    target_entity_ids: list[str]
    preconditions: list[ValueCheck] = Field(default_factory=list)
    target_checks: list[ValueCheck]
    invariant_checks: list[InvariantCheck] = Field(default_factory=list)
    data_retention_checks: list[DataRetentionCheck] = Field(default_factory=list)
    comparison: ComparisonPolicy = Field(default_factory=ComparisonPolicy)
    output_policy: OutputPolicy

    @model_validator(mode="after")
    def validate_origin(self):
        if self.origin_kind == "user_intended":
            if not self.user_intent:
                raise ValueError("A user-intended change requires user_intent")
            if self.origin_review is not None:
                raise ValueError("A user-intended change cannot have an origin review")
        elif self.origin_review is None:
            raise ValueError("A review-derived change requires its complete origin review")
        if self.comparison.data_retention_not_applicable and self.data_retention_checks:
            raise ValueError(
                "Data-retention checks conflict with data_retention_not_applicable"
            )
        return self


class TargetBinding(DomainModel):
    target_entity_id: str
    executor_ref: str


class SourceOperation(DomainModel):
    operation_id: str
    kind: Literal["set_parameter", "add_source", "remove_source"]
    source_path: str
    parameter: str | None = None
    value: Any = None

    @field_validator("source_path")
    @classmethod
    def normalized_source_path(cls, value: str) -> str:
        return ManifestFile.normalized_relative_path(value)

    @model_validator(mode="after")
    def validate_operation(self):
        if self.kind == "set_parameter":
            if not self.parameter or self.value is None:
                raise ValueError("set_parameter requires a parameter and non-null value")
        elif self.parameter is not None or self.value is not None:
            raise ValueError("Source additions/removals cannot have parameter values")
        return self


class ChangePlan(DomainModel):
    schema_version: str = "0.1"
    plan_id: str
    request_id: str
    executor: GeneratorRef
    target_bindings: list[TargetBinding]
    operations: list[SourceOperation] = Field(default_factory=list)
    expected_invalidated_refs: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_sha256: str
    baseline_manifest_validation: Literal["passed", "not_provided", "not_applicable"] = (
        "not_provided"
    )


class ChangePreparationSpec(DomainModel):
    """Explicit executor handoff inputs; no CAD operation is executed here."""

    schema_version: str = "0.1"
    executor: GeneratorRef
    target_executor_ref: str
    operations: list[SourceOperation] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    output_policy: OutputPolicy
    matching: EntityMatchingProfile
    preconditions: list[ValueCheck] = Field(default_factory=list)
    invariant_checks: list[InvariantCheck] = Field(default_factory=list)
    data_retention_checks: list[DataRetentionCheck] = Field(default_factory=list)
    comparison: ComparisonPolicy = Field(default_factory=ComparisonPolicy)


class ChangePreparation(DomainModel):
    schema_version: str = "0.1"
    preparation_id: str
    request: ChangeRequest
    plan: ChangePlan


class ApprovalRecord(DomainModel):
    schema_version: str = "0.1"
    approval_id: str
    request_id: str
    plan_id: str
    base_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    base_source_manifest_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    executor: GeneratorRef
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    approver: str = Field(min_length=1)
    decision: Literal["approved", "rejected"]
    approved_at: str = Field(min_length=1)


class ExecutionRecord(DomainModel):
    schema_version: str = "0.1"
    execution_id: str
    approval_id: str
    request_id: str
    plan_id: str
    executor: GeneratorRef
    input_sources: list[ManifestFile] = Field(default_factory=list)
    base_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    new_sources: list[ManifestFile] = Field(default_factory=list)
    new_artifact_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    new_source_manifest_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    result: Literal["succeeded", "failed"]
    mode: Literal["attested_local", "observed_external"]
    attested_by: str | None = Field(default=None, min_length=1)
    attestation: str | None = Field(default=None, min_length=1)
    log_refs: list[str] = Field(default_factory=list)
    executed_at: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_result(self):
        if self.result == "succeeded" and self.new_artifact_sha256 is None:
            raise ValueError("A successful execution must identify its new artifact")
        return self


class VerificationRequest(DomainModel):
    """All deterministic inputs for one read-only before/after verification run."""

    change: ChangeRequest
    plan: ChangePlan | None = None
    approval: ApprovalRecord | None = None
    execution: ExecutionRecord | None = None
    before_artifact: SourceArtifact
    after_artifact: SourceArtifact | None = None
    before_snapshot: ModelSnapshot
    after_snapshot: ModelSnapshot | None = None
    before_factset: FactSet
    after_factset: FactSet | None = None
    before_manifest: SourceManifest | None = None
    after_manifest: SourceManifest | None = None
    before_manifest_directory: str | None = None
    after_manifest_directory: str | None = None
    origin_review: ReviewReport | None = None
    allow_relocated_output: bool = False

    @model_validator(mode="after")
    def validate_output_group(self):
        outputs = [self.after_artifact, self.after_snapshot, self.after_factset]
        if any(item is None for item in outputs) and not all(
            item is None for item in outputs
        ):
            raise ValueError(
                "after_artifact, after_snapshot and after_factset must be present together"
            )
        return self


class ConditionalRef(DomainModel):
    state: Literal["present", "missing", "not_provided", "not_applicable"]
    ref: str | None = None
    reason_code: str | None = None

    @model_validator(mode="after")
    def validate_reference(self):
        if self.state == "present" and not self.ref:
            raise ValueError("A present conditional reference requires ref")
        if self.state != "present" and self.ref is not None:
            raise ValueError("An unavailable conditional reference cannot contain ref")
        return self


class VerificationCheck(DomainModel):
    group: Literal[
        "input_identity",
        "manifest",
        "precondition",
        "matching",
        "target",
        "invariant",
        "non_target",
        "data_retention",
        "original_rule",
        "approval",
        "execution",
    ]
    check_id: str
    subject_id: str | None = None
    status: Literal["passed", "failed", "incomplete", "not_applicable"]
    reason_code: str | None = None
    expected: Any = None
    actual: Any = None
    facts: list[Fact] = Field(default_factory=list)
    gaps: list[FactGap] = Field(default_factory=list)
    message: str


class ModificationReport(DomainModel):
    schema_version: str = "0.1"
    report_id: str
    request_id: str
    plan_id: str | None = None
    verification_profile_id: str
    after_artifact: ConditionalRef
    after_snapshot: ConditionalRef
    after_factset: ConditionalRef
    before_manifest: ConditionalRef
    after_manifest: ConditionalRef
    origin_review: ConditionalRef
    after_review: ConditionalRef
    manifest_validation: Literal[
        "passed", "failed", "incomplete", "not_provided", "not_applicable"
    ]
    approval_validation: Literal["passed", "failed", "not_provided"]
    verification_status: Literal["passed", "failed", "incomplete"]
    execution_provenance: Literal["attested", "unattested", "contradicted"]
    change_observed: Literal["changed", "no_change", "unknown"]
    checks: list[VerificationCheck]
    entity_matches: list[EntityMatchResult] = Field(default_factory=list)
    unmatched_candidate_entity_ids: list[str] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    unresolved_issues: list[str] = Field(default_factory=list)
    tool_error: bool = False
