"""Deterministic builders for P2 source manifests, approvals and execution records.

These builders only read raw bytes from an explicit workspace and bind project
records through the existing ``bind_*`` contract functions. They never execute
CAD, never run source scripts and never modify files. Approval and execution
facts are never inferred: the approver, decision, timestamps, execution mode,
result and an explicit attestation must be supplied by the caller.
"""

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal

from cad_to_facts.contract import (
    bind_approval_record,
    bind_change_plan,
    bind_execution_record,
    bind_source_manifest,
    verify_change_request_identity,
    verify_source_manifest_identity,
)
from cad_to_facts.domain.change import (
    ApprovalRecord,
    ChangePlan,
    ChangeRequest,
    ExecutionRecord,
    GeneratedArtifact,
    GeneratorRef,
    ManifestFile,
    SourceManifest,
    SourceModification,
)
from cad_to_facts.errors import ConfigurationError
from cad_to_facts.manifest import validate_manifest_files

__all__ = [
    "GeneratedArtifactInput",
    "build_root_source_manifest",
    "build_derived_source_manifest",
    "build_approval_record",
    "build_execution_record",
]

_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class GeneratedArtifactInput:
    """Declared generated output; exact bytes are recomputed from the workspace."""

    path: str
    format: str
    source_paths: tuple[str, ...] = ()


def _require_relative_path(path: str, *, label: str) -> str:
    """Validate a normalized workspace-relative POSIX path without touching disk."""
    if not isinstance(path, str) or not path:
        raise ConfigurationError(
            f"{label} path must be a normalized workspace-relative POSIX path, got {path!r}"
        )
    if (
        "\\" in path
        or PureWindowsPath(path).is_absolute()
        or PurePosixPath(path).is_absolute()
        or PurePosixPath(path).as_posix() != path
        or any(part in {"", ".", ".."} for part in path.split("/"))
    ):
        raise ConfigurationError(
            f"{label} path must be a normalized workspace-relative POSIX path: {path!r}"
        )
    return path


def _workspace_root(workspace: str | Path) -> Path:
    root = Path(workspace).resolve()
    if not root.is_dir():
        raise ConfigurationError(f"Workspace directory does not exist: {workspace!r}")
    return root


def _hashed_file(root: Path, path: str, *, label: str) -> ManifestFile:
    """Hash one confined workspace file, refusing paths that escape the root."""
    try:
        resolved = (root / path).resolve()
    except OSError as exc:
        raise ConfigurationError(
            f"{label} file cannot be resolved inside the workspace: {path!r}"
        ) from exc
    if not resolved.is_relative_to(root):
        raise ConfigurationError(f"{label} path escapes the workspace: {path!r}")
    if not resolved.is_file():
        raise ConfigurationError(
            f"{label} file does not exist inside the workspace: {path!r}"
        )
    digest = hashlib.sha256()
    size = 0
    with resolved.open("rb") as stream:
        while chunk := stream.read(_CHUNK_SIZE):
            digest.update(chunk)
            size += len(chunk)
    return ManifestFile(path=path, sha256=digest.hexdigest(), size_bytes=size)


def _hash_artifact_file(path: str | Path) -> str:
    candidate = Path(path).resolve()
    if not candidate.is_file():
        raise ConfigurationError(f"New artifact file does not exist: {path!r}")
    digest = hashlib.sha256()
    with candidate.open("rb") as stream:
        while chunk := stream.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _collect_files(root: Path, paths: Sequence[str], *, label: str) -> list[ManifestFile]:
    normalized = [_require_relative_path(path, label=label) for path in paths]
    if len(set(normalized)) != len(normalized):
        duplicates = sorted({path for path in normalized if normalized.count(path) > 1})
        raise ConfigurationError(
            f"Duplicate {label.lower()} paths in one manifest: {', '.join(duplicates)}"
        )
    return [_hashed_file(root, path, label=label) for path in normalized]


def _collect_artifact(root: Path, item: GeneratedArtifactInput) -> GeneratedArtifact:
    if not isinstance(item, GeneratedArtifactInput):
        raise ConfigurationError(
            f"Generated artifacts must be GeneratedArtifactInput values, got {item!r}"
        )
    path = _require_relative_path(item.path, label="Generated artifact")
    source_paths = [
        _require_relative_path(source_path, label="Generated artifact source")
        for source_path in item.source_paths
    ]
    bound = _hashed_file(root, path, label="Generated artifact")
    return GeneratedArtifact(
        path=bound.path,
        sha256=bound.sha256,
        size_bytes=bound.size_bytes,
        format=item.format,
        source_paths=source_paths,
    )


