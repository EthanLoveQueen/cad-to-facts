import hashlib

import pytest

from cad_to_facts.contract import bind_change_plan, bind_change_request
from cad_to_facts.domain.change import (
    ChangePlan,
    ChangeRequest,
    ComparisonPolicy,
    GeneratorRef,
    OutputPolicy,
    SourceManifest,
    SourceModification,
    SourceOperation,
    TargetBinding,
    ValueCheck,
    VerificationProfile,
)
from cad_to_facts.domain.facts import ExtractionQuery, FactRequest
from cad_to_facts.domain.matching import EntityMatchingProfile
from cad_to_facts.errors import ConfigurationError
from cad_to_facts.manifest import validate_manifest_files
from cad_to_facts.records import (
    GeneratedArtifactInput,
    build_approval_record,
    build_derived_source_manifest,
    build_execution_record,
    build_root_source_manifest,
)

GENERATOR = GeneratorRef(name="text-to-cad", version="0.11.10")
MODEL_BEFORE = b"HEIGHT = 30\n"
MODEL_AFTER = b"HEIGHT = 40\n"
BOX_BEFORE = b"STEP-BEFORE"
BOX_AFTER = b"STEP-AFTER"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _box_artifact() -> GeneratedArtifactInput:
    return GeneratedArtifactInput(path="box.step", format="step", source_paths=["model.py"])


def _before_workspace(tmp_path):
    workspace = tmp_path / "before"
    workspace.mkdir()
    (workspace / "model.py").write_bytes(MODEL_BEFORE)
    (workspace / "box.step").write_bytes(BOX_BEFORE)
    return workspace


def _after_workspace(tmp_path):
    workspace = tmp_path / "after"
    workspace.mkdir()
    (workspace / "model.py").write_bytes(MODEL_AFTER)
    (workspace / "box.step").write_bytes(BOX_AFTER)
    return workspace


def _profile() -> VerificationProfile:
    return VerificationProfile(
        profile_id="0" * 64,
        adapter_id="occt-step",
        adapter_version="0.1.0",
        parser_kernel_version="OCCT-8.0.1",
        parse_options={},
        extractor_version="0.1.0",
        extraction_query_template=ExtractionQuery(
            requests=[
                FactRequest(subject_id="*", predicate="bbox.extent.z", name="height")
            ]
        ),
        matching=EntityMatchingProfile(profile_id="0" * 64, method="adapter_key"),
    )


def _bound_request(base_artifact_sha256, base_source_manifest_sha256=None):
    return bind_change_request(
        ChangeRequest(
            request_id="0" * 64,
            origin_kind="user_intended",
            user_intent="Set box height to 40 mm",
            base_artifact_sha256=base_artifact_sha256,
            base_snapshot_id="snapshot-before",
            base_factset_id="facts-before",
            base_source_manifest_sha256=base_source_manifest_sha256,
            verification_profile=_profile(),
            target_entity_ids=["solid:0"],
            target_checks=[
                ValueCheck(
                    check_id="height-target",
                    subject_id="solid:0",
                    predicate="bbox.extent.z",
                    operator=">=",
                    value=40.0,
                    unit="mm",
                )
            ],
            comparison=ComparisonPolicy(
                required_baseline_entity_ids=["solid:0"],
                data_retention_not_applicable=True,
            ),
            output_policy=OutputPolicy(path="after.step"),
        )
    )


def _bound_plan(request, operations=()):
    return bind_change_plan(
        ChangePlan(
            plan_id="0" * 64,
            request_id=request.request_id,
            executor=GENERATOR,
            target_bindings=[
                TargetBinding(target_entity_id="solid:0", executor_ref="HEIGHT")
            ],
            operations=list(operations),
            payload={"entrypoint": "model.py"},
            payload_sha256="0" * 64,
            baseline_manifest_validation="not_provided",
        )
    )


def _set_height_operation():
    return SourceOperation(
        operation_id="set-height",
        kind="set_parameter",
        source_path="model.py",
        parameter="HEIGHT",
        value=40.0,
    )


