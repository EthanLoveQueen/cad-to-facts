"""Prepare neutral design-side process inputs without planning manufacturing."""

from cad_to_facts import __version__
from cad_to_facts.contract import (
    bind_context,
    verify_factset_identity,
    verify_snapshot_identity,
)
from cad_to_facts.domain.facts import FactSet
from cad_to_facts.domain.process import (
    ProcessCardInput,
    ProcessCoverage,
    ProcessEntity,
    ProcessExternalInput,
    ProcessInputOptions,
    ProcessMissingInput,
)
from cad_to_facts.domain.review import ReviewContext
from cad_to_facts.domain.snapshot import Diagnostic, ModelSnapshot
from cad_to_facts.identity import structured_hash


GEOMETRY_PREDICATES = ("volume", "area", "bbox.extent.x", "bbox.extent.y", "bbox.extent.z")
_DESIGN_INPUT_MESSAGES = {
    "declared_material": "STEP declared-material extraction is not implemented; user context is not a declared file fact",
    "semantic_pmi": "Semantic PMI can be extracted with 'facts pmi' but is not projected into ProcessCardInput; no dimensions or tolerances are inferred",
    "validated_features": "Validated feature extraction is not implemented; no hole, pocket or fillet candidates are invented",
}
_FORBIDDEN_CONTEXT_KEYS = {
    "operations", "operation_sequence", "setups", "setup_plan", "machine_selection",
    "tool_selection", "cutting_parameters", "cycle_time", "process_route",
}


def _validate_context_values(values) -> None:
    if isinstance(values, dict):
        for key, value in values.items():
            if key in _FORBIDDEN_CONTEXT_KEYS:
                raise ValueError(
                    f"Process-planning decision {key!r} is outside the process-input scope"
                )
            _validate_context_values(value)
    elif isinstance(values, list):
        for value in values:
            _validate_context_values(value)


def prepare(
    snapshot: ModelSnapshot,
    factset: FactSet,
    context: ReviewContext,
    options: ProcessInputOptions | None = None,
) -> ProcessCardInput:
    """Project verified facts and explicit context into a neutral work product."""

    snapshot = verify_snapshot_identity(snapshot)
    factset = verify_factset_identity(factset)
    if (
        factset.snapshot_id != snapshot.snapshot_id
        or factset.snapshot_content_hash != snapshot.snapshot_content_hash
    ):
        raise ValueError("FactSet does not belong to the supplied snapshot")
    if bind_context(context).context_id != context.context_id:
        raise ValueError("ReviewContext content identity is stale")
    _validate_context_values(context.values)
    options = options or ProcessInputOptions()
    if snapshot.drawing is not None:
        raise ValueError("process-input currently requires a STEP single-part snapshot")

    missing: list[ProcessMissingInput] = []
    entities: list[ProcessEntity] = []
    required_design = set(options.required_design_inputs)
    for entity in sorted(snapshot.entities, key=lambda item: item.entity_id):
        facts = sorted(
            [fact for fact in factset.facts if fact.subject.entity_id == entity.entity_id],
            key=lambda fact: (fact.predicate, fact.fact_id),
        )
        gaps = sorted(
            [
                gap for gap in factset.gaps
                if gap.subject is not None and gap.subject.entity_id == entity.entity_id
            ],
            key=lambda gap: (gap.request.predicate, gap.reason_code),
        )
        present = {fact.predicate for fact in facts}
        for predicate in GEOMETRY_PREDICATES:
            if predicate in present:
                continue
            matching = [gap for gap in gaps if gap.request.predicate == predicate]
            reason = matching[0].reason_code if matching else "NOT_COMPUTED"
            missing.append(ProcessMissingInput(
                subject_id=entity.entity_id,
                field=f"geometry.{predicate}",
                reason_code=reason,
                required=True,
                message=f"Required geometry fact {predicate} is unavailable ({reason})",
            ))
        for field, message in _DESIGN_INPUT_MESSAGES.items():
            missing.append(ProcessMissingInput(
                subject_id=entity.entity_id,
                field=field,
                reason_code="UNSUPPORTED",
                required=field in required_design,
                message=message,
            ))
        entities.append(ProcessEntity(entity=entity, facts=facts, gaps=gaps))

    if len(snapshot.entities) != 1:
        missing.append(ProcessMissingInput(
            subject_id="snapshot",
            field="part_identity",
            reason_code="NOT_COMPUTED",
            required=True,
            message="process-input requires exactly one discovered solid; none is selected implicitly",
        ))

    external: list[ProcessExternalInput] = []
    for name in sorted(context.values):
        value = context.values[name]
        if value is not None:
            external.append(ProcessExternalInput(name=name, value=value))
    for name in sorted(set(options.required_context)):
        if name not in context.values or context.values[name] is None:
            missing.append(ProcessMissingInput(
                subject_id="context",
                field=name,
                reason_code="ABSENT",
                required=True,
                message=f"Required user-supplied process context {name!r} is absent",
            ))

    diagnostics = list(snapshot.diagnostics) + list(factset.diagnostics)
    if len(snapshot.entities) != 1:
        diagnostics.append(Diagnostic(
            code="PROCESS_SINGLE_PART_REQUIRED",
            severity="warning",
            stage="translate",
            message=f"Expected one solid for process input, discovered {len(snapshot.entities)}",
            scope_refs=["snapshot"],
            affects=["process_input"],
            impact="partial",
            discovery_impact="none",
        ))
    missing.sort(key=lambda item: (item.subject_id, item.field, item.reason_code))
    required_missing = sum(item.required for item in missing)
    optional_missing = len(missing) - required_missing
    fully_measured = sum(
        len([fact for fact in entity.facts if fact.predicate in GEOMETRY_PREDICATES])
        == len(GEOMETRY_PREDICATES)
        for entity in entities
    )
    unresolved_diagnostic = any(
        item.disposition != "resolved"
        and (item.impact != "none" or item.discovery_impact != "none")
        for item in diagnostics
    )
    complete = bool(
        snapshot.status == "ready"
        and snapshot.entity_discovery == "complete"
        and len(snapshot.entities) == 1
        and fully_measured == 1
        and required_missing == 0
        and not unresolved_diagnostic
    )
    result = ProcessCardInput(
        process_input_id="0" * 64,
        artifact_sha256=snapshot.artifact_sha256,
        snapshot_id=snapshot.snapshot_id,
        snapshot_content_hash=snapshot.snapshot_content_hash,
        factset_id=factset.factset_id,
        context_id=context.context_id,
        preparer_version=__version__,
        options=options,
        entities=entities,
        external_inputs=external,
        missing_inputs=missing,
        coverage=ProcessCoverage(
            entity_total=len(entities),
            fully_measured_entity_total=fully_measured,
            required_missing_total=required_missing,
            optional_missing_total=optional_missing,
            structure_discovery=snapshot.entity_discovery,
        ),
        diagnostics=diagnostics,
        complete=complete,
    )
    return result.model_copy(update={
        "process_input_id": structured_hash(
            "process-card-input", result, exclude={"process_input_id"}
        )
    })