def _validate_disjoint_sets(
    source_files: list[ManifestFile],
    dependency_files: list[ManifestFile],
    artifact_files: list[GeneratedArtifact],
) -> None:
    seen: dict[str, str] = {}
    for label, files in (
        ("a source", source_files),
        ("a dependency", dependency_files),
        ("a generated artifact", artifact_files),
    ):
        for item in files:
            previous = seen.get(item.path)
            if previous is not None:
                raise ConfigurationError(
                    f"Path {item.path!r} is declared both as {previous} and as {label}"
                )
            seen[item.path] = label


def _validate_artifact_source_mapping(
    source_files: list[ManifestFile], artifact_files: list[GeneratedArtifact]
) -> None:
    source_paths = {item.path for item in source_files}
    for artifact in artifact_files:
        unknown = sorted(set(artifact.source_paths) - source_paths)
        if unknown:
            raise ConfigurationError(
                f"Generated artifact {artifact.path!r} references unknown source paths: "
                + ", ".join(unknown)
            )


def _verified_plan(plan: ChangePlan) -> ChangePlan:
    """Return the canonical plan, rejecting content that does not match its IDs."""
    canonical = bind_change_plan(plan)
    if canonical.plan_id != plan.plan_id or canonical.payload_sha256 != plan.payload_sha256:
        raise ConfigurationError(
            "ChangePlan content does not match its bound plan_id/payload_sha256; "
            "bind the plan before building records"
        )
    return canonical


def _validated_workspace_manifest(
    manifest: SourceManifest, workspace: str | Path, *, side: str
) -> SourceManifest:
    canonical = verify_source_manifest_identity(manifest)
    root = _workspace_root(workspace)
    diagnostics = validate_manifest_files(canonical, root)
    if diagnostics:
        codes = ", ".join(sorted({item.code for item in diagnostics}))
        raise ConfigurationError(
            f"{side} SourceManifest does not match its workspace bytes: {codes}"
        )
    return canonical


def build_root_source_manifest(
    *,
    workspace: str | Path,
    generator: GeneratorRef,
    sources: Sequence[str],
    dependencies: Sequence[str] = (),
    artifacts: Sequence[GeneratedArtifactInput] = (),
    parameters: Mapping[str, Any] | None = None,
) -> SourceManifest:
    """Build a bound root SourceManifest from exact bytes in an actual workspace.

    Every listed path must be a normalized workspace-relative POSIX path that resolves
    to a regular file inside ``workspace`` (symlink escapes are rejected). Exact raw-byte
    SHA-256 hashes and sizes are recomputed from disk; nothing is written and no script
    is run. Source, dependency and generated-artifact path sets must be disjoint, and
    every generated artifact must map to declared sources.
    """
    root = _workspace_root(workspace)
    source_files = _collect_files(root, sources, label="Source")
    dependency_files = _collect_files(root, dependencies, label="Dependency")
    artifact_files = [_collect_artifact(root, item) for item in artifacts]
    _validate_disjoint_sets(source_files, dependency_files, artifact_files)
    _validate_artifact_source_mapping(source_files, artifact_files)
    if not source_files:
        raise ConfigurationError("A root SourceManifest requires at least one editable source")
    return bind_source_manifest(
        SourceManifest(
            manifest_sha256="0" * 64,
            lineage_kind="root",
            generator=generator,
            parameters=dict(parameters or {}),
            sources=source_files,
            dependency_files=dependency_files,
            generated_artifacts=artifact_files,
        )
    )