def _approval(request, plan, **updates):
    values = {
        "request": request,
        "plan": plan,
        "approver": "local-user",
        "decision": "approved",
        "approved_at": "2026-11-14T00:00:00Z",
    }
    values.update(updates)
    return build_approval_record(**values)


def _execution(approval, plan, before_manifest, before_workspace, after_manifest, after_workspace, **updates):
    values = {
        "approval": approval,
        "plan": plan,
        "before_manifest": before_manifest,
        "before_workspace": before_workspace,
        "after_manifest": after_manifest,
        "after_workspace": after_workspace,
        "new_artifact_path": (
            after_workspace / "box.step" if after_workspace is not None else None
        ),
        "result": "succeeded",
        "mode": "attested_local",
        "executed_at": "2026-11-14T00:01:00Z",
        "attested_by": "local-user",
        "attestation": "Ran the approved plan in the isolated workspace and exported box.step",
        "log_refs": ["run.log"],
    }
    values.update(updates)
    return build_execution_record(**values)


def _source_chain(tmp_path):
    before_workspace = _before_workspace(tmp_path)
    after_workspace = _after_workspace(tmp_path)
    before_manifest = build_root_source_manifest(
        workspace=before_workspace,
        generator=GENERATOR,
        sources=["model.py"],
        artifacts=[_box_artifact()],
    )
    request = _bound_request(
        base_artifact_sha256=_sha(BOX_BEFORE),
        base_source_manifest_sha256=before_manifest.manifest_sha256,
    )
    plan = _bound_plan(request, operations=[_set_height_operation()])
    after_manifest = build_derived_source_manifest(
        before_manifest=before_manifest,
        before_workspace=before_workspace,
        after_workspace=after_workspace,
        plan=plan,
        generator=GENERATOR,
        sources=["model.py"],
        artifacts=[_box_artifact()],
    )
    return before_workspace, after_workspace, before_manifest, request, plan, after_manifest


# --- Root SourceManifest builder -------------------------------------------------


def test_root_manifest_recomputes_exact_bytes_and_binds(tmp_path):
    workspace = _before_workspace(tmp_path)
    (workspace / "uv.lock").write_bytes(b"lock")
    manifest = build_root_source_manifest(
        workspace=workspace,
        generator=GENERATOR,
        sources=["model.py"],
        dependencies=["uv.lock"],
        artifacts=[_box_artifact()],
        parameters={"entrypoint": "model.py"},
    )

    assert manifest.lineage_kind == "root"
    assert manifest.parent_manifest_sha256 is None
    assert manifest.modified_from == []
    source = manifest.sources[0]
    assert source.path == "model.py"
    assert source.sha256 == _sha(MODEL_BEFORE)
    assert source.size_bytes == len(MODEL_BEFORE)
    artifact = manifest.generated_artifacts[0]
    assert artifact.sha256 == _sha(BOX_BEFORE)
    assert artifact.size_bytes == len(BOX_BEFORE)
    assert artifact.source_paths == ["model.py"]
    assert validate_manifest_files(manifest, workspace) == []


def test_root_manifest_is_deterministic_and_order_insensitive(tmp_path):
    workspace = _before_workspace(tmp_path)
    (workspace / "a.py").write_bytes(b"A = 1\n")
    (workspace / "b.py").write_bytes(b"B = 1\n")

    first = build_root_source_manifest(
        workspace=workspace,
        generator=GENERATOR,
        sources=["a.py", "b.py"],
    )
    second = build_root_source_manifest(
        workspace=workspace,
        generator=GENERATOR,
        sources=["b.py", "a.py"],
    )

    assert first.manifest_sha256 == second.manifest_sha256
    assert [item.path for item in first.sources] == ["a.py", "b.py"]


