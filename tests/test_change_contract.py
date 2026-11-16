import pytest

from cad_to_facts.contract import (
    bind_approval_record,
    bind_change_plan,
    bind_change_request,
    bind_execution_record,
    bind_source_manifest,
)
from cad_to_facts.domain.change import (
    ApprovalRecord,
    ChangePlan,
    ChangeRequest,
    ComparisonPolicy,
    ExecutionRecord,
    GeneratedArtifact,
    ManifestFile,
    OutputPolicy,
    SourceManifest,
    SourceOperation,
    TargetBinding,
    ValueCheck,
    VerificationProfile,
)
from cad_to_facts.domain.facts import ExtractionQuery, FactRequest
from cad_to_facts.domain.matching import EntityMatchingProfile
from cad_to_facts.manifest import validate_manifest_files


def _file(path, sha256):
    return ManifestFile(path=path, sha256=sha256, size_bytes=1)


def test_manifest_lineage_is_explicit_and_validated():
    with pytest.raises(ValueError, match="derived manifest requires"):
        SourceManifest(
            manifest_sha256="0" * 64,
            lineage_kind="derived",
            generator={"name": "text-to-cad", "version": "0.11.10"},
            sources=[_file("model.py", "a" * 64)],
        )

    with pytest.raises(ValueError, match="root manifest cannot"):
        SourceManifest(
            manifest_sha256="0" * 64,
            lineage_kind="root",
            parent_manifest_sha256="b" * 64,
            generator={"name": "text-to-cad", "version": "0.11.10"},
            sources=[_file("model.py", "a" * 64)],
        )


def test_manifest_identity_ignores_unordered_file_order_but_not_content():
    first = SourceManifest(
        manifest_sha256="0" * 64,
        lineage_kind="root",
        generator={"name": "text-to-cad", "version": "0.11.10"},
        sources=[_file("b.py", "b" * 64), _file("a.py", "a" * 64)],
        dependency_files=[_file("uv.lock", "c" * 64)],
    )
    second = first.model_copy(update={"sources": list(reversed(first.sources))})
    changed = first.model_copy(
        update={"sources": [_file("a.py", "d" * 64), first.sources[0]]}
    )

    bound = bind_source_manifest(first)

    assert bind_source_manifest(second).manifest_sha256 == bound.manifest_sha256
    assert bind_source_manifest(changed).manifest_sha256 != bound.manifest_sha256
    assert [item.path for item in bound.sources] == ["a.py", "b.py"]


def test_manifest_file_validation_checks_actual_bytes(tmp_path):
    (tmp_path / "model.py").write_bytes(b"HEIGHT = 30\n")
    (tmp_path / "box.step").write_bytes(b"STEP-BEFORE")
    source_bytes = (tmp_path / "model.py").read_bytes()
    artifact_bytes = (tmp_path / "box.step").read_bytes()
    import hashlib

    manifest = bind_source_manifest(
        SourceManifest(
            manifest_sha256="0" * 64,
            lineage_kind="root",
            generator={"name": "text-to-cad", "version": "0.11.10"},
            sources=[
                ManifestFile(
                    path="model.py",
                    sha256=hashlib.sha256(source_bytes).hexdigest(),
                    size_bytes=len(source_bytes),
                )
            ],
            generated_artifacts=[
                GeneratedArtifact(
                    path="box.step",
                    sha256=hashlib.sha256(artifact_bytes).hexdigest(),
                    size_bytes=len(artifact_bytes),
                    format="step",
                    source_paths=["model.py"],
                )
            ],
        )
    )

    assert validate_manifest_files(manifest, tmp_path) == []

    (tmp_path / "model.py").write_bytes(b"HEIGHT = 40\n")
    diagnostics = validate_manifest_files(manifest, tmp_path)

    assert [diagnostic.code for diagnostic in diagnostics] == ["SOURCE_HASH_MISMATCH"]
    assert diagnostics[0].impact == "fatal"