def build_derived_source_manifest(
    *,
    before_manifest: SourceManifest,
    before_workspace: str | Path,
    after_workspace: str | Path,
    plan: ChangePlan,
    generator: GeneratorRef,
    sources: Sequence[str],
    dependencies: Sequence[str] = (),
    artifacts: Sequence[GeneratedArtifactInput] = (),
    parameters: Mapping[str, Any] | None = None,
) -> SourceManifest:
    """Build a bound derived SourceManifest for an actual after workspace.

    The before manifest is checked against its bound identity and its actual before
    workspace bytes. The after source set must then agree exactly with the ChangePlan:
    additions and removals must equal the plan's ``add_source``/``remove_source``
    operations, and every actually changed common source must be declared as a
    ``set_parameter`` operation. ``modified_from`` is inferred from the actual changed
    common paths only when consistent with the plan; otherwise this raises
    ConfigurationError instead of inventing lineage. The generator must equal the plan
    executor so downstream approval/execution binding stays consistent.
    """
    canonical_before = _validated_workspace_manifest(
        before_manifest, before_workspace, side="Before"
    )
    canonical_plan = _verified_plan(plan)
    if generator != canonical_plan.executor:
        raise ConfigurationError(
            "The derived manifest generator must equal the ChangePlan executor"
        )
    before_by_path = {item.path: item for item in canonical_before.sources}
    declared_additions = {
        item.source_path for item in canonical_plan.operations if item.kind == "add_source"
    }
    declared_removals = {
        item.source_path for item in canonical_plan.operations if item.kind == "remove_source"
    }
    declared_changes = {
        item.source_path
        for item in canonical_plan.operations
        if item.kind == "set_parameter"
    }

    after_root = _workspace_root(after_workspace)
    source_files = _collect_files(after_root, sources, label="Source")
    dependency_files = _collect_files(after_root, dependencies, label="Dependency")
    artifact_files = [_collect_artifact(after_root, item) for item in artifacts]
    _validate_disjoint_sets(source_files, dependency_files, artifact_files)
    _validate_artifact_source_mapping(source_files, artifact_files)
    if not source_files:
        raise ConfigurationError(
            "A derived SourceManifest requires at least one editable source"
        )
    after_by_path = {item.path: item for item in source_files}
    after_paths = set(after_by_path)

    added = after_paths - set(before_by_path)
    if added != declared_additions:
        raise ConfigurationError(
            "After-workspace source additions do not match the plan add_source "
            f"operations: actual={sorted(added)} declared={sorted(declared_additions)}"
        )
    removed = set(before_by_path) - after_paths
    if removed != declared_removals:
        raise ConfigurationError(
            "After-workspace source removals do not match the plan remove_source "
            f"operations: actual={sorted(removed)} declared={sorted(declared_removals)}"
        )
    carried = set(before_by_path) & after_paths
    unknown_change_targets = sorted(declared_changes - carried)
    if unknown_change_targets:
        raise ConfigurationError(
            "Plan set_parameter operations must target sources carried from before "
            f"to after: {', '.join(unknown_change_targets)}"
        )
    changed_common = sorted(
        path
        for path in carried
        if before_by_path[path].sha256 != after_by_path[path].sha256
    )
    undeclared_changes = sorted(set(changed_common) - declared_changes)
    if undeclared_changes:
        raise ConfigurationError(
            "Actually changed sources are not declared as set_parameter operations "
            f"in the plan: {', '.join(undeclared_changes)}"
        )
    return bind_source_manifest(
        SourceManifest(
            manifest_sha256="0" * 64,
            lineage_kind="derived",
            parent_manifest_sha256=canonical_before.manifest_sha256,
            generator=generator,
            parameters=dict(parameters or {}),
            sources=source_files,
            dependency_files=dependency_files,
            generated_artifacts=artifact_files,
            modified_from=[
                SourceModification(old_path=path, new_path=path)
                for path in changed_common
            ],
        )
    )


def build_approval_record(
    *,
    request: ChangeRequest,
    plan: ChangePlan,
    approver: str,
    decision: Literal["approved", "rejected"],
    approved_at: str,
) -> ApprovalRecord:
    """Bind an explicit approval to the complete ChangeRequest and ChangePlan.

    Approval is never inferred: ``approver``, ``decision`` and ``approved_at`` must be
    supplied explicitly. The request and plan must match their bound content IDs and
    the plan must belong to the request; otherwise the stale or mismatched inputs are
    rejected with ConfigurationError.
    """
    canonical_request = verify_change_request_identity(request)
    canonical_plan = _verified_plan(plan)
    if canonical_plan.request_id != canonical_request.request_id:
        raise ConfigurationError(
            "The ChangePlan does not belong to the ChangeRequest: request_id mismatch"
        )
    if not isinstance(approver, str) or not approver.strip():
        raise ConfigurationError(
            "An explicit non-empty approver is required; approval is never inferred"
        )
    if not isinstance(approved_at, str) or not approved_at.strip():
        raise ConfigurationError(
            "An explicit non-empty approved_at is required; approval is never inferred"
        )
    return bind_approval_record(
        ApprovalRecord(
            approval_id="0" * 64,
            request_id=canonical_request.request_id,
            plan_id=canonical_plan.plan_id,
            base_artifact_sha256=canonical_request.base_artifact_sha256,
            base_source_manifest_sha256=canonical_request.base_source_manifest_sha256,
            executor=canonical_plan.executor,
            payload_sha256=canonical_plan.payload_sha256,
            approver=approver,
            decision=decision,
            approved_at=approved_at,
        )
    )