@pytest.mark.parametrize(
    "bad_path",
    [
        "../escape.py",
        "sub/../../escape.py",
        "/absolute.py",
        "C:/absolute.py",
        "a\\b.py",
        "a/./b.py",
        "a//b.py",
        "",
    ],
)
def test_root_manifest_rejects_non_workspace_relative_paths(tmp_path, bad_path):
    with pytest.raises(ConfigurationError, match="workspace-relative"):
        build_root_source_manifest(
            workspace=tmp_path,
            generator=GENERATOR,
            sources=[bad_path],
        )


def test_root_manifest_rejects_missing_files_and_set_overlaps(tmp_path):
    workspace = _before_workspace(tmp_path)
    with pytest.raises(ConfigurationError, match="does not exist"):
        build_root_source_manifest(
            workspace=workspace,
            generator=GENERATOR,
            sources=["ghost.py"],
        )
    with pytest.raises(ConfigurationError, match="both as a source and as a dependency"):
        build_root_source_manifest(
            workspace=workspace,
            generator=GENERATOR,
            sources=["model.py"],
            dependencies=["model.py"],
        )
    with pytest.raises(ConfigurationError, match="unknown source paths"):
        build_root_source_manifest(
            workspace=workspace,
            generator=GENERATOR,
            sources=["model.py"],
            artifacts=[
                GeneratedArtifactInput(
                    path="box.step", format="step", source_paths=["ghost.py"]
                )
            ],
        )


def test_root_manifest_rejects_duplicate_source_paths(tmp_path):
    workspace = _before_workspace(tmp_path)
    with pytest.raises(ConfigurationError, match="Duplicate source paths"):
        build_root_source_manifest(
            workspace=workspace,
            generator=GENERATOR,
            sources=["model.py", "model.py"],
        )


def test_root_manifest_rejects_missing_workspace(tmp_path):
    with pytest.raises(ConfigurationError, match="Workspace directory does not exist"):
        build_root_source_manifest(
            workspace=tmp_path / "ghost",
            generator=GENERATOR,
            sources=["model.py"],
        )


# --- Derived SourceManifest builder ------------------------------------------------


def test_derived_manifest_binds_parent_and_infers_modified_from(tmp_path):
    before_workspace, after_workspace, before_manifest, _, plan, _ = _source_chain(tmp_path)

    after_manifest = build_derived_source_manifest(
        before_manifest=before_manifest,
        before_workspace=before_workspace,
        after_workspace=after_workspace,
        plan=plan,
        generator=GENERATOR,
        sources=["model.py"],
        artifacts=[_box_artifact()],
    )

    assert after_manifest.lineage_kind == "derived"
    assert after_manifest.parent_manifest_sha256 == before_manifest.manifest_sha256
    assert after_manifest.modified_from == [
        SourceModification(old_path="model.py", new_path="model.py")
    ]
    source = after_manifest.sources[0]
    assert source.sha256 == _sha(MODEL_AFTER)
    assert source.size_bytes == len(MODEL_AFTER)
    assert after_manifest.generated_artifacts[0].sha256 == _sha(BOX_AFTER)
    assert validate_manifest_files(after_manifest, after_workspace) == []


def test_derived_manifest_is_deterministic(tmp_path):
    before_workspace, after_workspace, before_manifest, _, plan, after_manifest = (
        _source_chain(tmp_path)
    )

    again = build_derived_source_manifest(
        before_manifest=before_manifest,
        before_workspace=before_workspace,
        after_workspace=after_workspace,
        plan=plan,
        generator=GENERATOR,
        sources=["model.py"],
        artifacts=[_box_artifact()],
    )

    assert again.manifest_sha256 == after_manifest.manifest_sha256


def test_derived_manifest_rejects_undeclared_source_change(tmp_path):
    before_workspace, after_workspace, before_manifest, request, _, _ = _source_chain(tmp_path)
    plan = _bound_plan(request, operations=[])

    with pytest.raises(ConfigurationError, match="set_parameter"):
        build_derived_source_manifest(
            before_manifest=before_manifest,
            before_workspace=before_workspace,
            after_workspace=after_workspace,
            plan=plan,
            generator=GENERATOR,
            sources=["model.py"],
        )