def test_change_request_identity_binds_checks_and_tolerances():
    profile = VerificationProfile(
        profile_id="0" * 64,
        adapter_id="occt-step",
        adapter_version="0.1.0",
        parser_kernel_version="OCCT-8.0.1",
        parse_options={"read_precision_mode": 0},
        extractor_version="0.1.0",
        extraction_query_template=ExtractionQuery(
            requests=[
                FactRequest(
                    subject_id="*",
                    predicate="bbox.extent.z",
                    name="height",
                )
            ]
        ),
        matching=EntityMatchingProfile(
            profile_id="0" * 64,
            method="adapter_key",
        ),
    )
    request = ChangeRequest(
        request_id="0" * 64,
        origin_kind="user_intended",
        user_intent="Set box height to at least 40 mm",
        base_artifact_sha256="a" * 64,
        base_snapshot_id="snapshot-before",
        base_factset_id="facts-before",
        verification_profile=profile,
        target_entity_ids=["solid:0"],
        target_checks=[
            ValueCheck(
                check_id="height-minimum",
                subject_id="solid:0",
                predicate="bbox.extent.z",
                operator=">=",
                value=40.0,
                unit="mm",
            ),
            ValueCheck(
                check_id="width-invariant",
                subject_id="solid:0",
                predicate="bbox.extent.x",
                operator="==",
                value=10.0,
                unit="mm",
            ),
        ],
        comparison=ComparisonPolicy(
            required_baseline_entity_ids=["solid:0"],
            data_retention_not_applicable=True,
        ),
        output_policy=OutputPolicy(path="after.step"),
    )

    bound = bind_change_request(request)
    reordered = request.model_copy(
        update={"target_checks": list(reversed(request.target_checks))}
    )
    changed = request.model_copy(
        update={
            "target_checks": [
                request.target_checks[0].model_copy(update={"value": 41.0}),
                request.target_checks[1],
            ]
        }
    )

    assert bind_change_request(reordered).request_id == bound.request_id
    assert bind_change_request(changed).request_id != bound.request_id
    assert bound.target_checks[0].check_id == "height-minimum"


def test_change_request_forbids_base_overwrite():
    with pytest.raises(ValueError):
        OutputPolicy(path="before.step", overwrite_base=True)


def test_change_plan_identity_binds_operations_payload_and_executor():
    plan = ChangePlan(
        plan_id="0" * 64,
        request_id="a" * 64,
        executor={"name": "text-to-cad", "version": "0.11.10"},
        target_bindings=[
            TargetBinding(target_entity_id="solid:0", executor_ref="HEIGHT"),
            TargetBinding(target_entity_id="solid:1", executor_ref="WIDTH"),
        ],
        operations=[
            SourceOperation(
                operation_id="set-height",
                kind="set_parameter",
                source_path="model.py",
                parameter="HEIGHT",
                value=40.0,
            ),
            SourceOperation(
                operation_id="set-width",
                kind="set_parameter",
                source_path="model.py",
                parameter="WIDTH",
                value=10.0,
            ),
        ],
        expected_invalidated_refs=["solid:0"],
        payload={"entrypoint": "model.py"},
        payload_sha256="0" * 64,
        baseline_manifest_validation="passed",
    )

    bound = bind_change_plan(plan)
    reordered = plan.model_copy(
        update={
            "target_bindings": list(reversed(plan.target_bindings)),
            "operations": list(reversed(plan.operations)),
        }
    )
    changed_operation = plan.model_copy(
        update={
            "operations": [
                plan.operations[0].model_copy(update={"value": 41.0}),
                plan.operations[1],
            ]
        }
    )
    changed_payload = plan.model_copy(update={"payload": {"entrypoint": "other.py"}})

    assert bind_change_plan(reordered).plan_id == bound.plan_id
    assert bind_change_plan(changed_operation).plan_id != bound.plan_id
    assert bind_change_plan(changed_payload).plan_id != bound.plan_id
    assert bound.payload_sha256 != "0" * 64


def test_approval_and_execution_ids_bind_the_complete_records():
    approval = ApprovalRecord(
        approval_id="0" * 64,
        request_id="a" * 64,
        plan_id="b" * 64,
        base_artifact_sha256="c" * 64,
        base_source_manifest_sha256="d" * 64,
        executor={"name": "text-to-cad", "version": "0.11.10"},
        payload_sha256="e" * 64,
        approver="local-user",
        decision="approved",
        approved_at="2026-11-14T00:00:00Z",
    )
    bound_approval = bind_approval_record(approval)

    assert bind_approval_record(
        approval.model_copy(update={"plan_id": "f" * 64})
    ).approval_id != bound_approval.approval_id
    assert bind_approval_record(
        approval.model_copy(update={"approved_at": "2026-11-14T00:02:00Z"})
    ).approval_id != bound_approval.approval_id

    execution = ExecutionRecord(
        execution_id="0" * 64,
        approval_id=bound_approval.approval_id,
        request_id=approval.request_id,
        plan_id=approval.plan_id,
        executor=approval.executor,
        input_sources=[_file("model.py", "1" * 64)],
        base_artifact_sha256=approval.base_artifact_sha256,
        payload_sha256=approval.payload_sha256,
        new_sources=[_file("model.py", "2" * 64)],
        new_artifact_sha256="3" * 64,
        new_source_manifest_sha256="4" * 64,
        result="succeeded",
        mode="attested_local",
        log_refs=["run.log"],
        executed_at="2026-11-14T00:01:00Z",
    )
    bound_execution = bind_execution_record(execution)

    assert bind_execution_record(
        execution.model_copy(update={"new_artifact_sha256": "5" * 64})
    ).execution_id != bound_execution.execution_id
    assert bind_execution_record(
        execution.model_copy(update={"executed_at": "2026-11-14T00:03:00Z"})
    ).execution_id != bound_execution.execution_id