def build_execution_record(
    *,
    approval: ApprovalRecord,
    plan: ChangePlan,
    before_manifest: SourceManifest,
    before_workspace: str | Path,
    result: Literal["succeeded", "failed"],
    mode: Literal["attested_local", "observed_external"],
    executed_at: str,
    attested_by: str | None = None,
    attestation: str | None = None,
    log_refs: Sequence[str] = (),
    after_manifest: SourceManifest | None = None,
    after_workspace: str | Path | None = None,
    new_artifact_path: str | Path | None = None,
) -> ExecutionRecord:
    """Bind an explicit execution attestation to an approval, plan and actual outputs.

    Execution is never claimed merely because files exist: ``mode``, ``result``,
    ``executed_at`` and an explicit attestation (``attested_by`` plus the ``attestation``
    statement) must be supplied by the caller. The approval must be bound, approved, and
    consistent with the plan. ``input_sources`` are bound to the before manifest bytes,
    and ``new_sources``/``new_artifact_sha256`` are bound to the after manifest bytes
    and the actual new artifact file. A succeeded execution must identify its actual
    outputs; a failed execution may omit them. The attestation is stored in the
    ExecutionRecord so later verification can identify who attested what.
    """
    if not attested_by or not attested_by.strip():
        raise ConfigurationError(
            "An ExecutionRecord must not claim execution merely because output files "
            "exist: supply an explicit non-empty attested_by identifying who attests the run"
        )
    if not attestation or not attestation.strip():
        raise ConfigurationError(
            "An ExecutionRecord must not claim execution merely because output files "
            "exist: supply an explicit non-empty attestation statement describing the run"
        )
    if not isinstance(executed_at, str) or not executed_at.strip():
        raise ConfigurationError("An explicit non-empty executed_at is required")

    canonical_plan = _verified_plan(plan)
    rebound_approval = bind_approval_record(approval)
    if rebound_approval.approval_id != approval.approval_id:
        raise ConfigurationError(
            "ApprovalRecord content does not match its bound approval_id; "
            "bind the approval before attesting execution"
        )
    if approval.decision != "approved":
        raise ConfigurationError(
            "Execution attestation requires an approved ApprovalRecord, "
            f"got decision={approval.decision!r}"
        )
    mismatches = []
    if approval.request_id != canonical_plan.request_id:
        mismatches.append("request_id")
    if approval.plan_id != canonical_plan.plan_id:
        mismatches.append("plan_id")
    if approval.executor != canonical_plan.executor:
        mismatches.append("executor")
    if approval.payload_sha256 != canonical_plan.payload_sha256:
        mismatches.append("payload_sha256")
    if mismatches:
        raise ConfigurationError(
            "The ApprovalRecord does not match the ChangePlan: " + ", ".join(mismatches)
        )

    canonical_before = _validated_workspace_manifest(
        before_manifest, before_workspace, side="Before"
    )
    base_artifact_known = any(
        item.sha256 == approval.base_artifact_sha256
        for item in canonical_before.generated_artifacts
    )
    if not base_artifact_known:
        raise ConfigurationError(
            "The before SourceManifest does not contain the approved base artifact"
        )
    if (
        approval.base_source_manifest_sha256 is not None
        and approval.base_source_manifest_sha256 != canonical_before.manifest_sha256
    ):
        raise ConfigurationError(
            "The approval was bound to a different before SourceManifest"
        )

    new_sources: list[ManifestFile] = []
    new_source_manifest_sha256: str | None = None
    new_artifact_sha256: str | None = None
    if result == "succeeded" and (
        after_manifest is None or after_workspace is None or new_artifact_path is None
    ):
        raise ConfigurationError(
            "A succeeded execution must identify its actual outputs: provide "
            "after_manifest, after_workspace and new_artifact_path"
        )
    if after_manifest is not None:
        if after_workspace is None:
            raise ConfigurationError(
                "An after workspace is required to bind the after manifest bytes"
            )
        canonical_after = _validated_workspace_manifest(
            after_manifest, after_workspace, side="After"
        )
        new_sources = list(canonical_after.sources)
        new_source_manifest_sha256 = canonical_after.manifest_sha256
        if new_artifact_path is not None:
            new_artifact_sha256 = _hash_artifact_file(new_artifact_path)
            artifact_known = any(
                item.sha256 == new_artifact_sha256
                for item in canonical_after.generated_artifacts
            )
            if not artifact_known:
                raise ConfigurationError(
                    "The new artifact bytes are not declared as a generated artifact "
                    "of the after SourceManifest"
                )
    elif new_artifact_path is not None:
        raise ConfigurationError(
            "A new artifact can only be bound together with the after SourceManifest "
            "that declares it"
        )

    record = ExecutionRecord(
        execution_id="0" * 64,
        approval_id=approval.approval_id,
        request_id=canonical_plan.request_id,
        plan_id=canonical_plan.plan_id,
        executor=canonical_plan.executor,
        input_sources=list(canonical_before.sources),
        base_artifact_sha256=approval.base_artifact_sha256,
        payload_sha256=canonical_plan.payload_sha256,
        new_sources=new_sources,
        new_artifact_sha256=new_artifact_sha256,
        new_source_manifest_sha256=new_source_manifest_sha256,
        result=result,
        mode=mode,
        attested_by=attested_by,
        attestation=attestation,
        log_refs=list(log_refs),
        executed_at=executed_at,
    )
    return bind_execution_record(record)