def test_derived_manifest_rejects_unplanned_additions_and_removals(tmp_path):
    before_workspace, after_workspace, before_manifest, request, _, _ = _source_chain(tmp_path)
    (after_workspace / "extra.py").write_bytes(b"EXTRA = True\n")
    plan = _bound_plan(
        request,
        operations=[_set_height_operation()],
    )
    with pytest.raises(ConfigurationError, match="add_source"):
        build_derived_source_manifest(
            before_manifest=before_manifest,
            before_workspace=before_workspace,
            after_workspace=after_workspace,
            plan=plan,
            generator=GENERATOR,
            sources=["model.py", "extra.py"],
        )

    plan = _bound_plan(
        request,
        operations=[
            _set_height_operation(),
            SourceOperation(
                operation_id="add-extra",
                kind="add_source",
                source_path="extra.py",
            ),
        ],
    )
    (before_workspace / "old.py").write_bytes(b"OLD = True\n")
    before_manifest = build_root_source_manifest(
        workspace=before_workspace,
        generator=GENERATOR,
        sources=["model.py", "old.py"],
        artifacts=[_box_artifact()],
    )
    with pytest.raises(ConfigurationError, match="remove_source"):
        build_derived_source_manifest(
            before_manifest=before_manifest,
            before_workspace=before_workspace,
            after_workspace=after_workspace,
            plan=plan,
            generator=GENERATOR,
            sources=["model.py", "extra.py"],
        )


def test_derived_manifest_rejects_stale_before_manifest(tmp_path):
    before_workspace, after_workspace, before_manifest, _, plan, _ = _source_chain(tmp_path)
    (before_workspace / "model.py").write_bytes(b"HEIGHT = 99\n")

    with pytest.raises(ConfigurationError, match="Before SourceManifest"):
        build_derived_source_manifest(
            before_manifest=before_manifest,
            before_workspace=before_workspace,
            after_workspace=after_workspace,
            plan=plan,
            generator=GENERATOR,
            sources=["model.py"],
        )


def test_derived_manifest_rejects_generator_mismatch(tmp_path):
    before_workspace, after_workspace, before_manifest, _, plan, _ = _source_chain(tmp_path)

    with pytest.raises(ConfigurationError, match="executor"):
        build_derived_source_manifest(
            before_manifest=before_manifest,
            before_workspace=before_workspace,
            after_workspace=after_workspace,
            plan=plan,
            generator=GeneratorRef(name="other-generator", version="9.9.9"),
            sources=["model.py"],
        )


def test_derived_manifest_allows_declared_change_without_byte_change(tmp_path):
    before_workspace, after_workspace, before_manifest, request, _, _ = _source_chain(tmp_path)
    (before_workspace / "config.py").write_bytes(b"MODE = 'release'\n")
    (after_workspace / "config.py").write_bytes(b"MODE = 'release'\n")
    before_manifest = build_root_source_manifest(
        workspace=before_workspace,
        generator=GENERATOR,
        sources=["model.py", "config.py"],
        artifacts=[_box_artifact()],
    )
    plan = _bound_plan(
        request,
        operations=[
            _set_height_operation(),
            SourceOperation(
                operation_id="set-config",
                kind="set_parameter",
                source_path="config.py",
                parameter="MODE",
                value="release",
            ),
        ],
    )

    after_manifest = build_derived_source_manifest(
        before_manifest=before_manifest,
        before_workspace=before_workspace,
        after_workspace=after_workspace,
        plan=plan,
        generator=GENERATOR,
        sources=["model.py", "config.py"],
    )

    assert [item.old_path for item in after_manifest.modified_from] == ["model.py"]


# --- ApprovalRecord builder ---------------------------------------------------------


def test_approval_binds_complete_request_and_plan(tmp_path):
    scenario_before = _before_workspace(tmp_path)
    before_manifest = build_root_source_manifest(
        workspace=scenario_before,
        generator=GENERATOR,
        sources=["model.py"],
        artifacts=[_box_artifact()],
    )
    request = _bound_request(
        base_artifact_sha256=_sha(BOX_BEFORE),
        base_source_manifest_sha256=before_manifest.manifest_sha256,
    )
    plan = _bound_plan(request, operations=[_set_height_operation()])

    approval = _approval(request, plan)

    assert approval.request_id == request.request_id
    assert approval.plan_id == plan.plan_id
    assert approval.base_artifact_sha256 == request.base_artifact_sha256
    assert approval.base_source_manifest_sha256 == before_manifest.manifest_sha256
    assert approval.executor == plan.executor
    assert approval.payload_sha256 == plan.payload_sha256
    assert approval.approval_id != "0" * 64
    assert _approval(request, plan).approval_id == approval.approval_id


def test_approval_rejects_mismatched_plan(tmp_path):
    request = _bound_request(base_artifact_sha256=_sha(BOX_BEFORE))
    other_request = _bound_request(base_artifact_sha256="a" * 64)
    plan = _bound_plan(other_request)

    with pytest.raises(ConfigurationError, match="request_id"):
        _approval(request, plan)


def test_approval_rejects_tampered_request_and_plan(tmp_path):
    request = _bound_request(base_artifact_sha256=_sha(BOX_BEFORE))
    plan = _bound_plan(request)
    tampered_request = request.model_copy(
        update={"target_checks": [request.target_checks[0].model_copy(update={"value": 41.0})]}
    )
    with pytest.raises(ConfigurationError, match="request_id"):
        _approval(tampered_request, plan)

    request = _bound_request(base_artifact_sha256=_sha(BOX_BEFORE))
    tampered_plan = plan.model_copy(update={"payload": {"entrypoint": "other.py"}})
    with pytest.raises(ConfigurationError, match="plan_id"):
        _approval(request, tampered_plan)


def test_approval_requires_explicit_fields(tmp_path):
    request = _bound_request(base_artifact_sha256=_sha(BOX_BEFORE))
    plan = _bound_plan(request)

    with pytest.raises(ConfigurationError, match="approver"):
        _approval(request, plan, approver="")
    with pytest.raises(ConfigurationError, match="approved_at"):
        _approval(request, plan, approved_at=" ")


def test_approval_is_never_inferred_and_explicit_rejection_is_bound(tmp_path):
    request = _bound_request(base_artifact_sha256=_sha(BOX_BEFORE))
    plan = _bound_plan(request)

    rejected = _approval(request, plan, decision="rejected")

    assert rejected.decision == "rejected"
    assert rejected.approver == "local-user"
    assert rejected.approved_at == "2026-11-14T00:00:00Z"


# --- ExecutionRecord builder --------------------------------------------------------


def test_execution_binds_manifest_bytes_and_actual_outputs(tmp_path):
    (
        before_workspace,
        after_workspace,
        before_manifest,
        request,
        plan,
        after_manifest,
    ) = _source_chain(tmp_path)
    approval = _approval(request, plan)

    execution = _execution(
        approval, plan, before_manifest, before_workspace, after_manifest, after_workspace
    )

    assert execution.approval_id == approval.approval_id
    assert execution.request_id == request.request_id
    assert execution.plan_id == plan.plan_id
    assert execution.executor == plan.executor
    assert execution.base_artifact_sha256 == request.base_artifact_sha256
    assert execution.payload_sha256 == plan.payload_sha256
    assert execution.input_sources == before_manifest.sources
    assert execution.new_sources == after_manifest.sources
    assert execution.new_source_manifest_sha256 == after_manifest.manifest_sha256
    assert execution.new_artifact_sha256 == _sha(BOX_AFTER)
    assert execution.result == "succeeded"
    assert execution.mode == "attested_local"
    assert execution.attested_by == "local-user"
    assert execution.attestation == (
        "Ran the approved plan in the isolated workspace and exported box.step"
    )
    assert execution.log_refs == ["run.log"]
    assert execution.execution_id != "0" * 64
    again = _execution(
        approval, plan, before_manifest, before_workspace, after_manifest, after_workspace
    )
    assert again.execution_id == execution.execution_id


def test_execution_refuses_omitted_attestation(tmp_path):
    (
        before_workspace,
        after_workspace,
        before_manifest,
        request,
        plan,
        after_manifest,
    ) = _source_chain(tmp_path)
    approval = _approval(request, plan)

    with pytest.raises(ConfigurationError, match="attested_by"):
        _execution(
            approval,
            plan,
            before_manifest,
            before_workspace,
            after_manifest,
            after_workspace,
            attested_by=None,
        )
    with pytest.raises(ConfigurationError, match="attestation statement"):
        _execution(
            approval,
            plan,
            before_manifest,
            before_workspace,
            after_manifest,
            after_workspace,
            attestation=" ",
        )


def test_execution_rejects_mismatched_or_unapproved_approval(tmp_path):
    (
        before_workspace,
        after_workspace,
        before_manifest,
        request,
        plan,
        after_manifest,
    ) = _source_chain(tmp_path)
    approval = _approval(request, plan)

    changed_plan = bind_change_plan(
        plan.model_copy(update={"payload": {"entrypoint": "other.py"}})
    )
    with pytest.raises(ConfigurationError, match="ApprovalRecord does not match"):
        _execution(
            approval,
            changed_plan,
            before_manifest,
            before_workspace,
            after_manifest,
            after_workspace,
        )

    rejected = _approval(request, plan, decision="rejected")
    with pytest.raises(ConfigurationError, match="approved"):
        _execution(
            rejected,
            plan,
            before_manifest,
            before_workspace,
            after_manifest,
            after_workspace,
        )

    tampered = approval.model_copy(update={"approver": "someone-else"})
    with pytest.raises(ConfigurationError, match="approval_id"):
        _execution(
            tampered,
            plan,
            before_manifest,
            before_workspace,
            after_manifest,
            after_workspace,
        )


def test_execution_rejects_tampered_after_manifest_bytes(tmp_path):
    (
        before_workspace,
        after_workspace,
        before_manifest,
        request,
        plan,
        after_manifest,
    ) = _source_chain(tmp_path)
    approval = _approval(request, plan)
    (after_workspace / "box.step").write_bytes(b"STEP-TAMPERED")

    with pytest.raises(ConfigurationError, match="After SourceManifest"):
        _execution(
            approval,
            plan,
            before_manifest,
            before_workspace,
            after_manifest,
            after_workspace,
        )


def test_execution_rejects_artifact_not_declared_in_after_manifest(tmp_path):
    (
        before_workspace,
        after_workspace,
        before_manifest,
        request,
        plan,
        after_manifest,
    ) = _source_chain(tmp_path)
    approval = _approval(request, plan)
    stray = tmp_path / "stray.step"
    stray.write_bytes(b"STEP-STRAY")

    with pytest.raises(ConfigurationError, match="generated artifact"):
        _execution(
            approval,
            plan,
            before_manifest,
            before_workspace,
            after_manifest,
            after_workspace,
            new_artifact_path=stray,
        )


def test_execution_succeeded_requires_actual_outputs(tmp_path):
    (
        before_workspace,
        _,
        before_manifest,
        request,
        plan,
        _,
    ) = _source_chain(tmp_path)
    approval = _approval(request, plan)

    with pytest.raises(ConfigurationError, match="actual outputs"):
        _execution(
            approval,
            plan,
            before_manifest,
            before_workspace,
            None,
            None,
            new_artifact_path=None,
        )


def test_execution_failed_may_attest_without_new_outputs(tmp_path):
    (
        before_workspace,
        _,
        before_manifest,
        request,
        plan,
        _,
    ) = _source_chain(tmp_path)
    approval = _approval(request, plan)

    execution = _execution(
        approval,
        plan,
        before_manifest,
        before_workspace,
        None,
        None,
        new_artifact_path=None,
        result="failed",
        log_refs=["run.log", "stderr.log"],
    )

    assert execution.result == "failed"
    assert execution.new_artifact_sha256 is None
    assert execution.new_source_manifest_sha256 is None
    assert execution.new_sources == []
    assert execution.input_sources == before_manifest.sources
